from datetime import date
from decimal import InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableView,
                               QTabWidget, QVBoxLayout, QWidget)

from retail import money
from retail.i18n import tr
from retail.services import items, parties, purchases, stock
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import error_label, ok_cancel
from retail_ui.widgets.pickers import ItemPicker

STOCK_HEADERS = ["common.name", "items.on_hand", "items.reorder", "stock.status"]
PURCHASE_HEADERS = ["common.date", "pur.invoice", "pur.supplier", "bill.total"]
LINE_HEADERS = ["bill.item", "bill.qty", "pur.cost", "bill.total"]


class AdjustDialog(QDialog):
    def __init__(self, item_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("stock.adjust"))
        form = QFormLayout(self)
        form.addRow(QLabel(item_name))
        self.qty_edit = QLineEdit()
        self.reason_edit = QLineEdit()
        form.addRow(tr("stock.adjust_qty"), self.qty_edit)
        form.addRow(tr("stock.reason"), self.reason_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.qty_edit.textChanged.connect(self._check)
        self.reason_edit.textChanged.connect(self._check)
        self._check()

    def _qty(self):
        try:
            milli = money.qty_to_milli(self.qty_edit.text().strip())
        except InvalidOperation as exc:
            raise ValueError("not a quantity") from exc
        if milli == 0:
            raise ValueError("zero")
        return milli

    def _check(self):
        try:
            self._qty()
            self.ok_button.setEnabled(bool(self.reason()))
        except ValueError:
            self.ok_button.setEnabled(False)

    def qty_milli(self):
        return self._qty()

    def reason(self):
        return self.reason_edit.text().strip()


class PurchaseDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._lines = []
        self.setWindowTitle(tr("pur.new"))
        self.setMinimumWidth(640)
        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.supplier_box = QComboBox()
        self.new_supplier_edit = QLineEdit()
        self.new_supplier_edit.setPlaceholderText(tr("pur.new_supplier"))
        self.add_supplier_button = QPushButton(tr("common.add"))
        supplier_row = QHBoxLayout()
        for w in (self.supplier_box, self.new_supplier_edit, self.add_supplier_button):
            supplier_row.addWidget(w)
        form.addRow(tr("pur.supplier"), supplier_row)
        self.invoice_edit = QLineEdit()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(tr("pur.invoice"), self.invoice_edit)
        form.addRow(tr("common.date"), self.date_edit)
        outer.addLayout(form)

        self.picker = ItemPicker(lambda: self.session.conn)
        outer.addWidget(self.picker)
        entry = QFormLayout()
        self.qty_edit = QLineEdit()
        self.cost_edit = QLineEdit()
        self.serials_edit = QPlainTextEdit()
        self.serials_edit.setFixedHeight(60)
        self.batch_edit = QLineEdit()
        self.expiry_edit = QLineEdit()
        self._qty_label = QLabel(tr("bill.qty"))
        entry.addRow(self._qty_label, self.qty_edit)
        entry.addRow(tr("pur.cost"), self.cost_edit)
        self._serials_label = QLabel(tr("pur.serials"))
        entry.addRow(self._serials_label, self.serials_edit)
        self._batch_label, self._expiry_label = QLabel(tr("pur.batch")), QLabel(tr("pur.expiry"))
        entry.addRow(self._batch_label, self.batch_edit)
        entry.addRow(self._expiry_label, self.expiry_edit)
        outer.addLayout(entry)
        self.add_line_button = QPushButton(tr("pur.add_line"))
        self.error_label = error_label()
        outer.addWidget(self.add_line_button)
        outer.addWidget(self.error_label)

        self.purchase_model = RowsModel(LINE_HEADERS)
        table = QTableView()
        table.setModel(self.purchase_model)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(table)
        box, self.ok_button = ok_cancel(self)
        outer.addWidget(box)
        self.ok_button.setEnabled(False)

        self._reload_suppliers()
        self.add_supplier_button.clicked.connect(self._add_supplier)
        self.add_line_button.clicked.connect(lambda _=False: self.add_line())
        self.picker.selection_changed.connect(self._update_fields)
        self._update_fields()

    def _reload_suppliers(self, select=None):
        self.supplier_box.clear()
        self.supplier_box.addItem(tr("pur.no_supplier"), None)
        for p in parties.list_parties(self.session.conn, kind="supplier"):
            self.supplier_box.addItem(p["name"], p["id"])
        if select is not None:
            self.supplier_box.setCurrentIndex(self.supplier_box.findData(select))

    def _add_supplier(self):
        try:
            new_id = parties.create_party(self.session.conn, name=self.new_supplier_edit.text(), type="supplier")
        except Exception as exc:
            show_error(self, exc)
            return
        self.new_supplier_edit.clear()
        self._reload_suppliers(select=new_id)

    def _update_fields(self):
        item = self.picker.selected_item()
        tracking = item["tracking"] if item else "none"
        serial, batch = tracking == "serial", tracking == "batch"
        for widget in (self.qty_edit, self._qty_label):
            widget.setHidden(serial)
        for widget in (self.serials_edit, self._serials_label):
            widget.setHidden(not serial)
        for widget in (self.batch_edit, self._batch_label, self.expiry_edit, self._expiry_label):
            widget.setHidden(not batch)

    def add_line(self):
        item = self.picker.selected_item()
        try:
            if item is None:
                raise ValueError("no item")
            cost = fmt.parse_rupees(self.cost_edit.text())
            tracking = item["tracking"]
            if tracking == "serial":
                serials = tuple(s.strip() for s in self.serials_edit.toPlainText().splitlines() if s.strip())
                if not serials:
                    raise ValueError("no serials")
                line = purchases.PurchaseLine(item["id"], 1000 * len(serials), cost, serials=serials)
            elif tracking == "batch":
                batch = self.batch_edit.text().strip()
                if not batch:
                    raise ValueError("no batch")
                expiry = self.expiry_edit.text().strip() or None
                if expiry is not None:
                    date.fromisoformat(expiry)
                line = purchases.PurchaseLine(item["id"], fmt.parse_qty(self.qty_edit.text()), cost,
                                              batch_no=batch, expiry=expiry)
            else:
                line = purchases.PurchaseLine(item["id"], fmt.parse_qty(self.qty_edit.text()), cost)
        except ValueError:
            self.error_label.setText(tr("err.invalid_input"))
            return False
        self.error_label.setText("")
        self._lines.append((line, item["name"]))
        for edit in (self.qty_edit, self.cost_edit, self.batch_edit, self.expiry_edit):
            edit.clear()
        self.serials_edit.clear()
        self.purchase_model.set_rows(
            [(name, fmt.qty(l.qty_milli), fmt.rupees(l.cost_paise),
              fmt.rupees(money.line_amount(l.cost_paise, l.qty_milli))) for l, name in self._lines],
            right_cols=(1, 2, 3))
        self.ok_button.setEnabled(True)
        return True

    def supplier_id(self):
        return self.supplier_box.currentData()

    def invoice_no(self):
        return self.invoice_edit.text().strip() or None

    def date_iso(self):
        return self.date_edit.date().toString(Qt.DateFormat.ISODate)

    def lines(self):
        return [line for line, _name in self._lines]


class StockScreen(Screen):
    nav_key = "nav.stock"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        stock_page = QWidget()
        sl = QVBoxLayout(stock_page)
        self.low_label = QLabel()
        sl.addWidget(self.low_label)
        self.stock_model = self.track(RowsModel(STOCK_HEADERS))
        self.stock_table = self._table(self.stock_model)
        sl.addWidget(self.stock_table, 1)
        self.adjust_button = self.bind(QPushButton(), "stock.adjust")
        self.adjust_button.clicked.connect(lambda _=False: self.adjust_stock())
        sl.addWidget(self.adjust_button)
        self.tabs.addTab(stock_page, "")

        purchase_page = QWidget()
        pl = QVBoxLayout(purchase_page)
        self.purchase_model = self.track(RowsModel(PURCHASE_HEADERS))
        pl.addWidget(self._table(self.purchase_model), 1)
        self.new_purchase_button = self.bind(QPushButton(), "pur.new")
        self.new_purchase_button.clicked.connect(lambda _=False: self.new_purchase())
        pl.addWidget(self.new_purchase_button)
        self.tabs.addTab(purchase_page, "")
        self._tab_titles()

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    def _tab_titles(self):
        self.tabs.setTabText(0, tr("stock.tab_stock"))
        self.tabs.setTabText(1, tr("stock.tab_purchases"))

    def retranslate(self):
        super().retranslate()
        self._tab_titles()
        self.refresh()

    def refresh(self):
        conn = self.session.conn
        selected = self._selected_item_id()
        rows, ids, low = [], [], []
        for i, r in enumerate(items.list_items(conn, limit=20000)):
            unit = f" {r['unit']}" if r["tracking"] == "weighed" else ""
            is_low = bool(r["reorder_milli"]) and r["on_hand_milli"] <= r["reorder_milli"]
            rows.append((r["name"], fmt.qty(r["on_hand_milli"]) + unit,
                         (fmt.qty(r["reorder_milli"]) + unit) if r["reorder_milli"] else "",
                         tr("stock.status_low") if is_low else tr("stock.status_ok")))
            ids.append(r["id"])
            if is_low:
                low.append(i)
        self.stock_model.set_rows(rows, ids, right_cols=(1, 2), highlight=low)
        if selected in ids:
            self.stock_table.selectRow(ids.index(selected))
        self.low_label.setText(tr("stock.low", count=len(low)) if low else "")
        self.purchase_model.set_rows(
            [(fmt.date_text(p["purchase_date"]), p["invoice_no"] or "", p["supplier"], fmt.rupees(p["total_paise"]))
             for p in purchases.list_purchases(conn)], right_cols=(3,))

    def _selected_item_id(self):
        rows = self.stock_table.selectionModel().selectedRows()
        return self.stock_model.id_at(rows[0].row()) if rows else None

    def apply_read_only(self, read_only):
        self.adjust_button.setEnabled(not read_only)
        self.new_purchase_button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def adjust_stock(self):
        def run():
            item_id = self._selected_item_id()
            if item_id is None:
                return
            answer = self._ask_adjust(items.get_item(self.session.conn, item_id))
            if answer is not None:
                stock.adjust_stock(self.session.conn, item_id, *answer)
        self._guarded(run)

    def new_purchase(self):
        def run():
            answer = self._ask_purchase()
            if answer is not None:
                purchases.create_purchase(self.session.conn, **answer)
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_adjust(self, item):
        dialog = AdjustDialog(item["name"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.qty_milli(), dialog.reason()

    def _ask_purchase(self):
        dialog = PurchaseDialog(self.session, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {"party_id": dialog.supplier_id(), "invoice_no": dialog.invoice_no(),
                "date_iso": dialog.date_iso(), "lines": dialog.lines()}
