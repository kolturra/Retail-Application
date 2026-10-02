import csv

import pytest
from PySide6.QtCore import QDate, Qt

from retail import i18n
from retail.services import billing, items, parties, stock
from retail_ui.screens.reports import ReportsScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = ReportsScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def seed(conn):
    """A sale of 2 x Rs 118 (18% GST) and a return of one of them."""
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn)
    line_id = billing.add_line(conn, bill_id, item, 2000)
    billing.finalize(conn, bill_id, [("cash", 23600)])
    billing.create_return(conn, bill_id, [(line_id, 1000)])


def _read(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def cell(model, row, col):
    return model.data(model.index(row, col))


def test_sales_register_tab(screen):
    seed(screen.session.conn)
    screen.refresh()
    m = screen.sales_model
    assert m.rowCount() == 2
    assert [cell(m, 0, c) for c in (0, 2, 5, 6, 7, 8, 10)] == [
        "S000001", i18n.tr("bills.sale"), "₹200.00", "₹18.00", "₹18.00", "₹0.00", "₹236.00"]
    assert cell(m, 1, 0) == "R000001" and cell(m, 1, 2) == i18n.tr("bills.return") and cell(m, 1, 10) == "-₹118.00"


def test_gst_summary_tab_nets_returns(screen):
    seed(screen.session.conn)
    screen.refresh()
    m = screen.gst_model
    assert m.rowCount() == 1
    assert [cell(m, 0, c) for c in range(5)] == ["18%", "₹100.00", "₹9.00", "₹9.00", "₹0.00"]


def test_daily_summary_tab(screen):
    seed(screen.session.conn)
    screen.refresh()
    m = screen.day_model
    assert [(cell(m, r, 0), cell(m, r, 1)) for r in range(m.rowCount())] == [
        (i18n.tr("rep.sales"), "₹236.00"), (i18n.tr("rep.returns"), "₹118.00"), (i18n.tr("rep.net"), "₹118.00"),
        (i18n.tr("rep.by_mode"), ""), (i18n.tr("pay.cash"), "₹118.00")]


def test_empty_range_shows_empty_tables(screen):
    screen.refresh()
    assert screen.sales_model.rowCount() == 0 and screen.gst_model.rowCount() == 0
    assert cell(screen.day_model, 2, 1) == "₹0.00"


def test_bad_range_is_reported_and_clears_the_tables(screen):
    seed(screen.session.conn)
    screen.refresh()
    screen.from_edit.setDate(QDate(2030, 1, 1))
    screen.to_edit.setDate(QDate(2020, 1, 1))
    screen.refresh()
    assert screen.errors == [] and screen.sales_model.rowCount() == 0 and screen.gst_model.rowCount() == 0
    assert screen.status_label.text() == i18n.tr("rep.bad_range")


def test_export_sales_register_csv(screen, tmp_path):
    seed(screen.session.conn)
    screen.refresh()
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_sales()
    rows = _read(tmp_path / "sales_register.csv")
    assert [r["bill_no"] for r in rows] == ["S000001", "R000001"] and rows[0]["total"] == "236.00"
    assert rows[1]["total"] == "-118.00" and "sales_register.csv" in screen.status_label.text()


def test_export_gst_summary_csv(screen, tmp_path):
    seed(screen.session.conn)
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_gst()
    rows = _read(tmp_path / "gst_summary.csv")
    assert rows == [{"gst_rate_bp": "1800", "taxable": "100.00", "cgst": "9.00", "sgst": "9.00", "igst": "0.00"}]


def test_cancelled_export_writes_nothing(screen, tmp_path):
    screen._ask_save_path = lambda name: None
    screen.export_sales()
    # tmp_path also holds the app's own data folder (RetailApp); nothing else may appear
    assert [p.name for p in tmp_path.iterdir() if p.name != "RetailApp"] == [] and screen.errors == []


def test_unwritable_export_path_is_reported(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen._ask_save_path = lambda name: str(blocker / "sub" / name)
    screen.export_sales()
    assert len(screen.errors) == 1


def test_exports_stay_available_when_read_only_and_texts_retranslate(screen, tmp_path):
    screen.apply_read_only(True)
    assert screen.export_sales_button.isEnabled() and screen.export_gst_button.isEnabled()
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_sales()
    assert screen.status_label.text()
    en = (screen.tabs.tabText(0), screen.sales_model.headerData(3, Qt.Orientation.Horizontal),
          screen.export_sales_button.text())
    i18n.set_language("te")
    screen.retranslate()
    assert screen.status_label.text() == ""
    assert screen.sales_model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("print.bill_no")
    assert screen.tabs.tabText(0) == i18n.tr("rep.tab_sales")
    assert screen.sales_model.headerData(3, Qt.Orientation.Horizontal) == i18n.tr("bill.customer")
    assert screen.export_sales_button.text() == i18n.tr("rep.export_sales")
    assert (screen.tabs.tabText(0), screen.sales_model.headerData(3, Qt.Orientation.Horizontal),
            screen.export_sales_button.text()) != en
    assert all(a != b for a, b in zip((screen.tabs.tabText(0), screen.sales_model.headerData(3, Qt.Orientation.Horizontal),
               screen.export_sales_button.text()), en))


def test_export_stock_register_csv_round_trip_and_injection(screen, tmp_path):
    conn = screen.session.conn
    soap = items.create_item(conn, name="Soap", sell_price_paise=11800, buy_price_paise=9000, unit="kg")
    items.create_item(conn, name="=HYPERLINK(1)", sell_price_paise=100)
    stock.record(conn, soap, 2_500, "opening")
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_stock()
    rows = _read(tmp_path / "stock_register.csv")
    assert [r["item"] for r in rows] == ["'=HYPERLINK(1)", "Soap"]
    assert rows[1]["on_hand"] == "2.5" and rows[1]["buy_price"] == "90.00" and rows[1]["unit"] == "kg"
    assert "stock_register.csv" in screen.status_label.text() and screen.errors == []


def test_export_party_ledgers_csv(screen, tmp_path):
    seed(screen.session.conn)
    parties.create_party(screen.session.conn, name="@cmd", opening_balance_paise=700)
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_ledger()
    rows = _read(tmp_path / "customer_ledgers.csv")
    assert [r["party"] for r in rows] == ["'@cmd"]
    assert rows[0]["entry"] == "opening" and rows[0]["balance"] == "7.00"


def test_new_exports_enabled_read_only_cancel_and_unwritable(screen, tmp_path):
    screen.apply_read_only(True)
    assert screen.export_stock_button.isEnabled() and screen.export_ledger_button.isEnabled()
    screen._ask_save_path = lambda name: None
    screen.export_stock()
    screen.export_ledger()
    assert [p.name for p in tmp_path.iterdir() if p.name != "RetailApp"] == [] and screen.errors == []
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen._ask_save_path = lambda name: str(blocker / "sub" / name)
    screen.export_stock()
    screen.export_ledger()
    assert len(screen.errors) == 2
    en = (screen.export_stock_button.text(), screen.export_ledger_button.text())
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.export_stock_button.text() == i18n.tr("rep.export_stock") != en[0]
    assert screen.export_ledger_button.text() == i18n.tr("rep.export_customer_ledgers") != en[1]
