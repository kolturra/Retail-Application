from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from retail.i18n import tr
from retail_ui import APP_NAME, vendor
from retail_ui.widgets.helpers import error_label


class ActivationDialog(QDialog):
    def __init__(self, machine_id, invalid=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — {tr('act.title')}")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        intro = QLabel(tr("act.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("act.machine_id")))
        self.machine_edit = QLineEdit(machine_id)
        self.machine_edit.setReadOnly(True)
        row.addWidget(self.machine_edit)
        self.copy_button = QPushButton(tr("act.copy"))
        self.copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(machine_id))
        row.addWidget(self.copy_button)
        layout.addLayout(row)

        requests = QHBoxLayout()
        self.whatsapp_button = QPushButton(tr("act.request_whatsapp"))
        self.whatsapp_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(vendor.whatsapp_request_url(machine_id))))
        requests.addWidget(self.whatsapp_button)
        self.email_button = QPushButton(tr("act.request_email"))
        email_url = vendor.email_request_url(machine_id)
        self.email_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(email_url)))
        self.email_button.setHidden(email_url is None)
        requests.addWidget(self.email_button)
        layout.addLayout(requests)

        layout.addWidget(QLabel(tr("act.key")))
        self.key_edit = QPlainTextEdit()
        self.key_edit.setFixedHeight(90)
        layout.addWidget(self.key_edit)
        self.invalid_label = error_label(tr("act.invalid"))
        self.invalid_label.setHidden(not invalid)
        layout.addWidget(self.invalid_label)

        buttons = QDialogButtonBox()
        self.activate_button = buttons.addButton(tr("act.activate"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("act.quit"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.activate_button.setEnabled(False)
        self.key_edit.textChanged.connect(lambda: self.activate_button.setEnabled(bool(self.key())))

    def key(self):
        return self.key_edit.toPlainText().strip()


def request_activation(machine_id, invalid):
    """The callable bootstrap.bootstrap() expects: a key, or None when the user quits."""
    dialog = ActivationDialog(machine_id, invalid)
    return dialog.key() if dialog.exec() == QDialog.DialogCode.Accepted else None
