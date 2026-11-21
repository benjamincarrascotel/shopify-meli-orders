"""meli-orders: buy paid Shopify orders on Mercado Libre and fulfil them.

  meli-orders doctor                              what is missing, and how to fix it
  meli-orders settings language es|en             language the user is addressed in
  meli-orders store add <store> <web address>    authorize the store in its isolated browser
  meli-orders store login <store>                 log in to Mercado Libre in that browser
  meli-orders product list|search|inspect|init|check|approval ...
  meli-orders status <store>                      pending orders and what a run would do
  meli-orders run <store>                         the purchase run

Exit codes of `run`: 0 done, 10 orders left for manual review, 20 an approval is needed,
30 stopped by a limit or the balance, 1 error or a payment that could not be confirmed.
"""
import argparse
import json
import sys
from contextlib import contextmanager

from . import browser, config, doctor, ledger, shopify
from .meli import checkout, search, session
from .meli.site import SITES, site as site_of
from .messages import t
from .orders import Stop, numeric_id, plan
from .run import EXIT_APPROVAL, exit_code, run


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_doctor(args):
    results = doctor.checks()
    if args.json:
        show(results)
    else:
        for r in results:
            mark = "✓" if r["ok"] else "!" if r["warning"] else "✗"
            print(f"{mark} {r['check']}" + (f"  ({r['detail']})" if r["detail"] else ""))
            if r["fix"]:
                print(f"    → {r['fix']}")
        print(t("doctor.ok") if doctor.passed(results) else t("doctor.failed"))
    return 0 if doctor.passed(results) else 1


def cmd_settings(args):
    if args.language:
        config.save_settings({**config.settings(), "language": args.language})
    show(config.settings())


def cmd_store_add(args):
    domain = shopify.internal_domain(args.domain)
    try:
        authorized = not shopify.missing_scopes(domain)
    except shopify.ShopifyError:
        authorized = False
    if not authorized:  # no browser at all when the store already grants everything
        print(t("store.authorizing" if sys.platform == "darwin" else "store.authorizing_default"), flush=True)
        shopify.authorize(domain, config.profile_dir(args.store))
    info = shopify.shop(domain)
    existing = config.store(args.store) if args.store in config.stores() else {}
    show(config.save_store({
        "meli": {"site": args.site, "account": None, "logged_in_at": None},
        "payment": {"method": "account_money"},
        "limits": {"daily_cap": None, "currency": info["currencyCode"]},
        **existing,
        "slug": args.store, "name": info["name"],
        "shopify": {"domain": info["myshopifyDomain"], "authorized_at": config.now()},
    }))


def cmd_store_login(args):
    print(t("login.open"), flush=True)
    print(t("login.saved", account=session.login(args.store)))


def cmd_store_limits(args):
    store = config.store(args.store)
    store["limits"]["daily_cap"] = None if args.daily_cap == "none" else float(args.daily_cap)
    show(config.save_store(store)["limits"])


def cmd_store_list(args):
    show([{k: s[k] for k in ("slug", "name", "shopify", "meli", "limits")} for s in map(config.store, config.stores())])


def cmd_product_list(args):
    """Active Shopify products, with whether each one is already configured."""
    store = config.store(args.store)
    configured = {p["shopify"]["product_id"]: p["key"] for p in config.products(args.store)}
    show([{
        "product_id": numeric_id(p["id"]), "title": p["title"], "handle": p["handle"],
        "configured_as": configured.get(numeric_id(p["id"])),
        "images": [i["url"] for i in p["images"]["nodes"]],
        "variants": [{"variant_id": numeric_id(v["id"]), "title": v["title"], "price": v["price"]} for v in p["variants"]["nodes"]],
    } for p in shopify.active_products(store["shopify"]["domain"])])


@contextmanager
def _browser(slug):
    """The store's logged-in browser, refusing any other Mercado Libre account."""
    store = config.store(slug)
    site = site_of(store["meli"]["site"])
    with browser.session(slug) as page:
        session.ensure(page, store, site)
        yield page, site


def cmd_product_search(args):
    with _browser(args.store) as (page, site):
        show(search.search(page, site, args.query, args.limit))


def cmd_product_inspect(args):
    with _browser(args.store) as (page, _):
        show(search.inspect(page, args.url))


