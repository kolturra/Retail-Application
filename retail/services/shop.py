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


_SHOP_FIELDS = ("name", "gstin", "address", "state_code", "bill_footer", "gst_enabled",
                "price_includes_gst", "oversell_policy", "language")


@writes
def update_shop(conn, **fields):
    get_shop(conn)  # raises ShopNotSetUp before anything else
    unknown = sorted(set(fields) - set(_SHOP_FIELDS))
    if unknown:
        raise ShopError(f"Cannot change {unknown} here")
    if not fields:
        raise ShopError("Nothing to change")
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip()
        if not fields["name"]:
            raise ShopError("Shop name is required")
    if "state_code" in fields and not re.fullmatch(r"\d{2}", fields["state_code"] or ""):
        raise ShopError("State code must be two digits, e.g. '36'")
    if "oversell_policy" in fields and fields["oversell_policy"] not in _POLICIES:
        raise ShopError(f"oversell_policy must be one of {_POLICIES}")
    if "language" in fields and fields["language"] not in _LANGUAGES:
        raise ShopError(f"language must be one of {_LANGUAGES}")
    for flag in ("gst_enabled", "price_includes_gst"):
        if flag in fields:
            if type(fields[flag]) is not bool:
                raise ShopError(f"{flag} must be True or False")
            fields[flag] = int(fields[flag])
    with transaction(conn):
        # column names come from the _SHOP_FIELDS whitelist above, values are bound parameters
        conn.execute(f"UPDATE shop SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = 1",
                     tuple(fields.values()))
        audit.log(conn, "update", "shop", 1, ", ".join(sorted(fields)))
