"""Normalize order statuses (Arabic sheet + English admin)."""

from sqlalchemy import or_
from sqlalchemy.orm import Query

PENDING = {"pending", "في الانتظار", "en attente"}
CONFIRMED = {"confirmed", "مؤكد", "confirmé"}
SHIPPED = {"shipped", "تم الشحن", "expédié", "expedie"}
DELIVERED = {"delivered", "تم التسليم", "livré", "livre"}
RETURNED = {"returned", "مرتجع", "retourné", "retourne"}
CANCELLED = {"cancelled", "canceled", "ملغى", "ملغي", "annulé", "annule"}


def _norm(status: str | None) -> str:
    return (status or "").strip().lower()


def is_pending(status: str | None) -> bool:
    s = _norm(status)
    return s in PENDING or (not s)


def is_confirmed(status: str | None) -> bool:
    s = _norm(status)
    if s in CONFIRMED:
        return True
    raw = (status or "").strip()
    return "مؤك" in raw or "confirm" in s


def is_shipped(status: str | None) -> bool:
    s = _norm(status)
    return s in SHIPPED or s in DELIVERED


def is_delivered(status: str | None) -> bool:
    s = _norm(status)
    if s in DELIVERED:
        return True
    raw = (status or "").strip()
    return "تسليم" in raw and "شحن" not in raw


def is_returned(status: str | None) -> bool:
    return _norm(status) in RETURNED


def is_cancelled(status: str | None) -> bool:
    return _norm(status) in CANCELLED


def is_active_order(status: str | None) -> bool:
    return not is_cancelled(status)


def counts_for_confirmation_rate(status: str | None) -> bool:
    """Confirmed by phone, shipped, or delivered — excludes pending/cancelled."""
    if is_cancelled(status):
        return False
    return is_confirmed(status) or is_shipped(status) or is_delivered(status)


def canonical_status(status: str | None) -> str:
    raw = (status or "").strip()
    if not raw:
        return "في الانتظار"
    if is_cancelled(raw):
        return "ملغي"
    if is_returned(raw):
        return "مرتجع"
    if is_delivered(raw):
        return "تم التسليم"
    if is_shipped(raw) and not is_delivered(raw):
        return "تم الشحن"
    if is_confirmed(raw):
        return "مؤكد"
    if is_pending(raw):
        return "في الانتظار"
    return raw


def apply_admin_status_filter(query: Query, status: str | None) -> Query:
    raw = (status or "").strip()
    if not raw:
        return query

    if is_delivered(raw) or raw.lower() in {"delivered"}:
        return query.filter(
            or_(
                models.Order.status.in_(tuple(DELIVERED)),
                models.Order.status.like("%تسليم%"),
            )
        )

    if is_returned(raw) or "مرتج" in raw:
        return query.filter(
            or_(
                models.Order.status.in_(tuple(RETURNED)),
                models.Order.status.like("%مرتج%"),
            )
        )

    if is_cancelled(raw) or "ملغ" in raw:
        return query.filter(
            or_(
                models.Order.status.in_(tuple(CANCELLED)),
                models.Order.status.like("%ملغ%"),
            )
        )

    if is_shipped(raw) and not is_delivered(raw):
        return query.filter(
            or_(
                models.Order.status.in_(tuple(SHIPPED)),
                models.Order.status.like("%شحن%"),
            )
        ).filter(~models.Order.status.like("%تسليم%"))

    if is_confirmed(raw) or "confirm" in raw.lower() or "مؤك" in raw:
        return query.filter(
            or_(
                models.Order.status.in_(tuple(CONFIRMED)),
                models.Order.status.like("%مؤك%"),
            )
        ).filter(~models.Order.status.like("%شحن%")).filter(
            ~models.Order.status.like("%تسليم%")
        )

    if is_pending(raw) or raw.lower() == "pending":
        return query.filter(
            or_(
                models.Order.status.in_(tuple(PENDING)),
                models.Order.status.is_(None),
                models.Order.status == "",
                models.Order.status == "Pending",
            )
        )

    return query.filter(models.Order.status == raw)


# Late import avoids circular dependency at module load for type hints only.
from . import models  # noqa: E402


ALL_STATUSES = [
    "Pending",
    "Confirmed",
    "Shipped",
    "Delivered",
    "Returned",
    "Cancelled",
    "في الانتظار",
    "مؤكد",
    "تم الشحن",
    "تم التسليم",
    "مرتجع",
    "ملغى",
]
