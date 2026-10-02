import pytest
from PySide6.QtCore import Qt

from retail import segments
from retail.services import items, parties
from retail_ui.screens import counter_dialogs as cd


def rows(conn):
    a = items.create_item(conn, name="Bath soap", sell_price_paise=1000)
    b = items.create_item(conn, name="Hand soap", sell_price_paise=2000)
    return items.list_items(conn), a, b


def test_pick_item_dialog(shop_conn, qtbot):
    listed, a, b = rows(shop_conn)
    d = cd.PickItemDialog(listed)
    qtbot.addWidget(d)
    assert d.selected_item_id() == a                      # first row preselected
    d.list.setCurrentRow(1)
    assert d.selected_item_id() == b
    assert "₹20.00" in d.list.item(1).text()


@pytest.mark.parametrize("text,ok,value", [("2", True, 2000), ("0.75", True, 750), ("", False, None),
                                           ("0", False, None), ("abc", False, None), ("-1", False, None)])
def test_qty_dialog(qtbot, text, ok, value):
    d = cd.QtyDialog("Rice")
    qtbot.addWidget(d)
    d.edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.qty_milli() == value


def test_serial_dialog(qtbot):
    d = cd.SerialDialog("Phone")
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.edit.setText("  356938035643809 ")
    assert d.ok_button.isEnabled() and d.serial() == "356938035643809"


def grocery(conn):
    segments.apply_template(conn, "grocery")      # the shop_conn fixture sets no template features
    return segments.template_settings(conn)


def electronics(conn):
    segments.apply_template(conn, "electronics")
    return segments.template_settings(conn)


def test_quick_add_numeric_prefill_becomes_the_barcode(shop_conn, qtbot):
    d = cd.QuickAddDialog("8901719101015", grocery(shop_conn))
    qtbot.addWidget(d)
    assert d.name_edit.text() == "" and d.barcode_edit.text() == "8901719101015"
    assert not d.ok_button.isEnabled()                    # name and price still missing
    d.name_edit.setText(" Parle-G ")
    d.price_edit.setText("₹10")
    assert d.ok_button.isEnabled()
    v = d.values()
    assert v["name"] == "Parle-G" and v["sell_price_paise"] == 1000 and v["barcodes"] == ["8901719101015"]
    assert v["tracking"] == "none" and v["unit"] == "pcs"


def test_quick_add_text_prefill_becomes_the_name_and_gst_defaults_to_zero(shop_conn, qtbot):
    d = cd.QuickAddDialog("rice", grocery(shop_conn))
    qtbot.addWidget(d)
    assert d.name_edit.text() == "rice" and d.barcode_edit.text() == ""
    d.price_edit.setText("60")
    assert d.values()["gst_rate_bp"] == 0 and d.values()["barcodes"] == []


def test_quick_add_negative_price_disables_ok(shop_conn, qtbot):
    d = cd.QuickAddDialog("rice", grocery(shop_conn))
    qtbot.addWidget(d)
    d.price_edit.setText("60")
    assert d.ok_button.isEnabled()
    d.price_edit.setText("-5")
    assert not d.ok_button.isEnabled()


def test_quick_add_offers_only_the_tracking_modes_the_template_enables(shop_conn, qtbot):
    g = cd.QuickAddDialog("x", grocery(shop_conn))
    qtbot.addWidget(g)
    assert [g.tracking_box.itemData(i) for i in range(g.tracking_box.count())] == ["none", "weighed"]
    e = cd.QuickAddDialog("x", electronics(shop_conn))
    qtbot.addWidget(e)
    assert "serial" in [e.tracking_box.itemData(i) for i in range(e.tracking_box.count())]
    assert e.tracking_box.currentData() == "serial"       # the template's default
    g.tracking_box.setCurrentIndex(g.tracking_box.findData("weighed"))
    g.name_edit.setText("Rice")
    g.price_edit.setText("60")
    assert g.values()["unit"] == "kg"


def test_quick_add_gst_slabs_come_from_the_template(shop_conn, qtbot):
    d = cd.QuickAddDialog("x", grocery(shop_conn))
    qtbot.addWidget(d)
    assert [d.gst_box.itemData(i) for i in range(d.gst_box.count())] == [0, 500, 1800, 4000]
    d.gst_box.setCurrentIndex(d.gst_box.findData(1800))
    d.name_edit.setText("Soap")
    d.price_edit.setText("118")
    assert d.values()["gst_rate_bp"] == 1800


def test_customer_dialog_search_select_and_create(shop_conn, qtbot):
    ravi = parties.create_party(shop_conn, name="Ravi", phone="9876500001")
    parties.create_party(shop_conn, name="Wholesale Co", type="supplier")
    d = cd.CustomerDialog(shop_conn)
    qtbot.addWidget(d)
    assert d.list.count() == 1                            # suppliers are not customers
    d.list.setCurrentRow(0)
    assert d.party_id() == ravi and not d.cleared()
    d.search_edit.setText("zzz")
    assert d.list.count() == 0 and d.party_id() is None
    d.new_name.setText("Sita")
    d.new_phone.setText("12345")
    d.add_button.click()
    sita = d.party_id()
    assert sita is not None and parties.list_parties(shop_conn, search="Sita")[0]["phone"] == "12345"


