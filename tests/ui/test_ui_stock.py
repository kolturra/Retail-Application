import pytest
from PySide6.QtCore import Qt

from retail import i18n
from retail.services import items, parties, purchases, stock
from retail_ui.screens.stock import AdjustDialog, PurchaseDialog, StockScreen
from retail_ui.widgets.pickers import ItemPicker


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = StockScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def test_item_picker_searches_and_selects(shop_conn, qtbot):
    a = items.create_item(shop_conn, name="Bath soap", sell_price_paise=1)
    b = items.create_item(shop_conn, name="Rice", sell_price_paise=1)
    p = ItemPicker(lambda: shop_conn)
    qtbot.addWidget(p)
    assert p.list.count() == 2 and p.selected_item() is None
    p.list.setCurrentRow(1)
    assert p.selected_item()["id"] == b
    p.search.setText("soap")
    assert p.list.count() == 1 and p.selected_item() is None
    p.list.setCurrentRow(0)
    assert p.selected_item()["id"] == a


@pytest.mark.parametrize("text,ok,milli", [("5", True, 5000), ("-2.5", True, -2500), ("0", False, None),
                                           ("", False, None), ("abc", False, None), ("1e3", False, None),
                                           ("1_0", False, None), ("1.0004", False, None), ("+3", True, 3000)])
def test_adjust_dialog_quantity(qtbot, text, ok, milli):
    d = AdjustDialog("Rice")
    qtbot.addWidget(d)
    d.reason_edit.setText("count")
    d.qty_edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.qty_milli() == milli


def test_adjust_dialog_needs_a_reason(qtbot):
    d = AdjustDialog("Rice")
    qtbot.addWidget(d)
    d.qty_edit.setText("1")
    assert not d.ok_button.isEnabled()
    d.reason_edit.setText("  damaged ")
    assert d.ok_button.isEnabled() and d.reason() == "damaged"


