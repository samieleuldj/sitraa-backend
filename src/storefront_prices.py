"""Live storefront prices — override static frontend catalog without redeploying Next.js."""

from __future__ import annotations

import json
import os
from typing import Any

# Update prices here; redeploy backend only (no frontend rebuild needed once API is live).
DEFAULT_STOREFRONT_PRICES: dict[str, dict[str, float]] = {
    "mini-clima-geant": {"price": 2900, "old_price": 3900},
}


def _load_env_overrides() -> dict[str, dict[str, float]]:
    raw = (os.getenv("STOREFRONT_PRICE_OVERRIDES") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def get_storefront_prices() -> dict[str, dict[str, Any]]:
    merged = {k: dict(v) for k, v in DEFAULT_STOREFRONT_PRICES.items()}
    for product_id, override in _load_env_overrides().items():
        if not isinstance(override, dict):
            continue
        entry = merged.setdefault(str(product_id), {})
        if "price" in override:
            entry["price"] = float(override["price"])
        if "old_price" in override:
            entry["old_price"] = float(override["old_price"])
    return merged


def get_product_price(product_id: str) -> dict[str, float] | None:
    prices = get_storefront_prices()
    entry = prices.get(product_id)
    if not entry:
        return None
    result: dict[str, float] = {}
    if "price" in entry:
        result["price"] = float(entry["price"])
    if "old_price" in entry:
        result["old_price"] = float(entry["old_price"])
    return result or None
