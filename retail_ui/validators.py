import re

_GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$", re.ASCII)


def gstin_error(text, state_code):
    """None when blank (optional) or well-formed and matching the state code, else a reason."""
    text = (text or "").strip().upper()
    if not text:
        return None
    if not _GSTIN.match(text):
        return "format"
    if text[:2] != state_code:
        return "state"
    return None


def phone_digits(text):
    return re.sub(r"[^0-9]", "", text or "")
