# Retail App — Core Engine Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the headless, fully tested core of the multi-segment retail app: SQLite data layer, GST/stock/billing services, segment templates, backup/restore, offline licensing, i18n catalogue, reports and exports.

**Architecture:** Three layers, dependencies pointing down only: UI (Plan 2) → services (pure Python, all business rules) → data (SQLite, versioned migrations). Money is integer paise, quantities are integer milli-units, stock is an append-only movement ledger, finished bills are never edited. Segments (grocery, electronics) are JSON templates over one shared schema.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `cryptography` (Ed25519 licensing), `pytest`. PySide6 arrives in Plan 2.

**Spec:** `docs/superpowers/specs/2026-09-30-retail-app-design.md`

**Plan 2 (written after this plan lands):** PySide6 counter screen, item/party/purchase screens, print layouts (thermal 58/80mm, A4), WhatsApp bill, activation window, onboarding wizard (template pick, backup location), font bundling for Hindi/Telugu, PyInstaller installer, grocery-volume UI performance check.

## Global Constraints

- Windows desktop app, one PC per shop, works fully offline (spec §2).
- Python; storage is SQLite, one file per shop (spec §2).
- Money is integer paise everywhere; never floats (spec §3). Quantities are integer milli-units (1000 = 1 unit or 1 kg) — plan-level choice to keep decimal quantities exact.
- Stock is an append-only movement ledger; quantity on hand is derived (spec §3).
- Finished bills are never edited; corrections are sale returns or cancelling entries, each in the audit log (spec §3).
- UI layer has no business logic; all rules live in `retail/services/` (spec §3).
- Segment templates are JSON data and never change the schema (spec §5).
- Item tracking modes are exactly `none`, `weighed`, `batch`, `serial` (spec §4).
- Intra-state sale → CGST+SGST; inter-state → IGST (spec §6). Non-GST estimate bills are a per-shop setting (spec §6).
- Selling below stock is a per-shop setting: `block`, `warn` or `allow` (spec §6).
- Licensing is offline: Ed25519-signed key with machine ID, expiry date and plan; after expiry the app is read-only with full export, never locked out (spec §7).
- The license private key is never shipped or committed (spec §7).
- Languages: English (default), Hindi, Telugu; a test fails if Hindi or Telugu is missing any string (spec §8).
- Each migration is versioned and runs after an automatic backup (spec §4, §7).
- Commit messages end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Assumptions added by this plan (not stated in the spec — confirm during review)

1. **Prices are GST-inclusive (MRP style) by default**, with a per-shop `price_includes_gst` switch. Indian retail shelf prices are normally MRP-inclusive.
2. **Payment modes:** `cash`, `upi`, `card`, `emi`, `credit`. `credit` (udhaar) requires a customer.
3. **GST slabs preloaded in templates: 0%, 5%, 18%, 40%** (`[0, 500, 1800, 4000]` basis points). The spec lists GST-rule verification as an open item — verify against the current GST rate schedule before release. Item rates stay editable per item.
4. **Exports are CSV** (opens in Excel). Native `.xlsx` is deferred.
5. Held bills do not reserve stock; stock is re-checked when the bill is finalized.

## Review Focus

Failure modes the spec implies but a happy-path build would miss, most likely first. Each has a pinning test in the task named.

1. A serial/IMEI typed with spaces or lowercase, already sold, or entered twice on one bill must be rejected, and a second bill racing for the same serial must fail without partial writes (Task 7, Task 8).
2. Fractional, zero or negative quantity on a non-weighed item must be rejected (Task 7).
3. Returning more than was sold, or returning the same line again across two returns, must be rejected (Task 9).
4. Finalizing an empty bill, payments that don't add up to the total, or a credit sale with no customer must fail and change nothing (Task 8).
5. Restoring a corrupt file, a non-shop database, or a backup from a newer app version must fail and leave the current data untouched (Task 12).

---

## File Structure

```
pyproject.toml
README.md
.gitignore
retail/
  __init__.py
  money.py            paise/milli helpers, rounding
  clock.py            now/today/add_months (single place to patch time)
  guard.py            read-only switch + @writes decorator
  db.py               connect, transaction(), migrate(), open_shop()
  migrations/0001_init.sql
  services/
    __init__.py
    audit.py          audit_log writer
    shop.py           shop settings
    items.py          item catalogue, barcode/sku/name resolution, "3*" prefix
    stock.py          movement ledger, serial/batch units, oversell check
    gst.py            per-line tax split
    parties.py        customers/suppliers, udhaar balance
    billing.py        build/hold/finalize/return sale bills
    purchases.py      supplier bills feeding the ledger
    backup.py         backup, prune, validate, restore
    reports.py        sales register, GST summary, daily summary, CSV
    staff.py          staff, salary/rent/expenses
  segments/
    __init__.py       template loader, apply, feature toggles
    grocery.json
    electronics.json
  license.py          machine ID, key verify, apply to guard
  public_key.py       generated by tools/license_issuer.py
  i18n.py
  locales/en.json  hi.json  te.json
tools/
  __init__.py
  license_issuer.py   vendor-only: gen-keys, issue
tests/
  conftest.py  test_*.py
```

---

### Task 1: Project scaffold, money and clock helpers

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `retail/__init__.py`, `retail/money.py`, `retail/clock.py`, `retail/services/__init__.py`, `tests/test_money.py`, `tests/test_clock.py`

**Interfaces:**
- Produces: `money.rupees_to_paise(value) -> int`, `money.paise_to_str(paise: int) -> str`, `money.qty_to_milli(value) -> int`, `money.milli_to_str(milli: int) -> str`, `money.line_amount(rate_paise: int, qty_milli: int) -> int`, `money.round_to_rupee(total_paise: int) -> tuple[int, int]` (rounded total, adjustment), `clock.now_iso() -> str`, `clock.today() -> date`, `clock.add_months(d: date, months: int) -> date`.

- [ ] **Step 1: Initialise the repo and environment**

Run (from the project folder):
```bash
git init
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
```

Create `pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "retail-app"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["cryptography>=42"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["retail*"]

[tool.setuptools.package-data]
retail = ["migrations/*.sql", "locales/*.json", "segments/*.json"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

Create `.gitignore`:
```
.venv/
__pycache__/
*.egg-info/
*.db
*.restoring
keys/
build/
dist/
```

Create `README.md`:
```markdown
# Retail App

Multi-segment retail desktop app (grocery, electronics). See `docs/superpowers/specs/`.

Setup: `python -m venv .venv`, then `.venv/Scripts/python -m pip install -e ".[dev]"`.
Tests: `.venv/Scripts/python -m pytest`.
```

Create empty-bodied `retail/services/__init__.py`, and `retail/__init__.py`:
```python
__version__ = "0.1.0"
```

Run: `.venv/Scripts/python -m pip install -e ".[dev]"`
Expected: installs `retail-app`, `cryptography`, `pytest` without error.

- [ ] **Step 2: Write the failing tests**

`tests/test_money.py`:
```python
import pytest

from retail import money


def test_rupees_to_paise_is_exact_for_float_noise():
    assert money.rupees_to_paise(0.1 + 0.2) == 30
    assert money.rupees_to_paise("10.005") == 1001
    assert money.rupees_to_paise(59) == 5900


def test_paise_to_str():
    assert money.paise_to_str(5) == "0.05"
    assert money.paise_to_str(12345) == "123.45"
    assert money.paise_to_str(-12345) == "-123.45"
    assert money.paise_to_str(0) == "0.00"


def test_quantity_helpers():
    assert money.qty_to_milli("0.75") == 750
    assert money.qty_to_milli(3) == 3000
    assert money.milli_to_str(750) == "0.75"
    assert money.milli_to_str(2000) == "2"
    assert money.milli_to_str(1500) == "1.5"


@pytest.mark.parametrize(
    "rate,qty,expected",
    [(10000, 750, 7500), (3333, 500, 1667), (11800, 1000, 11800), (100, 3000, 300)],
)
def test_line_amount_rounds_half_up(rate, qty, expected):
    assert money.line_amount(rate, qty) == expected


@pytest.mark.parametrize(
    "total,expected",
    [(10049, (10000, -49)), (10050, (10100, 50)), (10000, (10000, 0)), (0, (0, 0))],
)
def test_round_to_rupee(total, expected):
    assert money.round_to_rupee(total) == expected
```

`tests/test_clock.py`:
```python
from datetime import date

from retail import clock


def test_add_months_clamps_to_month_end():
    assert clock.add_months(date(2026, 1, 31), 12) == date(2027, 1, 31)
    assert clock.add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert clock.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert clock.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_now_iso_shape():
    stamp = clock.now_iso()
    assert len(stamp) == 19 and stamp[10] == "T"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_money.py tests/test_clock.py -v`
Expected: FAIL with `ImportError: cannot import name 'money'` / `'clock'`.

- [ ] **Step 4: Write the implementation**

`retail/money.py`:
```python
"""Money is integer paise; quantity is integer milli-units. No floats anywhere."""
from decimal import ROUND_HALF_UP, Decimal

_ONE = Decimal(1)


def _round(value: Decimal) -> int:
    return int(value.quantize(_ONE, rounding=ROUND_HALF_UP))


def rupees_to_paise(value) -> int:
    return _round(Decimal(str(value)) * 100)


def paise_to_str(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{whole}.{frac:02d}"


def qty_to_milli(value) -> int:
    return _round(Decimal(str(value)) * 1000)


def milli_to_str(milli: int) -> str:
    sign = "-" if milli < 0 else ""
    whole, frac = divmod(abs(milli), 1000)
    if frac == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{frac:03d}".rstrip("0")


def line_amount(rate_paise: int, qty_milli: int) -> int:
    return _round(Decimal(rate_paise) * Decimal(qty_milli) / 1000)


def round_to_rupee(total_paise: int) -> tuple[int, int]:
    """Return (total rounded to the nearest rupee, adjustment applied)."""
    rounded = _round(Decimal(total_paise) / 100) * 100
    return rounded, rounded - total_paise
```

`retail/clock.py`:
```python
"""Single home for time so tests can pass explicit dates."""
import calendar
from datetime import date, datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> date:
    return date.today()


def add_months(d: date, months: int) -> date:
    carry, month0 = divmod(d.month - 1 + months, 12)
    year, month = d.year + carry, month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))
```

- [ ] **Step 5: Run tests to verify they pass, then commit**

Run: `.venv/Scripts/python -m pytest tests/test_money.py tests/test_clock.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "chore: scaffold project with money and clock helpers" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Data foundation — transactions, migrations, schema, audit, read-only guard

**Files:**
- Create: `retail/db.py`, `retail/guard.py`, `retail/migrations/0001_init.sql`, `retail/services/audit.py`, `tests/conftest.py`, `tests/test_db.py`, `tests/test_schema.py`, `tests/test_guard.py`

**Interfaces:**
- Consumes: `clock.now_iso`.
- Produces: `db.connect(path) -> sqlite3.Connection` (autocommit mode, `Row` factory, foreign keys on); `db.schema_version(conn) -> int`; `db.migrate(conn, *, migrations_dir=MIGRATIONS_DIR, before=None) -> int`; `db.transaction(conn)` context manager (nestable via savepoints); `guard.ReadOnlyError`, `guard.set_read_only(bool)`, `guard.is_read_only() -> bool`, `guard.writes` decorator; `audit.log(conn, action, entity, entity_id=None, detail="", actor="owner")`. Fixtures `db_path`, `conn`. **Rule for all later tasks:** every public write function is decorated `@writes` and wraps its SQL in `with transaction(conn):`; helpers prefixed `_` never open a transaction themselves.

- [ ] **Step 1: Write the failing tests**

`tests/conftest.py`:
```python
import pytest

from retail import db, guard


@pytest.fixture(autouse=True)
def _writable():
    guard.set_read_only(False)
    yield
    guard.set_read_only(False)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "shop.db"


@pytest.fixture
def conn(db_path):
    connection = db.connect(db_path)
    db.migrate(connection)
    yield connection
    connection.close()
```

`tests/test_db.py`:
```python
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
```

`tests/test_schema.py`:
```python
import sqlite3

import pytest

from retail.services import audit

EXPECTED = {
    "shop", "counter", "item", "item_barcode", "stock_unit", "stock_movement", "party",
    "party_payment", "bill", "bill_line", "payment", "purchase", "purchase_line",
    "warranty", "audit_log", "staff", "expense",
}


def test_schema_has_all_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED <= names


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO item_barcode(code, item_id) VALUES ('1', 999)")


def test_audit_log_writes_a_row(conn):
    audit.log(conn, "create", "item", 7, "Soap")
    row = conn.execute("SELECT actor, action, entity, entity_id, detail FROM audit_log").fetchone()
    assert tuple(row) == ("owner", "create", "item", 7, "Soap")
```

`tests/test_guard.py`:
```python
import pytest

from retail import guard


@guard.writes
def _write():
    return "written"


def test_writes_pass_when_writable():
    assert _write() == "written"


def test_writes_blocked_when_read_only():
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        _write()
    assert guard.is_read_only() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_db.py tests/test_schema.py tests/test_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'db'` / `'guard'`.

- [ ] **Step 3: Write the implementation**

`retail/guard.py`:
```python
"""Read-only switch. Business writes are decorated with @writes so an expired
license blocks them while reads and exports keep working."""
import functools


class ReadOnlyError(RuntimeError):
    """Raised when a write is attempted while the license is expired."""


_read_only = False


def set_read_only(value: bool) -> None:
    global _read_only
    _read_only = value


def is_read_only() -> bool:
    return _read_only


def writes(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if _read_only:
            raise ReadOnlyError("License expired: shop data is read-only.")
        return func(*args, **kwargs)

    return wrapper
```

`retail/db.py`:
```python
import itertools
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

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
            conn.execute(f"RELEASE {name}")
    else:
        conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
```

`retail/services/audit.py`:
```python
from retail import clock


def log(conn, action, entity, entity_id=None, detail="", actor="owner"):
    """Append an audit row. Runs inside the caller's transaction."""
    conn.execute(
        "INSERT INTO audit_log(at, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
        (clock.now_iso(), actor, action, entity, entity_id, detail),
    )
```

