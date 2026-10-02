import pytest
from PySide6.QtCore import Qt

from retail import i18n
from retail.services import billing, items, parties, stock
from retail_ui import print_ui
from retail_ui.screens import bills
from retail_ui.screens.bills import BillsScreen, ReturnDialog


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def sell(conn, qty=2000, party_id=None, name="Soap"):
    item = items.create_item(conn, name=name, sell_price_paise=1000)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    line_id = billing.add_line(conn, bill_id, item, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, [("cash", total)])
    return bill_id, line_id


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = BillsScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def cell(sc, row, col):
    return sc.model.data(sc.model.index(row, col))


def test_lists_todays_final_bills_newest_first(screen):
    a, _ = sell(screen.session.conn, name="A")
    b, _ = sell(screen.session.conn, name="B")
    billing.start_bill(screen.session.conn)                      # held: never listed
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["S000002", "S000001"]
    assert cell(screen, 0, 2) == i18n.tr("bills.sale") and cell(screen, 0, 4) == "₹20.00"
    assert a and b


def test_search_filters_by_number_or_customer(screen):
    ravi = parties.create_party(screen.session.conn, name="Ravi")
    sell(screen.session.conn, party_id=ravi, name="A")
    sell(screen.session.conn, name="B")
    screen.search_edit.setText("ravi")
    screen.refresh()
    assert screen.model.rowCount() == 1 and cell(screen, 0, 3) == "Ravi"
    screen.search_edit.setText("s000002")
    screen.refresh()
    assert cell(screen, 0, 0) == "S000002" and cell(screen, 0, 3) == i18n.tr("counter.walk_in_label")


def test_a_bad_date_range_is_reported_not_raised(screen):
    from PySide6.QtCore import QDate
    screen.from_edit.setDate(QDate(2030, 1, 1))
    screen.to_edit.setDate(QDate(2020, 1, 1))
    screen.refresh()
    assert len(screen.errors) == 1 and screen.model.rowCount() == 0


def test_print_pdf_and_whatsapp_actions_use_the_selected_bill(screen, monkeypatch):
    bill_id, _ = sell(screen.session.conn)
    screen.refresh()
    screen.table.selectRow(0)
    calls = []
    monkeypatch.setattr(bills.print_ui, "preview_bill", lambda parent, session, bid: calls.append(("print", bid)))
    monkeypatch.setattr(bills.print_ui, "save_pdf", lambda parent, session, bid, path=None: calls.append(("pdf", bid)))
    monkeypatch.setattr(bills.print_ui, "send_whatsapp", lambda parent, session, bid, **k: calls.append(("wa", bid)))
    screen.preview()
    screen.save_pdf()
    screen.send_whatsapp()
    assert calls == [("print", bill_id), ("pdf", bill_id), ("wa", bill_id)]


def test_actions_do_nothing_without_a_selection(screen, monkeypatch):
    monkeypatch.setattr(bills.print_ui, "preview_bill", lambda *a, **k: pytest.fail("no bill selected"))
    screen.preview()
    screen._ask_return = lambda lines, has_customer: pytest.fail("no bill selected")
    screen.return_items()


def test_return_flow_creates_a_return_and_refreshes(screen):
    bill_id, line_id = sell(screen.session.conn, qty=3000)
    screen.refresh()
    screen.table.selectRow(0)
    asked = []
    screen._ask_return = lambda lines, has_customer: asked.append((lines, has_customer)) or ([(line_id, 1000)], "cash")
    screen.return_items()
    assert asked[0][0][0]["remaining_milli"] == 3000 and asked[0][1] is False
    assert screen.model.rowCount() == 2 and cell(screen, 0, 2) == i18n.tr("bills.return")
    assert stock.on_hand(screen.session.conn, items.list_items(screen.session.conn)[0]["id"]) == 48_000


