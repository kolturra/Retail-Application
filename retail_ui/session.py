import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from retail import clock, db, guard, i18n
from retail import license as lic
from retail.services import backup, shop
from retail_ui import settings as ui_settings

log = logging.getLogger("retail_ui")


class AppSession(QObject):
    """Owns the shop connection, licence state and the signals screens listen to."""

    language_changed = Signal(str)
    read_only_changed = Signal(bool)
    data_changed = Signal()

    def __init__(self, paths, settings, conn, license_state, *, public_key, machine_id):
        super().__init__()
        self.paths = paths
        self.settings = settings
        self.conn = conn
        self.license = license_state
        self.public_key = public_key
        self.machine_id = machine_id

    # --- state -------------------------------------------------------------
    @property
    def read_only(self) -> bool:
        return self.license.read_only

    @property
    def backup_dir(self) -> Path:
        return Path(self.settings.backup_dir) if self.settings.backup_dir else self.paths.backup_dir

    def has_shop(self) -> bool:
        return self.conn.execute("SELECT 1 FROM shop WHERE id = 1").fetchone() is not None

    def shop(self):
        return shop.get_shop(self.conn)

    # --- settings / language ---------------------------------------------------
    def save_settings(self) -> None:
        ui_settings.save(self.paths.settings_path, self.settings)

    def set_language(self, code: str) -> None:
        shop.update_shop(self.conn, language=code)  # validates the code and persists it
        i18n.set_language(code)
        self.language_changed.emit(code)

    def notify_changed(self) -> None:
        self.data_changed.emit()

    # --- licence ---------------------------------------------------------------
    def refresh_license(self) -> None:
        self.license = lic.apply_license(self.paths.license_path, self.public_key, self.machine_id)
        self.read_only_changed.emit(self.license.read_only)

    def activate(self, key: str):
        """Verify first; only a valid key is saved. An invalid key changes nothing."""
        state = lic.verify_key(key, self.machine_id, self.public_key, clock.today())
        if state.status == "invalid":
            return state
        lic.save_key(self.paths.license_path, key)
        self.refresh_license()
        return self.license

    # --- backup / restore ------------------------------------------------------
    def _extra_dir(self):
        return Path(self.settings.extra_backup_dir) if self.settings.extra_backup_dir else None

    def backup_now(self):
        return backup.backup_now(self.conn, self.backup_dir, extra_dir=self._extra_dir())

    def backup_if_due(self) -> None:
        """Daily backup; a failure is logged and never blocks the caller (e.g. closing the app)."""
        try:
            if backup.daily_backup_due(self.backup_dir, clock.today()):
                self.backup_now()
        except Exception:
            log.exception("daily backup failed")

    def restore_from(self, path):
        """Replace the live database with a backup. The connection is closed for the swap and always
        reopened, so after a failed restore the app keeps running on the old data."""
        self.conn.close()
        try:
            return backup.restore(path, self.paths.db_path, self.backup_dir, max_version=db.latest_version())
        finally:
            self.conn = db.open_shop(self.paths.db_path, self.backup_dir)
            guard.set_read_only(self.license.read_only)
            self.data_changed.emit()

    def close(self) -> None:
        self.conn.close()
