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
    restored = Signal()          # the database was replaced: remembered row ids are meaningless now

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
        """Switch the screen language. After the licence expires the database is read-only, so the
        choice then lasts for this session only instead of being refused."""
        try:
            shop.update_shop(self.conn, language=code)  # validates the code and persists it
        except guard.ReadOnlyError:
            log.info("licence expired: language %s applied for this session only", code)
        i18n.set_language(code)  # raises ValueError for an unsupported code, before anything is emitted
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
        original = None
        result = None
        try:
            result = backup.restore(path, self.paths.db_path, self.backup_dir, max_version=db.latest_version())
        except Exception as exc:
            original = exc
        try:
            self.conn = db.open_shop(self.paths.db_path, self.backup_dir)
        except Exception as reopen_error:
            log.exception("could not reopen the database after restore")
            raise (original if original is not None else reopen_error)
        guard.set_read_only(self.license.read_only)
        if original is None:
            self.restored.emit()  # first, so nobody keeps a bill id from the replaced data
        new_language = None
        if self.has_shop():
            code = self.shop()["language"]
            if code != i18n.get_language():
                i18n.set_language(code)
                new_language = code
        self.data_changed.emit()
        if new_language is not None:
            self.language_changed.emit(new_language)  # after the data, so screens retranslate current data
        if original is not None:
            raise original
        return result

    def close(self) -> None:
        self.conn.close()
