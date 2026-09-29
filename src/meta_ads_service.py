import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger(__name__)


def _meta_config() -> tuple[str, str, float]:
    token = (
        os.getenv("META_ADS_ACCESS_TOKEN")
        or os.getenv("META_ACCESS_TOKEN")
        or ""
    ).strip()
    account_id = (os.getenv("META_AD_ACCOUNT_ID") or "").strip()
    if account_id and not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    try:
        usd_to_dzd = float(os.getenv("USD_TO_DZD", "250.50"))
    except ValueError:
        usd_to_dzd = 250.50

    return token, account_id, usd_to_dzd


def _to_dzd(amount: float, currency: str, usd_to_dzd: float) -> float:
    code = (currency or "DZD").upper()
    if code == "DZD":
        return round(amount, 2)
    if code == "USD":
        return round(amount * usd_to_dzd, 2)
    if code == "EUR":
        eur_to_dzd = float(os.getenv("EUR_TO_DZD", str(usd_to_dzd * 1.08)))
        return round(amount * eur_to_dzd, 2)
    return round(amount, 2)


def fetch_meta_daily_spend(days_back: int = 7) -> list[dict]:
    token, account_id, usd_to_dzd = _meta_config()
    if not token or not account_id:
        return []

    today = datetime.now(ZoneInfo("Africa/Algiers")).date()
    since = (today - timedelta(days=max(1, days_back) - 1)).isoformat()
    until = today.isoformat()

    url = f"https://graph.facebook.com/v21.0/{account_id}/insights"
    params = {
        "fields": "spend,account_currency,date_start,date_stop",
        "time_range": json.dumps({"since": since, "until": until}),
        "time_increment": "1",
        "access_token": token,
    }

    rows: list[dict] = []
    with httpx.Client(timeout=30.0) as client:
        while url:
            response = client.get(url, params=params if "graph.facebook.com" in url else None)
            data = response.json()
            if response.status_code >= 400:
                message = data.get("error", {}).get("message") or response.text[:200]
                raise ValueError(f"Meta Ads API: {message}")

            for item in data.get("data", []):
                spend = float(item.get("spend") or 0)
                if spend <= 0:
                    continue
                currency = item.get("account_currency") or "USD"
                spend_date = item.get("date_start") or item.get("date_stop")
                if not spend_date:
                    continue
                rows.append(
                    {
                        "spend_date": spend_date,
                        "amount_dzd": _to_dzd(spend, currency, usd_to_dzd),
                        "currency": currency,
                        "raw_spend": spend,
                    }
                )

            next_url = data.get("paging", {}).get("next")
            url = next_url
            params = None

    return rows


def sync_meta_ad_spend(db: Session, days_back: int = 7) -> dict:
    token, account_id, _ = _meta_config()
    if not token or not account_id:
        return {"ok": False, "reason": "meta_not_configured", "synced": 0}

    try:
        rows = fetch_meta_daily_spend(days_back=days_back)
    except ValueError as exc:
        logger.warning("Meta ad sync failed: %s", exc)
        return {"ok": False, "reason": str(exc), "synced": 0}

    synced = 0
    for row in rows:
        spend_date = date.fromisoformat(row["spend_date"])
        existing = (
            db.query(models.DailyAdSpend)
            .filter(
                models.DailyAdSpend.spend_date == spend_date,
                models.DailyAdSpend.platform == "meta",
                models.DailyAdSpend.source == "auto",
            )
            .first()
        )
        note = f"Auto Meta ({row['currency']} {row['raw_spend']})"
        if existing:
            existing.amount_dzd = row["amount_dzd"]
            existing.notes = note
        else:
            db.add(
                models.DailyAdSpend(
                    spend_date=spend_date,
                    platform="meta",
                    amount_dzd=row["amount_dzd"],
                    notes=note,
                    source="auto",
                )
            )
        synced += 1

    db.commit()
    return {"ok": True, "synced": synced, "days": days_back}
