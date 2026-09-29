import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .accounting_service import enrich_metrics
from .anti_fraud import get_client_ip
from .ip_validation import lookup_ip

ALGIERS_TZ = ZoneInfo("Africa/Algiers")


def _algiers_day(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ALGIERS_TZ).date().isoformat()


def _display_date_range(date_from: Optional[str], date_to: Optional[str], start: datetime, end: datetime) -> tuple[str, str]:
    if date_from and date_to:
        return date_from, date_to
    return _algiers_day(start), _algiers_day(end)


def strict_ip_filter_enabled() -> bool:
    return os.getenv("ANALYTICS_STRICT_IP_FILTER", "false").lower() in {"1", "true", "yes"}


def _parse_date_only(value: str, *, end_of_day: bool = False) -> datetime:
    """Interpret YYYY-MM-DD as Algeria local day boundaries, store/compare in UTC."""
    year, month, day = map(int, value.split("-")[:3])
    if end_of_day:
        local = datetime(year, month, day, 23, 59, 59, 999999, tzinfo=ALGIERS_TZ)
    else:
        local = datetime(year, month, day, 0, 0, 0, tzinfo=ALGIERS_TZ)
    return local.astimezone(timezone.utc)


def _parse_datetime(value: Optional[str], *, end_of_day: bool = False) -> datetime:
    if not value:
        now_alg = datetime.now(ALGIERS_TZ)
        local = now_alg.replace(hour=0, minute=0, second=0, microsecond=0)
        return local.astimezone(timezone.utc)

    raw = value.strip()
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return _parse_date_only(raw, end_of_day=end_of_day)

    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed.astimezone(timezone.utc)