`retail/migrations/0001_init.sql`:
```sql
CREATE TABLE shop (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT NOT NULL,
  gstin TEXT,
  address TEXT NOT NULL DEFAULT '',
  state_code TEXT NOT NULL,
  bill_footer TEXT NOT NULL DEFAULT '',
  template TEXT NOT NULL DEFAULT 'grocery',
  features TEXT NOT NULL DEFAULT '{}',
  gst_enabled INTEGER NOT NULL DEFAULT 1,
  price_includes_gst INTEGER NOT NULL DEFAULT 1,
  oversell_policy TEXT NOT NULL DEFAULT 'warn' CHECK (oversell_policy IN ('block','warn','allow')),
  language TEXT NOT NULL DEFAULT 'en' CHECK (language IN ('en','hi','te'))
);

CREATE TABLE counter (name TEXT PRIMARY KEY, value INTEGER NOT NULL);

CREATE TABLE item (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  sku TEXT UNIQUE,
  hsn TEXT,
  gst_rate_bp INTEGER NOT NULL DEFAULT 0 CHECK (gst_rate_bp >= 0),
  unit TEXT NOT NULL DEFAULT 'pcs',
  sell_price_paise INTEGER NOT NULL DEFAULT 0 CHECK (sell_price_paise >= 0),
  buy_price_paise INTEGER NOT NULL DEFAULT 0 CHECK (buy_price_paise >= 0),
  reorder_milli INTEGER NOT NULL DEFAULT 0 CHECK (reorder_milli >= 0),
  warranty_months INTEGER NOT NULL DEFAULT 0 CHECK (warranty_months >= 0),
  tracking TEXT NOT NULL DEFAULT 'none' CHECK (tracking IN ('none','weighed','batch','serial')),
  active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_item_name ON item(name);

CREATE TABLE item_barcode (
  code TEXT PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES item(id)
);

CREATE TABLE stock_unit (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES item(id),
  serial TEXT,
  batch_no TEXT,
  expiry TEXT,
  status TEXT NOT NULL DEFAULT 'in_stock' CHECK (status IN ('in_stock','sold'))
);
CREATE UNIQUE INDEX ux_stock_unit_serial ON stock_unit(item_id, serial) WHERE serial IS NOT NULL;

CREATE TABLE stock_movement (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL REFERENCES item(id),
  unit_id INTEGER REFERENCES stock_unit(id),
  qty_milli INTEGER NOT NULL CHECK (qty_milli <> 0),
  type TEXT NOT NULL CHECK (type IN ('opening','purchase','sale','sale_return','purchase_return','adjustment')),
  ref_type TEXT,
  ref_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_stock_movement_item ON stock_movement(item_id);
CREATE INDEX ix_stock_movement_unit ON stock_movement(unit_id);

CREATE TABLE party (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  phone TEXT,
  gstin TEXT,
  state_code TEXT,
  type TEXT NOT NULL DEFAULT 'customer' CHECK (type IN ('customer','supplier','both')),
  opening_balance_paise INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE party_payment (
  id INTEGER PRIMARY KEY,
  party_id INTEGER NOT NULL REFERENCES party(id),
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  mode TEXT NOT NULL CHECK (mode IN ('cash','upi','card')),
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE bill (
  id INTEGER PRIMARY KEY,
  bill_no TEXT UNIQUE,
  kind TEXT NOT NULL CHECK (kind IN ('sale','sale_return')),
  status TEXT NOT NULL CHECK (status IN ('held','final','cancelled')),
  party_id INTEGER REFERENCES party(id),
  ref_bill_id INTEGER REFERENCES bill(id),
  gst_mode TEXT NOT NULL CHECK (gst_mode IN ('gst','estimate')),
  created_at TEXT NOT NULL,
  finalized_at TEXT,
  taxable_paise INTEGER NOT NULL DEFAULT 0,
  cgst_paise INTEGER NOT NULL DEFAULT 0,
  sgst_paise INTEGER NOT NULL DEFAULT 0,
  igst_paise INTEGER NOT NULL DEFAULT 0,
  round_off_paise INTEGER NOT NULL DEFAULT 0,
  total_paise INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE bill_line (
  id INTEGER PRIMARY KEY,
  bill_id INTEGER NOT NULL REFERENCES bill(id),
  item_id INTEGER NOT NULL REFERENCES item(id),
  unit_id INTEGER REFERENCES stock_unit(id),
  ref_line_id INTEGER REFERENCES bill_line(id),
  qty_milli INTEGER NOT NULL CHECK (qty_milli > 0),
  rate_paise INTEGER NOT NULL,
  discount_paise INTEGER NOT NULL DEFAULT 0,
  amount_paise INTEGER NOT NULL,
  gst_rate_bp INTEGER NOT NULL DEFAULT 0,
  taxable_paise INTEGER NOT NULL DEFAULT 0,
  cgst_paise INTEGER NOT NULL DEFAULT 0,
  sgst_paise INTEGER NOT NULL DEFAULT 0,
  igst_paise INTEGER NOT NULL DEFAULT 0,
  total_paise INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_bill_line_bill ON bill_line(bill_id);
CREATE INDEX ix_bill_line_ref ON bill_line(ref_line_id);

CREATE TABLE payment (
  id INTEGER PRIMARY KEY,
  bill_id INTEGER NOT NULL REFERENCES bill(id),
  mode TEXT NOT NULL CHECK (mode IN ('cash','upi','card','emi','credit')),
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  created_at TEXT NOT NULL
);

CREATE TABLE purchase (
  id INTEGER PRIMARY KEY,
  party_id INTEGER REFERENCES party(id),
  invoice_no TEXT,
  purchase_date TEXT NOT NULL,
  total_paise INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE purchase_line (
  id INTEGER PRIMARY KEY,
  purchase_id INTEGER NOT NULL REFERENCES purchase(id),
  item_id INTEGER NOT NULL REFERENCES item(id),
  qty_milli INTEGER NOT NULL CHECK (qty_milli > 0),
  cost_paise INTEGER NOT NULL CHECK (cost_paise >= 0)
);

CREATE TABLE warranty (
  id INTEGER PRIMARY KEY,
  unit_id INTEGER NOT NULL REFERENCES stock_unit(id),
  bill_id INTEGER NOT NULL REFERENCES bill(id),
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id INTEGER,
  detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE staff (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT '',
  monthly_salary_paise INTEGER NOT NULL DEFAULT 0 CHECK (monthly_salary_paise >= 0),
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE expense (
  id INTEGER PRIMARY KEY,
  spent_on TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('salary','rent','electricity','transport','other')),
  amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
  note TEXT NOT NULL DEFAULT '',
  staff_id INTEGER REFERENCES staff(id)
);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_db.py tests/test_schema.py tests/test_guard.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add data layer with migrations, transactions, audit and read-only guard" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Shop setup and item catalogue

**Files:**
- Create: `retail/services/shop.py`, `retail/services/items.py`, `tests/test_shop.py`, `tests/test_items.py`
- Modify: `tests/conftest.py` (add `shop_conn` fixture)

**Interfaces:**
- Consumes: `db.transaction`, `guard.writes`, `audit.log`, `money.qty_to_milli`.
- Produces: `shop.ShopError`, `shop.ShopNotSetUp`, `shop.setup_shop(conn, *, name, state_code, gstin=None, address="", template="grocery", gst_enabled=True, price_includes_gst=True, oversell_policy="warn", language="en") -> None`, `shop.get_shop(conn) -> Row`; `items.ItemError`, `items.create_item(conn, *, name, sell_price_paise, gst_rate_bp=0, unit="pcs", tracking="none", sku=None, hsn=None, buy_price_paise=0, reorder_milli=0, warranty_months=0, barcodes=()) -> int`, `items.add_barcode(conn, item_id, code) -> None`, `items.resolve(conn, text, limit=20) -> list[Row]`, `items.parse_entry(text) -> tuple[int, str]`. Fixture `shop_conn` (a `conn` with a grocery shop in state `"36"`, GST-inclusive prices, oversell policy `warn`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:
```python
from retail.services import shop as _shop


@pytest.fixture
def shop_conn(conn):
    _shop.setup_shop(conn, name="Test Shop", state_code="36")
    return conn
```

`tests/test_shop.py`:
```python
import pytest

from retail import guard
from retail.services import shop


def test_setup_and_get_shop(conn):
    shop.setup_shop(conn, name="Sri Kirana", state_code="36", gstin="36ABCDE1234F1Z5")
    s = shop.get_shop(conn)
    assert s["name"] == "Sri Kirana"
    assert s["template"] == "grocery"
    assert s["price_includes_gst"] == 1 and s["gst_enabled"] == 1
    assert s["oversell_policy"] == "warn"


def test_get_shop_before_setup_raises(conn):
    with pytest.raises(shop.ShopNotSetUp):
        shop.get_shop(conn)


@pytest.mark.parametrize("kwargs", [
    {"name": "", "state_code": "36"},
    {"name": "X", "state_code": "ABC"},
    {"name": "X", "state_code": "3"},
    {"name": "X", "state_code": "36", "oversell_policy": "maybe"},
    {"name": "X", "state_code": "36", "language": "fr"},
])
def test_setup_rejects_bad_input(conn, kwargs):
    with pytest.raises(shop.ShopError):
        shop.setup_shop(conn, **kwargs)


def test_setup_blocked_when_read_only(conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        shop.setup_shop(conn, name="X", state_code="36")
```

`tests/test_items.py`:
```python
import time

import pytest

from retail import guard
from retail.services import items


def test_create_item_with_barcodes(shop_conn):
    iid = items.create_item(shop_conn, name="Parle-G 100g", sell_price_paise=1000, gst_rate_bp=500,
                            sku="PARLE100", barcodes=["8901719101015", " 8901719101022 "])
    row = shop_conn.execute("SELECT * FROM item WHERE id=?", (iid,)).fetchone()
    assert row["name"] == "Parle-G 100g" and row["gst_rate_bp"] == 500
    codes = {r["code"] for r in shop_conn.execute("SELECT code FROM item_barcode WHERE item_id=?", (iid,))}
    assert codes == {"8901719101015", "8901719101022"}


def test_resolve_prefers_barcode_then_sku_then_name(shop_conn):
    a = items.create_item(shop_conn, name="Alpha", sell_price_paise=100, barcodes=["111"])
    b = items.create_item(shop_conn, name="Beta soap", sell_price_paise=100, sku="BETA")
    c = items.create_item(shop_conn, name="Gamma soap", sell_price_paise=100)
    assert [r["id"] for r in items.resolve(shop_conn, "111")] == [a]
    assert [r["id"] for r in items.resolve(shop_conn, " BETA ")] == [b]
    assert [r["id"] for r in items.resolve(shop_conn, "soap")] == [b, c]
    assert [r["id"] for r in items.resolve(shop_conn, "GAMMA")] == [c]
    assert items.resolve(shop_conn, "   ") == []
    assert items.resolve(shop_conn, "zzz") == []


def test_resolve_treats_percent_literally(shop_conn):
    items.create_item(shop_conn, name="Alpha", sell_price_paise=100)
    assert items.resolve(shop_conn, "%") == []


def test_resolve_skips_inactive_items(shop_conn):
    iid = items.create_item(shop_conn, name="Old stock", sell_price_paise=100)
    shop_conn.execute("UPDATE item SET active=0 WHERE id=?", (iid,))
    assert items.resolve(shop_conn, "old") == []


@pytest.mark.parametrize("text,expected", [
    ("3*8901719101015", (3000, "8901719101015")),
    ("0.75 * rice", (750, "rice")),
    ("rice", (1000, "rice")),
    ("  rice  ", (1000, "rice")),
    ("12", (1000, "12")),
])
def test_parse_entry(text, expected):
    assert items.parse_entry(text) == expected


def test_duplicate_sku_and_barcode_rejected(shop_conn):
    items.create_item(shop_conn, name="A", sell_price_paise=100, sku="X", barcodes=["1"])
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, name="B", sell_price_paise=100, sku="X")
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, name="C", sell_price_paise=100, barcodes=["1"])
    assert shop_conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 1


@pytest.mark.parametrize("kwargs", [
    {"name": "", "sell_price_paise": 100},
    {"name": "A", "sell_price_paise": -1},
    {"name": "A", "sell_price_paise": 100, "tracking": "magic"},
    {"name": "A", "sell_price_paise": 100, "barcodes": [""]},
])
def test_create_item_validation(shop_conn, kwargs):
    with pytest.raises(items.ItemError):
        items.create_item(shop_conn, **kwargs)


def test_create_item_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        items.create_item(shop_conn, name="A", sell_price_paise=100)


def test_name_search_stays_fast_on_a_large_catalogue(shop_conn):
    shop_conn.execute("BEGIN")
    shop_conn.executemany(
        "INSERT INTO item(name, sku, sell_price_paise) VALUES (?,?,?)",
        [(f"Product {i}", f"SKU{i}", 100) for i in range(5000)],
    )
    shop_conn.execute("COMMIT")
    started = time.perf_counter()
    assert len(items.resolve(shop_conn, "product 4999")) == 1
    assert time.perf_counter() - started < 0.25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_shop.py tests/test_items.py -v`
Expected: FAIL — `ImportError: cannot import name 'shop'` from `retail.services`.

- [ ] **Step 3: Write the implementation**

`retail/services/shop.py`:
```python
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
```

`retail/services/items.py`:
```python
import re
import sqlite3

from retail import money
from retail.db import transaction
from retail.guard import writes
from retail.services import audit

TRACKING = ("none", "weighed", "batch", "serial")
_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\*\s*(.+?)\s*$")


class ItemError(ValueError):
    pass


def _insert_barcode(conn, item_id, code):
    code = (code or "").strip()
    if not code:
        raise ItemError("Barcode cannot be empty")
    try:
        conn.execute("INSERT INTO item_barcode(code, item_id) VALUES (?,?)", (code, item_id))
    except sqlite3.IntegrityError as exc:
        raise ItemError(f"Barcode {code!r} is already used by another item") from exc


