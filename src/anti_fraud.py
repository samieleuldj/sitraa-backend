import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models

TEST_PHONE = "0555555555"
HIGH_PRICE_THRESHOLD = int(os.getenv("HIGH_PRICE_THRESHOLD", "5000"))
MAX_QTY_HIGH_PRICE = int(os.getenv("MAX_QTY_HIGH_PRICE", "2"))
MAX_QTY_LOW_PRICE = int(os.getenv("MAX_QTY_LOW_PRICE", "4"))
ORDERS_PER_IP_PER_DAY = int(os.getenv("ORDERS_PER_IP_PER_DAY", "1"))
ORDERS_PER_PHONE_PER_DAY = int(os.getenv("ORDERS_PER_PHONE_PER_DAY", "1"))

MOBILE_UA_PATTERN = re.compile(
    r"Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile",
    re.IGNORECASE,
)


def get_whitelisted_ips() -> set[str]:
    raw = os.getenv("ALLOWED_DESKTOP_IPS", "")
    return {ip.strip() for ip in raw.split(",") if ip.strip()}


def is_mobile_user_agent(user_agent: str) -> bool:
    return bool(MOBILE_UA_PATTERN.search(user_agent or ""))


def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def is_ip_whitelisted(ip: Optional[str]) -> bool:
    if not ip:
        return False
    return ip in get_whitelisted_ips()


def validate_order_security(
    *,
    request: Request,
    db: Session,
    phone: str,
    quantity: int,
    unit_price: float,
    delivery_type: str,
) -> None:
    user_agent = request.headers.get("user-agent", "")
    client_ip = get_client_ip(request)
    whitelisted = is_ip_whitelisted(client_ip)

    if delivery_type not in {"home", "office"}:
        raise HTTPException(status_code=400, detail="يرجى اختيار نوع التوصيل")

    max_qty = MAX_QTY_HIGH_PRICE if unit_price >= HIGH_PRICE_THRESHOLD else MAX_QTY_LOW_PRICE
    if quantity < 1 or quantity > max_qty:
        raise HTTPException(
            status_code=400,
            detail=f"الحد الأقصى للكمية هو {max_qty} قطعة لهذا المنتج",
        )

    if phone == TEST_PHONE or whitelisted:
        return

    since = datetime.now(timezone.utc) - timedelta(hours=24)

    if client_ip:
        ip_orders = (
            db.query(models.Order)
            .filter(
                models.Order.ip_address == client_ip,
                models.Order.created_at >= since,
                models.Order.phone != TEST_PHONE,
            )
            .count()
        )
        if ip_orders >= ORDERS_PER_IP_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail="تم استلام طلب من هذا الاتصال اليوم. يرجى المحاولة غداً أو التواصل عبر الواتساب.",
            )

    phone_orders = (
        db.query(models.Order)
        .filter(
            models.Order.phone == phone,
            models.Order.created_at >= since,
            models.Order.phone != TEST_PHONE,
        )
        .count()
    )
    if phone_orders >= ORDERS_PER_PHONE_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail="تم استلام طلب بهذا الرقم اليوم. إذا كان خطأ، تواصل معنا عبر الواتساب.",
        )


def get_max_quantity(unit_price: float) -> int:
    return MAX_QTY_HIGH_PRICE if unit_price >= HIGH_PRICE_THRESHOLD else MAX_QTY_LOW_PRICE
