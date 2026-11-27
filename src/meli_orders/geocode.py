"""The order's street checked against OpenStreetMap (Nominatim) before it is typed into Mercado Libre.

Customers write the neighbourhood after the number («Los Aromos 1234 villa los pinos»), which Mercado
Libre's autocomplete refuses. Nominatim returns the street, number and commune separately (observed
2026-11-27). A lookup only ever corrects the street: no answer, or one that disagrees, leaves the address as
the customer wrote it.
"""
import json
import re
import urllib.parse
import urllib.request

from .orders import norm

URL = "https://nominatim.openstreetmap.org/search"
COMMUNE_FIELDS = ("suburb", "city", "town", "village", "municipality", "city_district")


def _until_number(street):
    """«los aromos 1234 villa los pinos» -> («los aromos 1234», «villa los pinos»)."""
    last = list(re.finditer(r"\d+", street))[-1]
    return street[:last.end()].strip(), street[last.end():].strip(" ,.-#")


def lookup(street, city, country):
    """Nominatim's address for this street and number in this city, or None. Never raises."""
    query = urllib.parse.urlencode({"format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": country,
                                    "street": _until_number(street)[0], "city": city})
    # its policy asks for an identifying User-Agent and at most one request a second; a run does one per
    # order, and each checkout takes far longer than a second
    request = urllib.request.Request(f"{URL}?{query}", headers={"User-Agent": "meli-orders"})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            found = json.load(answer)
    except Exception:
        return None
    return found[0].get("address") if found else None


def corrected(who, found):
    """The recipient with the street as OpenStreetMap knows it, when it has the same number in the same commune."""
    if not found or not found.get("road") or not found.get("house_number"):
        return who
    street, after = _until_number(who["street"])
    if found["house_number"] != re.findall(r"\d+", street)[-1]:
        return who
    if norm(who["city"]) not in {norm(found[k]) for k in COMMUNE_FIELDS if found.get(k)}:
        return who
    notes = ", ".join(part for part in (after, who.get("notes")) if part)
    return {**who, "street": f"{found['road']} {found['house_number']}", "notes": notes}


def check(who, site):
    return corrected(who, lookup(who["street"], who["city"], site["tld"].split(".")[-1]))
