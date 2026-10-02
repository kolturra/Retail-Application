import logging
import sys

import pytest

from retail import guard, i18n
from retail import license as lic
from retail.services import billing, items, parties, stock
from retail_ui import app, errors
from retail_ui.main_window import MainWindow
from retail_ui.screens import registry
from retail_ui.screens.data import DataScreen


@pytest.fixture(autouse=True)
def _reset():
    yield
    i18n.set_language("en")
    guard.set_read_only(False)
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    if QApplication.instance():
        QApplication.instance().setFont(QFont())


def test_registry_has_every_screen_in_order():
    assert [cls.nav_key for cls in registry.all_screens()] == [
        "nav.counter", "nav.bills", "nav.items", "nav.stock", "nav.parties", "nav.reports", "nav.staff",
        "nav.settings", "nav.data"]


def test_selftest_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert app.selftest() == 0
    assert app.main(["retail", "--selftest"]) == 0
    assert not (tmp_path / "RetailApp").exists()          # it works in a throw-away folder


def test_selftest_reports_failure(monkeypatch, capsys):
    from retail import segments
    monkeypatch.setattr(segments, "list_templates", lambda: ["does-not-exist"])
    assert app.selftest() == 1
    assert "selftest" in capsys.readouterr().err.lower()


def test_logging_goes_to_a_rotating_file(paths):
    handler = app.configure_logging(paths)
    try:
        logging.getLogger("retail_ui").info("hello log")
        handler.flush()
        assert "hello log" in paths.log_path.read_text(encoding="utf-8")
    finally:
        logging.getLogger("retail_ui").removeHandler(handler)
        handler.close()


def test_the_exception_hook_logs_and_shows_the_translated_message(monkeypatch, caplog):
    shown = []
    monkeypatch.setattr(app, "show_error", lambda parent, exc: shown.append(errors.message_for(exc)))
    old = sys.excepthook
    try:
        hook = app.install_excepthook()
        assert sys.excepthook is hook
        with caplog.at_level(logging.CRITICAL, logger="retail_ui"):
            hook(RuntimeError, RuntimeError("boom"), None)
        assert shown == [i18n.tr("err.unexpected")] and "unhandled" in caplog.text.lower()
    finally:
        sys.excepthook = old


def test_the_exception_hook_survives_a_failure_while_reporting(monkeypatch):
    monkeypatch.setattr(app, "show_error", lambda parent, exc: (_ for _ in ()).throw(RuntimeError("no GUI")))
    old = sys.excepthook
    try:
        app.install_excepthook()(RuntimeError, RuntimeError("boom"), None)   # must not raise
    finally:
        sys.excepthook = old


def build_window(make_session, qtbot, template="grocery"):
    session = make_session(template=template)
    window = MainWindow(session, registry.all_screens())
    qtbot.addWidget(window)
    window.show()
    return session, window


@pytest.mark.parametrize("template", ["grocery", "electronics"])
def test_every_screen_opens_in_every_language_and_in_read_only(make_session, qtbot, template):
    session, window = build_window(make_session, qtbot, template)
    conn = session.conn
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, barcodes=["8901"])
    stock.record(conn, item, 9000, "opening")
    parties.create_party(conn, name="Ravi", phone="9876543210")
    assert window.nav.count() == 9
    for code in ("en", "hi", "te", "en"):
        session.set_language(code)
        for row in range(window.nav.count()):
            window.nav.setCurrentRow(row)
            assert window.nav.item(row).text() == i18n.tr(window.screens[row].nav_key)
    session.license = lic.LicenseState("expired", buyer="B", expires="2020-01-01", plan="standard")
    guard.set_read_only(True)
    session.read_only_changed.emit(True)
    assert not window.banner.isHidden()
    for row in range(window.nav.count()):
        window.nav.setCurrentRow(row)
    window.close()


def test_a_complete_sale_through_the_real_window(make_session, qtbot):
    session, window = build_window(make_session, qtbot)
    conn = session.conn
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, barcodes=["8901"])
    stock.record(conn, item, 9000, "opening")
    counter = window.screens[0]
    counter._show_error = lambda exc: pytest.fail(str(exc))
    counter._ask_payments = lambda total, party_id: [("cash", total)]
    counter.entry.setText("2*8901")
    counter.entry.returnPressed.emit()
    counter.pay()
    assert billing.get_bill(conn, counter.last_bill_id)["bill"]["bill_no"] == "S000001"
    window.nav.setCurrentRow(1)                                    # the Bills screen lists it
    assert window.screens[1].model.rowCount() == 1
    window.close()
    assert list(session.backup_dir.glob("daily-*.db"))             # closing took the daily backup


def recovery_session(make_session):
    """No shop and an expired licence, as bootstrap leaves it when only a restore is possible."""
    session = make_session(with_shop=False)
    session.license = lic.LicenseState("expired", buyer="B", expires="2020-01-01", plan="standard")
    guard.set_read_only(True)
    return session


def test_recovery_mode_offers_only_backup_and_licence(make_session, qtbot):
    session = recovery_session(make_session)
    assert not session.has_shop() and session.read_only
    window = app.build_window(session)
    qtbot.addWidget(window)
    window.show()
    assert [type(s) for s in window.screens] == [DataScreen]
    assert window.nav.count() == 1
    assert not window.notice.isHidden()
    assert window.notice.text() == i18n.tr("app.recovery_notice")
    english = i18n.tr("app.recovery_notice")
    for code in ("hi", "te"):
        i18n.set_language(code)
        assert i18n.tr("app.recovery_notice") != english
    window.close()                                                  # closing without a shop must not raise