@writes
def create_item(conn, *, name, sell_price_paise, gst_rate_bp=0, unit="pcs", tracking="none",
                sku=None, hsn=None, buy_price_paise=0, reorder_milli=0, warranty_months=0,
                barcodes=()):
    name = (name or "").strip()
    if not name:
        raise ItemError("Item name is required")
    if sell_price_paise < 0:
        raise ItemError("Selling price cannot be negative")
    if tracking not in TRACKING:
        raise ItemError(f"tracking must be one of {TRACKING}")
    sku = (sku or "").strip() or None
    with transaction(conn):
        try:
            cur = conn.execute(
                """INSERT INTO item(name, sku, hsn, gst_rate_bp, unit, sell_price_paise,
                       buy_price_paise, reorder_milli, warranty_months, tracking)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (name, sku, hsn, gst_rate_bp, unit, sell_price_paise, buy_price_paise,
                 reorder_milli, warranty_months, tracking),
            )
        except sqlite3.IntegrityError as exc:
            raise ItemError(f"SKU {sku!r} is already used by another item") from exc
        item_id = cur.lastrowid
        for code in barcodes:
            _insert_barcode(conn, item_id, code)
        audit.log(conn, "create", "item", item_id, name)
    return item_id


@writes
def add_barcode(conn, item_id, code):
    with transaction(conn):
        _insert_barcode(conn, item_id, code)


def resolve(conn, text, limit=20):
    """Barcode (exact) -> SKU (exact) -> name (substring, case-insensitive)."""
    text = (text or "").strip()
    if not text:
        return []
    by_barcode = conn.execute(
        "SELECT i.* FROM item i JOIN item_barcode b ON b.item_id = i.id WHERE b.code = ? AND i.active = 1",
        (text,),
    ).fetchall()
    if by_barcode:
        return by_barcode
    by_sku = conn.execute("SELECT * FROM item WHERE sku = ? AND active = 1", (text,)).fetchall()
    if by_sku:
        return by_sku
    return conn.execute(
        "SELECT * FROM item WHERE active = 1 AND instr(lower(name), lower(?)) > 0 ORDER BY name LIMIT ?",
        (text, limit),
    ).fetchall()


def parse_entry(text):
    """'3*abc' -> (3000, 'abc'); anything else -> (1000, stripped text)."""
    match = _PREFIX.match(text or "")
    if match:
        return money.qty_to_milli(match.group(1)), match.group(2)
    return 1000, (text or "").strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_shop.py tests/test_items.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add shop setup and item catalogue with barcode/sku/name resolution" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Stock ledger

**Files:**
- Create: `retail/services/stock.py`, `tests/test_stock.py`

**Interfaces:**
- Consumes: `db.transaction`, `guard.writes`, `clock.now_iso`, tables `stock_movement`, `stock_unit`, `item`.
- Produces: `stock.InsufficientStock`, `stock.DuplicateSerial`; `stock.record(conn, item_id, qty_milli, mtype, ref_type=None, ref_id=None, unit_id=None) -> int`; `stock._record(...)` same signature, no transaction (for use inside other services' transactions); `stock.on_hand(conn, item_id) -> int`; `stock.unit_on_hand(conn, unit_id) -> int`; `stock.add_unit(conn, item_id, *, serial=None, batch_no=None, expiry=None) -> int` and `stock._add_unit` (no transaction); `stock.find_serial(conn, item_id, serial) -> Row | None` (normalises: strip + upper); `stock.find_batch(conn, item_id, batch_no) -> int | None`; `stock.pick_batch(conn, item_id) -> int | None` (earliest expiry with positive on-hand); `stock.check_available(conn, item_id, qty_milli, policy) -> str` returns `"ok"` or `"warn"`, raises `InsufficientStock` under `block`; `stock.low_stock(conn) -> list[Row]`. Movement types: `opening`, `purchase`, `sale`, `sale_return`, `purchase_return`, `adjustment`.

- [ ] **Step 1: Write the failing tests**

`tests/test_stock.py`:
```python
import pytest

from retail.services import items, stock


@pytest.fixture
def rice(shop_conn):
    return items.create_item(shop_conn, name="Rice", sell_price_paise=6000, unit="kg", tracking="weighed")


def test_record_and_on_hand(shop_conn, rice):
    other = items.create_item(shop_conn, name="Dal", sell_price_paise=100)
    stock.record(shop_conn, rice, 10_000, "opening")
    stock.record(shop_conn, rice, -2_500, "sale", "bill", 1)
    stock.record(shop_conn, other, 5_000, "opening")
    assert stock.on_hand(shop_conn, rice) == 7_500
    assert stock.on_hand(shop_conn, other) == 5_000


def test_record_rejects_zero_and_unknown_type(shop_conn, rice):
    with pytest.raises(Exception):
        stock.record(shop_conn, rice, 0, "opening")
    with pytest.raises(Exception):
        stock.record(shop_conn, rice, 1000, "gift")
    assert stock.on_hand(shop_conn, rice) == 0


def test_serial_units_are_normalised_and_unique(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    uid = stock.add_unit(shop_conn, phone, serial="  ab123 ")
    assert stock.find_serial(shop_conn, phone, "AB123")["id"] == uid
    assert stock.find_serial(shop_conn, phone, " ab123 ")["id"] == uid
    assert stock.find_serial(shop_conn, phone, "nope") is None
    with pytest.raises(stock.DuplicateSerial):
        stock.add_unit(shop_conn, phone, serial="AB123")


def test_pick_batch_chooses_earliest_expiry_with_stock(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    late = stock.add_unit(shop_conn, milk, batch_no="A", expiry="2026-12-01")
    early = stock.add_unit(shop_conn, milk, batch_no="B", expiry="2026-10-01")
    empty = stock.add_unit(shop_conn, milk, batch_no="C", expiry="2026-09-01")
    for uid in (late, early):
        stock.record(shop_conn, milk, 5_000, "purchase", unit_id=uid)
    stock.record(shop_conn, milk, 1_000, "purchase", unit_id=empty)
    stock.record(shop_conn, milk, -1_000, "sale", unit_id=empty)
    assert stock.unit_on_hand(shop_conn, early) == 5_000
    assert stock.pick_batch(shop_conn, milk) == early
    assert stock.find_batch(shop_conn, milk, "A") == late
    assert stock.find_batch(shop_conn, milk, "Z") is None


def test_pick_batch_none_when_nothing_in_stock(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    assert stock.pick_batch(shop_conn, milk) is None


def test_check_available_policies(shop_conn, rice):
    stock.record(shop_conn, rice, 1_000, "opening")
    assert stock.check_available(shop_conn, rice, 1_000, "block") == "ok"
    assert stock.check_available(shop_conn, rice, 2_000, "warn") == "warn"
    assert stock.check_available(shop_conn, rice, 2_000, "allow") == "ok"
    with pytest.raises(stock.InsufficientStock):
        stock.check_available(shop_conn, rice, 2_000, "block")


def test_low_stock_lists_items_at_or_below_reorder_level(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=100, reorder_milli=5_000)
    b = items.create_item(shop_conn, name="B", sell_price_paise=100, reorder_milli=5_000)
    items.create_item(shop_conn, name="C", sell_price_paise=100)  # no reorder level
    stock.record(shop_conn, a, 5_000, "opening")
    stock.record(shop_conn, b, 6_000, "opening")
    assert [r["name"] for r in stock.low_stock(shop_conn)] == ["A"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_stock.py -v`
Expected: FAIL — `ImportError: cannot import name 'stock'`.

- [ ] **Step 3: Write the implementation**

`retail/services/stock.py`:
```python
"""Append-only stock ledger. Quantity on hand is always derived from movements."""
import sqlite3

from retail import clock
from retail.db import transaction
from retail.guard import writes


class InsufficientStock(ValueError):
    pass


class DuplicateSerial(ValueError):
    pass


def _norm_serial(serial):
    return (serial or "").strip().upper()


def _record(conn, item_id, qty_milli, mtype, ref_type=None, ref_id=None, unit_id=None):
    cur = conn.execute(
        """INSERT INTO stock_movement(item_id, unit_id, qty_milli, type, ref_type, ref_id, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (item_id, unit_id, qty_milli, mtype, ref_type, ref_id, clock.now_iso()),
    )
    return cur.lastrowid


@writes
def record(conn, item_id, qty_milli, mtype, ref_type=None, ref_id=None, unit_id=None):
    with transaction(conn):
        return _record(conn, item_id, qty_milli, mtype, ref_type, ref_id, unit_id)


def on_hand(conn, item_id):
    return conn.execute(
        "SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE item_id = ?", (item_id,)
    ).fetchone()[0]


def unit_on_hand(conn, unit_id):
    return conn.execute(
        "SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE unit_id = ?", (unit_id,)
    ).fetchone()[0]


def _add_unit(conn, item_id, *, serial=None, batch_no=None, expiry=None):
    serial = _norm_serial(serial) or None
    try:
        cur = conn.execute(
            "INSERT INTO stock_unit(item_id, serial, batch_no, expiry) VALUES (?,?,?,?)",
            (item_id, serial, batch_no, expiry),
        )
    except sqlite3.IntegrityError as exc:
        raise DuplicateSerial(f"Serial {serial!r} already exists for this item") from exc
    return cur.lastrowid


@writes
def add_unit(conn, item_id, *, serial=None, batch_no=None, expiry=None):
    with transaction(conn):
        return _add_unit(conn, item_id, serial=serial, batch_no=batch_no, expiry=expiry)


def find_serial(conn, item_id, serial):
    return conn.execute(
        "SELECT * FROM stock_unit WHERE item_id = ? AND serial = ?", (item_id, _norm_serial(serial))
    ).fetchone()


def find_batch(conn, item_id, batch_no):
    row = conn.execute(
        "SELECT id FROM stock_unit WHERE item_id = ? AND serial IS NULL AND batch_no = ?",
        (item_id, batch_no),
    ).fetchone()
    return row["id"] if row else None


def pick_batch(conn, item_id):
    """Earliest-expiry batch that still has stock (no expiry sorts last)."""
    row = conn.execute(
        """SELECT u.id FROM stock_unit u
           WHERE u.item_id = ? AND u.serial IS NULL AND u.batch_no IS NOT NULL
             AND (SELECT COALESCE(SUM(qty_milli), 0) FROM stock_movement WHERE unit_id = u.id) > 0
           ORDER BY (u.expiry IS NULL), u.expiry, u.id LIMIT 1""",
        (item_id,),
    ).fetchone()
    return row["id"] if row else None


def check_available(conn, item_id, qty_milli, policy):
    """Return 'ok' or 'warn'; raise InsufficientStock when the policy is 'block'."""
    have = on_hand(conn, item_id)
    if have >= qty_milli:
        return "ok"
    if policy == "block":
        raise InsufficientStock(f"Only {have / 1000:g} in stock")
    return "warn" if policy == "warn" else "ok"


def low_stock(conn):
    return conn.execute(
        """SELECT i.*, COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0) AS on_hand_milli
           FROM item i
           WHERE i.active = 1 AND i.reorder_milli > 0
             AND COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0) <= i.reorder_milli
           ORDER BY i.name"""
    ).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_stock.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add append-only stock ledger with serial and batch units" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: GST line calculation

**Files:**
- Create: `retail/services/gst.py`, `tests/test_gst.py`

**Interfaces:**
- Produces: `gst.LineTax` (frozen dataclass: `taxable`, `cgst`, `sgst`, `igst`, `total`, all int paise); `gst.split_line(amount_paise: int, rate_bp: int, *, inclusive: bool, intra_state: bool) -> LineTax`; `gst.is_intra_state(shop_state: str, party_state: str | None) -> bool` (unknown party state counts as intra-state). `rate_bp` is basis points: 1800 = 18%.

- [ ] **Step 1: Write the failing tests**

`tests/test_gst.py`:
```python
import pytest

from retail.services import gst


def test_inclusive_intra_state_splits_evenly():
    t = gst.split_line(11800, 1800, inclusive=True, intra_state=True)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total) == (10000, 900, 900, 0, 11800)


def test_exclusive_inter_state_uses_igst():
    t = gst.split_line(10000, 1800, inclusive=False, intra_state=False)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total) == (10000, 0, 0, 1800, 11800)


def test_odd_paise_tax_gives_extra_paisa_to_sgst():
    t = gst.split_line(100, 500, inclusive=True, intra_state=True)
    assert (t.taxable, t.cgst, t.sgst, t.total) == (95, 2, 3, 100)


def test_zero_rate_has_no_tax():
    t = gst.split_line(5000, 0, inclusive=True, intra_state=True)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total) == (5000, 0, 0, 0, 5000)


@pytest.mark.parametrize("amount", [1, 99, 1049, 11799, 123457])
@pytest.mark.parametrize("rate", [500, 1800, 4000])
def test_parts_always_sum_to_total(amount, rate):
    for inclusive in (True, False):
        for intra in (True, False):
            t = gst.split_line(amount, rate, inclusive=inclusive, intra_state=intra)
            assert t.taxable + t.cgst + t.sgst + t.igst == t.total


def test_is_intra_state():
    assert gst.is_intra_state("36", "36") is True
    assert gst.is_intra_state("36", "27") is False
    assert gst.is_intra_state("36", None) is True
    assert gst.is_intra_state("36", "") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_gst.py -v`
Expected: FAIL — `ImportError: cannot import name 'gst'`.

- [ ] **Step 3: Write the implementation**

`retail/services/gst.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class LineTax:
    taxable: int
    cgst: int
    sgst: int
    igst: int
    total: int


def _div_round(numerator: int, denominator: int) -> int:
    """Integer division rounded half-up (numerator >= 0)."""
    return (2 * numerator + denominator) // (2 * denominator)


def split_line(amount_paise, rate_bp, *, inclusive, intra_state):
    if rate_bp == 0:
        return LineTax(amount_paise, 0, 0, 0, amount_paise)
    if inclusive:
        taxable = _div_round(amount_paise * 10000, 10000 + rate_bp)
        tax = amount_paise - taxable
        total = amount_paise
    else:
        taxable = amount_paise
        tax = _div_round(amount_paise * rate_bp, 10000)
        total = amount_paise + tax
    if intra_state:
        cgst = tax // 2
        return LineTax(taxable, cgst, tax - cgst, 0, total)
    return LineTax(taxable, 0, 0, tax, total)


def is_intra_state(shop_state, party_state):
    return not party_state or party_state == shop_state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_gst.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add GST line tax split" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Parties and udhaar ledger

**Files:**
- Create: `retail/services/parties.py`, `tests/test_parties.py`

**Interfaces:**
- Consumes: `db.transaction`, `guard.writes`, `audit.log`, `clock.now_iso`, tables `party`, `party_payment`, `bill`, `payment`.
- Produces: `parties.PartyError`; `parties.create_party(conn, *, name, phone=None, gstin=None, state_code=None, type="customer", opening_balance_paise=0) -> int`; `parties.balance(conn, party_id) -> int` (positive = the party owes the shop): opening balance + credit payments on final sale bills − credit payments on final return bills − received payments; `parties.receive_payment(conn, party_id, amount_paise, mode="cash", note="") -> int`; `parties.list_dues(conn) -> list[dict]` (`party_id`, `name`, `phone`, `balance_paise` for balances > 0, largest first).

- [ ] **Step 1: Write the failing tests**

`tests/test_parties.py`:
```python
import pytest

from retail.services import parties


def test_create_party_and_opening_balance(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", phone="9876543210", state_code="36",
                               opening_balance_paise=25000)
    assert parties.balance(shop_conn, pid) == 25000


def test_receive_payment_reduces_balance(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", opening_balance_paise=25000)
    parties.receive_payment(shop_conn, pid, 10000, mode="upi", note="part payment")
    assert parties.balance(shop_conn, pid) == 15000


@pytest.mark.parametrize("amount", [0, -5])
def test_receive_payment_requires_positive_amount(shop_conn, amount):
    pid = parties.create_party(shop_conn, name="Ravi")
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, pid, amount)


def test_receive_payment_rejects_bad_mode_and_unknown_party(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi")
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, pid, 100, mode="credit")
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, 999, 100)


def test_create_party_validation(shop_conn):
    with pytest.raises(parties.PartyError):
        parties.create_party(shop_conn, name=" ")
    with pytest.raises(parties.PartyError):
        parties.create_party(shop_conn, name="X", type="alien")


def test_list_dues_orders_largest_first_and_hides_zero(shop_conn):
    a = parties.create_party(shop_conn, name="A", opening_balance_paise=100)
    b = parties.create_party(shop_conn, name="B", opening_balance_paise=900)
    parties.create_party(shop_conn, name="C")
    dues = parties.list_dues(shop_conn)
    assert [d["name"] for d in dues] == ["B", "A"]
    assert dues[0]["balance_paise"] == 900 and dues[0]["party_id"] == b and a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_parties.py -v`
Expected: FAIL — `ImportError: cannot import name 'parties'`.

- [ ] **Step 3: Write the implementation**

`retail/services/parties.py`:
```python
from retail import clock
from retail.db import transaction
from retail.guard import writes
from retail.services import audit

_TYPES = ("customer", "supplier", "both")
_RECEIVE_MODES = ("cash", "upi", "card")


class PartyError(ValueError):
    pass


@writes
def create_party(conn, *, name, phone=None, gstin=None, state_code=None, type="customer",
                 opening_balance_paise=0):
    name = (name or "").strip()
    if not name:
        raise PartyError("Party name is required")
    if type not in _TYPES:
        raise PartyError(f"type must be one of {_TYPES}")
    with transaction(conn):
        cur = conn.execute(
            """INSERT INTO party(name, phone, gstin, state_code, type, opening_balance_paise)
               VALUES (?,?,?,?,?,?)""",
            (name, phone, gstin, state_code, type, opening_balance_paise),
        )
        audit.log(conn, "create", "party", cur.lastrowid, name)
    return cur.lastrowid


def balance(conn, party_id):
    """Positive means the party owes the shop (udhaar)."""
    row = conn.execute(
        """SELECT p.opening_balance_paise
             + COALESCE((SELECT SUM(CASE b.kind WHEN 'sale' THEN pay.amount_paise
                                                ELSE -pay.amount_paise END)
                         FROM payment pay JOIN bill b ON b.id = pay.bill_id
                         WHERE b.party_id = p.id AND b.status = 'final' AND pay.mode = 'credit'), 0)
             - COALESCE((SELECT SUM(amount_paise) FROM party_payment WHERE party_id = p.id), 0)
           FROM party p WHERE p.id = ?""",
        (party_id,),
    ).fetchone()
    if row is None:
        raise PartyError("No such party")
    return row[0]


@writes
def receive_payment(conn, party_id, amount_paise, mode="cash", note=""):
    if amount_paise <= 0:
        raise PartyError("Payment must be greater than zero")
    if mode not in _RECEIVE_MODES:
        raise PartyError(f"mode must be one of {_RECEIVE_MODES}")
    with transaction(conn):
        if conn.execute("SELECT 1 FROM party WHERE id = ?", (party_id,)).fetchone() is None:
            raise PartyError("No such party")
        cur = conn.execute(
            "INSERT INTO party_payment(party_id, amount_paise, mode, note, created_at) VALUES (?,?,?,?,?)",
            (party_id, amount_paise, mode, note, clock.now_iso()),
        )
        audit.log(conn, "receive_payment", "party", party_id, f"{amount_paise} via {mode}")
    return cur.lastrowid


