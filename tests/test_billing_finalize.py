from datetime import date

import pytest

from retail import guard
from retail.services import billing, items, parties, shop, stock
from retail.services.billing import BillingError, SerialUnavailable


def add_stock(conn, item_id, qty_milli):
    stock.record(conn, item_id, qty_milli, "opening")


def add_phone(conn, item_id, serial):
    unit = stock.add_unit(conn, item_id, serial=serial)
    stock.record(conn, item_id, 1000, "opening", unit_id=unit)
    return unit


@pytest.fixture
def soap(shop_conn):
    iid = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    add_stock(shop_conn, iid, 10_000)
    return iid


def held_soap_bill(conn, soap, qty=1000, party_id=None):
    bill_id = billing.start_bill(conn, party_id=party_id)
    billing.add_line(conn, bill_id, soap, qty)
    return bill_id


def test_finalize_numbers_bills_and_moves_stock(shop_conn, soap):
    a = held_soap_bill(shop_conn, soap, 2000)
    assert billing.finalize(shop_conn, a, [("cash", 23600)]) == "S000001"
    b = held_soap_bill(shop_conn, soap)
    assert billing.finalize(shop_conn, b, [("upi", 5000), ("cash", 6800)]) == "S000002"
    assert stock.on_hand(shop_conn, soap) == 7_000
    bill = billing.get_bill(shop_conn, a)["bill"]
    assert bill["status"] == "final" and bill["bill_no"] == "S000001" and bill["finalized_at"]
    modes = [r["mode"] for r in shop_conn.execute("SELECT mode FROM payment WHERE bill_id = ? ORDER BY id", (b,))]
    assert modes == ["upi", "cash"]


@pytest.mark.parametrize("payments", [
    [("cash", 100)],                 # too little
    [("cash", 99999)],               # too much
    [],                              # nothing paid on a non-zero bill
    [("bitcoin", 11800)],            # unknown mode
    [("cash", 11800), ("cash", 0)],  # zero-value payment row
    [("cash", True)],                # bool amount
    [("cash", 11800.0)],             # float amount
    [("cash", "11800")],             # str amount
    [("cash", None)],                # None amount
])
def test_finalize_rejects_bad_payments_and_changes_nothing(shop_conn, soap, payments):
    bill_id = held_soap_bill(shop_conn, soap)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, payments)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "held"
    assert stock.on_hand(shop_conn, soap) == 10_000
    assert shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == 0


@pytest.mark.parametrize("today", ["2026-01-31", 20260131, 1.5, True])
def test_finalize_rejects_non_date_today(shop_conn, soap, today):
    bill_id = held_soap_bill(shop_conn, soap)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, [("cash", 11800)], today=today)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "held"


def test_finalize_rejects_empty_bill(shop_conn):
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, [])
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "held"


def test_credit_sale_needs_a_customer_and_raises_balance(shop_conn, soap):
    anon = held_soap_bill(shop_conn, soap)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, anon, [("credit", 11800)])
    ravi = parties.create_party(shop_conn, name="Ravi")
    bill_id = held_soap_bill(shop_conn, soap, party_id=ravi)
    billing.finalize(shop_conn, bill_id, [("credit", 11800)])
    assert parties.balance(shop_conn, ravi) == 11800
    parties.receive_payment(shop_conn, ravi, 5000)
    assert parties.balance(shop_conn, ravi) == 6800


def test_finalized_bill_is_immutable(shop_conn, soap):
    bill_id = held_soap_bill(shop_conn, soap)
    line_id = billing.get_bill(shop_conn, bill_id)["lines"][0]["id"]
    billing.finalize(shop_conn, bill_id, [("cash", 11800)])
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, 1000)
    with pytest.raises(BillingError):
        billing.remove_line(shop_conn, bill_id, line_id)
    with pytest.raises(BillingError):
        billing.set_party(shop_conn, bill_id, None)
    with pytest.raises(BillingError):
        billing.cancel_held(shop_conn, bill_id)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, [("cash", 11800)])


