import os
import sqlite3
from datetime import date

import pytest

from retail import db
from retail.services import backup, items, shop


@pytest.fixture
def bk(tmp_path):
    return tmp_path / "backups"


def test_backup_now_creates_a_valid_copy(shop_conn, bk):
    items.create_item(shop_conn, name="Soap", sell_price_paise=100)
    result = backup.backup_now(shop_conn, bk)
    assert result.path.exists() and result.path.name.startswith("daily-") and result.extra_error is None
    assert backup.validate_backup(result.path) == db.schema_version(shop_conn)


def test_backup_prunes_to_keep_newest(shop_conn, bk):
    made = []
    for i in range(4):
        p = backup.backup_now(shop_conn, bk, keep=99).path
        os.utime(p, ns=(1_000_000_000 * (i + 1),) * 2)
        made.append(p)
    backup.backup_now(shop_conn, bk, keep=2)
    remaining = backup.list_backups(bk)
    assert len(remaining) == 2 and made[0] not in remaining and made[1] not in remaining


def test_prune_is_per_prefix(shop_conn, bk):
    backup.backup_now(shop_conn, bk, prefix="pre-migrate", keep=1)
    backup.backup_now(shop_conn, bk, prefix="daily", keep=1)
    backup.backup_now(shop_conn, bk, prefix="daily", keep=1)
    names = [p.name for p in backup.list_backups(bk)]
    assert sum(n.startswith("daily-") for n in names) == 1
    assert sum(n.startswith("pre-migrate-") for n in names) == 1


def test_extra_dir_gets_a_copy_and_failure_is_reported_not_raised(shop_conn, bk, tmp_path):
    extra = tmp_path / "usb"
    ok = backup.backup_now(shop_conn, bk, extra_dir=extra)
    assert (extra / ok.path.name).exists()
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    bad = backup.backup_now(shop_conn, bk, extra_dir=blocker / "sub")
    assert bad.path.exists() and bad.extra_error


def test_daily_backup_due(shop_conn, bk):
    today = date.today()
    assert backup.daily_backup_due(bk, today) is True
    backup.backup_now(shop_conn, bk)
    assert backup.daily_backup_due(bk, today) is False
    backup.backup_now(shop_conn, bk, prefix="pre-migrate")
    assert backup.daily_backup_due(bk, date(2001, 1, 1)) is True


