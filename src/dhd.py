import logging
import os
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from .wilaya_codes import extract_wilaya_code

logger = logging.getLogger(__name__)

DEFAULT_DHD_API_URL = "https://platform.dhd-dz.com"
LEGACY_DHD_API_URL = "https://dhd.ecotrack.dz"


def normalize_phone_for_dhd(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("213") and len(digits) >= 12:
        digits = "0" + digits[3:]
    if len(digits) == 9 and digits[0] in "567":
        digits = "0" + digits
    return digits


def get_dhd_config() -> tuple[str, str]:
    token = (os.getenv("DHD_API_TOKEN") or "").strip()
    base_url = (os.getenv("DHD_API_URL") or DEFAULT_DHD_API_URL).rstrip("/")
    if base_url.rstrip("/") == LEGACY_DHD_API_URL:
        base_url = DEFAULT_DHD_API_URL
    return token, base_url


def extract_tracking(response: dict[str, Any]) -> str | None:
    for key in ("tracking", "num_tracking", "tracking_number", "code"):
        value = response.get(key)
        if value:
            return str(value)

    data = response.get("data")
    if isinstance(data, dict):
        for key in ("tracking", "num_tracking", "tracking_number", "code"):
            value = data.get(key)
            if value:
                return str(value)

    return None


def _resolve_redirect_url(current_url: str, response: httpx.Response) -> str | None:
    location = response.headers.get("location") or response.headers.get("Location")
    if not location:
        return None
    return urljoin(current_url, location)


def _parse_json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception as exc:
        raise ValueError(f"رد DHD غير صالح: {response.text[:200]}") from exc
    if not isinstance(data, dict):
        return {"data": data}
    return data


def _dhd_request(
    method: str,
    path: str,
    *,
    json_payload: dict | None = None,
    params: dict | None = None,
) -> tuple[httpx.Response, dict[str, Any]]:
    token, base_url = get_dhd_config()
    if not token:
        raise ValueError("DHD_API_TOKEN غير مضبوط في EasyPanel")

    headers = {"Authorization": f"Bearer {token}"}
    if json_payload is not None:
        headers["Content-Type"] = "application/json"

    url = f"{base_url}{path}"
    with httpx.Client(timeout=15.0) as client:
        response = None
        for _ in range(5):
            if method == "POST":
                response = client.post(
                    url,
                    json=json_payload,
                    headers=headers,
                    params=params,
                    follow_redirects=False,
                )
            else:
                response = client.get(
                    url,
                    headers=headers,
                    params=params,
                    follow_redirects=False,
                )

            if response.status_code not in {301, 302, 303, 307, 308}:
                break

            next_url = _resolve_redirect_url(url, response)
            if not next_url or next_url == url:
                break
            logger.info("DHD redirect %s -> %s", url, next_url)
            url = next_url.rstrip("/")

        if response is None:
            raise ValueError("لا يوجد رد من DHD")

    data = _parse_json_response(response)
    return response, data


def create_dhd_parcel(order: dict[str, Any]) -> dict[str, Any]:
    wilaya_code = extract_wilaya_code(str(order.get("wilaya", "")))
    if wilaya_code < 1 or wilaya_code > 58:
        raise ValueError("كود الولاية غير صالح")

    delivery_type = str(order.get("delivery_type") or "home")
    stop_desk = 1 if delivery_type in {"office", "مكتب"} else 0

    phone = normalize_phone_for_dhd(str(order.get("phone", "")))
    if not phone:
        raise ValueError("رقم الهاتف مطلوب")

    from .commune_resolver import resolve_commune_for_dhd

    raw_commune = str(order.get("commune") or "")
    dhd_commune = resolve_commune_for_dhd(raw_commune, wilaya_code, stop_desk=bool(stop_desk))

    payload = {
        "reference": str(order.get("order_id") or ""),
        "nom_client": str(order.get("customer_name") or ""),
        "telephone": phone,
        "adresse": f"{dhd_commune}, {order.get('wilaya', '')}".strip(", "),
        "commune": dhd_commune,
        "code_wilaya": wilaya_code,
        "montant": int(float(order.get("total_price") or 0)),
        "produit": str(order.get("product_name") or ""),
        "type": 1,
        "stop_desk": stop_desk,
        "remarque": str(order.get("notes") or ""),
    }

    response, data = _dhd_request("POST", "/api/v1/create/order", json_payload=payload)

    if response.status_code >= 400 or data.get("success") is False:
        message = data.get("message") or response.text[:200]
        raise ValueError(f"فشل إرسال DHD: {message}")

    tracking = extract_tracking(data)
    if not tracking:
        logger.warning("DHD parcel created without tracking for %s: %s", order.get("order_id"), data)

    return {"tracking": tracking, "response": data}


def _extract_order_row(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if payload.get("tracking") or payload.get("reference"):
            return payload
        nested = payload.get("data")
        if isinstance(nested, dict) and (nested.get("tracking") or nested.get("reference")):
            return nested
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict) and (item.get("tracking") or item.get("reference")):
                    return item
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and (item.get("tracking") or item.get("reference")):
                return item
    return None


def _matches_dhd_lookup(row: dict[str, Any], *, tracking: str = "", reference: str = "") -> bool:
    row_tracking = str(row.get("tracking") or "").strip()
    row_reference = str(row.get("reference") or "").strip()
    if tracking and row_tracking == tracking:
        return True
    if reference and row_reference and row_reference == reference:
        return True
    return False


def fetch_dhd_orders(*, max_pages: int = 5, per_page: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        response, data = _dhd_request(
            "GET",
            "/api/v1/get/orders",
            params={"page": page, "per_page": per_page},
        )
        if response.status_code >= 400 or data.get("success") is False:
            break

        batch = data.get("data")
        if not isinstance(batch, list) or not batch:
            break

        rows.extend(item for item in batch if isinstance(item, dict))
        last_page = int(data.get("last_page") or page)
        if page >= last_page:
            break

    return rows


def find_dhd_order(*, tracking: str = "", reference: str = "") -> dict[str, Any] | None:
    tracking = (tracking or "").strip()
    reference = (reference or "").strip()
    if not tracking and not reference:
        return None

    rows = fetch_dhd_orders()
    for row in rows:
        if _matches_dhd_lookup(row, tracking=tracking, reference=reference):
            return row
    return None


def get_dhd_order_status(tracking: str, reference: str | None = None) -> dict[str, Any]:
    tracking = (tracking or "").strip()
    reference = (reference or "").strip()
    if not tracking and not reference:
        raise ValueError("رقم التتبع أو مرجع الطلبية مطلوب")

    row = find_dhd_order(tracking=tracking, reference=reference)
    if row:
        return row

    raise ValueError(f"الطلبية غير موجودة في DHD: {tracking or reference}")


def map_dhd_status(raw: dict[str, Any]) -> str | None:
    row = _extract_order_row(raw)
    if not row:
        return None

    global_status = str(row.get("global_status") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    livred_at = row.get("livred_at")
    return_id = row.get("return_id")
    return_asked_at = row.get("return_asked_at")

    if livred_at or global_status == "livre":
        return "تم التسليم"

    if "livré" in status or "livre_non" in status or status == "livre":
        return "تم التسليم"
    # DHD: encaissé = COD collected → delivered for P&L
    if "encaiss" in status:
        return "تم التسليم"

    if global_status == "retour" or return_id or return_asked_at or status.startswith("retour"):
        return "مرتجع"

    if "annul" in status or "cancel" in status or "ملغ" in status:
        return "ملغي"

    if global_status == "en_process":
        return "تم الشحن"

    shipped_markers = (
        "vers_wilaya",
        "prete_a_expedier",
        "en_livraison",
        "expedie",
        "expédi",
        "transit",
        "dispatch",
        "livraison",
        "shipp",
        "شحن",
    )
    if any(marker in status for marker in shipped_markers):
        return "تم الشحن"

    for key in ("status", "statut", "etat", "state", "situation", "last_status", "global_status"):
        text = str(row.get(key) or "").strip().lower()
        if not text:
            continue
        if any(word in text for word in ("delivered", "تسليم", "livré")):
            return "تم التسليم"
        if "livre" in text and "livraison" not in text:
            return "تم التسليم"
        if any(word in text for word in ("retour", "return", "مرتج")):
            return "مرتجع"

    return None
