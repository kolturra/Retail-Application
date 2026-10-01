"""Append-only stock ledger. Quantity on hand is always derived from movements."""
import sqlite3

from retail import clock
from retail.db import transaction
from retail.guard import writes
from retail.services import audit


class InsufficientStock(ValueError):
    pass


class DuplicateSerial(ValueError):
    pass


def _norm_serial(serial):
    return (serial or "").strip().upper()


def _record(conn, item_id, qty_milli, mtype, ref_type=None, ref_id=None, unit_id=None):
    cur = conn.execute(
        """INSERT INTO stock_movement(item_id, unit_id, qty_milli, type, ref_type, ref_id, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (item_id, unit_id, qty_milli, mtype, ref_type, ref_id, clock.now_iso()),
    )
    return cur.lastrowid


@writes
def record(conn, item_id, qty_milli, mtype, ref_type=None, ref_id=None, unit_id=None):
    with transaction(conn):
        return _record(conn, item_id, qty_milli, mtype, ref_type, ref_id, unit_id)


def on_hand(conn, item_id):
    return conn.execute(
        "SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE item_id = ?", (item_id,)
    ).fetchone()[0]


def unit_on_hand(conn, unit_id):
    return conn.execute(
        "SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE unit_id = ?", (unit_id,)
    ).fetchone()[0]


def _add_unit(conn, item_id, *, serial=None, batch_no=None, expiry=None):
    serial = _norm_serial(serial) or None
    try:
        cur = conn.execute(
            "INSERT INTO stock_unit(item_id, serial, batch_no, expiry) VALUES (?,?,?,?)",
            (item_id, serial, batch_no, expiry),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc) or "stock_unit" not in str(exc):
            raise
        raise DuplicateSerial(f"Serial {serial!r} already exists for this item") from exc
    return cur.lastrowid


@writes
def add_unit(conn, item_id, *, serial=None, batch_no=None, expiry=None):
    with transaction(conn):
        return _add_unit(conn, item_id, serial=serial, batch_no=batch_no, expiry=expiry)


def find_serial(conn, item_id, serial):
    return conn.execute(
        "SELECT * FROM stock_unit WHERE item_id = ? AND serial = ?", (item_id, _norm_serial(serial))
    ).fetchone()


def find_batch(conn, item_id, batch_no):
    row = conn.execute(
        "SELECT id FROM stock_unit WHERE item_id = ? AND serial IS NULL AND batch_no = ?",
        (item_id, batch_no),
    ).fetchone()
    return row["id"] if row else None


def pick_batch(conn, item_id):
    """Earliest-expiry batch that still has stock (no expiry sorts last)."""
    row = conn.execute(
        """SELECT u.id FROM stock_unit u
           WHERE u.item_id = ? AND u.serial IS NULL AND u.batch_no IS NOT NULL
             AND (SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE unit_id = u.id) > 0
           ORDER BY (u.expiry IS NULL), u.expiry, u.id LIMIT 1""",
        (item_id,),
    ).fetchone()
    return row["id"] if row else None


def batches_in_expiry_order(conn, item_id):
    """Unit ids of batches with positive stock, earliest expiry first (no expiry last, then id)."""
    rows = conn.execute(
        """SELECT u.id FROM stock_unit u
           WHERE u.item_id = ? AND u.serial IS NULL AND u.batch_no IS NOT NULL
             AND (SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE unit_id = u.id) > 0
           ORDER BY (u.expiry IS NULL), u.expiry, u.id""",
        (item_id,),
    ).fetchall()
    return [r["id"] for r in rows]


def check_available(conn, item_id, qty_milli, policy):
    """Return 'ok' or 'warn'; raise InsufficientStock when the policy is 'block'."""
    have = on_hand(conn, item_id)
    if have >= qty_milli:
        return "ok"
    if policy == "block":
        raise InsufficientStock(f"Only {have / 1000:g} in stock")
    return "warn" if policy == "warn" else "ok"


def low_stock(conn):
    return conn.execute(
        """SELECT i.*, COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0) AS on_hand_milli
           FROM item i
           WHERE i.active = 1 AND i.reorder_milli > 0
             AND COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0) <= i.reorder_milli
           ORDER BY i.name"""
    ).fetchall()


class StockError(ValueError):
    pass


@writes
def adjust_stock(conn, item_id, qty_milli, reason):
    """Audited manual correction (damage, count difference) for counted/weighed items."""
    if type(qty_milli) is not int or qty_milli == 0:
        raise StockError("An adjustment must be a non-zero whole number of milli-units")
    reason = (reason or "").strip() if isinstance(reason, str) or reason is None else ""
    if not reason:
        raise StockError("A reason is required")
    with transaction(conn):
        item = conn.execute("SELECT tracking FROM item WHERE id = ? AND active = 1", (item_id,)).fetchone()
        if item is None:
            raise StockError("No such item")
        if item["tracking"] in ("serial", "batch"):
            raise StockError("Serial and batch stock is changed through purchases and returns")
        if on_hand(conn, item_id) + qty_milli < 0:
            raise InsufficientStock("The adjustment would make stock negative")
        movement_id = _record(conn, item_id, qty_milli, "adjustment", "adjustment", None)
        audit.log(conn, "adjust", "item", item_id, f"{qty_milli}: {reason}")
    return movement_id
