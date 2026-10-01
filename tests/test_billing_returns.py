import pytest

from retail.services import billing, items, parties, stock
from retail.services.billing import BillingError


def sold_soaps(conn, qty=3000, party_id=None):
    soap = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(conn, soap, 10_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    line_id = billing.add_line(conn, bill_id, soap, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, [("cash", total)])
    return soap, bill_id, line_id


def test_full_return_restocks_and_refunds(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    assert stock.on_hand(shop_conn, soap) == 7_000
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 3000)])
    r = billing.get_bill(shop_conn, ret)["bill"]
    assert r["kind"] == "sale_return" and r["status"] == "final" and r["bill_no"] == "R000001"
    assert r["ref_bill_id"] == bill_id and r["total_paise"] == 35400
    assert stock.on_hand(shop_conn, soap) == 10_000
    refund = shop_conn.execute("SELECT mode, amount_paise FROM payment WHERE bill_id = ?", (ret,)).fetchone()
    assert (refund["mode"], refund["amount_paise"]) == ("cash", 35400)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"] == 35400  # original untouched


def test_partial_return_refunds_proportional_gst(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=2000)
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    r = billing.get_bill(shop_conn, ret)["bill"]
    assert (r["taxable_paise"], r["cgst_paise"], r["sgst_paise"], r["total_paise"]) == (10000, 900, 900, 11800)


def test_cannot_return_more_than_sold_even_across_returns(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=3000)
    billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    last = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert billing.get_bill(shop_conn, last)["bill"]["total_paise"] == 11800  # no rounding drift
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert stock.on_hand(shop_conn, soap) == 10_000


def test_failed_return_leaves_no_trace(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=1000)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 5000)])
    assert shop_conn.execute("SELECT COUNT(*) FROM bill WHERE kind='sale_return'").fetchone()[0] == 0
    assert stock.on_hand(shop_conn, soap) == 9_000


@pytest.mark.parametrize("returns", [[], [(99999, 1000)]])
def test_return_input_validation(shop_conn, returns):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, returns)


def test_same_line_listed_twice_in_one_return_is_rejected(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=2000)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 1000), (line_id, 1000)])


def test_zero_or_negative_return_quantity_is_rejected(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    for qty in (0, -1000):
        with pytest.raises(BillingError):
            billing.create_return(shop_conn, bill_id, [(line_id, qty)])


def test_only_final_sale_bills_can_be_returned(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    ret_line = billing.get_bill(shop_conn, ret)["lines"][0]["id"]
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, ret, [(ret_line, 1000)])
    held = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, held, soap, 1000)
    held_line = billing.get_bill(shop_conn, held)["lines"][0]["id"]
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, held, [(held_line, 1000)])


def test_credit_refund_reduces_udhaar_and_needs_a_customer(shop_conn):
    ravi = parties.create_party(shop_conn, name="Ravi")
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=11800)
    stock.record(shop_conn, soap, 10_000, "opening")
    bill_id = billing.start_bill(shop_conn, party_id=ravi)
    line_id = billing.add_line(shop_conn, bill_id, soap, 2000)
    billing.finalize(shop_conn, bill_id, [("credit", 23600)])
    assert parties.balance(shop_conn, ravi) == 23600
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)], refund_mode="credit")
    assert parties.balance(shop_conn, ravi) == 11800
    anon, anon_bill, anon_line = sold_soaps(shop_conn)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, anon_bill, [(anon_line, 1000)], refund_mode="credit")
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, anon_bill, [(anon_line, 1000)], refund_mode="emi")


def test_serial_return_restocks_unit_clears_warranty_and_allows_resale(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial",
                              warranty_months=12)
    unit = stock.add_unit(shop_conn, phone, serial="IMEI123")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, phone, 1000, serial="IMEI123")
    billing.finalize(shop_conn, bill_id, [("cash", 1000000)])
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert stock.on_hand(shop_conn, phone) == 1000
    assert shop_conn.execute("SELECT status FROM stock_unit WHERE id=?", (unit,)).fetchone()[0] == "in_stock"
    assert shop_conn.execute("SELECT COUNT(*) FROM warranty WHERE unit_id=?", (unit,)).fetchone()[0] == 0
    again = billing.start_bill(shop_conn)
    assert billing.add_line(shop_conn, again, phone, 1000, serial="IMEI123")


@pytest.mark.parametrize("bad", [True, 1000.0, "1000", None, (1, 2, 3), 5])
def test_return_entries_must_be_pairs_of_plain_ints(shop_conn, bad):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    entries = [bad] if (isinstance(bad, tuple) or bad == 5) else [(line_id, bad)]
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, entries)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(True, 1000)])
    assert shop_conn.execute("SELECT COUNT(*) FROM bill WHERE kind='sale_return'").fetchone()[0] == 0
