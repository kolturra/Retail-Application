import pytest
from PySide6.QtCore import Qt

from retail import guard, i18n
from retail.services import billing, items, parties, stock
from retail_ui import errors
from retail_ui.screens.counter import CounterScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = CounterScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)      # collect instead of showing a modal box
    return sc


def stocked(conn, **kw):
    kw.setdefault("sell_price_paise", 11800)
    kw.setdefault("gst_rate_bp", 1800)
    item_id = items.create_item(conn, **kw)
    stock.record(conn, item_id, 50_000, "opening")
    return item_id


def type_and_enter(screen, text):
    screen.entry.setText(text)
    screen.entry.returnPressed.emit()


def totals_text(screen):
    return screen.total_label.text()


def test_scanning_a_barcode_adds_a_line_and_refocuses_the_input(screen, qtbot):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    screen.show()
    type_and_enter(screen, "8901")
    assert screen.model.rowCount() == 1 and screen.entry.text() == ""
    assert "₹118.00" in totals_text(screen) and screen.focusWidget() is screen.entry
    row = [screen.model.data(screen.model.index(0, c)) for c in range(screen.model.columnCount())]
    assert row[0] == "Soap" and row[1] == "1" and row[5] == "₹118.00"


def test_quantity_prefix_and_blank_enter(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "")
    type_and_enter(screen, "3*8901")
    assert screen.model.rowCount() == 1 and screen.model.data(screen.model.index(0, 1)) == "3"
    assert "₹354.00" in totals_text(screen)


def test_unknown_code_opens_quick_add_prefilled_then_adds_the_line(screen):
    asked = []
    screen._ask_new_item = lambda text: asked.append(text) or {
        "name": "Parle-G", "sell_price_paise": 1000, "gst_rate_bp": 500, "tracking": "none",
        "unit": "pcs", "barcodes": ["8901719101015"]}
    type_and_enter(screen, "8901719101015")
    assert asked == ["8901719101015"] and screen.model.rowCount() == 1
    assert items.resolve(screen.session.conn, "8901719101015")[0]["name"] == "Parle-G"


def test_cancelling_quick_add_adds_nothing(screen):
    screen._ask_new_item = lambda text: None
    type_and_enter(screen, "999999")
    assert screen.model.rowCount() == 0 and screen.errors == []


def test_several_name_matches_use_the_picker(screen):
    a = stocked(screen.session.conn, name="Bath soap")
    b = stocked(screen.session.conn, name="Hand soap")
    screen._ask_pick = lambda rows: b
    type_and_enter(screen, "soap")
    assert screen.model.data(screen.model.index(0, 0)) == "Hand soap"
    screen._ask_pick = lambda rows: None
    type_and_enter(screen, "soap")
    assert screen.model.rowCount() == 1 and a


def test_weighed_item_asks_for_weight(screen):
    stocked(screen.session.conn, name="Rice", sell_price_paise=6000, gst_rate_bp=0, unit="kg", tracking="weighed")
    screen._ask_qty = lambda item: 750
    type_and_enter(screen, "rice")
    assert screen.model.data(screen.model.index(0, 1)) == "0.75 kg"
    assert "₹45.00" in totals_text(screen)


def test_serial_item_asks_for_serial(screen):
    conn = screen.session.conn
    phone = items.create_item(conn, name="Phone", sell_price_paise=100000, tracking="serial", barcodes=["1234567"])
    unit = stock.add_unit(conn, phone, serial="IMEI1")
    stock.record(conn, phone, 1000, "opening", unit_id=unit)
    screen._ask_serial = lambda item: "imei1"
    type_and_enter(screen, "1234567")
    assert "IMEI1" in screen.model.data(screen.model.index(0, 0))
    screen._ask_serial = lambda item: "WRONG"
    type_and_enter(screen, "1234567")
    assert len(screen.errors) == 1 and screen.model.rowCount() == 1       # engine error shown, bill intact


def test_blank_serial_is_ignored(screen):
    conn = screen.session.conn
    phone = items.create_item(conn, name="Phone", sell_price_paise=100000, tracking="serial", barcodes=["1234567"])
    unit = stock.add_unit(conn, phone, serial="IMEI1")
    stock.record(conn, phone, 1000, "opening", unit_id=unit)
    screen._ask_serial = lambda item: "   "
    type_and_enter(screen, "1234567")
    assert screen.model.rowCount() == 0 and screen.errors == []


