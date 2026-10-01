from types import SimpleNamespace

import pytest

from retail import guard
from retail.services import billing, items, parties, stock
from retail_ui.screens.counter_logic import CounterController


@pytest.fixture
def ctl(shop_conn):
    return CounterController(SimpleNamespace(conn=shop_conn))


def stocked(conn, **kw):
    kw.setdefault("sell_price_paise", 11800)
    kw.setdefault("gst_rate_bp", 1800)
    item_id = items.create_item(conn, **kw)
    stock.record(conn, item_id, 50_000, "opening")
    return item_id


def test_barcode_scan_adds_a_line(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    result = ctl.submit("8901")
    assert result.kind == "added" and result.qty_milli == 1000
    assert ctl.detail()["bill"]["total_paise"] == 11800 and ctl.has_lines()


def test_trailing_whitespace_from_a_scanner_is_ignored(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    assert ctl.submit("8901  \r\n").kind == "added"


def test_quantity_prefix(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("3*8901")
    assert ctl.detail()["lines"][0]["qty_milli"] == 3000


@pytest.mark.parametrize("text", ["", "   ", "0*soap", "0.0001*soap"])
def test_empty_and_zero_quantity_entries_are_ignored(shop_conn, ctl, text):
    stocked(shop_conn, name="Soap")
    assert ctl.submit(text).kind == "ignored"
    assert ctl.bill_id is None and billing.list_held(shop_conn) == []


def test_unknown_code_asks_for_a_new_item_and_creates_no_bill(shop_conn, ctl):
    result = ctl.submit("2*999999")
    assert (result.kind, result.text, result.qty_milli) == ("new_item", "999999", 2000)
    assert ctl.bill_id is None


def test_several_name_matches_ask_which_one(shop_conn, ctl):
    stocked(shop_conn, name="Bath soap")
    stocked(shop_conn, name="Hand soap")
    result = ctl.submit("soap")
    assert result.kind == "pick" and [r["name"] for r in result.items] == ["Bath soap", "Hand soap"]
    chosen = result.items[1]
    assert ctl.add(chosen, result.qty_milli, explicit_qty=result.explicit_qty).kind == "added"
    assert ctl.detail()["lines"][0]["item_name"] == "Hand soap"


def test_weighed_item_without_a_typed_quantity_asks_for_weight(shop_conn, ctl):
    rice = stocked(shop_conn, name="Rice", sell_price_paise=6000, gst_rate_bp=0, unit="kg", tracking="weighed")
    result = ctl.submit("rice")
    assert result.kind == "weight" and result.item["id"] == rice and ctl.bill_id is None
    assert ctl.add(result.item, 750).kind == "added"
    assert ctl.detail()["bill"]["total_paise"] == 4500


def test_weighed_item_with_a_typed_quantity_does_not_ask(shop_conn, ctl):
    stocked(shop_conn, name="Rice", sell_price_paise=6000, gst_rate_bp=0, unit="kg", tracking="weighed")
    assert ctl.submit("0.5*rice").kind == "added"


def test_serial_item_asks_for_the_serial_then_adds(shop_conn, ctl):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial")
    unit = stock.add_unit(shop_conn, phone, serial="IMEI1")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    result = ctl.submit("phone")
    assert result.kind == "serial" and result.item["id"] == phone
    added = ctl.add(result.item, 1000, serial=" imei1 ")
    assert added.kind == "added" and ctl.detail()["lines"][0]["serial"] == "IMEI1"


def test_a_failed_add_surfaces_the_engine_error_and_leaves_no_phantom_line(shop_conn, ctl):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial")
    with pytest.raises(billing.SerialUnavailable):
        ctl.add(items.get_item(shop_conn, phone), 1000, serial="NOPE")
    assert not ctl.has_lines()


def test_customer_discount_and_delete_line(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("2*8901")
    line_id = ctl.detail()["lines"][0]["id"]
    ctl.set_discount(line_id, 1800)
    assert ctl.detail()["bill"]["total_paise"] == 21800
    pune = parties.create_party(shop_conn, name="Pune Co", state_code="27")
    ctl.set_customer(pune)
    assert ctl.detail()["bill"]["igst_paise"] > 0 and ctl.detail()["party"]["name"] == "Pune Co"
    ctl.remove_line(line_id)
    assert not ctl.has_lines()


def test_hold_lists_the_bill_and_resume_brings_it_back(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    stocked(shop_conn, name="Tea", barcodes=["8902"])
    ctl.submit("8901")
    first = ctl.hold()
    assert first is not None and ctl.bill_id is None
    ctl.submit("8902")
    held = ctl.held_bills()
    assert [(h["id"], h["lines"]) for h in held] == [(first, 1)]
    second = ctl.bill_id
    ctl.resume(first)                       # the current bill is held automatically
    assert ctl.bill_id == first and [h["id"] for h in ctl.held_bills()] == [second]


def test_hold_of_an_empty_bill_returns_none_and_cancels_it(shop_conn, ctl):
    pune = parties.create_party(shop_conn, name="Pune Co")
    ctl.set_customer(pune)                   # creates a held bill with no lines
    assert ctl.hold() is None and ctl.bill_id is None
    assert billing.list_held(shop_conn) == []


def test_held_bills_ignore_empty_ones(shop_conn, ctl):
    billing.start_bill(shop_conn)           # an empty held bill left by an earlier crash
    assert ctl.held_bills() == []


def test_resume_rejects_unknown_and_non_held_bills(shop_conn, ctl):
    item = stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    bill_id, _ = ctl.pay([("cash", 11800)])
    with pytest.raises(billing.BillingError):
        ctl.resume(bill_id)
    with pytest.raises(billing.BillingError):
        ctl.resume(999)
    assert item


def test_pay_finalizes_resets_and_returns_the_bill_number(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    bill_id, bill_no = ctl.pay([("cash", 11800)])
    assert bill_no == "S000001" and ctl.bill_id is None and not ctl.has_lines()
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "final"
    with pytest.raises(billing.BillingError):
        ctl.pay([("cash", 1)])              # nothing to pay


def test_a_failed_payment_keeps_the_bill(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    with pytest.raises(billing.BillingError):
        ctl.pay([("cash", 1)])
    assert ctl.has_lines()


def test_discard_cancels_the_current_bill(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    bill_id = ctl.bill_id
    ctl.discard()
    assert ctl.bill_id is None and billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "cancelled"
    ctl.discard()                           # nothing to discard: no error


def test_read_only_blocks_adding(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        ctl.submit("8901")
