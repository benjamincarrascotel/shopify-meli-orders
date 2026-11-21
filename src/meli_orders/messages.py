"""Every text shown to the user, in the language stored in settings (config.language())."""
import json
from functools import lru_cache

from . import config


@lru_cache
def catalog(lang):
    return json.loads((config.PACKAGE / "locales" / f"{lang}.json").read_text(encoding="utf-8"))


def t(key, **values):
    text = catalog(config.language()).get(key) or catalog("en")[key]
    return text.format(**values)
