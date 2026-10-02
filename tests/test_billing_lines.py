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


def _batch_item(conn, policy="block"):
    shop.setup_shop(conn, name="S", state_code="36", oversell_policy=policy)
    milk = items.create_item(conn, name="Milk", sell_price_paise=100, tracking="batch")
    early = stock.add_unit(conn, milk, batch_no="B", expiry="2026-10-01")
    late = stock.add_unit(conn, milk, batch_no="A", expiry="2026-12-01")
    stock.record(conn, milk, 2_000, "purchase", unit_id=early)
    stock.record(conn, milk, 5_000, "purchase", unit_id=late)
    return milk, early, late


def test_block_policy_rejects_line_larger_than_any_single_batch(shop_conn):
    milk, _, _ = _batch_item(shop_conn)  # 7 in total but max 5 in one batch
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(stock.InsufficientStock):
        billing.add_line(shop_conn, bill_id, milk, 6000)


def test_block_policy_counts_batch_quantity_already_on_the_bill(shop_conn):
    milk, early, _ = _batch_item(shop_conn)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, milk, 2000, unit_id=early)
    with pytest.raises(stock.InsufficientStock):
        billing.add_line(shop_conn, bill_id, milk, 1000, unit_id=early)


def test_auto_pick_moves_to_next_batch_when_first_is_used_up(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    bill_id = billing.start_bill(shop_conn)
    first = billing.add_line(shop_conn, bill_id, milk, 2000)
    second = billing.add_line(shop_conn, bill_id, milk, 1000)
    by_id = {ln["id"]: ln["unit_id"] for ln in billing.get_bill(shop_conn, bill_id)["lines"]}
    assert (by_id[first], by_id[second]) == (early, late)


def test_warn_policy_allows_selling_beyond_a_batch(shop_conn):
    milk, early, late = _batch_item(shop_conn, policy="warn")
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, milk, 9000)
    assert billing.get_bill(shop_conn, bill_id)["lines"][0]["unit_id"] == early
    assert line
    assert billing.add_line(shop_conn, bill_id, milk, 1000, unit_id=late)


def test_supplied_unit_must_be_a_batch_of_the_same_item(shop_conn):
    milk, _, _ = _batch_item(shop_conn)
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial")
    serial_unit = add_phone(shop_conn, phone, "IMEI9")
    other = items.create_item(shop_conn, name="Curd", sell_price_paise=100, tracking="batch")
    other_unit = stock.add_unit(shop_conn, other, batch_no="C")
    stock.record(shop_conn, other, 5_000, "purchase", unit_id=other_unit)
    bill_id = billing.start_bill(shop_conn)
    for bad in (serial_unit, other_unit):
        with pytest.raises(BillingError):
            billing.add_line(shop_conn, bill_id, milk, 1000, unit_id=bad)


def test_party_must_exist(shop_conn, soap):
    with pytest.raises(BillingError, match="No such party"):
        billing.start_bill(shop_conn, party_id=999)
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError, match="No such party"):
        billing.set_party(shop_conn, bill_id, 999)


def test_cancelled_bill_rejects_further_changes(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.cancel_held(shop_conn, bill_id)
    with pytest.raises(BillingError):
        billing.remove_line(shop_conn, bill_id, line)
    with pytest.raises(BillingError):
        billing.set_party(shop_conn, bill_id, None)
    with pytest.raises(BillingError):
        billing.cancel_held(shop_conn, bill_id)


def test_cancel_held_writes_audit_row(shop_conn):
    bill_id = billing.start_bill(shop_conn)
    billing.cancel_held(shop_conn, bill_id)
    row = shop_conn.execute(
        "SELECT * FROM audit_log WHERE action = 'cancel_held' AND entity = 'bill'"
    ).fetchone()
    assert row is not None and row["entity_id"] == bill_id


def test_mixed_rate_bill_totals_are_sum_of_lines_with_one_round_off(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=11800, gst_rate_bp=1800)
    b = items.create_item(shop_conn, name="B", sell_price_paise=10550, gst_rate_bp=500)
    c = items.create_item(shop_conn, name="C", sell_price_paise=3333, gst_rate_bp=0)
    bill_id = billing.start_bill(shop_conn)
    for it in (a, b, c):
        billing.add_line(shop_conn, bill_id, it, 1000)
    data = billing.get_bill(shop_conn, bill_id)
    bill, lines = data["bill"], data["lines"]
    for col in ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise"):
        assert bill[col] == sum(ln[col] for ln in lines)
    line_sum = sum(ln["total_paise"] for ln in lines)
    assert line_sum == 11800 + 10550 + 3333
    assert bill["total_paise"] == 25700 and bill["round_off_paise"] == 25700 - line_sum
    assert bill["total_paise"] % 100 == 0


def test_gst_exclusive_total_is_taxable_plus_tax(shop_conn):
    shop.setup_shop(shop_conn, name="S", state_code="36", price_includes_gst=False)
    it = items.create_item(shop_conn, name="Soap", sell_price_paise=10000, gst_rate_bp=1800)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, it, 1000)
    assert totals(shop_conn, bill_id) == (10000, 900, 900, 0, 0, 11800)


