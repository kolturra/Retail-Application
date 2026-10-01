from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableView, QVBoxLayout)

from retail import segments
from retail.i18n import tr
from retail.services import billing, items
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.screens import counter_dialogs as dialogs
from retail_ui.screens.counter_logic import CounterController
from retail_ui.widgets.base import RowsModel, Screen

HEADERS = ["bill.item", "bill.qty", "bill.rate", "bill.discount", "counter.gst", "bill.total"]


class CounterScreen(Screen):
    nav_key = "nav.counter"
    sale_completed = Signal(int)

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.controller = CounterController(session)
        self.last_bill_id = None
        layout = QVBoxLayout(self)

        self.entry = QLineEdit()
        self.entry.setStyleSheet("font-size: 18px; padding: 6px;")
        self.entry.returnPressed.connect(self._on_enter)
        layout.addWidget(self.entry)
        self.customer_label = QLabel()
        layout.addWidget(self.customer_label)

        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.tax_label = QLabel()
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label = QLabel()
        layout.addWidget(self.tax_label)
        layout.addWidget(self.total_label)

        row = QHBoxLayout()
        self.customer_button = self._button("counter.customer", " (F2)", self.pick_customer, row)
        self.discount_button = self._button("counter.discount", " (F5)", self.apply_discount, row)
        self.hold_button = self._button("counter.hold", " (F3)", self.hold_bill, row)
        self.held_button = self._button("counter.held", " (F4)", self.show_held, row)
        self.discard_button = self._button("counter.discard", " (F8)", self.discard_bill, row)
        self.delete_button = self._button("counter.delete_line", " (F6)", self.delete_selected_line, row)
        self.pay_button = self._button("counter.pay", " (F12)", self.pay, row)
        self.pay_button.setStyleSheet("font-weight: bold; padding: 8px 18px;")
        layout.addLayout(row)
        layout.addWidget(self.status_label)

        self.shortcut_keys = {}
        for key, handler in (("F2", self.pick_customer), ("F3", self.hold_bill), ("F4", self.show_held),
                             ("F5", self.apply_discount), ("F6", self.delete_selected_line),
                             ("F8", self.discard_bill), ("Del", self.delete_selected_line), ("F12", self.pay)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
            self.shortcut_keys[key] = shortcut

        self.bind(self.entry, "counter.entry_hint", "setPlaceholderText")
        self.retranslate()

    def _button(self, key, suffix, handler, row):
        button = QPushButton()
        self.bind(button, key, suffix=suffix)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    # --- Screen protocol ------------------------------------------------------
    def retranslate(self):
        super().retranslate()
        self._render()

    def refresh(self):
        self._drop_stale_bill()
        self._render()
        self.entry.setFocus()

    def _drop_stale_bill(self):
        """After a restore the remembered bill may not exist (or no longer be a held sale)."""
        bill_id = self.controller.bill_id
        if bill_id is None:
            return
        try:
            bill = billing.get_bill_detail(self.session.conn, bill_id)["bill"]
            valid = bill["status"] == "held" and bill["kind"] == "sale"
        except billing.BillingError:
            valid = False
        if not valid:
            self.controller.bill_id = None

    def apply_read_only(self, read_only):
        for widget in (self.entry, self.customer_button, self.discount_button, self.hold_button,
                       self.held_button, self.discard_button, self.delete_button, self.pay_button):
            widget.setEnabled(not read_only)
        for shortcut in self.shortcut_keys.values():      # none is read-only safe today
            shortcut.setEnabled(not read_only)

    # --- input -----------------------------------------------------------------
    def _on_enter(self):
        text = self.entry.text()
        self.entry.clear()
        self.submit_text(text)

    def submit_text(self, text):
        try:
            self._handle(self.controller.submit(text))
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._render()
            self.entry.setFocus()

    def _handle(self, entry):
        kind = entry.kind
        if kind == "pick":
            item_id = self._ask_pick(entry.items)
            if item_id is not None:
                item = next(i for i in entry.items if i["id"] == item_id)
                self._handle(self.controller.add(item, entry.qty_milli, explicit_qty=entry.explicit_qty))
        elif kind == "weight":
            qty = self._ask_qty(entry.item)
            if qty is not None:
                self._handle(self.controller.add(entry.item, qty, explicit_qty=True))
        elif kind == "serial":
            serial = (self._ask_serial(entry.item) or "").strip()
            if serial:
                self._handle(self.controller.add(entry.item, 1000, serial=serial))
        elif kind == "new_item":
            values = self._ask_new_item(entry.text)
            if values is not None:
                item = items.get_item(self.session.conn, items.create_item(self.session.conn, **values))
                self._handle(self.controller.add(item, entry.qty_milli, explicit_qty=entry.explicit_qty))

    # --- actions ----------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._render()
            self.entry.setFocus()

    def _selected_line_id(self):
        rows = self.table.selectionModel().selectedRows()
        index = rows[0] if rows else self.table.currentIndex()
        return self.model.id_at(index.row()) if index.isValid() else None

    def pick_customer(self):
        def run():
            answer = self._ask_customer()
            if answer is None:
                return
            action, party_id = answer
            self.controller.set_customer(party_id if action == "set" else None)
        self._guarded(run)

    def apply_discount(self):
        def run():
            line_id = self._selected_line_id()
            if line_id is None:
                return
            line = next(l for l in self.controller.detail()["lines"] if l["id"] == line_id)
            max_paise = (line["rate_paise"] * line["qty_milli"] + 500) // 1000  # the undiscounted amount
            paise = self._ask_discount(max_paise)
            if paise is not None:
                self.controller.set_discount(line_id, paise)
        self._guarded(run)

    def delete_selected_line(self):
        def run():
            line_id = self._selected_line_id()
            if line_id is not None:
                self.controller.remove_line(line_id)
        self._guarded(run)

    def hold_bill(self):
        self._guarded(self.controller.hold)

    def show_held(self):
        def run():
            answer = self._ask_held(self.controller.held_bills())
            if answer is None:
                return
            action, bill_id = answer
            if action == "resume":
                self.controller.resume(bill_id)
            elif action == "discard":
                billing.cancel_held(self.session.conn, bill_id)
        self._guarded(run)

    def discard_bill(self):
        def run():
            if self.controller.bill_id is not None and self._confirm("counter.discard_confirm"):
                self.controller.discard()
        self._guarded(run)

    def pay(self):
        def run():
            detail = self.controller.detail()
            if not detail or not detail["lines"]:
                return
            total = detail["bill"]["total_paise"]
            party_id = detail["bill"]["party_id"]
            payments = self._ask_payments(total, party_id)
            if payments is None:
                return
            bill_id, bill_no = self.controller.pay(payments)
            self.last_bill_id = bill_id
            self.status_label.setText(tr("counter.saved", bill_no=bill_no))
            self.sale_completed.emit(bill_id)
        self._guarded(run)

    # --- drawing -----------------------------------------------------------------
    def _render(self):
        detail = self.controller.detail()
        if not detail:
            self.model.set_rows([])
            self.total_label.setText(fmt.rupees(0))
            self.tax_label.setText("")
            self.customer_label.setText(tr("counter.walk_in_label"))
            return
        rows, ids = [], []
        for line in detail["lines"]:
            name = line["item_name"] + (f"  [{line['serial']}]" if line["serial"] else "")
            qty = fmt.qty(line["qty_milli"]) + (f" {line['unit']}" if line["tracking"] == "weighed" else "")
            rows.append((name, qty, fmt.rupees(line["rate_paise"]),
                         fmt.rupees(line["discount_paise"]) if line["discount_paise"] else "",
                         f"{line['gst_rate_bp'] / 100:g}%" if detail["bill"]["gst_mode"] == "gst" else "",
                         fmt.rupees(line["total_paise"])))
            ids.append(line["id"])
        self.model.set_rows(rows, ids, right_cols=(1, 2, 3, 4, 5))
        if rows:
            self.table.selectRow(len(rows) - 1)
        bill = detail["bill"]
        self.total_label.setText(fmt.rupees(bill["total_paise"]))
        parts = []
        if bill["gst_mode"] == "gst":
            for key, column in (("tax.cgst", "cgst_paise"), ("tax.sgst", "sgst_paise"), ("tax.igst", "igst_paise")):
                if bill[column]:
                    parts.append(f"{tr(key)} {fmt.rupees(bill[column])}")
        if bill["round_off_paise"]:
            parts.append(f"{tr('bill.round_off')} {fmt.rupees(bill['round_off_paise'])}")
        self.tax_label.setText("    ".join(parts))
        party = detail["party"]
        self.customer_label.setText(tr("counter.customer_set", name=party["name"]) if party
                                    else tr("counter.walk_in_label"))

    # --- prompts (replaced by tests; each returns None when the user cancels) ------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_pick(self, rows):
        dialog = dialogs.PickItemDialog(rows, self)
        return dialog.selected_item_id() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_qty(self, item):
        dialog = dialogs.QtyDialog(item["name"], self)
        return dialog.qty_milli() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_serial(self, item):
        dialog = dialogs.SerialDialog(item["name"], self)
        return dialog.serial() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_new_item(self, text):
        dialog = dialogs.QuickAddDialog(text, segments.template_settings(self.session.conn), self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_customer(self):
        dialog = dialogs.CustomerDialog(self.session.conn, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return ("clear", None) if dialog.cleared() else (("set", dialog.party_id()) if dialog.party_id() else None)

    def _ask_discount(self, max_paise):
        dialog = dialogs.DiscountDialog(max_paise, self)
        return dialog.discount_paise() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_held(self, rows):
        dialog = dialogs.HeldBillsDialog(rows, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.action() is None:
            return None
        return dialog.action(), dialog.selected_bill_id()

    def _ask_payments(self, total_paise, party_id):
        features = segments.template_settings(self.session.conn).get("features", {})
        dialog = dialogs.PayDialog(total_paise, party_id is not None, features, self)
        return dialog.payments() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _confirm(self, key):
        answer = QMessageBox.question(self, "", tr(key),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes
