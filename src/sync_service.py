import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models
from .dhd import fetch_dhd_orders, map_dhd_status
from .google_sheets import push_order_status_to_sheet
from .meta_ads_service import sync_meta_ad_spend
from .order_status import canonical_status, is_cancelled

logger = logging.getLogger(__name__)


def sync_order_from_sheet(
    db: Session,
    order_id: str,
    status: str | None = None,
    tracking_number: str | None = None,
) -> models.Order | None:
    order = (
        db.query(models.Order)
        .filter(models.Order.order_id == order_id.strip())
        .first()
    )
    if not order:
        return None

    if status and status.strip():
        order.status = canonical_status(status)
    if tracking_number is not None:
        tracking = tracking_number.strip()
        if tracking:
            order.tracking_number = tracking

    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return order


def sync_orders_bulk_from_sheet(
    db: Session,
    orders: list[dict],
) -> dict:
    synced = 0
    missing: list[str] = []
    for item in orders:
        order_id = (item.get("order_id") or "").strip()
        if not order_id:
            continue
        order = (
            db.query(models.Order)
            .filter(models.Order.order_id == order_id)
            .first()
        )
        if not order:
            missing.append(order_id)
            continue

        status = item.get("status")
        if status and str(status).strip():
            order.status = canonical_status(str(status))
        tracking_number = item.get("tracking_number")
        if tracking_number is not None:
            tracking = str(tracking_number).strip()
            if tracking:
                order.tracking_number = tracking
        order.updated_at = datetime.now(timezone.utc)
        synced += 1

    if synced:
        db.commit()

    return {"synced": synced, "missing": missing[:20]}


def sync_dhd_order_statuses(db: Session, limit: int = 500) -> dict:
    token = (os.getenv("DHD_API_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "reason": "dhd_not_configured", "updated": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=120)
    orders = (
        db.query(models.Order)
        .filter(models.Order.created_at >= cutoff)
        .order_by(models.Order.updated_at.desc())
        .limit(limit)
        .all()
    )

    updated = 0
    checked = 0
    errors: list[str] = []
    sheet_updates: list[tuple[str, str, str]] = []

    try:
        dhd_rows = fetch_dhd_orders(max_pages=20, per_page=100)
    except Exception as exc:
        logger.warning("DHD bulk fetch failed: %s", exc)
        dhd_rows = []

    dhd_by_tracking = {
        str(row.get("tracking") or "").strip(): row
        for row in dhd_rows
        if str(row.get("tracking") or "").strip()
    }
    dhd_by_reference = {
        str(row.get("reference") or "").strip(): row
        for row in dhd_rows
        if str(row.get("reference") or "").strip()
    }

    for order in orders:
        tracking = (order.tracking_number or "").strip()
        reference = (order.order_id or "").strip()
        if not tracking and not reference:
            continue

        checked += 1
        try:
            raw = dhd_by_tracking.get(tracking) or dhd_by_reference.get(reference)
            if not raw:
                errors.append(f"{order.order_id}: not found in DHD")
                continue

            if is_cancelled(order.status):
                continue

            mapped = map_dhd_status(raw)
            if not mapped:
                continue

            new_status = canonical_status(mapped)
            new_tracking = str(raw.get("tracking") or tracking or "").strip()
            changed = False

            if new_tracking and new_tracking != (order.tracking_number or "").strip():
                order.tracking_number = new_tracking
                changed = True
            if new_status != order.status:
                order.status = new_status
                changed = True

            if changed:
                order.updated_at = datetime.now(timezone.utc)
                updated += 1
                sheet_updates.append((order.order_id, new_status, new_tracking or tracking))
        except Exception as exc:
            errors.append(f"{order.order_id}: {exc}")
            logger.warning("DHD sync failed for %s: %s", order.order_id, exc)

    if updated:
        db.commit()

    for order_id, status, tracking in sheet_updates:
        push_order_status_to_sheet(order_id, status, tracking)

    return {
        "ok": True,
        "checked": checked,
        "updated": updated,
        "errors": errors[:5],
    }


def run_auto_sync(db: Session) -> dict:
    days_back = int(os.getenv("META_SYNC_DAYS", "7"))
    meta = sync_meta_ad_spend(db, days_back=days_back)
    dhd = sync_dhd_order_statuses(db)
    return {
        "meta": meta,
        "dhd": dhd,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
