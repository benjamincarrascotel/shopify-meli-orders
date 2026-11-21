"""The purchase run against fakes: what gets written to Shopify, and in which order."""
from contextlib import contextmanager

import pytest

from conftest import PRODUCT, order
from meli_orders import browser, config, ledger, run as run_module, shopify
from meli_orders.meli import checkout, session
from meli_orders.meli.checkout import Review
from meli_orders.orders import ListingProblem, OrderProblem, TAG_CHECK, TAG_MANUAL, TAG_PURCHASED


class Page:
    def screenshot(self, **_):
        pass

    def content(self):
        return ""


@pytest.fixture
def world(home, monkeypatch):
    """Fake Shopify and Mercado Libre; `calls` is everything the run did, in order."""
    state = {"orders": [order()], "calls": [], "review": Review(1, 11980, 2990, 13990, 50000, "Los Aromos 1234", "Llega mañana"),
             "confirmed": True, "prepare_error": None}
    calls = state["calls"]

    @contextmanager
    def fake_session(slug):
        yield Page()

    def prepare(page, listing, units, who):
        calls.append(("prepare", listing["seller"]))
        error = state["prepare_error"]
        if error and (not isinstance(error, dict) or listing["seller"] in error):
            raise error[listing["seller"]] if isinstance(error, dict) else error
        return state["review"]

    monkeypatch.setattr(browser, "session", fake_session)
    monkeypatch.setattr(session, "ensure", lambda *a: None)
    monkeypatch.setattr(checkout, "prepare", prepare)
    monkeypatch.setattr(checkout, "select_wallet", lambda *a: state["review"])
    monkeypatch.setattr(checkout, "pay", lambda page: calls.append(("pay",)))
    monkeypatch.setattr(checkout, "confirmed", lambda page, minutes: state["confirmed"])
    monkeypatch.setattr(checkout, "latest_purchase_id", lambda *a: "555")
    monkeypatch.setattr(shopify, "open_paid_orders", lambda domain: state["orders"])
    monkeypatch.setattr(shopify, "add_tag", lambda d, i, tag: calls.append(("tag+", tag)))
    monkeypatch.setattr(shopify, "remove_tag", lambda d, i, tag: calls.append(("tag-", tag)))
    monkeypatch.setattr(shopify, "append_note", lambda d, o, line: calls.append(("note", line)))
    monkeypatch.setattr(shopify, "fulfill", lambda d, i: calls.append(("fulfill",)))
    return state


def kinds(calls):
    return [c if len(c) == 1 or c[0] in ("tag+", "tag-") else c[:1] for c in calls]


def test_auto_purchase_tags_before_paying_and_fulfils_after_confirmation(world):
    results = run_module.run("demo")
    assert results[0]["result"] == "purchased" and results[0]["purchase_id"] == "555" and results[0]["fulfilled"]
    assert kinds(world["calls"]) == [("prepare",), ("tag+", TAG_CHECK), ("pay",), ("tag+", TAG_PURCHASED),
                                     ("tag-", TAG_CHECK), ("note",), ("fulfill",)]
    assert ledger.spent_today("demo") == 11980


def test_unconfirmed_payment_never_fulfils_and_never_says_not_bought(world):
    world["confirmed"] = False
    results = run_module.run("demo")
    assert results[0]["result"] == "unconfirmed"
    assert kinds(world["calls"]) == [("prepare",), ("tag+", TAG_CHECK), ("pay",)]
    assert run_module.exit_code(results) == run_module.EXIT_ERROR


def test_crash_after_the_pay_click_is_unconfirmed_not_manual(world, monkeypatch):
    monkeypatch.setattr(checkout, "confirmed", lambda page, minutes: 1 / 0)
    results = run_module.run("demo")
    assert results[0]["result"] == "unconfirmed"
    assert ("tag+", TAG_MANUAL) not in world["calls"] and ("fulfill",) not in world["calls"]


def test_first_purchase_waits_then_keeps_asking_until_the_user_chooses(world):
    config.save_product("demo", PRODUCT | {"approval": {"mode": "first_purchase_pending", "first_order": None, "decided_at": None}})
    waiting = run_module.run("demo")
    assert waiting[0]["result"] == "needs_approval" and waiting[0]["first_purchase"] and waiting[0]["balance_after"] == 50000 - 11980
    assert ("pay",) not in world["calls"]
    bought = run_module.run("demo", approve="#10")
    assert bought[0]["result"] == "purchased" and bought[0]["ask_approval_mode"]
    assert config.product("demo", "scratcher")["approval"]["mode"] == "each_purchase"


def test_an_approval_does_not_cover_a_higher_total(world):
    config.save_product("demo", PRODUCT | {"approval": {"mode": "each_purchase", "first_order": "#1", "decided_at": None}})
    run_module.run("demo")
    world["review"] = Review(1, 12500, 2990, 13990, 50000, "Los Aromos 1234", None)
    assert run_module.run("demo", approve="#10")[0]["result"] == "needs_approval"
    assert run_module.run("demo", approve="#10")[0]["result"] == "purchased"


def test_fallback_listing_is_used_when_the_main_one_fails(world):
    world["prepare_error"] = {"Main Seller": ListingProblem("seller_changed", seller="Main Seller")}
    results = run_module.run("demo")
    assert results[0]["result"] == "purchased" and results[0]["seller"] == "Backup Seller"


def test_order_that_cannot_be_bought_is_flagged_and_left_unfulfilled(world):
    world["prepare_error"] = OrderProblem("address_not_found", street="Los Aromos 1234", city="Ñuñoa")
    results = run_module.run("demo")
    assert results[0]["result"] == "manual" and "Los Aromos 1234" in results[0]["text"]
    assert kinds(world["calls"]) == [("prepare",), ("tag+", TAG_MANUAL), ("note",)]


def test_a_dearer_delivery_never_blocks_a_purchase(world):
    world["review"] = Review(1, 9000 + 25000, 25000, 9000, 50000, "Los Aromos 1234", None)
    results = run_module.run("demo")
    assert results[0]["result"] == "purchased" and results[0]["items"] == 9000 and results[0]["shipping"] == 25000


def test_balance_must_cover_everything_pending_before_the_first_purchase(world):
    world["orders"] = [order("#10"), order("#11")]
    world["review"] = Review(1, 11980, 2990, 13990, 20000, "Los Aromos 1234", None)  # 11980 + estimate 12000 > 20000
    results = run_module.run("demo")
    assert [r["result"] for r in results] == ["stopped"] and results[0]["reason"] == "insufficient_balance"
    assert ("pay",) not in world["calls"]


def test_daily_cap_stops_the_run(world):
    store = config.store("demo")
    store["limits"]["daily_cap"] = 15000
    config.save_store(store)
    ledger.append("demo", order="#1", result="purchased", total=9000)
    results = run_module.run("demo")
    assert results[0]["reason"] == "daily_cap" and world["calls"] == []


def test_dry_run_changes_nothing(world):
    world["orders"] = [order("#10"), order("#11", lines=((1, "100", "1"), (1, "999", "9")))]
    results = run_module.run("demo", dry_run=True)
    assert {r["order"]: r["result"] for r in results} == {"#11": "manual", "#10": "dry_run"}
    assert kinds(world["calls"]) == [("prepare",)] and ledger.entries("demo") == []