def test_stock_tab_lists_on_hand_and_flags_low_stock(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Rice", sell_price_paise=1, unit="kg", tracking="weighed", reorder_milli=5000)
    b = items.create_item(conn, name="Soap", sell_price_paise=1)
    stock.record(conn, a, 2000, "opening")
    stock.record(conn, b, 9000, "opening")
    screen.refresh()
    assert [screen.stock_model.data(screen.stock_model.index(r, 0)) for r in range(2)] == ["Rice", "Soap"]
    assert screen.stock_model.data(screen.stock_model.index(0, 1)) == "2 kg"
    assert screen.stock_model.data(screen.stock_model.index(0, 3)) == i18n.tr("stock.status_low")
    assert screen.stock_model.data(screen.stock_model.index(1, 3)) == i18n.tr("stock.status_ok")
    assert screen.stock_model.data(screen.stock_model.index(0, 0), Qt.ItemDataRole.BackgroundRole) is not None
    assert screen.stock_model.data(screen.stock_model.index(1, 0), Qt.ItemDataRole.BackgroundRole) is None
    assert screen.low_label.text() == i18n.tr("stock.low", count=1)


def test_adjust_flow_changes_stock_and_reports_errors(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Soap", sell_price_paise=1)
    stock.record(conn, a, 3000, "opening")
    screen.refresh()
    screen.stock_table.selectRow(0)
    screen._ask_adjust = lambda item: (-1000, "damaged")
    screen.adjust_stock()
    assert stock.on_hand(conn, a) == 2000
    screen._ask_adjust = lambda item: (-9000, "oops")
    screen.adjust_stock()
    assert len(screen.errors) == 1 and stock.on_hand(conn, a) == 2000
    screen._ask_adjust = lambda item: None
    screen.adjust_stock()
    assert stock.on_hand(conn, a) == 2000


def test_adjust_does_nothing_without_a_selection(screen):
    screen._ask_adjust = lambda item: pytest.fail("nothing selected")
    screen.adjust_stock()


def test_purchase_dialog_builds_plain_serial_and_batch_lines(make_session, qtbot):
    s = make_session()
    conn = s.conn
    tea = items.create_item(conn, name="Tea", sell_price_paise=500)
    phone = items.create_item(conn, name="Phone", sell_price_paise=1, tracking="serial")
    milk = items.create_item(conn, name="Milk", sell_price_paise=1, tracking="batch")
    sup = parties.create_party(conn, name="Wholesale", type="supplier")
    d = PurchaseDialog(s)
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled() and d.supplier_id() is None
    d.supplier_box.setCurrentIndex(d.supplier_box.findData(sup))
    d.invoice_edit.setText(" W-1 ")

    def pick(name):
        d.picker.search.setText(name)
        d.picker.list.setCurrentRow(0)

    pick("Tea")
    d.qty_edit.setText("10")
    d.cost_edit.setText("30")
    assert d.add_line() is True and d.ok_button.isEnabled()
    pick("Phone")
    assert not d.serials_edit.isHidden() and d.qty_edit.isHidden()
    d.serials_edit.setPlainText("imei1\n\n imei2 \n")
    d.cost_edit.setText("8000")
    assert d.add_line() is True
    pick("Milk")
    assert not d.batch_edit.isHidden()
    d.qty_edit.setText("6")
    d.cost_edit.setText("50")
    d.batch_edit.setText("B1")
    d.expiry_edit.setText("2026-12-01")
    assert d.add_line() is True
    lines = d.lines()
    assert [(l.item_id, l.qty_milli, l.cost_paise) for l in lines] == [
        (tea, 10000, 3000), (phone, 2000, 800000), (milk, 6000, 5000)]
    assert lines[1].serials == ("imei1", "imei2") and lines[2].batch_no == "B1" and lines[2].expiry == "2026-12-01"
    assert d.invoice_no() == "W-1" and d.supplier_id() == sup and len(d.date_iso()) == 10
    assert d.purchase_model.rowCount() == 3


@pytest.mark.parametrize("setup", [
    dict(name="Tea", qty="", cost="30"), dict(name="Tea", qty="abc", cost="30"), dict(name="Tea", qty="1", cost=""),
    dict(name="Phone", serials="", cost="1"), dict(name="Milk", qty="1", cost="1", batch=""),
])
def test_purchase_dialog_rejects_incomplete_lines(make_session, qtbot, setup):
    s = make_session()
    for name, tracking in (("Tea", "none"), ("Phone", "serial"), ("Milk", "batch")):
        items.create_item(s.conn, name=name, sell_price_paise=1, tracking=tracking)
    d = PurchaseDialog(s)
    qtbot.addWidget(d)
    d.picker.search.setText(setup["name"])
    d.picker.list.setCurrentRow(0)
    d.qty_edit.setText(setup.get("qty", ""))
    d.cost_edit.setText(setup.get("cost", ""))
    d.serials_edit.setPlainText(setup.get("serials", ""))
    d.batch_edit.setText(setup.get("batch", ""))
    assert d.add_line() is False and d.lines() == [] and d.error_label.text() == i18n.tr("err.invalid_input")


def test_purchase_dialog_can_add_a_supplier(make_session, qtbot):
    s = make_session()
    d = PurchaseDialog(s)
    qtbot.addWidget(d)
    d.new_supplier_edit.setText("City Wholesale")
    d.add_supplier_button.click()
    assert d.supplier_box.currentText() == "City Wholesale" and d.supplier_id() is not None


def test_new_purchase_flow_receives_stock_and_lists_the_purchase(screen):
    conn = screen.session.conn
    tea = items.create_item(conn, name="Tea", sell_price_paise=500)
    screen._ask_purchase = lambda: {"party_id": None, "invoice_no": "W1", "date_iso": "2026-09-01",
                                    "lines": [purchases.PurchaseLine(tea, 4000, 300)]}
    screen.new_purchase()
    assert stock.on_hand(conn, tea) == 4000
    assert screen.purchase_model.data(screen.purchase_model.index(0, 1)) == "W1"
    assert screen.purchase_model.data(screen.purchase_model.index(0, 3)) == "₹12.00"


def test_a_failed_purchase_is_reported_and_writes_nothing(screen):
    conn = screen.session.conn
    phone = items.create_item(conn, name="Phone", sell_price_paise=1, tracking="serial")
    screen._ask_purchase = lambda: {"party_id": None, "invoice_no": None, "date_iso": "2026-09-01",
                                    "lines": [purchases.PurchaseLine(phone, 1000, 1, serials=("A",)),
                                              purchases.PurchaseLine(phone, 1000, 1, serials=("a",))]}
    screen.new_purchase()
    assert len(screen.errors) == 1 and stock.on_hand(conn, phone) == 0


def test_read_only_and_language(screen):
    screen.apply_read_only(True)
    assert not screen.adjust_button.isEnabled() and not screen.new_purchase_button.isEnabled()
    i18n.set_language("te")
    screen.retranslate()
    assert screen.stock_model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("common.name")
    assert screen.tabs.tabText(0) == i18n.tr("stock.tab_stock")


@pytest.mark.parametrize("name", ["", "  "])
def test_add_supplier_errors_go_through_show_error(make_session, qtbot, name):
    d = PurchaseDialog(make_session())
    qtbot.addWidget(d)
    d.errors = []
    d._show_error = lambda exc: d.errors.append(exc)
    d.new_supplier_edit.setText(name)
    d.add_supplier_button.click()
    assert len(d.errors) == 1
