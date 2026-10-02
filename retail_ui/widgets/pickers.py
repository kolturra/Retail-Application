from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QVBoxLayout, QWidget

from retail.i18n import tr
from retail.services import items
from retail_ui import fmt


class ItemPicker(QWidget):
    """A search box over a list of items (name, SKU or barcode)."""

    selection_changed = Signal()

    def __init__(self, conn_getter, parent=None):
        super().__init__(parent)
        self._conn = conn_getter
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("common.search"))
        self.list = QListWidget()
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        self.search.textChanged.connect(lambda _t: self.reload())
        self.list.currentRowChanged.connect(lambda _r: self.selection_changed.emit())
        self.reload()

    def reload(self):
        self._rows = items.list_items(self._conn(), self.search.text(), limit=50)
        self.list.blockSignals(True)
        self.list.clear()
        for r in self._rows:
            self.list.addItem(f"{r['name']}    ({fmt.qty(r['on_hand_milli'])})")
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        self.selection_changed.emit()

    def selected_item(self):
        row = self.list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None