def test_customer_dialog_walk_in_clears_the_customer(shop_conn, qtbot):
    d = cd.CustomerDialog(shop_conn)
    qtbot.addWidget(d)
    d.walk_in_button.click()
    assert d.cleared() and d.party_id() is None


@pytest.mark.parametrize("text,ok,paise", [("0", True, 0), ("₹18", True, 1800), ("18.5", True, 1850),
                                           ("200", False, None), ("-1", False, None), ("x", False, None), ("", False, None)])
def test_discount_dialog(qtbot, text, ok, paise):
    d = cd.DiscountDialog(max_paise=11800)
    qtbot.addWidget(d)
    d.edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.discount_paise() == paise


def test_held_bills_dialog(qtbot):
    held = [{"id": 5, "party": "Ravi", "total_paise": 11800, "lines": 2},
            {"id": 9, "party": "", "total_paise": 500, "lines": 1}]
    d = cd.HeldBillsDialog(held)
    qtbot.addWidget(d)
    assert d.list.count() == 2 and d.selected_bill_id() == 5 and d.action() is None
    d.list.setCurrentRow(1)
    d.resume_button.click()
    assert d.action() == "resume" and d.selected_bill_id() == 9
    d2 = cd.HeldBillsDialog(held)
    qtbot.addWidget(d2)
    d2.discard_button.click()
    assert d2.action() == "discard"
    empty = cd.HeldBillsDialog([])
    qtbot.addWidget(empty)
    assert not empty.resume_button.isEnabled() and empty.selected_bill_id() is None


def test_pay_dialog_cash_is_prefilled_and_valid(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={"emi": False, "udhaar": True})
    qtbot.addWidget(d)
    assert set(d.edits) == {"cash", "upi", "card"}        # no credit without a customer, no EMI
    assert d.edits["cash"].text() == "118.00" and d.is_valid() and d.ok_button.isEnabled()
    assert d.payments() == [("cash", 11800)] and d.remaining_paise == 0


def test_pay_dialog_split_payment_and_balance(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.edits["cash"].setText("50")
    assert d.remaining_paise == 6800 and not d.is_valid() and not d.ok_button.isEnabled()
    d.edits["upi"].setText("68")
    assert d.is_valid() and d.payments() == [("cash", 5000), ("upi", 6800)]


def test_pay_dialog_overpayment_and_garbage_are_invalid(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.edits["upi"].setText("1")
    assert d.remaining_paise == -100 and not d.is_valid()
    d.edits["upi"].setText("abc")
    assert not d.is_valid() and not d.ok_button.isEnabled()


def test_pay_dialog_negative_amount_is_invalid_even_when_the_sum_balances(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.edits["cash"].setText("200")
    d.edits["upi"].setText("-82")
    assert d.remaining_paise == 0                         # sums to the total, but one amount is negative
    assert not d.is_valid() and not d.ok_button.isEnabled()


def test_pay_dialog_change_for_cash_given(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.cash_given_edit.setText("200")
    assert d.change_paise == 8200
    d.cash_given_edit.setText("50")
    assert d.change_paise == 0                            # not enough cash given: no change shown


def test_pay_dialog_credit_and_emi_depend_on_customer_and_features(qtbot):
    d = cd.PayDialog(11800, has_customer=True, features={"emi": True, "udhaar": True})
    qtbot.addWidget(d)
    assert set(d.edits) == {"cash", "upi", "card", "emi", "credit"}
    d.edits["cash"].setText("0")
    d.edits["credit"].setText("118")
    assert d.payments() == [("credit", 11800)] and d.is_valid()
    no_udhaar = cd.PayDialog(11800, has_customer=True, features={"udhaar": False})
    qtbot.addWidget(no_udhaar)
    assert "credit" not in no_udhaar.edits


def test_pay_dialog_free_bill_is_valid_with_no_payments(qtbot):
    d = cd.PayDialog(0, has_customer=False, features={})
    qtbot.addWidget(d)
    assert d.is_valid() and d.payments() == []


def test_batch_dialog_lists_batches_defaults_to_current_and_marks_expired(shop_conn, qtbot):
    from retail import i18n
    choices = [{"id": 5, "batch_no": "OLD", "expiry": "2000-01-31", "on_hand_milli": 2500},
               {"id": 6, "batch_no": "NEW", "expiry": "2999-12-01", "on_hand_milli": 4000},
               {"id": 7, "batch_no": "NOEXP", "expiry": None, "on_hand_milli": 1000}]
    d = cd.BatchDialog(choices, 6)
    qtbot.addWidget(d)
    assert d.selected_batch_id() == 6 and d.list.count() == 3
    assert "OLD" in d.list.item(0).text() and "31-01-2000" in d.list.item(0).text()
    assert "2.5" in d.list.item(0).text() and i18n.tr("dlg.batch_expired") in d.list.item(0).text()
    assert i18n.tr("dlg.batch_expired") not in d.list.item(1).text()
    assert i18n.tr("dlg.batch_no_expiry") in d.list.item(2).text()
    d.list.setCurrentRow(2)
    assert d.selected_batch_id() == 7


def test_batch_dialog_with_no_choices_cannot_be_accepted(shop_conn, qtbot):
    d = cd.BatchDialog([], None)
    qtbot.addWidget(d)
    assert d.selected_batch_id() is None and not d.ok_button.isEnabled()
