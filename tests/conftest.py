import pytest

from meli_orders import config

STORE = {
    "slug": "demo", "name": "Demo Shop",
    "shopify": {"domain": "demo.myshopify.com", "authorized_at": None},
    "meli": {"site": "MLC", "account": "Demo", "logged_in_at": None},
    "payment": {"method": "account_money"},
    "limits": {"daily_cap": None, "currency": "CLP"},
}

PRODUCT = {
    "key": "scratcher", "status": "active",
    "shopify": {"product_id": "100", "title": "Scratcher", "handle": "scratcher", "variants": [
        {"variant_id": "1", "title": "Single", "units_per_item": 1},
        {"variant_id": "2", "title": "Pack of two", "units_per_item": 2},
    ]},
    "listings": [
        {"url": "https://www.mercadolibre.cl/main", "seller": "Main Seller", "variation": None,
         "verified": {"unit_price": 9000, "shipping": 3000, "total": 12000, "checked_at": "2026-01-01", "identical_evidence": "same photos"}},
        {"url": "https://www.mercadolibre.cl/backup", "seller": "Backup Seller", "variation": None, "verified": None},
    ],
    "limits": {"max_unit_price": 10000, "max_shipping": 4000},
    "approval": {"mode": "auto", "first_order": "#1", "decided_at": "2026-01-01"},
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An empty local/ folder with one store and one product, in English."""
    monkeypatch.setenv("MELI_ORDERS_HOME", str(tmp_path))
    monkeypatch.setenv("MELI_ORDERS_LANG", "en")
    config.save_store(STORE)
    config.save_product("demo", PRODUCT)
    return tmp_path


def order(name="#10", lines=((1, "100", "1"),), **extra):
    """A paid, open order; lines are (quantity, product id, variant id)."""
    return {
        "id": f"gid://shopify/Order/{name.lstrip('#')}", "name": name, "note": None, "tags": [], "test": False,
        "cancelledAt": None, "phone": None, "refunds": [],
        "lineItems": {"nodes": [{"quantity": q, "title": "x", "product": {"id": f"gid://shopify/Product/{p}"},
                                 "variant": {"id": f"gid://shopify/ProductVariant/{v}"}} for q, p, v in lines]},
        "shippingAddress": {"name": "Ana Soto", "company": None, "address1": "Casa", "address2": "Los Aromos 1234",
                            "city": "Ñuñoa", "phone": "+56912345678"},
        **extra,
    }
