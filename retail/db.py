import itertools
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from retail.services import backup

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_FILE = re.compile(r"^(\d{4})_.+\.sql$")
_savepoint_ids = itertools.count(1)


def connect(path) -> sqlite3.Connection:
    """Autocommit connection; use transaction() for every write."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn, *, migrations_dir=MIGRATIONS_DIR, before=None) -> int:
    """Apply pending NNNN_name.sql files in order; return the resulting version.
    `before` is called once, only if something is pending (used for backups)."""
    current = schema_version(conn)
    pending = sorted(
        (int(m.group(1)), path)
        for path in Path(migrations_dir).iterdir()
        if (m := _MIGRATION_FILE.match(path.name)) and int(m.group(1)) > current
    )
    if not pending:
        return current
    if before is not None:
        before()
    for version, path in pending:
        script = path.read_text(encoding="utf-8")
        try:
            conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return pending[-1][0]


@contextmanager
def transaction(conn):
    """BEGIN/COMMIT at the outermost level, SAVEPOINT when nested."""
    if conn.in_transaction:
        name = f"sp_{next(_savepoint_ids)}"
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
            raise
        else:
            try:
                conn.execute(f"RELEASE {name}")
            except BaseException:
                if conn.in_transaction:
                    conn.execute(f"ROLLBACK TO {name}")
                    conn.execute(f"RELEASE {name}")
                raise
    else:
        conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            try:
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise


def latest_version(migrations_dir=MIGRATIONS_DIR) -> int:
    versions = [int(m.group(1)) for p in Path(migrations_dir).iterdir() if (m := _MIGRATION_FILE.match(p.name))]
    return max(versions, default=0)


def open_shop(db_path, backup_dir, *, migrations_dir=MIGRATIONS_DIR):
    """Open the shop database, upgrading it safely: an existing database is backed up first."""
    conn = connect(db_path)
    before = None
    if schema_version(conn) > 0:
        before = lambda: backup.backup_now(conn, backup_dir, prefix="pre-migrate")
    migrate(conn, migrations_dir=migrations_dir, before=before)
    return conn
