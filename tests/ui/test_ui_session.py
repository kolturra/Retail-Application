from datetime import date

import pytest

from retail import guard, i18n
from retail.services import items, shop
from retail_ui import settings as ui_settings


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def test_session_exposes_shop_and_license(make_session):
    s = make_session()
    assert s.has_shop() and s.shop()["name"] == "Test Shop"
    assert s.license.status == "active" and s.read_only is False
    assert s.backup_dir == s.paths.backup_dir


def test_session_without_shop(make_session):
    s = make_session(with_shop=False)
    assert s.has_shop() is False


def test_set_language_persists_switches_catalogue_and_emits(make_session, qtbot):
    s = make_session()
    with qtbot.waitSignal(s.language_changed) as blocker:
        s.set_language("hi")
    assert blocker.args == ["hi"] and shop.get_shop(s.conn)["language"] == "hi" and i18n.get_language() == "hi"
    with pytest.raises(shop.ShopError):
        s.set_language("fr")
    assert i18n.get_language() == "hi"


def test_custom_backup_dir_and_settings_save(make_session, tmp_path):
    s = make_session()
    s.settings.backup_dir = str(tmp_path / "mybk")
    s.save_settings()
    assert s.backup_dir == tmp_path / "mybk"
    assert ui_settings.load(s.paths.settings_path).backup_dir == str(tmp_path / "mybk")


def test_backup_now_and_backup_if_due(make_session):
    s = make_session()
    result = s.backup_now()
    assert result.path.exists() and result.path.parent == s.backup_dir
    s.backup_if_due()          # a daily backup now exists -> no second daily file
    assert len([p for p in s.backup_dir.glob("daily-*.db")]) == 1


def test_backup_if_due_never_raises(make_session, monkeypatch):
    s = make_session()
    from retail.services import backup
    monkeypatch.setattr(backup, "backup_now", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    s.backup_if_due()          # must swallow the failure (and log it)


def test_extra_backup_dir_gets_a_copy(make_session, tmp_path):
    s = make_session()
    s.settings.extra_backup_dir = str(tmp_path / "usb")
    result = s.backup_now()
    assert (tmp_path / "usb" / result.path.name).exists() and result.extra_error is None


def test_restore_from_swaps_the_database_and_notifies(make_session, qtbot):
    s = make_session()
    snapshot = s.backup_now().path
    items.create_item(s.conn, name="Added later", sell_price_paise=100)
    with qtbot.waitSignal(s.data_changed):
        safety = s.restore_from(snapshot)
    assert safety is not None and safety.exists()
    assert [r["name"] for r in items.list_items(s.conn)] == []          # the new connection sees the old data
    items.create_item(s.conn, name="Works after restore", sell_price_paise=100)


def test_failed_restore_keeps_working_on_the_old_data(make_session, tmp_path):
    from retail.services import backup
    s = make_session()
    items.create_item(s.conn, name="Keep me", sell_price_paise=100)
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database")
    with pytest.raises(backup.BackupError):
        s.restore_from(bad)
    assert [r["name"] for r in items.list_items(s.conn)] == ["Keep me"]   # connection reopened on the old data


def test_activate_saves_only_valid_keys_and_emits(make_session, keypair, machine_id, qtbot):
    from retail import license as lic
    from tools import license_issuer
    s = make_session(expires="2099-12-31")
    good_before = lic.load_key(s.paths.license_path)
    assert s.activate("garbage").status == "invalid"
    assert lic.load_key(s.paths.license_path) == good_before and not guard.is_read_only()  # untouched
    new_key = license_issuer.issue(keypair[0], machine=machine_id, buyer="B", expires="2098-01-01")
    with qtbot.waitSignal(s.read_only_changed):
        state = s.activate(new_key)
    assert state.status == "active" and lic.load_key(s.paths.license_path) == new_key
    assert s.license.expires == "2098-01-01"


def test_expired_license_is_read_only(make_session):
    s = make_session()
    from retail import license as lic
    state = lic.apply_license(s.paths.license_path, s.public_key, s.machine_id, date(2100, 1, 1))
    s.license = state
    assert s.read_only is True


def test_close_closes_the_connection(make_session):
    s = make_session()
    s.close()
    with pytest.raises(Exception):
        s.conn.execute("SELECT 1")


def test_restore_reapplies_the_restored_language(make_session, qtbot):
    s = make_session()
    snapshot = s.backup_now().path          # taken while the shop language is "en"
    s.set_language("hi")
    with qtbot.waitSignal(s.language_changed) as blocker:
        s.restore_from(snapshot)
    assert blocker.args == ["en"] and i18n.get_language() == "en"


def test_restore_reapplies_the_read_only_guard(make_session):
    from retail import license as lic
    s = make_session()
    snapshot = s.backup_now().path
    s.license = lic.apply_license(s.paths.license_path, s.public_key, s.machine_id, date(2100, 1, 1))
    assert guard.is_read_only()
    s.restore_from(snapshot)
    assert guard.is_read_only()


def test_refresh_license_applies_the_guard_when_expired(make_session, monkeypatch):
    from retail import clock
    s = make_session()
    assert not guard.is_read_only()
    monkeypatch.setattr(clock, "today", lambda: date(2100, 1, 1))
    s.refresh_license()
    assert s.read_only and guard.is_read_only()


def test_language_can_still_be_switched_after_the_licence_expires(make_session, qtbot):
    from retail import license as lic
    s = make_session()
    s.license = lic.LicenseState("expired", expires="2020-01-01")
    guard.set_read_only(True)
    with qtbot.waitSignal(s.language_changed):
        s.set_language("te")
    assert i18n.get_language() == "te"
    assert s.shop()["language"] == "en"                      # not saved: the database is read-only
    with pytest.raises(ValueError):
        s.set_language("fr")


def test_restore_of_a_backup_without_a_shop_is_refused_before_anything_changes(make_session, tmp_path):
    import shutil
    import sqlite3
    from retail.services import backup
    s = make_session()
    shopless = tmp_path / "shopless.db"
    shutil.copy2(s.backup_now().path, shopless)
    raw = sqlite3.connect(shopless)
    for (name,) in raw.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='shop'").fetchall():
        raw.execute(f"DROP TRIGGER {name}")
    raw.execute("DELETE FROM shop")
    raw.commit()
    raw.close()
    conn = s.conn
    with pytest.raises(backup.BackupError):
        s.restore_from(shopless)
    assert s.conn is conn and s.has_shop()           # the live connection was never even closed
