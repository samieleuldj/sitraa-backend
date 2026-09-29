import logging
import os
import time
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

IP_LOOKUP_TTL_SECONDS = int(os.getenv("IP_LOOKUP_TTL_SECONDS", "86400"))
IP_LOOKUP_TIMEOUT = float(os.getenv("IP_LOOKUP_TIMEOUT", "2.5"))
_count_private = os.getenv("ANALYTICS_COUNT_PRIVATE_IPS", "").lower() in {"1", "true", "yes"}

_cache: dict[str, tuple[float, "IpLookupResult"]] = {}


@dataclass
class IpLookupResult:
    ip: str
    country_code: Optional[str]
    country_name: Optional[str]
    city: Optional[str]
    isp: Optional[str]
    is_proxy: bool
    is_hosting: bool
    is_private: bool
    is_valid: bool
    lookup_failed: bool


def _is_private_ip(ip: str) -> bool:
    try:
        value = ip_address(ip)
    except ValueError:
        return True

    if value.is_private or value.is_loopback or value.is_link_local:
        return True

    for network in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
        if value in ip_network(network):
            return True
    return False


def _build_result(
    ip: str,
    *,
    country_code: Optional[str] = None,
    country_name: Optional[str] = None,
    city: Optional[str] = None,
    isp: Optional[str] = None,
    is_proxy: bool = False,
    is_hosting: bool = False,
    is_private: bool = False,
    lookup_failed: bool = False,
) -> IpLookupResult:
    is_algeria = country_code == "DZ"
    is_valid = (
        is_algeria
        and not is_proxy
        and not is_hosting
        and (not is_private or _count_private)
    )
    return IpLookupResult(
        ip=ip,
        country_code=country_code,
        country_name=country_name,
        city=city,
        isp=isp,
        is_proxy=is_proxy,
        is_hosting=is_hosting,
        is_private=is_private,
        is_valid=is_valid,
        lookup_failed=lookup_failed,
    )


def lookup_ip(ip: Optional[str]) -> IpLookupResult:
    if not ip:
        return _build_result("", lookup_failed=True)

    ip = ip.strip()
    if _is_private_ip(ip):
        return _build_result(ip, is_private=True, country_code="LOCAL")

    cached = _cache.get(ip)
    if cached and cached[0] > time.time():
        return cached[1]

    try:
        fields = "status,message,country,countryCode,city,isp,proxy,hosting,mobile,query"
        url = f"http://ip-api.com/json/{ip}?fields={fields}"
        with httpx.Client(timeout=IP_LOOKUP_TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "success":
            result = _build_result(ip, lookup_failed=True)
        else:
            result = _build_result(
                ip,
                country_code=data.get("countryCode"),
                country_name=data.get("country"),
                city=data.get("city"),
                isp=data.get("isp"),
                is_proxy=bool(data.get("proxy")),
                is_hosting=bool(data.get("hosting")),
            )
    except Exception as exc:
        logger.warning("IP lookup failed for %s: %s", ip, exc)
        result = _build_result(ip, lookup_failed=True)

    _cache[ip] = (time.time() + IP_LOOKUP_TTL_SECONDS, result)
    return result