def test_a_shop_gets_the_full_window_without_a_notice(make_session, qtbot):
    session = make_session()
    window = app.build_window(session)
    qtbot.addWidget(window)
    assert window.nav.count() == 9 and window.notice.isHidden()
    window.close()


@pytest.fixture
def main_env(monkeypatch, paths, qapp):
    monkeypatch.setattr(app.AppPaths, "default", classmethod(lambda cls: paths))
    ran = []
    monkeypatch.setattr(app, "_run_event_loop", lambda qt_app: ran.append(True) or 0)
    old = sys.excepthook
    yield ran
    sys.excepthook = old


def test_main_returns_zero_when_the_user_quits_at_activation(monkeypatch, main_env):
    monkeypatch.setattr(app, "bootstrap", lambda *a, **k: None)
    assert app.main(["retail"]) == 0
    assert main_env == []                                           # no window, no event loop


def test_main_runs_the_window_closes_the_session_and_releases_the_log(monkeypatch, main_env, make_session):
    session = make_session()
    monkeypatch.setattr(app, "bootstrap", lambda *a, **k: session)
    before = list(logging.getLogger("retail_ui").handlers)
    old_hook = sys.excepthook
    fonts_seen = []
    monkeypatch.setattr(app.fonts, "apply_language_font", lambda qt_app, code: fonts_seen.append(code))
    built = []
    real_build = app.build_window
    monkeypatch.setattr(app, "build_window", lambda s: built.append(list(fonts_seen)) or real_build(s))
    assert app.main(["retail"]) == 0
    assert main_env == [True]
    assert fonts_seen == ["en", "en"] and built == [["en", "en"]]   # shop language applied before the window
    assert sys.excepthook is old_hook                               # restored by main itself
    assert logging.getLogger("retail_ui").handlers == before        # the log handler did not leak
    with pytest.raises(Exception):
        session.conn.execute("SELECT 1")                            # the session was closed


def test_main_survives_recovery_mode(monkeypatch, main_env, make_session):
    session = recovery_session(make_session)
    monkeypatch.setattr(app, "bootstrap", lambda *a, **k: session)
    windows = []
    real = app.build_window
    monkeypatch.setattr(app, "build_window", lambda s: windows.append(real(s)) or windows[-1])
    try:
        assert app.main(["retail"]) == 0 and main_env == [True]
        assert [type(s) for s in windows[0].screens] == [DataScreen]
    finally:
        for w in windows:
            w.close()
            w.deleteLater()


def test_a_failing_backup_never_blocks_closing(make_session, qtbot, monkeypatch):
    session, window = build_window(make_session, qtbot)
    from retail.services import backup
    monkeypatch.setattr(backup, "backup_now", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    window.close()                                                  # must not raise
    assert not window.isVisible()


def test_main_logs_and_shows_the_translated_message_when_bootstrap_fails(monkeypatch, main_env, paths):
    shown = []
    monkeypatch.setattr(app, "show_error", lambda parent, exc: shown.append(errors.message_for(exc)))
    monkeypatch.setattr(app, "bootstrap", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("corrupt db")))
    before = list(logging.getLogger("retail_ui").handlers)
    old_hook = sys.excepthook
    assert app.main(["retail"]) == 1
    assert shown == [i18n.tr("err.unexpected")]
    assert "corrupt db" in paths.log_path.read_text(encoding="utf-8")   # logged before the handler was removed
    assert logging.getLogger("retail_ui").handlers == before and sys.excepthook is old_hook


def test_main_cleans_up_when_the_event_loop_raises(monkeypatch, main_env, make_session):
    session = make_session()
    monkeypatch.setattr(app, "bootstrap", lambda *a, **k: session)
    monkeypatch.setattr(app, "show_error", lambda parent, exc: None)
    monkeypatch.setattr(app, "_run_event_loop", lambda qt_app: (_ for _ in ()).throw(RuntimeError("loop")))
    before = list(logging.getLogger("retail_ui").handlers)
    old_hook = sys.excepthook
    assert app.main(["retail"]) == 1
    with pytest.raises(Exception):
        session.conn.execute("SELECT 1")
    assert logging.getLogger("retail_ui").handlers == before and sys.excepthook is old_hook


def test_main_survives_a_failing_error_dialog(monkeypatch, main_env):
    monkeypatch.setattr(app, "show_error", lambda parent, exc: (_ for _ in ()).throw(RuntimeError("no GUI")))
    monkeypatch.setattr(app, "bootstrap", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert app.main(["retail"]) == 1


def test_the_exception_hook_delegates_interrupts_to_the_previous_hook(monkeypatch):
    shown, previous = [], []
    monkeypatch.setattr(app, "show_error", lambda parent, exc: shown.append(exc))
    old = sys.excepthook
    sys.excepthook = lambda *a: previous.append(a[0])
    try:
        hook = app.install_excepthook()
        hook(KeyboardInterrupt, KeyboardInterrupt(), None)
        hook(SystemExit, SystemExit(0), None)
    finally:
        sys.excepthook = old
    assert previous == [KeyboardInterrupt, SystemExit] and shown == []


def test_selftest_fails_when_a_translation_misses_a_key(monkeypatch, capsys):
    catalogue = dict(i18n._load("te"))
    catalogue.pop("err.unexpected")
    monkeypatch.setitem(i18n._catalogues, "te", catalogue)
    assert app.selftest() == 1
    assert "err.unexpected" in capsys.readouterr().err
