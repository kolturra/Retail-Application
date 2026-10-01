import pytest
from PySide6.QtCore import Qt

from retail import i18n, segments
from retail.services import items, stock
from retail_ui.screens.items import ItemDialog, ItemsScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = ItemsScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def cell(sc, row, col):
    return sc.model.data(sc.model.index(row, col))


def grocery(conn):
    segments.apply_template(conn, "grocery")      # the shop_conn fixture sets no template features
    return segments.template_settings(conn)


def test_dialog_new_item_validation_and_values(shop_conn, qtbot):
    d = ItemDialog(grocery(shop_conn))
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.name_edit.setText(" Soap ")
    d.price_edit.setText("₹118")
    assert d.ok_button.isEnabled()
    d.gst_box.setCurrentIndex(d.gst_box.findData(1800))
    d.sku_edit.setText("S1")
    d.buy_edit.setText("90.50")
    d.reorder_edit.setText("5")
    d.barcodes_edit.setText("111, 222 ,, 111")
    v = d.values()
    assert v == {"name": "Soap", "sku": "S1", "hsn": None, "gst_rate_bp": 1800, "unit": "pcs",
                 "sell_price_paise": 11800, "buy_price_paise": 9050, "reorder_milli": 5000,
                 "warranty_months": 0, "tracking": "none"}
    assert d.barcodes() == ["111", "222"]
    d.buy_edit.setText("x")
    assert not d.ok_button.isEnabled()


def test_dialog_edit_prefills_and_can_lock_tracking(shop_conn, qtbot):
    item_id = items.create_item(shop_conn, name="Rice", sell_price_paise=6000, gst_rate_bp=500, unit="kg",
                                tracking="weighed", sku="R1", hsn="1006", reorder_milli=2500, barcodes=["999"])
    row = items.get_item(shop_conn, item_id)
    d = ItemDialog(grocery(shop_conn), item=row, barcodes=items.item_barcodes(shop_conn, item_id), locked_tracking=True)
    qtbot.addWidget(d)
    assert (d.name_edit.text(), d.sku_edit.text(), d.hsn_edit.text(), d.price_edit.text()) == ("Rice", "R1", "1006", "60.00")
    assert d.gst_box.currentData() == 500 and d.unit_box.currentText() == "kg"
    assert d.tracking_box.currentData() == "weighed" and not d.tracking_box.isEnabled()
    assert d.reorder_edit.text() == "2.5" and d.barcodes_edit.text() == "999"


def test_dialog_keeps_a_gst_rate_that_is_not_in_the_template_slabs(shop_conn, qtbot):
    item_id = items.create_item(shop_conn, name="Old", sell_price_paise=100, gst_rate_bp=1200)
    d = ItemDialog(grocery(shop_conn), item=items.get_item(shop_conn, item_id))
    qtbot.addWidget(d)
    assert d.gst_box.currentData() == 1200


def test_dialog_warranty_field_follows_the_template_feature(shop_conn, qtbot):
    g = ItemDialog(grocery(shop_conn))
    qtbot.addWidget(g)
    assert g.warranty_spin.isHidden()
    segments.apply_template(shop_conn, "electronics")
    e = ItemDialog(segments.template_settings(shop_conn))
    qtbot.addWidget(e)
    assert not e.warranty_spin.isHidden() and e.tracking_box.currentData() == "serial"


def test_screen_lists_items_with_stock_and_highlights_low_stock(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Rice", sell_price_paise=6000, unit="kg", tracking="weighed", reorder_milli=5000)
    b = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, sku="S1")
    stock.record(conn, a, 2000, "opening")
    stock.record(conn, b, 9000, "opening")
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(2)] == ["Rice", "Soap"]
    assert cell(screen, 1, 1) == "S1" and cell(screen, 1, 2) == "₹118.00" and cell(screen, 1, 3) == "18%"
    assert cell(screen, 0, 5) == "2 kg" and cell(screen, 0, 6) == "5 kg"
    assert screen.model.data(screen.model.index(0, 0), Qt.ItemDataRole.BackgroundRole) is not None   # low
    assert screen.model.data(screen.model.index(1, 0), Qt.ItemDataRole.BackgroundRole) is None


