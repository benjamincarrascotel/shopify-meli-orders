"""Drive a Mercado Libre listing to the review screen, and pay from there.

Screens are located by their Spanish labels and a few stable attributes, as observed on
mercadolibre.cl on 2026-11-20. What has never run against the real site says "not exercised".
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..orders import ListingProblem, OrderProblem, Stop, norm

AMOUNT = r"\$\s*([\d.]+(?:,\d+)?)"


@dataclass
class Review:
    """What the review screen shows just before paying."""
    units: int
    total: float
    shipping: float | None
    product_amount: float | None
    balance: float | None
    place: str | None
    delivery: str | None


def money(text):
    """'13.990' -> 13990, '1.234,50' -> 1234.5 (dot groups thousands on every supported site)."""
    value = float(text.replace(".", "").replace(",", "."))
    return int(value) if value.is_integer() else value


def parse_review(text):
    """(product amount, shipping, total, balance) from the review screen's text; None where a row is missing."""
    start = text.rfind("Resumen de compra")
    summary = text[start:] if start >= 0 else text
    summary = summary.split("Pagar y finalizar")[0]

    def row(label, until):
        found = re.search(rf"{label}(.*?)(?={until}|$)", summary, re.S)
        return found.group(1) if found else ""

    product = re.findall(AMOUNT, row(r"Productos?", "Descuento|Envío"))
    shipping_row = row("Envío", "Ingresar|Total")
    shipping_amounts = re.findall(AMOUNT, shipping_row)
    shipping = 0 if "Gratis" in shipping_row else money(shipping_amounts[-1]) if shipping_amounts else None
    total = re.search(rf"Total((?:\s*{AMOUNT})+)", summary)  # the first amount is the crossed-out price
    balance = re.search(rf"Saldo:\s*{AMOUNT}", text)
    return (money(product[0]) if product else None, shipping,
            money(re.findall(AMOUNT, total.group(1))[-1]) if total else None,
            money(balance.group(1)) if balance else None)


def without_symbols(text):
    """«O'Higgins 450» -> «OHiggins 450»: Mercado Libre's address form refuses symbols in the street."""
    return " ".join(re.sub(r"[^\w\s]", "", text).split())


def bare(text):
    """Lowercase, without accents or symbols: «O'Higgins 450» -> «ohiggins 450»."""
    return without_symbols(norm(text))


def pick_suggestion(texts, street, city):
    """The autocomplete entry for this street and number in this city; None when it is missing or ambiguous.

    The house number must be the same. The street name may differ by a spelling slip or a symbol
    («Ohiggins» for «O'Higgins»): the closest name wins when it is close enough and clearly ahead.
    """
    number = re.findall(r"\d+", street)[-1]
    in_city = [t for t in dict.fromkeys(texts)
               if "\n" not in t and "," in t and norm(t.rsplit(",", 1)[1]) == norm(city)
               and re.findall(r"\d+", t.split(",")[0])[-1:] == [number]]
    scored = sorted(((SequenceMatcher(None, bare(t.split(",")[0]), bare(street)).ratio(), t) for t in in_city), reverse=True)
    if not scored or scored[0][0] < 0.8 or (len(scored) > 1 and scored[1][0] > scored[0][0] - 0.05):
        return None
    return scored[0][1]


def selected_variations(page):
    """{'Color': 'Marrón'}: the options selected in the listing's pickers. The description is ignored on purpose."""
    titles = page.locator(".ui-pdp-outside_variations__picker p, .ui-pdp-variations__picker p").all_inner_texts()
    return {name.strip(): value.strip() for name, _, value in (title.partition(":") for title in titles) if value.strip()}


def choose_quantity(page, units):
    selector = page.locator("#quantity-selector")
    selector.click()
    option = page.locator(f'[data-testid="quantity-selector-item-{units}"]')
    try:
        option.wait_for(timeout=5000)  # the list renders after the click
    except Exception:  # it stops at the stock, or at "more than 6" which is not automated
        raise ListingProblem("quantity_unavailable", units=units)
    option.click()
    try:  # the selector repaints a moment after the click
        selector.filter(has_text=re.compile(rf"\b{units} unidades")).wait_for(timeout=5000)
    except Exception:
        raise ListingProblem("quantity_unavailable", units=units)


