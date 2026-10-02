import pytest
from PySide6.QtCore import Qt

from retail import i18n, license as lic
from retail.services import backup
from retail_ui import APP_NAME
from retail_ui.main_window import MainWindow
from retail_ui.widgets.base import RowsModel, Screen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        from PySide6.QtGui import QFont
        app.setFont(QFont())


class ScreenA(Screen):
    nav_key = "nav.counter"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.refreshed = self.retranslated = 0
        self.read_only_calls = []

    def refresh(self):
        self.refreshed += 1

    def retranslate(self):
        super().retranslate()
        self.retranslated += 1

    def apply_read_only(self, read_only):
        self.read_only_calls.append(read_only)


class ScreenB(ScreenA):
    nav_key = "nav.items"


def make_window(make_session, qtbot):
    session = make_session()
    window = MainWindow(session, [ScreenA, ScreenB])
    qtbot.addWidget(window)
    return session, window


def test_navigation_lists_translated_screens_and_refreshes_on_switch(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    assert [w.nav.item(i).text() for i in range(w.nav.count())] == [i18n.tr("nav.counter"), i18n.tr("nav.items")]
    first = w.screens[0].refreshed
    w.nav.setCurrentRow(1)
    assert w.stack.currentIndex() == 1 and w.screens[1].refreshed >= 1 and w.screens[0].refreshed == first


def test_data_changed_refreshes_the_visible_screen_only(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    w.nav.setCurrentRow(1)
    a, b = w.screens[0].refreshed, w.screens[1].refreshed
    session.notify_changed()
    assert w.screens[1].refreshed == b + 1 and w.screens[0].refreshed == a


def test_language_switch_retranslates_everything_and_applies_a_font(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    w.language_box.setCurrentIndex(w.language_box.findData("hi"))
    assert i18n.get_language() == "hi" and session.shop()["language"] == "hi"
    assert w.nav.item(0).text() == i18n.tr("nav.counter") != "Counter"
    assert all(s.retranslated == 1 for s in w.screens)
    assert w.status_label.text().startswith(session.shop()["name"])


def test_language_combo_follows_the_session_language(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    session.set_language("te")
    assert w.language_box.currentData() == "te"


def test_read_only_shows_a_banner_and_tells_every_screen(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    assert w.banner.isHidden()
    session.license = lic.LicenseState("expired", expires="2020-01-01")
    session.read_only_changed.emit(True)
    assert not w.banner.isHidden() and w.banner.text() == i18n.tr("license.read_only")
    assert all(s.read_only_calls[-1] is True for s in w.screens)
    session.license = lic.LicenseState("active", expires="2099-01-01")
    session.read_only_changed.emit(False)
    assert w.banner.isHidden() and all(s.read_only_calls[-1] is False for s in w.screens)


def test_window_starts_read_only_when_the_licence_is_expired(make_session, qtbot):
    session = make_session()
    session.license = lic.LicenseState("expired", expires="2020-01-01")
    w = MainWindow(session, [ScreenA])
    qtbot.addWidget(w)
    assert not w.banner.isHidden() and w.screens[0].read_only_calls == [True]


def test_closing_takes_the_daily_backup(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    assert not list(session.backup_dir.glob("daily-*.db"))
    w.close()
    assert len(list(session.backup_dir.glob("daily-*.db"))) == 1


def test_a_failing_backup_never_blocks_closing(make_session, qtbot, monkeypatch):
    session, w = make_window(make_session, qtbot)
    monkeypatch.setattr(backup, "backup_now", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    assert w.close() is True


def test_bind_retranslates_with_suffix_and_models_follow(make_session, qtbot):
    from PySide6.QtWidgets import QPushButton
    session = make_session()
    screen = ScreenA(session)
    qtbot.addWidget(screen)
    button = screen.bind(QPushButton(), "bill.pay", suffix=" (F12)")
    model = screen.track(RowsModel(["bill.item", "bill.total"]))
    assert button.text() == f"{i18n.tr('bill.pay')} (F12)"
    i18n.set_language("hi")
    screen.retranslate()
    assert button.text() == f"{i18n.tr('bill.pay')} (F12)" and button.text().startswith("भुगतान")
    assert model.headerData(1, Qt.Orientation.Horizontal) == i18n.tr("bill.total")


def test_rows_model_shape_ids_alignment_and_highlight(qtbot):
    m = RowsModel(["bill.item", "bill.total"])
    m.set_rows([("Soap", "₹10.00"), ("Rice", "₹5.00")], ids=[11, 22], right_cols=(1,), highlight=(1,))
    assert (m.rowCount(), m.columnCount()) == (2, 2)
    assert m.data(m.index(0, 0)) == "Soap" and m.id_at(1) == 22 and m.id_at(5) is None
    assert m.data(m.index(0, 1), Qt.ItemDataRole.TextAlignmentRole) & Qt.AlignmentFlag.AlignRight
    assert m.data(m.index(0, 0), Qt.ItemDataRole.BackgroundRole) is None
    assert m.data(m.index(1, 0), Qt.ItemDataRole.BackgroundRole) is not None


def test_window_tolerates_a_session_without_a_shop_and_no_screens(make_session, qtbot):
    session = make_session(with_shop=False)
    w = MainWindow(session, [ScreenA])
    qtbot.addWidget(w)
    assert w.status_label.text().startswith(APP_NAME)
    empty = MainWindow(session, [])
    qtbot.addWidget(empty)
    assert empty.screens == [] and empty.stack.count() == 0


# ---- M3: the licence is re-checked while the app stays open ----

def _past_expiry(monkeypatch):
    from datetime import date
    from retail import clock
    monkeypatch.setattr(clock, "today", lambda: date(2100, 1, 1))


def _real_window(make_session, qtbot, **kw):
    from retail_ui.screens.data import DataScreen
    from retail_ui.screens.items import ItemsScreen
    session = make_session()
    w = MainWindow(session, [ItemsScreen, DataScreen], **kw)
    qtbot.addWidget(w)
    return session, w


def test_expiry_while_running_flips_everything_read_only_on_the_timer_slot(make_session, qtbot, monkeypatch):
    session, w = _real_window(make_session, qtbot)
    items_screen, data_screen = w.screens
    assert w.banner.isHidden() and items_screen.add_button.isEnabled()
    _past_expiry(monkeypatch)
    w._check_license()
    assert session.read_only and not w.banner.isHidden()
    assert not items_screen.add_button.isEnabled()
    assert data_screen.isEnabled()            # the owner can still back up, restore and activate


def test_not_expired_stays_writable(make_session, qtbot):
    session, w = _real_window(make_session, qtbot)
    w._check_license()
    w.nav.setCurrentRow(1)
    w.nav.setCurrentRow(0)
    assert not session.read_only and w.banner.isHidden() and w.screens[0].add_button.isEnabled()


def test_navigating_rechecks_the_licence(make_session, qtbot, monkeypatch):
    session, w = _real_window(make_session, qtbot)
    _past_expiry(monkeypatch)
    w.nav.setCurrentRow(1)
    assert session.read_only and not w.banner.isHidden() and not w.screens[0].add_button.isEnabled()


def test_a_failing_recheck_never_raises(make_session, qtbot, monkeypatch):
    session, w = _real_window(make_session, qtbot)
    _past_expiry(monkeypatch)
    monkeypatch.setattr(session, "refresh_license", lambda: (_ for _ in ()).throw(OSError("disk")))
    w._check_license()
    w.nav.setCurrentRow(1)


def test_the_timer_runs_at_the_given_interval_and_stops_on_close(make_session, qtbot, monkeypatch):
    session, w = _real_window(make_session, qtbot, license_check_ms=50)
    assert w._license_timer.isActive() and w._license_timer.interval() == 50
    _past_expiry(monkeypatch)
    qtbot.waitUntil(lambda: session.read_only, timeout=3000)       # the timer itself did it
    w.close()
    assert not w._license_timer.isActive()


def test_default_interval_is_one_minute(make_session, qtbot):
    _, w = _real_window(make_session, qtbot)
    assert w._license_timer.interval() == 60_000
