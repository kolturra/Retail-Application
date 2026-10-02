from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from retail import clock, money
from retail.i18n import tr
from retail.services import parties
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.helpers import ok_cancel


def _valid(parser, text):
    try:
        parser(text)
        return True
    except ValueError:
        return False


def _non_negative_rupees(text):
    paise = fmt.parse_rupees(text)
    if paise < 0:
        raise ValueError("negative amount")
    return paise


class PickItemDialog(QDialog):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.pick_title"))
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for it in items:
            entry = QListWidgetItem(f"{it['name']}  —  {fmt.rupees(it['sell_price_paise'])}")
            entry.setData(Qt.ItemDataRole.UserRole, it["id"])
            self.list.addItem(entry)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(self.list)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)

    def selected_item_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class QtyDialog(QDialog):
    def __init__(self, item_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.qty_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(item_name))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("dlg.qty_label"))
        layout.addWidget(self.edit)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.ok_button.setEnabled(_valid(fmt.parse_qty, self.edit.text()))

    def qty_milli(self):
        return fmt.parse_qty(self.edit.text())


class SerialDialog(QDialog):
    def __init__(self, item_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.serial_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{item_name}\n{tr('dlg.serial_prompt')}"))
        self.edit = QLineEdit()
        layout.addWidget(self.edit)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.edit.textChanged.connect(lambda: self.ok_button.setEnabled(bool(self.serial())))
        self.ok_button.setEnabled(False)

    def serial(self):
        return self.edit.text().strip()


class QuickAddDialog(QDialog):
    def __init__(self, prefill, template, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.new_item_title"))
        features = template.get("features", {})
        form = QFormLayout(self)
        digits = prefill.isdigit() and len(prefill) >= 6
        self.name_edit = QLineEdit("" if digits else prefill)
        self.barcode_edit = QLineEdit(prefill if digits else "")
        self.price_edit = QLineEdit()
        self.gst_box = QComboBox()
        for bp in template.get("gst_slabs_bp", [0]):
            self.gst_box.addItem(f"{bp / 100:g}%", bp)
        self.gst_box.setCurrentIndex(max(self.gst_box.findData(0), 0))
        self.tracking_box = QComboBox()
        allowed = ["none"] + [t for t in ("weighed", "batch", "serial") if features.get(t)]
        for mode in allowed:
            self.tracking_box.addItem(tr(f"trk.{mode}"), mode)
        default = template.get("default_tracking", "none")
        self.tracking_box.setCurrentIndex(max(self.tracking_box.findData(default), 0))
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("dlg.barcode"), self.barcode_edit)
        form.addRow(tr("dlg.price"), self.price_edit)
        form.addRow(tr("dlg.gst_rate"), self.gst_box)
        form.addRow(tr("dlg.tracking"), self.tracking_box)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.name_edit.textChanged.connect(self._check)
        self.price_edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.ok_button.setEnabled(bool(self.name_edit.text().strip())
                                  and _valid(_non_negative_rupees, self.price_edit.text()))

    def values(self):
        tracking = self.tracking_box.currentData()
        barcode = self.barcode_edit.text().strip()
        return {"name": self.name_edit.text().strip(),
                "sell_price_paise": fmt.parse_rupees(self.price_edit.text()),
                "gst_rate_bp": self.gst_box.currentData(), "tracking": tracking,
                "unit": "kg" if tracking == "weighed" else "pcs",
                "barcodes": [barcode] if barcode else []}


class CustomerDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(tr("dlg.customer_title"))
        self._party_id = None
        self._cleared = False
        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("common.search"))
        layout.addWidget(self.search_edit)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.walk_in_button = QPushButton(tr("dlg.walk_in"))
        layout.addWidget(self.walk_in_button)
        layout.addWidget(QLabel(tr("dlg.new_customer")))
        row = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText(tr("common.name"))
        self.new_phone = QLineEdit()
        self.new_phone.setPlaceholderText(tr("common.phone"))
        self.add_button = QPushButton(tr("common.add"))
        for w in (self.new_name, self.new_phone, self.add_button):
            row.addWidget(w)
        layout.addLayout(row)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.search_edit.textChanged.connect(self._reload)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        self.walk_in_button.clicked.connect(self._walk_in)
        self.add_button.clicked.connect(self._add)
        self._reload()

    def _reload(self):
        self.list.clear()
        for p in parties.list_parties(self.conn, kind="customer", search=self.search_edit.text()):
            item = QListWidgetItem(f"{p['name']}  {p['phone'] or ''}")
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            self.list.addItem(item)

    def _walk_in(self):
        self._cleared = True
        self.accept()

    def _add(self):
        try:
            self._party_id = parties.create_party(self.conn, name=self.new_name.text(),
                                                  phone=self.new_phone.text().strip() or None)
        except Exception as exc:
            show_error(self, exc)
            return
        self.accept()

    def party_id(self):
        if self._party_id is not None:
            return self._party_id
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def cleared(self):
        return self._cleared


