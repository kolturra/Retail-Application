from dataclasses import dataclass

from retail import clock, money
from retail.db import transaction
from retail.guard import writes
from retail.services import audit, stock


class PurchaseError(ValueError):
    pass


@dataclass(frozen=True)
class PurchaseLine:
    item_id: int
    qty_milli: int
    cost_paise: int
    serials: tuple = ()
    batch_no: str | None = None
    expiry: str | None = None


def _receive(conn, purchase_id, line):
    item = conn.execute("SELECT * FROM item WHERE id = ? AND active = 1", (line.item_id,)).fetchone()
    if item is None:
        raise PurchaseError("No such item")
    if line.qty_milli <= 0:
        raise PurchaseError("Quantity must be greater than zero")
    if line.cost_paise < 0:
        raise PurchaseError("Cost cannot be negative")
    tracking = item["tracking"]
    if tracking != "weighed" and line.qty_milli % 1000:
        raise PurchaseError("Only weighed items can be bought in fractions")
    if tracking == "serial":
        if not line.serials or line.qty_milli != 1000 * len(line.serials):
            raise PurchaseError("Serial items need exactly one serial number per unit")
        for serial in line.serials:
            unit_id = stock._add_unit(conn, line.item_id, serial=serial)
            stock._record(conn, line.item_id, 1000, "purchase", "purchase", purchase_id, unit_id)
    elif tracking == "batch":
        if not line.batch_no:
            raise PurchaseError("Batch items need a batch number")
        unit_id = stock.find_batch(conn, line.item_id, line.batch_no)
        if unit_id is None:
            unit_id = stock._add_unit(conn, line.item_id, batch_no=line.batch_no, expiry=line.expiry)
        stock._record(conn, line.item_id, line.qty_milli, "purchase", "purchase", purchase_id, unit_id)
    else:
        stock._record(conn, line.item_id, line.qty_milli, "purchase", "purchase", purchase_id)
    conn.execute(
        "INSERT INTO purchase_line(purchase_id, item_id, qty_milli, cost_paise) VALUES (?,?,?,?)",
        (purchase_id, line.item_id, line.qty_milli, line.cost_paise),
    )
    conn.execute("UPDATE item SET buy_price_paise = ? WHERE id = ?", (line.cost_paise, line.item_id))
    return money.line_amount(line.cost_paise, line.qty_milli)


@writes
def create_purchase(conn, *, party_id, invoice_no, lines, date_iso=None):
    lines = list(lines)  # a generator must not be silently exhausted by validation
    if not lines:
        raise PurchaseError("A purchase needs at least one line")
    for line in lines:
        if not isinstance(line, PurchaseLine):
            raise PurchaseError("Invalid purchase line")
        for value in (line.qty_milli, line.cost_paise):
            if type(value) is not int:
                raise PurchaseError("Quantity and cost must be whole numbers")
        if type(line.serials) not in (tuple, list) or not all(
                type(s) is str and s.strip() for s in line.serials):
            raise PurchaseError("Serials must be a list of non-empty text values")
    if party_id is not None and conn.execute(
            "SELECT 1 FROM party WHERE id = ?", (party_id,)).fetchone() is None:
        raise PurchaseError("No such party")
    with transaction(conn):
        purchase_id = conn.execute(
            "INSERT INTO purchase(party_id, invoice_no, purchase_date) VALUES (?,?,?)",
            (party_id, invoice_no, date_iso or clock.today().isoformat()),
        ).lastrowid
        total = sum(_receive(conn, purchase_id, line) for line in lines)
        conn.execute("UPDATE purchase SET total_paise = ? WHERE id = ?", (total, purchase_id))
        audit.log(conn, "create", "purchase", purchase_id, invoice_no or "")
    return purchase_id
