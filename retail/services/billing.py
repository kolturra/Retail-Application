"""Sale bills. A bill is built as 'held', finalized once, and never edited afterwards.
Money is integer paise; quantity is integer milli-units."""
from datetime import date, datetime

from retail import clock, money
from retail.db import transaction
from retail.guard import writes
from retail.services import audit, gst, shop, stock

PAYMENT_MODES = ("cash", "upi", "card", "emi", "credit")
REFUND_MODES = ("cash", "upi", "card", "credit")


class BillingError(ValueError):
    pass


class SerialUnavailable(BillingError):
    pass


def _bill(conn, bill_id, *, status=None):
    row = conn.execute("SELECT * FROM bill WHERE id = ?", (bill_id,)).fetchone()
    if row is None:
        raise BillingError("No such bill")
    if status is not None and row["status"] != status:
        raise BillingError(f"Bill is {row['status']}, expected {status}")
    return row


def _item(conn, item_id):
    row = conn.execute("SELECT * FROM item WHERE id = ? AND active = 1", (item_id,)).fetchone()
    if row is None:
        raise BillingError("No such item")
    return row


def _check_party(conn, party_id):
    if party_id is not None and conn.execute(
        "SELECT 1 FROM party WHERE id = ?", (party_id,)
    ).fetchone() is None:
        raise BillingError("No such party")


def _next_number(conn, name, prefix):
    conn.execute(
        "INSERT INTO counter(name, value) VALUES (?, 1) ON CONFLICT(name) DO UPDATE SET value = value + 1",
        (name,),
    )
    value = conn.execute("SELECT value FROM counter WHERE name = ?", (name,)).fetchone()[0]
    return f"{prefix}{value:06d}"


def _retax(conn, bill_id):
    """Recompute every line's tax and the bill totals from the stored line amounts."""
    bill = _bill(conn, bill_id)
    s = shop.get_shop(conn)
    party_state = None
    if bill["party_id"] is not None:
        party_state = conn.execute(
            "SELECT state_code FROM party WHERE id = ?", (bill["party_id"],)
        ).fetchone()["state_code"]
    intra = gst.is_intra_state(s["state_code"], party_state)
    inclusive = bool(s["price_includes_gst"])
    taxable = cgst = sgst = igst = grand = 0
    for line in conn.execute(
        "SELECT id, amount_paise, gst_rate_bp FROM bill_line WHERE bill_id = ?", (bill_id,)
    ).fetchall():
        rate = line["gst_rate_bp"] if bill["gst_mode"] == "gst" else 0
        t = gst.split_line(line["amount_paise"], rate, inclusive=inclusive, intra_state=intra)
        conn.execute(
            """UPDATE bill_line SET taxable_paise=?, cgst_paise=?, sgst_paise=?, igst_paise=?, total_paise=?
               WHERE id = ?""",
            (t.taxable, t.cgst, t.sgst, t.igst, t.total, line["id"]),
        )
        taxable += t.taxable
        cgst += t.cgst
        sgst += t.sgst
        igst += t.igst
        grand += t.total
    rounded, round_off = money.round_to_rupee(grand)
    conn.execute(
        """UPDATE bill SET taxable_paise=?, cgst_paise=?, sgst_paise=?, igst_paise=?,
               round_off_paise=?, total_paise=? WHERE id = ?""",
        (taxable, cgst, sgst, igst, round_off, rounded, bill_id),
    )


def _batch_remaining(conn, bill_id, unit_id):
    on_bill = conn.execute(
        "SELECT COALESCE(SUM(qty_milli), 0) FROM bill_line WHERE bill_id = ? AND unit_id = ?",
        (bill_id, unit_id),
    ).fetchone()[0]
    return stock.unit_on_hand(conn, unit_id) - on_bill


def _choose_batch(conn, bill_id, item_id, qty_milli, unit_id, policy):
    """Pick or validate the batch for a line. A line is never split across batches."""
    if unit_id is not None:
        if conn.execute(
            "SELECT 1 FROM stock_unit WHERE id = ? AND item_id = ? AND serial IS NULL AND batch_no IS NOT NULL",
            (unit_id, item_id),
        ).fetchone() is None:
            raise BillingError("That batch does not belong to this item")
        if _batch_remaining(conn, bill_id, unit_id) < qty_milli and policy == "block":
            raise stock.InsufficientStock("Not enough stock in that batch")
        return unit_id
    candidates = stock.batches_in_expiry_order(conn, item_id)
    remaining = {u: _batch_remaining(conn, bill_id, u) for u in candidates}
    for u in candidates:
        if remaining[u] >= qty_milli:
            return u
    if policy == "block":
        raise stock.InsufficientStock("No single batch has enough stock")
    for u in candidates:
        if remaining[u] > 0:
            return u
    raise BillingError("No batch in stock for this item")


