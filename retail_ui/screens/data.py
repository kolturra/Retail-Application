from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from retail.i18n import tr
from retail.services import backup
from retail_ui import APP_NAME, __version__, fmt, vendor
from retail_ui.errors import show_error
from retail_ui.widgets import helpers
from retail_ui.widgets.base import Screen


class DataScreen(Screen):
    """Backup, restore, licence and about. Nothing here is ever disabled: it must work in read-only
    (expired) mode and in recovery mode where the database has no shop yet."""

    nav_key = "nav.data"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        paths_box = self._group("data.paths", layout)
        form = QFormLayout(paths_box)
        self.backup_dir_edit, self.extra_dir_edit = QLineEdit(), QLineEdit()
        form.addRow(self.bind(QLabel(), "ob.backup_dir"), self._with_browse(self.backup_dir_edit))
        form.addRow(self.bind(QLabel(), "ob.extra_dir"), self._with_browse(self.extra_dir_edit))
        self.save_paths_button = self.bind(QPushButton(), "data.save_paths")
        self.save_paths_button.clicked.connect(lambda _=False: self.save_paths())
        form.addRow(self.save_paths_button)

        backup_box = self._group("data.backups", layout)
        bl = QVBoxLayout(backup_box)
        self.folder_label = QLabel()          # which folder is really in use (a fallback is called out)
        self.folder_label.setWordWrap(True)
        bl.addWidget(self.folder_label)
        self.backups_list = QListWidget()
        bl.addWidget(self.backups_list)
        row = QHBoxLayout()
        self.backup_now_button = self.bind(QPushButton(), "data.backup_now")
        self.restore_button = self.bind(QPushButton(), "data.restore")
        row.addWidget(self.backup_now_button)
        row.addWidget(self.restore_button)
        self.restore_file_button = self.bind(QPushButton(), "data.restore_file")
        row.addWidget(self.restore_file_button)
        self.restore_file_button.clicked.connect(lambda _=False: self.restore_from_file())
        bl.addLayout(row)
        self.backup_now_button.clicked.connect(lambda _=False: self.backup_now())
        self.restore_button.clicked.connect(lambda _=False: self.restore_selected())

        license_box = self._group("data.license", layout)
        ll = QVBoxLayout(license_box)
        self.buyer_label, self.expires_label = QLabel(), QLabel()
        self.plan_label, self.state_label = QLabel(), QLabel()
        for label in (self.buyer_label, self.expires_label, self.plan_label, self.state_label):
            ll.addWidget(label)
        machine_row = QHBoxLayout()
        self.machine_label = QLabel()
        machine_row.addWidget(self.machine_label)
        self.copy_button = self.bind(QPushButton(), "act.copy")
        self.copy_button.clicked.connect(lambda _=False: QGuiApplication.clipboard().setText(session.machine_id))
        machine_row.addWidget(self.copy_button)
        ll.addLayout(machine_row)
        ll.addWidget(self.bind(QLabel(), "data.new_key"))
        self.key_edit = QPlainTextEdit()
        self.key_edit.setFixedHeight(70)
        ll.addWidget(self.key_edit)
        self.activate_button = self.bind(QPushButton(), "act.activate")
        self.activate_button.clicked.connect(lambda _=False: self.activate())
        ll.addWidget(self.activate_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.about_label = QLabel()
        layout.addWidget(self.status_label)
        layout.addWidget(self.about_label)
        layout.addStretch(1)

    def _group(self, title_key, layout):
        group = QGroupBox()
        self.bind(group, title_key, "setTitle")
        layout.addWidget(group)
        return group

    def _with_browse(self, edit):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit)
        button = self.bind(QPushButton(), "common.browse")
        button.clicked.connect(lambda _=False: self._browse(edit))
        row.addWidget(button)
        return holder

    def _browse(self, edit):
        folder = self._pick_folder(edit.text())
        if folder:
            edit.setText(folder)

    # --- Screen protocol ------------------------------------------------------
    def retranslate(self):
        super().retranslate()
        self.status_label.clear()  # a message in the old language must not linger
        self.refresh()

    def refresh(self):
        s = self.session
        self.backup_dir_edit.setText(s.settings.backup_dir)
        self.extra_dir_edit.setText(s.settings.extra_backup_dir)
        self._refresh_lists()

    def _refresh_lists(self):
        """Everything except the folder edits (so a failed save never overwrites what was typed)."""
        s = self.session
        self.backups_list.clear()
        self.folder_label.setText(tr("data.folder_fallback", path=s.backup_dir) if s.backup_dir_fallback
                                  else tr("data.folder_in_use", path=s.backup_dir))
        for path, where in self._all_backups():
            try:
                st = path.stat()
                when = fmt.date_text(datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"))
                detail = f"{when}, {st.st_size // 1024} KB"
            except OSError:
                detail = "?"
            item = QListWidgetItem(f"{path.name}    ({detail}, {where})")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.backups_list.addItem(item)
        lic = s.license  # never touches shop fields: the database may have no shop (recovery mode)
        self.buyer_label.setText(tr("data.buyer", name=lic.buyer))
        self.expires_label.setText(tr("data.expires", date=fmt.date_text(lic.expires) if lic.expires else ""))
        self.plan_label.setText(tr("data.plan", plan=lic.plan))
        self.state_label.setText(tr("data.status_active") if lic.status == "active" else tr("data.status_expired"))
        self.machine_label.setText(f"{tr('act.machine_id')}: {s.machine_id}")
        self.about_label.setText(f"{APP_NAME}  v{__version__}    {tr('data.contact', phone=vendor.VENDOR_PHONE)}")

    def _all_backups(self):
        """Backups from the main folder and the second location, newest first, each file once."""
        s = self.session
        found, seen = [], set()
        for folder, label in ((s.backup_dir, tr("data.loc_primary")),
                              (Path(s.settings.extra_backup_dir) if s.settings.extra_backup_dir else None,
                               tr("data.loc_extra"))):
            if folder is None:
                continue
            for path in backup.list_backups(folder):
                try:
                    key = path.resolve()
                    mtime = path.stat().st_mtime_ns
                except OSError:
                    continue
                if key not in seen:
                    seen.add(key)
                    found.append((mtime, path, label))
        found.sort(key=lambda f: (f[0], f[1].name), reverse=True)
        return [(path, label) for _, path, label in found]

    def apply_read_only(self, read_only):
        """Nothing here is blocked: backups, restores, folders and activation must always work."""

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action, keep_edits=False):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._refresh_lists() if keep_edits else self.refresh()

    def save_paths(self):
        settings = self.session.settings
        before = (settings.backup_dir, settings.extra_backup_dir)
        failed = []

        def run():
            backup_dir, extra = self.backup_dir_edit.text().strip(), self.extra_dir_edit.text().strip()
            try:
                for folder in (backup_dir, extra):
                    if folder:
                        Path(folder).mkdir(parents=True, exist_ok=True)
                settings.backup_dir, settings.extra_backup_dir = backup_dir, extra
                self.session.save_settings()
            except Exception:
                settings.backup_dir, settings.extra_backup_dir = before  # never leave memory ahead of disk
                failed.append(True)
                raise
        self._guarded(run, keep_edits=True)
        if not failed:
            self.refresh()

    def backup_now(self):
        def run():
            result = self.session.backup_now()
            message = tr("data.backup_done", name=result.path.name)
            if result.extra_error:
                message += "\n" + tr("data.extra_failed")
            self.status_label.setText(message)
        self._guarded(run)

    def restore_selected(self):
        item = self.backups_list.currentItem()
        if item is not None:
            self._restore(item.data(Qt.ItemDataRole.UserRole))

    def restore_from_file(self):
        """Restore a backup from anywhere (the second location on a new PC, a USB stick, an e-mailed copy)."""
        path = self._pick_backup_file()
        if path:
            self._restore(path)

    def _restore(self, path):
        restart = []

        def run():
            if not self._confirm("data.restore_confirm"):
                return
            had_shop = self.session.has_shop()
            self.session.restore_from(path)
            self.status_label.setText(tr("data.restored"))
            if not had_shop and self.session.has_shop():
                restart.append(True)  # recovery mode: the app was started without a shop
        self._guarded(run)
        if restart:
            self._notify_restart()

    def activate(self):
        def run():
            state = self.session.activate(self.key_edit.toPlainText().strip())
            if state.status == "invalid":
                self.status_label.setText(tr("act.invalid"))
            else:
                self.key_edit.clear()
                self.status_label.setText(tr("data.key_ok") if state.status == "active" else tr("data.key_expired"))
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _confirm(self, key):
        return helpers.confirm(self, key)

    def _pick_backup_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("data.pick_file"), str(self.session.backup_dir), "*.db")
        return path

    def _pick_folder(self, start):
        return QFileDialog.getExistingDirectory(self, tr("common.browse"), start)

    def _notify_restart(self):
        helpers.inform(self, "data.restart_notice")
        self.window().close()
