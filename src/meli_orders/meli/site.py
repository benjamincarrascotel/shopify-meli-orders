"""Mercado Libre sites. The country is configuration; only Chile has been run end to end.

The checkout screens are driven by their Spanish labels, so only Spanish-speaking sites are listed.
A site with validated=False has the right domains but its address form has never been exercised.
"""

SITES = {
    "MLC": {"country": "Chile", "tld": "cl", "phone_prefix": "56", "phone_digits": 9, "currency": "CLP", "validated": True},
    "MLA": {"country": "Argentina", "tld": "com.ar", "phone_prefix": "54", "phone_digits": 10, "currency": "ARS", "validated": False},
    "MLM": {"country": "México", "tld": "com.mx", "phone_prefix": "52", "phone_digits": 10, "currency": "MXN", "validated": False},
    "MCO": {"country": "Colombia", "tld": "com.co", "phone_prefix": "57", "phone_digits": 10, "currency": "COP", "validated": False},
}


def site(site_id):
    info = SITES[site_id]
    return {
        **info,
        "id": site_id,
        "home": f"https://www.mercadolibre.{info['tld']}/",
        "search": f"https://listado.mercadolibre.{info['tld']}/",
        "account": f"myaccount.mercadolibre.{info['tld']}",
    }