def test_restore_round_trip(db_path, bk):
    conn = db.open_shop(db_path, bk)
    shop.setup_shop(conn, name="Before", state_code="36")
    snapshot = backup.backup_now(conn, bk).path
    shop.setup_shop(conn, name="After", state_code="36")
    conn.close()
    safety = backup.restore(snapshot, db_path, bk)
    assert safety.exists() and safety.name.startswith("pre-restore-")
    conn = db.open_shop(db_path, bk)
    assert shop.get_shop(conn)["name"] == "Before"
    conn.close()
    probe = sqlite3.connect(safety.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        assert probe.execute("SELECT name FROM shop").fetchone()[0] == "After"
    finally:
        probe.close()


@pytest.mark.parametrize("content", [b"this is not a database at all", b"", b"SQLite format 3\x00" + b"\x00" * 200])
def test_restore_of_corrupt_file_fails_and_leaves_data_untouched(db_path, bk, tmp_path, content):
    conn = db.open_shop(db_path, bk)
    shop.setup_shop(conn, name="Keep me", state_code="36")
    conn.close()
    before = db_path.read_bytes()
    bad = tmp_path / "bad.db"
    bad.write_bytes(content)
    with pytest.raises(backup.BackupError):
        backup.restore(bad, db_path, bk)
    assert db_path.read_bytes() == before
    assert not list(bk.glob("pre-restore-*"))


def test_restore_of_missing_file_fails(db_path, bk, tmp_path):
    db.open_shop(db_path, bk).close()
    before = db_path.read_bytes()
    with pytest.raises(backup.BackupError):
        backup.restore(tmp_path / "nope.db", db_path, bk)
    assert db_path.read_bytes() == before
    assert not list(bk.glob("pre-restore-*"))


def test_restore_of_a_non_shop_database_fails(db_path, bk, tmp_path):
    db.open_shop(db_path, bk).close()
    before = db_path.read_bytes()
    other = tmp_path / "other.db"
    c = db.connect(other)
    c.execute("CREATE TABLE unrelated(x)")
    c.close()
    with pytest.raises(backup.BackupError):
        backup.restore(other, db_path, bk)
    assert db_path.read_bytes() == before


def test_restore_of_a_backup_from_a_newer_app_version_fails(db_path, bk):
    conn = db.open_shop(db_path, bk)
    snapshot = backup.backup_now(conn, bk).path
    conn.close()
    before = db_path.read_bytes()
    with pytest.raises(backup.BackupError):
        backup.restore(snapshot, db_path, bk, max_version=db.latest_version() - 1)
    assert db_path.read_bytes() == before


def _migration_dir(tmp_path, count):
    d = tmp_path / "mig"
    d.mkdir(exist_ok=True)
    (d / "0001_a.sql").write_text("CREATE TABLE shop(x INTEGER);")
    if count > 1:
        (d / "0002_b.sql").write_text("CREATE TABLE extra(y INTEGER);")
    return d


def test_open_shop_backs_up_before_upgrading_an_existing_database(tmp_path, db_path, bk):
    d = _migration_dir(tmp_path, 1)
    db.open_shop(db_path, bk, migrations_dir=d).close()
    assert not list(bk.glob("pre-migrate-*"))          # fresh database: nothing to protect
    d = _migration_dir(tmp_path, 2)
    conn = db.open_shop(db_path, bk, migrations_dir=d)
    assert db.schema_version(conn) == 2
    assert len(list(bk.glob("pre-migrate-*"))) == 1
    conn.close()
    db.open_shop(db_path, bk, migrations_dir=d).close()  # nothing pending: no new backup
    assert len(list(bk.glob("pre-migrate-*"))) == 1


def test_latest_version_matches_shipped_migrations():
    assert db.latest_version() == 2


# --- standing-ruling additions ---

@pytest.mark.parametrize("keep", [0, -1, True, 1.5, "3", None])
def test_backup_now_rejects_bad_keep(shop_conn, bk, keep):
    with pytest.raises(backup.BackupError):
        backup.backup_now(shop_conn, bk, keep=keep)
    assert not list(bk.glob("*.db"))


@pytest.mark.parametrize("prefix", ["", "a/b", "a" + chr(92) + "b", "..", None, 5])
def test_backup_now_rejects_bad_prefix(shop_conn, bk, prefix):
    with pytest.raises(backup.BackupError):
        backup.backup_now(shop_conn, bk, prefix=prefix)
    assert not list(bk.glob("*.db"))


def test_garbage_file_named_like_a_backup_does_not_break_listing(shop_conn, bk):
    good = backup.backup_now(shop_conn, bk).path
    junk = bk / "daily-20200101-000000.db"
    junk.write_bytes(b"garbage")
    listed = backup.list_backups(bk)
    assert good in listed and junk in listed
    backup.backup_now(shop_conn, bk, keep=1)  # pruning also tolerates it
    with pytest.raises(backup.BackupError):
        backup.validate_backup(junk)


# --- fix round 1 ---

def test_open_shop_closes_the_connection_when_migration_fails(tmp_path, db_path, bk):
    d = tmp_path / "badmig"
    d.mkdir()
    (d / "0001_bad.sql").write_text("THIS IS NOT SQL;")
    with pytest.raises(sqlite3.Error):
        db.open_shop(db_path, bk, migrations_dir=d)
    db_path.unlink()  # on Windows this fails if a handle leaked
    assert not db_path.exists()


class _FailingConn:
    def backup(self, target):
        raise sqlite3.OperationalError("disk I/O error")


def test_failed_backup_leaves_no_partial_file(bk):
    with pytest.raises(sqlite3.OperationalError):
        backup.backup_now(_FailingConn(), bk)
    assert not list(bk.glob("*"))
    assert backup.daily_backup_due(bk, date.today()) is True


def test_prune_is_anchored_to_the_prefix(shop_conn, bk):
    backup.backup_now(shop_conn, bk, prefix="pre-migrate", keep=5)
    backup.backup_now(shop_conn, bk, prefix="pre", keep=1)
    backup.backup_now(shop_conn, bk, prefix="pre", keep=1)
    names = [p.name for p in backup.list_backups(bk)]
    assert sum(n.startswith("pre-migrate-") for n in names) == 1
    assert sum(n.startswith("pre-2") for n in names) == 1


@pytest.mark.parametrize("prefix", ["a*", "a?", "a[b", "a]"])
def test_backup_now_rejects_wildcard_prefix(shop_conn, bk, prefix):
    with pytest.raises(backup.BackupError):
        backup.backup_now(shop_conn, bk, prefix=prefix)


def test_prune_tolerates_unremovable_files_and_keeps_new_backup(shop_conn, bk, monkeypatch):
    old = backup.backup_now(shop_conn, bk, keep=99).path
    os.utime(old, ns=(1_000_000_000,) * 2)
    real_unlink = type(old).unlink

    def locked(self, *a, **k):
        if self == old:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(type(old), "unlink", locked)
    result = backup.backup_now(shop_conn, bk, keep=1)
    assert result.path.exists() and old.exists()


def test_prune_never_deletes_the_new_backup(shop_conn, bk):
    first = backup.backup_now(shop_conn, bk, keep=99).path
    os.utime(first, ns=(4_000_000_000_000_000_000,) * 2)  # looks newer than anything made now
    result = backup.backup_now(shop_conn, bk, keep=1)
    assert result.path.exists()


def test_restore_failure_cleans_staging_and_leaves_live_db(db_path, bk, monkeypatch):
    conn = db.open_shop(db_path, bk)
    snapshot = backup.backup_now(conn, bk).path
    conn.close()
    before = db_path.read_bytes()

    def boom(src, dst):
        raise OSError("in use")

    monkeypatch.setattr(backup.os, "replace", boom)
    with pytest.raises(backup.BackupError):
        backup.restore(snapshot, db_path, bk)
    assert not list(db_path.parent.glob("*.restoring"))
    assert db_path.read_bytes() == before


def test_restore_with_no_existing_db_returns_none(db_path, bk):
    conn = db.open_shop(db_path, bk)
    snapshot = backup.backup_now(conn, bk).path
    conn.close()
    db_path.unlink()
    assert backup.restore(snapshot, db_path, bk) is None
    assert db_path.exists()


def test_validate_rejects_unmigrated_database(tmp_path):
    p = tmp_path / "v0.db"
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE shop(x)")
    c.commit()
    c.close()
    with pytest.raises(backup.BackupError):
        backup.validate_backup(p)
