import re

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableView, QVBoxLayout)

from retail import money
from retail.i18n import tr
from retail.services import parties
from retail_ui import fmt, states, validators
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

HEADERS = ["common.name", "common.phone", "party.balance"]
VIEWS = (("customers", "party.customers"), ("suppliers", "party.suppliers"), ("dues", "party.dues"))
MAX_RECEIVE_PAISE = 10 ** 12          # a sanity bound on one payment (Rs 10,000,000,000)


class PartyDialog(QDialog):
    def __init__(self, party=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("party.dialog_title"))
        self._editing = party is not None
        form = QFormLayout(self)
        self.name_edit = QLineEdit(party["name"] if party else "")
        self.phone_edit = QLineEdit((party["phone"] or "") if party else "")
        self.gstin_edit = QLineEdit((party["gstin"] or "") if party else "")
        self.state_box = QComboBox()
        self.state_box.addItem(tr("party.none_state"), "")
        for code, name in states.STATES.items():
            self.state_box.addItem(f"{code} — {name}", code)
        self.state_box.setCurrentIndex(max(self.state_box.findData((party["state_code"] or "") if party else ""), 0))
        self.type_box = QComboBox()
        for kind in ("customer", "supplier", "both"):
            self.type_box.addItem(tr(f"party.type_{kind}"), kind)
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("common.phone"), self.phone_edit)
        form.addRow(tr("tax.gstin"), self.gstin_edit)
        form.addRow(tr("ob.state"), self.state_box)
        form.addRow(tr("party.type"), self.type_box)
        self.type_box.setHidden(self._editing)
        form.labelForField(self.type_box).setHidden(self._editing)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        for signal in (self.name_edit.textChanged, self.gstin_edit.textChanged, self.phone_edit.textChanged, self.state_box.currentIndexChanged):
            signal.connect(lambda *_: self._check())
        self._check()

    def _check(self):
        gstin = self.gstin_edit.text().strip()
        gstin_ok = not gstin or (bool(self.state_box.currentData())
                                 and validators.gstin_error(gstin, self.state_box.currentData()) is None)
        phone = self.phone_edit.text().strip()
        phone_ok = not phone or (bool(validators.phone_digits(phone)) and re.fullmatch(r"[0-9 +()\-]+", phone) is not None)
        self.ok_button.setEnabled(bool(self.name_edit.text().strip()) and gstin_ok and phone_ok)

    def values(self):
        out = {"name": self.name_edit.text().strip(), "phone": self.phone_edit.text().strip(),
               "gstin": self.gstin_edit.text().strip().upper(), "state_code": self.state_box.currentData()}
        if not self._editing:
            out["type"] = self.type_box.currentData()
        return out


class ReceiveDialog(QDialog):
    def __init__(self, party_name, due_paise, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("party.receive"))
        form = QFormLayout(self)
        form.addRow(QLabel(party_name))
        self.amount_edit = QLineEdit(money.paise_to_str(max(due_paise, 0)))
        self.mode_box = QComboBox()
        for mode in ("cash", "upi", "card"):
            self.mode_box.addItem(tr(f"pay.{mode}"), mode)
        self.note_edit = QLineEdit()
        form.addRow(tr("common.amount"), self.amount_edit)
        form.addRow(tr("dlg.pay_title"), self.mode_box)
        form.addRow(tr("common.note"), self.note_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.amount_edit.textChanged.connect(self._check)
        self._check()

    def _amount(self):
        paise = fmt.parse_rupees(self.amount_edit.text())
        if not 0 < paise <= MAX_RECEIVE_PAISE:
            raise ValueError("Amount out of range")
        return paise

    def _check(self):
        try:
            self._amount()
            self.ok_button.setEnabled(True)
        except (ValueError, ArithmeticError):
            self.ok_button.setEnabled(False)

    def amount_paise(self):
        return self._amount()

    def mode(self):
        return self.mode_box.currentData()

    def note(self):
        return self.note_edit.text().strip()


class PartiesScreen(Screen):
    nav_key = "nav.parties"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self._read_only = False
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.view_box = QComboBox()
        for code, key in VIEWS:
            self.view_box.addItem(tr(key), code)
        self.search_edit = QLineEdit()
        self.bind(self.search_edit, "common.search", "setPlaceholderText")
        top.addWidget(self.view_box)
        top.addWidget(self.search_edit, 1)
        layout.addLayout(top)
        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.add_button = self._button("common.add", self.add_party, row)
        self.edit_button = self._button("common.edit", self.edit_party, row)
        self.receive_button = self._button("party.receive", self.receive_payment, row)
        layout.addLayout(row)
        self.view_box.currentIndexChanged.connect(lambda _i: self.refresh())
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        self._rows = {}

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    def _view(self):
        return self.view_box.currentData()

    def refresh(self):
        view = self._view()
        kind = "supplier" if view == "suppliers" else "customer"
        selected = self._selected_id()
        rows = parties.list_parties(self.session.conn, kind=kind, search=self.search_edit.text())
        if view == "dues":
            rows = sorted((r for r in rows if r["balance_paise"] > 0), key=lambda r: -r["balance_paise"])
        self._rows = {r["id"]: r for r in rows}
        ids = [r["id"] for r in rows]
        self.model.set_rows(
            [(r["name"], r["phone"] or "", "" if view == "suppliers" else fmt.rupees(r["balance_paise"]))
             for r in rows], ids=ids, right_cols=(2,))
        if selected in ids:
            self.table.selectRow(ids.index(selected))

    def retranslate(self):
        super().retranslate()
        for i, (_code, key) in enumerate(VIEWS):
            self.view_box.setItemText(i, tr(key))
        self.refresh()

    def apply_read_only(self, read_only):
        self._read_only = bool(read_only)
        for button in (self.add_button, self.edit_button, self.receive_button):
            button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _selected_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.id_at(rows[0].row()) if rows else None

    def _selected(self):
        return self._rows.get(self._selected_id())

    def _guarded(self, action):
        if self._read_only:
            return
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def add_party(self):
        def run():
            v = self._ask_party(None)
            if v is not None:
                parties.create_party(self.session.conn, name=v["name"], phone=v["phone"] or None,
                                     gstin=v["gstin"] or None, state_code=v["state_code"] or None, type=v["type"])
        self._guarded(run)

    def edit_party(self):
        def run():
            party = self._selected()
            if party is None:
                return
            v = self._ask_party(party)
            if v is not None:
                parties.update_party(self.session.conn, party["id"], name=v["name"], phone=v["phone"] or None,
                                     gstin=v["gstin"] or None, state_code=v["state_code"] or None)
        self._guarded(run)

    def receive_payment(self):
        def run():
            party = self._selected()
            if party is None or self._view() == "suppliers":
                return
            answer = self._ask_receive(party["name"], party["balance_paise"])
            if answer is not None:
                paise, mode, note = answer
                parties.receive_payment(self.session.conn, party["id"], paise, mode=mode, note=note)
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_party(self, party):
        dialog = PartyDialog(party, self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_receive(self, name, due_paise):
        dialog = ReceiveDialog(name, due_paise, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.amount_paise(), dialog.mode(), dialog.note()
