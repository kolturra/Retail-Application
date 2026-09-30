import sqlite3

import pytest

from retail import db


def _dir(tmp_path, files):
    d = tmp_path / "m"
    d.mkdir()
    for name, sql in files.items():
        (d / name).write_text(sql)
    return d


def test_migrate_applies_in_order_and_is_idempotent(tmp_path):
    d = _dir(tmp_path, {"0001_a.sql": "CREATE TABLE t(x INTEGER);", "0002_b.sql": "ALTER TABLE t ADD COLUMN y TEXT;"})
    conn = db.connect(tmp_path / "a.db")
    assert db.migrate(conn, migrations_dir=d) == 2
    assert db.schema_version(conn) == 2
    assert db.migrate(conn, migrations_dir=d) == 2


def test_failed_migration_rolls_back_and_keeps_version(tmp_path):
    d = _dir(tmp_path, {
        "0001_a.sql": "CREATE TABLE t(x INTEGER);",
        "0002_bad.sql": "CREATE TABLE u(x INTEGER); INSERT INTO nope VALUES (1);",
    })
    conn = db.connect(tmp_path / "a.db")
    with pytest.raises(sqlite3.Error):
        db.migrate(conn, migrations_dir=d)
    assert db.schema_version(conn) == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "t" in tables and "u" not in tables


def test_before_callback_runs_only_when_pending(tmp_path):
    d = _dir(tmp_path, {"0001_a.sql": "CREATE TABLE t(x INTEGER);"})
    conn = db.connect(tmp_path / "a.db")
    calls = []
    db.migrate(conn, migrations_dir=d, before=lambda: calls.append(1))
    db.migrate(conn, migrations_dir=d, before=lambda: calls.append(1))
    assert calls == [1]


def test_transaction_commits_and_rolls_back(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    conn.execute("CREATE TABLE t(x INTEGER)")
    with db.transaction(conn):
        conn.execute("INSERT INTO t VALUES (1)")
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            conn.execute("INSERT INTO t VALUES (2)")
            raise RuntimeError("boom")
    assert [r[0] for r in conn.execute("SELECT x FROM t")] == [1]


def test_nested_transaction_inner_failure_rolls_back_only_inner(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    conn.execute("CREATE TABLE t(x INTEGER)")
    with db.transaction(conn):
        conn.execute("INSERT INTO t VALUES (1)")
        try:
            with db.transaction(conn):
                conn.execute("INSERT INTO t VALUES (2)")
                raise RuntimeError("inner")
        except RuntimeError:
            pass
    assert [r[0] for r in conn.execute("SELECT x FROM t")] == [1]


def test_outer_failure_rolls_back_inner_success(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    conn.execute("CREATE TABLE t(x INTEGER)")
    with pytest.raises(RuntimeError):
        with db.transaction(conn):
            with db.transaction(conn):
                conn.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("outer")
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
