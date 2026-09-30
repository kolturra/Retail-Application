import sqlite3

import pytest

from retail.services import audit

EXPECTED = {
    "shop", "counter", "item", "item_barcode", "stock_unit", "stock_movement", "party",
    "party_payment", "bill", "bill_line", "payment", "purchase", "purchase_line",
    "warranty", "audit_log", "staff", "expense",
}


def test_schema_has_all_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED <= names


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO item_barcode(code, item_id) VALUES ('1', 999)")


def test_audit_log_writes_a_row(conn):
    audit.log(conn, "create", "item", 7, "Soap")
    row = conn.execute("SELECT actor, action, entity, entity_id, detail FROM audit_log").fetchone()
    assert tuple(row) == ("owner", "create", "item", 7, "Soap")


def _item(conn):
    conn.execute("INSERT INTO item(id, name) VALUES (1, 'Soap')")


def _bill(conn, status):
    conn.execute(
        "INSERT INTO bill(id, kind, status, gst_mode, created_at) VALUES (1, 'sale', 'held', 'gst', 't')",
    )
    conn.execute(
        "INSERT INTO bill_line(id, bill_id, item_id, qty_milli, rate_paise, amount_paise) "
        "VALUES (1, 1, 1, 1000, 100, 100)"
    )
    if status == "final":
        conn.execute("UPDATE bill SET status = 'final' WHERE id = 1")


@pytest.mark.parametrize("sql", ["UPDATE stock_movement SET qty_milli = 5", "DELETE FROM stock_movement"])
def test_stock_movement_is_append_only(conn, sql):
    _item(conn)
    conn.execute("INSERT INTO stock_movement(item_id, qty_milli, type, created_at) VALUES (1, 1000, 'opening', 't')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


@pytest.mark.parametrize("sql", ["UPDATE audit_log SET detail = 'x'", "DELETE FROM audit_log"])
def test_audit_log_is_append_only(conn, sql):
    audit.log(conn, "create", "item", 1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


@pytest.mark.parametrize("sql", [
    "UPDATE bill SET total_paise = 1",
    "DELETE FROM bill",
    "UPDATE bill_line SET qty_milli = 2000",
    "DELETE FROM bill_line",
    "INSERT INTO bill_line(bill_id, item_id, qty_milli, rate_paise, amount_paise) VALUES (1, 1, 1000, 1, 1)",
])
def test_final_bill_and_lines_are_immutable(conn, sql):
    _item(conn)
    _bill(conn, "final")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_held_bill_and_lines_stay_editable(conn):
    _item(conn)
    _bill(conn, "held")
    conn.execute("INSERT INTO bill_line(bill_id, item_id, qty_milli, rate_paise, amount_paise) VALUES (1, 1, 1000, 1, 1)")
    conn.execute("UPDATE bill_line SET qty_milli = 2000 WHERE id = 1")
    conn.execute("DELETE FROM bill_line WHERE id = 1")
    conn.execute("UPDATE bill SET total_paise = 50 WHERE id = 1")
    conn.execute("UPDATE bill SET status = 'final' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE bill SET total_paise = 1 WHERE id = 1")


def test_held_bill_can_be_deleted(conn):
    _item(conn)
    _bill(conn, "held")
    conn.execute("DELETE FROM bill_line WHERE bill_id = 1")
    conn.execute("DELETE FROM bill WHERE id = 1")