def test_returning_a_return_bill_is_reported(screen):
    bill_id, line_id = sell(screen.session.conn)
    billing.create_return(screen.session.conn, bill_id, [(line_id, 1000)])
    screen.refresh()
    screen.table.selectRow(0)                                     # the newest row is the return
    screen._ask_return = lambda *a: pytest.fail("a return bill cannot be returned")
    screen.return_items()
    assert len(screen.errors) == 1


def test_read_only_disables_returns_but_not_printing(screen):
    screen.apply_read_only(True)
    assert not screen.return_button.isEnabled()
    assert screen.preview_button.isEnabled() and screen.pdf_button.isEnabled() and screen.whatsapp_button.isEnabled()


def test_language_switch_retranslates_headers(screen):
    i18n.set_language("te")
    screen.retranslate()
    assert screen.model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("print.bill_no")


# ---- the return dialog ---------------------------------------------------------

def lines(*specs):
    return [{"line_id": i + 1, "item_id": i + 1, "item_name": n, "tracking": t, "qty_milli": q,
             "returned_milli": r, "remaining_milli": q - r, "total_paise": 100} for i, (n, t, q, r) in enumerate(specs)]


def test_return_dialog_collects_quantities_and_validates(qtbot):
    d = ReturnDialog(lines(("Soap", "none", 3000, 0), ("Phone", "serial", 1000, 0), ("Tea", "none", 1000, 1000)),
                     has_customer=False)
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled() and d.returns() == []
    d.rows[1].setText("2")
    assert d.returns() == [(1, 2000)] and d.ok_button.isEnabled()
    d.rows[1].setText("4")                                        # more than was sold
    assert not d.ok_button.isEnabled()
    d.rows[1].setText("abc")
    assert not d.ok_button.isEnabled()
    d.rows[1].setText("")
    d.rows[2].setChecked(True)                                    # serial units are returned whole
    assert d.returns() == [(2, 1000)] and d.ok_button.isEnabled()
    assert 3 not in d.rows                                        # nothing left to return on the Tea line


def test_return_dialog_refund_modes(qtbot):
    plain = ReturnDialog(lines(("Soap", "none", 1000, 0)), has_customer=False)
    qtbot.addWidget(plain)
    assert [plain.refund_box.itemData(i) for i in range(plain.refund_box.count())] == ["cash", "upi", "card"]
    with_customer = ReturnDialog(lines(("Soap", "none", 1000, 0)), has_customer=True)
    qtbot.addWidget(with_customer)
    assert "credit" in [with_customer.refund_box.itemData(i) for i in range(with_customer.refund_box.count())]


# ---- print_ui ---------------------------------------------------------------------

def test_save_pdf_writes_a_pdf_to_the_given_path(make_session, qtbot, tmp_path):
    session = make_session()
    bill_id, _ = sell(session.conn)
    path = print_ui.save_pdf(None, session, bill_id, path=tmp_path / "b.pdf")
    assert path.read_bytes().startswith(b"%PDF")


def test_send_whatsapp_prefers_the_customer_phone(make_session, qtbot):
    session = make_session()
    ravi = parties.create_party(session.conn, name="Ravi", phone="98765 43210")
    bill_id, _ = sell(session.conn, party_id=ravi)
    opened = []
    assert print_ui.send_whatsapp(None, session, bill_id, opener=opened.append) is True
    assert opened[0].startswith("https://wa.me/919876543210?text=")


def test_print_layout_setting_overrides_the_template(make_session, qtbot, tmp_path):
    session = make_session()
    session.settings.print_layout = "thermal_58"
    bill_id, _ = sell(session.conn)
    assert print_ui.layout_for(session) == "thermal_58"
    session.settings.print_layout = ""
    assert print_ui.layout_for(session) is None


def test_save_pdf_raises_oserror_when_nothing_was_written(make_session, qtbot, tmp_path):
    session = make_session()
    bill_id, _ = sell(session.conn)
    with pytest.raises(OSError):
        print_ui.save_pdf(None, session, bill_id, path=tmp_path / "missing_dir" / "b.pdf")
