import pytest

from retail.services import items, stock


@pytest.fixture
def rice(shop_conn):
    return items.create_item(shop_conn, name="Rice", sell_price_paise=6000, unit="kg", tracking="weighed")


def test_record_and_on_hand(shop_conn, rice):
    other = items.create_item(shop_conn, name="Dal", sell_price_paise=100)
    stock.record(shop_conn, rice, 10_000, "opening")
    stock.record(shop_conn, rice, -2_500, "sale", "bill", 1)
    stock.record(shop_conn, other, 5_000, "opening")
    assert stock.on_hand(shop_conn, rice) == 7_500
    assert stock.on_hand(shop_conn, other) == 5_000


def test_record_rejects_zero_and_unknown_type(shop_conn, rice):
    with pytest.raises(Exception):
        stock.record(shop_conn, rice, 0, "opening")
    with pytest.raises(Exception):
        stock.record(shop_conn, rice, 1000, "gift")
    assert stock.on_hand(shop_conn, rice) == 0


def test_serial_units_are_normalised_and_unique(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    uid = stock.add_unit(shop_conn, phone, serial="  ab123 ")
    assert stock.find_serial(shop_conn, phone, "AB123")["id"] == uid
    assert stock.find_serial(shop_conn, phone, " ab123 ")["id"] == uid
    assert stock.find_serial(shop_conn, phone, "nope") is None
    with pytest.raises(stock.DuplicateSerial):
        stock.add_unit(shop_conn, phone, serial="AB123")


def test_pick_batch_chooses_earliest_expiry_with_stock(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    late = stock.add_unit(shop_conn, milk, batch_no="A", expiry="2026-12-01")
    early = stock.add_unit(shop_conn, milk, batch_no="B", expiry="2026-10-01")
    empty = stock.add_unit(shop_conn, milk, batch_no="C", expiry="2026-09-01")
    for uid in (late, early):
        stock.record(shop_conn, milk, 5_000, "purchase", unit_id=uid)
    stock.record(shop_conn, milk, 1_000, "purchase", unit_id=empty)
    stock.record(shop_conn, milk, -1_000, "sale", unit_id=empty)
    assert stock.unit_on_hand(shop_conn, early) == 5_000
    assert stock.pick_batch(shop_conn, milk) == early
    assert stock.find_batch(shop_conn, milk, "A") == late
    assert stock.find_batch(shop_conn, milk, "Z") is None


def test_pick_batch_none_when_nothing_in_stock(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    assert stock.pick_batch(shop_conn, milk) is None


def test_check_available_policies(shop_conn, rice):
    stock.record(shop_conn, rice, 1_000, "opening")
    assert stock.check_available(shop_conn, rice, 1_000, "block") == "ok"
    assert stock.check_available(shop_conn, rice, 2_000, "warn") == "warn"
    assert stock.check_available(shop_conn, rice, 2_000, "allow") == "ok"
    with pytest.raises(stock.InsufficientStock):
        stock.check_available(shop_conn, rice, 2_000, "block")


def test_low_stock_lists_items_at_or_below_reorder_level(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=100, reorder_milli=5_000)
    b = items.create_item(shop_conn, name="B", sell_price_paise=100, reorder_milli=5_000)
    items.create_item(shop_conn, name="C", sell_price_paise=100)  # no reorder level
    stock.record(shop_conn, a, 5_000, "opening")
    stock.record(shop_conn, b, 6_000, "opening")
    assert [r["name"] for r in stock.low_stock(shop_conn)] == ["A"]
