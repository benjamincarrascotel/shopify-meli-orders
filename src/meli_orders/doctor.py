"""Is everything a run needs in place? The first step of setup, and the first thing to run when something fails."""
import shutil
import subprocess
import sys

from . import browser, config, shopify
from .meli.site import SITES
from .messages import t


def checks():
    """One dict per check: name, ok, detail, how to fix it when it failed, and whether a failure only warns.

    Python and this project's libraries are not checked: this code running means they are installed.
    """
    found = []
    system = "darwin" if sys.platform == "darwin" else "win32" if sys.platform == "win32" else "linux"

    def add(name, ok, detail="", fix=None, warning=False, **values):
        found.append({"check": name, "ok": bool(ok), "detail": str(detail or ""), "warning": warning and not ok,
                      "fix": t(f"fix.{fix}", **values) if fix and not ok else ""})

    # the fix is the install command for this system
    add("google-chrome", browser.chrome_path(), browser.chrome_path(), f"chrome_{system}")
    add("shopify", shutil.which("shopify"), shutil.which("shopify"), f"shopify_{system}")
    add("system validated", system == "darwin", sys.platform, "platform", warning=True)
    if (config.root() / ".git").exists():  # a copy downloaded as a zip has nothing to commit by mistake
        # Trailing slash: the folder does not exist on a fresh clone, and the rule only matches folders.
        ignored = subprocess.run(["git", "-C", str(config.root()), "check-ignore", "-q", "local/"], capture_output=True).returncode == 0
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
        add(f"{slug}: site validated", SITES[store["meli"]["site"]]["validated"], store["meli"]["site"], "site_unvalidated", warning=True)
        try:
            missing = shopify.missing_scopes(store["shopify"]["domain"])
            add(f"{slug}: shopify access", not missing, ", ".join(missing) or store["shopify"]["domain"], "shopify_auth", store=slug)
        except shopify.ShopifyError as error:
            add(f"{slug}: shopify access", False, str(error)[:160], "shopify_auth", store=slug)
        add(f"{slug}: mercado libre account", store["meli"]["account"], store["meli"]["account"], "meli_login", store=slug)
        add(f"{slug}: products", products, "", "no_products", store=slug)
    return found


def passed(results):
    """Warnings (a system or a Mercado Libre site never run end to end) do not fail the check."""
    return all(r["ok"] or r["warning"] for r in results)
