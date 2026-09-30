import re

from retail.db import transaction
from retail.guard import writes
from retail.services import audit

_POLICIES = ("block", "warn", "allow")
_LANGUAGES = ("en", "hi", "te")


class ShopError(ValueError):
    pass


class ShopNotSetUp(RuntimeError):
    pass


@writes
def setup_shop(conn, *, name, state_code, gstin=None, address="", template="grocery",
               gst_enabled=True, price_includes_gst=True, oversell_policy="warn", language="en"):
    if not name or not name.strip():
        raise ShopError("Shop name is required")
    if not re.fullmatch(r"\d{2}", state_code or ""):
        raise ShopError("State code must be two digits, e.g. '36'")
    if oversell_policy not in _POLICIES:
        raise ShopError(f"oversell_policy must be one of {_POLICIES}")
    if language not in _LANGUAGES:
        raise ShopError(f"language must be one of {_LANGUAGES}")
    with transaction(conn):
        conn.execute(
            """INSERT OR REPLACE INTO shop(id, name, gstin, address, state_code, template,
                   gst_enabled, price_includes_gst, oversell_policy, language)
               VALUES (1,?,?,?,?,?,?,?,?,?)""",
            (name.strip(), gstin, address, state_code, template, int(gst_enabled),
             int(price_includes_gst), oversell_policy, language),
        )
        audit.log(conn, "setup", "shop", 1, name.strip())


def get_shop(conn):
    row = conn.execute("SELECT * FROM shop WHERE id = 1").fetchone()
    if row is None:
        raise ShopNotSetUp("The shop has not been set up yet")
    return row