@writes
def start_bill(conn, *, party_id=None):
    s = shop.get_shop(conn)
    _check_party(conn, party_id)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO bill(kind, status, party_id, gst_mode, created_at) VALUES ('sale','held',?,?,?)",
            (party_id, "gst" if s["gst_enabled"] else "estimate", clock.now_iso()),
        )
    return cur.lastrowid


@writes
def add_line(conn, bill_id, item_id, qty_milli=1000, *, serial=None, unit_id=None,
             discount_paise=0, rate_paise=None):
    for label, value, optional in (("Quantity", qty_milli, False), ("Discount", discount_paise, False),
                                   ("Rate", rate_paise, True), ("Unit", unit_id, True)):
        if value is None and optional:
            continue
        if type(value) is not int:
            raise BillingError(f"{label} must be a whole number")
    with transaction(conn):
        bill = _bill(conn, bill_id, status="held")
        if bill["kind"] != "sale":
            raise BillingError("Lines can only be added to a sale bill")
        item = _item(conn, item_id)
        if qty_milli <= 0:
            raise BillingError("Quantity must be greater than zero")
        if discount_paise < 0:
            raise BillingError("Discount cannot be negative")
        tracking = item["tracking"]
        if tracking != "weighed" and qty_milli % 1000:
            raise BillingError("Only weighed items can be sold in fractions")
        s = shop.get_shop(conn)
        if tracking == "serial":
            if qty_milli != 1000:
                raise BillingError("Serial-tracked items are sold one unit per line")
            unit = stock.find_serial(conn, item_id, serial or "")
            if unit is None or unit["status"] != "in_stock":
                raise SerialUnavailable(f"Serial {serial!r} is not in stock")
            if conn.execute(
                "SELECT 1 FROM bill_line WHERE bill_id = ? AND unit_id = ?", (bill_id, unit["id"])
            ).fetchone():
                raise SerialUnavailable("That serial is already on this bill")
            unit_id = unit["id"]
        else:
            if tracking == "batch":
                unit_id = _choose_batch(conn, bill_id, item_id, qty_milli, unit_id, s["oversell_policy"])
            else:
                unit_id = None
                already = conn.execute(
                    "SELECT COALESCE(SUM(qty_milli), 0) FROM bill_line WHERE bill_id = ? AND item_id = ?",
                    (bill_id, item_id),
                ).fetchone()[0]
                stock.check_available(conn, item_id, already + qty_milli, s["oversell_policy"])
        rate = item["sell_price_paise"] if rate_paise is None else rate_paise
        if rate < 0:
            raise BillingError("Rate cannot be negative")
        amount = money.line_amount(rate, qty_milli) - discount_paise
        if amount < 0:
            raise BillingError("Discount is larger than the line amount")
        cur = conn.execute(
            """INSERT INTO bill_line(bill_id, item_id, unit_id, qty_milli, rate_paise, discount_paise,
                   amount_paise, gst_rate_bp) VALUES (?,?,?,?,?,?,?,?)""",
            (bill_id, item_id, unit_id, qty_milli, rate, discount_paise, amount, item["gst_rate_bp"]),
        )
        _retax(conn, bill_id)
    return cur.lastrowid


@writes
def remove_line(conn, bill_id, line_id):
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        cur = conn.execute("DELETE FROM bill_line WHERE id = ? AND bill_id = ?", (line_id, bill_id))
        if cur.rowcount == 0:
            raise BillingError("No such line on this bill")
        _retax(conn, bill_id)


@writes
def set_party(conn, bill_id, party_id):
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        _check_party(conn, party_id)
        conn.execute("UPDATE bill SET party_id = ? WHERE id = ?", (party_id, bill_id))
        _retax(conn, bill_id)


