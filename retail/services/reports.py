"""Read-only reports. Deliberately not guarded, so they keep working after license expiry."""
import csv
import re
from datetime import date

from retail import money

SALES_COLUMNS = ["bill_no", "bill_date", "kind", "party", "gstin", "taxable_paise", "cgst_paise",
                 "sgst_paise", "igst_paise", "round_off_paise", "total_paise"]

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_FORMULA_PREFIXES = ("=", "+", "-", "@")


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


def _safe_text(value):
    """Defuse CSV formula injection: text starting with = + - @ gets a leading single quote."""
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


def write_csv(rows, path, columns):
    """UTF-8 with BOM so Excel opens it correctly; *_paise columns are written as rupees."""
    headers = [c[: -len("_paise")] if c.endswith("_paise") else c for c in columns]
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                money.paise_to_str(row[c]) if c.endswith("_paise") else _safe_text(row[c]) for c in columns
            ])