def list_dues(conn):
    dues = []
    for p in conn.execute("SELECT id, name, phone FROM party WHERE type IN ('customer','both')").fetchall():
        bal = balance(conn, p["id"])
        if bal > 0:
            dues.append({"party_id": p["id"], "name": p["name"], "phone": p["phone"], "balance_paise": bal})
    return sorted(dues, key=lambda d: (-d["balance_paise"], d["name"]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_parties.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add parties and udhaar balance ledger" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Billing — building a held bill (lines, tax, totals, hold)

**Files:**
- Create: `retail/services/billing.py`, `tests/test_billing_lines.py`

**Interfaces:**
- Consumes: `shop.get_shop`, `items` rows, `stock.find_serial`, `stock.pick_batch`, `stock.check_available`, `stock.InsufficientStock`, `gst.split_line`, `gst.is_intra_state`, `money.line_amount`, `money.round_to_rupee`, `db.transaction`, `guard.writes`, `audit.log`, `clock.now_iso`.
- Produces: `billing.BillingError(ValueError)`, `billing.SerialUnavailable(BillingError)`, `billing.PAYMENT_MODES`; `billing.start_bill(conn, *, party_id=None) -> int`; `billing.add_line(conn, bill_id, item_id, qty_milli=1000, *, serial=None, unit_id=None, discount_paise=0, rate_paise=None) -> int`; `billing.remove_line(conn, bill_id, line_id) -> None`; `billing.set_party(conn, bill_id, party_id) -> None`; `billing.get_bill(conn, bill_id) -> {"bill": Row, "lines": list[Row]}`; `billing.list_held(conn) -> list[Row]`; `billing.cancel_held(conn, bill_id) -> None`; internal `billing._bill(conn, bill_id, *, status=None) -> Row`, `billing._retax(conn, bill_id) -> None`, `billing._next_number(conn, name, prefix) -> str`. Held bills have `bill_no = NULL`; totals on the bill row are kept current after every change; `bill.total_paise` is rounded to the whole rupee and `round_off_paise` holds the adjustment.

- [ ] **Step 1: Write the failing tests**

`tests/test_billing_lines.py`:
```python
import pytest

from retail.services import billing, items, parties, shop, stock
from retail.services.billing import BillingError, SerialUnavailable


def add_stock(conn, item_id, qty_milli):
    stock.record(conn, item_id, qty_milli, "opening")


def add_phone(conn, item_id, serial):
    unit = stock.add_unit(conn, item_id, serial=serial)
    stock.record(conn, item_id, 1000, "opening", unit_id=unit)
    return unit


def totals(conn, bill_id):
    b = billing.get_bill(conn, bill_id)["bill"]
    return (b["taxable_paise"], b["cgst_paise"], b["sgst_paise"], b["igst_paise"],
            b["round_off_paise"], b["total_paise"])


@pytest.fixture
def soap(shop_conn):  # Rs 118.00 MRP-inclusive, 18% GST
    iid = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    add_stock(shop_conn, iid, 10_000)
    return iid


def test_line_totals_gst_inclusive(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    assert totals(shop_conn, bill_id) == (10000, 900, 900, 0, 0, 11800)


def test_weighed_item_takes_fractional_quantity(shop_conn):
    rice = items.create_item(shop_conn, name="Rice", sell_price_paise=6000, unit="kg", tracking="weighed")
    add_stock(shop_conn, rice, 20_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, rice, 750)
    assert totals(shop_conn, bill_id)[-1] == 4500


def test_total_is_rounded_to_whole_rupee(shop_conn):
    toffee = items.create_item(shop_conn, name="Toffee bag", sell_price_paise=1049)
    add_stock(shop_conn, toffee, 5_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, toffee, 1000)
    assert totals(shop_conn, bill_id)[-2:] == (-49, 1000)


def test_inter_state_customer_gets_igst(shop_conn, soap):
    pune = parties.create_party(shop_conn, name="Pune Traders", state_code="27")
    bill_id = billing.start_bill(shop_conn, party_id=pune)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    assert totals(shop_conn, bill_id) == (10000, 0, 0, 1800, 0, 11800)


def test_set_party_retaxes_existing_lines(shop_conn, soap):
    pune = parties.create_party(shop_conn, name="Pune Traders", state_code="27")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.set_party(shop_conn, bill_id, pune)
    assert totals(shop_conn, bill_id) == (10000, 0, 0, 1800, 0, 11800)


def test_estimate_mode_applies_no_tax(shop_conn):
    shop.setup_shop(shop_conn, name="Small Shop", state_code="36", gst_enabled=False)
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    add_stock(shop_conn, soap, 1_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    assert totals(shop_conn, bill_id) == (11800, 0, 0, 0, 0, 11800)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["gst_mode"] == "estimate"


def test_discount_and_price_override(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, soap, 1000, discount_paise=1800)
    assert totals(shop_conn, bill_id)[-1] == 10000
    billing.add_line(shop_conn, bill_id, soap, 1000, rate_paise=5000)
    assert totals(shop_conn, bill_id)[-1] == 15000
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, 1000, discount_paise=99999)


@pytest.mark.parametrize("qty", [500, 0, -1000, 1500])
def test_non_weighed_item_rejects_fractional_zero_or_negative_quantity(shop_conn, soap, qty):
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, qty)
    assert billing.get_bill(shop_conn, bill_id)["lines"] == []


def test_serial_is_normalised_and_must_exist_in_stock(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, phone, 1000, serial="  imei123 ")
    assert line_id
    with pytest.raises(SerialUnavailable):
        billing.add_line(shop_conn, bill_id, phone, 1000, serial="UNKNOWN")
    with pytest.raises(SerialUnavailable):
        billing.add_line(shop_conn, bill_id, phone, 1000, serial=None)


def test_same_serial_cannot_be_added_twice_to_one_bill(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="IMEI123")
    with pytest.raises(SerialUnavailable):
        billing.add_line(shop_conn, bill_id, phone, 1000, serial="imei123")
    assert len(billing.get_bill(shop_conn, bill_id)["lines"]) == 1


def test_serial_items_sell_one_unit_per_line(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, phone, 2000, serial="IMEI123")


def test_batch_item_auto_picks_earliest_expiry(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    late = stock.add_unit(shop_conn, milk, batch_no="A", expiry="2026-12-01")
    early = stock.add_unit(shop_conn, milk, batch_no="B", expiry="2026-10-01")
    for uid in (late, early):
        stock.record(shop_conn, milk, 5_000, "purchase", unit_id=uid)
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, milk, 2000)
    line = [ln for ln in billing.get_bill(shop_conn, bill_id)["lines"] if ln["id"] == line_id][0]
    assert line["unit_id"] == early


def test_batch_item_without_stock_is_rejected(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, milk, 1000)


def test_block_policy_counts_quantity_already_on_the_bill(shop_conn):
    shop.setup_shop(shop_conn, name="S", state_code="36", oversell_policy="block")
    it = items.create_item(shop_conn, name="Tea", sell_price_paise=100)
    add_stock(shop_conn, it, 2_000)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, it, 1000)
    billing.add_line(shop_conn, bill_id, it, 1000)
    with pytest.raises(stock.InsufficientStock):
        billing.add_line(shop_conn, bill_id, it, 1000)


def test_warn_policy_allows_selling_below_stock(shop_conn):
    it = items.create_item(shop_conn, name="Tea", sell_price_paise=100)
    bill_id = billing.start_bill(shop_conn)
    assert billing.add_line(shop_conn, bill_id, it, 1000)


def test_remove_line_updates_totals(shop_conn, soap):
    bill_id = billing.start_bill(shop_conn)
    first = billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.add_line(shop_conn, bill_id, soap, 1000)
    billing.remove_line(shop_conn, bill_id, first)
    assert totals(shop_conn, bill_id)[-1] == 11800
    with pytest.raises(BillingError):
        billing.remove_line(shop_conn, bill_id, first)


def test_hold_list_and_cancel(shop_conn, soap):
    a = billing.start_bill(shop_conn)
    b = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, a, soap, 1000)
    assert {r["id"] for r in billing.list_held(shop_conn)} == {a, b}
    billing.cancel_held(shop_conn, b)
    assert [r["id"] for r in billing.list_held(shop_conn)] == [a]
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, b, soap, 1000)
    assert billing.get_bill(shop_conn, a)["bill"]["bill_no"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_billing_lines.py -v`
Expected: FAIL — `ImportError: cannot import name 'billing'`.

- [ ] **Step 3: Write the implementation**

`retail/services/billing.py`:
```python
"""Sale bills. A bill is built as 'held', finalized once, and never edited afterwards.
Money is integer paise; quantity is integer milli-units."""
from retail import clock, money
from retail.db import transaction
from retail.guard import writes
from retail.services import audit, gst, shop, stock

PAYMENT_MODES = ("cash", "upi", "card", "emi", "credit")
REFUND_MODES = ("cash", "upi", "card", "credit")


class BillingError(ValueError):
    pass


class SerialUnavailable(BillingError):
    pass


def _bill(conn, bill_id, *, status=None):
    row = conn.execute("SELECT * FROM bill WHERE id = ?", (bill_id,)).fetchone()
    if row is None:
        raise BillingError("No such bill")
    if status is not None and row["status"] != status:
        raise BillingError(f"Bill is {row['status']}, expected {status}")
    return row


def _item(conn, item_id):
    row = conn.execute("SELECT * FROM item WHERE id = ? AND active = 1", (item_id,)).fetchone()
    if row is None:
        raise BillingError("No such item")
    return row


def _next_number(conn, name, prefix):
    conn.execute(
        "INSERT INTO counter(name, value) VALUES (?, 1) ON CONFLICT(name) DO UPDATE SET value = value + 1",
        (name,),
    )
    value = conn.execute("SELECT value FROM counter WHERE name = ?", (name,)).fetchone()[0]
    return f"{prefix}{value:06d}"


def _retax(conn, bill_id):
    """Recompute every line's tax and the bill totals from the stored line amounts."""
    bill = _bill(conn, bill_id)
    s = shop.get_shop(conn)
    party_state = None
    if bill["party_id"] is not None:
        party_state = conn.execute(
            "SELECT state_code FROM party WHERE id = ?", (bill["party_id"],)
        ).fetchone()["state_code"]
    intra = gst.is_intra_state(s["state_code"], party_state)
    inclusive = bool(s["price_includes_gst"])
    taxable = cgst = sgst = igst = grand = 0
    for line in conn.execute(
        "SELECT id, amount_paise, gst_rate_bp FROM bill_line WHERE bill_id = ?", (bill_id,)
    ).fetchall():
        rate = line["gst_rate_bp"] if bill["gst_mode"] == "gst" else 0
        t = gst.split_line(line["amount_paise"], rate, inclusive=inclusive, intra_state=intra)
        conn.execute(
            """UPDATE bill_line SET taxable_paise=?, cgst_paise=?, sgst_paise=?, igst_paise=?, total_paise=?
               WHERE id = ?""",
            (t.taxable, t.cgst, t.sgst, t.igst, t.total, line["id"]),
        )
        taxable += t.taxable
        cgst += t.cgst
        sgst += t.sgst
        igst += t.igst
        grand += t.total
    rounded, round_off = money.round_to_rupee(grand)
    conn.execute(
        """UPDATE bill SET taxable_paise=?, cgst_paise=?, sgst_paise=?, igst_paise=?,
               round_off_paise=?, total_paise=? WHERE id = ?""",
        (taxable, cgst, sgst, igst, round_off, rounded, bill_id),
    )


@writes
def start_bill(conn, *, party_id=None):
    s = shop.get_shop(conn)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO bill(kind, status, party_id, gst_mode, created_at) VALUES ('sale','held',?,?,?)",
            (party_id, "gst" if s["gst_enabled"] else "estimate", clock.now_iso()),
        )
    return cur.lastrowid


@writes
def add_line(conn, bill_id, item_id, qty_milli=1000, *, serial=None, unit_id=None,
             discount_paise=0, rate_paise=None):
    with transaction(conn):
        bill = _bill(conn, bill_id, status="held")
        if bill["kind"] != "sale":
            raise BillingError("Lines can only be added to a sale bill")
        item = _item(conn, item_id)
        if qty_milli <= 0:
            raise BillingError("Quantity must be greater than zero")
        if discount_paise < 0:
            raise BillingError("Discount cannot be negative")
        tracking = item["tracking"]
        if tracking != "weighed" and qty_milli % 1000:
            raise BillingError("Only weighed items can be sold in fractions")
        s = shop.get_shop(conn)
        if tracking == "serial":
            if qty_milli != 1000:
                raise BillingError("Serial-tracked items are sold one unit per line")
            unit = stock.find_serial(conn, item_id, serial or "")
            if unit is None or unit["status"] != "in_stock":
                raise SerialUnavailable(f"Serial {serial!r} is not in stock")
            if conn.execute(
                "SELECT 1 FROM bill_line WHERE bill_id = ? AND unit_id = ?", (bill_id, unit["id"])
            ).fetchone():
                raise SerialUnavailable("That serial is already on this bill")
            unit_id = unit["id"]
        else:
            if tracking == "batch":
                if unit_id is None:
                    unit_id = stock.pick_batch(conn, item_id)
                if unit_id is None:
                    raise BillingError("No batch in stock for this item")
                if conn.execute(
                    "SELECT 1 FROM stock_unit WHERE id = ? AND item_id = ?", (unit_id, item_id)
                ).fetchone() is None:
                    raise BillingError("That batch does not belong to this item")
            else:
                unit_id = None
            already = conn.execute(
                "SELECT COALESCE(SUM(qty_milli), 0) FROM bill_line WHERE bill_id = ? AND item_id = ?",
                (bill_id, item_id),
            ).fetchone()[0]
            stock.check_available(conn, item_id, already + qty_milli, s["oversell_policy"])
        rate = item["sell_price_paise"] if rate_paise is None else rate_paise
        if rate < 0:
            raise BillingError("Rate cannot be negative")
        amount = money.line_amount(rate, qty_milli) - discount_paise
        if amount < 0:
            raise BillingError("Discount is larger than the line amount")
        cur = conn.execute(
            """INSERT INTO bill_line(bill_id, item_id, unit_id, qty_milli, rate_paise, discount_paise,
                   amount_paise, gst_rate_bp) VALUES (?,?,?,?,?,?,?,?)""",
            (bill_id, item_id, unit_id, qty_milli, rate, discount_paise, amount, item["gst_rate_bp"]),
        )
        _retax(conn, bill_id)
    return cur.lastrowid


@writes
def remove_line(conn, bill_id, line_id):
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        cur = conn.execute("DELETE FROM bill_line WHERE id = ? AND bill_id = ?", (line_id, bill_id))
        if cur.rowcount == 0:
            raise BillingError("No such line on this bill")
        _retax(conn, bill_id)


@writes
def set_party(conn, bill_id, party_id):
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        conn.execute("UPDATE bill SET party_id = ? WHERE id = ?", (party_id, bill_id))
        _retax(conn, bill_id)


def get_bill(conn, bill_id):
    bill = _bill(conn, bill_id)
    lines = conn.execute("SELECT * FROM bill_line WHERE bill_id = ? ORDER BY id", (bill_id,)).fetchall()
    return {"bill": bill, "lines": lines}


def list_held(conn):
    return conn.execute(
        "SELECT * FROM bill WHERE kind = 'sale' AND status = 'held' ORDER BY id"
    ).fetchall()


@writes
def cancel_held(conn, bill_id):
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        conn.execute("UPDATE bill SET status = 'cancelled' WHERE id = ?", (bill_id,))
        audit.log(conn, "cancel_held", "bill", bill_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_billing_lines.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: build held sale bills with per-line GST, tracking rules and totals" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Billing — finalize, payments, warranty

**Files:**
- Modify: `retail/services/billing.py` (append `finalize`)
- Create: `tests/test_billing_finalize.py`

**Interfaces:**
- Consumes: everything from Task 7, `stock._record`, `stock.check_available`, `clock.add_months`, `parties.balance` (tests only).
- Produces: `billing.finalize(conn, bill_id, payments, *, today=None) -> str` — `payments` is `list[tuple[str, int]]` of `(mode, amount_paise)`; must sum exactly to `bill.total_paise` (an empty list is allowed only when the total is 0); returns the bill number `S000001`, `S000002`, … Finalizing is atomic: stock movements, sold serials, warranty rows, payments, bill number and audit entry are written together or not at all.

- [ ] **Step 1: Write the failing tests**

`tests/test_billing_finalize.py`:
```python
from datetime import date

import pytest

from retail import guard
from retail.services import billing, items, parties, shop, stock
from retail.services.billing import BillingError, SerialUnavailable


def add_stock(conn, item_id, qty_milli):
    stock.record(conn, item_id, qty_milli, "opening")


def add_phone(conn, item_id, serial):
    unit = stock.add_unit(conn, item_id, serial=serial)
    stock.record(conn, item_id, 1000, "opening", unit_id=unit)
    return unit


@pytest.fixture
def soap(shop_conn):
    iid = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    add_stock(shop_conn, iid, 10_000)
    return iid


def held_soap_bill(conn, soap, qty=1000, party_id=None):
    bill_id = billing.start_bill(conn, party_id=party_id)
    billing.add_line(conn, bill_id, soap, qty)
    return bill_id


def test_finalize_numbers_bills_and_moves_stock(shop_conn, soap):
    a = held_soap_bill(shop_conn, soap, 2000)
    assert billing.finalize(shop_conn, a, [("cash", 23600)]) == "S000001"
    b = held_soap_bill(shop_conn, soap)
    assert billing.finalize(shop_conn, b, [("upi", 5000), ("cash", 6800)]) == "S000002"
    assert stock.on_hand(shop_conn, soap) == 7_000
    bill = billing.get_bill(shop_conn, a)["bill"]
    assert bill["status"] == "final" and bill["bill_no"] == "S000001" and bill["finalized_at"]
    modes = [r["mode"] for r in shop_conn.execute("SELECT mode FROM payment WHERE bill_id = ? ORDER BY id", (b,))]
    assert modes == ["upi", "cash"]


@pytest.mark.parametrize("payments", [
    [("cash", 100)],                 # too little
    [("cash", 99999)],               # too much
    [],                              # nothing paid on a non-zero bill
    [("bitcoin", 11800)],            # unknown mode
    [("cash", 11800), ("cash", 0)],  # zero-value payment row
])
def test_finalize_rejects_bad_payments_and_changes_nothing(shop_conn, soap, payments):
    bill_id = held_soap_bill(shop_conn, soap)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, payments)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "held"
    assert stock.on_hand(shop_conn, soap) == 10_000
    assert shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == 0


def test_finalize_rejects_empty_bill(shop_conn):
    bill_id = billing.start_bill(shop_conn)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, [])
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "held"


def test_credit_sale_needs_a_customer_and_raises_balance(shop_conn, soap):
    anon = held_soap_bill(shop_conn, soap)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, anon, [("credit", 11800)])
    ravi = parties.create_party(shop_conn, name="Ravi")
    bill_id = held_soap_bill(shop_conn, soap, party_id=ravi)
    billing.finalize(shop_conn, bill_id, [("credit", 11800)])
    assert parties.balance(shop_conn, ravi) == 11800
    parties.receive_payment(shop_conn, ravi, 5000)
    assert parties.balance(shop_conn, ravi) == 6800


def test_finalized_bill_is_immutable(shop_conn, soap):
    bill_id = held_soap_bill(shop_conn, soap)
    line_id = billing.get_bill(shop_conn, bill_id)["lines"][0]["id"]
    billing.finalize(shop_conn, bill_id, [("cash", 11800)])
    with pytest.raises(BillingError):
        billing.add_line(shop_conn, bill_id, soap, 1000)
    with pytest.raises(BillingError):
        billing.remove_line(shop_conn, bill_id, line_id)
    with pytest.raises(BillingError):
        billing.set_party(shop_conn, bill_id, None)
    with pytest.raises(BillingError):
        billing.cancel_held(shop_conn, bill_id)
    with pytest.raises(BillingError):
        billing.finalize(shop_conn, bill_id, [("cash", 11800)])


def test_serial_sale_marks_unit_sold_and_creates_warranty(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial",
                              warranty_months=12)
    unit = add_phone(shop_conn, phone, "IMEI123")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="imei123")
    billing.finalize(shop_conn, bill_id, [("cash", 1000000)], today=date(2026, 1, 31))
    assert stock.on_hand(shop_conn, phone) == 0
    assert shop_conn.execute("SELECT status FROM stock_unit WHERE id=?", (unit,)).fetchone()[0] == "sold"
    w = shop_conn.execute("SELECT start_date, end_date FROM warranty WHERE unit_id=?", (unit,)).fetchone()
    assert (w["start_date"], w["end_date"]) == ("2026-01-31", "2027-01-31")


def test_two_bills_racing_for_one_serial_second_fails_without_partial_writes(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    unit = add_phone(shop_conn, phone, "IMEI123")
    first = billing.start_bill(shop_conn)
    second = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, first, phone, 1000, serial="IMEI123")
    billing.add_line(shop_conn, second, phone, 1000, serial="IMEI123")
    billing.finalize(shop_conn, first, [("cash", 1000000)])
    movements_before = shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0]
    with pytest.raises(SerialUnavailable):
        billing.finalize(shop_conn, second, [("cash", 1000000)])
    assert billing.get_bill(shop_conn, second)["bill"]["status"] == "held"
    assert billing.get_bill(shop_conn, second)["bill"]["bill_no"] is None
    assert shop_conn.execute("SELECT COUNT(*) FROM stock_movement").fetchone()[0] == movements_before
    assert shop_conn.execute("SELECT COUNT(*) FROM payment").fetchone()[0] == 1
    assert unit


def test_block_policy_is_rechecked_at_finalize(shop_conn):
    shop.setup_shop(shop_conn, name="S", state_code="36", oversell_policy="block")
    it = items.create_item(shop_conn, name="Tea", sell_price_paise=100)
    add_stock(shop_conn, it, 1_000)
    a = held_soap_bill(shop_conn, it)
    b = held_soap_bill(shop_conn, it)
    billing.finalize(shop_conn, a, [("cash", 100)])
    with pytest.raises(stock.InsufficientStock):
        billing.finalize(shop_conn, b, [("cash", 100)])
    assert stock.on_hand(shop_conn, it) == 0


def test_free_bill_can_be_finalized_without_payments(shop_conn):
    gift = items.create_item(shop_conn, name="Free sample", sell_price_paise=0)
    add_stock(shop_conn, gift, 1_000)
    bill_id = held_soap_bill(shop_conn, gift)
    assert billing.finalize(shop_conn, bill_id, []) == "S000001"


