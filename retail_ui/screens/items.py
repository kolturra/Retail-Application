from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableView, QVBoxLayout)

from retail import money, segments
from retail.i18n import tr
from retail.services import items
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

HEADERS = ["common.name", "item.sku", "dlg.price", "counter.gst", "dlg.tracking", "items.on_hand", "items.reorder"]
LIST_LIMIT = 500


def _valid_or_blank(parser, text):
    if not text.strip():
        return True
    try:
        parser(text)
        return True
    except ValueError:
        return False


class ItemDialog(QDialog):
    def __init__(self, template, item=None, barcodes=(), locked_tracking=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("items.dialog_title"))
        features = template.get("features", {})
        form = QFormLayout(self)
        self.name_edit = QLineEdit(item["name"] if item else "")
        self.sku_edit = QLineEdit((item["sku"] or "") if item else "")
        self.hsn_edit = QLineEdit((item["hsn"] or "") if item else "")
        self.price_edit = QLineEdit(money.paise_to_str(item["sell_price_paise"]) if item else "")
        self.buy_edit = QLineEdit(money.paise_to_str(item["buy_price_paise"]) if item and item["buy_price_paise"] else "")
        self.gst_box = QComboBox()
        slabs = list(template.get("gst_slabs_bp", [0]))
        if item and item["gst_rate_bp"] not in slabs:
            slabs.append(item["gst_rate_bp"])
        for bp in slabs:
            self.gst_box.addItem(f"{bp / 100:g}%", bp)
        self.gst_box.setCurrentIndex(max(self.gst_box.findData(item["gst_rate_bp"] if item else 0), 0))
        self.unit_box = QComboBox()
        self.unit_box.setEditable(True)
        self.unit_box.addItems(template.get("units", ["pcs"]))
        self.unit_box.setCurrentText(item["unit"] if item else self.unit_box.itemText(0))
        self.tracking_box = QComboBox()
        modes = ["none"] + [t for t in ("weighed", "batch", "serial") if features.get(t)]
        if item and item["tracking"] not in modes:
            modes.append(item["tracking"])
        for mode in modes:
            self.tracking_box.addItem(tr(f"trk.{mode}"), mode)
        wanted = item["tracking"] if item else template.get("default_tracking", "none")
        self.tracking_box.setCurrentIndex(max(self.tracking_box.findData(wanted), 0))
        self.tracking_box.setEnabled(not locked_tracking)
        self.reorder_edit = QLineEdit(fmt.qty(item["reorder_milli"]) if item and item["reorder_milli"] else "")
        self.warranty_spin = QSpinBox()
        self.warranty_spin.setRange(0, 120)
        self.warranty_spin.setValue(item["warranty_months"] if item else 0)
        self.barcodes_edit = QLineEdit(", ".join(barcodes))
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("item.sku"), self.sku_edit)
        form.addRow(tr("item.hsn"), self.hsn_edit)
        form.addRow(tr("dlg.price"), self.price_edit)
        form.addRow(tr("items.buy_price"), self.buy_edit)
        form.addRow(tr("dlg.gst_rate"), self.gst_box)
        form.addRow(tr("items.unit"), self.unit_box)
        form.addRow(tr("dlg.tracking"), self.tracking_box)
        form.addRow(tr("items.reorder"), self.reorder_edit)
        self._warranty_label = tr("items.warranty")
        form.addRow(self._warranty_label, self.warranty_spin)
        self.warranty_spin.setHidden(not (features.get("warranty") or (item and item["warranty_months"])))
        form.labelForField(self.warranty_spin).setHidden(self.warranty_spin.isHidden())
        form.addRow(tr("items.barcodes"), self.barcodes_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        for edit in (self.name_edit, self.price_edit, self.buy_edit, self.reorder_edit):
            edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.ok_button.setEnabled(
            bool(self.name_edit.text().strip()) and _valid_or_blank(fmt.parse_rupees, self.price_edit.text())
            and bool(self.price_edit.text().strip())
            and _valid_or_blank(fmt.parse_rupees, self.buy_edit.text())
            and _valid_or_blank(fmt.parse_qty, self.reorder_edit.text()))

    def values(self):
        buy, reorder = self.buy_edit.text().strip(), self.reorder_edit.text().strip()
        return {"name": self.name_edit.text().strip(), "sku": self.sku_edit.text().strip(),
                "hsn": self.hsn_edit.text().strip() or None, "gst_rate_bp": self.gst_box.currentData(),
                "unit": self.unit_box.currentText().strip() or "pcs",
                "sell_price_paise": fmt.parse_rupees(self.price_edit.text()),
                "buy_price_paise": fmt.parse_rupees(buy) if buy else 0,
                "reorder_milli": fmt.parse_qty(reorder) if reorder else 0,
                "warranty_months": self.warranty_spin.value(), "tracking": self.tracking_box.currentData()}

    def barcodes(self):
        return list(dict.fromkeys(c.strip() for c in self.barcodes_edit.text().split(",") if c.strip()))


class ItemsScreen(Screen):
    nav_key = "nav.items"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.bind(self.search_edit, "common.search", "setPlaceholderText")
        self.inactive_box = self.bind(QCheckBox(), "items.show_inactive")
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.inactive_box)
        layout.addLayout(top)
        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.note_label = QLabel()
        layout.addWidget(self.note_label)
        row = QHBoxLayout()
        self.add_button = self._button("common.add", self.add_item, row)
        self.edit_button = self._button("common.edit", self.edit_item, row)
        self.toggle_button = self._button("items.deactivate", self.toggle_active, row)
        layout.addLayout(row)
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        self.inactive_box.toggled.connect(lambda _c: self.refresh())

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    def refresh(self):
        rows = items.list_items(self.session.conn, self.search_edit.text(),
                                include_inactive=self.inactive_box.isChecked(), limit=LIST_LIMIT)
        table, ids, low = [], [], []
        for i, r in enumerate(rows):
            unit = f" {r['unit']}" if r["tracking"] == "weighed" else ""
            name = r["name"] + (f"  [{tr('items.inactive')}]" if not r["active"] else "")
            table.append((name, r["sku"] or "", fmt.rupees(r["sell_price_paise"]),
                          f"{r['gst_rate_bp'] / 100:g}%" if r["gst_rate_bp"] else "", tr(f"trk.{r['tracking']}"),
                          fmt.qty(r["on_hand_milli"]) + unit,
                          (fmt.qty(r["reorder_milli"]) + unit) if r["reorder_milli"] else ""))
            ids.append(r["id"])
            if r["reorder_milli"] and r["on_hand_milli"] <= r["reorder_milli"]:
                low.append(i)
        self.model.set_rows(table, ids, right_cols=(2, 3, 5, 6), highlight=low)
        self.note_label.setText(tr("items.limit_note") if len(rows) >= LIST_LIMIT else "")

    def retranslate(self):
        super().retranslate()
        self.refresh()

    def apply_read_only(self, read_only):
        for button in (self.add_button, self.edit_button, self.toggle_button):
            button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _selected_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.id_at(rows[0].row()) if rows else None

    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def add_item(self):
        def run():
            answer = self._ask_item(None, [], False)
            if answer is not None:
                v = answer["values"]
                items.create_item(self.session.conn, **{**v, "sku": v["sku"] or None},
                                  barcodes=answer["barcodes"])
        self._guarded(run)

    def edit_item(self):
        def run():
            item_id = self._selected_id()
            if item_id is None:
                return
            conn = self.session.conn
            answer = self._ask_item(items.get_item(conn, item_id), items.item_barcodes(conn, item_id),
                                    items.has_stock_history(conn, item_id))
            if answer is not None:
                items.update_item(conn, item_id, **answer["values"])
                items.set_barcodes(conn, item_id, answer["barcodes"])
        self._guarded(run)

    def toggle_active(self):
        def run():
            item_id = self._selected_id()
            if item_id is not None:
                items.set_item_active(self.session.conn, item_id,
                                      not items.get_item(self.session.conn, item_id)["active"])
        self._guarded(run)

    # --- prompts ------------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_item(self, item, barcodes, locked_tracking):
        dialog = ItemDialog(segments.template_settings(self.session.conn), item, barcodes, locked_tracking, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {"values": dialog.values(), "barcodes": dialog.barcodes()}
