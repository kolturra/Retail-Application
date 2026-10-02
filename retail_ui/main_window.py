import logging

from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QStackedWidget, QVBoxLayout, QWidget)

from retail import i18n
from retail.i18n import tr
from retail_ui import APP_NAME, __version__, fmt, fonts
from retail_ui.errors import show_error

log = logging.getLogger("retail_ui")


class MainWindow(QMainWindow):
    def __init__(self, session, screen_classes, parent=None, *, notice_key=None):
        super().__init__(parent)
        self.session = session
        self.notice_key = notice_key
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 760)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background:#b00020;color:white;padding:6px;")
        outer.addWidget(self.banner)
        self.notice = QLabel()  # e.g. the recovery-mode explanation; empty and hidden normally
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("background:#fff3cd;color:#664d03;padding:6px;")
        outer.addWidget(self.notice)

        body = QHBoxLayout()
        side = QVBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        side.addWidget(self.nav)
        self.language_box = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_box.addItem(name, code)
        self.language_box.setCurrentIndex(self.language_box.findData(i18n.get_language()))
        side.addWidget(self.language_box)
        body.addLayout(side)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)

        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)

        self.screens = []
        for cls in screen_classes:
            screen = cls(session)
            self.screens.append(screen)
            self.stack.addWidget(screen)
            self.nav.addItem(QListWidgetItem(tr(cls.nav_key)))

        self.nav.currentRowChanged.connect(self._show_screen)
        self.language_box.currentIndexChanged.connect(self._on_language_chosen)
        session.language_changed.connect(self._on_language)
        session.read_only_changed.connect(self._on_read_only)
        session.data_changed.connect(self._on_data_changed)

        self._update_banner()
        self._update_status()
        for screen in self.screens:
            screen.apply_read_only(session.read_only)
        if self.screens:
            self.nav.setCurrentRow(0)

    # --- navigation / refresh -----------------------------------------------
    def _show_screen(self, row):
        if 0 <= row < len(self.screens):
            self.stack.setCurrentIndex(row)
            self.screens[row].refresh()

    def _on_data_changed(self):
        self._update_status()  # the shop name may have been edited or restored
        row = self.stack.currentIndex()
        if 0 <= row < len(self.screens):
            self.screens[row].refresh()

    # --- language ---------------------------------------------------------------
    def _on_language_chosen(self):
        code = self.language_box.currentData()
        if code == i18n.get_language():
            return
        try:
            self.session.set_language(code)
        except Exception as exc:
            show_error(self, exc)
            self._sync_language_box()

    def _sync_language_box(self):
        self.language_box.blockSignals(True)
        self.language_box.setCurrentIndex(self.language_box.findData(i18n.get_language()))
        self.language_box.blockSignals(False)

    def _on_language(self, code):
        self._sync_language_box()
        app = QApplication.instance()
        if app is not None:
            fonts.apply_language_font(app, code)
        for i, screen in enumerate(self.screens):
            self.nav.item(i).setText(tr(screen.nav_key))
            try:
                screen.retranslate()
            except Exception:  # one screen must never stop the others from switching language
                log.exception("retranslating %s failed", type(screen).__name__)
        self._update_banner()
        self._update_status()

    # --- licence -----------------------------------------------------------------
    def _on_read_only(self, read_only):
        self._update_banner()
        self._update_status()
        for screen in self.screens:
            screen.apply_read_only(read_only)

    def _update_banner(self):
        self.banner.setText(tr("license.read_only"))
        self.banner.setHidden(not self.session.read_only)
        self.notice.setText(tr(self.notice_key) if self.notice_key else "")
        self.notice.setHidden(not self.notice_key)

    def _update_status(self):
        lic_state = self.session.license
        parts = [self.session.shop()["name"] if self.session.has_shop() else APP_NAME]
        if lic_state.expires:
            parts.append(tr("status.expires", date=fmt.date_text(lic_state.expires)))
        parts.append(f"v{__version__}")
        self.status_label.setText("   |   ".join(parts))

    # --- closing -----------------------------------------------------------------
    def closeEvent(self, event):
        self.session.backup_if_due()  # never raises: a backup problem must not trap the user
        event.accept()