def test_start_bill_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        billing.start_bill(shop_conn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_billing_finalize.py -v`
Expected: FAIL — `AttributeError: module 'retail.services.billing' has no attribute 'finalize'`.

- [ ] **Step 3: Write the implementation**

Append to `retail/services/billing.py`:
```python
@writes
def finalize(conn, bill_id, payments, *, today=None):
    """Finish a held sale bill. `payments` is [(mode, amount_paise), ...]."""
    today = today or clock.today()
    with transaction(conn):
        bill = _bill(conn, bill_id, status="held")
        if bill["kind"] != "sale":
            raise BillingError("Only sale bills are finalized here")
        lines = conn.execute(
            """SELECT l.*, i.tracking, i.warranty_months FROM bill_line l
               JOIN item i ON i.id = l.item_id WHERE l.bill_id = ? ORDER BY l.id""",
            (bill_id,),
        ).fetchall()
        if not lines:
            raise BillingError("Cannot finalize an empty bill")
        for mode, amount in payments:
            if mode not in PAYMENT_MODES:
                raise BillingError(f"Unknown payment mode {mode!r}")
            if amount <= 0:
                raise BillingError("Each payment must be greater than zero")
        if sum(amount for _, amount in payments) != bill["total_paise"]:
            raise BillingError("Payments must add up exactly to the bill total")
        if any(mode == "credit" for mode, _ in payments) and bill["party_id"] is None:
            raise BillingError("Credit sales need a customer")

        policy = shop.get_shop(conn)["oversell_policy"]
        needed = {}
        for line in lines:
            if line["tracking"] == "serial":
                unit = conn.execute(
                    "SELECT status FROM stock_unit WHERE id = ?", (line["unit_id"],)
                ).fetchone()
                if unit is None or unit["status"] != "in_stock":
                    raise SerialUnavailable("A serial on this bill is no longer in stock")
            else:
                needed[line["item_id"]] = needed.get(line["item_id"], 0) + line["qty_milli"]
        for item_id, qty in needed.items():
            stock.check_available(conn, item_id, qty, policy)

        bill_no = _next_number(conn, "sale", "S")
        now = clock.now_iso()
        conn.execute(
            "UPDATE bill SET status = 'final', bill_no = ?, finalized_at = ? WHERE id = ?",
            (bill_no, now, bill_id),
        )
        for line in lines:
            stock._record(conn, line["item_id"], -line["qty_milli"], "sale", "bill", bill_id, line["unit_id"])
            if line["tracking"] == "serial":
                conn.execute("UPDATE stock_unit SET status = 'sold' WHERE id = ?", (line["unit_id"],))
                if line["warranty_months"]:
                    end = clock.add_months(today, line["warranty_months"])
                    conn.execute(
                        "INSERT INTO warranty(unit_id, bill_id, start_date, end_date) VALUES (?,?,?,?)",
                        (line["unit_id"], bill_id, today.isoformat(), end.isoformat()),
                    )
        for mode, amount in payments:
            conn.execute(
                "INSERT INTO payment(bill_id, mode, amount_paise, created_at) VALUES (?,?,?,?)",
                (bill_id, mode, amount, now),
            )
        audit.log(conn, "finalize", "bill", bill_id, bill_no)
    return bill_no
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_billing_lines.py tests/test_billing_finalize.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: finalize sale bills atomically with payments, stock and warranty" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Billing — sale returns

**Files:**
- Modify: `retail/services/billing.py` (append `create_return`)
- Create: `tests/test_billing_returns.py`

**Interfaces:**
- Consumes: Task 7–8 functions, `stock._record`.
- Produces: `billing.create_return(conn, original_bill_id, returns, *, refund_mode="cash") -> int` — `returns` is `list[tuple[int, int]]` of `(original_line_id, qty_milli)`; creates and immediately finalizes a `sale_return` bill numbered `R000001`…, restocks items (serial units go back to `in_stock` and their warranty row is deleted), records one refund payment for the return total (`credit` refund reduces the customer's udhaar balance), and returns the return bill's id. Never modifies the original bill.

- [ ] **Step 1: Write the failing tests**

`tests/test_billing_returns.py`:
```python
import pytest

from retail.services import billing, items, parties, stock
from retail.services.billing import BillingError


def sold_soaps(conn, qty=3000, party_id=None):
    soap = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(conn, soap, 10_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    line_id = billing.add_line(conn, bill_id, soap, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, [("cash", total)])
    return soap, bill_id, line_id


def test_full_return_restocks_and_refunds(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    assert stock.on_hand(shop_conn, soap) == 7_000
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 3000)])
    r = billing.get_bill(shop_conn, ret)["bill"]
    assert r["kind"] == "sale_return" and r["status"] == "final" and r["bill_no"] == "R000001"
    assert r["ref_bill_id"] == bill_id and r["total_paise"] == 35400
    assert stock.on_hand(shop_conn, soap) == 10_000
    refund = shop_conn.execute("SELECT mode, amount_paise FROM payment WHERE bill_id = ?", (ret,)).fetchone()
    assert (refund["mode"], refund["amount_paise"]) == ("cash", 35400)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"] == 35400  # original untouched


def test_partial_return_refunds_proportional_gst(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=2000)
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    r = billing.get_bill(shop_conn, ret)["bill"]
    assert (r["taxable_paise"], r["cgst_paise"], r["sgst_paise"], r["total_paise"]) == (10000, 900, 900, 11800)


def test_cannot_return_more_than_sold_even_across_returns(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=3000)
    billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 2000)])
    last = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert billing.get_bill(shop_conn, last)["bill"]["total_paise"] == 11800  # no rounding drift
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert stock.on_hand(shop_conn, soap) == 10_000


def test_failed_return_leaves_no_trace(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=1000)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 5000)])
    assert shop_conn.execute("SELECT COUNT(*) FROM bill WHERE kind='sale_return'").fetchone()[0] == 0
    assert stock.on_hand(shop_conn, soap) == 9_000


@pytest.mark.parametrize("returns", [[], [(99999, 1000)]])
def test_return_input_validation(shop_conn, returns):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, returns)


def test_same_line_listed_twice_in_one_return_is_rejected(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn, qty=2000)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, bill_id, [(line_id, 1000), (line_id, 1000)])


def test_zero_or_negative_return_quantity_is_rejected(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    for qty in (0, -1000):
        with pytest.raises(BillingError):
            billing.create_return(shop_conn, bill_id, [(line_id, qty)])


def test_only_final_sale_bills_can_be_returned(shop_conn):
    soap, bill_id, line_id = sold_soaps(shop_conn)
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    ret_line = billing.get_bill(shop_conn, ret)["lines"][0]["id"]
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, ret, [(ret_line, 1000)])
    held = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, held, soap, 1000)
    held_line = billing.get_bill(shop_conn, held)["lines"][0]["id"]
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, held, [(held_line, 1000)])


def test_credit_refund_reduces_udhaar_and_needs_a_customer(shop_conn):
    ravi = parties.create_party(shop_conn, name="Ravi")
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=11800)
    stock.record(shop_conn, soap, 10_000, "opening")
    bill_id = billing.start_bill(shop_conn, party_id=ravi)
    line_id = billing.add_line(shop_conn, bill_id, soap, 2000)
    billing.finalize(shop_conn, bill_id, [("credit", 23600)])
    assert parties.balance(shop_conn, ravi) == 23600
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)], refund_mode="credit")
    assert parties.balance(shop_conn, ravi) == 11800
    anon, anon_bill, anon_line = sold_soaps(shop_conn)
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, anon_bill, [(anon_line, 1000)], refund_mode="credit")
    with pytest.raises(BillingError):
        billing.create_return(shop_conn, anon_bill, [(anon_line, 1000)], refund_mode="emi")


def test_serial_return_restocks_unit_clears_warranty_and_allows_resale(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial",
                              warranty_months=12)
    unit = stock.add_unit(shop_conn, phone, serial="IMEI123")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, phone, 1000, serial="IMEI123")
    billing.finalize(shop_conn, bill_id, [("cash", 1000000)])
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert stock.on_hand(shop_conn, phone) == 1000
    assert shop_conn.execute("SELECT status FROM stock_unit WHERE id=?", (unit,)).fetchone()[0] == "in_stock"
    assert shop_conn.execute("SELECT COUNT(*) FROM warranty WHERE unit_id=?", (unit,)).fetchone()[0] == 0
    again = billing.start_bill(shop_conn)
    assert billing.add_line(shop_conn, again, phone, 1000, serial="IMEI123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_billing_returns.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'create_return'`.

- [ ] **Step 3: Write the implementation**

Append to `retail/services/billing.py`:
```python
@writes
def create_return(conn, original_bill_id, returns, *, refund_mode="cash"):
    """returns: [(original_line_id, qty_milli), ...]. Creates and finalizes a return bill."""
    if refund_mode not in REFUND_MODES:
        raise BillingError(f"refund_mode must be one of {REFUND_MODES}")
    if not returns:
        raise BillingError("Nothing to return")
    line_ids = [line_id for line_id, _ in returns]
    if len(set(line_ids)) != len(line_ids):
        raise BillingError("The same line was listed twice")
    with transaction(conn):
        orig = _bill(conn, original_bill_id, status="final")
        if orig["kind"] != "sale":
            raise BillingError("Only sale bills can be returned")
        if refund_mode == "credit" and orig["party_id"] is None:
            raise BillingError("Credit refunds need a customer")
        now = clock.now_iso()
        return_id = conn.execute(
            """INSERT INTO bill(kind, status, party_id, ref_bill_id, gst_mode, created_at)
               VALUES ('sale_return','held',?,?,?,?)""",
            (orig["party_id"], original_bill_id, orig["gst_mode"], now),
        ).lastrowid
        for line_id, qty in returns:
            if qty <= 0:
                raise BillingError("Return quantity must be greater than zero")
            ol = conn.execute(
                "SELECT * FROM bill_line WHERE id = ? AND bill_id = ?", (line_id, original_bill_id)
            ).fetchone()
            if ol is None:
                raise BillingError("That line is not on the original bill")
            done = conn.execute(
                """SELECT COALESCE(SUM(l.qty_milli), 0) AS q, COALESCE(SUM(l.amount_paise), 0) AS a
                   FROM bill_line l JOIN bill b ON b.id = l.bill_id
                   WHERE l.ref_line_id = ? AND b.kind = 'sale_return' AND b.status = 'final'""",
                (line_id,),
            ).fetchone()
            remaining = ol["qty_milli"] - done["q"]
            if qty > remaining:
                raise BillingError("Cannot return more than was sold")
            if qty == remaining:
                amount = ol["amount_paise"] - done["a"]  # settle exactly, no rounding drift
            else:
                amount = (2 * ol["amount_paise"] * qty + ol["qty_milli"]) // (2 * ol["qty_milli"])
            conn.execute(
                """INSERT INTO bill_line(bill_id, item_id, unit_id, ref_line_id, qty_milli, rate_paise,
                       discount_paise, amount_paise, gst_rate_bp) VALUES (?,?,?,?,?,?,0,?,?)""",
                (return_id, ol["item_id"], ol["unit_id"], line_id, qty, ol["rate_paise"], amount,
                 ol["gst_rate_bp"]),
            )
        _retax(conn, return_id)
        total = conn.execute("SELECT total_paise FROM bill WHERE id = ?", (return_id,)).fetchone()[0]
        bill_no = _next_number(conn, "sale_return", "R")
        lines = conn.execute(
            """SELECT l.*, i.tracking FROM bill_line l JOIN item i ON i.id = l.item_id
               WHERE l.bill_id = ?""",
            (return_id,),
        ).fetchall()
        for line in lines:
            stock._record(conn, line["item_id"], line["qty_milli"], "sale_return", "bill", return_id,
                          line["unit_id"])
            if line["tracking"] == "serial":
                conn.execute("UPDATE stock_unit SET status = 'in_stock' WHERE id = ?", (line["unit_id"],))
                conn.execute("DELETE FROM warranty WHERE unit_id = ?", (line["unit_id"],))
        if total > 0:
            conn.execute(
                "INSERT INTO payment(bill_id, mode, amount_paise, created_at) VALUES (?,?,?,?)",
                (return_id, refund_mode, total, now),
            )
        conn.execute(
            "UPDATE bill SET status = 'final', bill_no = ?, finalized_at = ? WHERE id = ?",
            (bill_no, now, return_id),
        )
        audit.log(conn, "return", "bill", return_id, f"{bill_no} against bill {original_bill_id}")
    return return_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_billing_lines.py tests/test_billing_finalize.py tests/test_billing_returns.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add sale returns with restock, refunds and over-return protection" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Purchases

**Files:**
- Create: `retail/services/purchases.py`, `tests/test_purchases.py`

**Interfaces:**
- Consumes: `stock._record`, `stock._add_unit`, `stock.find_batch`, `stock.DuplicateSerial`, `money.line_amount`, `clock.today`.
- Produces: `purchases.PurchaseError(ValueError)`; `purchases.PurchaseLine` (frozen dataclass: `item_id: int`, `qty_milli: int`, `cost_paise: int`, `serials: tuple[str, ...] = ()`, `batch_no: str | None = None`, `expiry: str | None = None`); `purchases.create_purchase(conn, *, party_id, invoice_no, lines, date_iso=None) -> int`. Rules: `serial` items need exactly one serial per unit (`qty_milli == 1000 * len(serials)`), `batch` items need `batch_no` (an existing batch with the same number is topped up), only `weighed` items may have fractional quantity; last cost updates `item.buy_price_paise`; everything is atomic.

- [ ] **Step 1: Write the failing tests**

`tests/test_purchases.py`:
```python
import pytest

from retail.services import items, parties, purchases, stock
from retail.services.purchases import PurchaseError, PurchaseLine


def supplier(conn):
    return parties.create_party(conn, name="Wholesale Co", type="supplier")


def test_simple_purchase_adds_stock_and_updates_cost(shop_conn):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    pid = purchases.create_purchase(shop_conn, party_id=supplier(shop_conn), invoice_no="INV-1",
                                    lines=[PurchaseLine(tea, 10_000, 350)])
    assert stock.on_hand(shop_conn, tea) == 10_000
    assert shop_conn.execute("SELECT buy_price_paise FROM item WHERE id=?", (tea,)).fetchone()[0] == 350
    assert shop_conn.execute("SELECT total_paise FROM purchase WHERE id=?", (pid,)).fetchone()[0] == 3500


def test_weighed_purchase_allows_fractions(shop_conn):
    rice = items.create_item(shop_conn, name="Rice", sell_price_paise=6000, tracking="weighed")
    pid = purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                    lines=[PurchaseLine(rice, 25_500, 4000)])
    assert stock.on_hand(shop_conn, rice) == 25_500
    assert shop_conn.execute("SELECT total_paise FROM purchase WHERE id=?", (pid,)).fetchone()[0] == 102000


def test_fractional_quantity_rejected_for_counted_items(shop_conn):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(tea, 1_500, 350)])
    assert stock.on_hand(shop_conn, tea) == 0


def test_serial_purchase_creates_one_unit_per_serial(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    purchases.create_purchase(shop_conn, party_id=None, invoice_no="P1",
                              lines=[PurchaseLine(phone, 2000, 800000, serials=("A1", "b2"))])
    assert stock.on_hand(shop_conn, phone) == 2000
    assert stock.find_serial(shop_conn, phone, "B2")["status"] == "in_stock"


@pytest.mark.parametrize("serials,qty", [((), 1000), (("A1",), 2000), (("A1", "A2"), 1000)])
def test_serial_purchase_count_must_match(shop_conn, serials, qty):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(phone, qty, 1, serials=serials)])


def test_duplicate_serial_rolls_back_the_whole_purchase(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                              lines=[PurchaseLine(phone, 1000, 1, serials=("A1",))])
    with pytest.raises(stock.DuplicateSerial):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None, lines=[
            PurchaseLine(tea, 5_000, 100), PurchaseLine(phone, 1000, 1, serials=("a1",))])
    assert stock.on_hand(shop_conn, tea) == 0
    assert shop_conn.execute("SELECT COUNT(*) FROM purchase").fetchone()[0] == 1


def test_batch_purchase_requires_batch_and_tops_up_existing_batch(shop_conn):
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=100, tracking="batch")
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(milk, 5_000, 50)])
    for _ in range(2):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None, lines=[
            PurchaseLine(milk, 5_000, 50, batch_no="B1", expiry="2026-12-01")])
    unit = stock.find_batch(shop_conn, milk, "B1")
    assert stock.unit_on_hand(shop_conn, unit) == 10_000
    assert shop_conn.execute("SELECT COUNT(*) FROM stock_unit WHERE item_id=?", (milk,)).fetchone()[0] == 1


def test_purchase_needs_lines_and_positive_quantities(shop_conn):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None, lines=[])
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(tea, 0, 100)])
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(tea, 1000, -1)])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_purchases.py -v`
Expected: FAIL — `ImportError: cannot import name 'purchases'`.

- [ ] **Step 3: Write the implementation**

`retail/services/purchases.py`:
```python
from dataclasses import dataclass

from retail import clock, money
from retail.db import transaction
from retail.guard import writes
from retail.services import audit, stock


class PurchaseError(ValueError):
    pass


@dataclass(frozen=True)
class PurchaseLine:
    item_id: int
    qty_milli: int
    cost_paise: int
    serials: tuple = ()
    batch_no: str | None = None
    expiry: str | None = None


def _receive(conn, purchase_id, line):
    item = conn.execute("SELECT * FROM item WHERE id = ? AND active = 1", (line.item_id,)).fetchone()
    if item is None:
        raise PurchaseError("No such item")
    if line.qty_milli <= 0:
        raise PurchaseError("Quantity must be greater than zero")
    if line.cost_paise < 0:
        raise PurchaseError("Cost cannot be negative")
    tracking = item["tracking"]
    if tracking != "weighed" and line.qty_milli % 1000:
        raise PurchaseError("Only weighed items can be bought in fractions")
    if tracking == "serial":
        if not line.serials or line.qty_milli != 1000 * len(line.serials):
            raise PurchaseError("Serial items need exactly one serial number per unit")
        for serial in line.serials:
            unit_id = stock._add_unit(conn, line.item_id, serial=serial)
            stock._record(conn, line.item_id, 1000, "purchase", "purchase", purchase_id, unit_id)
    elif tracking == "batch":
        if not line.batch_no:
            raise PurchaseError("Batch items need a batch number")
        unit_id = stock.find_batch(conn, line.item_id, line.batch_no)
        if unit_id is None:
            unit_id = stock._add_unit(conn, line.item_id, batch_no=line.batch_no, expiry=line.expiry)
        stock._record(conn, line.item_id, line.qty_milli, "purchase", "purchase", purchase_id, unit_id)
    else:
        stock._record(conn, line.item_id, line.qty_milli, "purchase", "purchase", purchase_id)
    conn.execute(
        "INSERT INTO purchase_line(purchase_id, item_id, qty_milli, cost_paise) VALUES (?,?,?,?)",
        (purchase_id, line.item_id, line.qty_milli, line.cost_paise),
    )
    conn.execute("UPDATE item SET buy_price_paise = ? WHERE id = ?", (line.cost_paise, line.item_id))
    return money.line_amount(line.cost_paise, line.qty_milli)


@writes
def create_purchase(conn, *, party_id, invoice_no, lines, date_iso=None):
    if not lines:
        raise PurchaseError("A purchase needs at least one line")
    with transaction(conn):
        purchase_id = conn.execute(
            "INSERT INTO purchase(party_id, invoice_no, purchase_date) VALUES (?,?,?)",
            (party_id, invoice_no, date_iso or clock.today().isoformat()),
        ).lastrowid
        total = sum(_receive(conn, purchase_id, line) for line in lines)
        conn.execute("UPDATE purchase SET total_paise = ? WHERE id = ?", (total, purchase_id))
        audit.log(conn, "create", "purchase", purchase_id, invoice_no or "")
    return purchase_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_purchases.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add supplier purchases feeding the stock ledger" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Segment templates

