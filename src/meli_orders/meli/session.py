"""The Mercado Libre session kept in the store's isolated browser profile."""
import time

from .. import browser, config
from ..orders import Stop
from .site import site as site_of


def account(page, site):
    """Account name shown in the header when logged in, else None."""
    try:
        text = page.locator(f'a[href*="{site["account"]}/summary"]').first.inner_text(timeout=3000).strip()
    except Exception:
        return None
    return text.splitlines()[0] if text else None


def login(slug, minutes=15):
    """Open Mercado Libre for the user to log in; save the account every later run must see."""
    store = config.store(slug)
    site = site_of(store["meli"]["site"])
    with browser.session(slug) as page:
        page.goto(site["home"])
        deadline, name = time.time() + minutes * 60, None
        while not name and time.time() < deadline and page.context.pages:  # no pages: the user closed the window
            time.sleep(3)
            name = next(filter(None, (account(tab, site) for tab in page.context.pages)), None)
    if not name:
        raise Stop("login_not_seen")
    store["meli"] |= {"account": name, "logged_in_at": config.now()}
    config.save_store(store)
    return name


def ensure(page, store, site):
    """Fail unless the browser is logged in to the account this store was configured with."""
    page.goto(site["home"], wait_until="domcontentloaded")
    found = account(page, site)
    if not found or found != store["meli"]["account"]:
        raise Stop("wrong_account", found=found or "-", expected=store["meli"]["account"] or "-")
