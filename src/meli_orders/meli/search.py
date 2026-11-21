"""Find and read Mercado Libre listings, for choosing what to buy. Read-only."""
import re
from urllib.parse import quote

from .checkout import money, selected_variations

# One object per result card. Sponsored cards link through a click tracker, so `ad` is reported.
CARDS = """() => [...document.querySelectorAll('.poly-card')].map(card => {
  const text = sel => (card.querySelector(sel)?.innerText || '').trim();
  const link = card.querySelector('a.poly-component__title');
  return {
    title: link?.innerText.trim() || '',
    url: link?.href || '',
    price: text('.poly-price__current .andes-money-amount__fraction'),
    reviews: text('.poly-component__review-compacted'),
    shipping: text('.poly-component__shipping-v2'),
    seller: text('.poly-component__seller'),
    full: !!card.querySelector('use[href="#poly_full"]'),
    image: card.querySelector('img.poly-component__picture')?.src || '',
  };
})"""

LISTING = """() => {
  const text = sel => (document.querySelector(sel)?.innerText || '').trim();
  return {
    title: text('h1.ui-pdp-title'),
    price: document.querySelector('meta[itemprop="price"]')?.content || '',
    subtitle: text('.ui-pdp-subtitle'),
    rating: text('.ui-pdp-review__rating'),
    reviews: text('.ui-pdp-review__amount'),
    seller: text('.ui-seller-data-header__title'),
    images: [...document.querySelectorAll('.ui-pdp-gallery__figure__image')].map(i => i.src).filter(Boolean),
  };
}"""


def search(page, site, query, limit=20):
    page.goto(site["search"] + quote(re.sub(r"\s+", "-", query.strip())), wait_until="domcontentloaded")
    page.locator(".poly-card").first.wait_for()
    cards = []
    for card in page.evaluate(CARDS):
        if not card["url"] or not card["price"]:
            continue
        card["ad"] = "is_advertising=true" in card["url"]
        card["price"] = money(card["price"])
        card["shipping"] = card["shipping"].split("\n")[0]  # the card repeats it for screen readers
        cards.append(card)
    return sorted(cards, key=lambda card: card["ad"])[:limit]  # organic results before sponsored ones


def inspect(page, url):
    """Facts of one listing page: what the user needs to judge it and what the product file records."""
    page.goto(url, wait_until="domcontentloaded")
    page.locator("h1.ui-pdp-title").wait_for()
    facts = page.evaluate(LISTING)
    body = page.inner_text("body")
    available = re.search(r"\(\+?(\d+) disponibles?\)", body)
    return {
        **facts,
        "url": page.url.split("#")[0].split("?")[0],
        "price": money(facts["price"].replace(".", ",")) if facts["price"] else None,
        "full": "Almacenado y enviado por" in body,
        "in_stock": "Stock disponible" in body or bool(available),
        "available": int(available.group(1)) if available else None,
        "official_store": "Tienda oficial" in body,
        "variations": selected_variations(page),
        "buyable": page.get_by_role("button", name="Comprar ahora").count() > 0,
    }
