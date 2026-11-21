"""Shopify Admin API through the Shopify CLI (`shopify store auth` / `shopify store execute`).

The CLI keeps the store's authorization, so nothing here stores a token and any terminal or agent
can run it. Orders are read and updated only through this module, never in a browser.
"""
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import browser
from .orders import Stop

# Requested in one approval so a later feature never needs a second one. write_* includes read_*.
SCOPES = [
    "read_products", "write_orders",
    "write_merchant_managed_fulfillment_orders", "write_assigned_fulfillment_orders",
    "write_third_party_fulfillment_orders", "write_fulfillments", "write_returns", "write_order_edits",
]

ORDERS = """query($q: String!) { orders(first: 100, query: $q, sortKey: CREATED_AT) { nodes {
  id name note tags test cancelledAt phone refunds { id }
  lineItems(first: 20) { nodes { quantity title product { id } variant { id } } }
  shippingAddress { name company address1 address2 city phone } } } }"""

PRODUCTS = """{ products(first: 100, query: "status:active") { nodes {
  id title handle featuredImage { url } images(first: 6) { nodes { url } }
  variants(first: 50) { nodes { id title price } } } } }"""


class ShopifyError(Exception):
    pass


def gql(domain, query, variables=None, mutate=False):
    cmd = ["shopify", "store", "execute", "--store", domain, "--json", "--query", query]
    if variables is not None:
        cmd += ["--variables", json.dumps(variables)]
    if mutate:
        cmd.append("--allow-mutations")
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    body = "\n".join(line for line in out.splitlines() if '"type":"progress"' not in line)
    if "{" not in body:
        raise ShopifyError(f"no answer from the Shopify CLI for {domain}")
    data = json.loads(body[body.index("{"):])
    if "error" in data or "errors" in data:
        raise ShopifyError(json.dumps(data, ensure_ascii=False)[:1500])
    return data


def _done(payload):
    if payload.get("userErrors"):
        raise ShopifyError(json.dumps(payload["userErrors"], ensure_ascii=False))
    return payload


def internal_domain(address):
    """The store's <code>.myshopify.com, from that domain or from the address customers visit.

    Every Shopify storefront publishes it at /meta.json (observed 2026-11-21); a store behind a password does not.
    """
    host = re.sub(r"^https?://", "", address.strip().lower()).split("/")[0]
    if host.endswith(".myshopify.com"):
        return host
    try:
        with urllib.request.urlopen(f"https://{host}/meta.json", timeout=15) as answer:
            return json.load(answer)["myshopify_domain"]
    except (OSError, ValueError, KeyError):
        raise Stop("store_domain_not_found", address=address) from None


def shop(domain):
    return gql(domain, "{ shop { name myshopifyDomain currencyCode } }")["shop"]


def granted_scopes(domain):
    nodes = gql(domain, "{ currentAppInstallation { accessScopes { handle } } }")["currentAppInstallation"]["accessScopes"]
    return {n["handle"] for n in nodes}


def missing_scopes(domain):
    """Scopes of SCOPES not granted; a granted write_x also covers read_x."""
    granted = granted_scopes(domain)
    return [s for s in SCOPES if s not in granted and s.replace("read_", "write_", 1) not in granted]


def authorize(domain, profile):
    """Approve the full scope list in the store's isolated Chrome profile, not in the default browser.

    The CLI has no headless mode and opens the page with `open <url>`; a shim named `open` earlier
    in PATH sends that URL to the isolated profile instead. macOS only for now.
    """
    profile.mkdir(parents=True, exist_ok=True)
    try:
        # never narrow what the store already grants: other tools on this computer share the CLI's authorization
        scopes = sorted(set(SCOPES) | granted_scopes(domain))
    except (ShopifyError, ValueError):
        scopes = SCOPES
    with tempfile.TemporaryDirectory() as shim:
        script = Path(shim, "open")
        # the two keychain flags are the ones Playwright saves this profile's cookies with
        script.write_text('#!/bin/sh\nfor url; do :; done\n'
                          f'"{browser.chrome_path()}" --user-data-dir="{profile}" '
                          '--use-mock-keychain --password-store=basic "$url" >/dev/null 2>&1 &\n')
        script.chmod(0o755)
        env = {**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"}
        done = subprocess.run(["shopify", "store", "auth", "--store", domain, "--scopes", ",".join(scopes)], env=env)
    browser.close_profile(profile)  # free the profile for the next automated run
    if done.returncode:
        raise ShopifyError("the Shopify authorization did not complete")


def active_products(domain):
    return gql(domain, PRODUCTS)["products"]["nodes"]


def open_paid_orders(domain):
    return gql(domain, ORDERS, {"q": "fulfillment_status:unfulfilled financial_status:paid status:open"})["orders"]["nodes"]


def _tags(domain, order_id, mutation, tag):
    query = f"mutation($id: ID!, $tags: [String!]!) {{ {mutation}(id: $id, tags: $tags) {{ userErrors {{ message }} }} }}"
    _done(gql(domain, query, {"id": order_id, "tags": [tag]}, mutate=True)[mutation])


def add_tag(domain, order_id, tag):
    _tags(domain, order_id, "tagsAdd", tag)


def remove_tag(domain, order_id, tag):
    _tags(domain, order_id, "tagsRemove", tag)


def append_note(domain, order, line):
    note = "\n".join(filter(None, [order.get("note"), line]))
    query = "mutation($input: OrderInput!) { orderUpdate(input: $input) { userErrors { message } } }"
    _done(gql(domain, query, {"input": {"id": order["id"], "note": note}}, mutate=True)["orderUpdate"])
    order["note"] = note


def fulfill(domain, order_id):
    """Mark the order fulfilled; Shopify emails the shipping confirmation. Call only after a confirmed purchase."""
    query = "query($id: ID!) { order(id: $id) { fulfillmentOrders(first: 10) { nodes { id status } } } }"
    nodes = gql(domain, query, {"id": order_id})["order"]["fulfillmentOrders"]["nodes"]
    lines = [{"fulfillmentOrderId": n["id"]} for n in nodes if n["status"] == "OPEN"]
    query = "mutation($f: FulfillmentInput!) { fulfillmentCreate(fulfillment: $f) { userErrors { message } } }"
    _done(gql(domain, query, {"f": {"lineItemsByFulfillmentOrder": lines, "notifyCustomer": True}}, mutate=True)["fulfillmentCreate"])
