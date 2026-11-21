"""Is everything a run needs in place? The first step of setup, and the first thing to run when something fails."""
import shutil
import subprocess
import sys

from . import browser, config, shopify
from .meli.site import SITES
from .messages import t


def checks():
    """One dict per check: name, ok, detail, and how to fix it when it failed."""
    found = []

    def add(name, ok, detail="", fix=None, **values):
        found.append({"check": name, "ok": bool(ok), "detail": str(detail or ""),
                      "fix": t(f"fix.{fix}", **values) if fix and not ok else ""})

    add("google-chrome", browser.chrome_path(), browser.chrome_path(), "chrome")
    for tool in ("uv", "git", "shopify"):
        add(tool, shutil.which(tool), shutil.which(tool), tool)
    add("macos", sys.platform == "darwin", sys.platform, "platform")
    ignored = subprocess.run(["git", "-C", str(config.root()), "check-ignore", "-q", "local"], capture_output=True).returncode == 0
    add("local-folder-ignored-by-git", ignored, config.local(), "local_ignored")
    language = config.settings().get("language")
    add("language", language, language, "language")

    if not config.stores():
        add("stores", False, "", "no_store")
    for slug in config.stores():
        try:
            store, products = config.store(slug), config.products(slug)
        except config.ConfigError as error:
            add(f"{slug}: configuration", False, error, "config")
            continue
        add(f"{slug}: configuration", True, f"{len(products)} product(s)")
        add(f"{slug}: site validated", SITES[store["meli"]["site"]]["validated"], store["meli"]["site"], "site_unvalidated")
        try:
            missing = shopify.missing_scopes(store["shopify"]["domain"])
            add(f"{slug}: shopify access", not missing, ", ".join(missing) or store["shopify"]["domain"], "shopify_auth", store=slug)
        except shopify.ShopifyError as error:
            add(f"{slug}: shopify access", False, str(error)[:160], "shopify_auth", store=slug)
        add(f"{slug}: mercado libre account", store["meli"]["account"], store["meli"]["account"], "meli_login", store=slug)
        add(f"{slug}: products", products, "", "no_products", store=slug)
    return found