def test_clearing_party_switches_back_to_intra_state(shop_conn, soap):
    pune = parties.create_party(shop_conn, name="Pune Traders", state_code="27")
    bill_id = billing.start_bill(shop_conn, party_id=pune)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.set_party(shop_conn, bill_id, None)
    assert totals(shop_conn, bill_id) == (10000, 900, 900, 0, 0, 11800)


def _unit_of(conn, bill_id, line_id):
    return next(l["unit_id"] for l in billing.get_bill(conn, bill_id)["lines"] if l["id"] == line_id)


def test_set_line_batch_overrides_the_auto_picked_batch(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, milk, 2000)
    assert _unit_of(shop_conn, bill_id, line) == early
    billing.set_line_batch(shop_conn, bill_id, line, late)
    assert _unit_of(shop_conn, bill_id, line) == late
    billing.set_line_batch(shop_conn, bill_id, line, late)  # same batch: no-op
    billing.finalize(shop_conn, bill_id, [("cash", 200)])
    assert stock.unit_on_hand(shop_conn, late) == 3000 and stock.unit_on_hand(shop_conn, early) == 2000


def test_set_line_batch_validates_batch_item_and_stock(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    other = items.create_item(shop_conn, name="Curd", sell_price_paise=100, tracking="batch")
    other_unit = stock.add_unit(shop_conn, other, batch_no="C")
    stock.record(shop_conn, other, 5_000, "purchase", unit_id=other_unit)
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, milk, 3000, unit_id=late)
    with pytest.raises(BillingError):
        billing.set_line_batch(shop_conn, bill_id, line, other_unit)   # another item's batch
    with pytest.raises(stock.InsufficientStock):
        billing.set_line_batch(shop_conn, bill_id, line, early)        # only 2 in that batch
    for bad in (True, "1", None, 1.0):
        with pytest.raises(BillingError):
            billing.set_line_batch(shop_conn, bill_id, line, bad)
    with pytest.raises(BillingError):
        billing.set_line_batch(shop_conn, bill_id, 9999, early)
    assert _unit_of(shop_conn, bill_id, line) == late


def test_set_line_batch_counts_other_lines_on_that_batch(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, milk, 2000, unit_id=early)
    line = billing.add_line(shop_conn, bill_id, milk, 1000, unit_id=late)
    with pytest.raises(stock.InsufficientStock):
        billing.set_line_batch(shop_conn, bill_id, line, early)


def test_set_line_batch_allows_an_expired_batch_like_add_line(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    shop_conn.execute("UPDATE stock_unit SET expiry = '2000-01-01' WHERE id = ?", (early,))
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, milk, 1000, unit_id=late)
    billing.set_line_batch(shop_conn, bill_id, line, early)
    assert _unit_of(shop_conn, bill_id, line) == early


def test_set_line_batch_rejects_untracked_lines_and_final_bills(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, soap)
    with pytest.raises(BillingError):
        billing.set_line_batch(shop_conn, bill_id, line, 1)
    milk, early, late = _batch_item(shop_conn)
    b2 = billing.start_bill(shop_conn)
    l2 = billing.add_line(shop_conn, b2, milk, 1000)
    billing.finalize(shop_conn, b2, [("cash", 100)])
    with pytest.raises(BillingError):
        billing.set_line_batch(shop_conn, b2, l2, late)


def test_set_line_batch_is_blocked_when_read_only(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, milk, 1000)
    guard.set_read_only(True)
    try:
        with pytest.raises(guard.ReadOnlyError):
            billing.set_line_batch(shop_conn, bill_id, line, late)
    finally:
        guard.set_read_only(False)


def test_batch_choices_lists_stocked_batches_in_expiry_order(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    empty = stock.add_unit(shop_conn, milk, batch_no="Z", expiry="2026-09-01")
    assert [(c["id"], c["batch_no"], c["expiry"], c["on_hand_milli"]) for c in stock.batch_choices(shop_conn, milk)] == [
        (early, "B", "2026-10-01", 2000), (late, "A", "2026-12-01", 5000)]
    assert [c["id"] for c in stock.batch_choices(shop_conn, milk, include_unit_id=empty)][0] == empty


def test_set_line_batch_requires_a_sale_bill(shop_conn):
    milk, early, late = _batch_item(shop_conn)
    bill_id = billing.start_bill(shop_conn)
    line = billing.add_line(shop_conn, bill_id, milk, 1000)
    shop_conn.execute("UPDATE bill SET kind = 'sale_return' WHERE id = ?", (bill_id,))
    with pytest.raises(BillingError):
        billing.set_line_batch(shop_conn, bill_id, line, late)