**Files:**
- Create: `retail/segments/__init__.py`, `retail/segments/grocery.json`, `retail/segments/electronics.json`, `tests/test_segments.py`

**Interfaces:**
- Consumes: `shop.get_shop`, `db.transaction`, `guard.writes`, `audit.log`.
- Produces: `segments.UnknownTemplate(ValueError)`; `segments.list_templates() -> list[str]`; `segments.load(name) -> dict`; `segments.apply_template(conn, name) -> dict` (sets `shop.template` and stores the template JSON in `shop.features`); `segments.template_settings(conn) -> dict`; `segments.feature_enabled(conn, key) -> bool`; `segments.set_feature(conn, key, enabled) -> None` (a shop can enable features from either template). Template keys: `name`, `label`, `default_tracking`, `units`, `bill_layout`, `gst_slabs_bp`, `features` (booleans: `weighed`, `batch`, `serial`, `warranty`, `emi`, `udhaar`, `low_stock_alerts`).

- [ ] **Step 1: Write the failing tests**

`tests/test_segments.py`:
```python
import pytest

from retail import guard, segments
from retail.services import items, shop

REQUIRED = {"name", "label", "default_tracking", "units", "bill_layout", "gst_slabs_bp", "features"}
FEATURES = {"weighed", "batch", "serial", "warranty", "emi", "udhaar", "low_stock_alerts"}


def test_shipped_templates():
    assert segments.list_templates() == ["electronics", "grocery"]


@pytest.mark.parametrize("name", ["grocery", "electronics"])
def test_template_files_are_well_formed(name):
    t = segments.load(name)
    assert REQUIRED <= set(t) and t["name"] == name
    assert t["default_tracking"] in items.TRACKING
    assert set(t["features"]) == FEATURES and all(isinstance(v, bool) for v in t["features"].values())
    assert t["gst_slabs_bp"] == sorted(t["gst_slabs_bp"]) and 0 in t["gst_slabs_bp"]
    assert t["bill_layout"] in {"thermal_58", "thermal_80", "a4"}


def test_template_intent():
    g, e = segments.load("grocery"), segments.load("electronics")
    assert g["features"]["weighed"] and g["features"]["udhaar"] and not g["features"]["serial"]
    assert e["features"]["serial"] and e["features"]["warranty"] and e["features"]["emi"]
    assert e["default_tracking"] == "serial" and e["bill_layout"] == "a4"


def test_unknown_template_raises():
    with pytest.raises(segments.UnknownTemplate):
        segments.load("pharmacy")
    with pytest.raises(segments.UnknownTemplate):
        segments.load("../secret")


def test_apply_template_and_read_back(shop_conn):
    segments.apply_template(shop_conn, "electronics")
    assert shop.get_shop(shop_conn)["template"] == "electronics"
    assert segments.template_settings(shop_conn)["default_tracking"] == "serial"
    assert segments.feature_enabled(shop_conn, "warranty") is True
    assert segments.feature_enabled(shop_conn, "weighed") is False


def test_shop_can_mix_features_from_both_segments(shop_conn):
    segments.apply_template(shop_conn, "grocery")
    assert segments.feature_enabled(shop_conn, "serial") is False
    segments.set_feature(shop_conn, "serial", True)
    segments.set_feature(shop_conn, "warranty", True)
    assert segments.feature_enabled(shop_conn, "serial") and segments.feature_enabled(shop_conn, "weighed")
    with pytest.raises(segments.UnknownTemplate):
        segments.set_feature(shop_conn, "teleport", True)


def test_feature_enabled_is_false_before_any_template_applied(shop_conn):
    assert segments.feature_enabled(shop_conn, "serial") is False
    assert segments.template_settings(shop_conn) == {}


def test_apply_template_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        segments.apply_template(shop_conn, "grocery")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_segments.py -v`
Expected: FAIL — `ImportError: cannot import name 'segments'`.

- [ ] **Step 3: Write the implementation**

`retail/segments/grocery.json`:
```json
{
  "name": "grocery",
  "label": "Grocery / Kirana / General Store",
  "default_tracking": "none",
  "units": ["pcs", "kg", "g", "litre", "ml", "packet"],
  "bill_layout": "thermal_80",
  "gst_slabs_bp": [0, 500, 1800, 4000],
  "features": {
    "weighed": true,
    "batch": false,
    "serial": false,
    "warranty": false,
    "emi": false,
    "udhaar": true,
    "low_stock_alerts": true
  }
}
```

`retail/segments/electronics.json`:
```json
{
  "name": "electronics",
  "label": "Electronics / Mobile / Appliances",
  "default_tracking": "serial",
  "units": ["pcs"],
  "bill_layout": "a4",
  "gst_slabs_bp": [0, 500, 1800, 4000],
  "features": {
    "weighed": false,
    "batch": false,
    "serial": true,
    "warranty": true,
    "emi": true,
    "udhaar": false,
    "low_stock_alerts": false
  }
}
```

`retail/segments/__init__.py`:
```python
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
    settings = template_settings(conn)
    known = {k for name in list_templates() for k in load(name)["features"]}
    if key not in known:
        raise UnknownTemplate(f"Unknown feature {key!r}")
    settings.setdefault("features", {})[key] = bool(enabled)
    with transaction(conn):
        conn.execute("UPDATE shop SET features = ? WHERE id = 1", (json.dumps(settings),))
        audit.log(conn, "set_feature", "shop", 1, f"{key}={bool(enabled)}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_segments.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add grocery and electronics segment templates with feature toggles" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Backup, restore and `open_shop`

**Files:**
- Create: `retail/services/backup.py`, `tests/test_backup.py`
- Modify: `retail/db.py` (add `latest_version`, `open_shop`)

**Interfaces:**
- Consumes: `db.connect`, `db.migrate`, `db.schema_version`.
- Produces: `backup.BackupError`; `backup.BackupResult` (dataclass: `path: Path`, `extra_error: str | None`); `backup.backup_now(conn, backup_dir, *, prefix="daily", keep=14, extra_dir=None) -> BackupResult` (uses SQLite's online backup API; prunes each prefix to `keep` newest, in both folders; a failing `extra_dir`, e.g. an unplugged USB drive, is reported in `extra_error` and never blocks the primary backup); `backup.list_backups(backup_dir) -> list[Path]` (newest first); `backup.daily_backup_due(backup_dir, today: date) -> bool`; `backup.validate_backup(path) -> int` (returns schema version, raises `BackupError` for corrupt/non-shop files); `backup.restore(backup_path, db_path, backup_dir, *, max_version=None) -> Path` (returns the `pre-restore` safety copy; caller must close its connection first); `db.latest_version(migrations_dir=MIGRATIONS_DIR) -> int`; `db.open_shop(db_path, backup_dir, *, migrations_dir=MIGRATIONS_DIR) -> Connection` (connects, and migrates after a `pre-migrate` backup when upgrading an existing database).

- [ ] **Step 1: Write the failing tests**

`tests/test_backup.py`:
```python
import os
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
    assert backup.validate_backup(safety)  # the pre-restore copy holds the "After" state


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
    with pytest.raises(backup.BackupError):
        backup.restore(tmp_path / "nope.db", db_path, bk)


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
    db.open_shop(db_path, bk, migrations_dir=d).close()  # nothing pending: no new backup
    assert len(list(bk.glob("pre-migrate-*"))) == 1


