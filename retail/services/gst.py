from dataclasses import dataclass


@dataclass(frozen=True)
class LineTax:
    taxable: int
    cgst: int
    sgst: int
    igst: int
    total: int


def _div_round(numerator: int, denominator: int) -> int:
    """Integer division rounded half-up (numerator >= 0)."""
    return (2 * numerator + denominator) // (2 * denominator)


def split_line(amount_paise, rate_bp, *, inclusive, intra_state):
    if rate_bp == 0:
        return LineTax(amount_paise, 0, 0, 0, amount_paise)
    if inclusive:
        taxable = _div_round(amount_paise * 10000, 10000 + rate_bp)
        tax = amount_paise - taxable
        total = amount_paise
    else:
        taxable = amount_paise
        tax = _div_round(amount_paise * rate_bp, 10000)
        total = amount_paise + tax
    if intra_state:
        cgst = tax // 2
        return LineTax(taxable, cgst, tax - cgst, 0, total)
    return LineTax(taxable, 0, 0, tax, total)


def is_intra_state(shop_state, party_state):
    return not party_state or party_state == shop_state


def place_of_supply(shop_state, party_state):
    """The state the sale is taxed for: the customer's when known, else the shop's (the same rule
    is_intra_state uses, so intra-state <=> place of supply == shop state)."""
    return party_state or shop_state
