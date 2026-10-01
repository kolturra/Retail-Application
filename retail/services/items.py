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
        if "item_barcode.code" in str(exc):
            raise ItemError(f"Barcode {code!r} is already used by another item") from exc
        raise


@writes
def create_item(conn, *, name, sell_price_paise, gst_rate_bp=0, unit="pcs", tracking="none",
                sku=None, hsn=None, buy_price_paise=0, reorder_milli=0, warranty_months=0,
                barcodes=()):
    name = (name or "").strip()
    if not name:
        raise ItemError("Item name is required")
    if tracking not in TRACKING:
        raise ItemError(f"tracking must be one of {TRACKING}")
    for label, value in (("sell_price_paise", sell_price_paise), ("buy_price_paise", buy_price_paise),
                         ("gst_rate_bp", gst_rate_bp), ("reorder_milli", reorder_milli),
                         ("warranty_months", warranty_months)):
        if type(value) is not int or value < 0:
            raise ItemError(f"{label} must be a non-negative whole number")
    # A bare string would otherwise be iterated character by character into one-digit barcodes.
    if type(barcodes) not in (list, tuple, set) or not all(
            type(code) is str and code.strip() for code in barcodes):
        raise ItemError("barcodes must be a list of non-empty text values")
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
            if "item.sku" in str(exc):
                raise ItemError(f"SKU {sku!r} is already used by another item") from exc
            raise
        item_id = cur.lastrowid
        for code in barcodes:
            _insert_barcode(conn, item_id, code)
        audit.log(conn, "create", "item", item_id, name)
    return item_id


@writes
def add_barcode(conn, item_id, code):
    with transaction(conn):
        if conn.execute("SELECT 1 FROM item WHERE id = ?", (item_id,)).fetchone() is None:
            raise ItemError("No such item")
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


_UPDATABLE = ("name", "sku", "hsn", "gst_rate_bp", "unit", "sell_price_paise", "buy_price_paise",
              "reorder_milli", "warranty_months", "tracking")
_INT_FIELDS = ("gst_rate_bp", "sell_price_paise", "buy_price_paise", "reorder_milli", "warranty_months")


def get_item(conn, item_id):
    return conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()


def item_barcodes(conn, item_id):
    return [r["code"] for r in conn.execute(
        "SELECT code FROM item_barcode WHERE item_id = ? ORDER BY code", (item_id,))]


def list_items(conn, search="", *, include_inactive=False, limit=500):
    search = (search or "").strip()
    return conn.execute(
        """SELECT i.*, COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0)
                  AS on_hand_milli
           FROM item i
           WHERE (? = 1 OR i.active = 1)
             AND (? = '' OR instr(lower(i.name), lower(?)) > 0 OR i.sku = ?
                  OR EXISTS (SELECT 1 FROM item_barcode b WHERE b.item_id = i.id AND b.code = ?))
           ORDER BY i.name LIMIT ?""",
        (int(include_inactive), search, search, search, search, limit),
    ).fetchall()


@writes
def update_item(conn, item_id, **fields):
    unknown = sorted(set(fields) - set(_UPDATABLE))
    if unknown:
        raise ItemError(f"Cannot change {unknown}")
    if not fields:
        raise ItemError("Nothing to change")
    old = get_item(conn, item_id)
    if old is None:
        raise ItemError("No such item")
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip()
        if not fields["name"]:
            raise ItemError("Item name is required")
    for field in _INT_FIELDS:
        if field in fields and (type(fields[field]) is not int or fields[field] < 0):
            raise ItemError(f"{field} must be a non-negative whole number")
    if "sku" in fields:
        fields["sku"] = (fields["sku"] or "").strip() or None
    if "tracking" in fields:
        if fields["tracking"] not in TRACKING:
            raise ItemError(f"tracking must be one of {TRACKING}")
        if fields["tracking"] != old["tracking"] and conn.execute(
                "SELECT 1 FROM stock_movement WHERE item_id = ? LIMIT 1", (item_id,)).fetchone():
            raise ItemError("Tracking cannot change once the item has stock history")
    with transaction(conn):
        try:
            # column names come from the _UPDATABLE whitelist above, values are bound parameters
            conn.execute(f"UPDATE item SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                         (*fields.values(), item_id))
        except sqlite3.IntegrityError as exc:
            if "item.sku" in str(exc):
                raise ItemError(f"SKU {fields['sku']!r} is already used by another item") from exc
            raise
        audit.log(conn, "update", "item", item_id, ", ".join(sorted(fields)))


@writes
def set_item_active(conn, item_id, active):
    if type(active) is not bool:
        raise ItemError("active must be True or False")
    with transaction(conn):
        if conn.execute("UPDATE item SET active = ? WHERE id = ?", (int(active), item_id)).rowcount == 0:
            raise ItemError("No such item")
        audit.log(conn, "activate" if active else "deactivate", "item", item_id)


@writes
def set_barcodes(conn, item_id, codes):
    if isinstance(codes, str) or not isinstance(codes, (list, tuple, set)):
        raise ItemError("barcodes must be a list of codes")
    cleaned = list(dict.fromkeys(c.strip() for c in codes if isinstance(c, str) and c.strip()))
    with transaction(conn):
        if get_item(conn, item_id) is None:
            raise ItemError("No such item")
        conn.execute("DELETE FROM item_barcode WHERE item_id = ?", (item_id,))
        for code in cleaned:
            _insert_barcode(conn, item_id, code)
        audit.log(conn, "barcodes", "item", item_id, ",".join(cleaned))
