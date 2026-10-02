import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

import retail
from retail import i18n
from retail import license as lic
from retail.services import items
from retail_ui import fmt, vendor
from retail_ui.screens.data import DataScreen
from tools import license_issuer


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = DataScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._confirm = lambda key: True
    sc.refresh()
    return sc


def test_licence_and_about_information(screen):
    assert "Test Shop" in screen.buyer_label.text() and "31-12-2099" in screen.expires_label.text()
    assert i18n.tr("data.status_active") in screen.state_label.text()
    assert vendor.VENDOR_PHONE in screen.about_label.text()
    assert f"v{retail.__version__}" in screen.about_label.text()


def test_expired_licence_is_labelled_read_only(screen):
    screen.session.license = lic.LicenseState("expired", buyer="Test Shop", expires="2020-01-01", plan="standard")
    screen.refresh()
    assert i18n.tr("data.status_expired") in screen.state_label.text()


def test_backup_now_creates_a_file_lists_it_and_says_so(screen):
    screen.backup_now()
    assert screen.backups_list.count() == 1
    name = next(screen.session.backup_dir.glob("daily-*.db")).name
    assert name in screen.status_label.text() and name in screen.backups_list.item(0).text()


def test_a_missing_second_location_is_reported_without_failing_the_backup(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen.session.settings.extra_backup_dir = str(blocker / "usb")
    screen.backup_now()
    assert screen.backups_list.count() == 1 and i18n.tr("data.extra_failed") in screen.status_label.text()


def test_save_paths_creates_folders_and_persists(screen, tmp_path):
    from retail_ui import settings as ui_settings
    screen.backup_dir_edit.setText(str(tmp_path / "bk"))
    screen.extra_dir_edit.setText(str(tmp_path / "usb"))
    screen.save_paths()
    assert (tmp_path / "bk").is_dir() and (tmp_path / "usb").is_dir()
    saved = ui_settings.load(screen.session.paths.settings_path)
    assert (saved.backup_dir, saved.extra_backup_dir) == (str(tmp_path / "bk"), str(tmp_path / "usb"))
    assert screen.errors == []


def test_unwritable_path_is_reported_and_not_saved(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen.backup_dir_edit.setText(str(blocker / "sub"))
    screen.save_paths()
    assert len(screen.errors) == 1 and screen.session.settings.backup_dir == ""


def test_restore_replaces_the_data_after_confirmation(screen):
    conn = screen.session.conn
    screen.backup_now()
    items.create_item(conn, name="Added later", sell_price_paise=1)
    screen.backups_list.setCurrentRow(0)
    asked = []
    screen._confirm = lambda key: asked.append(key) or True
    screen.restore_selected()
    assert asked == ["data.restore_confirm"] and items.list_items(screen.session.conn) == []
    assert i18n.tr("data.restored") in screen.status_label.text() and screen.errors == []


def test_declining_the_confirmation_changes_nothing(screen):
    screen.backup_now()
    items.create_item(screen.session.conn, name="Keep", sell_price_paise=1)
    screen.backups_list.setCurrentRow(0)
    screen._confirm = lambda key: False
    screen.restore_selected()
    assert [r["name"] for r in items.list_items(screen.session.conn)] == ["Keep"]


def test_restoring_a_corrupt_file_is_reported_and_keeps_the_data(screen):
    items.create_item(screen.session.conn, name="Keep", sell_price_paise=1)
    bad = screen.session.backup_dir / "daily-20200101-000000.db"
    bad.write_bytes(b"this is not a database")
    screen.refresh()
    screen.backups_list.setCurrentRow(0)
    screen.restore_selected()
    assert len(screen.errors) == 1 and [r["name"] for r in items.list_items(screen.session.conn)] == ["Keep"]


def test_restore_needs_a_selection(screen):
    screen._confirm = lambda key: pytest.fail("nothing is selected")
    screen.restore_selected()


def test_activating_a_valid_key_updates_the_licence(screen, keypair, machine_id):
    key = license_issuer.issue(keypair[0], machine=machine_id, buyer="New Buyer", expires="2098-06-01")
    screen.key_edit.setPlainText(f"  {key}\n")
    screen.activate()
    assert "01-06-2098" in screen.expires_label.text() and screen.key_edit.toPlainText() == ""
    assert i18n.tr("data.key_ok") in screen.status_label.text()


def test_an_invalid_key_changes_nothing(screen):
    screen.key_edit.setPlainText("garbage")
    screen.activate()
    assert i18n.tr("act.invalid") in screen.status_label.text() and "31-12-2099" in screen.expires_label.text()


def test_copy_machine_id(screen):
    screen.copy_button.click()
    assert QGuiApplication.clipboard().text() == screen.session.machine_id


def test_everything_here_stays_available_when_read_only_and_retranslates(screen):
    screen.apply_read_only(True)
    for name in ("save_paths_button", "backup_now_button", "restore_button", "activate_button", "copy_button"):
        assert getattr(screen, name).isEnabled(), name
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.backup_now_button.text() == i18n.tr("data.backup_now")


# --- carry-forward rulings: recovery mode, hooks, language, activation errors ----------------------

def _recovery_screen(make_session, qtbot, snapshot_from=None):
    from retail import guard
    session = make_session(with_shop=False)
    if snapshot_from is not None:  # built while the guard is still open
        _shop_snapshot(snapshot_from, session.backup_dir)
    session.license = lic.LicenseState("expired", buyer="Test Shop", expires="2020-01-01", plan="standard")
    guard.set_read_only(True)
    sc = DataScreen(session)
    qtbot.addWidget(sc)
    sc.errors, sc.restarts = [], []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._confirm = lambda key: True
    sc._notify_restart = lambda: sc.restarts.append(True)
    sc.refresh()
    return sc


def _shop_snapshot(tmp_path, into):
    from retail import db
    from retail.services import backup, shop
    other = db.open_shop(tmp_path / "other.db", tmp_path / "other_bk")
    try:
        shop.setup_shop(other, name="Restored Shop", state_code="36")
        result = backup.backup_now(other, tmp_path / "other_out")
    finally:
        other.close()
    into.mkdir(parents=True, exist_ok=True)
    target = into / "daily-20200101-000000.db"
    target.write_bytes(result.path.read_bytes())
    return target


def test_recovery_mode_without_a_shop_stays_fully_enabled(make_session, qtbot):
    sc = _recovery_screen(make_session, qtbot)
    assert not sc.session.has_shop() and sc.session.read_only
    sc.apply_read_only(True)
    for name in ("save_paths_button", "backup_now_button", "restore_button", "activate_button", "copy_button"):
        assert getattr(sc, name).isEnabled(), name
    assert i18n.tr("data.status_expired") in sc.state_label.text() and sc.errors == []


def test_restore_that_creates_a_shop_asks_for_a_restart(make_session, qtbot, tmp_path):
    sc = _recovery_screen(make_session, qtbot, snapshot_from=tmp_path)
    sc.backups_list.setCurrentRow(0)
    sc.restore_selected()
    assert sc.errors == [] and sc.session.has_shop() and sc.restarts == [True]


def test_restore_on_a_normal_session_does_not_ask_for_a_restart(screen):
    screen.restarts = []
    screen._notify_restart = lambda: screen.restarts.append(True)
    screen.backup_now()
    screen.backups_list.setCurrentRow(0)
    screen.restore_selected()
    assert screen.restarts == []


def test_restore_refreshes_from_the_new_database(screen):
    screen.backup_now()
    screen.backups_list.setCurrentRow(0)
    seen = []
    screen.session.data_changed.connect(lambda: seen.append(True))
    screen.restore_selected()
    assert seen


def test_labels_retranslate_and_differ_from_english(screen):
    en = (screen.backup_now_button.text(), screen.state_label.text(), screen.buyer_label.text())
    screen.status_label.setText("stale")
    i18n.set_language("hi")
    screen.retranslate()
    hi = (screen.backup_now_button.text(), screen.state_label.text(), screen.buyer_label.text())
    assert all(a != b for a, b in zip(en, hi)) and screen.status_label.text() == ""


def test_activation_errors_go_through_the_hook_and_never_leak_the_key(screen, monkeypatch, caplog, keypair, machine_id):
    key = license_issuer.issue(keypair[0], machine=machine_id, buyer="B", expires="2098-06-01")

    def boom(path, k):
        raise OSError("disk full")
    monkeypatch.setattr(lic, "save_key", boom)
    screen.key_edit.setPlainText(key)
    with caplog.at_level("DEBUG"):
        screen.activate()
    assert len(screen.errors) == 1 and isinstance(screen.errors[0], OSError)
    assert key not in caplog.text and "31-12-2099" in screen.expires_label.text()


def test_non_ascii_key_is_invalid_not_a_crash(screen):
    screen.key_edit.setPlainText("é.é")
    screen.activate()
    assert screen.errors == [] and i18n.tr("act.invalid") in screen.status_label.text()


def test_registry_ends_with_the_data_screen_and_has_nine_screens():
    from retail_ui.screens.registry import all_screens
    assert all_screens()[-1] is DataScreen and len(all_screens()) == 9


# --- fix round 1 ---------------------------------------------------------------------------------

def test_activating_an_expired_key_says_so_and_stays_read_only(screen, keypair, machine_id, monkeypatch):
    from retail import clock
    from datetime import date
    key = license_issuer.issue(keypair[0], machine=machine_id, buyer="Old", expires="2098-06-01")
    monkeypatch.setattr(clock, "today", lambda: date(2099, 1, 1))  # the key is valid but already expired
    screen.key_edit.setPlainText(key)
    screen.activate()
    assert screen.status_label.text() == i18n.tr("data.key_expired") != i18n.tr("data.key_ok")
    assert i18n.tr("data.status_expired") in screen.state_label.text() and screen.session.read_only


def test_failed_save_paths_keeps_typed_text_and_reverts_memory(screen, monkeypatch, tmp_path):
    def boom():
        raise OSError("disk")
    monkeypatch.setattr(screen.session, "save_settings", boom)
    screen.backup_dir_edit.setText(str(tmp_path / "typed"))
    screen.save_paths()
    assert len(screen.errors) == 1
    assert screen.backup_dir_edit.text() == str(tmp_path / "typed")
    assert screen.session.settings.backup_dir == "" and screen.session.settings.extra_backup_dir == ""


def test_backup_rows_show_date_and_size_and_restore_uses_the_path(screen):
    from datetime import date
    screen.backup_now()
    text = screen.backups_list.item(0).text()
    assert fmt.date_text(date.today().isoformat()) in text and "KB" in text
    assert screen.backups_list.item(0).data(Qt.ItemDataRole.UserRole).endswith(".db")


def test_backup_now_works_in_recovery_mode(make_session, qtbot):
    sc = _recovery_screen(make_session, qtbot)
    sc.backup_now()
    assert sc.errors == [] and sc.backups_list.count() == 1


# --- I4: both backup locations and restore-from-file --------------------------------------------
def test_backups_from_both_locations_are_listed_once_and_labelled(screen, tmp_path):
    screen.session.settings.extra_backup_dir = str(tmp_path / "usb")
    result = screen.session.backup_now()               # writes to the main folder and the second location
    only_usb = tmp_path / "usb" / "daily-20200101-000000.db"
    only_usb.write_bytes(result.path.read_bytes())
    screen.refresh()
    rows = [screen.backups_list.item(i).text() for i in range(screen.backups_list.count())]
    assert len(rows) == 3
    assert sum(i18n.tr("data.loc_extra") in r for r in rows) == 2
    assert sum(i18n.tr("data.loc_primary") in r for r in rows) == 1
    screen.session.settings.extra_backup_dir = str(screen.session.backup_dir)   # same folder twice: no duplicates
    screen.refresh()
    assert screen.backups_list.count() == 1


def test_restoring_the_second_location_copy_from_the_list(screen, tmp_path):
    screen.session.settings.extra_backup_dir = str(tmp_path / "usb")
    screen.session.backup_now()
    items.create_item(screen.session.conn, name="Later", sell_price_paise=1)
    for f in screen.session.backup_dir.glob("*.db"):
        f.unlink()                                      # the main folder is gone; only the USB copy remains
    screen.refresh()
    assert screen.backups_list.count() == 1 and i18n.tr("data.loc_extra") in screen.backups_list.item(0).text()
    screen.backups_list.setCurrentRow(0)
    screen.restore_selected()
    assert screen.errors == [] and items.list_items(screen.session.conn) == []


def test_restore_from_file_confirms_then_restores(screen, tmp_path):
    snapshot = screen.session.backup_now().path
    elsewhere = tmp_path / "mail" / "shop-copy.db"
    elsewhere.parent.mkdir()
    elsewhere.write_bytes(snapshot.read_bytes())
    items.create_item(screen.session.conn, name="Later", sell_price_paise=1)
    asked = []
    screen._confirm = lambda key: asked.append(key) or True
    screen._pick_backup_file = lambda: str(elsewhere)
    screen.restore_from_file()
    assert asked == ["data.restore_confirm"] and items.list_items(screen.session.conn) == [] and screen.errors == []


def test_restore_from_file_cancelled_or_corrupt(screen, tmp_path):
    items.create_item(screen.session.conn, name="Keep", sell_price_paise=1)
    screen._confirm = lambda key: pytest.fail("no file was chosen")
    screen._pick_backup_file = lambda: ""
    screen.restore_from_file()
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"nope")
    screen._confirm = lambda key: True
    screen._pick_backup_file = lambda: str(bad)
    screen.restore_from_file()
    assert len(screen.errors) == 1 and [r["name"] for r in items.list_items(screen.session.conn)] == ["Keep"]


def test_restore_from_file_works_in_read_only_mode(screen):
    from retail import guard
    snapshot = screen.session.backup_now().path
    screen.session.license = lic.LicenseState("expired", buyer="B", expires="2020-01-01", plan="standard")
    guard.set_read_only(True)
    screen.apply_read_only(True)
    assert screen.restore_file_button.isEnabled() and screen.restore_button.isEnabled()
    screen._pick_backup_file = lambda: str(snapshot)
    screen.restore_from_file()
    assert screen.errors == [] and i18n.tr("data.restored") in screen.status_label.text()


def test_recovery_mode_restores_from_a_file_and_asks_for_a_restart(make_session, qtbot):
    donor = make_session()
    snapshot = donor.backup_now().path
    donor.close()
    donor.paths.db_path.unlink()
    session = make_session(with_shop=False)
    sc = DataScreen(session)
    qtbot.addWidget(sc)
    sc.errors, restarts = [], []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._confirm = lambda key: True
    sc._pick_backup_file = lambda: str(snapshot)
    sc._notify_restart = lambda: restarts.append(True)
    assert not session.has_shop()
    sc.restore_from_file()
    assert sc.errors == [] and session.has_shop() and restarts == [True]


# --- I5: an unusable custom folder never blocks the app --------------------------------------------
def test_an_unusable_backup_folder_falls_back_to_the_default_and_says_so(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen.session.settings.backup_dir = str(blocker / "E_drive")
    screen.refresh()
    assert screen.session.backup_dir == screen.session.paths.backup_dir and screen.session.backup_dir_fallback
    assert i18n.tr("data.folder_fallback", path=screen.session.paths.backup_dir) == screen.folder_label.text()
    screen.backup_now()
    assert screen.errors == [] and list(screen.session.paths.backup_dir.glob("daily-*.db"))


# --- M7: a backup without a shop is refused in normal mode -------------------------------------------
def test_a_backup_with_no_shop_row_is_refused_in_normal_mode(screen, tmp_path):
    import shutil
    import sqlite3
    from retail.services import backup as backup_service
    snapshot = screen.session.backup_now().path
    shopless = tmp_path / "shopless.db"
    shutil.copy2(snapshot, shopless)
    raw = sqlite3.connect(shopless)
    for (name,) in raw.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='shop'").fetchall():
        raw.execute(f"DROP TRIGGER {name}")
    raw.execute("DELETE FROM shop")
    raw.commit()
    raw.close()
    items.create_item(screen.session.conn, name="Keep", sell_price_paise=1)
    screen._pick_backup_file = lambda: str(shopless)
    screen.restore_from_file()
    assert len(screen.errors) == 1 and isinstance(screen.errors[0], backup_service.BackupError)
    assert screen.session.has_shop() and [r["name"] for r in items.list_items(screen.session.conn)] == ["Keep"]