def cmd_product_init(args):
    """Create the product file from a Shopify product and the chosen listings, main one first."""
    store = config.store(args.store)
    found = [p for p in shopify.active_products(store["shopify"]["domain"]) if numeric_id(p["id"]) == args.shopify_product]
    if not found:
        raise config.ConfigError(f"no active Shopify product {args.shopify_product}")
    listings = []
    with _browser(args.store) as (page, _):
        for url in args.listing:
            facts = search.inspect(page, url)
            if not facts["seller"] or not facts["buyable"]:
                raise config.ConfigError(f"{url}: no seller or no «Comprar ahora» on the page")
            variation = next(iter(facts["variations"].items()), None)
            listings.append({"url": facts["url"], "seller": facts["seller"], "verified": None,
                             "variation": {"name": variation[0], "value": variation[1]} if variation else None})
    show(config.save_product(args.store, {
        "key": args.key, "status": "active",
        "shopify": {"product_id": args.shopify_product, "title": found[0]["title"], "handle": found[0]["handle"],
                    "variants": [{"variant_id": numeric_id(v["id"]), "title": v["title"], "units_per_item": 1}
                                 for v in found[0]["variants"]["nodes"]]},
        "listings": listings,
        "approval": {"mode": "first_purchase_pending", "first_order": None, "decided_at": None},
        "research": {"researched_at": config.now(), "notes": args.notes or ""},
    }))


def cmd_product_check(args):
    """Take every listing to the payment screen without paying, to the account's default address."""
    product = config.product(args.store, args.key)
    report = []
    with _browser(args.store) as (page, _):
        for listing in product["listings"]:
            try:
                review = checkout.prepare(page, listing, args.units)
            except Stop as problem:
                report.append({"url": listing["url"], "ok": False, "reason": problem.code,
                               "text": t(f"reason.{problem.code}", **problem.details)})
                continue
            shipping = review.shipping or 0
            measured = {"unit_price": (review.total - shipping) / args.units, "shipping": shipping, "total": review.total}
            report.append({"url": listing["url"], "ok": True, "units": args.units, **measured,
                           "balance": review.balance, "delivery": review.delivery})
            if args.save:
                evidence = args.evidence or (listing["verified"] or {}).get("identical_evidence", "")
                listing["verified"] = {**measured, "checked_at": config.now(), "identical_evidence": evidence}
    if args.save:
        config.save_product(args.store, product)
    show(report)
    return 0 if all(r["ok"] for r in report) else 1


def cmd_product_approval(args):
    product = config.product(args.store, args.key)
    if product["approval"]["mode"] == "first_purchase_pending":
        raise Stop("first_purchase_not_approved")  # the first purchase always waits for the user
    product["approval"] |= {"mode": {"auto": "auto", "each": "each_purchase"}[args.mode], "decided_at": config.now()}
    show(config.save_product(args.store, product)["approval"])


def cmd_validate(args):
    config.settings()
    for slug in config.stores():
        config.store(slug)
        config.products(slug)
    print(t("validate.ok"))


def cmd_status(args):
    """What a run would do, without opening a browser."""
    store = config.store(args.store)
    products = config.products(args.store)
    orders = []
    for order in shopify.open_paid_orders(store["shopify"]["domain"]):
        decided = plan(order, products)
        if decided["action"] != "ignore":
            orders.append({"order": order["name"], "action": decided["action"], "reason": decided.get("reason"),
                           "product": decided["product"]["key"] if "product" in decided else None,
                           "units": decided.get("units")})
    show({
        "store": store["slug"], "account": store["meli"]["account"], "limits": store["limits"],
        "spent_today": ledger.spent_today(args.store),
        "products": [{"key": p["key"], "status": p["status"], "approval": p["approval"]["mode"],
                      "listings": len(p["listings"])} for p in products],
        "orders": orders,
    })


def _print_results(results):
    if not results:
        print(t("run.nothing"))
    for r in results:
        amount = f" · {r['total']} {r.get('currency', '')}".rstrip() if "total" in r else ""
        print(f"{r['order']}: {t('result.' + r['result'])}{amount}" + (f" · {r['text']}" if r.get("text") else ""))


def _latest(results):
    """One result per order: the last one, except that a later 'skipped' never hides what happened before."""
    final = {}
    for r in results:
        if not (r["result"] == "skipped" and r["order"] in final):
            final[r["order"]] = r
    return list(final.values())


