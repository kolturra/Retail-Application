import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class UiSettings:
    backup_dir: str = ""        # empty = the default folder under the data directory
    extra_backup_dir: str = ""  # optional second copy (USB / synced folder)
    auto_print: bool = False
    print_layout: str = ""      # empty = the template's default layout


def load(path) -> UiSettings:
    """Never raises: a missing, corrupt or wrongly-typed file yields the defaults."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        defaults = UiSettings()
        values = {}
        for f in fields(UiSettings):
            value = data[f.name] if isinstance(data, dict) and f.name in data else getattr(defaults, f.name)
            if type(value) is not type(getattr(defaults, f.name)):
                return UiSettings()
            values[f.name] = value
        return UiSettings(**values)
    except (OSError, ValueError):
        return UiSettings()


def save(path, settings: UiSettings) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
