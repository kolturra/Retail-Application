import time

import pytest

from retail import guard
from retail.services import items


def test_create_item_with_barcodes(shop_conn):
    iid = items.create_item(shop_conn, name="Parle-G 100g", sell_price_paise=1000, gst_rate_bp=500,
                            sku="PARLE100", barcodes=["8901719101015", " 8901719101022 "])
    row = shop_conn.execute("SELECT * FROM item WHERE id=?", (iid,)).fetchone()
    assert row["name"] == "Parle-G 100g" and row["gst_rate_bp"] == 500
    codes = {r["code"] for r in shop_conn.execute("SELECT code FROM item_barcode WHERE item_id=?", (iid,))}
    assert codes == {"8901719101015", "8901719101022"}


def test_resolve_prefers_barcode_then_sku_then_name(shop_conn):
    a = items.create_item(shop_conn, name="Alpha", sell_price_paise=100, barcodes=["111"])
    b = items.create_item(shop_conn, name="Beta soap", sell_price_paise=100, sku="BETA")
    c = items.create_item(shop_conn, name="Gamma soap", sell_price_paise=100)
    assert [r["id"] for r in items.resolve(shop_conn, "111")] == [a]
    assert [r["id"] for r in items.resolve(shop_conn, " BETA ")] == [b]
    assert [r["id"] for r in items.resolve(shop_conn, "soap")] == [b, c]
    assert [r["id"] for r in items.resolve(shop_conn, "GAMMA")] == [c]
    assert items.resolve(shop_conn, "   ") == []
    assert items.resolve(shop_conn, "zzz") == []


def test_resolve_treats_percent_literally(shop_conn):
    items.create_item(shop_conn, name="Alpha", sell_price_paise=100)
    assert items.resolve(shop_conn, "%") == []


def test_resolve_skips_inactive_items(shop_conn):
    iid = items.create_item(shop_conn, name="Old stock", sell_price_paise=100)
    shop_conn.execute("UPDATE item SET active=0 WHERE id=?", (iid,))
    assert items.resolve(shop_conn, "old") == []


@pytest.mark.parametrize("text,expected", [
    ("3*8901719101015", (3000, "8901719101015")),
    ("0.75 * rice", (750, "rice")),
    ("rice", (1000, "rice")),
    ("  rice  ", (1000, "rice")),
    ("12", (1000, "12")),
])
def test_parse_entry(text, expected):
    assert items.parse_entry(text) == expected


def test_duplicate_sku_and_barcode_rejected(shop_conn):
    items.create_item(shop_conn, name="A", sell_price_paise=100, sku="X", barcodes=["1"])
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, name="B", sell_price_paise=100, sku="X")
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, name="C", sell_price_paise=100, barcodes=["1"])
    assert shop_conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 1


@pytest.mark.parametrize("kwargs", [
    {"name": "", "sell_price_paise": 100},
    {"name": "A", "sell_price_paise": -1},
    {"name": "A", "sell_price_paise": 100, "tracking": "magic"},
    {"name": "A", "sell_price_paise": 100, "barcodes": [""]},
])
def test_create_item_validation(shop_conn, kwargs):
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, **kwargs)


def test_create_item_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        items.create_item(shop_conn, name="A", sell_price_paise=100)


def test_name_search_stays_fast_on_a_large_catalogue(shop_conn):
    shop_conn.execute("BEGIN")
    shop_conn.executemany(
        "INSERT INTO item(name, sku, sell_price_paise) VALUES (?,?,?)",
        [(f"Product {i}", f"SKU{i}", 100) for i in range(5000)],
    )
    shop_conn.execute("COMMIT")
    started = time.perf_counter()
    assert len(items.resolve(shop_conn, "product 4999")) == 1
    assert time.perf_counter() - started < 0.25


@pytest.mark.parametrize("kwargs", [
    {"sell_price_paise": 10.5},
    {"sell_price_paise": True},
    {"sell_price_paise": 100, "buy_price_paise": -1},
    {"sell_price_paise": 100, "buy_price_paise": 1.5},
    {"sell_price_paise": 100, "gst_rate_bp": -1},
    {"sell_price_paise": 100, "gst_rate_bp": False},
    {"sell_price_paise": 100, "reorder_milli": -1},
    {"sell_price_paise": 100, "warranty_months": -1},
])
def test_create_item_rejects_bad_numbers(shop_conn, kwargs):
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, name="A", **kwargs)
    assert shop_conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 0


def test_add_barcode_unknown_item(shop_conn):
    with pytest.raises(items.ItemError, match="No such item"):
        items.add_barcode(shop_conn, 999, "123")


def test_add_barcode_duplicate(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=100, barcodes=["1"])
    with pytest.raises(items.ItemError, match="already used"):
        items.add_barcode(shop_conn, a, "1")
    items.add_barcode(shop_conn, a, "2")


def test_non_unique_integrity_error_not_reported_as_duplicate(shop_conn):
    # Validation blocks every non-UNIQUE path via the public API, so provoke the
    # FK failure directly through the private helper.
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        items._insert_barcode(shop_conn, 999, "555")