def test_search_and_show_inactive(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Rice", sell_price_paise=1)
    items.create_item(conn, name="Soap", sell_price_paise=1)
    items.set_item_active(conn, a, False)
    screen.refresh()
    assert screen.model.rowCount() == 1
    screen.inactive_box.setChecked(True)
    screen.refresh()
    assert screen.model.rowCount() == 2 and i18n.tr("items.inactive") in cell(screen, 0, 0)
    screen.search_edit.setText("soap")
    screen.refresh()
    assert screen.model.rowCount() == 1


def test_add_item_creates_it_with_barcodes(screen):
    values = {"name": "Parle-G", "sku": "P1", "hsn": None, "gst_rate_bp": 500, "unit": "pcs",
              "sell_price_paise": 1000, "buy_price_paise": 800, "reorder_milli": 0, "warranty_months": 0,
              "tracking": "none"}
    screen._ask_item = lambda item, barcodes, locked: {"values": values, "barcodes": ["8901"]}
    screen.add_item()
    assert screen.model.rowCount() == 1 and items.resolve(screen.session.conn, "8901")[0]["name"] == "Parle-G"


def test_edit_item_updates_fields_and_barcodes_and_locks_tracking_after_stock(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Soap", sell_price_paise=100, barcodes=["111"])
    stock.record(conn, a, 1000, "opening")
    screen.refresh()
    screen.table.selectRow(0)
    seen = {}

    def ask(item, barcodes, locked):
        seen.update(name=item["name"], barcodes=barcodes, locked=locked)
        return {"values": {"name": "Soap Big", "sku": "", "hsn": None, "gst_rate_bp": 0, "unit": "pcs",
                           "sell_price_paise": 250, "buy_price_paise": 0, "reorder_milli": 0,
                           "warranty_months": 0, "tracking": "none"}, "barcodes": ["222"]}

    screen._ask_item = ask
    screen.edit_item()
    assert seen == {"name": "Soap", "barcodes": ["111"], "locked": True}
    row = items.get_item(conn, a)
    assert (row["name"], row["sell_price_paise"]) == ("Soap Big", 250) and items.item_barcodes(conn, a) == ["222"]


def test_validation_errors_from_the_engine_are_reported_not_raised(screen):
    conn = screen.session.conn
    items.create_item(conn, name="A", sell_price_paise=1, sku="X")
    values = {"name": "B", "sku": "X", "hsn": None, "gst_rate_bp": 0, "unit": "pcs", "sell_price_paise": 1,
              "buy_price_paise": 0, "reorder_milli": 0, "warranty_months": 0, "tracking": "none"}
    screen._ask_item = lambda item, barcodes, locked: {"values": values, "barcodes": []}
    screen.add_item()
    assert len(screen.errors) == 1 and screen.model.rowCount() == 1


def test_toggle_active_deactivates_and_reactivates(screen):
    a = items.create_item(screen.session.conn, name="Soap", sell_price_paise=1)
    screen.inactive_box.setChecked(True)
    screen.refresh()
    screen.table.selectRow(0)
    screen.toggle_active()
    assert items.get_item(screen.session.conn, a)["active"] == 0
    screen.table.selectRow(0)
    screen.toggle_active()
    assert items.get_item(screen.session.conn, a)["active"] == 1


def test_a_note_appears_when_the_list_is_truncated(screen):
    conn = screen.session.conn
    conn.execute("BEGIN")
    conn.executemany("INSERT INTO item(name, sell_price_paise) VALUES (?,?)",
                     [(f"Item {i:04d}", 100) for i in range(600)])
    conn.execute("COMMIT")
    screen.refresh()
    assert screen.model.rowCount() == 500 and screen.note_label.text() == i18n.tr("items.limit_note")
    screen.search_edit.setText("Item 0599")
    assert screen.model.rowCount() == 1 and screen.note_label.text() == ""


def test_read_only_disables_edits(screen):
    screen.apply_read_only(True)
    assert not any(b.isEnabled() for b in (screen.add_button, screen.edit_button, screen.toggle_button))
    assert screen.search_edit.isEnabled()


def test_language_switch_retranslates(screen):
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("common.name")
    assert screen.add_button.text() == i18n.tr("common.add")
