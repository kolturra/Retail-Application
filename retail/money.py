"""Money is integer paise; quantity is integer milli-units. No floats anywhere."""
from decimal import ROUND_HALF_UP, Decimal

_ONE = Decimal(1)


def _round(value: Decimal) -> int:
    return int(value.quantize(_ONE, rounding=ROUND_HALF_UP))


def rupees_to_paise(value) -> int:
    return _round(Decimal(str(value)) * 100)


def paise_to_str(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{whole}.{frac:02d}"


def qty_to_milli(value) -> int:
    return _round(Decimal(str(value)) * 1000)


def milli_to_str(milli: int) -> str:
    sign = "-" if milli < 0 else ""
    whole, frac = divmod(abs(milli), 1000)
    if frac == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{frac:03d}".rstrip("0")


def line_amount(rate_paise: int, qty_milli: int) -> int:
    return _round(Decimal(rate_paise) * Decimal(qty_milli) / 1000)


def round_to_rupee(total_paise: int) -> tuple[int, int]:
    """Return (total rounded to the nearest rupee, adjustment applied)."""
    rounded = _round(Decimal(total_paise) / 100) * 100
    return rounded, rounded - total_paise
