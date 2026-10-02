import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class BackupResult:
    path: Path
    extra_error: str | None = None


def _unique_path(directory: Path, prefix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"{prefix}-{stamp}.db"
    n = 1
    while path.exists():
        path = directory / f"{prefix}-{stamp}-{n}.db"
        n += 1
    return path


def _prune(directory: Path, prefix: str, keep: int, protect: Path | None = None) -> None:
    """Best-effort: never raises for a locked/odd file and never deletes `protect`."""
    pattern = re.compile(rf"^{re.escape(prefix)}-\d{{8}}-\d{{6}}(-\d+)?\.db$")
    candidates = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for p in entries:
        if not pattern.match(p.name):
            continue
        try:
            candidates.append((p.stat().st_mtime_ns, p.name, p))
        except OSError:
            continue
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    if protect is not None:
        # The file just created always counts as the newest, whatever its mtime/name tie-break.
        candidates = [c for c in candidates if c[2] != protect]
        keep -= 1
    for _, _, old in candidates[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def backup_now(conn, backup_dir, *, prefix="daily", keep=14, extra_dir=None) -> BackupResult:
    if type(keep) is not int or keep < 1:
        raise BackupError("keep must be a whole number of at least 1")
    if (
        not isinstance(prefix, str)
        or not prefix
        or any(c in prefix for c in "/\\*?[]")
        or prefix in (".", "..")
    ):
        raise BackupError("prefix must be a non-empty name without path separators or wildcards")
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(backup_dir, prefix)
    target = None
    try:
        target = sqlite3.connect(str(dest))
        conn.backup(target)
        target.close()
        target = None
    except BaseException:
        if target is not None:
            try:
                target.close()
            except sqlite3.Error:
                pass
        try:
            dest.unlink()
        except OSError:
            pass
        raise
    _prune(backup_dir, prefix, keep, protect=dest)
    extra_error = None
    if extra_dir is not None:
        try:
            extra_dir = Path(extra_dir)
            extra_dir.mkdir(parents=True, exist_ok=True)
            copied = extra_dir / dest.name
            shutil.copy2(dest, copied)
            _prune(extra_dir, prefix, keep, protect=copied)
        except OSError as exc:
            extra_error = str(exc)
    return BackupResult(dest, extra_error)


def list_backups(backup_dir):
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("*.db"), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)


def daily_backup_due(backup_dir, today: date) -> bool:
    prefix = f"daily-{today:%Y%m%d}-"
    return not any(p.name.startswith(prefix) for p in list_backups(backup_dir))


def validate_backup(path) -> int:
    """Return the backup's schema version, or raise BackupError if it is not a usable shop database."""
    path = Path(path)
    if not path.is_file():
        raise BackupError(f"Backup file not found: {path}")
    try:
        probe = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            intact = probe.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            has_shop = probe.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shop'"
            ).fetchone() is not None
            version = probe.execute("PRAGMA user_version").fetchone()[0]
        finally:
            probe.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Not a valid backup: {exc}") from exc
    if not intact or not has_shop or version < 1:
        raise BackupError("This file is not a valid shop backup")
    return version


def restore(backup_path, db_path, backup_dir, *, max_version=None) -> Path | None:
    """Replace db_path with backup_path. Close your connection first.
    Returns the safety copy of the data that was replaced, or None if there was no existing database."""
    version = validate_backup(backup_path)
    if max_version is not None and version > max_version:
        raise BackupError("This backup was made by a newer version of the app")
    db_path, backup_dir = Path(db_path), Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    safety = None
    staging = db_path.with_suffix(".restoring")
    try:
        if db_path.exists():
            safety = _unique_path(backup_dir, "pre-restore")
            shutil.copy2(db_path, safety)
        shutil.copy2(backup_path, staging)
        os.replace(staging, db_path)
    except OSError as exc:
        try:
            staging.unlink()
        except OSError:
            pass
        raise BackupError(f"Could not restore (the database file may be in use, or the disk is full): {exc}") from exc
    return safety
