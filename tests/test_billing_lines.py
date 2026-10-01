import pytest

from retail.services import billing, items, parties, shop, stock
from retail.services.billing import BillingError, SerialUnavailable


def add_stock(conn, item_id, qty_milli):
    stock.record(conn, item_id, qty_milli, "opening")


def add_phone(conn, item_id, serial):
    unit = stock.add_unit(conn, item_id, serial=serial)
    stock.record(conn, item_id, 1000, "opening", unit_id=unit)
    return unit


def totals(conn, bill_id):
    b = billing.get_bill(conn, bill_id)["bill"]
    return (b["taxable_paise"], b["cgst_paise"], b["sgst_paise"], b["igst_paise"],
            b["round_off_paise"], b["total_paise"])


@pytest.fixture
def soap(shop_conn):  # Rs 118.00 MRP-inclusive, 18% GST
    iid = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    add_stock(shop_conn, iid, 10_000)
    return iid


def test_line_totals_gst_inclusive(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    assert totals(shop_conn, bill_id) == (10000, 900, 900, 0, 0, 11800)


def test_weighed_item_takes_fractional_quantity(shop_conn):
    rice = items.create_item(shop_conn, name="Rice", sell_price_paise=6000, unit="kg", tracking="weighed")
    add_stock(shop_conn, rice, 20_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, rice, 750)
    assert totals(shop_conn, bill_id)[-1] == 4500


def test_total_is_rounded_to_whole_rupee(shop_conn):
    toffee = items.create_item(shop_conn, name="Toffee bag", sell_price_paise=1049)
    add_stock(shop_conn, toffee, 5_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, toffee, 1000)
    assert totals(shop_conn, bill_id)[-2:] == (-49, 1000)


def test_inter_state_customer_gets_igst(shop_conn, soap):
    pune = parties.create_party(shop_conn, name="Pune Traders", state_code="27")
    bill_id = billing.start_bill(shop_conn, party_id=pune)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    assert totals(shop_conn, bill_id) == (10000, 0, 0, 1800, 0, 11800)


def test_set_party_retaxes_existing_lines(shop_conn, soap):
    pune = parties.create_party(shop_conn, name="Pune Traders", state_code="27")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.set_party(shop_conn, bill_id, pune)
    assert totals(shop_conn, bill_id) == (10000, 0, 0, 1800, 0, 11800)


def test_estimate_mode_applies_no_tax(shop_conn):
    shop.setup_shop(shop_conn, name="Small Shop", state_code="36", gst_enabled=False)
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    add_stock(shop_conn, soap, 1_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    assert totals(shop_conn, bill_id) == (11800, 0, 0, 0, 0, 11800)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["gst_mode"] == "estimate"


def test_discount_and_price_override(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000, discount_paise=1800)
    assert totals(shop_conn, bill_id)[-1] == 10000
    billing.add_line(shop_conn, bill_id, soap, 1000, rate_paise=5000)
    assert totals(shop_conn, bill_id)[-1] == 15000
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, 1000, discount_paise=99999)


@pytest.mark.parametrize("qty", [500, 0, -1000, 1500])
def test_non_weighed_item_rejects_fractional_zero_or_negative_quantity(shop_conn, soap, qty):
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, qty)
    assert billing.get_bill(shop_conn, bill_id)["lines"] == []


def test_serial_is_normalised_and_must_exist_in_stock(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, phone, 1000, serial="  imei123 ")
    assert line_id
    with pytest.raises(SerialUnavailable):
        billing.add_line(shop_conn, bill_id, phone, 1000, serial="UNKNOWN")
    with pytest.raises(SerialUnavailable):
        billing.add_line(shop_conn, bill_id, phone, 1000, serial=None)


def test_same_serial_cannot_be_added_twice_to_one_bill(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="IMEI123")
    with pytest.raises(SerialUnavailable):
        billing.add_line(shop_conn, bill_id, phone, 1000, serial="imei123")
    assert len(billing.get_bill(shop_conn, bill_id)["lines"]) == 1


def test_serial_items_sell_one_unit_per_line(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, phone, 2000, serial="IMEI123")


def test_batch_item_auto_picks_earliest_expiry(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    late = stock.add_unit(shop_conn, milk, batch_no="A", expiry="2026-12-01")
    early = stock.add_unit(shop_conn, milk, batch_no="B", expiry="2026-10-01")
    for uid in (late, early):
        stock.record(shop_conn, milk, 5_000, "purchase", unit_id=uid)
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, milk, 2000)
    line = [ln for ln in billing.get_bill(shop_conn, bill_id)["lines"] if ln["id"] == line_id][0]
    assert line["unit_id"] == early


def test_batch_item_without_stock_is_rejected(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, milk, 1000)


def test_block_policy_counts_quantity_already_on_the_bill(shop_conn):
    shop.setup_shop(shop_conn, name="S", state_code="36", oversell_policy="block")
    it = items.create_item(shop_conn, name="Tea", sell_price_paise=100)
    add_stock(shop_conn, it, 2_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, it, 1000)
    billing.add_line(shop_conn, bill_id, it, 1000)
    with pytest.raises(stock.InsufficientStock):
        billing.add_line(shop_conn, bill_id, it, 1000)


def test_warn_policy_allows_selling_below_stock(shop_conn):
    it = items.create_item(shop_conn, name="Tea", sell_price_paise=100)
    bill_id = billing.start_bill(shop_conn)
    assert billing.add_line(shop_conn, bill_id, it, 1000)


def test_remove_line_updates_totals(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    first = billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.remove_line(shop_conn, bill_id, first)
    assert totals(shop_conn, bill_id)[-1] == 11800
    with pytest.raises(BillingError):
        billing.remove_line(shop_conn, bill_id, first)


def test_hold_list_and_cancel(shop_conn, soap):
    a = billing.start_bill(shop_conn)
    b = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, a, soap, 1000)
    assert {r["id"] for r in billing.list_held(shop_conn)} == {a, b}
    billing.cancel_held(shop_conn, b)
    assert [r["id"] for r in billing.list_held(shop_conn)] == [a]
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, b, soap, 1000)
    assert billing.get_bill(shop_conn, a)["bill"]["bill_no"] is None


@pytest.mark.parametrize("kwargs", [
    {"qty_milli": 1000.0}, {"qty_milli": True}, {"qty_milli": "1000"}, {"qty_milli": None},
    {"discount_paise": 1.5}, {"discount_paise": True}, {"discount_paise": None},
    {"rate_paise": 100.0}, {"rate_paise": True}, {"rate_paise": "100"},
    {"unit_id": 1.0}, {"unit_id": True}, {"unit_id": "1"},
])
def test_add_line_rejects_non_int_numeric_arguments(shop_conn, soap, kwargs):
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, **kwargs)
    assert billing.get_bill(shop_conn, bill_id)["lines"] == []
