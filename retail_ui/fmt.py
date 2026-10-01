"""Display formatting and parsing. Money stays integer paise and quantity integer milli-units
everywhere else; only this module turns them into text."""
from decimal import Decimal, InvalidOperation

from retail import money


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
    cleaned = (text or "").replace("₹", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Not an amount: {text!r}") from exc
    if not value.is_finite():
        raise ValueError(f"Not an amount: {text!r}")
    return money.rupees_to_paise(value)


def qty(milli: int) -> str:
    return money.milli_to_str(milli)


def parse_qty(text: str) -> int:
    try:
        milli = money.qty_to_milli((text or "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"Not a quantity: {text!r}") from exc
    if milli <= 0:
        raise ValueError("Quantity must be greater than zero")
    return milli


def date_text(iso: str) -> str:
    if not iso:
        return ""
    day, _, clock_part = iso.partition("T")
    y, m, d = day.split("-")
    return f"{d}-{m}-{y}" + (f" {clock_part[:5]}" if clock_part else "")