def test_engine_errors_are_reported_not_raised_and_focus_returns(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    guard.set_read_only(True)
    screen.show()
    type_and_enter(screen, "8901")
    assert len(screen.errors) == 1 and isinstance(screen.errors[0], guard.ReadOnlyError)
    assert errors.message_for(screen.errors[0]) == i18n.tr("err.read_only")
    assert screen.focusWidget() is screen.entry


def test_discount_delete_and_customer(screen):
    conn = screen.session.conn
    stocked(conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "2*8901")
    screen.table.selectRow(0)
    screen._ask_discount = lambda max_paise: 1800
    screen.apply_discount()
    assert "₹218.00" in totals_text(screen) and screen.model.data(screen.model.index(0, 3)) == "₹18.00"
    ravi = parties.create_party(conn, name="Ravi", state_code="27")
    screen._ask_customer = lambda: ("set", ravi)
    screen.pick_customer()
    assert "Ravi" in screen.customer_label.text() and "IGST" in screen.tax_label.text()
    screen._ask_customer = lambda: ("clear", None)
    screen.pick_customer()
    assert "Ravi" not in screen.customer_label.text()
    screen.table.selectRow(0)
    screen.delete_selected_line()
    assert screen.model.rowCount() == 0


def test_hold_resume_and_discard(screen):
    conn = screen.session.conn
    stocked(conn, name="Soap", barcodes=["8901"])
    stocked(conn, name="Tea", barcodes=["8902"], sell_price_paise=500, gst_rate_bp=0)
    type_and_enter(screen, "8901")
    screen.hold_bill()
    assert screen.model.rowCount() == 0 and screen.controller.held_bills()[0]["lines"] == 1
    type_and_enter(screen, "8902")
    held_id = screen.controller.held_bills()[0]["id"]
    screen._ask_held = lambda rows: ("resume", held_id)
    screen.show_held()
    assert screen.model.data(screen.model.index(0, 0)) == "Soap"
    screen._confirm = lambda key: True
    screen.discard_bill()
    assert screen.model.rowCount() == 0
    screen._confirm = lambda key: False
    type_and_enter(screen, "8902")
    screen.discard_bill()
    assert screen.model.rowCount() == 1


def test_held_bills_survive_closing_the_app(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    first = CounterScreen(session)
    qtbot.addWidget(first)
    type_and_enter(first, "8901")
    first.hold_bill()
    second = CounterScreen(session)                   # "restart"
    qtbot.addWidget(second)
    assert [h["lines"] for h in second.controller.held_bills()] == [1]


def test_pay_finalizes_clears_and_announces_the_bill(screen, qtbot):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "8901")
    seen = []
    screen.sale_completed.connect(seen.append)
    screen._ask_payments = lambda total, party_id: [("cash", total)]
    screen.pay()
    assert screen.model.rowCount() == 0 and len(seen) == 1 and screen.last_bill_id == seen[0]
    assert billing.get_bill(screen.session.conn, seen[0])["bill"]["bill_no"] == "S000001"
    assert "S000001" in screen.status_label.text()


def test_cancelled_payment_keeps_the_bill(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "8901")
    screen._ask_payments = lambda total, party_id: None
    screen.pay()
    assert screen.model.rowCount() == 1


def test_paying_an_empty_bill_does_nothing(screen):
    screen._ask_payments = lambda total, party_id: pytest.fail("no dialog for an empty bill")
    screen.pay()
    assert screen.errors == []


def test_language_switch_keeps_the_bill_and_retranslates(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "2*8901")
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.model.rowCount() == 1 and "₹236.00" in totals_text(screen)
    assert screen.model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("bill.item") != "Item"
    assert screen.pay_button.text() == f"{i18n.tr('counter.pay')} (F12)"


def test_read_only_disables_the_write_controls(screen):
    screen.apply_read_only(True)
    for name in ("entry", "customer_button", "discount_button", "hold_button", "held_button",
                 "discard_button", "delete_button", "pay_button"):
        assert not getattr(screen, name).isEnabled(), name
    screen.apply_read_only(False)
    assert screen.entry.isEnabled() and screen.pay_button.isEnabled()


def test_function_key_shortcuts_are_registered(screen):
    assert set(screen.shortcut_keys) == {"F2", "F3", "F4", "F5", "F8", "Del", "F12"}


def test_refresh_after_a_restore_follows_the_new_connection(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    sc = CounterScreen(session)
    qtbot.addWidget(sc)
    type_and_enter(sc, "8901")
    snapshot = session.backup_now().path
    session.restore_from(snapshot)                    # new connection, same data
    sc.refresh()
    assert sc.controller.conn is session.conn and sc.model.rowCount() == 1


def test_refresh_after_a_restore_clears_a_bill_id_missing_from_the_restored_database(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    sc = CounterScreen(session)
    qtbot.addWidget(sc)
    type_and_enter(sc, "8901")
    sc.hold_bill()
    snapshot = session.backup_now().path
    type_and_enter(sc, "8901")                        # a second bill, created after the backup
    stale_id = sc.controller.bill_id
    sc.hold_bill()
    sc.controller.resume(stale_id)
    assert sc.controller.bill_id == stale_id
    session.restore_from(snapshot)
    sc.refresh()
    assert sc.controller.bill_id is None and sc.model.rowCount() == 0
