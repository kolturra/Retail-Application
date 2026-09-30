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
