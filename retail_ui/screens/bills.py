from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableView,
                               QVBoxLayout)

from retail.i18n import tr
from retail.services import billing
from retail_ui import fmt, print_ui
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

HEADERS = ["print.bill_no", "common.date", "bills.type", "bill.customer", "bill.total"]


class ReturnDialog(QDialog):
    """One row per original line still holding something to return. Serial units are returned whole."""

    def __init__(self, lines, has_customer, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("bills.return_items"))
        self._lines = {l["line_id"]: l for l in lines if l["remaining_milli"] > 0}
        self.rows = {}
        form = QFormLayout(self)
        for line_id, line in self._lines.items():
            label = (f"{line['item_name']}  ({tr('bills.remaining')}: {fmt.qty(line['remaining_milli'])})")
            if line["tracking"] == "serial":
                widget = QCheckBox()
                widget.toggled.connect(self._check)
            else:
                widget = QLineEdit()
                widget.textChanged.connect(self._check)
            self.rows[line_id] = widget
            form.addRow(label, widget)
        self.refund_box = QComboBox()
        for mode in ("cash", "upi", "card") + (("credit",) if has_customer else ()):
            self.refund_box.addItem(tr(f"pay.{mode}"), mode)
        form.addRow(tr("bills.refund_mode"), self.refund_box)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self._check()

    def _collect(self):
        """[(line_id, qty_milli)] or raises ValueError when any entry is invalid."""
        found = []
        for line_id, widget in self.rows.items():
            line = self._lines[line_id]
            if isinstance(widget, QCheckBox):
                qty = line["remaining_milli"] if widget.isChecked() else 0
            else:
                text = widget.text().strip()
                qty = fmt.parse_qty(text) if text else 0
            if qty > line["remaining_milli"]:
                raise ValueError("more than is left to return")
            if qty:
                found.append((line_id, qty))
        return found

    def _check(self):
        try:
            self.ok_button.setEnabled(bool(self._collect()))
        except ValueError:
            self.ok_button.setEnabled(False)

    def returns(self):
        try:
            return self._collect()
        except ValueError:
            return []

    def refund_mode(self):
        return self.refund_box.currentData()


class BillsScreen(Screen):
    nav_key = "nav.bills"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        today = QDate.currentDate()
        self.from_edit, self.to_edit = QDateEdit(today), QDateEdit(today)
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd-MM-yyyy")
        self.search_edit = QLineEdit()
        self.bind(self.search_edit, "common.search", "setPlaceholderText")
        self.refresh_button = self.bind(QPushButton(), "common.refresh")
        top.addWidget(self.bind(QLabel(), "common.from"))
        top.addWidget(self.from_edit)
        top.addWidget(self.bind(QLabel(), "common.to"))
        top.addWidget(self.to_edit)
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)

        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.preview_button = self._button("bills.print", self.preview, buttons)
        self.pdf_button = self._button("bills.pdf", self.save_pdf, buttons)
        self.whatsapp_button = self._button("bills.whatsapp", self.send_whatsapp, buttons)
        self.return_button = self._button("bills.return_items", self.return_items, buttons)
        layout.addLayout(buttons)

        self.refresh_button.clicked.connect(lambda _=False: self.refresh())
        self.search_edit.returnPressed.connect(self.refresh)

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    # --- Screen protocol ------------------------------------------------------
    def refresh(self):
        try:
            rows = billing.list_bills(self.session.conn, self.from_edit.date().toString(Qt.DateFormat.ISODate),
                                      self.to_edit.date().toString(Qt.DateFormat.ISODate),
                                      search=self.search_edit.text())
        except Exception as exc:
            self.model.set_rows([])
            self._show_error(exc)
            return
        self.model.set_rows(
            [(r["bill_no"], fmt.date_text(r["finalized_at"]),
              tr("bills.return") if r["kind"] == "sale_return" else tr("bills.sale"),
              r["party"] or tr("counter.walk_in_label"), fmt.rupees(r["total_paise"])) for r in rows],
            ids=[r["id"] for r in rows], right_cols=(4,))

    def retranslate(self):
        super().retranslate()
        self.refresh()

    def apply_read_only(self, read_only):
        self.return_button.setEnabled(not read_only)   # printing and sending stay available

    # --- actions ------------------------------------------------------------------
    def _selected_bill_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.id_at(rows[0].row()) if rows else None

    def _run(self, action):
        bill_id = self._selected_bill_id()
        if bill_id is None:
            return
        try:
            action(bill_id)
        except Exception as exc:
            self._show_error(exc)

    def preview(self):
        self._run(lambda bill_id: print_ui.preview_bill(self, self.session, bill_id))

    def save_pdf(self):
        self._run(lambda bill_id: print_ui.save_pdf(self, self.session, bill_id))

    def send_whatsapp(self):
        self._run(lambda bill_id: print_ui.send_whatsapp(self, self.session, bill_id))

    def return_items(self):
        def run(bill_id):
            detail = billing.get_bill_detail(self.session.conn, bill_id)
            lines = billing.returnable_lines(self.session.conn, bill_id)   # raises for a return bill
            answer = self._ask_return(lines, detail["bill"]["party_id"] is not None)
            if answer is None:
                return
            returns, mode = answer
            billing.create_return(self.session.conn, bill_id, returns, refund_mode=mode)
            self.session.notify_changed()
            self.refresh()
        self._run(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_return(self, lines, has_customer):
        dialog = ReturnDialog(lines, has_customer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.returns():
            return None
        return dialog.returns(), dialog.refund_mode()
