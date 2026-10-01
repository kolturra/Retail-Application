from PySide6.QtWidgets import QDialogButtonBox, QLabel

from retail.i18n import tr


def ok_cancel(dialog, ok_key="common.ok", cancel_key="common.cancel"):
    box = QDialogButtonBox()
    ok = box.addButton(tr(ok_key), QDialogButtonBox.ButtonRole.AcceptRole)
    box.addButton(tr(cancel_key), QDialogButtonBox.ButtonRole.RejectRole)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box, ok


def error_label(text=""):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #b00020;")
    return label
