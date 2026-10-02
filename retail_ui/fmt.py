"""Display formatting and parsing. Money stays integer paise and quantity integer milli-units
everywhere else; only this module turns them into text."""
import re
from decimal import Decimal

from retail import money


_NUMBER = re.compile(r"^[+-]?[0-9]+(\.[0-9]+)?$")


# a comma is only accepted as a proper thousands separator: 1,234.50 (groups of 3) or the Indian
# 1,23,456.78 that fmt.rupees() prints. "1,5" must never silently become 15.
_GROUPED = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d{1,2}(,\d{2})*,\d{3})(\.[0-9]+)?$")


def _strict(text: str, what: str, max_decimals: int | None = None) -> str:
    cleaned = (text or "").replace("₹", "").strip()
    if "," in cleaned:
        if not _GROUPED.match(cleaned):
            raise ValueError(f"Not {what}: {text!r}")
        cleaned = cleaned.replace(",", "")
    if not _NUMBER.match(cleaned):
        raise ValueError(f"Not {what}: {text!r}")
    if max_decimals is not None and "." in cleaned and len(cleaned.split(".")[1]) > max_decimals:
        raise ValueError(f"Too many decimals: {text!r}")
    return cleaned


def _group(whole: int) -> str:
    digits = str(whole)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def rupees(paise: int, symbol: str = "₹") -> str:
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{symbol}{_group(whole)}.{frac:02d}"


def parse_rupees(text: str) -> int:
    cleaned = _strict(text, "an amount", 2)
    try:
        return money.rupees_to_paise(Decimal(cleaned))
    except ArithmeticError as exc:
        raise ValueError(f"Not an amount: {text!r}") from exc


def qty(milli: int) -> str:
    return money.milli_to_str(milli)


def parse_qty(text: str) -> int:
    cleaned = _strict(text, "a quantity", 3)
    try:
        milli = money.qty_to_milli(cleaned)
    except ArithmeticError as exc:
        raise ValueError(f"Not a quantity: {text!r}") from exc
    if milli <= 0:
        raise ValueError("Quantity must be greater than zero")
    return milli


def parse_signed_qty(text: str) -> int:
    """A non-zero quantity with an optional sign, in whole milli-units (at most 3 decimals)."""
    cleaned = _strict(text, "a quantity")
    if "." in cleaned and len(cleaned.split(".")[1]) > 3:
        raise ValueError(f"Too many decimals: {text!r}")
    milli = money.qty_to_milli(cleaned)
    if milli == 0:
        raise ValueError("Quantity must not be zero")
    return milli


def date_text(iso: str) -> str:
    if not iso:
        return ""
    day, _, clock_part = iso.partition("T")
    y, m, d = day.split("-")
    return f"{d}-{m}-{y}" + (f" {clock_part[:5]}" if clock_part else "")
