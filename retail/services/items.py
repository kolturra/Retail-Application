import re
import sqlite3

from retail import money
from retail.db import transaction
from retail.guard import writes
from retail.services import audit

TRACKING = ("none", "weighed", "batch", "serial")
_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\*\s*(.+?)\s*$")


class ItemError(ValueError):
    pass


def _insert_barcode(conn, item_id, code):
    code = (code or "").strip()
    if not code:
        raise ItemError("Barcode cannot be empty")
    try:
        conn.execute("INSERT INTO item_barcode(code, item_id) VALUES (?,?)", (code, item_id))
    except sqlite3.IntegrityError as exc:
        raise ItemError(f"Barcode {code!r} is already used by another item") from exc


@writes
def create_item(conn, *, name, sell_price_paise, gst_rate_bp=0, unit="pcs", tracking="none",
                sku=None, hsn=None, buy_price_paise=0, reorder_milli=0, warranty_months=0,
                barcodes=()):
    name = (name or "").strip()
    if not name:
        raise ItemError("Item name is required")
    if sell_price_paise < 0:
        raise ItemError("Selling price cannot be negative")
    if tracking not in TRACKING:
        raise ItemError(f"tracking must be one of {TRACKING}")
    sku = (sku or "").strip() or None
    with transaction(conn):
        try:
            cur = conn.execute(
                """INSERT INTO item(name, sku, hsn, gst_rate_bp, unit, sell_price_paise,
                       buy_price_paise, reorder_milli, warranty_months, tracking)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (name, sku, hsn, gst_rate_bp, unit, sell_price_paise, buy_price_paise,
                 reorder_milli, warranty_months, tracking),
            )
        except sqlite3.IntegrityError as exc:
            raise ItemError(f"SKU {sku!r} is already used by another item") from exc
        item_id = cur.lastrowid
        for code in barcodes:
            _insert_barcode(conn, item_id, code)
        audit.log(conn, "create", "item", item_id, name)
    return item_id


@writes
def add_barcode(conn, item_id, code):
    with transaction(conn):
        _insert_barcode(conn, item_id, code)


def resolve(conn, text, limit=20):
    """Barcode (exact) -> SKU (exact) -> name (substring, case-insensitive)."""
    text = (text or "").strip()
    if not text:
        return []
    by_barcode = conn.execute(
        "SELECT i.* FROM item i JOIN item_barcode b ON b.item_id = i.id WHERE b.code = ? AND i.active = 1",
        (text,),
    ).fetchall()
    if by_barcode:
        return by_barcode
    by_sku = conn.execute("SELECT * FROM item WHERE sku = ? AND active = 1", (text,)).fetchall()
    if by_sku:
        return by_sku
    return conn.execute(
        "SELECT * FROM item WHERE active = 1 AND instr(lower(name), lower(?)) > 0 ORDER BY name LIMIT ?",
        (text, limit),
    ).fetchall()


def parse_entry(text):
    """'3*abc' -> (3000, 'abc'); anything else -> (1000, stripped text)."""
    match = _PREFIX.match(text or "")
    if match:
        return money.qty_to_milli(match.group(1)), match.group(2)
    return 1000, (text or "").strip()