def deliver_to(page, recipient):
    """Select the recipient's address in the checkout, adding it to the account when it is new. Returns the street shown."""
    street = recipient["street"]
    page.get_by_text("Cambiar dirección").click()
    add = page.get_by_text("Agregar nueva dirección")
    add.wait_for()
    # a run stopped after saving the address leaves it in the account: reuse it instead of piling up copies.
    # It was saved without symbols, so «O'Higgins 450» on the order is «OHiggins 450» there.
    saved = page.get_by_role("radio", name=re.compile(
        rf"{re.escape(without_symbols(street))}.*{re.escape(recipient['name'])}", re.I | re.S))
    if saved.count():
        saved.first.check()
        page.get_by_text("Continuar", exact=True).click()
        place = without_symbols(street)
    else:
        add.click()
        box = page.get_by_role("textbox", name="Calle y número")
        box.click()
        box.fill("")  # the form keeps the draft of an attempt that stopped before saving (observed 2026-11-21)
        box.press_sequentially(street, delay=80)
        page.wait_for_timeout(2500)
        number = re.findall(r"\d+", street)[-1]
        pick = pick_suggestion(page.get_by_text(re.compile(number)).all_inner_texts(), street, recipient["city"])
        if not pick:
            raise OrderProblem("address_not_found", street=street, city=recipient["city"])
        # the list item, not its text: clicking the text copies it without selecting the place (observed 2026-11-21)
        page.get_by_text(pick, exact=True).first.locator("xpath=ancestor::li[1]").click()
        # its own suggestion can be «O'Higgins 450», which the same form then refuses: «Evita incluir símbolos».
        # Removing the symbols keeps the chosen place and its pin (observed 2026-11-21). The box takes the
        # suggestion a moment after the click.
        chosen = pick.split(",")[0].strip()
        for _ in range(20):
            if box.input_value() == chosen:
                break
            page.wait_for_timeout(250)
        place = without_symbols(chosen)
        if place != chosen:
            box.fill(place)
        no_number = page.get_by_role("checkbox", name="La calle no tiene número")
        if no_number.count() and no_number.is_checked():  # left checked by a draft, it saves the number as «SN»
            no_number.uncheck()
        page.get_by_role("textbox", name="Nombre y apellido").fill(recipient["name"])
        page.get_by_role("textbox", name="Teléfono").fill(recipient["phone"])
        page.get_by_text("Guardar", exact=True).first.click()

        # a field the form refuses shows red helper text under it (observed 2026-11-21)
        review = page.get_by_text("Revisa la dirección")
        refused = page.locator("#address-form .andes-ui-typography--color-negative")
        review.or_(refused).first.wait_for()
        if not review.is_visible():
            raise OrderProblem("address_form_refused", message=" ".join(refused.all_inner_texts()))
        # an edited street opens «Verifica que los datos de tu dirección sean correctos» over the map, with
        # street and number split (observed 2026-11-21)
        split = page.locator("form.csn-container")
        try:
            split.wait_for(timeout=5000)
        except Exception:
            split = None  # an address taken as suggested goes straight to the map
        if split:
            if split.locator("#streetNumber").input_value().strip() != re.findall(r"\d+", place)[-1]:
                raise OrderProblem("map_shows_other_address")
            split.get_by_text("Continuar", exact=True).click()
            split.wait_for(state="hidden")
        shown = norm(f"{place}, {recipient['city']}")
        for _ in range(20):  # the label under the map settles after the confirmation
            if shown in norm(page.inner_text("body")):
                break
            page.wait_for_timeout(250)
        else:
            raise OrderProblem("map_shows_other_address")
        page.get_by_text("Guardar dirección", exact=True).first.click()

    page.get_by_text(re.compile("Cuéntanos más sobre tu dirección|Finaliza tu compra")).first.wait_for()
    if "extra-info" in page.url:
        # the place type is mandatory to save; a company name on the order (not a RUT) means a workplace
        kind = "Un lugar de trabajo" if recipient["workplace"] else "Una vivienda"
        page.get_by_role("radio", name=re.compile(kind)).check()  # the input covers its label text
        if recipient["notes"]:
            # «Las indicaciones no deben incluir caracteres como <> @ [ ] # o $», and it refused «·» too (observed 2026-11-21)
            notes = " ".join(re.sub(r"[^\w\s.,-]", " ", recipient["notes"]).split())
            page.get_by_placeholder(re.compile("Entre calles")).fill(notes[:255])
        page.get_by_text("Guardar", exact=True).first.click()
        done = page.get_by_text("Finaliza tu compra")
        refused = page.locator(".andes-ui-typography--color-negative")
        done.or_(refused).first.wait_for()
        if not done.is_visible():
            raise OrderProblem("address_form_refused", message=" ".join(refused.all_inner_texts()))
    try:
        page.get_by_text(place).first.wait_for()
    except Exception:
        raise OrderProblem("review_shows_other_address")
    return place


def prefer_free_delivery(page):
    """Take a free home-delivery option whenever there is one."""
    # not exercised: on the only real purchase so far every option was free and the default was kept
    free = page.locator('li:has(input[name^="shipping-options-"]:not([disabled]))').filter(has_text="Gratis")
    if free.count() and not free.locator("input:checked").count():
        free.first.locator("input").check()
        page.wait_for_timeout(3000)  # the total reloads with the new option