def test_latest_version_matches_shipped_migrations():
    assert db.latest_version() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_backup.py -v`
Expected: FAIL — `ImportError: cannot import name 'backup'` (and `db.open_shop` missing).

- [ ] **Step 3: Write the implementation**

`retail/services/backup.py`:
```python
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
```

Modify `retail/db.py` — add at the top `from retail.services import backup`, and append:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_backup.py -v`
Expected: all PASS. Then run the whole suite: `.venv/Scripts/python -m pytest -q` — expected all PASS (this also proves `db` still imports cleanly with `backup`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add backup, safe restore and migration-safe open_shop" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Offline licensing and the vendor key-issuer tool

**Files:**
- Create: `retail/license.py`, `tools/__init__.py`, `tools/license_issuer.py`, `retail/public_key.py` (generated in Step 4), `tests/test_license.py`

**Interfaces:**
- Consumes: `guard.set_read_only`.
- Produces: `license.b64e(bytes) -> str`, `license.b64d(str) -> bytes`; `license.machine_id_from_guid(guid: str) -> str` (`RTL-XXXX-XXXX-XXXX-XXXX`); `license.get_machine_id() -> str` (Windows registry `MachineGuid`); `license.LicenseState` (frozen dataclass: `status` in `active|expired|invalid`, `buyer`, `expires`, `plan`, `reason`, property `read_only`); `license.verify_key(key: str, machine_id: str, public_key: bytes, today: date) -> LicenseState` (never raises; the expiry day itself is still valid); `license.save_key(path, key)`, `license.load_key(path) -> str | None`; `license.apply_license(path, public_key, machine_id, today=None) -> LicenseState` (also sets the read-only guard). Key format: `base64url(payload_json).base64url(ed25519_signature)`, payload `{"machine","buyer","expires","plan"}`. Vendor tool: `tools.license_issuer.generate_keypair() -> (private: bytes, public: bytes)`, `tools.license_issuer.issue(private_key, *, machine, buyer, expires, plan="standard") -> str`, CLI `python -m tools.license_issuer gen-keys|issue`. `retail.public_key.PUBLIC_KEY: bytes` (32 bytes).

- [ ] **Step 1: Write the failing tests**

`tests/test_license.py`:
```python
import re
import sys
from datetime import date

import pytest

from retail import guard
from retail import license as lic
from tools import license_issuer as issuer

MACHINE = "RTL-AAAA-BBBB-CCCC-DDDD"
TODAY = date(2026, 9, 30)


@pytest.fixture
def keys():
    return issuer.generate_keypair()


def make_key(priv, *, machine=MACHINE, expires="2027-09-30", buyer="Sri Kirana", plan="standard"):
    return issuer.issue(priv, machine=machine, buyer=buyer, expires=expires, plan=plan)


def test_valid_key_is_active(keys):
    priv, pub = keys
    state = lic.verify_key(make_key(priv), MACHINE, pub, TODAY)
    assert state.status == "active" and not state.read_only
    assert (state.buyer, state.expires, state.plan) == ("Sri Kirana", "2027-09-30", "standard")


def test_last_day_is_valid_and_next_day_is_expired(keys):
    priv, pub = keys
    key = make_key(priv, expires="2027-09-30")
    assert lic.verify_key(key, MACHINE, pub, date(2027, 9, 30)).status == "active"
    expired = lic.verify_key(key, MACHINE, pub, date(2027, 10, 1))
    assert expired.status == "expired" and expired.read_only and expired.buyer == "Sri Kirana"


def test_key_for_another_pc_is_invalid(keys):
    priv, pub = keys
    state = lic.verify_key(make_key(priv, machine="RTL-1111-2222-3333-4444"), MACHINE, pub, TODAY)
    assert state.status == "invalid" and state.read_only and state.reason


def test_tampered_payload_is_invalid(keys):
    priv, pub = keys
    payload, sig = make_key(priv).split(".")
    forged = lic.b64e(lic.b64d(payload).replace(b"2027", b"2099")) + "." + sig
    assert lic.verify_key(forged, MACHINE, pub, TODAY).status == "invalid"


def test_key_signed_by_someone_else_is_invalid(keys):
    priv, _ = keys
    _, other_pub = issuer.generate_keypair()
    assert lic.verify_key(make_key(priv), MACHINE, other_pub, TODAY).status == "invalid"


@pytest.mark.parametrize("garbage", ["", "abc", "a.b", ".....", "!!!.???", " ", "a.b.c", "తె.x"])
def test_garbage_never_raises(keys, garbage):
    _, pub = keys
    assert lic.verify_key(garbage, MACHINE, pub, TODAY).status == "invalid"


def test_key_with_bad_expiry_is_invalid(keys):
    priv, pub = keys
    payload = b'{"buyer":"x","expires":"never","machine":"%s","plan":"p"}' % MACHINE.encode()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    sig = Ed25519PrivateKey.from_private_bytes(priv).sign(payload)
    key = lic.b64e(payload) + "." + lic.b64e(sig)
    assert lic.verify_key(key, MACHINE, pub, TODAY).status == "invalid"


def test_machine_id_is_stable_and_well_formed():
    a = lic.machine_id_from_guid("  ABCD-1234  ")
    assert re.fullmatch(r"RTL-[0-9A-F]{4}(-[0-9A-F]{4}){3}", a)
    assert a == lic.machine_id_from_guid("abcd-1234")
    assert a != lic.machine_id_from_guid("abcd-1235")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry only")
def test_real_machine_id_on_windows():
    assert re.fullmatch(r"RTL-[0-9A-F]{4}(-[0-9A-F]{4}){3}", lic.get_machine_id())


def test_apply_license_sets_read_only_guard(keys, tmp_path):
    priv, pub = keys
    path = tmp_path / "license.key"
    assert lic.load_key(path) is None
    assert lic.apply_license(path, pub, MACHINE, TODAY).status == "invalid"   # no key yet
    assert guard.is_read_only() is True
    lic.save_key(path, make_key(priv))
    assert lic.apply_license(path, pub, MACHINE, TODAY).status == "active"
    assert guard.is_read_only() is False
    assert lic.apply_license(path, pub, MACHINE, date(2028, 1, 1)).status == "expired"
    assert guard.is_read_only() is True


def test_embedded_public_key_is_a_32_byte_ed25519_key():
    from retail import public_key
    assert len(public_key.PUBLIC_KEY) == 32


def test_cli_gen_keys_then_issue_verifies(tmp_path, monkeypatch, capsys):
    (tmp_path / "retail").mkdir()
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys"]) == 0
    assert issuer.main(["gen-keys", "--out", "keys"]) == 1          # never overwrite a private key
    capsys.readouterr()
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "Test", "--expires", "2027-01-01"]) == 0
    key = capsys.readouterr().out.strip()
    ns = {}
    exec((tmp_path / "retail" / "public_key.py").read_text(encoding="utf-8"), ns)
    assert lic.verify_key(key, MACHINE, ns["PUBLIC_KEY"], TODAY).status == "active"
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "T", "--expires", "01/01/2027"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_license.py -v`
Expected: FAIL — `ImportError` on `retail.license` / `tools`.

- [ ] **Step 3: Write the implementation**

`retail/license.py`:
```python
"""Offline license check. One key = one PC. The vendor signs {machine, buyer, expires, plan}
with a private Ed25519 key; the app verifies with the embedded public key. No server needed."""
import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from retail import clock, guard


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def machine_id_from_guid(guid: str) -> str:
    digest = hashlib.sha256(guid.strip().lower().encode("utf-8")).hexdigest().upper()
    return "RTL-" + "-".join(digest[i:i + 4] for i in range(0, 16, 4))


def read_machine_guid() -> str:
    import winreg  # Windows only, imported lazily

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        return winreg.QueryValueEx(key, "MachineGuid")[0]


def get_machine_id() -> str:
    return machine_id_from_guid(read_machine_guid())


@dataclass(frozen=True)
class LicenseState:
    status: str  # 'active' | 'expired' | 'invalid'
    buyer: str = ""
    expires: str = ""
    plan: str = ""
    reason: str = ""

    @property
    def read_only(self) -> bool:
        return self.status != "active"


def _invalid(reason: str) -> LicenseState:
    return LicenseState("invalid", reason=reason)


def verify_key(key: str, machine_id: str, public_key: bytes, today: date) -> LicenseState:
    try:
        payload_b64, signature_b64 = key.strip().split(".")
        payload = b64d(payload_b64)
        Ed25519PublicKey.from_public_bytes(public_key).verify(b64d(signature_b64), payload)
        data = json.loads(payload)
        expires = date.fromisoformat(data["expires"])
    except (ValueError, KeyError, TypeError, InvalidSignature):
        return _invalid("The license key is not valid")
    if data.get("machine") != machine_id:
        return _invalid("This key was issued for a different PC")
    state = "active" if today <= expires else "expired"
    return LicenseState(state, buyer=str(data.get("buyer", "")), expires=data["expires"],
                        plan=str(data.get("plan", "")))


def save_key(path, key: str) -> None:
    Path(path).write_text(key.strip(), encoding="utf-8")


def load_key(path) -> str | None:
    path = Path(path)
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def apply_license(path, public_key: bytes, machine_id: str, today: date | None = None) -> LicenseState:
    """Check the saved key and switch the app to read-only unless the license is active."""
    key = load_key(path)
    state = (
        LicenseState("invalid", reason="No license key has been entered")
        if not key
        else verify_key(key, machine_id, public_key, today or clock.today())
    )
    guard.set_read_only(state.read_only)
    return state
```

`tools/__init__.py`: empty file.

`tools/license_issuer.py`:
```python
"""VENDOR-ONLY tool. Never ship this or the private key with the installer.

  python -m tools.license_issuer gen-keys [--out keys]
  python -m tools.license_issuer issue --machine RTL-... --buyer "Name" --expires 2027-09-30 [--plan standard]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from retail.license import b64e


def generate_keypair():
    private = Ed25519PrivateKey.generate()
    raw_private = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    raw_public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return raw_private, raw_public


def issue(private_key, *, machine, buyer, expires, plan="standard"):
    payload = json.dumps(
        {"machine": machine, "buyer": buyer, "expires": expires, "plan": plan},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(payload)
    return f"{b64e(payload)}.{b64e(signature)}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="license_issuer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("gen-keys")
    gen.add_argument("--out", default="keys")
    iss = sub.add_parser("issue")
    iss.add_argument("--private", default="keys/private.key")
    iss.add_argument("--machine", required=True)
    iss.add_argument("--buyer", required=True)
    iss.add_argument("--expires", required=True, help="YYYY-MM-DD")
    iss.add_argument("--plan", default="standard")
    args = parser.parse_args(argv)

    if args.cmd == "gen-keys":
        target = Path(args.out) / "private.key"
        if target.exists():
            print(f"Refusing to overwrite {target}. Back it up, then delete it deliberately.", file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        private, public = generate_keypair()
        target.write_text(private.hex(), encoding="utf-8")
        Path("retail/public_key.py").write_text(
            '"""Generated by tools/license_issuer.py gen-keys. Safe to commit."""\n'
            f'PUBLIC_KEY = bytes.fromhex("{public.hex()}")\n',
            encoding="utf-8",
        )
        print(f"Private key written to {target} - back it up somewhere safe and NEVER commit or ship it.")
        return 0

    try:
        date.fromisoformat(args.expires)
    except ValueError:
        print("--expires must look like 2027-09-30", file=sys.stderr)
        return 2
    private = bytes.fromhex(Path(args.private).read_text(encoding="utf-8").strip())
    print(issue(private, machine=args.machine, buyer=args.buyer, expires=args.expires, plan=args.plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the real key pair, run tests**

Run (from the project root):
```bash
.venv/Scripts/python -m tools.license_issuer gen-keys
```
Expected: prints "Private key written to keys\private.key ..." and creates `retail/public_key.py`. **Back up `keys/private.key` outside this folder now** (it is git-ignored; losing it means you can never issue keys that existing installs accept).

Run: `.venv/Scripts/python -m pytest tests/test_license.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git status --short   # confirm keys/ is NOT listed
git commit -m "feat: add offline Ed25519 licensing with expiry, plan and vendor issuer tool" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: i18n catalogue (English, Hindi, Telugu)

**Files:**
- Create: `retail/i18n.py`, `retail/locales/en.json`, `retail/locales/hi.json`, `retail/locales/te.json`, `tests/test_i18n.py`

**Interfaces:**
- Produces: `i18n.LANGUAGES` (`{"en": "English", "hi": "हिन्दी", "te": "తెలుగు"}`), `i18n.DEFAULT_LANGUAGE`, `i18n.set_language(code) -> None`, `i18n.get_language() -> str`, `i18n.tr(key, **values) -> str`. Catalogue is keyed by stable ids (`bill.total`). Unknown key → `KeyError` (a programming error). Missing translation in Hindi/Telugu falls back to English at runtime, but the completeness test makes that impossible to ship.

- [ ] **Step 1: Write the failing tests**

`tests/test_i18n.py`:
```python
import json
import string
from pathlib import Path

import pytest

from retail import i18n

LOCALES = Path(i18n.__file__).parent / "locales"
SAME_AS_ENGLISH_ALLOWED = {"pay.upi"}


def load(code):
    return json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.fixture(autouse=True)
def _reset_language():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def test_languages_are_english_hindi_telugu():
    assert list(i18n.LANGUAGES) == ["en", "hi", "te"]
    assert i18n.LANGUAGES["hi"] == "हिन्दी" and i18n.LANGUAGES["te"] == "తెలుగు"
    assert i18n.DEFAULT_LANGUAGE == "en"


@pytest.mark.parametrize("code", ["hi", "te"])
def test_translation_is_complete_no_english_leaks(code):
    en, other = load("en"), load(code)
    assert set(other) == set(en), f"{code} keys differ: {set(en) ^ set(other)}"
    for key, text in other.items():
        assert text.strip(), f"{code}:{key} is empty"
        assert fields(text) == fields(en[key]), f"{code}:{key} placeholders differ from English"
        if key not in SAME_AS_ENGLISH_ALLOWED:
            assert text != en[key], f"{code}:{key} is still English"


def test_english_values_are_non_empty():
    assert all(v.strip() for v in load("en").values())


def test_tr_switches_language():
    assert i18n.tr("bill.total") == "Total"
    i18n.set_language("hi")
    assert i18n.get_language() == "hi" and i18n.tr("bill.total") == "कुल"
    i18n.set_language("te")
    assert i18n.tr("bill.total") == "మొత్తం"


def test_tr_formats_placeholders():
    assert i18n.tr("stock.low", count=3) == "3 items are low on stock"
    i18n.set_language("hi")
    assert "3" in i18n.tr("stock.low", count=3)


def test_unknown_language_and_key_raise():
    with pytest.raises(ValueError):
        i18n.set_language("fr")
    with pytest.raises(KeyError):
        i18n.tr("does.not.exist")
    assert i18n.get_language() == "en"


def test_missing_translation_falls_back_to_english(monkeypatch):
    i18n.set_language("hi")
    monkeypatch.setitem(i18n._catalogues, "hi", {})   # simulate an incomplete catalogue
    assert i18n.tr("bill.total") == "Total"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_i18n.py -v`
Expected: FAIL — `ImportError: cannot import name 'i18n'`.

- [ ] **Step 3: Write the implementation**

`retail/i18n.py`:
```python
"""Screen-language catalogue: English (default), Hindi, Telugu. Keys are stable ids.
tests/test_i18n.py fails if hi/te are missing a key, so English cannot leak into translated screens."""
import json
from pathlib import Path

LANGUAGES = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు"}
DEFAULT_LANGUAGE = "en"
_DIR = Path(__file__).parent / "locales"
_catalogues: dict[str, dict[str, str]] = {}
_current = DEFAULT_LANGUAGE


def _load(code: str) -> dict[str, str]:
    if code not in _catalogues:
        _catalogues[code] = json.loads((_DIR / f"{code}.json").read_text(encoding="utf-8"))
    return _catalogues[code]


def set_language(code: str) -> None:
    global _current
    if code not in LANGUAGES:
        raise ValueError(f"Unsupported language {code!r}")
    _current = code


def get_language() -> str:
    return _current


def tr(key: str, **values) -> str:
    text = _load(_current).get(key)
    if text is None:
        text = _load(DEFAULT_LANGUAGE)[key]  # KeyError here means the key is undefined everywhere
    return text.format(**values) if values else text
```

`retail/locales/en.json`:
```json
{
  "bill.new": "New bill",
  "bill.hold": "Hold bill",
  "bill.resume": "Resume bill",
  "bill.pay": "Pay",
  "bill.print": "Print",
  "bill.total": "Total",
  "bill.customer": "Customer",
  "bill.item": "Item",
  "bill.qty": "Quantity",
  "bill.rate": "Rate",
  "bill.discount": "Discount",
  "bill.round_off": "Round off",
  "pay.cash": "Cash",
  "pay.upi": "UPI",
  "pay.card": "Card",
  "pay.emi": "EMI",
  "pay.credit": "Credit (Udhaar)",
  "common.search": "Search",
  "common.save": "Save",
  "common.cancel": "Cancel",
  "stock.low": "{count} items are low on stock",
  "license.read_only": "License expired. Your data is safe and can be viewed and exported."
}
```

`retail/locales/hi.json`:
```json
{
  "bill.new": "नया बिल",
  "bill.hold": "बिल होल्ड करें",
  "bill.resume": "बिल फिर शुरू करें",
  "bill.pay": "भुगतान करें",
  "bill.print": "प्रिंट करें",
  "bill.total": "कुल",
  "bill.customer": "ग्राहक",
  "bill.item": "वस्तु",
  "bill.qty": "मात्रा",
  "bill.rate": "दर",
  "bill.discount": "छूट",
  "bill.round_off": "राउंड ऑफ",
  "pay.cash": "नकद",
  "pay.upi": "UPI",
  "pay.card": "कार्ड",
  "pay.emi": "ईएमआई",
  "pay.credit": "उधार",
  "common.search": "खोजें",
  "common.save": "सहेजें",
  "common.cancel": "रद्द करें",
  "stock.low": "{count} वस्तुओं का स्टॉक कम है",
  "license.read_only": "लाइसेंस समाप्त हो गया है। आपका डेटा सुरक्षित है और देखा व एक्सपोर्ट किया जा सकता है।"
}
```

`retail/locales/te.json`:
```json
{
  "bill.new": "కొత్త బిల్లు",
  "bill.hold": "బిల్లును హోల్డ్ చేయండి",
  "bill.resume": "బిల్లును తిరిగి ప్రారంభించండి",
  "bill.pay": "చెల్లించండి",
  "bill.print": "ప్రింట్ చేయండి",
  "bill.total": "మొత్తం",
  "bill.customer": "కస్టమర్",
  "bill.item": "వస్తువు",
  "bill.qty": "పరిమాణం",
  "bill.rate": "ధర",
  "bill.discount": "తగ్గింపు",
  "bill.round_off": "రౌండ్ ఆఫ్",
  "pay.cash": "నగదు",
  "pay.upi": "UPI",
  "pay.card": "కార్డ్",
  "pay.emi": "ఈఎంఐ",
  "pay.credit": "అప్పు",
  "common.search": "వెతకండి",
  "common.save": "సేవ్ చేయండి",
  "common.cancel": "రద్దు చేయండి",
  "stock.low": "{count} వస్తువుల స్టాక్ తక్కువగా ఉంది",
  "license.read_only": "లైసెన్స్ గడువు ముగిసింది. మీ డేటా సురక్షితంగా ఉంది; దాన్ని చూడవచ్చు మరియు ఎక్స్‌పోర్ట్ చేయవచ్చు."
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_i18n.py -v`
Expected: all PASS. (Translations are a first draft — have a native speaker review them before release, as Kuttu did with its Translation Review sheet.)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add English/Hindi/Telugu catalogue with completeness test" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Reports and CSV export

**Files:**
- Create: `retail/services/reports.py`, `tests/test_reports.py`

**Interfaces:**
- Consumes: final bills/lines/payments, `money.paise_to_str`.
- Produces (all read-only, so they keep working after license expiry): `reports.sales_register(conn, start: str, end: str) -> list[dict]` (keys `bill_no`, `bill_date`, `kind`, `party`, `gstin`, `taxable_paise`, `cgst_paise`, `sgst_paise`, `igst_paise`, `round_off_paise`, `total_paise`; return bills carry negative amounts; dates are inclusive `YYYY-MM-DD`); `reports.gst_summary(conn, start, end) -> list[dict]` (per GST rate, GST-mode bills only: `gst_rate_bp`, `taxable_paise`, `cgst_paise`, `sgst_paise`, `igst_paise`, returns netted off); `reports.daily_summary(conn, day) -> dict` (`sales_paise`, `returns_paise`, `net_paise`, `by_mode` mapping payment mode → net paise); `reports.SALES_COLUMNS`, `reports.write_csv(rows, path, columns) -> None` (UTF-8 with BOM so Excel opens it; `*_paise` columns are written as rupees with the suffix dropped from the header).

- [ ] **Step 1: Write the failing tests**

`tests/test_reports.py`:
```python
import csv

from retail import clock, guard
from retail.services import billing, items, parties, reports, shop, stock

TODAY = clock.today().isoformat()


def seed(conn):
    """Two sales (one cash, one udhaar to an out-of-state customer) and a partial return."""
    soap = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    oil = items.create_item(conn, name="Oil", sell_price_paise=10500, gst_rate_bp=500)
    stock.record(conn, soap, 50_000, "opening")
    stock.record(conn, oil, 50_000, "opening")
    pune = parties.create_party(conn, name="Pune Traders", gstin="27ABCDE1234F1Z5", state_code="27")
    a = billing.start_bill(conn)
    line_a = billing.add_line(conn, a, soap, 2000)
    billing.add_line(conn, a, oil, 1000)
    billing.finalize(conn, a, [("cash", 34100)])
    b = billing.start_bill(conn, party_id=pune)
    billing.add_line(conn, b, soap, 1000)
    billing.finalize(conn, b, [("credit", 11800)])
    billing.create_return(conn, a, [(line_a, 1000)])
    return a, b


def test_sales_register_lists_final_bills_with_returns_negative(shop_conn):
    seed(shop_conn)
    rows = reports.sales_register(shop_conn, TODAY, TODAY)
    assert [r["bill_no"] for r in rows] == ["S000001", "S000002", "R000001"]
    assert [r["total_paise"] for r in rows] == [34100, 11800, -11800]
    igst_row = rows[1]
    assert (igst_row["igst_paise"], igst_row["cgst_paise"], igst_row["party"], igst_row["gstin"]) == (
        1800, 0, "Pune Traders", "27ABCDE1234F1Z5")
    assert rows[2]["kind"] == "sale_return" and rows[2]["taxable_paise"] == -10000


def test_sales_register_excludes_held_and_cancelled_and_out_of_range(shop_conn):
    seed(shop_conn)
    held = billing.start_bill(shop_conn)
    cancelled = billing.start_bill(shop_conn)
    billing.cancel_held(shop_conn, cancelled)
    assert len(reports.sales_register(shop_conn, TODAY, TODAY)) == 3
    assert reports.sales_register(shop_conn, "2001-01-01", "2001-12-31") == []
    assert held


def test_gst_summary_groups_by_rate_and_nets_returns(shop_conn):
    seed(shop_conn)
    summary = {r["gst_rate_bp"]: r for r in reports.gst_summary(shop_conn, TODAY, TODAY)}
    soap18 = summary[1800]
    # soap sold 2 + 1 (igst) and 1 returned: taxable (2+1-1) * 100.00
    assert soap18["taxable_paise"] == 20000
    # sales: 2 soaps intra-state (cgst 1800, sgst 1800) + 1 soap inter-state (igst 1800);
    # return: 1 soap intra-state (cgst -900, sgst -900)
    assert (soap18["cgst_paise"], soap18["sgst_paise"], soap18["igst_paise"]) == (900, 900, 1800)
    assert summary[500]["taxable_paise"] == 10000


def test_gst_summary_ignores_estimate_bills(shop_conn):
    shop.setup_shop(shop_conn, name="Small", state_code="36", gst_enabled=False)
    it = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(shop_conn, it, 5_000, "opening")
    bill = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill, it, 1000)
    billing.finalize(shop_conn, bill, [("cash", 11800)])
    assert reports.gst_summary(shop_conn, TODAY, TODAY) == []
    assert len(reports.sales_register(shop_conn, TODAY, TODAY)) == 1


def test_daily_summary(shop_conn):
    seed(shop_conn)
    s = reports.daily_summary(shop_conn, TODAY)
    assert (s["sales_paise"], s["returns_paise"], s["net_paise"]) == (45900, 11800, 34100)
    assert s["by_mode"] == {"cash": 34100 - 11800, "credit": 11800}


def test_write_csv_converts_paise_and_opens_in_excel(shop_conn, tmp_path):
    seed(shop_conn)
    path = tmp_path / "register.csv"
    reports.write_csv(reports.sales_register(shop_conn, TODAY, TODAY), path, reports.SALES_COLUMNS)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert rows[0]["bill_no"] == "S000001" and rows[0]["total"] == "341.00"
    assert rows[2]["total"] == "-118.00" and "total_paise" not in rows[0]


def test_reports_still_work_when_license_is_expired(shop_conn, tmp_path):
    seed(shop_conn)
    guard.set_read_only(True)
    assert len(reports.sales_register(shop_conn, TODAY, TODAY)) == 3
    reports.write_csv(reports.sales_register(shop_conn, TODAY, TODAY), tmp_path / "x.csv", reports.SALES_COLUMNS)
    assert (tmp_path / "x.csv").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_reports.py -v`
Expected: FAIL — `ImportError: cannot import name 'reports'`.

- [ ] **Step 3: Write the implementation**

`retail/services/reports.py`:
```python
"""Read-only reports. Deliberately not guarded, so they keep working after license expiry."""
import csv

from retail import money

SALES_COLUMNS = ["bill_no", "bill_date", "kind", "party", "gstin", "taxable_paise", "cgst_paise",
                 "sgst_paise", "igst_paise", "round_off_paise", "total_paise"]

_SIGN = "(CASE WHEN b.kind = 'sale_return' THEN -1 ELSE 1 END)"


def sales_register(conn, start, end):
    rows = conn.execute(
        f"""SELECT b.bill_no, date(b.finalized_at) AS bill_date, b.kind,
                   COALESCE(p.name, '') AS party, COALESCE(p.gstin, '') AS gstin,
                   {_SIGN} * b.taxable_paise AS taxable_paise, {_SIGN} * b.cgst_paise AS cgst_paise,
                   {_SIGN} * b.sgst_paise AS sgst_paise, {_SIGN} * b.igst_paise AS igst_paise,
                   {_SIGN} * b.round_off_paise AS round_off_paise, {_SIGN} * b.total_paise AS total_paise
            FROM bill b LEFT JOIN party p ON p.id = b.party_id
            WHERE b.status = 'final' AND date(b.finalized_at) BETWEEN ? AND ?
            ORDER BY b.finalized_at, b.id""",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def gst_summary(conn, start, end):
    rows = conn.execute(
        f"""SELECT l.gst_rate_bp AS gst_rate_bp,
                   SUM({_SIGN} * l.taxable_paise) AS taxable_paise, SUM({_SIGN} * l.cgst_paise) AS cgst_paise,
                   SUM({_SIGN} * l.sgst_paise) AS sgst_paise, SUM({_SIGN} * l.igst_paise) AS igst_paise
            FROM bill_line l JOIN bill b ON b.id = l.bill_id
            WHERE b.status = 'final' AND b.gst_mode = 'gst' AND date(b.finalized_at) BETWEEN ? AND ?
            GROUP BY l.gst_rate_bp ORDER BY l.gst_rate_bp""",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def daily_summary(conn, day):
    totals = {
        r["kind"]: r["total"]
        for r in conn.execute(
            """SELECT kind, SUM(total_paise) AS total FROM bill
               WHERE status = 'final' AND date(finalized_at) = ? GROUP BY kind""",
            (day,),
        )
    }
    by_mode = {
        r["mode"]: r["net"]
        for r in conn.execute(
            f"""SELECT p.mode AS mode, SUM({_SIGN} * p.amount_paise) AS net
                FROM payment p JOIN bill b ON b.id = p.bill_id
                WHERE b.status = 'final' AND date(b.finalized_at) = ? GROUP BY p.mode""",
            (day,),
        )
    }
    sales, returns = totals.get("sale", 0), totals.get("sale_return", 0)
    return {"sales_paise": sales, "returns_paise": returns, "net_paise": sales - returns, "by_mode": by_mode}


def write_csv(rows, path, columns):
    """UTF-8 with BOM so Excel opens it correctly; *_paise columns are written as rupees."""
    headers = [c[: -len("_paise")] if c.endswith("_paise") else c for c in columns]
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                money.paise_to_str(row[c]) if c.endswith("_paise") else row[c] for c in columns
            ])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_reports.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add sales register, GST summary, daily summary and CSV export" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Staff and expenses

**Files:**
- Create: `retail/services/staff.py`, `tests/test_staff.py`

**Interfaces:**
- Consumes: tables `staff`, `expense` (already in schema), `db.transaction`, `guard.writes`, `audit.log`, `clock.today`.
- Produces: `staff.StaffError`; `staff.add_staff(conn, *, name, role="", monthly_salary_paise=0) -> int`; `staff.list_staff(conn, active_only=True) -> list[Row]`; `staff.add_expense(conn, *, spent_on, category, amount_paise, note="", staff_id=None) -> int` (categories `salary`, `rent`, `electricity`, `transport`, `other`); `staff.pay_salary(conn, staff_id, spent_on=None) -> int` (records a `salary` expense for the staff member's monthly salary; refuses a second salary in the same calendar month); `staff.expense_total(conn, start, end, category=None) -> int`.

- [ ] **Step 1: Write the failing tests**

`tests/test_staff.py`:
```python
import pytest

from retail import guard
from retail.services import staff
from retail.services.staff import StaffError


def test_add_and_list_staff(shop_conn):
    a = staff.add_staff(shop_conn, name="Anil", role="Cashier", monthly_salary_paise=1200000)
    b = staff.add_staff(shop_conn, name="Bala")
    shop_conn.execute("UPDATE staff SET active = 0 WHERE id = ?", (b,))
    assert [r["name"] for r in staff.list_staff(shop_conn)] == ["Anil"]
    assert {r["id"] for r in staff.list_staff(shop_conn, active_only=False)} == {a, b}


@pytest.mark.parametrize("kwargs", [{"name": " "}, {"name": "X", "monthly_salary_paise": -1}])
def test_staff_validation(shop_conn, kwargs):
    with pytest.raises(StaffError):
        staff.add_staff(shop_conn, **kwargs)


def test_expenses_and_totals(shop_conn):
    staff.add_expense(shop_conn, spent_on="2026-09-05", category="rent", amount_paise=1500000)
    staff.add_expense(shop_conn, spent_on="2026-09-10", category="electricity", amount_paise=250000, note="Aug bill")
    staff.add_expense(shop_conn, spent_on="2026-10-01", category="rent", amount_paise=1500000)
    assert staff.expense_total(shop_conn, "2026-09-01", "2026-09-30") == 1750000
    assert staff.expense_total(shop_conn, "2026-09-01", "2026-10-31", category="rent") == 3000000


@pytest.mark.parametrize("kwargs", [
    {"spent_on": "2026-09-05", "category": "party", "amount_paise": 100},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": 0},
    {"spent_on": "05/09/2026", "category": "rent", "amount_paise": 100},
])
def test_expense_validation(shop_conn, kwargs):
    with pytest.raises(StaffError):
        staff.add_expense(shop_conn, **kwargs)


def test_pay_salary_records_expense_once_per_month(shop_conn):
    a = staff.add_staff(shop_conn, name="Anil", monthly_salary_paise=1200000)
    staff.pay_salary(shop_conn, a, "2026-09-30")
    assert staff.expense_total(shop_conn, "2026-09-01", "2026-09-30", category="salary") == 1200000
    with pytest.raises(StaffError):
        staff.pay_salary(shop_conn, a, "2026-09-15")
    staff.pay_salary(shop_conn, a, "2026-10-31")
    assert staff.expense_total(shop_conn, "2026-01-01", "2026-12-31", category="salary") == 2400000


def test_pay_salary_needs_a_salary_and_a_real_person(shop_conn):
    unpaid = staff.add_staff(shop_conn, name="Intern")
    with pytest.raises(StaffError):
        staff.pay_salary(shop_conn, unpaid, "2026-09-30")
    with pytest.raises(StaffError):
        staff.pay_salary(shop_conn, 999, "2026-09-30")


def test_writes_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        staff.add_staff(shop_conn, name="X")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_staff.py -v`
Expected: FAIL — `ImportError: cannot import name 'staff'`.

- [ ] **Step 3: Write the implementation**

`retail/services/staff.py`:
```python
from datetime import date

from retail import clock
from retail.db import transaction
from retail.guard import writes
from retail.services import audit

CATEGORIES = ("salary", "rent", "electricity", "transport", "other")


class StaffError(ValueError):
    pass


def _check_date(text):
    try:
        date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise StaffError("Dates must look like 2026-09-30") from exc


@writes
def add_staff(conn, *, name, role="", monthly_salary_paise=0):
    name = (name or "").strip()
    if not name:
        raise StaffError("Staff name is required")
    if monthly_salary_paise < 0:
        raise StaffError("Salary cannot be negative")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO staff(name, role, monthly_salary_paise) VALUES (?,?,?)",
            (name, role, monthly_salary_paise),
        )
        audit.log(conn, "create", "staff", cur.lastrowid, name)
    return cur.lastrowid