def cmd_run(args):
    interactive = sys.stdin.isatty() and not args.json
    approve, everything = args.approve, []
    while True:
        results = run(args.store, only=args.order, dry_run=args.dry_run, approve=approve, retry_manual=args.retry_manual)
        everything += results
        waiting = next((r for r in results if r["result"] == "needs_approval"), None)
        if not (waiting and interactive):
            break
        # the browser is closed by now: the user reads the real figures here and decides
        print(t("approval.summary", **waiting))
        if input(t("approval.confirm") + " ").strip().lower() not in ("y", "yes", "s", "si", "sí"):
            break
        everything.remove(waiting)
        approve = waiting["order"]
    everything = _latest(everything)
    if interactive:
        for r in (r for r in everything if r.get("ask_approval_mode")):
            choice = input(t("approval.ask_mode", product=r["product"]) + " ").strip()
            if choice in ("1", "2"):
                cmd_product_approval(argparse.Namespace(store=args.store, key=r["product"], mode="auto" if choice == "1" else "each"))
    if args.json:
        show({"store": args.store, "results": everything, "exit_code": exit_code(everything)})
    else:
        _print_results(everything)
        waiting = [r for r in everything if r["result"] == "needs_approval"]
        if waiting:
            print(t("approval.summary", **waiting[0]))
            print(t("approval.how", order=waiting[0]["order"], code=EXIT_APPROVAL))
    return exit_code(everything)


def build():
    parser = argparse.ArgumentParser(prog="meli-orders", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def command(parent, name, func, *arguments):
        sub = parent.add_parser(name, help=(func.__doc__ or "").strip().split("\n")[0])
        for flags, options in arguments:
            sub.add_argument(*flags, **options)
        sub.set_defaults(func=func)

    store = (("store",), {"help": "store name, as chosen in `store add`"})
    as_json = (("--json",), {"action": "store_true", "help": "machine-readable output"})
    command(commands, "doctor", cmd_doctor, as_json)
    command(commands, "validate", cmd_validate)
    command(commands, "settings", cmd_settings, (("language",), {"nargs": "?", "choices": ["es", "en"]}))
    command(commands, "status", cmd_status, store)
    command(commands, "run", cmd_run, store, as_json,
            (("--order",), {"help": "only this order, e.g. '#1234'"}),
            (("--dry-run",), {"action": "store_true", "help": "stop on the payment screen of the first order, pay nothing, change nothing"}),
            (("--approve",), {"metavar": "ORDER", "help": "pay this order, whose purchase the user has just approved"}),
            (("--retry-manual",), {"action": "store_true", "help": "also try the orders flagged for manual review"}))

    stores = commands.add_parser("store", help="connect a store").add_subparsers(dest="action", required=True)
    command(stores, "list", cmd_store_list)
    command(stores, "add", cmd_store_add, store, (("domain",), {"help": "the store's web address, or its <code>.myshopify.com"}),
            (("--site",), {"default": "MLC", "choices": sorted(SITES), "help": "Mercado Libre site (default MLC, Chile)"}))
    command(stores, "login", cmd_store_login, store)
    command(stores, "limits", cmd_store_limits, store, (("--daily-cap",), {"required": True, "help": "amount per day, or 'none'"}))

    products = commands.add_parser("product", help="configure what is bought").add_subparsers(dest="action", required=True)
    key = (("key",), {"help": "product name, as chosen in `product init`"})
    command(products, "list", cmd_product_list, store)
    command(products, "search", cmd_product_search, store, (("query",), {}), (("--limit",), {"type": int, "default": 20}))
    command(products, "inspect", cmd_product_inspect, store, (("url",), {}))
    command(products, "init", cmd_product_init, store, key,
            (("--shopify-product",), {"required": True, "help": "numeric Shopify product id"}),
            (("--listing",), {"action": "append", "required": True, "help": "listing URL; repeat for fallbacks, main one first"}),
            (("--notes",), {"help": "what the research found"}))
    command(products, "check", cmd_product_check, store, key,
            (("--units",), {"type": int, "default": 1}),
            (("--save",), {"action": "store_true", "help": "record what was measured in the product file"}),
            (("--evidence",), {"help": "why the listing is the same product; saved with --save"}))
    command(products, "approval", cmd_product_approval, store, key, (("mode",), {"choices": ["auto", "each"]}))
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # the texts have ✓, « and accents; Windows consoles default to another code page
    args = build().parse_args(argv)
    try:
        code = args.func(args)
    except Stop as problem:
        print(t(f"reason.{problem.code}", **problem.details), file=sys.stderr)
        code = 1
    except browser.Busy:
        print(t("error.busy"), file=sys.stderr)
        code = 1
    except (config.ConfigError, shopify.ShopifyError) as error:
        print(t("error.generic", detail=error), file=sys.stderr)
        code = 1
    sys.exit(code or 0)


if __name__ == "__main__":
    main()
