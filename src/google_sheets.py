import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from .phone_utils import normalize_algerian_phone

logger = logging.getLogger(__name__)

ALGIERS_TZ = timezone(timedelta(hours=1))


def get_webhook_url(product_name: str = "") -> Optional[str]:
    # Default webhook for Cellulite
    url = os.getenv("GOOGLE_SHEET_WEBHOOK_URL") or os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    
    # New webhook for Mini Clima and Makeup Bag
    new_products_webhook = "https://script.google.com/macros/s/AKfycbwSvzh7dt9QGEYVnyMBf7deyUWrbFvQj472a03OyxLbc4CmcnjSC5BjkZvBSQdRZ16Z4w/exec"
    
    name = str(product_name or "").lower()
    if "مكيف" in name or "clima" in name or "حقيبة" in name or "مكياج" in name or "makeup" in name:
        return new_products_webhook

    if not url or url.strip() in {"", "your_google_script_url_here"}:
        return None
    return url.strip()


def _delivery_label(delivery_type: str) -> str:
    if delivery_type in {"home", "منزل"}:
        return "منزل"
    if delivery_type in {"office", "مكتب"}:
        return "مكتب"
    return delivery_type or ""


def build_sheet_payload(order: dict) -> dict:
    quantity = int(order.get("quantity") or 1)
    unit_price = float(order.get("unit_price") or 0)
    product_price = float(order.get("product_price") or (unit_price * quantity))
    total_price = float(order["total_price"])

    shipping_cost = order.get("shipping_cost")
    if shipping_cost is None:
        shipping_cost = max(0.0, total_price - product_price)
    else:
        shipping_cost = float(shipping_cost)

    delivery_type = order.get("delivery_type") or "home"

    return {
        "order_id": order["order_id"],
        "date": datetime.now(ALGIERS_TZ).strftime("%d/%m/%Y %H:%M:%S"),
        "customer_name": order["customer_name"],
        "phone": normalize_algerian_phone(order["phone"]),
        "wilaya": order["wilaya"],
        "commune": order["commune"],
        "product_name": order["product_name"],
        "quantity": quantity,
        "unit_price": unit_price,
        "product_price": product_price,
        "shipping_cost": shipping_cost,
        "total_price": total_price,
        "delivery_type": _delivery_label(str(delivery_type)),
        "status": "في الانتظار",
        "tracking_number": "",
        "notes": order.get("notes") or "",
    }


def _post_google_script(url: str, payload: dict) -> httpx.Response:
    """
    Google Apps Script web apps return 302 redirects.
    Re-POST the JSON body on each redirect (httpx defaults to GET on 302).
    """
    headers = {"Content-Type": "application/json"}
    with httpx.Client(timeout=12.0) as client:
        current_url = url
        response = None
        for _ in range(5):
            response = client.post(
                current_url,
                json=payload,
                headers=headers,
                follow_redirects=False,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            redirect_url = response.headers.get("location")
            if not redirect_url:
                break
            current_url = redirect_url
        if response is None:
            raise RuntimeError("Google Sheets webhook: no response")
        return response


def send_order_to_google_sheets(order: dict) -> bool:
    url = get_webhook_url(order.get("product_name", ""))
    if not url:
        logger.warning(
            "SHEETS SKIP order=%s reason=GOOGLE_SHEET_WEBHOOK_URL missing",
            order.get("order_id"),
        )
        return False

    payload = build_sheet_payload(order)

    try:
        response = _post_google_script(url, payload)
        body = response.text[:500]

        if response.status_code >= 400:
            logger.warning(
                "SHEETS FAIL order=%s status=%s body=%s",
                order.get("order_id"),
                response.status_code,
                body,
            )
            return False

        try:
            data = response.json()
            if data.get("result") == "error" or data.get("success") is False:
                logger.warning(
                    "SHEETS FAIL order=%s apps_script_error=%s",
                    order.get("order_id"),
                    body,
                )
                return False
        except ValueError:
            pass

        logger.warning(
            "SHEETS OK order=%s status=%s body=%s",
            order.get("order_id"),
            response.status_code,
            body[:200],
        )
        return True
    except Exception:
        logger.exception("SHEETS ERROR order=%s", order.get("order_id"))
        return False


def push_order_status_to_sheet(
    order_id: str,
    status: str,
    tracking_number: str | None = None,
) -> bool:
    url = get_webhook_url()
    if not url:
        return False

    payload = {
        "action": "status_sync",
        "order_id": order_id.strip(),
        "status": status.strip(),
        "tracking_number": (tracking_number or "").strip(),
    }
    if not payload["order_id"] or not payload["status"]:
        return False

    try:
        response = _post_google_script(url, payload)
        if response.status_code >= 400:
            logger.warning(
                "SHEETS status sync fail order=%s status=%s http=%s",
                order_id,
                status,
                response.status_code,
            )
            return False
        return True
    except Exception:
        logger.exception("SHEETS status sync error order=%s", order_id)
        return False
