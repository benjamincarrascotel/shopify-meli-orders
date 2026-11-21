"""Pure logic: addresses, order plans, the review screen's text, configuration, texts."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from conftest import PRODUCT, order
from meli_orders import config, ledger, messages
from meli_orders.meli.checkout import money, parse_review, pick_suggestion
from meli_orders.meli.site import site
from meli_orders.orders import OrderProblem, Stop, TAG_CHECK, TAG_MANUAL, TAG_PURCHASED, estimate, local_phone, plan, recipient, split_address
from meli_orders.run import EXIT_APPROVAL, EXIT_ERROR, EXIT_LIMIT, EXIT_MANUAL, EXIT_OK, exit_code

ROOT = Path(__file__).parents[1]
CL = site("MLC")


def test_address_lines_are_swapped_by_customers():
    assert split_address("Casa", "Los Aromos 1234") == ("Los Aromos 1234", "Casa")
    assert split_address("Av. Matta 123", "Depto 45") == ("Av. Matta 123", "Depto 45")
    assert split_address("Los Olmos 9", None) == ("Los Olmos 9", "")
    with pytest.raises(OrderProblem):
        split_address("Casa", None)


def test_phone_loses_the_country_prefix():
    assert local_phone("+56912345678", CL) == "912345678"
    assert local_phone("9 1234 5678", CL) == "912345678"
    with pytest.raises(OrderProblem):
        local_phone("123", CL)


def test_store_domain_is_taken_as_given_or_reported_missing(monkeypatch):
    from meli_orders import shopify
    assert shopify.internal_domain("https://AB12-3c.myshopify.com/admin") == "ab12-3c.myshopify.com"
    monkeypatch.setattr(shopify.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with pytest.raises(Stop):
        shopify.internal_domain("shop.example")


def test_recipient_from_order():
    assert recipient(order(), CL) == {"name": "Ana Soto", "phone": "912345678", "street": "Los Aromos 1234",
                                      "city": "Ñuñoa", "notes": "Casa", "workplace": False}


def test_plan_buys_units_and_packs():
    assert plan(order(lines=((3, "100", "1"),)), [PRODUCT]) | {"product": None} == {
        "action": "buy", "product": None, "units": 3}
    assert plan(order(lines=((2, "100", "2"),)), [PRODUCT])["units"] == 4


def test_plan_leaves_other_orders_alone():
    assert plan(order(lines=((1, "999", "9"),)), [PRODUCT]) == {"action": "ignore"}
    assert plan(order(test=True), [PRODUCT]) == {"action": "ignore"}
    assert plan(order(tags=[TAG_PURCHASED]), [PRODUCT]) == {"action": "ignore"}
    assert plan(order(refunds=[{"id": "r"}]), [PRODUCT]) == {"action": "ignore"}


def test_plan_sends_doubtful_orders_to_the_user():
    assert plan(order(lines=((1, "100", "1"), (1, "999", "9"))), [PRODUCT]) == {"action": "manual", "reason": "mixed_products"}
    assert plan(order(lines=((1, "100", "7"),)), [PRODUCT]) == {"action": "manual", "reason": "unknown_variant"}
    assert plan(order(tags=[TAG_CHECK]), [PRODUCT]) == {"action": "skip", "reason": "unconfirmed_payment"}
    assert plan(order(tags=[TAG_MANUAL]), [PRODUCT]) == {"action": "skip", "reason": "waiting_manual_review"}
    assert plan(order(tags=[TAG_MANUAL]), [PRODUCT], retry_manual=True)["action"] == "buy"
    assert plan(order(), [PRODUCT | {"status": "paused"}]) == {"action": "skip", "reason": "product_paused"}


def test_estimate_uses_the_verified_checkout():
    assert estimate(PRODUCT, 2) == 2 * 9000 + 3000
    never_checked = PRODUCT | {"listings": [PRODUCT["listings"][1]]}
    assert estimate(never_checked, 2) == 0


REVIEW = """Finaliza tu compra
Forma de entrega
Envío
$ 2.990
Medios de pago
Dinero disponible
Saldo:
$
2.035.586
Resumen de compra
Producto
$
13.990
Descuento del producto
-
$
5.000
Envío
{shipping}
Ingresar código de cupón
Total
$
16.980
$
{total}
Ahorraste
$
5.000
Pagar y finalizar"""


def test_review_screen_text():
    assert parse_review(REVIEW.format(shipping="$\n2.990", total="11.980")) == (13990, 2990, 11980, 2035586)
    assert parse_review(REVIEW.format(shipping="$\n2.990\nGratis", total="8.990")) == (13990, 0, 8990, 2035586)
    assert parse_review("nothing here") == (None, None, None, None)
    assert money("1.234,50") == 1234.5


def test_address_suggestion_must_be_in_the_city():
    seen = ["Los Aromos 1234, Santiago, Ñuñoa", "Ernesto Los Aromos 1234, Puente Alto", "Los Aromos 1234"]
    assert pick_suggestion(seen, "los aromos 1234", "Nunoa") == seen[0]
    assert pick_suggestion(seen, "Los Aromos 1234", "Santiago") is None


def test_config_round_trip_and_validation(home):
    assert config.stores() == ["demo"]
    saved = config.product("demo", "scratcher")
    assert saved["schema_version"] == 1 and saved["created_at"] and saved["listings"][0]["seller"] == "Main Seller"
    with pytest.raises(config.ConfigError):
        config.save_product("demo", PRODUCT | {"limits": {"max_shipping": 4000}})  # no such thing as a cap per product
    with pytest.raises(config.ConfigError):
        config.save_settings({"language": "fr"})
    assert config.save_settings({"language": "es"})["language"] == "es"


def test_ledger_daily_total(home):
    ledger.append("demo", order="#1", result="purchased", total=9000)
    ledger.append("demo", order="#2", result="needs_approval", total=5000)
    ledger.append("demo", order="#3", result="purchased", total=1000)
    assert ledger.spent_today("demo") == 10000
    assert ledger.last("demo", "#2", "needs_approval")["total"] == 5000
    assert ledger.last("demo", "#2", "purchased") is None


def test_exit_codes():
    assert exit_code([]) == EXIT_OK
    assert exit_code([{"result": "purchased", "fulfilled": True}, {"result": "skipped"}]) == EXIT_OK
    assert exit_code([{"result": "purchased"}, {"result": "manual"}]) == EXIT_MANUAL
    assert exit_code([{"result": "manual"}, {"result": "needs_approval"}]) == EXIT_APPROVAL
    assert exit_code([{"result": "stopped"}]) == EXIT_LIMIT
    assert exit_code([{"result": "unconfirmed"}, {"result": "needs_approval"}]) == EXIT_ERROR
    assert exit_code([{"result": "purchased", "fulfilled": False}]) == EXIT_ERROR


def test_both_languages_have_the_same_texts():
    en, es = messages.catalog("en"), messages.catalog("es")
    assert en.keys() == es.keys()
    for key in en:
        assert set(re.findall(r"{(\w+)}", en[key])) == set(re.findall(r"{(\w+)}", es[key])), key


def test_every_reason_and_fix_used_in_the_code_has_a_text():
    source = "".join(p.read_text() for p in (ROOT / "src/meli_orders").rglob("*.py"))
    used = set(re.findall(r'(?:Stop|OrderProblem|ListingProblem|_stopped\(order,)\s*\(?"(\w+)"', source))
    used |= set(re.findall(r'"reason": "(\w+)"', source))
    missing = {f"reason.{code}" for code in used} - messages.catalog("en").keys()
    assert used and not missing, missing
    fixes = set(re.findall(r'add\([^\n]*?, "(\w+)"(?:, store=slug)?\)', (ROOT / "src/meli_orders/doctor.py").read_text()))
    assert fixes and not {f"fix.{f}" for f in fixes} - messages.catalog("en").keys()


def test_schemas_are_valid_json_schema():
    from jsonschema import Draft202012Validator
    for path in (ROOT / "src/meli_orders/schemas").glob("*.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_nothing_under_local_is_tracked_by_git():
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "local"], capture_output=True, text=True).stdout
    assert tracked.strip() == ""
