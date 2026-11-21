"""Append-only purchase ledger, one JSON line per outcome. File: local/stores/<slug>/ledger.jsonl"""
import json
from datetime import datetime

from . import config


def path(slug):
    return config.store_dir(slug) / "ledger.jsonl"


def append(slug, **entry):
    entry = {"at": config.now(), "day": datetime.now().date().isoformat(), **entry}
    path(slug).parent.mkdir(parents=True, exist_ok=True)
    with path(slug).open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def entries(slug):
    if not path(slug).exists():
        return []
    return [json.loads(line) for line in path(slug).read_text().splitlines() if line.strip()]


def spent_today(slug):
    today = datetime.now().date().isoformat()
    return sum(e["total"] for e in entries(slug) if e["result"] == "purchased" and e["day"] == today)


def last(slug, order, result):
    """Most recent entry of that order with that result, or None."""
    found = [e for e in entries(slug) if e.get("order") == order and e["result"] == result]
    return found[-1] if found else None
