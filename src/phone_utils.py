import re


def normalize_algerian_phone(phone: str) -> str:
    """Return Algerian mobile as 10 digits starting with 0 (e.g. 0550123456)."""
    clean = re.sub(r"\s+", "", phone or "").replace("+213", "0")
    if clean.startswith("213") and len(clean) >= 12:
        clean = "0" + clean[3:]
    if len(clean) == 9 and clean[0] in {"5", "6", "7"}:
        clean = "0" + clean
    return clean
