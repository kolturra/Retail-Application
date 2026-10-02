from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QWidget

from retail.i18n import tr


class Screen(QWidget):
    """Base for every navigable screen. Screens never hold business rules; they call services."""

    nav_key = ""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._bindings = []
        self._models = []

    def bind(self, widget, key, setter="setText", suffix=""):
        """Set a translated text now and again on every retranslate()."""
        self._bindings.append((widget, key, setter, suffix))
        getattr(widget, setter)(tr(key) + suffix)
        return widget

    def track(self, model):
        self._models.append(model)
        return model

    def retranslate(self):
        for widget, key, setter, suffix in self._bindings:
            getattr(widget, setter)(tr(key) + suffix)
        for model in self._models:
            model.retranslate()

    def refresh(self):
        """Reload from the database (called when shown and when data changed)."""

    def apply_read_only(self, read_only):
        """Disable write controls after the licence expires."""


class RowsModel(QAbstractTableModel):
    """A read-only table of already-formatted strings with translated headers."""

    def __init__(self, header_keys, parent=None):
        super().__init__(parent)
        self._keys = list(header_keys)
        self._rows = []
        self._ids = []
        self._right = set()
        self._highlight = set()

    def set_rows(self, rows, ids=None, right_cols=(), highlight=()):
        self.beginResetModel()
        self._rows = [tuple(r) for r in rows]
        self._ids = list(ids) if ids is not None else list(range(len(self._rows)))
        self._right = set(right_cols)
        self._highlight = set(highlight)
        self.endResetModel()

    def id_at(self, row):
        return self._ids[row] if 0 <= row < len(self._ids) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._keys)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in self._right:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and index.row() in self._highlight:
            return QBrush(QColor("#fff3cd"))
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(self._keys[section])
        return None

    def retranslate(self):
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, max(len(self._keys) - 1, 0))
