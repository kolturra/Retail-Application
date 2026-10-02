import pytest
from PySide6.QtCore import Qt

from retail import i18n
from retail.services import billing, items, parties, stock
from retail_ui.screens.parties import PartiesScreen, PartyDialog, ReceiveDialog


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = PartiesScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def cell(sc, row, col):
    return sc.model.data(sc.model.index(row, col))


def owe(conn, party_id, paise):
    item = items.create_item(conn, name=f"Item{paise}", sell_price_paise=paise)
    stock.record(conn, item, 9000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    billing.add_line(conn, bill_id, item, 1000)
    billing.finalize(conn, bill_id, [("credit", billing.get_bill(conn, bill_id)["bill"]["total_paise"])])


def test_party_dialog_validation(qtbot):
    d = PartyDialog()
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.name_edit.setText(" Ravi ")
    assert d.ok_button.isEnabled()
    d.gstin_edit.setText("36ABCDE1234F1Z5")                  # a GSTIN needs a matching state
    assert not d.ok_button.isEnabled()
    d.state_box.setCurrentIndex(d.state_box.findData("36"))
    assert d.ok_button.isEnabled()
    d.phone_edit.setText(" 98765 ")
    d.type_box.setCurrentIndex(d.type_box.findData("supplier"))
    assert d.values() == {"name": "Ravi", "phone": "98765", "gstin": "36ABCDE1234F1Z5", "state_code": "36",
                          "type": "supplier"}


def test_party_dialog_edit_prefills_and_hides_the_type(qtbot, shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", phone="1", state_code="27")
    row = shop_conn.execute("SELECT * FROM party WHERE id=?", (pid,)).fetchone()
    d = PartyDialog(party=row)
    qtbot.addWidget(d)
    assert d.name_edit.text() == "Ravi" and d.state_box.currentData() == "27" and d.type_box.isHidden()
    assert "type" not in d.values()


@pytest.mark.parametrize("text,ok,paise", [("100", True, 10000), ("₹50.5", True, 5050), ("0", False, None),
                                           ("-1", False, None), ("x", False, None), ("", False, None),
                                           ("१००", False, None), ("1" + "0" * 30, False, None),
                                           ("10000000000.01", False, None), ("10000000000", True, 10**12)])
def test_receive_dialog(qtbot, text, ok, paise):
    d = ReceiveDialog("Ravi", 20000)
    qtbot.addWidget(d)
    assert d.amount_edit.text() == "200.00"                   # prefilled with what is due
    d.amount_edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.amount_paise() == paise and d.mode() == "cash"


def test_customers_tab_shows_balances_and_search(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi", phone="9876500001")
    parties.create_party(conn, name="Sita")
    parties.create_party(conn, name="Wholesale", type="supplier")
    owe(conn, ravi, 5000)
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["Ravi", "Sita"]
    assert cell(screen, 0, 2) == "₹50.00" and cell(screen, 1, 2) == "₹0.00"
    screen.search_edit.setText("98765")
    screen.refresh()
    assert screen.model.rowCount() == 1


def test_suppliers_and_dues_views(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi")
    parties.create_party(conn, name="Sita")
    parties.create_party(conn, name="Wholesale", type="supplier")
    owe(conn, ravi, 5000)
    screen.view_box.setCurrentIndex(screen.view_box.findData("suppliers"))
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["Wholesale"] and cell(screen, 0, 2) == ""
    screen.view_box.setCurrentIndex(screen.view_box.findData("dues"))
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["Ravi"]


def test_add_and_edit_flow(screen):
    conn = screen.session.conn
    screen._ask_party = lambda party: {"name": "Ravi", "phone": "1", "gstin": "", "state_code": "36", "type": "customer"}
    screen.add_party()
    assert screen.model.rowCount() == 1 and parties.list_parties(conn)[0]["state_code"] == "36"
    screen.table.selectRow(0)
    seen = []
    screen._ask_party = lambda party: seen.append(party["name"]) or {
        "name": "Ravi K", "phone": "2", "gstin": "", "state_code": "27"}
    screen.edit_party()
    assert seen == ["Ravi"] and cell(screen, 0, 0) == "Ravi K"
    screen.table.selectRow(0)
    screen._ask_party = lambda party: {"name": " ", "phone": "", "gstin": "", "state_code": ""}
    screen.edit_party()
    assert len(screen.errors) == 1


def test_receive_payment_reduces_the_balance(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi")
    owe(conn, ravi, 5000)
    screen.refresh()
    screen.table.selectRow(0)
    asked = []
    screen._ask_receive = lambda name, due: asked.append((name, due)) or (2000, "upi", "part")
    screen.receive_payment()
    assert asked == [("Ravi", 5000)] and parties.balance(conn, ravi) == 3000 and cell(screen, 0, 2) == "₹30.00"


def test_selection_is_restored_after_refresh(screen):
    conn = screen.session.conn
    parties.create_party(conn, name="Asha")
    ravi = parties.create_party(conn, name="Ravi")
    screen.refresh()
    screen.table.selectRow(1)
    screen.refresh()
    assert screen.model.id_at(screen.table.selectionModel().selectedRows()[0].row()) == ravi


def test_receive_payment_is_not_offered_for_suppliers_or_without_selection(screen):
    screen._ask_receive = lambda name, due: pytest.fail("no dialog expected")
    screen.receive_payment()
    parties.create_party(screen.session.conn, name="Wholesale", type="supplier")
    screen.view_box.setCurrentIndex(screen.view_box.findData("suppliers"))
    screen.refresh()
    screen.table.selectRow(0)
    screen.receive_payment()


def test_read_only_and_language(screen):
    screen.apply_read_only(True)
    assert not any(b.isEnabled() for b in (screen.add_button, screen.edit_button, screen.receive_button))
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.model.headerData(2, Qt.Orientation.Horizontal) == i18n.tr("party.balance")
    assert screen.view_box.itemText(0) == i18n.tr("party.customers")


def test_read_only_blocks_the_actions_themselves(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi")
    owe(conn, ravi, 5000)
    screen.refresh()
    screen.table.selectRow(0)
    for hook in ("_ask_party", "_ask_receive"):
        setattr(screen, hook, lambda *a: pytest.fail("no dialog expected"))
    screen.apply_read_only(True)
    screen.add_party()
    screen.edit_party()
    screen.receive_payment()
    screen.apply_read_only(False)
    assert all(b.isEnabled() for b in (screen.add_button, screen.edit_button, screen.receive_button))
