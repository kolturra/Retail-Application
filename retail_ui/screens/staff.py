from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QTableView, QTabWidget,
                               QVBoxLayout, QWidget)

from retail import clock
from retail.i18n import tr
from retail.services import staff
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets import helpers
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

STAFF_HEADERS = ["common.name", "staff.role", "staff.salary"]
EXPENSE_HEADERS = ["common.date", "exp.category", "exp.staff", "common.note", "common.amount"]
MAX_PAISE = 10 ** 12          # a sanity bound on one salary or expense (Rs 10,000,000,000)


class StaffDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("staff.add"))
        form = QFormLayout(self)
        self.name_edit, self.role_edit, self.salary_edit = QLineEdit(), QLineEdit(), QLineEdit()
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("staff.role"), self.role_edit)
        form.addRow(tr("staff.salary"), self.salary_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.name_edit.textChanged.connect(self._check)
        self.salary_edit.textChanged.connect(self._check)
        self._check()

    def _salary(self):
        text = self.salary_edit.text().strip()
        if not text:
            return 0
        paise = fmt.parse_rupees(text)
        if not 0 <= paise <= MAX_PAISE:
            raise ValueError("Salary out of range")
        return paise

    def _check(self):
        try:
            self._salary()
            self.ok_button.setEnabled(bool(self.name_edit.text().strip()))
        except (ValueError, ArithmeticError):
            self.ok_button.setEnabled(False)

    def values(self):
        return {"name": self.name_edit.text().strip(), "role": self.role_edit.text().strip(),
                "monthly_salary_paise": self._salary()}


class ExpenseDialog(QDialog):
    def __init__(self, staff_rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("exp.add"))
        form = QFormLayout(self)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd-MM-yyyy")
        self.category_box = QComboBox()
        for category in staff.CATEGORIES:
            self.category_box.addItem(tr(f"exp.cat_{category}"), category)
        self.amount_edit, self.note_edit = QLineEdit(), QLineEdit()
        self.staff_box = QComboBox()
        self.staff_box.addItem(tr("exp.no_staff"), None)
        for person in staff_rows:
            self.staff_box.addItem(person["name"], person["id"])
        form.addRow(tr("common.date"), self.date_edit)
        form.addRow(tr("exp.category"), self.category_box)
        form.addRow(tr("common.amount"), self.amount_edit)
        form.addRow(tr("common.note"), self.note_edit)
        form.addRow(tr("exp.staff"), self.staff_box)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.amount_edit.textChanged.connect(self._check)
        self._check()

    def _amount(self):
        paise = fmt.parse_rupees(self.amount_edit.text())
        if not 0 < paise <= MAX_PAISE:
            raise ValueError("Amount out of range")
        return paise

    def _check(self):
        try:
            self._amount()
            self.ok_button.setEnabled(True)
        except (ValueError, ArithmeticError):
            self.ok_button.setEnabled(False)

    def values(self):
        return {"spent_on": self.date_edit.date().toString(Qt.DateFormat.ISODate),
                "category": self.category_box.currentData(),
                "amount_paise": self._amount(),
                "note": self.note_edit.text().strip(), "staff_id": self.staff_box.currentData()}


class StaffScreen(Screen):
    nav_key = "nav.staff"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self._read_only = False
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        staff_page = QWidget()
        sl = QVBoxLayout(staff_page)
        self.staff_model = self.track(RowsModel(STAFF_HEADERS))
        self.staff_table = self._table(self.staff_model)
        sl.addWidget(self.staff_table, 1)
        row = QHBoxLayout()
        self.add_staff_button = self._button("staff.add", self.add_staff, row)
        self.pay_salary_button = self._button("staff.pay", self.pay_salary, row)
        sl.addLayout(row)
        self.tabs.addTab(staff_page, "")

        expense_page = QWidget()
        el = QVBoxLayout(expense_page)
        top = QHBoxLayout()
        today = QDate.currentDate()
        self.from_edit, self.to_edit = QDateEdit(QDate(today.year(), today.month(), 1)), QDateEdit(today)
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd-MM-yyyy")
            edit.dateChanged.connect(lambda _d: self.refresh())
        top.addWidget(self.bind(QLabel(), "common.from"))
        top.addWidget(self.from_edit)
        top.addWidget(self.bind(QLabel(), "common.to"))
        top.addWidget(self.to_edit)
        top.addStretch(1)
        el.addLayout(top)
        self.expense_model = self.track(RowsModel(EXPENSE_HEADERS))
        el.addWidget(self._table(self.expense_model), 1)
        self.total_label = QLabel()
        el.addWidget(self.total_label)
        self.status_label = QLabel()
        el.addWidget(self.status_label)
        row2 = QHBoxLayout()
        self.add_expense_button = self._button("exp.add", self.add_expense, row2)
        el.addLayout(row2)
        self.tabs.addTab(expense_page, "")
        self._tab_titles()

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    def _tab_titles(self):
        self.tabs.setTabText(0, tr("staff.tab_staff"))
        self.tabs.setTabText(1, tr("staff.tab_expenses"))

    def _range(self):
        return (self.from_edit.date().toString(Qt.DateFormat.ISODate),
                self.to_edit.date().toString(Qt.DateFormat.ISODate))

    def retranslate(self):
        super().retranslate()
        self._tab_titles()
        self.status_label.clear()
        self.refresh()

    def _selected_id(self):
        rows = self.staff_table.selectionModel().selectedRows()
        return self.staff_model.id_at(rows[0].row()) if rows else None

    def refresh(self):
        conn = self.session.conn
        selected = self._selected_id()
        people = staff.list_staff(conn)
        ids = [p["id"] for p in people]
        self.staff_model.set_rows([(p["name"], p["role"], fmt.rupees(p["monthly_salary_paise"])) for p in people],
                                  ids=ids, right_cols=(2,))
        if selected in ids:
            self.staff_table.selectRow(ids.index(selected))
        start, end = self._range()
        if start > end:
            self.expense_model.set_rows([])
            self.total_label.setText("")
            self.status_label.setText(tr("rep.bad_range"))
            return
        self.status_label.clear()
        try:
            rows = staff.list_expenses(conn, start, end)
            total = staff.expense_total(conn, start, end)
        except Exception as exc:
            self.expense_model.set_rows([])
            self.total_label.setText("")
            self._show_error(exc)
            return
        self.expense_model.set_rows(
            [(fmt.date_text(r["spent_on"]), tr(f"exp.cat_{r['category']}"), r["staff_name"], r["note"],
              fmt.rupees(r["amount_paise"])) for r in rows], right_cols=(4,))
        self.total_label.setText(f"{tr('exp.total')}: {fmt.rupees(total)}")

    def apply_read_only(self, read_only):
        self._read_only = bool(read_only)
        for button in (self.add_staff_button, self.pay_salary_button, self.add_expense_button):
            button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action):
        if self._read_only:
            return
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def add_staff(self):
        def run():
            v = self._ask_staff()
            if v is not None:
                staff.add_staff(self.session.conn, **v)
        self._guarded(run)

    def pay_salary(self):
        def run():
            staff_id = self._selected_id()
            if staff_id is not None and self._confirm("staff.pay_confirm"):
                staff.pay_salary(self.session.conn, staff_id, clock.today().isoformat())
        self._guarded(run)

    def add_expense(self):
        def run():
            v = self._ask_expense(staff.list_staff(self.session.conn))
            if v is not None:
                staff.add_expense(self.session.conn, **v)
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_staff(self):
        dialog = StaffDialog(self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_expense(self, staff_rows):
        dialog = ExpenseDialog(staff_rows, self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _confirm(self, key):
        return helpers.confirm(self, key)
