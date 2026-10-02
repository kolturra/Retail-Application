import pytest
from PySide6.QtCore import QDate, Qt

from retail import clock, i18n
from retail.services import staff
from retail_ui.screens.staff import ExpenseDialog, StaffDialog, StaffScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = StaffScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._confirm = lambda key: True
    return sc


def cell(model, row, col):
    return model.data(model.index(row, col))


def test_staff_dialog(qtbot):
    d = StaffDialog()
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.name_edit.setText(" Anil ")
    d.role_edit.setText("Cashier")
    d.salary_edit.setText("₹12,000")
    assert d.ok_button.isEnabled()
    assert d.values() == {"name": "Anil", "role": "Cashier", "monthly_salary_paise": 1200000}
    d.salary_edit.setText("abc")
    assert not d.ok_button.isEnabled()
    d.salary_edit.setText("")
    assert d.ok_button.isEnabled() and d.values()["monthly_salary_paise"] == 0


@pytest.mark.parametrize("bad", ["-5", "1e3", "99999999999999999999", "१२"])
def test_staff_dialog_rejects_bad_salary(qtbot, bad):
    d = StaffDialog()
    qtbot.addWidget(d)
    d.name_edit.setText("Anil")
    d.salary_edit.setText(bad)
    assert not d.ok_button.isEnabled()


def test_expense_dialog(qtbot, shop_conn):
    anil = staff.add_staff(shop_conn, name="Anil", monthly_salary_paise=100)
    d = ExpenseDialog(staff.list_staff(shop_conn))
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.amount_edit.setText("2500")
    d.category_box.setCurrentIndex(d.category_box.findData("rent"))
    d.note_edit.setText(" Sept ")
    d.date_edit.setDate(QDate(2026, 9, 5))
    assert d.ok_button.isEnabled() and d.values() == {
        "spent_on": "2026-09-05", "category": "rent", "amount_paise": 250000, "note": "Sept", "staff_id": None}
    d.staff_box.setCurrentIndex(d.staff_box.findData(anil))
    assert d.values()["staff_id"] == anil
    for bad in ("0", "-5", "abc", "99999999999999999999"):
        d.amount_edit.setText(bad)
        assert not d.ok_button.isEnabled()


def test_add_staff_and_list(screen):
    screen._ask_staff = lambda: {"name": "Anil", "role": "Cashier", "monthly_salary_paise": 1200000}
    screen.add_staff()
    assert screen.staff_model.rowCount() == 1
    assert [cell(screen.staff_model, 0, c) for c in range(3)] == ["Anil", "Cashier", "₹12,000.00"]


def test_pay_salary_records_an_expense_once_per_month(screen):
    staff.add_staff(screen.session.conn, name="Anil", monthly_salary_paise=1200000)
    screen.refresh()
    screen.staff_table.selectRow(0)
    screen.pay_salary()
    today = clock.today().isoformat()
    assert staff.expense_total(screen.session.conn, today[:8] + "01", today, category="salary") == 1200000
    assert screen.staff_table.selectionModel().selectedRows()[0].row() == 0     # selection restored
    screen.pay_salary()                                        # the same month again
    assert len(screen.errors) == 1


def test_pay_salary_asks_first_and_needs_a_selection(screen):
    staff.add_staff(screen.session.conn, name="Anil", monthly_salary_paise=100)
    screen.refresh()
    screen._confirm = lambda key: pytest.fail("nothing is selected")
    screen.pay_salary()
    screen.staff_table.selectRow(0)
    screen._confirm = lambda key: False
    screen.pay_salary()
    today = clock.today().isoformat()
    assert staff.expense_total(screen.session.conn, today[:8] + "01", today) == 0


def test_add_expense_updates_the_list_and_total(screen):
    today = clock.today().isoformat()
    screen._ask_expense = lambda staff_rows: {"spent_on": today, "category": "rent", "amount_paise": 1500000,
                                              "note": "Shop rent", "staff_id": None}
    screen.add_expense()
    assert screen.expense_model.rowCount() == 1
    assert [cell(screen.expense_model, 0, c) for c in (1, 3, 4)] == [i18n.tr("exp.cat_rent"), "Shop rent", "₹15,000.00"]
    assert "₹15,000.00" in screen.total_label.text()


def test_expense_category_is_translated(screen):
    staff.add_expense(screen.session.conn, spent_on=clock.today().isoformat(), category="rent", amount_paise=100)
    i18n.set_language("hi")
    screen.retranslate()
    assert cell(screen.expense_model, 0, 1) == i18n.tr("exp.cat_rent") != "Rent"


def test_invalid_expense_is_reported_not_raised(screen):
    screen._ask_expense = lambda staff_rows: {"spent_on": "2026-09-05", "category": "party", "amount_paise": 1,
                                              "note": "", "staff_id": None}
    screen.add_expense()
    assert len(screen.errors) == 1 and screen.expense_model.rowCount() == 0


def test_expense_range_filters_and_bad_range_shows_status(screen):
    staff.add_expense(screen.session.conn, spent_on="2020-01-10", category="rent", amount_paise=100)
    screen.from_edit.setDate(QDate(2020, 1, 1))
    screen.to_edit.setDate(QDate(2020, 1, 31))
    assert screen.expense_model.rowCount() == 1
    assert screen.status_label.text() == ""
    screen.to_edit.setDate(QDate(2019, 1, 1))
    assert screen.errors == []
    assert screen.status_label.text() == i18n.tr("rep.bad_range")
    assert screen.expense_model.rowCount() == 0 and screen.total_label.text() == ""
    screen.to_edit.setDate(QDate(2020, 2, 1))
    assert screen.status_label.text() == "" and screen.expense_model.rowCount() == 1


def test_read_only_blocks_buttons_and_handlers(screen):
    staff.add_staff(screen.session.conn, name="Anil", monthly_salary_paise=100)
    screen.refresh()
    screen.staff_table.selectRow(0)
    screen.apply_read_only(True)
    assert not any(b.isEnabled() for b in (screen.add_staff_button, screen.pay_salary_button, screen.add_expense_button))
    screen._ask_staff = lambda: pytest.fail("blocked")
    screen._ask_expense = lambda rows: pytest.fail("blocked")
    screen._confirm = lambda key: pytest.fail("blocked")
    screen.add_staff()
    screen.pay_salary()
    screen.add_expense()
    assert screen.staff_model.rowCount() == 1 and screen.expense_model.rowCount() == 0
    screen.apply_read_only(False)
    assert screen.add_staff_button.isEnabled()


def test_language(screen):
    en_role, en_tab = i18n.tr("staff.role"), i18n.tr("staff.tab_expenses")
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.staff_model.headerData(1, Qt.Orientation.Horizontal) == i18n.tr("staff.role") != en_role
    assert screen.tabs.tabText(1) == i18n.tr("staff.tab_expenses") != en_tab