def test_serial_sale_marks_unit_sold_and_creates_warranty(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial",
                              warranty_months=12)
    unit = add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="imei123")
    billing.finalize(shop_conn, bill_id, [("cash", 1000000)], today=date(2026, 1, 31))
    assert stock.on_hand(shop_conn, phone) == 0
    assert shop_conn.execute("SELECT status FROM stock_unit WHERE id=?", (unit,)).fetchone()[0] == "sold"
    w = shop_conn.execute("SELECT start_date, end_date FROM warranty WHERE unit_id=?", (unit,)).fetchone()
    assert (w["start_date"], w["end_date"]) == ("2026-01-31", "2027-01-31")


def test_two_bills_racing_for_one_serial_second_fails_without_partial_writes(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    unit = add_phone(shop_conn, phone, "IMEI123")
    first = billing.start_bill(shop_conn)
    second = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, first, phone, 1000, serial="IMEI123")
    billing.add_line(shop_conn, second, phone, 1000, serial="IMEI123")
    billing.finalize(shop_conn, first, [("cash", 1000000)])
    movements_before = shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0]
    with pytest.raises(SerialUnavailable):
        billing.finalize(shop_conn, second, [("cash", 1000000)])
    assert billing.get_bill(shop_conn, second)["bill"]["status"] == "held"
    assert billing.get_bill(shop_conn, second)["bill"]["bill_no"] is None
    assert shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0] == movements_before
    assert shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == 1
    assert unit


def test_block_policy_is_rechecked_at_finalize(shop_conn):
    shop.setup_shop(shop_conn, name="S", state_code="36", oversell_policy="block")
    it = items.create_item(shop_conn, name="Tea", sell_price_paise=100)
    add_stock(shop_conn, it, 1_000)
    a = held_soap_bill(shop_conn, it)
    b = held_soap_bill(shop_conn, it)
    billing.finalize(shop_conn, a, [("cash", 100)])
    with pytest.raises(stock.InsufficientStock):
        billing.finalize(shop_conn, b, [("cash", 100)])
    assert stock.on_hand(shop_conn, it) == 0


def test_block_policy_rechecks_each_batch_at_finalize(shop_conn):
    shop.setup_shop(shop_conn, name="S", state_code="36", oversell_policy="block")
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    early = stock.add_unit(shop_conn, milk, batch_no="A", expiry="2026-12-01")
    late = stock.add_unit(shop_conn, milk, batch_no="B", expiry="2027-06-01")
    stock.record(shop_conn, milk, 1000, "opening", unit_id=early)
    stock.record(shop_conn, milk, 5000, "opening", unit_id=late)
    a = held_soap_bill(shop_conn, milk)
    b = held_soap_bill(shop_conn, milk)
    assert {ln["unit_id"] for ln in billing.get_bill(shop_conn, b)["lines"]} == {early}
    billing.finalize(shop_conn, a, [("cash", 100)])
    movements = shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0]
    payments = shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0]
    with pytest.raises(stock.InsufficientStock):
        billing.finalize(shop_conn, b, [("cash", 100)])
    assert billing.get_bill(shop_conn, b)["bill"]["status"] == "held"
    assert billing.get_bill(shop_conn, b)["bill"]["bill_no"] is None
    assert shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0] == movements
    assert shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == payments
    assert stock.unit_on_hand(shop_conn, early) == 0 and stock.unit_on_hand(shop_conn, late) == 5000


def test_free_bill_can_be_finalized_without_payments(shop_conn):
    gift = items.create_item(shop_conn, name="Free sample", sell_price_paise=0)
    add_stock(shop_conn, gift, 1_000)
    bill_id = held_soap_bill(shop_conn, gift)
    assert billing.finalize(shop_conn, bill_id, []) == "S000001"


def test_start_bill_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        billing.start_bill(shop_conn)
