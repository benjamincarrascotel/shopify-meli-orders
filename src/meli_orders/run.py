"""One purchase run for a store: approvals, the balance, the optional daily cap, and the order of steps
that keeps Shopify truthful. There is no price or shipping cap: the cost is what the listing and the
delivery cost that day, shown to the user on the first purchase.

Integrity rules, in the order the code enforces them:
1. An order is fulfilled (and the customer emailed) only after Mercado Libre's confirmation page.
2. TAG_CHECK goes on the order before the pay click and becomes TAG_PURCHASED on confirmation; an
   order left with TAG_CHECK is never bought again until the user has looked at it.
3. An order that could not be bought gets TAG_MANUAL and the reason in its note; nothing else changes.
   That path is closed once the pay click is possible: from there a failure is "unconfirmed", never "not bought".
"""
from datetime import datetime

from . import browser, config, ledger, shopify
from .meli import checkout, session
from .meli.site import site as site_of
from .messages import t
from .orders import ListingProblem, Stop, TAG_CHECK, TAG_MANUAL, TAG_PURCHASED, estimate, plan, recipient

EXIT_OK, EXIT_ERROR, EXIT_MANUAL, EXIT_APPROVAL, EXIT_LIMIT = 0, 1, 10, 20, 30
STOPS_RUN = {"needs_approval", "stopped", "unconfirmed", "dry_run"}


def exit_code(results):
    kinds = {r["result"] for r in results}
    for kind, code in (("unconfirmed", EXIT_ERROR), ("needs_approval", EXIT_APPROVAL), ("stopped", EXIT_LIMIT), ("manual", EXIT_MANUAL)):
        if kind in kinds:
            return code
    return EXIT_ERROR if any(r.get("fulfilled") is False for r in results) else EXIT_OK


def run(slug, only=None, dry_run=False, approve=None, retry_manual=False):
    """Buy every eligible order of the store. Returns one result dict per order touched."""
    store = config.store(slug)
    site = site_of(store["meli"]["site"])
    products = config.products(slug)
    results, todo = [], []
    for order in shopify.open_paid_orders(store["shopify"]["domain"]):
        if only and order["name"] != only:
            continue
        decided = plan(order, products, retry_manual)
        if decided["action"] == "buy":
            todo.append((order, decided))
        elif decided["action"] == "manual":
            results.append(_manual(store, order, Stop(decided["reason"]), dry_run))
        elif decided["action"] == "skip":
            results.append({"order": order["name"], "result": "skipped", "reason": decided["reason"],
                            "text": t(f"reason.{decided['reason']}")})
    if not todo:
        return results
    shots = config.store_dir(slug) / "runs" / datetime.now().date().isoformat()
    shots.mkdir(parents=True, exist_ok=True)
    with browser.session(slug) as page:
        session.ensure(page, store, site)
        for index, (order, decided) in enumerate(todo):
            later = sum(estimate(d["product"], d["units"]) for _, d in todo[index + 1:]) if index == 0 else 0
            files = shots / order["name"].lstrip("#")
            try:
                result = _prepare(page, store, site, order, decided, later, files, dry_run, approve)
            except shopify.ShopifyError:
                raise  # Shopify itself is failing: flagging the order there would fail too
            except Stop as problem:
                _snapshot(page, files, "stopped")
                result = _manual(store, order, problem, dry_run)
            except Exception as error:  # a screen changed or the browser died; nothing has been paid yet
                _snapshot(page, files, "stopped")
                result = _manual(store, order, Stop("unexpected_screen", detail=str(error).splitlines()[0][:200]), dry_run)
            if result["result"] == "ready":
                try:
                    result = _pay(page, store, site, order, decided, result, files)
                except Exception as error:  # never "not bought" from here: the click may have gone through
                    _snapshot(page, files, "unconfirmed")
                    result = {"order": order["name"], "result": "unconfirmed",
                              "text": t("reason.unconfirmed_payment") + f" ({str(error).splitlines()[0][:200]})"}
            results.append(result)
            if result["result"] in STOPS_RUN:
                break
    return results


def _snapshot(page, files, label, html=True):
    try:
        page.screenshot(path=f"{files}-{label}.png", full_page=True, timeout=5000)
        if html:
            open(f"{files}-{label}.html", "w", encoding="utf-8").write(page.content())
    except Exception:
        pass  # a frozen page must not hide why the order stopped


def _manual(store, order, problem, dry_run):
    """Flag the order for manual review in Shopify. Its fulfillment status is never touched."""
    reason = t(f"reason.{problem.code}", **problem.details)
    if not dry_run:
        domain = store["shopify"]["domain"]
        if TAG_MANUAL not in order["tags"]:
            shopify.add_tag(domain, order["id"], TAG_MANUAL)
        shopify.append_note(domain, order, t("note.manual", day=datetime.now().date().isoformat(), reason=reason))
        ledger.append(store["slug"], order=order["name"], result="manual", reason=problem.code, details=problem.details)
    return {"order": order["name"], "result": "manual", "reason": problem.code, "text": reason}