class DiscountDialog(QDialog):
    def __init__(self, max_paise, parent=None):
        super().__init__(parent)
        self.max_paise = max_paise
        self.setWindowTitle(tr("dlg.discount_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("dlg.discount_prompt")))
        self.edit = QLineEdit()
        layout.addWidget(self.edit)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.edit.textChanged.connect(self._check)
        self._check()

    def _amount(self):
        paise = fmt.parse_rupees(self.edit.text())
        if not 0 <= paise <= self.max_paise:
            raise ValueError("out of range")
        return paise

    def _check(self):
        self.ok_button.setEnabled(_valid(lambda _t: self._amount(), self.edit.text()))

    def discount_paise(self):
        return self._amount()


class HeldBillsDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.held_title"))
        self._action = None
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for r in rows:
            who = r["party"] or tr("dlg.walk_in")
            item = QListWidgetItem(f"#{r['id']}   {who}   {fmt.rupees(r['total_paise'])}   ({r['lines']})")
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.resume_button = QPushButton(tr("dlg.resume"))
        self.discard_button = QPushButton(tr("dlg.discard"))
        close = QPushButton(tr("common.close"))
        for b in (self.resume_button, self.discard_button, close):
            row.addWidget(b)
        layout.addLayout(row)
        self.resume_button.setEnabled(bool(rows))
        self.discard_button.setEnabled(bool(rows))
        self.resume_button.clicked.connect(lambda: self._finish("resume"))
        self.discard_button.clicked.connect(lambda: self._finish("discard"))
        close.clicked.connect(self.reject)

    def _finish(self, action):
        self._action = action
        self.accept()

    def action(self):
        return self._action

    def selected_bill_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class PayDialog(QDialog):
    def __init__(self, total_paise, has_customer, features, parent=None):
        super().__init__(parent)
        self.total_paise = total_paise
        self.setWindowTitle(tr("dlg.pay_title"))
        modes = ["cash", "upi", "card"]
        if features.get("emi"):
            modes.append("emi")
        if has_customer and features.get("udhaar"):
            modes.append("credit")
        form = QFormLayout(self)
        form.addRow(QLabel(f"{tr('bill.total')}: {fmt.rupees(total_paise)}"))
        self.edits = {}
        for mode in modes:
            edit = QLineEdit(money.paise_to_str(total_paise) if mode == "cash" else "")
            edit.textChanged.connect(self._recalc)
            self.edits[mode] = edit
            form.addRow(tr(f"pay.{mode}"), edit)
        self.cash_given_edit = QLineEdit()
        self.cash_given_edit.textChanged.connect(self._recalc)
        form.addRow(tr("dlg.cash_given"), self.cash_given_edit)
        self.balance_label = QLabel()
        self.change_label = QLabel()
        form.addRow(tr("dlg.balance"), self.balance_label)
        form.addRow(tr("dlg.change"), self.change_label)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.paid_paise = 0
        self.remaining_paise = total_paise
        self.change_paise = 0
        self._amounts = {}
        self._valid_input = True
        self._recalc()

    def _amount(self, edit):
        text = edit.text().strip()
        return 0 if not text else fmt.parse_rupees(text)

    def _recalc(self):
        try:
            amounts = {mode: self._amount(edit) for mode, edit in self.edits.items()}
            given = self._amount(self.cash_given_edit)
            self._valid_input = all(v >= 0 for v in amounts.values())
        except ValueError:
            self._valid_input = False
            self.ok_button.setEnabled(False)
            return
        self._amounts = amounts
        self.paid_paise = sum(amounts.values())
        self.remaining_paise = self.total_paise - self.paid_paise
        cash = amounts.get("cash", 0)
        self.change_paise = given - cash if given > cash else 0
        self.balance_label.setText(fmt.rupees(self.remaining_paise))
        self.change_label.setText(fmt.rupees(self.change_paise))
        self.ok_button.setEnabled(self.is_valid())

    def is_valid(self):
        return self._valid_input and self.remaining_paise == 0

    def payments(self):
        return [(mode, paise) for mode, paise in self._amounts.items() if paise > 0]


class BatchDialog(QDialog):
    """Pick the batch for a batch-tracked line. choices: dicts from stock.batch_choices."""

    def __init__(self, choices, current_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.batch_title"))
        today = clock.today().isoformat()
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for c in choices:
            expiry = fmt.date_text(c["expiry"]) if c["expiry"] else tr("dlg.batch_no_expiry")
            text = tr("dlg.batch_row", batch_no=c["batch_no"], expiry=expiry, qty=fmt.qty(c["on_hand_milli"]))
            if c["expiry"] and c["expiry"] < today:
                text += f"  [{tr('dlg.batch_expired')}]"
            entry = QListWidgetItem(text)
            entry.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.list.addItem(entry)
            if c["id"] == current_id:
                self.list.setCurrentItem(entry)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(self.list)
        box, self.ok_button = ok_cancel(self)
        self.ok_button.setEnabled(bool(choices))
        layout.addWidget(box)

    def selected_batch_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None
