"""Which Shopify orders are bought and with what plan. Pure functions: no network, no browser."""
import re
import unicodedata

TAG_PURCHASED = "mercadolibre-purchased"
TAG_CHECK = "mercadolibre-check"    # set just before paying; left behind only if the confirmation was never seen
TAG_MANUAL = "mercadolibre-manual"  # could not be bought automatically; skipped until the user removes it


class Stop(Exception):
    """A check failed and nothing is bought. `code` is a stable identifier with a text in locales/."""

    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


class OrderProblem(Stop):
    """Wrong with this order (address, phone): no listing would fix it, the order goes to manual review."""


class ListingProblem(Stop):
    """Wrong with this listing (seller, stock, price): the next listing of the product may still work."""


def norm(text):
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def numeric_id(gid):
    return (gid or "").rsplit("/", 1)[-1]


# what customers write after the house number: «Cuarto Piso», «piso 4», «depto 502», «Of. 3», «Casa 5», «Torre B»
EXTRA = re.compile(r"\b(?:(?:primer|segundo|tercer|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo|\d+\s*(?:°|º|er|ro|do|to|vo|no|mo)?)\s+piso"
                   r"|piso|departamento|depto|dpto|dep|oficina|of|casa|block|torre|local|condominio)\b", re.I)


def split_address(line1, line2):
    """(street with number, delivery notes). Customers swap the two fields, so the street is the line with a number.

    Mercado Libre's address search wants only street and number, so what follows the number (floor, office,
    apartment) moves to the notes. A word like «Torre» before the number is part of the street name.
    """
    lines = [line.strip() for line in (line1, line2) if line and line.strip()]
    street = next((line for line in lines if re.search(r"\d", line)), None)
    if not street:
        raise OrderProblem("address_without_number")
    notes = [line for line in lines if line is not street]
    extra = next((m for m in EXTRA.finditer(street) if re.search(r"\d+[a-z]?$", street[:m.start()].rstrip(" ,.-#"), re.I)), None)
    if extra:
        street, notes = street[:extra.start()].rstrip(" ,.-#"), [street[extra.start():].strip()] + notes
    return street, ", ".join(notes)


def local_phone(raw, site):
    """National number without the country prefix, as the address form wants it."""
    digits = re.sub(r"\D", "", raw or "")
    prefix, size = site["phone_prefix"], site["phone_digits"]
    if len(digits) == size + len(prefix) and digits.startswith(prefix):
        digits = digits[len(prefix):]
    if len(digits) != size:
        raise OrderProblem("invalid_phone", phone=raw or "")
    return digits


def is_rut(text):
    """A Chilean RUT, with or without dots, dash and check digit (for example 12.345.678-K or 12345678)."""
    return bool(re.fullmatch(r"\d{1,2}\.?\d{3}\.?\d{3}(-?[\dkK])?", (text or "").strip()))


def recipient(order, site):
    """Stores may relabel the checkout's Company field as RUT to collect it, so a RUT there is not a workplace."""
    ship = order.get("shippingAddress") or {}
    street, notes = split_address(ship.get("address1"), ship.get("address2"))
    if not ship.get("name") or not ship.get("city"):
        raise OrderProblem("incomplete_address")
    return {
        "name": ship["name"],
        "phone": local_phone(ship.get("phone") or order.get("phone"), site),
        "street": street,
        "city": ship["city"],
        "notes": notes,
        "workplace": bool(ship.get("company")) and not is_rut(ship["company"]),
    }


def plan(order, products, retry_manual=False):
    """What to do with one open, paid, unfulfilled order.

    Returns {"action": "ignore"} for orders that are not ours to touch, {"action": "skip", "reason"}
    for orders waiting on the user, {"action": "manual", "reason"} for orders to flag in Shopify,
    or {"action": "buy", "product", "units"}. Orders flagged for manual review are skipped
    unless retry_manual asks to try them again.
    """
    tags = set(order.get("tags") or [])
    if order.get("test") or order.get("cancelledAt") or order.get("refunds") or TAG_PURCHASED in tags:
        return {"action": "ignore"}
    by_id = {p["shopify"]["product_id"]: p for p in products}
    lines = order["lineItems"]["nodes"]
    ours = [line for line in lines if numeric_id((line.get("product") or {}).get("id")) in by_id]
    if not ours:
        # the store also sells things that are not bought on Mercado Libre; status reports them so a recreated product is noticed
        return {"action": "ignore", "reason": "unconfigured_product"}
    if TAG_CHECK in tags:
        return {"action": "skip", "reason": "unconfirmed_payment"}
    if TAG_MANUAL in tags and not retry_manual:
        return {"action": "skip", "reason": "waiting_manual_review"}
    product_ids = {numeric_id((line.get("product") or {}).get("id")) for line in lines}
    if len(ours) != len(lines) or len(product_ids) != 1:
        return {"action": "manual", "reason": "mixed_products"}
    product = by_id[product_ids.pop()]
    if product["status"] != "active":
        return {"action": "skip", "reason": "product_paused"}
    per_item = {v["variant_id"]: v["units_per_item"] for v in product["shopify"]["variants"]}
    units = 0
    for line in lines:
        variant = numeric_id((line.get("variant") or {}).get("id"))
        if variant not in per_item:
            return {"action": "manual", "reason": "unknown_variant"}
        units += line["quantity"] * per_item[variant]
    return {"action": "buy", "product": product, "units": units}


def estimate(product, units):
    """Expected cost from the last verified checkout of the main listing; 0 when it was never measured."""
    verified = product["listings"][0]["verified"]
    return units * verified["unit_price"] + verified["shipping"] if verified else 0