def _stopped(order, code, **details):
    return {"order": order["name"], "result": "stopped", "reason": code, "text": t(f"reason.{code}", **details), **details}


def _prepare(page, store, site, order, decided, later, files, dry_run, approve):
    """Reach the review screen and decide: stop, ask the user, or 'ready' to pay. Nothing is paid here."""
    slug = store["slug"]
    product, units, name = decided["product"], decided["units"], order["name"]
    daily = store["limits"]["daily_cap"]
    spent = ledger.spent_today(slug)
    if daily is not None and spent + estimate(product, units) > daily:
        return _stopped(order, "daily_cap", cap=daily, spent=spent)
    who = recipient(order, site)

    review = problem = None
    for listing in product["listings"]:
        try:
            review = checkout.prepare(page, listing, units, who)
            break
        except ListingProblem as error:  # the next listing may still work
            review, problem = None, error
    if review is None:
        raise problem
    if review.balance is None:
        return _stopped(order, "balance_unreadable")
    if review.balance < review.total + later:
        # checked before the first purchase against everything still pending, so a run never ends half bought
        return _stopped(order, "insufficient_balance", balance=review.balance, needed=review.total + later)

    facts = {
        "order": name, "product": product["key"], "listing": listing["url"], "seller": listing["seller"],
        "recipient": who["name"], "address": f"{review.place}, {who['city']}", "units": units,
        "items": review.total - (review.shipping or 0), "shipping": review.shipping or 0, "total": review.total,
        "delivery": review.delivery,
        "balance": review.balance, "balance_after": review.balance - review.total,
        "currency": store["limits"]["currency"],
    }
    _snapshot(page, files, "review", html=False)
    if dry_run:
        return {**facts, "result": "dry_run"}
    mode = product["approval"]["mode"]
    if mode != "auto":
        asked = ledger.last(slug, name, "needs_approval")
        # an approval covers the total the user saw; a higher one is asked again
        if approve != name or (asked and review.total > asked["total"]):
            ledger.append(slug, result="needs_approval", **facts)
            return {**facts, "result": "needs_approval", "first_purchase": mode == "first_purchase_pending"}
    return {**facts, "result": "ready", "place": review.place}


def _pay(page, store, site, order, decided, facts, files):
    """Pay with the Mercado Pago balance and, only on confirmation, record and fulfil the order."""
    slug, domain = store["slug"], store["shopify"]["domain"]
    product, units, name = decided["product"], decided["units"], order["name"]
    facts = {k: v for k, v in facts.items() if k != "result"}
    review = checkout.select_wallet(page, units, facts.pop("place"))
    if review.balance is None or review.balance < review.total:
        return _stopped(order, "insufficient_balance", balance=review.balance or 0, needed=review.total)
    facts |= {"items": review.total - (review.shipping or 0), "shipping": review.shipping or 0,
              "total": review.total, "balance": review.balance,
              "balance_after": review.balance - review.total}

    shopify.add_tag(domain, order["id"], TAG_CHECK)  # from here a later run must not buy this order again
    checkout.pay(page)
    if not checkout.confirmed(page, minutes=5):
        _snapshot(page, files, "unconfirmed")
        ledger.append(slug, result="unconfirmed", **facts)
        return {**facts, "result": "unconfirmed", "text": t("reason.unconfirmed_payment")}
    _snapshot(page, files, "paid", html=False)
    facts["purchase_id"] = checkout.latest_purchase_id(page, site)

    try:
        shopify.add_tag(domain, order["id"], TAG_PURCHASED)
        shopify.remove_tag(domain, order["id"], TAG_CHECK)
        if TAG_MANUAL in order["tags"]:
            shopify.remove_tag(domain, order["id"], TAG_MANUAL)
        shopify.append_note(domain, order, t("note.purchased", day=datetime.now().date().isoformat(),
                                             purchase=facts["purchase_id"] or "?", total=review.total,
                                             currency=facts["currency"], account=store["meli"]["account"]))
        shopify.fulfill(domain, order["id"])  # only now: the purchase is confirmed
        facts["fulfilled"] = True
    except shopify.ShopifyError as error:
        # bought but Shopify is behind; whatever tag is on the order keeps a later run from buying it again
        facts |= {"fulfilled": False, "text": t("reason.shopify_sync_failed", detail=str(error)[:200])}
    ledger.append(slug, result="purchased", **facts)

    if product["approval"]["mode"] == "first_purchase_pending":
        # the first purchase is done; until the user chooses, every purchase keeps asking
        product["approval"] = {"mode": "each_purchase", "first_order": name, "decided_at": None}
        config.save_product(slug, product)
        facts["ask_approval_mode"] = True
    return {**facts, "result": "purchased"}
