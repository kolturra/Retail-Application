import logging
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication

from retail import db, i18n, public_key, segments
from retail import license as lic
from retail_ui import APP_NAME, fonts
from retail_ui.bootstrap import bootstrap
from retail_ui.dialogs.activation import request_activation
from retail_ui.dialogs.onboarding import run_onboarding
from retail_ui.errors import show_error
from retail_ui.main_window import MainWindow
from retail_ui.paths import AppPaths
from retail_ui.screens import registry
from retail_ui.screens.data import DataScreen

log = logging.getLogger("retail_ui")


def configure_logging(paths) -> logging.Handler:
    handler = RotatingFileHandler(paths.log_path, maxBytes=500_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    return handler


def install_excepthook():
    """Unhandled errors are logged and shown as a translated message, never as a traceback."""
    def hook(exc_type, exc, tb):
        log.critical("unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            show_error(None, exc)
        except Exception:
            log.exception("could not show the error to the user")

    sys.excepthook = hook
    return hook


def selftest() -> int:
    """Used by the installer build: 0 = the packaged app can open a database and load its data files.
    Works only in a temporary folder; never touches the real app data or any key."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            paths.ensure()
            conn = db.open_shop(paths.db_path, paths.backup_dir)
            try:
                if db.schema_version(conn) != db.latest_version():
                    raise RuntimeError("database migration did not complete")
            finally:
                conn.close()
        if len(public_key.PUBLIC_KEY) != 32:
            raise RuntimeError("the embedded licence public key is not 32 bytes")
        try:
            for code in i18n.LANGUAGES:
                i18n.set_language(code)
                i18n.tr("bill.total")
        finally:
            i18n.set_language(i18n.DEFAULT_LANGUAGE)
        for name in segments.list_templates():
            segments.load(name)
        return 0
    except Exception as exc:
        print(f"selftest failed: {exc}", file=sys.stderr)
        return 1


def build_window(session) -> MainWindow:
    """All nine screens normally; without a shop (recovery mode after an expired licence) only
    Backup & Licence is offered, with an explanation, so the owner can restore or re-activate."""
    if session.has_shop():
        return MainWindow(session, registry.all_screens())
    return MainWindow(session, [DataScreen], notice_key="app.recovery_notice")


def _run_event_loop(qt_app) -> int:
    return qt_app.exec()  # replaced in tests: nothing in the suite may run a real event loop


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    qt_app = QApplication.instance() or QApplication(argv)
    qt_app.setApplicationName(APP_NAME)
    paths = AppPaths.default()
    paths.ensure()
    handler = configure_logging(paths)
    old_hook = sys.excepthook
    install_excepthook()
    session = None
    try:
        fonts.apply_language_font(qt_app, "en")
        session = bootstrap(paths, public_key=public_key.PUBLIC_KEY, machine_id=lic.get_machine_id(),
                            request_activation=request_activation, run_onboarding=run_onboarding)
        if session is None:
            return 0
        fonts.apply_language_font(qt_app, i18n.get_language())
        window = build_window(session)
        window.show()
        return _run_event_loop(qt_app)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                log.exception("could not close the database")
        sys.excepthook = old_hook
        log.removeHandler(handler)
        handler.close()
