import re

WILAYA_CODE_RE = re.compile(r"^(\d{1,2})")

# Old checkout labels (wrong codes/names before 2026-06 fix) → official DHD code.
LEGACY_WILAYA_LABELS: dict[str, int] = {
    "49 - \u0627\u0644\u0645\u063a\u064a\u0631": 57,
    "50 - \u0627\u0644\u0645\u0646\u064a\u0639\u0629": 58,
    "52 - \u0628\u0631\u062c \u0628\u0627\u062c\u064a \u0645\u062e\u062a\u0627\u0631": 50,
    "53 - \u0628\u0646\u064a \u0639\u0628\u0627\u0633": 52,
    "54 - \u062a\u0642\u0631\u062a": 55,
    "55 - \u062c\u0627\u0646\u062a": 56,
    "56 - \u0639\u064a\u0646 \u0635\u0627\u0644\u062d": 53,
    "57 - \u0625\u0646 \u0642\u0632\u0627\u0645": 54,
    "58 - \u0625\u0646 \u0623\u0645\u064a\u0646\u0627\u0633": 57,
}


def extract_wilaya_code(wilaya: str) -> int:
    label = re.sub(r"\s+", " ", (wilaya or "").strip())
    if not label:
        return 0
    if label in LEGACY_WILAYA_LABELS:
        return LEGACY_WILAYA_LABELS[label]
    match = WILAYA_CODE_RE.match(label)
    if not match:
        return 0
    return int(match.group(1))
