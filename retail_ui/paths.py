import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def default(cls):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return cls(Path(base) / "RetailApp")

    @property
    def db_path(self):
        return self.root / "shop.db"

    @property
    def license_path(self):
        return self.root / "license.key"

    @property
    def settings_path(self):
        return self.root / "settings.json"

    @property
    def backup_dir(self):
        return self.root / "backups"

    @property
    def log_path(self):
        return self.root / "app.log"

    def ensure(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
