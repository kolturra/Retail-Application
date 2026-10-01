import os
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


def _prune(directory: Path, prefix: str, keep: int) -> None:
    files = sorted(
        (p for p in directory.glob(f"{prefix}-*.db")),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )
    for old in files[keep:]:
        old.unlink()


def backup_now(conn, backup_dir, *, prefix="daily", keep=14, extra_dir=None) -> BackupResult:
    if type(keep) is not int or keep < 1:
        raise BackupError("keep must be a whole number of at least 1")
    if not isinstance(prefix, str) or not prefix or "/" in prefix or "\\" in prefix or prefix in (".", ".."):
        raise BackupError("prefix must be a non-empty name without path separators")
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(backup_dir, prefix)
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    _prune(backup_dir, prefix, keep)
    extra_error = None
    if extra_dir is not None:
        try:
            extra_dir = Path(extra_dir)
            extra_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, extra_dir / dest.name)
            _prune(extra_dir, prefix, keep)
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
    if not intact or not has_shop:
        raise BackupError("This file is not a valid shop backup")
    return version


def restore(backup_path, db_path, backup_dir, *, max_version=None) -> Path:
    """Replace db_path with backup_path. Close your connection first.
    Returns the safety copy of the data that was replaced."""
    version = validate_backup(backup_path)
    if max_version is not None and version > max_version:
        raise BackupError("This backup was made by a newer version of the app")
    db_path, backup_dir = Path(db_path), Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    safety = _unique_path(backup_dir, "pre-restore")
    if db_path.exists():
        shutil.copy2(db_path, safety)
    staging = db_path.with_suffix(".restoring")
    shutil.copy2(backup_path, staging)
    os.replace(staging, db_path)
    return safety
