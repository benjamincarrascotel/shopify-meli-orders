"""Local configuration: one settings file and, per store, a store file and one file per product.

Everything lives under local/ (git-ignored). Each file is validated against its JSON Schema in
schemas/ on every load and save, so a hand edit that breaks the structure fails here and not in
the middle of a purchase.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_VERSION = 1
PACKAGE = Path(__file__).parent


class ConfigError(Exception):
    pass


def root():
    return Path(os.environ.get("MELI_ORDERS_HOME") or PACKAGE.parents[1])


def local():
    return root() / "local"


def store_dir(slug):
    return local() / "stores" / slug


def profile_dir(slug):
    """The store's isolated Chrome profile: its Mercado Libre and Shopify sessions."""
    return store_dir(slug) / "browser-profile"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate(kind, data, path):
    schema = json.loads((PACKAGE / "schemas" / f"{kind}.schema.json").read_text())
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        where = "/".join(map(str, errors[0].path)) or "(root)"
        raise ConfigError(f"{path}: {where}: {errors[0].message}")


def _load(kind, path):
    if not path.exists():
        raise ConfigError(f"{path} does not exist")
    data = json.loads(path.read_text())
    _validate(kind, data, path)
    return data


def _save(kind, path, data):
    stamp = now()
    data = {"schema_version": SCHEMA_VERSION, "created_at": stamp, **data, "updated_at": stamp}
    _validate(kind, data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")  # write-then-rename: a crash never leaves half a file
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return data


def settings():
    path = local() / "settings.json"
    return _load("settings", path) if path.exists() else {}


def save_settings(data):
    return _save("settings", local() / "settings.json", data)


def language():
    """The one place that says which language the user is addressed in."""
    return os.environ.get("MELI_ORDERS_LANG") or settings().get("language", "en")


def stores():
    return sorted(p.parent.name for p in (local() / "stores").glob("*/store.json"))


def store(slug):
    return _load("store", store_dir(slug) / "store.json")


def save_store(data):
    return _save("store", store_dir(data["slug"]) / "store.json", data)


def products(slug):
    return [_load("product", p) for p in sorted((store_dir(slug) / "products").glob("*.json"))]


def product(slug, key):
    return _load("product", store_dir(slug) / "products" / f"{key}.json")


def save_product(slug, data):
    return _save("product", store_dir(slug) / "products" / f"{data['key']}.json", data)