def list_staff(conn, active_only=True):
    sql = "SELECT * FROM staff" + (" WHERE active = 1" if active_only else "") + " ORDER BY name"
    return conn.execute(sql).fetchall()


@writes
def add_expense(conn, *, spent_on, category, amount_paise, note="", staff_id=None):
    _check_date(spent_on)
    if category not in CATEGORIES:
        raise StaffError(f"category must be one of {CATEGORIES}")
    if amount_paise <= 0:
        raise StaffError("Amount must be greater than zero")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO expense(spent_on, category, amount_paise, note, staff_id) VALUES (?,?,?,?,?)",
            (spent_on, category, amount_paise, note, staff_id),
        )
        audit.log(conn, "create", "expense", cur.lastrowid, f"{category} {amount_paise}")
    return cur.lastrowid


@writes
def pay_salary(conn, staff_id, spent_on=None):
    spent_on = spent_on or clock.today().isoformat()
    _check_date(spent_on)
    with transaction(conn):
        person = conn.execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
        if person is None:
            raise StaffError("No such staff member")
        if person["monthly_salary_paise"] <= 0:
            raise StaffError("This staff member has no monthly salary set")
        month = spent_on[:7]
        if conn.execute(
            "SELECT 1 FROM expense WHERE staff_id = ? AND category = 'salary' AND substr(spent_on, 1, 7) = ?",
            (staff_id, month),
        ).fetchone():
            raise StaffError(f"Salary for {month} was already recorded")
        return add_expense(conn, spent_on=spent_on, category="salary",
                           amount_paise=person["monthly_salary_paise"], note=f"Salary {month}",
                           staff_id=staff_id)


def expense_total(conn, start, end, category=None):
    sql = "SELECT COALESCE(SUM(amount_paise), 0) FROM expense WHERE spent_on BETWEEN ? AND ?"
    params = [start, end]
    if category:
        sql += " AND category = ?"
        params.append(category)
    return conn.execute(sql, params).fetchone()[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_staff.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add staff, salary and expense tracking" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 17: End-to-end scenarios (grocery, electronics, expiry, restore)

**Files:**
- Create: `tests/test_scenarios.py`

**Interfaces:**
- Consumes: everything above. No new production code; this task is the cross-module proof that Plan 1 delivers the spec's success criteria, and any failure here is a bug in an earlier task to fix there.

- [ ] **Step 1: Write the scenario tests**

`tests/test_scenarios.py`:
```python
"""Cross-module scenarios that mirror the spec's success criteria."""
from datetime import date

import pytest

from retail import clock, db, guard, license as lic, segments
from retail.services import backup, billing, items, parties, purchases, reports, shop, stock
from retail.services.purchases import PurchaseLine
from tools import license_issuer as issuer

TODAY = clock.today().isoformat()


def test_grocery_day_weighed_sale_udhaar_and_gst_report(db_path, tmp_path):
    conn = db.open_shop(db_path, tmp_path / "bk")
    shop.setup_shop(conn, name="Sri Kirana", state_code="36", oversell_policy="warn")
    segments.apply_template(conn, "grocery")
    rice = items.create_item(conn, name="Sona Masoori Rice", sell_price_paise=6000, unit="kg",
                             tracking="weighed", gst_rate_bp=0, barcodes=["8900000000011"])
    biscuit = items.create_item(conn, name="Biscuits", sell_price_paise=1050, gst_rate_bp=1800,
                                barcodes=["8900000000028"], reorder_milli=5_000)
    wholesaler = parties.create_party(conn, name="City Wholesale", type="supplier")
    purchases.create_purchase(conn, party_id=wholesaler, invoice_no="W-77", lines=[
        PurchaseLine(rice, 50_000, 5200), PurchaseLine(biscuit, 6_000, 800)])

    ravi = parties.create_party(conn, name="Ravi", phone="9876543210", state_code="36")
    bill = billing.start_bill(conn, party_id=ravi)
    qty, text = items.parse_entry("0.75*8900000000011")           # scan with a weight typed first
    hit = items.resolve(conn, text)[0]
    billing.add_line(conn, bill, hit["id"], qty)
    qty, text = items.parse_entry("2*8900000000028")
    billing.add_line(conn, bill, items.resolve(conn, text)[0]["id"], qty)
    total = billing.get_bill(conn, bill)["bill"]["total_paise"]
    assert total == 6600                                          # 4500 + 2100, whole rupees, no round-off
    billing.finalize(conn, bill, [("cash", 2000), ("credit", total - 2000)])

    assert parties.balance(conn, ravi) == 4600
    parties.receive_payment(conn, ravi, 4600, mode="upi")
    assert parties.list_dues(conn) == []
    assert stock.on_hand(conn, rice) == 49_250
    assert [r["name"] for r in stock.low_stock(conn)] == ["Biscuits"]  # 4 left, reorder at 5

    summary = {r["gst_rate_bp"]: r for r in reports.gst_summary(conn, TODAY, TODAY)}
    assert summary[1800]["taxable_paise"] == 1780 and summary[1800]["cgst_paise"] == 160
    conn.close()


def test_electronics_serial_sale_warranty_and_return(db_path, tmp_path):
    conn = db.open_shop(db_path, tmp_path / "bk")
    shop.setup_shop(conn, name="Mobile World", state_code="36", oversell_policy="block")
    segments.apply_template(conn, "electronics")
    phone = items.create_item(conn, name="Galaxy M14", sell_price_paise=1299900, gst_rate_bp=1800,
                              tracking="serial", warranty_months=12, sku="M14-BLK")
    purchases.create_purchase(conn, party_id=None, invoice_no="D-1", lines=[
        PurchaseLine(phone, 2000, 1000000, serials=("356938035643809", "356938035643817"))])

    bill = billing.start_bill(conn)
    billing.add_line(conn, bill, phone, 1000, serial=" 356938035643809 ")
    total = billing.get_bill(conn, bill)["bill"]["total_paise"]
    billing.finalize(conn, bill, [("card", total - 500000), ("emi", 500000)], today=date(2026, 9, 30))
    assert stock.on_hand(conn, phone) == 1000
    warranty = conn.execute("SELECT end_date FROM warranty").fetchone()
    assert warranty["end_date"] == "2027-09-30"

    line = billing.get_bill(conn, bill)["lines"][0]["id"]
    billing.create_return(conn, bill, [(line, 1000)], refund_mode="card")
    assert stock.on_hand(conn, phone) == 2000
    assert conn.execute("SELECT COUNT(*) FROM warranty").fetchone()[0] == 0
    register = reports.sales_register(conn, TODAY, TODAY)
    assert [r["total_paise"] for r in register] == [total, -total]
    conn.close()


def test_expired_license_is_read_only_but_data_stays_visible_and_exportable(db_path, tmp_path):
    conn = db.open_shop(db_path, tmp_path / "bk")
    shop.setup_shop(conn, name="Shop", state_code="36")
    it = items.create_item(conn, name="Tea", sell_price_paise=500)
    stock.record(conn, it, 5_000, "opening")
    bill = billing.start_bill(conn)
    billing.add_line(conn, bill, it, 1000)
    billing.finalize(conn, bill, [("cash", 500)])

    priv, pub = issuer.generate_keypair()
    machine = "RTL-AAAA-BBBB-CCCC-DDDD"
    key_path = tmp_path / "license.key"
    lic.save_key(key_path, issuer.issue(priv, machine=machine, buyer="Shop", expires="2026-12-31"))
    assert lic.apply_license(key_path, pub, machine, date(2026, 12, 31)).status == "active"
    billing.start_bill(conn)                                        # still writable on the last day

    state = lic.apply_license(key_path, pub, machine, date(2027, 1, 1))
    assert state.status == "expired" and guard.is_read_only()
    with pytest.raises(guard.ReadOnlyError):
        billing.start_bill(conn)
    with pytest.raises(guard.ReadOnlyError):
        items.create_item(conn, name="New", sell_price_paise=1)
    with pytest.raises(guard.ReadOnlyError):
        stock.record(conn, it, 1000, "adjustment")

    assert stock.on_hand(conn, it) == 4_000                         # reads work
    rows = reports.sales_register(conn, TODAY, TODAY)
    reports.write_csv(rows, tmp_path / "export.csv", reports.SALES_COLUMNS)   # exports work
    assert (tmp_path / "export.csv").exists()
    assert backup.backup_now(conn, tmp_path / "bk").path.exists()   # backups still work
    conn.close()


def test_restore_undoes_a_bad_day(db_path, tmp_path):
    bk = tmp_path / "bk"
    conn = db.open_shop(db_path, bk)
    shop.setup_shop(conn, name="Shop", state_code="36")
    it = items.create_item(conn, name="Tea", sell_price_paise=500)
    stock.record(conn, it, 5_000, "opening")
    snapshot = backup.backup_now(conn, bk).path
    bill = billing.start_bill(conn)
    billing.add_line(conn, bill, it, 1000)
    billing.finalize(conn, bill, [("cash", 500)])
    conn.close()

    backup.restore(snapshot, db_path, bk, max_version=db.latest_version())
    conn = db.open_shop(db_path, bk)
    assert stock.on_hand(conn, it) == 5_000
    assert reports.sales_register(conn, TODAY, TODAY) == []
    assert billing.finalize(conn, _held_tea_bill(conn, it), [("cash", 500)]) == "S000001"  # numbering restored too
    conn.close()


def _held_tea_bill(conn, item_id):
    bill = billing.start_bill(conn)
    billing.add_line(conn, bill, item_id, 1000)
    return bill
```

- [ ] **Step 2: Run the scenarios**

Run: `.venv/Scripts/python -m pytest tests/test_scenarios.py -v`
Expected: all PASS. If a scenario fails, the bug is in the earlier task's module — fix it there (with a regression test in that task's test file), not by weakening the scenario.

- [ ] **Step 3: Run the whole suite and check coverage of the Review Focus list**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all PASS with no warnings about unclosed databases.

Confirm each Review Focus item has a passing pinning test:
1. Serial rules → `test_serial_is_normalised_and_must_exist_in_stock`, `test_same_serial_cannot_be_added_twice_to_one_bill`, `test_two_bills_racing_for_one_serial_second_fails_without_partial_writes`
2. Quantity rules → `test_non_weighed_item_rejects_fractional_zero_or_negative_quantity`
3. Over-return → `test_cannot_return_more_than_sold_even_across_returns`, `test_same_line_listed_twice_in_one_return_is_rejected`
4. Finalize guards → `test_finalize_rejects_bad_payments_and_changes_nothing`, `test_finalize_rejects_empty_bill`, `test_credit_sale_needs_a_customer_and_raises_balance`
5. Restore safety → `test_restore_of_corrupt_file_fails_and_leaves_data_untouched`, `test_restore_of_a_non_shop_database_fails`, `test_restore_of_a_backup_from_a_newer_app_version_fails`

Run: `.venv/Scripts/python -m pytest -q -k "serial or fractional or over_return or finalize or corrupt or newer" --co -q`
Expected: lists the tests named above.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: add end-to-end grocery, electronics, expiry and restore scenarios" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (spec coverage)

| Spec section | Covered by |
|---|---|
| §3 architecture, paise, ledger, immutable bills | Tasks 1, 2, 4, 8, 9 |
| §4 data model, tracking modes, migrations | Task 2 (schema), 3, 4, 10, 12 |
| §5 segment templates | Task 11 |
| §6 billing rules (input resolution, GST split, hold, oversell, estimate bills, per-tracking behaviour) | Tasks 3, 5, 7, 8 |
| §6 counter screen, print layouts (thermal/A4), WhatsApp | **Plan 2** (UI); template `bill_layout` value ready in Task 11 |
| §7 licensing, read-only after expiry, private key custody | Task 13, Task 17 |
| §7 updates (installer + auto-migrate after backup) | Task 12 (`open_shop`); installer packaging in **Plan 2** |
| §7 backup/restore/second location, exports | Tasks 12, 15 (CSV; `.xlsx` deferred, assumption 4) |
| §8 i18n en/hi/te + completeness test | Task 14; font bundling in **Plan 2** |
| §9 testing (services, migrations, i18n) | Every task; UI smoke tests in **Plan 2** |
| §10 grocery performance check | Task 3 (5,000-item search test); UI-level check in **Plan 2** |
| Staff / salary / rent / expenses (spec §4 tables) | Task 16 |

Placeholder scan: no TBD/TODO; every code step contains full code. Type consistency: `stock._record/_add_unit`, `billing._bill/_retax/_next_number`, `PurchaseLine`, `LineTax`, `LicenseState`, `BackupResult` are defined once and used with the same signatures downstream.

One thing worth knowing when reviewing: the plan's code was written but **not executed** (running it would have meant implementing before plan approval). The first `pytest` run in each task's Step 2/4 is where any typo surfaces.
