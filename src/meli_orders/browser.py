"""The store's isolated Chrome: its own profile folder, never the user's everyday Chrome profiles."""
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from . import config



class Busy(Exception):
    """Another run holds this store."""


def chrome_path():
    """Google Chrome's executable, or None. Chromium does not count: Playwright's "chrome" channel wants Chrome."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/opt/google/chrome/chrome",
        *(Path(os.environ[folder]) / "Google/Chrome/Application/chrome.exe"
          for folder in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA") if os.environ.get(folder)),
    ]
    found = next((str(p) for p in candidates if Path(p).exists()), None)
    return found or shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def close_profile(profile):
    """macOS and Linux only: used after the Shopify approval, which uses this profile only on macOS."""
    subprocess.run(["pkill", "-f", "--", f"--user-data-dir={profile}"], capture_output=True)


def _lock(handle):
    """Take the store's lock without waiting; OSError when another run holds it. Windows path not exercised."""
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def session(slug, timeout_ms=20000):
    """Open the store's browser and yield a page. One at a time per store."""
    from playwright.sync_api import sync_playwright  # imported late: most commands never open a browser

    profile = config.profile_dir(slug)
    profile.mkdir(parents=True, exist_ok=True)
    with (config.store_dir(slug) / ".lock").open("w") as lock:
        try:
            _lock(lock)
        except OSError:
            raise Busy(slug)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile), channel="chrome", headless=False, no_viewport=True, slow_mo=150,
                # sandbox on: without it Chrome shows a warning bar and macOS font prompts freeze the page
                chromium_sandbox=True, ignore_default_args=["--enable-automation"])
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(timeout_ms)
                # "Estás en Chile / Quedarme en Chile": shown at any moment when browsing from another
                # country, and it blocks every click until dismissed
                page.add_locator_handler(page.get_by_text(re.compile(r"^Quedarme en ")), lambda button: button.click())
                yield page
            finally:
                context.close()