def get_bill(conn, bill_id):
    bill = _bill(conn, bill_id)
    lines = conn.execute("SELECT * FROM bill_line WHERE bill_id = ? ORDER BY id", (bill_id,)).fetchall()
    return {"bill": bill, "lines": lines}


def list_held(conn):
    return conn.execute(
        "SELECT * FROM bill WHERE kind = 'sale' AND status = 'held' ORDER BY id"
    ).fetchall()


@writes
def cancel_held(conn, bill_id):
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        conn.execute("UPDATE bill SET status = 'cancelled' WHERE id = ?", (bill_id,))
        audit.log(conn, "cancel_held", "bill", bill_id)


@writes
def finalize(conn, bill_id, payments, *, today=None):
    """Finish a held sale bill. `payments` is [(mode, amount_paise), ...]."""
    if today is not None and not (isinstance(today, date) and not isinstance(today, datetime)):
        raise BillingError("today must be a date")
    for entry in payments:
        if type(entry) not in (tuple, list) or len(entry) != 2:
            raise BillingError("Each payment must be a (mode, amount) pair")
        if type(entry[1]) is not int:
            raise BillingError("Payment amount must be a whole number of paise")
    today = today or clock.today()
    with transaction(conn):
        bill = _bill(conn, bill_id, status="held")
        if bill["kind"] != "sale":
            raise BillingError("Only sale bills are finalized here")
        lines = conn.execute(
            """SELECT l.*, i.tracking, i.warranty_months FROM bill_line l
               JOIN item i ON i.id = l.item_id WHERE l.bill_id = ? ORDER BY l.id""",
            (bill_id,),
        ).fetchall()
        if not lines:
            raise BillingError("Cannot finalize an empty bill")
        for mode, amount in payments:
            if mode not in PAYMENT_MODES:
                raise BillingError(f"Unknown payment mode {mode!r}")
            if amount <= 0:
                raise BillingError("Each payment must be greater than zero")
        if sum(amount for _, amount in payments) != bill["total_paise"]:
            raise BillingError("Payments must add up exactly to the bill total")
        if any(mode == "credit" for mode, _ in payments) and bill["party_id"] is None:
            raise BillingError("Credit sales need a customer")

        policy = shop.get_shop(conn)["oversell_policy"]
        needed = {}
        per_unit = {}
        for line in lines:
            if line["tracking"] == "serial":
                unit = conn.execute(
                    "SELECT status FROM stock_unit WHERE id = ?", (line["unit_id"],)
                ).fetchone()
                if unit is None or unit["status"] != "in_stock":
                    raise SerialUnavailable("A serial on this bill is no longer in stock")
            else:
                needed[line["item_id"]] = needed.get(line["item_id"], 0) + line["qty_milli"]
                if line["unit_id"] is not None:
                    per_unit[line["unit_id"]] = per_unit.get(line["unit_id"], 0) + line["qty_milli"]
        for item_id, qty in needed.items():
            stock.check_available(conn, item_id, qty, policy)
        if policy == "block":
            for unit_id, qty in per_unit.items():
                if stock.unit_on_hand(conn, unit_id) < qty:
                    raise stock.InsufficientStock("Not enough stock in a batch on this bill")

        bill_no = _next_number(conn, "sale", "S")
        now = clock.now_iso()
        conn.execute(
            "UPDATE bill SET status = 'final', bill_no = ?, finalized_at = ? WHERE id = ?",
            (bill_no, now, bill_id),
        )
        for line in lines:
            stock._record(conn, line["item_id"], -line["qty_milli"], "sale", "bill", bill_id, line["unit_id"])
            if line["tracking"] == "serial":
                conn.execute("UPDATE stock_unit SET status = 'sold' WHERE id = ?", (line["unit_id"],))
                if line["warranty_months"]:
                    end = clock.add_months(today, line["warranty_months"])
                    conn.execute(
                        "INSERT INTO warranty(unit_id, bill_id, start_date, end_date) VALUES (?,?,?,?)",
                        (line["unit_id"], bill_id, today.isoformat(), end.isoformat()),
                    )
        for mode, amount in payments:
            conn.execute(
                "INSERT INTO payment(bill_id, mode, amount_paise, created_at) VALUES (?,?,?,?)",
                (bill_id, mode, amount, now),
            )
        audit.log(conn, "finalize", "bill", bill_id, bill_no)
    return bill_no