def default_date_range(
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[datetime, datetime]:
    start = _parse_datetime(date_from)
    end = _parse_datetime(date_to, end_of_day=True) if date_to else datetime.now(timezone.utc)
    if end < start:
        start, end = end, start
    return start, end


def record_analytics_event(
    *,
    db: Session,
    request: Request,
    event_type: str,
    session_id: str,
    page_path: Optional[str] = None,
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
    referrer: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
) -> models.AnalyticsEvent:
    client_ip = get_client_ip(request)
    ip_info = lookup_ip(client_ip)

    event = models.AnalyticsEvent(
        event_type=event_type,
        session_id=session_id[:64],
        page_path=(page_path or "")[:500] or None,
        product_id=(product_id or "")[:120] or None,
        product_name=(product_name or "")[:255] or None,
        referrer=(referrer or "")[:500] or None,
        utm_source=(utm_source or "")[:120] or None,
        utm_medium=(utm_medium or "")[:120] or None,
        utm_campaign=(utm_campaign or "")[:120] or None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        ip_address=client_ip,
        country_code=ip_info.country_code,
        city=ip_info.city,
        isp=ip_info.isp,
        is_proxy=ip_info.is_proxy,
        is_hosting=ip_info.is_hosting,
        is_valid=ip_info.is_valid if strict_ip_filter_enabled() else True,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def attach_ip_metadata_to_order(order: models.Order, request: Request) -> None:
    client_ip = get_client_ip(request)
    order.ip_address = client_ip
    if not strict_ip_filter_enabled():
        order.is_valid_traffic = True
        return

    ip_info = lookup_ip(client_ip)
    order.country_code = ip_info.country_code
    order.city = ip_info.city
    order.isp = ip_info.isp
    order.is_proxy = ip_info.is_proxy
    order.is_hosting = ip_info.is_hosting
    order.is_valid_traffic = ip_info.is_valid if strict_ip_filter_enabled() else True


def valid_order_filter():
    if not strict_ip_filter_enabled():
        return True
    return (models.Order.is_valid_traffic.is_(True)) | (models.Order.is_valid_traffic.is_(None))


def valid_event_filter():
    if not strict_ip_filter_enabled():
        return True
    return models.AnalyticsEvent.is_valid.is_(True)


def _event_count(db: Session, start: datetime, end: datetime, event_type: Optional[str] = None) -> int:
    query = db.query(func.count(models.AnalyticsEvent.id)).filter(
        models.AnalyticsEvent.created_at >= start,
        models.AnalyticsEvent.created_at <= end,
        valid_event_filter(),
    )
    if event_type:
        query = query.filter(models.AnalyticsEvent.event_type == event_type)
    return int(query.scalar() or 0)


def _unique_visitors(db: Session, start: datetime, end: datetime) -> int:
    return int(
        db.query(func.count(func.distinct(models.AnalyticsEvent.session_id)))
        .filter(
            models.AnalyticsEvent.created_at >= start,
            models.AnalyticsEvent.created_at <= end,
            valid_event_filter(),
            models.AnalyticsEvent.session_id.isnot(None),
            models.AnalyticsEvent.session_id != "",
        )
        .scalar()
        or 0
    )


def _product_view_counts(db: Session, start: datetime, end: datetime) -> dict[str, int]:
    rows = (
        db.query(
            models.AnalyticsEvent.product_id,
            models.AnalyticsEvent.product_name,
            func.count(models.AnalyticsEvent.id),
        )
        .filter(
            models.AnalyticsEvent.created_at >= start,
            models.AnalyticsEvent.created_at <= end,
            valid_event_filter(),
            models.AnalyticsEvent.event_type == "product_view",
        )
        .group_by(models.AnalyticsEvent.product_id, models.AnalyticsEvent.product_name)
        .all()
    )
    counts: dict[str, int] = {}
    for product_id, product_name, total in rows:
        if product_id:
            counts[str(product_id)] = counts.get(str(product_id), 0) + int(total or 0)
        if product_name:
            counts[str(product_name)] = counts.get(str(product_name), 0) + int(total or 0)
    return counts


def get_metrics(db: Session, date_from: Optional[str], date_to: Optional[str]) -> dict:
    start, end = default_date_range(date_from, date_to)
    display_from, display_to = _display_date_range(date_from, date_to, start, end)

    page_views = _event_count(db, start, end, "page_view")
    product_views = _event_count(db, start, end, "product_view")
    checkout_starts = _event_count(db, start, end, "checkout_start")
    unique_visitors = _unique_visitors(db, start, end)
    product_view_counts = _product_view_counts(db, start, end)

    orders = (
        db.query(models.Order)
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            valid_order_filter(),
        )
        .all()
    )

    order_count = len(orders)
    revenue = round(sum(order.total_price for order in orders), 2)
    avg_order_value = round(revenue / order_count, 2) if order_count else 0
    conversion_rate = round((order_count / unique_visitors) * 100, 2) if unique_visitors else 0

    daily_map: dict[str, dict] = {}
    for order in orders:
        day = _algiers_day(order.created_at)
        bucket = daily_map.setdefault(
            day,
            {"date": day, "visitors": 0, "page_views": 0, "orders": 0, "revenue": 0},
        )
        bucket["orders"] += 1
        bucket["revenue"] += order.total_price

    daily = []
    for day in sorted(daily_map.keys()):
        bucket = daily_map[day]
        daily.append(
            {
                "date": day,
                "visitors": bucket["visitors"],
                "page_views": bucket["page_views"],
                "orders": bucket["orders"],
                "revenue": round(bucket["revenue"], 2),
            }
        )

    product_clicks: dict[str, int] = {}
    product_views_by_id: dict[str, int] = {}
    product_views_by_name: dict[str, int] = {}
    for key, total in product_view_counts.items():
        product_clicks[key] = total
        product_views_by_id[key] = total
        product_views_by_name[key] = total

    by_product: dict[str, dict] = {}
    for order in orders:
        key = order.product_id or order.product_name or "Unknown"
        label = order.product_name or key
        item = by_product.setdefault(
            key,
            {
                "product_id": order.product_id or "",
                "product_name": label,
                "orders": 0,
                "revenue": 0,
                "quantity": 0,
            },
        )
        item["orders"] += 1
        item["revenue"] += order.total_price
        item["quantity"] += order.quantity or 1

    by_wilaya: dict[str, dict] = {}
    for order in orders:
        key = order.wilaya or "Unknown"
        item = by_wilaya.setdefault(key, {"wilaya": key, "orders": 0, "revenue": 0})
        item["orders"] += 1
        item["revenue"] += order.total_price

    result = {
        "from": display_from,
        "to": display_to,
        "timezone": "Africa/Algiers",
        "single_day": display_from == display_to,
        "strict_ip_filter": strict_ip_filter_enabled(),
        "page_views": page_views,
        "product_views": product_views,
        "checkout_starts": checkout_starts,
        "unique_visitors": unique_visitors,
        "orders": order_count,
        "revenue": revenue,
        "avg_order_value": avg_order_value,
        "conversion_rate": conversion_rate,
        "checkout_conversion_rate": round((order_count / checkout_starts) * 100, 2)
        if checkout_starts
        else 0,
        "funnel": [
            {"step": "زوار", "count": unique_visitors},
            {"step": "مشاهدات صفحات", "count": page_views},
            {"step": "مشاهدات منتجات", "count": product_views},
            {"step": "بدء الطلب", "count": checkout_starts},
            {"step": "طلبيات", "count": order_count},
        ],
        "daily": daily,
        "by_product": sorted(
            [
                {
                    **item,
                    "revenue": round(item["revenue"], 2),
                    "clicks": product_clicks.get(item["product_name"], 0),
                    "product_views": product_views_by_id.get(item["product_id"], 0)
                    or product_views_by_name.get(item["product_name"], 0),
                }
                for item in by_product.values()
            ],
            key=lambda row: row["orders"],
            reverse=True,
        ),
        "by_wilaya": sorted(
            [{**item, "revenue": round(item["revenue"], 2)} for item in by_wilaya.values()],
            key=lambda row: row["orders"],
            reverse=True,
        )[:15],
        "recent_activity": _recent_activity(db, start, end),
    }
    return enrich_metrics(
        db,
        result,
        start,
        end,
        orders,
        events=[],
        product_view_counts=product_view_counts,
        date_from=display_from,
        date_to=display_to,
    )


def _recent_activity(db: Session, start: datetime, end: datetime) -> list[dict]:
    recent_orders = (
        db.query(models.Order)
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            valid_order_filter(),
        )
        .order_by(models.Order.created_at.desc())
        .limit(8)
        .all()
    )
    return [
        {
            "type": "order",
            "label": f"طلبية #{order.order_id}",
            "detail": f"{order.customer_name} — {order.product_name}",
            "amount": order.total_price,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
        for order in recent_orders
    ]