def read_review(page, units, place):
    text = page.inner_text("body")
    product_amount, shipping, total, balance = parse_review(text)
    if total is None:
        raise Stop("review_unreadable")
    if units > 1 and not re.search(rf"Cantidad:?\s*{units}\b|\b{units}\s*(?:unidades|u\.)", text):
        raise ListingProblem("quantity_not_confirmed", units=units)
    chosen = page.locator('li:has(input[name^="shipping-options-"]:checked) label')
    delivery = chosen.first.inner_text().splitlines()[0] if chosen.count() else None
    return Review(units, total, shipping, product_amount, balance, place, delivery)


def duplicate_of(url):
    """The earlier purchase named by «Hiciste una compra igual hace un momento», or None on any other page."""
    found = re.search(r"/checkout/duplicated_purchase\?(?:.*&)?purchase_id=(\d+)", url)
    return found.group(1) if found else None


def purchase_id_of(url):
    """Purchase number in the confirmation page's address, or None."""
    found = re.search(r"/congrats\?(?:.*&)?purchaseId=(\d+)", url)
    return found.group(1) if found else None


def prepare(page, listing, units, recipient=None, ours=frozenset()):
    """Reach the review screen for `units` of `listing`.

    With a recipient the purchase is addressed to them; without one it keeps the account's default
    address, which is how a listing is measured without touching any customer data.

    When the same listing was bought minutes before, «Comprar ahora» leads to
    /gz/checkout/duplicated_purchase?purchase_id=<earlier> instead of the checkout (seen 2026-11-24, two
    orders of one product in one run). It continues only when that earlier purchase is in `ours`, the
    purchases this tool recorded for other orders; any other earlier purchase could be this very order
    bought by hand, so it stops. The «Continuar compra» click is not exercised against the real site.
    """
    page.goto(listing["url"], wait_until="domcontentloaded")
    buy = page.get_by_role("button", name="Comprar ahora").first
    try:
        buy.wait_for()
    except Exception:
        raise ListingProblem("not_buyable")
    body = page.inner_text("body")
    if listing["seller"] not in body:
        raise ListingProblem("seller_changed", seller=listing["seller"])
    variation = listing["variation"]
    if variation and selected_variations(page).get(variation["name"]) != variation["value"]:
        raise ListingProblem("variation_changed", variation=f"{variation['name']}: {variation['value']}")
    if units > 1:
        choose_quantity(page, units)
    # «Comprar ahora» and not the cart: the cart may hold other products of the account
    buy.click()
    review = page.get_by_text("Finaliza tu compra")
    again = page.get_by_text("Continuar compra", exact=True)
    try:
        review.or_(again).first.wait_for()
    except Exception:
        raise Stop("session_expired") if "login" in page.url else ListingProblem("checkout_not_reached")
    earlier = duplicate_of(page.url)
    if earlier:
        if earlier not in ours:
            raise Stop("duplicated_purchase", purchase=earlier)  # not a listing problem: a fallback would buy it again
        again.click()
        try:
            review.wait_for()
        except Exception:
            raise ListingProblem("checkout_not_reached")
    place = deliver_to(page, recipient) if recipient else None
    page.wait_for_timeout(3000)  # the delivery block reloads after an address change and the total with it
    prefer_free_delivery(page)
    return read_review(page, units, place)


def select_wallet(page, units, place):
    """Choose the Mercado Pago balance and read the review again: payment-method promotions change the total."""
    page.get_by_role("radio", name=re.compile("Dinero disponible")).check()
    page.wait_for_timeout(3000)
    return read_review(page, units, place)


def pay(page):
    page.get_by_role("button", name="Pagar y finalizar").click()


def confirmed(page, minutes):
    """True once Mercado Libre's confirmation page (/checkout/finisher/congrats) shows."""
    for _ in range(minutes * 30):
        if page.is_closed():
            return False
        if "congrats" in page.url:
            page.wait_for_timeout(3000)  # let it render before it is saved
            return True
        page.wait_for_timeout(2000)
    return False


def latest_purchase_id(page, site):
    """Purchase number of the newest purchase in «Mis compras»; None when it cannot be read."""
    # the confirmation page does not carry the number, so this trusts the list's order
    try:
        page.goto(f"https://{site['account']}/purchases/list", wait_until="domcontentloaded")
        href = page.locator('a[href*="/my-purchases/"]').first.get_attribute("href", timeout=10000)
        return re.search(r"/my-purchases/(\d+)", href).group(1)
    except Exception:
        return None
