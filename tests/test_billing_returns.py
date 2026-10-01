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





@pytest.mark.parametrize("make", [
    pytest.param(lambda lid: [(lid, True)], id="bool-qty"),
    pytest.param(lambda lid: [(lid, 1000.0)], id="float-qty"),
    pytest.param(lambda lid: [(lid, "1000")], id="str-qty"),
    pytest.param(lambda lid: [(lid, None)], id="none-qty"),
    pytest.param(lambda lid: [(True, 1000)], id="bool-line-id"),
    pytest.param(lambda lid: [(float(lid), 1000)], id="float-line-id"),
    pytest.param(lambda lid: [(lid, 1000, 1)], id="triple"),
    pytest.param(lambda lid: [lid], id="bare-int"),
    pytest.param(lambda lid: [[lid, 1000]], id="list-pair"),
])
def test_return_entries_must_be_pairs_of_plain_ints(shop_conn, make):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, make(line_id))
    assert shop_conn.execute("SELECT COUNT(*) FROM bill WHERE kind='sale_return'").fetchone()[0] == 0


def _odd_bill(conn, qty, price, gst_bp=0):
    item = items.create_item(conn, name="Odd", sell_price_paise=price, gst_rate_bp=gst_bp)
    stock.record(conn, item, 10_000, "opening")
    bill_id = billing.start_bill(conn)
    line_id = billing.add_line(conn, bill_id, item, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, [("cash", total)])
    return item, bill_id, line_id, total


def _refunds(conn, bill_id):
    return conn.execute(
        """SELECT COALESCE(SUM(p.amount_paise), 0) FROM payment p JOIN bill b ON b.id = p.bill_id
           WHERE b.ref_bill_id = ? AND b.kind = 'sale_return'""", (bill_id,)).fetchone()[0]


@pytest.mark.parametrize("gst_bp", [0, 500])
def test_three_unit_returns_refund_exactly_the_original_total(shop_conn, gst_bp):
    item, bill_id, line_id, total = _odd_bill(shop_conn, 3000, 10033, gst_bp)
    for _ in range(3):
        billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert _refunds(shop_conn, bill_id) == total


def test_single_full_return_refunds_original_total(shop_conn):
    item, bill_id, line_id, total = _odd_bill(shop_conn, 3000, 10033, 500)
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 3000)])
    assert billing.get_bill(shop_conn, ret)["bill"]["total_paise"] == total
    assert _refunds(shop_conn, bill_id) == total


def test_full_return_in_two_when_original_has_round_off(shop_conn):
    item, bill_id, line_id, total = _odd_bill(shop_conn, 3000, 10033)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["round_off_paise"] != 0
    assert total == 30100
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    last = billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    got = billing.get_bill(shop_conn, last)
    lines_total = sum(l["total_paise"] for l in got["lines"])
    assert got["bill"]["round_off_paise"] == got["bill"]["total_paise"] - lines_total
    assert _refunds(shop_conn, bill_id) == total


def test_serial_items_must_be_returned_whole(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    unit = stock.add_unit(shop_conn, phone, serial="IMEI9")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, phone, 1000, serial="IMEI9")
    billing.finalize(shop_conn, bill_id, [("cash", 1000000)])
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 500)])
    assert shop_conn.execute("SELECT COUNT(*) FROM bill WHERE kind='sale_return'").fetchone()[0] == 0
    assert stock.on_hand(shop_conn, phone) == 0
    assert shop_conn.execute("SELECT status FROM stock_unit WHERE id=?", (unit,)).fetchone()[0] == "sold"


def test_failed_return_does_not_burn_the_r_number(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=1000)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 5000)])
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert billing.get_bill(shop_conn, ret)["bill"]["bill_no"] == "R000001"


def test_second_invalid_line_rolls_back_everything(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=3000)
    pen = items.create_item(shop_conn, name="Pen", sell_price_paise=1000)
    stock.record(shop_conn, pen, 5000, "opening")
    b2 = billing.start_bill(shop_conn)
    l2 = billing.add_line(shop_conn, b2, pen, 1000)
    billing.finalize(shop_conn, b2, [("cash", 1000)])
    movements = shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0]
    payments = shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0]
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 1000), (l2, 1000)])
    assert shop_conn.execute("SELECT COUNT(*) FROM bill WHERE kind='sale_return'").fetchone()[0] == 0
    assert shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0] == movements
    assert shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == payments
    assert stock.on_hand(shop_conn, soap) == 7_000


def test_batch_line_returns_to_the_same_batch(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=10000, tracking="batch")
    batch = stock.add_unit(shop_conn, milk, batch_no="B1", expiry="2026-12-01")
    stock.record(shop_conn, milk, 5000, "opening", unit_id=batch)
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, milk, 2000)
    billing.finalize(shop_conn, bill_id, [("cash", 20000)])
    assert stock.unit_on_hand(shop_conn, batch) == 3000
    billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    assert stock.unit_on_hand(shop_conn, batch) == 5000


def test_original_bill_lines_and_payments_are_unchanged_by_a_return(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=3000)

    def snap():
        lines = [tuple(r) for r in shop_conn.execute(
            "SELECT * FROM bill_line WHERE bill_id=? ORDER BY id", (bill_id,))]
        pays = [tuple(r) for r in shop_conn.execute(
            "SELECT * FROM payment WHERE bill_id=? ORDER BY id", (bill_id,))]
        bill = tuple(shop_conn.execute("SELECT * FROM bill WHERE id=?", (bill_id,)).fetchone())
        return lines, pays, bill

    before = snap()
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    assert snap() == before
