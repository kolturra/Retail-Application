"""Read-only reports. Deliberately not guarded, so they keep working after license expiry."""
import csv
import re
from datetime import date

from retail import money

SALES_COLUMNS = ["bill_no", "bill_date", "kind", "party", "gstin", "taxable_paise", "cgst_paise",
                 "sgst_paise", "igst_paise", "round_off_paise", "total_paise"]

STOCK_COLUMNS = ["item", "sku", "unit", "active", "on_hand_milli", "reorder_milli", "buy_price_paise",
                 "sell_price_paise"]
LEDGER_COLUMNS = ["party", "phone", "date", "entry", "ref", "debit_paise", "credit_paise", "balance_paise"]

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")  # OWASP CSV-injection list


def _check_day(value):
    if type(value) is not str or not _DATE_RE.fullmatch(value):
        raise ValueError(f"date must be a YYYY-MM-DD string, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"not a valid calendar date: {value!r}") from None
    return value


def _check_range(start, end):
    if _check_day(start) > _check_day(end):
        raise ValueError(f"start {start} is after end {end}")


check_range = _check_range


def _safe_text(value):
    """Defuse CSV formula injection: text starting with = + - @ TAB or CR gets a leading single quote."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


_SIGN = "(CASE WHEN b.kind = 'sale_return' THEN -1 ELSE 1 END)"


def sales_register(conn, start, end):
    _check_range(start, end)
    rows = conn.execute(
        f"""SELECT b.bill_no, date(b.finalized_at) AS bill_date, b.kind,
                   COALESCE(p.name, '') AS party, COALESCE(p.gstin, '') AS gstin,
                   {_SIGN} * b.taxable_paise AS taxable_paise, {_SIGN} * b.cgst_paise AS cgst_paise,
                   {_SIGN} * b.sgst_paise AS sgst_paise, {_SIGN} * b.igst_paise AS igst_paise,
                   {_SIGN} * b.round_off_paise AS round_off_paise, {_SIGN} * b.total_paise AS total_paise
            FROM bill b LEFT JOIN party p ON p.id = b.party_id
            WHERE b.status = 'final' AND date(b.finalized_at) BETWEEN ? AND ?
            ORDER BY b.finalized_at, b.id""",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def gst_summary(conn, start, end):
    _check_range(start, end)
    rows = conn.execute(
        f"""SELECT l.gst_rate_bp AS gst_rate_bp,
                   SUM({_SIGN} * l.taxable_paise) AS taxable_paise, SUM({_SIGN} * l.cgst_paise) AS cgst_paise,
                   SUM({_SIGN} * l.sgst_paise) AS sgst_paise, SUM({_SIGN} * l.igst_paise) AS igst_paise
            FROM bill_line l JOIN bill b ON b.id = l.bill_id
            WHERE b.status = 'final' AND b.gst_mode = 'gst' AND date(b.finalized_at) BETWEEN ? AND ?
            GROUP BY l.gst_rate_bp ORDER BY l.gst_rate_bp""",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def daily_summary(conn, day):
    _check_day(day)
    totals = {
        r["kind"]: r["total"]
        for r in conn.execute(
            """SELECT kind, SUM(total_paise) AS total FROM bill
               WHERE status = 'final' AND date(finalized_at) = ? GROUP BY kind""",
            (day,),
        )
    }
    by_mode = {
        r["mode"]: r["net"]
        for r in conn.execute(
            f"""SELECT p.mode AS mode, SUM({_SIGN} * p.amount_paise) AS net
                FROM payment p JOIN bill b ON b.id = p.bill_id
                WHERE b.status = 'final' AND date(b.finalized_at) = ? GROUP BY p.mode""",
            (day,),
        )
    }
    sales, returns = totals.get("sale", 0), totals.get("sale_return", 0)
    return {"sales_paise": sales, "returns_paise": returns, "net_paise": sales - returns, "by_mode": by_mode}


def stock_register(conn):
    """Every item with its derived on-hand quantity (from the stock ledger), by name. Read-only."""
    rows = conn.execute(
        """SELECT i.name AS item, COALESCE(i.sku, '') AS sku, i.unit AS unit,
                  CASE i.active WHEN 1 THEN 'yes' ELSE 'no' END AS active,
                  COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0) AS on_hand_milli,
                  i.reorder_milli AS reorder_milli, i.buy_price_paise AS buy_price_paise,
                  i.sell_price_paise AS sell_price_paise
           FROM item i ORDER BY i.name, i.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def party_ledger(conn):
    """Statement for every customer (type customer/both, like parties.list_dues): opening balance, credit
    (udhaar) sales/returns and payments received, with a running balance (positive = owes the shop). The
    last balance of each party equals parties.balance. Suppliers are excluded on purpose: the engine does
    not track payables, so a supplier statement would look settled when it is not. Read-only."""
    out = []
    for p in conn.execute(
            "SELECT * FROM party WHERE type IN ('customer', 'both') ORDER BY name, id").fetchall():
        entries = []
        for r in conn.execute(
                """SELECT b.bill_no AS bill_no, b.kind AS kind, b.finalized_at AS at, b.id AS bid,
                          SUM(pay.amount_paise) AS amount
                   FROM payment pay JOIN bill b ON b.id = pay.bill_id
                   WHERE b.party_id = ? AND b.status = 'final' AND pay.mode = 'credit'
                   GROUP BY b.id ORDER BY b.finalized_at, b.id""", (p["id"],)):
            sale = r["kind"] == "sale"
            entries.append((r["at"], 0, r["bid"], "credit_sale" if sale else "credit_return", r["bill_no"],
                            r["amount"] if sale else 0, 0 if sale else r["amount"]))
        for r in conn.execute(
                "SELECT id, amount_paise, mode, created_at FROM party_payment WHERE party_id = ?", (p["id"],)):
            entries.append((r["created_at"], 1, r["id"], "payment", r["mode"], 0, r["amount_paise"]))
        entries.sort(key=lambda e: (e[0], e[1], e[2]))
        balance = p["opening_balance_paise"]
        base = {"party": p["name"], "phone": p["phone"] or ""}
        out.append({**base, "date": "", "entry": "opening", "ref": "", "debit_paise": 0, "credit_paise": 0,
                    "balance_paise": balance})
        for at, _o, _i, entry, ref, debit, credit in entries:
            balance += debit - credit
            out.append({**base, "date": at[:10], "entry": entry, "ref": ref, "debit_paise": debit,
                        "credit_paise": credit, "balance_paise": balance})
    return out


def write_csv(rows, path, columns):
    """UTF-8 with BOM so Excel opens it correctly; *_paise columns are written as rupees and
    *_milli columns as plain decimal quantities."""
    def head(c):
        for suffix in ("_paise", "_milli"):
            if c.endswith(suffix):
                return c[: -len(suffix)]
        return c

    def cell(row, c):
        if c.endswith("_paise"):
            return money.paise_to_str(row[c])
        if c.endswith("_milli"):
            return money.milli_to_str(row[c])
        return _safe_text(row[c])

    headers = [head(c) for c in columns]
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([cell(row, c) for c in columns])
