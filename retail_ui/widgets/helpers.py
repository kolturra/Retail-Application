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


# --- message boxes with translated buttons -------------------------------------------------
# Qt's stock buttons (Yes/No/OK/Cancel/Show Details...) come from Qt's own translations, which the
# app does not ship, so they would stay English. These build every button from the catalogue.
# The build_* functions only construct (tests inspect them); the plain ones run the box.
def _message_box(parent, icon, text, buttons, title=""):
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(icon, title, text, QMessageBox.StandardButton.NoButton, parent)
    made = [box.addButton(tr(key), role) for key, role in buttons]
    return box, made


def build_confirm_box(parent, key):
    from PySide6.QtWidgets import QMessageBox
    box, (yes, no) = _message_box(parent, QMessageBox.Icon.Question, tr(key),
                                  [("common.yes", QMessageBox.ButtonRole.YesRole),
                                   ("common.no", QMessageBox.ButtonRole.NoRole)])
    box.setDefaultButton(no)
    box.setEscapeButton(no)
    return box, yes


def confirm(parent, key) -> bool:
    box, yes = build_confirm_box(parent, key)
    box.exec()
    return box.clickedButton() is yes


def build_notice_box(parent, key, warning=False):
    from PySide6.QtWidgets import QMessageBox
    icon = QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information
    box, (ok,) = _message_box(parent, icon, tr(key), [("common.ok", QMessageBox.ButtonRole.AcceptRole)])
    box.setDefaultButton(ok)
    return box, ok


def inform(parent, key) -> None:
    build_notice_box(parent, key)[0].exec()


def warn(parent, key) -> None:
    build_notice_box(parent, key, warning=True)[0].exec()


def build_text_dialog(parent, title_key, label_key):
    from PySide6.QtWidgets import QInputDialog
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(tr(title_key))
    dialog.setLabelText(tr(label_key))
    dialog.setOkButtonText(tr("common.ok"))
    dialog.setCancelButtonText(tr("common.cancel"))
    return dialog


def ask_text(parent, title_key, label_key):
    """(text, accepted) like QInputDialog.getText, with translated buttons."""
    from PySide6.QtWidgets import QDialog
    dialog = build_text_dialog(parent, title_key, label_key)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.textValue(), accepted
