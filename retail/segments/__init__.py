"""Segment templates: JSON presets that enable features and defaults. They never change the schema."""
import json
from pathlib import Path

from retail.db import transaction
from retail.guard import writes
from retail.services import audit, shop

_DIR = Path(__file__).parent


class UnknownTemplate(ValueError):
    pass


def list_templates():
    return sorted(p.stem for p in _DIR.glob("*.json"))


def load(name):
    if name not in list_templates():
        raise UnknownTemplate(f"Unknown template {name!r}")
    return json.loads((_DIR / f"{name}.json").read_text(encoding="utf-8"))


def template_settings(conn):
    return json.loads(shop.get_shop(conn)["features"])


def feature_enabled(conn, key):
    return bool(template_settings(conn).get("features", {}).get(key, False))


@writes
def apply_template(conn, name):
    template = load(name)
    with transaction(conn):
        conn.execute(
            "UPDATE shop SET template = ?, features = ? WHERE id = 1", (name, json.dumps(template))
        )
        audit.log(conn, "apply_template", "shop", 1, name)
    return template


@writes
def set_feature(conn, key, enabled):
    if type(enabled) is not bool:
        raise ValueError("enabled must be True or False")
    known = {k for name in list_templates() for k in load(name)["features"]}
    if key not in known:
        raise UnknownTemplate(f"Unknown feature {key!r}")
    with transaction(conn):
        settings = template_settings(conn)
        settings.setdefault("features", {})[key] = enabled
        conn.execute("UPDATE shop SET features = ? WHERE id = 1", (json.dumps(settings),))
        audit.log(conn, "set_feature", "shop", 1, f"{key}={enabled}")
