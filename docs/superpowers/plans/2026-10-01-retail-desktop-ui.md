# Retail App — Desktop UI Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the PySide6 Windows desktop application on top of the finished core engine: activation, onboarding, the keyboard-first counter, item/stock/party/report/staff/settings screens, bill printing (thermal 58/80 mm and A4), WhatsApp bills, English/Hindi/Telugu with correct fonts, backup/restore UI, and a Windows installer.

**Architecture:** A new `retail_ui` package sits above `retail/` (the engine from Plan 1, which stays Qt-free). Screens never contain business rules: they call `retail.services.*`, and every user-visible string goes through `retail.i18n.tr`. Counter behaviour that is not drawing (barcode → SKU → name → quick-add, quantity prefixes, tracking prompts) lives in a Qt-free controller so it can be tested without a window. One `AppSession` object owns the SQLite connection, the licence state and the signals that tell screens to refresh, retranslate or go read-only.

**Tech Stack:** Python 3.11+ (3.14 in use), PySide6 ≥ 6.10 (LGPL, dynamically linked), pytest + pytest-qt (offscreen platform), PyInstaller (one-folder build), Inno Setup (installer script; external tool).

**Spec:** `docs/superpowers/specs/2026-09-30-retail-app-design.md` (UI parts: §6 counter and printing, §7 licensing/updates/backup, §8 languages). The engine it builds on: `docs/superpowers/plans/2026-09-30-retail-core-engine.md` (already implemented on branch `core-engine`).

## Global Constraints

- Windows desktop app, one PC per shop, works fully offline (spec §2).
- Python, PySide6 (Qt, LGPL, dynamically linked) (spec §2).
- The UI layer has no business logic; all rules live in `retail/services/` (spec §3). Screens call services and render results.
- Money is integer paise and quantity integer milli-units everywhere; they are formatted only at the display edge (spec §3).
- Counter screen is keyboard-first: an always-focused input takes a barcode scan, an item code/name, or a quantity prefix (`3*` then scan); F-keys for discount, customer, hold bill and pay (spec §6).
- Input resolution order: barcode → exact SKU → name search → quick-add (three fields) when not found (spec §6).
- Per-tracking behaviour: `weighed` focuses quantity; `serial` prompts for the IMEI/serial; `batch` auto-selects the earliest expiry (spec §6).
- Print layouts are thermal 58 mm / 80 mm and A4, chosen per template (spec §6).
- Languages: English (default), Hindi, Telugu; fonts with Devanagari and Telugu scripts must be selected per language; no English text may leak into translated screens (spec §8).
- After licence expiry the app is read-only with full export; the owner is never locked out (spec §7).
- Automatic daily backup (on close); a second backup location is prompted at onboarding (spec §7).
- The installer keeps the shop's database, and the app displays its version (spec §7).
- The licence private key and `tools/` are never shipped in the installer (spec §7).
- Never push to GitHub or any remote; the owner pushes manually (project rule).
- Commit messages end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Assumptions added by this plan (not stated in the spec — confirm during review)

1. **Working product name is "Retail App"** (`retail_ui.APP_NAME`); change it in one place when you pick the real brand.
2. **Vendor contact for activation requests** reuses the phone/WhatsApp number from Kuttu's `kuttu_contact.py` (`+91 98660 79246`); email is left blank (the button is hidden when blank), exactly as Kuttu does.
3. **Hindi/Telugu fonts:** use the Windows system font "Nirmala UI" (ships with Windows 8+ and covers Devanagari and Telugu) instead of bundling font files. If it is missing the app falls back to Qt's default and logs a warning.
4. **State names in the onboarding dropdown stay in English** (proper nouns); all other text is translated. All Hindi and Telugu strings are a first draft that needs native-speaker review before release.
5. **Printing goes through the Windows print dialog / preview** (`QPrinter`); no raw ESC/POS driver. Thermal layouts are page sizes 58 mm and 80 mm wide.
6. **Bill lines are not merged:** scanning the same item twice creates two lines (the engine has no "change quantity" call). Delete a line and re-scan to correct it.
7. **A newly quick-added item has zero stock;** under the `block` oversell policy the first sale is refused until stock is received (under `warn`/`allow` it sells).
8. **No automatic update check** in this plan (spec lists it as optional); updates are a new installer that keeps the data folder. The About box shows the version.
9. **User data lives in `%LOCALAPPDATA%\RetailApp\`** (database, licence key, settings, default backup folder), not next to the program, so reinstalling or upgrading never touches it.
10. **Held bills are shared with the engine:** closing the app with a held bill keeps it; it reappears in the Held Bills list.

## Review Focus

Failure modes the spec implies but a happy-path build would miss, most likely first. Each has a pinning test in the task named.

1. A barcode scanner types fast and may send trailing spaces, repeat a scan, or send an unknown code; `0*item` or an empty Enter must do nothing harmful, and an unknown code must open quick-add pre-filled (Task 9, Task 11).
2. Switching language in the middle of a bill must keep the lines and totals, retranslate every visible label, and pick a font that can draw Hindi/Telugu (Task 5, Task 8, Task 11).
3. Closing the app (or it crashing) with a held bill must not lose it, closing must take the daily backup, and a failing backup folder must never block closing (Task 8, Task 11).
4. Restoring a backup while screens hold the old connection must close and reopen the database, refresh every screen, and leave the app usable on the old data if the restore fails (Task 5, Task 20).
5. After licence expiry every write control is disabled AND a service `ReadOnlyError` that slips through shows a translated message instead of English text or a crash (Task 4, Task 8, Task 11).

---

## File Structure

```
pyproject.toml                         (modify: PySide6, pytest-qt, pyinstaller, retail_ui package)
retail/services/                       (modify: items, shop, parties, stock, billing, purchases, staff, reports — small support APIs)
retail_ui/
  __init__.py            APP_NAME, version
  vendor.py              vendor contact + activation request URLs
  paths.py               AppPaths (%LOCALAPPDATA%\RetailApp)
  settings.py            UiSettings JSON (backup folders, auto-print)
  fmt.py                 rupees/qty/date display + parsing (Indian digit grouping)
  states.py              GST state codes
  validators.py          GSTIN / phone checks
  errors.py              exception → translated message, show_error
  session.py             AppSession (connection, licence, signals, backup/restore)
  bootstrap.py           boot flow (activation → onboarding) with injectable dialogs
  fonts.py               per-language font choice
  app.py                 QApplication entry point, --selftest
  main_window.py         MainWindow shell (nav, banner, language, close backup)
  widgets/base.py        Screen base class, RowsModel
  widgets/pickers.py     ItemPicker, small shared widgets
  dialogs/activation.py  ActivationDialog
  dialogs/onboarding.py  OnboardingWizard
  screens/registry.py    ordered list of screens
  screens/counter_logic.py     Qt-free CounterController
  screens/counter_dialogs.py   pick/qty/serial/quick-add/customer/discount/held/pay dialogs
  screens/counter.py     CounterScreen
  screens/bills.py       bill history, reprint, WhatsApp, returns
  screens/bills.py       bill history, reprint, PDF, WhatsApp, returns
  screens/items.py  stock.py  parties.py  reports.py  staff.py  settings.py  data.py
  printing/bill_view.py  BillView data (localised strings) built from a bill
  printing/render.py     QTextDocument layouts + QPrinter/PDF
  print_ui.py            preview / PDF / WhatsApp helpers used by screens
  whatsapp.py            phone normalising, message, wa.me URL
  __main__.py            python -m retail_ui
packaging/retail_app.spec  build.ps1  installer.iss
docs/manual-test-checklist.md
tools/locale_add.py                    (dev tool: merge new strings into en/hi/te)
tests/ui/                              (pytest-qt tests, offscreen)
tests/test_support_services.py  test_locale_add.py  test_packaging_files.py  test_docs.py
```

## Task overview

| # | Task | Delivers |
|---|---|---|
| 1 | Carry-over fixes | return-line components add up; licence scenario date-proof |
| 2 | Engine APIs for screens | list/update/detail services (items, shop, parties, stock, billing, purchases, staff) |
| 3 | UI scaffold | `retail_ui` package, paths, settings, formatting, validators, deps |
| 4 | Translated errors + locale tool | `errors.py`, `tools/locale_add.py`, shared strings |
| 5 | Session, fonts, boot flow | `AppSession`, per-language fonts, activation→onboarding bootstrap |
| 6 | Activation dialog | machine ID, request links, key entry |
| 7 | Onboarding wizard | language, shop, segment, billing, backup folders |
| 8 | Main window shell | nav, banner, language switch, close backup, `Screen`/`RowsModel` |
| 9 | Counter logic | Qt-free entry resolution and hold/resume/pay |
| 10 | Counter dialogs | pick, quantity, serial, quick-add, customer, discount, held, pay |
| 11 | Counter screen | keyboard-first billing screen |
| 12 | Print layouts | bill view, thermal 58/80 + A4, PDF |
| 13 | WhatsApp bills | wa.me links |
| 14 | Bills screen | history, reprint, PDF, WhatsApp, returns; counter printing |
| 15 | Items screen | add/edit/deactivate, low-stock highlight |
| 16 | Stock & purchases | audited adjustments, purchases with serial/batch |
| 17 | Parties screen | customers, suppliers, udhaar payments |
| 18 | Reports screen | register, GST, daily summary, CSV |
| 19 | Staff & expenses | staff, salary, expenses |
| 20 | Settings screen | shop, billing, features, printing, language |
| 21 | Backup/restore/licence screen | backups, restore, activation, About |
| 22 | App entry + smoke test | `main()`, `--selftest`, logging, whole-app test |
| 23 | Performance check | 5,000-item grocery ceilings |
| 24 | Packaging | PyInstaller spec, build script, Inno Setup installer |
| 25 | Manual checklist | per-segment release checklist |

---

### Task 1: Carry-over fixes from the engine review

Fixes the three items the final review parked: partial-return lines whose components don't add up to the line total, a wrong code comment, and a licence test that starts failing on 2027-01-01.

**Files:**
- Modify: `retail/services/billing.py` (add `_return_part`, use it in `create_return`, fix comment)
- Modify: `tests/test_scenarios.py` (licence dates)
- Test: `tests/test_billing_returns.py` (append)

**Interfaces:**
- Consumes: existing `billing.create_return`, `_RETURN_COMPONENTS`.
- Produces: `billing._return_part(ol, done, qty) -> dict` with keys `amount_paise, taxable_paise, cgst_paise, sgst_paise, igst_paise, total_paise`; invariant for every return line: `total == taxable + cgst + sgst + igst`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_billing_returns.py`:
```python
@pytest.mark.parametrize("qty_sold,qty_back,price,rate,inter_state", [
    (3000, 1000, 10000, 1800, False),
    (3000, 1000, 10000, 1800, True),
    (7000, 2000, 9999, 500, False),
    (7000, 3000, 12345, 4000, True),
    (9000, 4000, 1049, 1800, False),
])
def test_partial_return_line_components_always_add_up(shop_conn, qty_sold, qty_back, price, rate, inter_state):
    party_id = parties.create_party(shop_conn, name="Pune", state_code="27") if inter_state else None
    item = items.create_item(shop_conn, name="Shirt", sell_price_paise=price, gst_rate_bp=rate)
    stock.record(shop_conn, item, 20_000, "opening")
    bill_id = billing.start_bill(shop_conn, party_id=party_id)
    line_id = billing.add_line(shop_conn, bill_id, item, qty_sold)
    total = billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"]
    billing.finalize(shop_conn, bill_id, [("cash", total)])
    ret = billing.create_return(shop_conn, bill_id, [(line_id, qty_back)])
    detail = billing.get_bill(shop_conn, ret)
    for line in detail["lines"]:
        assert line["total_paise"] == (line["taxable_paise"] + line["cgst_paise"]
                                       + line["sgst_paise"] + line["igst_paise"])
    b = detail["bill"]
    assert b["total_paise"] == (b["taxable_paise"] + b["cgst_paise"] + b["sgst_paise"]
                                + b["igst_paise"] + b["round_off_paise"])
    if inter_state:
        assert b["cgst_paise"] == 0 and b["sgst_paise"] == 0
```
(Add `parties` to the imports at the top of the file if it is not already imported: `from retail.services import billing, items, parties, stock`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_billing_returns.py -k components_always_add_up -v`
Expected: FAIL — e.g. for 3 × ₹100 at 18% the return line has taxable 8475 + cgst 763 + sgst 763 = 10001 ≠ total 10000.

- [ ] **Step 3: Implement**

In `retail/services/billing.py`, add this function immediately above `create_return`:
```python
def _return_part(ol, done, qty):
    """Money components of returning `qty` from original line `ol`, given what earlier final
    returns already took (`done`). The quantity that completes the line takes the exact remainder
    (no drift). A partial quantity pro-rates the line TOTAL and TAX and derives taxable = total - tax,
    so total == taxable + cgst + sgst + igst always holds."""
    remaining = ol["qty_milli"] - done["qty_milli"]
    if qty == remaining:
        return {c: ol[c] - done[c] for c in _RETURN_COMPONENTS}

    def share(value):
        return (2 * value * qty + ol["qty_milli"]) // (2 * ol["qty_milli"])

    total = share(ol["total_paise"])
    tax = share(ol["cgst_paise"] + ol["sgst_paise"] + ol["igst_paise"])
    if ol["igst_paise"]:
        cgst, sgst, igst = 0, 0, tax
    else:
        cgst = min(share(ol["cgst_paise"]), tax)
        sgst, igst = tax - cgst, 0
    return {"amount_paise": share(ol["amount_paise"]), "taxable_paise": total - tax,
            "cgst_paise": cgst, "sgst_paise": sgst, "igst_paise": igst, "total_paise": total}
```
Then in `create_return` replace the block
```python
            if qty == remaining:
                # settle exactly, no rounding drift: original minus everything returned before
                part = {c: ol[c] - done[c] for c in _RETURN_COMPONENTS}
            else:
                part = {c: (2 * ol[c] * qty + ol["qty_milli"]) // (2 * ol["qty_milli"])
                        for c in _RETURN_COMPONENTS}
```
with
```python
            part = _return_part(ol, done, qty)
```
and replace the comment sentences
```python
        # and once everything is back they equal it exactly. A partial return's round-off stays
        # within +/-50 paise; the completing one can reach about +/-1 rupee (the original bill's
        # round-off plus the rounding already given on earlier returns).
```
with
```python
        # and once everything is back they equal it exactly. Any return after the first can carry a
        # round-off of up to about +/-1 rupee: it is the difference between the cumulative rounding
        # of all returns so far and of the earlier ones.
```

- [ ] **Step 4: Fix the licence-date time bomb**

In `tests/test_scenarios.py`, in `test_expired_license_is_read_only_but_data_stays_visible_and_exportable`, change `expires="2026-12-31"` to `expires="2099-12-31"`, `date(2026, 12, 31)` to `date(2099, 12, 31)` and `date(2027, 1, 1)` to `date(2100, 1, 1)` (three occurrences in that test).

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/Scripts/python -W error::ResourceWarning -m pytest -q`
Expected: all PASS (438 + the 5 new parametrised cases).

```bash
git add -A
git commit -m "fix: return line components add up; make licence scenario date-proof" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Engine APIs the screens need

The UI needs lists, edits and details the engine does not expose yet. All additions follow the engine rules: public writes are `@writes` + `with transaction(conn):`, money is validated as plain ints, no broad `IntegrityError` translation.

**Files:**
- Modify: `retail/services/items.py`, `shop.py`, `parties.py`, `stock.py`, `billing.py`, `purchases.py`, `staff.py`, `reports.py`
- Test: `tests/test_support_services.py` (create)

**Interfaces (all new):**
- `items.get_item(conn, item_id) -> Row | None`; `items.item_barcodes(conn, item_id) -> list[str]`; `items.list_items(conn, search="", *, include_inactive=False, limit=500) -> list[Row]` (item columns plus `on_hand_milli`); `items.update_item(conn, item_id, **fields) -> None` (fields among `name, sku, hsn, gst_rate_bp, unit, sell_price_paise, buy_price_paise, reorder_milli, warranty_months, tracking`; tracking cannot change once the item has stock history); `items.set_item_active(conn, item_id, active: bool) -> None`; `items.set_barcodes(conn, item_id, codes) -> None`.
- `shop.update_shop(conn, **fields) -> None` (fields among `name, gstin, address, state_code, bill_footer, gst_enabled, price_includes_gst, oversell_policy, language`; never touches `template`/`features`).
- `parties.list_parties(conn, *, kind=None, search="") -> list[dict]` (party columns + `balance_paise`; `kind` of `"customer"`/`"supplier"` also matches type `both`); `parties.update_party(conn, party_id, *, name, phone=None, gstin=None, state_code=None) -> None`.
- `stock.StockError(ValueError)`; `stock.adjust_stock(conn, item_id, qty_milli, reason) -> int` (audited; counted/weighed items only; may not make stock negative).
- `billing.get_bill_detail(conn, bill_id) -> {"bill","party","lines","payments","warranties"}` (lines carry `item_name, unit, tracking, serial, batch_no`); `billing.list_bills(conn, start, end, *, search="") -> list[Row]` (final bills; `id, bill_no, kind, finalized_at, bill_date, party, total_paise`); `billing.set_line_discount(conn, bill_id, line_id, discount_paise) -> None` (held bills only); `billing.returnable_lines(conn, bill_id) -> list[dict]` (`line_id, item_id, item_name, tracking, qty_milli, returned_milli, remaining_milli, total_paise`).
- `purchases.list_purchases(conn, limit=50) -> list[Row]` (`id, invoice_no, purchase_date, supplier, total_paise`).
- `staff.list_expenses(conn, start, end, category=None) -> list[Row]` (`expense` columns + `staff_name`).
- `reports.check_range` (public alias of the existing range check).

- [ ] **Step 1: Write the failing tests**

`tests/test_support_services.py`:
```python
import pytest

from retail import guard
from retail.services import billing, items, parties, purchases, reports, shop, staff, stock


def sell(conn, item_id, qty_milli, payments, **kwargs):
    bill_id = billing.start_bill(conn, **kwargs)
    line_id = billing.add_line(conn, bill_id, item_id, qty_milli)
    billing.finalize(conn, bill_id, payments)
    return bill_id, line_id


# ---- items ---------------------------------------------------------------

def test_list_items_searches_name_sku_and_barcode_and_reports_stock(shop_conn):
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=500, sku="S1", barcodes=["b111"])
    rice = items.create_item(shop_conn, name="Rice", sell_price_paise=600)
    stock.record(shop_conn, soap, 2000, "opening")
    assert [r["name"] for r in items.list_items(shop_conn)] == ["Rice", "Soap"]
    assert [r["name"] for r in items.list_items(shop_conn, "soa")] == ["Soap"]
    assert items.list_items(shop_conn, "S1")[0]["name"] == "Soap"
    assert items.list_items(shop_conn, "b111")[0]["on_hand_milli"] == 2000
    items.set_item_active(shop_conn, rice, False)
    assert [r["name"] for r in items.list_items(shop_conn)] == ["Soap"]
    assert len(items.list_items(shop_conn, include_inactive=True)) == 2


def test_update_item_changes_fields_and_audits(shop_conn):
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=500)
    items.update_item(shop_conn, soap, name=" Soap Big ", sell_price_paise=700, sku="  ")
    row = items.get_item(shop_conn, soap)
    assert (row["name"], row["sell_price_paise"], row["sku"]) == ("Soap Big", 700, None)
    assert shop_conn.execute("SELECT COUNT(*) FROM audit_log WHERE entity='item' AND action='update'").fetchone()[0] == 1


@pytest.mark.parametrize("fields", [
    {"colour": "red"}, {}, {"name": " "}, {"sell_price_paise": 1.5}, {"sell_price_paise": -1},
    {"gst_rate_bp": True}, {"tracking": "magic"},
])
def test_update_item_rejects_bad_input(shop_conn, fields):
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=500)
    with pytest.raises(items.ItemError):
        items.update_item(shop_conn, soap, **fields)
    assert items.get_item(shop_conn, soap)["name"] == "Soap"


def test_update_item_unknown_item_and_duplicate_sku(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1, sku="X")
    b = items.create_item(shop_conn, name="B", sell_price_paise=1)
    with pytest.raises(items.ItemError):
        items.update_item(shop_conn, 999, name="Z")
    with pytest.raises(items.ItemError):
        items.update_item(shop_conn, b, sku="X")
    assert a


def test_tracking_cannot_change_after_stock_history(shop_conn):
    fresh = items.create_item(shop_conn, name="Fresh", sell_price_paise=1)
    items.update_item(shop_conn, fresh, tracking="weighed")
    used = items.create_item(shop_conn, name="Used", sell_price_paise=1)
    stock.record(shop_conn, used, 1000, "opening")
    with pytest.raises(items.ItemError):
        items.update_item(shop_conn, used, tracking="serial")
    items.update_item(shop_conn, used, tracking="none")  # unchanged value is fine


def test_set_barcodes_replaces_dedupes_and_is_atomic(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1, barcodes=["111", "222"])
    b = items.create_item(shop_conn, name="B", sell_price_paise=1, barcodes=["999"])
    items.set_barcodes(shop_conn, a, ["333", " 333 ", "444", ""])
    assert items.item_barcodes(shop_conn, a) == ["333", "444"]
    with pytest.raises(items.ItemError):
        items.set_barcodes(shop_conn, a, ["555", "999"])
    assert items.item_barcodes(shop_conn, a) == ["333", "444"]
    with pytest.raises(items.ItemError):
        items.set_barcodes(shop_conn, a, "123")
    assert b


def test_item_writes_blocked_when_read_only(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1)
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        items.update_item(shop_conn, a, name="B")
    with pytest.raises(guard.ReadOnlyError):
        items.set_item_active(shop_conn, a, False)
    with pytest.raises(guard.ReadOnlyError):
        items.set_barcodes(shop_conn, a, ["1"])


# ---- shop ----------------------------------------------------------------

def test_update_shop_changes_only_named_fields(shop_conn):
    before = shop.get_shop(shop_conn)
    shop.update_shop(shop_conn, name="New Name", gst_enabled=False, language="te", oversell_policy="block")
    after = shop.get_shop(shop_conn)
    assert (after["name"], after["gst_enabled"], after["language"], after["oversell_policy"]) == ("New Name", 0, "te", "block")
    assert after["state_code"] == before["state_code"] and after["features"] == before["features"]


@pytest.mark.parametrize("fields", [
    {"template": "electronics"}, {}, {"name": ""}, {"state_code": "ABC"}, {"oversell_policy": "maybe"},
    {"language": "fr"}, {"gst_enabled": 1}, {"price_includes_gst": "yes"},
])
def test_update_shop_rejects_bad_input(shop_conn, fields):
    with pytest.raises(shop.ShopError):
        shop.update_shop(shop_conn, **fields)


def test_update_shop_before_setup_raises(conn):
    with pytest.raises(shop.ShopNotSetUp):
        shop.update_shop(conn, name="X")


# ---- parties -------------------------------------------------------------

def test_list_parties_filters_by_kind_and_search_with_balances(shop_conn):
    a = parties.create_party(shop_conn, name="Ravi", phone="9876500001", opening_balance_paise=500)
    parties.create_party(shop_conn, name="Wholesale", type="supplier")
    parties.create_party(shop_conn, name="Both Co", type="both")
    assert [p["name"] for p in parties.list_parties(shop_conn, kind="customer")] == ["Both Co", "Ravi"]
    assert [p["name"] for p in parties.list_parties(shop_conn, kind="supplier")] == ["Both Co", "Wholesale"]
    found = parties.list_parties(shop_conn, search="98765")
    assert [p["name"] for p in found] == ["Ravi"] and found[0]["balance_paise"] == 500
    with pytest.raises(parties.PartyError):
        parties.list_parties(shop_conn, kind="alien")
    assert a


def test_update_party(shop_conn):
    a = parties.create_party(shop_conn, name="Ravi")
    parties.update_party(shop_conn, a, name=" Ravi K ", phone="123", state_code="27")
    row = shop_conn.execute("SELECT * FROM party WHERE id=?", (a,)).fetchone()
    assert (row["name"], row["phone"], row["state_code"]) == ("Ravi K", "123", "27")
    with pytest.raises(parties.PartyError):
        parties.update_party(shop_conn, a, name=" ")
    with pytest.raises(parties.PartyError):
        parties.update_party(shop_conn, 999, name="X")


# ---- stock ---------------------------------------------------------------

def test_adjust_stock_is_audited_and_never_goes_negative(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1)
    stock.record(shop_conn, a, 3000, "opening")
    stock.adjust_stock(shop_conn, a, -1000, "damaged")
    assert stock.on_hand(shop_conn, a) == 2000
    assert shop_conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='adjust'").fetchone()[0] == 1
    with pytest.raises(stock.InsufficientStock):
        stock.adjust_stock(shop_conn, a, -5000, "oops")
    stock.adjust_stock(shop_conn, a, 500, "found")
    assert stock.on_hand(shop_conn, a) == 2500


@pytest.mark.parametrize("qty,reason", [(0, "x"), (1.5, "x"), (True, "x"), (1000, " "), (1000, None)])
def test_adjust_stock_validation(shop_conn, qty, reason):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1)
    with pytest.raises(stock.StockError):
        stock.adjust_stock(shop_conn, a, qty, reason)


def test_adjust_stock_refuses_serial_batch_unknown_and_read_only(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1, tracking="serial")
    milk = items.create_item(shop_conn, name="Milk", sell_price_paise=1, tracking="batch")
    for item_id in (phone, milk, 999):
        with pytest.raises(stock.StockError):
            stock.adjust_stock(shop_conn, item_id, 1000, "x")
    a = items.create_item(shop_conn, name="A", sell_price_paise=1)
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        stock.adjust_stock(shop_conn, a, 1000, "x")


# ---- billing -------------------------------------------------------------

def test_get_bill_detail_has_names_serials_payments_and_warranty(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial", warranty_months=12)
    unit = stock.add_unit(shop_conn, phone, serial="imei1")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    cust = parties.create_party(shop_conn, name="Ravi", phone="9")
    bill_id = billing.start_bill(shop_conn, party_id=cust)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="IMEI1")
    billing.finalize(shop_conn, bill_id, [("cash", 40000), ("upi", 60000)])
    d = billing.get_bill_detail(shop_conn, bill_id)
    assert d["bill"]["bill_no"] == "S000001" and d["party"]["name"] == "Ravi"
    assert (d["lines"][0]["item_name"], d["lines"][0]["serial"], d["lines"][0]["tracking"]) == ("Phone", "IMEI1", "serial")
    assert [(p["mode"], p["amount_paise"]) for p in d["payments"]] == [("cash", 40000), ("upi", 60000)]
    assert d["warranties"][0]["serial"] == "IMEI1"
    anon = billing.start_bill(shop_conn)
    assert billing.get_bill_detail(shop_conn, anon)["party"] is None


def test_list_bills_final_only_with_search_and_range(shop_conn):
    from retail import clock
    today = clock.today().isoformat()
    a = items.create_item(shop_conn, name="A", sell_price_paise=100)
    stock.record(shop_conn, a, 9000, "opening")
    ravi = parties.create_party(shop_conn, name="Ravi")
    b1, _ = sell(shop_conn, a, 1000, [("cash", 100)], party_id=ravi)
    sell(shop_conn, a, 1000, [("cash", 100)])
    billing.start_bill(shop_conn)  # held, must not be listed
    rows = billing.list_bills(shop_conn, today, today)
    assert [r["bill_no"] for r in rows] == ["S000002", "S000001"]
    assert [r["bill_no"] for r in billing.list_bills(shop_conn, today, today, search="ravi")] == ["S000001"]
    assert [r["bill_no"] for r in billing.list_bills(shop_conn, today, today, search="s000002")] == ["S000002"]
    assert billing.list_bills(shop_conn, "2001-01-01", "2001-01-02") == []
    with pytest.raises(ValueError):
        billing.list_bills(shop_conn, today, "2001-01-01")
    assert b1


def test_set_line_discount_updates_totals_and_is_held_only(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1000)
    stock.record(shop_conn, a, 9000, "opening")
    bill_id = billing.start_bill(shop_conn)
    line_id = billing.add_line(shop_conn, bill_id, a, 2000)
    billing.set_line_discount(shop_conn, bill_id, line_id, 500)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"] == 1500
    billing.set_line_discount(shop_conn, bill_id, line_id, 0)
    assert billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"] == 2000
    for bad in (-1, 1.5, True, 99999):
        with pytest.raises(billing.BillingError):
            billing.set_line_discount(shop_conn, bill_id, line_id, bad)
    with pytest.raises(billing.BillingError):
        billing.set_line_discount(shop_conn, bill_id, 999, 1)
    billing.finalize(shop_conn, bill_id, [("cash", 2000)])
    with pytest.raises(billing.BillingError):
        billing.set_line_discount(shop_conn, bill_id, line_id, 1)


def test_returnable_lines_tracks_what_is_left(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1000)
    stock.record(shop_conn, a, 9000, "opening")
    bill_id, line_id = sell(shop_conn, a, 3000, [("cash", 3000)])
    assert billing.returnable_lines(shop_conn, bill_id)[0]["remaining_milli"] == 3000
    billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    row = billing.returnable_lines(shop_conn, bill_id)[0]
    assert (row["returned_milli"], row["remaining_milli"], row["item_name"]) == (1000, 2000, "A")
    held = billing.start_bill(shop_conn)
    with pytest.raises(billing.BillingError):
        billing.returnable_lines(shop_conn, held)


# ---- purchases / staff / reports ---------------------------------------------

def test_list_purchases_and_list_expenses(shop_conn):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    sup = parties.create_party(shop_conn, name="Wholesale", type="supplier")
    purchases.create_purchase(shop_conn, party_id=sup, invoice_no="W1",
                              lines=[purchases.PurchaseLine(tea, 2000, 300)], date_iso="2026-09-01")
    purchases.create_purchase(shop_conn, party_id=None, invoice_no="W2",
                              lines=[purchases.PurchaseLine(tea, 1000, 300)], date_iso="2026-09-05")
    rows = purchases.list_purchases(shop_conn)
    assert [(r["invoice_no"], r["supplier"], r["total_paise"]) for r in rows] == [("W2", "", 300), ("W1", "Wholesale", 600)]
    person = staff.add_staff(shop_conn, name="Anil", monthly_salary_paise=1000)
    staff.add_expense(shop_conn, spent_on="2026-09-10", category="rent", amount_paise=500)
    staff.pay_salary(shop_conn, person, "2026-09-30")
    rows = staff.list_expenses(shop_conn, "2026-09-01", "2026-09-30")
    assert [(r["category"], r["staff_name"]) for r in rows] == [("salary", "Anil"), ("rent", "")]
    assert len(staff.list_expenses(shop_conn, "2026-09-01", "2026-09-30", category="rent")) == 1
    with pytest.raises(staff.StaffError):
        staff.list_expenses(shop_conn, "2026-09-30", "2026-09-01")
    with pytest.raises(staff.StaffError):
        staff.list_expenses(shop_conn, "2026-09-01", "2026-09-30", category="party")


def test_check_range_is_public():
    reports.check_range("2026-09-01", "2026-09-30")
    with pytest.raises(ValueError):
        reports.check_range("2026-09-30", "2026-09-01")
```
- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_support_services.py -v`
Expected: FAIL — `AttributeError: module 'retail.services.items' has no attribute 'list_items'` (and similar).

- [ ] **Step 3: Implement the engine additions**

Append to `retail/services/items.py` (it already imports `sqlite3`, `transaction`, `writes`, `audit`):
```python
_UPDATABLE = ("name", "sku", "hsn", "gst_rate_bp", "unit", "sell_price_paise", "buy_price_paise",
              "reorder_milli", "warranty_months", "tracking")
_INT_FIELDS = ("gst_rate_bp", "sell_price_paise", "buy_price_paise", "reorder_milli", "warranty_months")


def get_item(conn, item_id):
    return conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()


def item_barcodes(conn, item_id):
    return [r["code"] for r in conn.execute(
        "SELECT code FROM item_barcode WHERE item_id = ? ORDER BY code", (item_id,))]


def list_items(conn, search="", *, include_inactive=False, limit=500):
    search = (search or "").strip()
    return conn.execute(
        """SELECT i.*, COALESCE((SELECT SUM(qty_milli) FROM stock_movement WHERE item_id = i.id), 0)
                  AS on_hand_milli
           FROM item i
           WHERE (? = 1 OR i.active = 1)
             AND (? = '' OR instr(lower(i.name), lower(?)) > 0 OR i.sku = ?
                  OR EXISTS (SELECT 1 FROM item_barcode b WHERE b.item_id = i.id AND b.code = ?))
           ORDER BY i.name LIMIT ?""",
        (int(include_inactive), search, search, search, search, limit),
    ).fetchall()


@writes
def update_item(conn, item_id, **fields):
    unknown = sorted(set(fields) - set(_UPDATABLE))
    if unknown:
        raise ItemError(f"Cannot change {unknown}")
    if not fields:
        raise ItemError("Nothing to change")
    old = get_item(conn, item_id)
    if old is None:
        raise ItemError("No such item")
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip()
        if not fields["name"]:
            raise ItemError("Item name is required")
    for field in _INT_FIELDS:
        if field in fields and (type(fields[field]) is not int or fields[field] < 0):
            raise ItemError(f"{field} must be a non-negative whole number")
    if "sku" in fields:
        fields["sku"] = (fields["sku"] or "").strip() or None
    if "tracking" in fields:
        if fields["tracking"] not in TRACKING:
            raise ItemError(f"tracking must be one of {TRACKING}")
        if fields["tracking"] != old["tracking"] and conn.execute(
                "SELECT 1 FROM stock_movement WHERE item_id = ? LIMIT 1", (item_id,)).fetchone():
            raise ItemError("Tracking cannot change once the item has stock history")
    with transaction(conn):
        try:
            # column names come from the _UPDATABLE whitelist above, values are bound parameters
            conn.execute(f"UPDATE item SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                         (*fields.values(), item_id))
        except sqlite3.IntegrityError as exc:
            if "item.sku" in str(exc):
                raise ItemError(f"SKU {fields['sku']!r} is already used by another item") from exc
            raise
        audit.log(conn, "update", "item", item_id, ", ".join(sorted(fields)))


@writes
def set_item_active(conn, item_id, active):
    if type(active) is not bool:
        raise ItemError("active must be True or False")
    with transaction(conn):
        if conn.execute("UPDATE item SET active = ? WHERE id = ?", (int(active), item_id)).rowcount == 0:
            raise ItemError("No such item")
        audit.log(conn, "activate" if active else "deactivate", "item", item_id)


@writes
def set_barcodes(conn, item_id, codes):
    if isinstance(codes, str) or not isinstance(codes, (list, tuple, set)):
        raise ItemError("barcodes must be a list of codes")
    cleaned = list(dict.fromkeys(c.strip() for c in codes if isinstance(c, str) and c.strip()))
    with transaction(conn):
        if get_item(conn, item_id) is None:
            raise ItemError("No such item")
        conn.execute("DELETE FROM item_barcode WHERE item_id = ?", (item_id,))
        for code in cleaned:
            _insert_barcode(conn, item_id, code)
        audit.log(conn, "barcodes", "item", item_id, ",".join(cleaned))
```

Append to `retail/services/shop.py`:
```python
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
```

Append to `retail/services/parties.py`:
```python
def list_parties(conn, *, kind=None, search=""):
    if kind not in (None, "customer", "supplier"):
        raise PartyError("kind must be 'customer' or 'supplier'")
    search = (search or "").strip()
    rows = conn.execute(
        """SELECT * FROM party
           WHERE (? IS NULL OR type IN (?, 'both'))
             AND (? = '' OR instr(lower(name), lower(?)) > 0 OR instr(COALESCE(phone, ''), ?) > 0)
           ORDER BY name""",
        (kind, kind, search, search, search),
    ).fetchall()
    return [{**dict(r), "balance_paise": balance(conn, r["id"])} for r in rows]


@writes
def update_party(conn, party_id, *, name, phone=None, gstin=None, state_code=None):
    name = (name or "").strip()
    if not name:
        raise PartyError("Party name is required")
    with transaction(conn):
        cur = conn.execute(
            "UPDATE party SET name = ?, phone = ?, gstin = ?, state_code = ? WHERE id = ?",
            (name, phone, gstin, state_code, party_id))
        if cur.rowcount == 0:
            raise PartyError("No such party")
        audit.log(conn, "update", "party", party_id, name)
```

In `retail/services/stock.py` add `from retail.services import audit` to the imports and append:
```python
class StockError(ValueError):
    pass


@writes
def adjust_stock(conn, item_id, qty_milli, reason):
    """Audited manual correction (damage, count difference) for counted/weighed items."""
    if type(qty_milli) is not int or qty_milli == 0:
        raise StockError("An adjustment must be a non-zero whole number of milli-units")
    reason = (reason or "").strip() if isinstance(reason, str) or reason is None else ""
    if not reason:
        raise StockError("A reason is required")
    with transaction(conn):
        item = conn.execute("SELECT tracking FROM item WHERE id = ? AND active = 1", (item_id,)).fetchone()
        if item is None:
            raise StockError("No such item")
        if item["tracking"] in ("serial", "batch"):
            raise StockError("Serial and batch stock is changed through purchases and returns")
        if on_hand(conn, item_id) + qty_milli < 0:
            raise InsufficientStock("The adjustment would make stock negative")
        movement_id = _record(conn, item_id, qty_milli, "adjustment", "adjustment", None)
        audit.log(conn, "adjust", "item", item_id, f"{qty_milli}: {reason}")
    return movement_id
```

In `retail/services/reports.py`, directly after the `_check_range` function add `check_range = _check_range`.

In `retail/services/billing.py` add `from retail.services import reports` to the existing `from retail.services import ...` import, and append:
```python
def get_bill_detail(conn, bill_id):
    bill = _bill(conn, bill_id)
    party = None
    if bill["party_id"] is not None:
        party = conn.execute("SELECT * FROM party WHERE id = ?", (bill["party_id"],)).fetchone()
    lines = conn.execute(
        """SELECT l.*, i.name AS item_name, i.unit AS unit, i.tracking AS tracking,
                  u.serial AS serial, u.batch_no AS batch_no
           FROM bill_line l JOIN item i ON i.id = l.item_id
           LEFT JOIN stock_unit u ON u.id = l.unit_id
           WHERE l.bill_id = ? ORDER BY l.id""",
        (bill_id,),
    ).fetchall()
    payments = conn.execute("SELECT * FROM payment WHERE bill_id = ? ORDER BY id", (bill_id,)).fetchall()
    warranties = conn.execute(
        """SELECT w.*, u.serial AS serial FROM warranty w JOIN stock_unit u ON u.id = w.unit_id
           WHERE w.bill_id = ? ORDER BY w.id""",
        (bill_id,),
    ).fetchall()
    return {"bill": bill, "party": party, "lines": lines, "payments": payments, "warranties": warranties}


def list_bills(conn, start, end, *, search=""):
    reports.check_range(start, end)
    search = (search or "").strip()
    return conn.execute(
        """SELECT b.id, b.bill_no, b.kind, b.finalized_at, date(b.finalized_at) AS bill_date,
                  COALESCE(p.name, '') AS party, b.total_paise
           FROM bill b LEFT JOIN party p ON p.id = b.party_id
           WHERE b.status = 'final' AND date(b.finalized_at) BETWEEN ? AND ?
             AND (? = '' OR instr(lower(b.bill_no), lower(?)) > 0
                  OR instr(lower(COALESCE(p.name, '')), lower(?)) > 0)
           ORDER BY b.finalized_at DESC, b.id DESC""",
        (start, end, search, search, search),
    ).fetchall()


@writes
def set_line_discount(conn, bill_id, line_id, discount_paise):
    if type(discount_paise) is not int or discount_paise < 0:
        raise BillingError("Discount must be a non-negative whole number of paise")
    with transaction(conn):
        _bill(conn, bill_id, status="held")
        line = conn.execute("SELECT * FROM bill_line WHERE id = ? AND bill_id = ?", (line_id, bill_id)).fetchone()
        if line is None:
            raise BillingError("No such line on this bill")
        amount = money.line_amount(line["rate_paise"], line["qty_milli"]) - discount_paise
        if amount < 0:
            raise BillingError("Discount is larger than the line amount")
        conn.execute("UPDATE bill_line SET discount_paise = ?, amount_paise = ? WHERE id = ?",
                     (discount_paise, amount, line_id))
        _retax(conn, bill_id)


def returnable_lines(conn, bill_id):
    bill = _bill(conn, bill_id, status="final")
    if bill["kind"] != "sale":
        raise BillingError("Only sale bills can be returned")
    rows = conn.execute(
        """SELECT l.id AS line_id, l.item_id, i.name AS item_name, i.tracking, l.qty_milli, l.total_paise,
                  COALESCE((SELECT SUM(r.qty_milli) FROM bill_line r JOIN bill rb ON rb.id = r.bill_id
                            WHERE r.ref_line_id = l.id AND rb.kind = 'sale_return' AND rb.status = 'final'), 0)
                      AS returned_milli
           FROM bill_line l JOIN item i ON i.id = l.item_id WHERE l.bill_id = ? ORDER BY l.id""",
        (bill_id,),
    ).fetchall()
    return [{**dict(r), "remaining_milli": r["qty_milli"] - r["returned_milli"]} for r in rows]
```

Append to `retail/services/purchases.py`:
```python
def list_purchases(conn, limit=50):
    return conn.execute(
        """SELECT p.id, p.invoice_no, p.purchase_date, COALESCE(pt.name, '') AS supplier, p.total_paise
           FROM purchase p LEFT JOIN party pt ON pt.id = p.party_id
           ORDER BY p.purchase_date DESC, p.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
```

Append to `retail/services/staff.py` (reuse its `_check_date`, `CATEGORIES`, `StaffError`):
```python
def list_expenses(conn, start, end, category=None):
    _check_date(start)
    _check_date(end)
    if start > end:
        raise StaffError("The start date must not be after the end date")
    if category is not None and category not in CATEGORIES:
        raise StaffError(f"category must be one of {CATEGORIES}")
    sql = ("SELECT e.*, COALESCE(s.name, '') AS staff_name FROM expense e "
           "LEFT JOIN staff s ON s.id = e.staff_id WHERE e.spent_on BETWEEN ? AND ?")
    params = [start, end]
    if category is not None:
        sql += " AND e.category = ?"
        params.append(category)
    return conn.execute(sql + " ORDER BY e.spent_on DESC, e.id DESC", params).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_support_services.py -v` then `.venv/Scripts/python -W error::ResourceWarning -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add list/update/detail APIs the UI screens need" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: UI package scaffold — paths, settings, formatting, validators

**Files:**
- Modify: `pyproject.toml`
- Create: `retail_ui/__init__.py`, `retail_ui/vendor.py`, `retail_ui/paths.py`, `retail_ui/settings.py`, `retail_ui/fmt.py`, `retail_ui/states.py`, `retail_ui/validators.py`, `tests/ui/conftest.py`, `tests/ui/test_ui_scaffold.py`

**Interfaces:**
- Produces: `retail_ui.APP_NAME`, `retail_ui.__version__`; `vendor.VENDOR_PHONE`, `vendor.VENDOR_EMAIL`, `vendor.whatsapp_request_url(machine_id) -> str`, `vendor.email_request_url(machine_id) -> str | None`; `paths.AppPaths(root: Path)` with properties `db_path, license_path, settings_path, backup_dir, log_path`, `ensure()`, classmethod `default()`; `settings.UiSettings` dataclass (`backup_dir: str = ""`, `extra_backup_dir: str = ""`, `auto_print: bool = False`, `print_layout: str = ""`), `settings.load(path) -> UiSettings` (never raises; corrupt/missing → defaults), `settings.save(path, s) -> None` (atomic); `fmt.rupees(paise) -> str`, `fmt.parse_rupees(text) -> int`, `fmt.qty(milli) -> str`, `fmt.parse_qty(text) -> int` (> 0), `fmt.date_text(iso) -> str`; `states.STATES: dict[str, str]`; `validators.gstin_error(text, state_code) -> str | None`, `validators.phone_digits(text) -> str`.

- [ ] **Step 1: Update `pyproject.toml` and install**

Edit `pyproject.toml`:
```toml
dependencies = ["cryptography>=42", "PySide6>=6.10,<7"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-qt>=4.5", "pyinstaller>=6.20"]

[tool.setuptools.packages.find]
include = ["retail*", "retail_ui*"]
```
and in `[tool.pytest.ini_options]` add `qt_api = "pyside6"`.

Run: `.venv/Scripts/python -m pip install -e ".[dev]"`
Expected: installs PySide6, pytest-qt, pyinstaller without error (PySide6 is a large download).

- [ ] **Step 2: Write the failing tests**

`tests/ui/conftest.py`:
```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # must be set before any QApplication exists
```

`tests/ui/test_ui_scaffold.py`:
```python
import json

import pytest

import retail_ui
from retail_ui import fmt, paths, settings, states, validators, vendor


def test_app_identity():
    assert retail_ui.APP_NAME == "Retail App" and retail_ui.__version__


def test_default_paths_use_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    p = paths.AppPaths.default()
    assert p.root == tmp_path / "RetailApp"
    p.ensure()
    assert p.root.is_dir() and p.backup_dir.is_dir()
    assert p.db_path.name == "shop.db" and p.license_path.name == "license.key"
    assert p.settings_path.name == "settings.json"


def test_settings_round_trip_and_tolerance(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path) == settings.UiSettings()
    s = settings.UiSettings(backup_dir="D:/bk", extra_backup_dir="E:/usb", auto_print=True, print_layout="a4")
    settings.save(path, s)
    assert settings.load(path) == s
    path.write_text("{not json", encoding="utf-8")
    assert settings.load(path) == settings.UiSettings()
    path.write_text(json.dumps({"backup_dir": 5, "auto_print": "yes", "extra": 1}), encoding="utf-8")
    assert settings.load(path) == settings.UiSettings()          # wrong types fall back to defaults
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("paise,text", [
    (0, "₹0.00"), (5, "₹0.05"), (123456, "₹1,234.56"), (12345678, "₹1,23,456.78"),
    (123456789, "₹12,34,567.89"), (-250000, "-₹2,500.00"), (99999, "₹999.99"),
])
def test_rupees_uses_indian_grouping(paise, text):
    assert fmt.rupees(paise) == text


@pytest.mark.parametrize("text,paise", [("₹1,234.50", 123450), (" 12 ", 1200), ("0.5", 50), ("12.345", 1235)])
def test_parse_rupees(text, paise):
    assert fmt.parse_rupees(text) == paise


@pytest.mark.parametrize("text", ["", "abc", "1.2.3", "₹", "--5"])
def test_parse_rupees_rejects_garbage(text):
    with pytest.raises(ValueError):
        fmt.parse_rupees(text)


def test_qty_helpers():
    assert fmt.qty(750) == "0.75" and fmt.qty(2000) == "2"
    assert fmt.parse_qty("0.75") == 750 and fmt.parse_qty(" 3 ") == 3000
    for bad in ("", "0", "-1", "abc", "0.0001"):
        with pytest.raises(ValueError):
            fmt.parse_qty(bad)


def test_date_text():
    assert fmt.date_text("2026-09-30") == "30-09-2026"
    assert fmt.date_text("2026-09-30T10:05:09") == "30-09-2026 10:05"
    assert fmt.date_text("") == ""


def test_states_and_gstin_validation():
    assert states.STATES["36"] == "Telangana" and states.STATES["27"] == "Maharashtra" and "28" not in states.STATES
    assert validators.gstin_error("", "36") is None                    # optional
    assert validators.gstin_error("36ABCDE1234F1Z5", "36") is None
    assert validators.gstin_error("36abcde1234f1z5", "36") is None     # case-insensitive
    assert validators.gstin_error("36ABCDE1234F1Z5", "27") is not None  # state prefix mismatch
    assert validators.gstin_error("123", "36") is not None
    assert validators.phone_digits("+91 98765-43210") == "919876543210"


def test_vendor_urls():
    assert vendor.whatsapp_request_url("RTL-AAAA-BBBB-CCCC-DDDD").startswith("https://wa.me/919866079246?text=")
    assert "RTL-AAAA-BBBB-CCCC-DDDD" in __import__("urllib.parse").parse.unquote(vendor.whatsapp_request_url("RTL-AAAA-BBBB-CCCC-DDDD"))
    assert (vendor.email_request_url("X") is None) == (vendor.VENDOR_EMAIL == "")
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_scaffold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui'`.

- [ ] **Step 4: Implement**

`retail_ui/__init__.py`:
```python
from retail import __version__  # noqa: F401  (shown in the About box)

APP_NAME = "Retail App"  # working title — change here when the product name is chosen
```

`retail_ui/vendor.py`:
```python
"""The software vendor's own contact details (not the shop's). A blank value is simply not offered."""
import re
import urllib.parse

VENDOR_PHONE = "+91 98660 79246"  # also the vendor's WhatsApp number (same as Kuttu)
VENDOR_EMAIL = ""


def _digits(phone):
    return re.sub(r"\D", "", phone)


def whatsapp_request_url(machine_id):
    text = f"Hello, I need a license key for Retail App. My machine ID is {machine_id}"
    return f"https://wa.me/{_digits(VENDOR_PHONE)}?text={urllib.parse.quote(text)}"


def email_request_url(machine_id):
    if not VENDOR_EMAIL:
        return None
    subject = urllib.parse.quote("Retail App - license request")
    body = urllib.parse.quote(f"Please issue a license key for machine ID {machine_id}")
    return f"mailto:{urllib.parse.quote(VENDOR_EMAIL, safe='@')}?subject={subject}&body={body}"
```

`retail_ui/paths.py`:
```python
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
```

`retail_ui/settings.py`:
```python
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
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    os.replace(tmp, path)
```

`retail_ui/fmt.py`:
```python
"""Display formatting and parsing. Money stays integer paise and quantity integer milli-units
everywhere else; only this module turns them into text."""
from decimal import Decimal, InvalidOperation

from retail import money


def _group(whole: int) -> str:
    digits = str(whole)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def rupees(paise: int, symbol: str = "₹") -> str:
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{symbol}{_group(whole)}.{frac:02d}"


def parse_rupees(text: str) -> int:
    cleaned = (text or "").replace("₹", "").replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Not an amount: {text!r}") from exc
    if not value.is_finite():
        raise ValueError(f"Not an amount: {text!r}")
    return money.rupees_to_paise(value)


def qty(milli: int) -> str:
    return money.milli_to_str(milli)


def parse_qty(text: str) -> int:
    try:
        milli = money.qty_to_milli((text or "").strip())
    except InvalidOperation as exc:
        raise ValueError(f"Not a quantity: {text!r}") from exc
    if milli <= 0:
        raise ValueError("Quantity must be greater than zero")
    return milli


def date_text(iso: str) -> str:
    if not iso:
        return ""
    day, _, clock_part = iso.partition("T")
    y, m, d = day.split("-")
    return f"{d}-{m}-{y}" + (f" {clock_part[:5]}" if clock_part else "")
```
(`money.qty_to_milli` raises `decimal.InvalidOperation` on junk, which `parse_qty` converts to `ValueError`; `money.rupees_to_paise` of a non-finite value is rejected above.)

`retail_ui/states.py`:
```python
"""GST state / union-territory codes (names stay in English: proper nouns)."""
STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
```

`retail_ui/validators.py`:
```python
import re

_GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$")


def gstin_error(text, state_code):
    """None when blank (optional) or well-formed and matching the state code, else a reason."""
    text = (text or "").strip().upper()
    if not text:
        return None
    if not _GSTIN.match(text):
        return "format"
    if text[:2] != state_code:
        return "state"
    return None


def phone_digits(text):
    return re.sub(r"\D", "", text or "")
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_scaffold.py -v` then the full suite `.venv/Scripts/python -W error::ResourceWarning -m pytest -q`
Expected: all PASS. (If `ResourceWarning` appears from Qt, report it rather than silencing the whole suite.)

```bash
git add -A
git commit -m "feat: add retail_ui scaffold with paths, settings, formatting and validators" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Translated error messages and the locale-merge tool

Reviewer finding M9: services raise English text. The UI must never show it to a Hindi/Telugu user. Errors are mapped by exception *type* to a translated key; the English detail goes only to a log and a "details" pane.

**Files:**
- Create: `tools/locale_add.py`, `retail_ui/errors.py`, `tests/test_locale_add.py`, `tests/ui/test_ui_errors.py`
- Modify: `retail/locales/en.json`, `hi.json`, `te.json` (via the tool), `tests/test_i18n.py` (allow-list)

**Interfaces:**
- Produces: `locale_add.merge(snippet: dict, locales_dir=Path("retail/locales")) -> list[str]` (returns the keys added; raises `ValueError` on a missing language, empty text, a conflicting existing key, or mismatched `{placeholders}`); CLI `python -m tools.locale_add snippet.json`. `errors.message_for(exc) -> str` (translated, never raises), `errors.detail_for(exc) -> str` (English, for logs), `errors.show_error(parent, exc) -> None` (modal `QMessageBox` with translated text and the English detail under "Details"). Every later task adds its strings with `locale_add` — never by hand-editing the three JSON files.

- [ ] **Step 1: Write the failing tests**

`tests/test_locale_add.py`:
```python
import json

import pytest

from tools import locale_add


@pytest.fixture
def locales(tmp_path):
    for code, text in (("en", "Total"), ("hi", "कुल"), ("te", "మొత్తం")):
        (tmp_path / f"{code}.json").write_text(json.dumps({"bill.total": text}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def load(locales, code):
    return json.loads((locales / f"{code}.json").read_text(encoding="utf-8"))


def test_merge_adds_keys_to_all_three_files(locales):
    added = locale_add.merge({"a.b": {"en": "Hello", "hi": "नमस्ते", "te": "హలో"}}, locales)
    assert added == ["a.b"]
    assert load(locales, "hi")["a.b"] == "नमस्ते" and load(locales, "te")["bill.total"] == "మొత్తం"
    assert (locales / "en.json").read_text(encoding="utf-8").endswith("}\n")


def test_merge_is_idempotent_for_identical_values(locales):
    snippet = {"a.b": {"en": "Hello", "hi": "नमस्ते", "te": "హలో"}}
    locale_add.merge(snippet, locales)
    assert locale_add.merge(snippet, locales) == []


@pytest.mark.parametrize("entry", [
    {"en": "x", "hi": "y"},                                  # missing te
    {"en": "x", "hi": "", "te": "z"},                        # empty
    {"en": "{n} items", "hi": "वस्तुएँ", "te": "{n} వస్తువులు"},  # placeholder mismatch
    {"en": "x", "hi": "y", "te": "z", "fr": "w"},            # unknown language
])
def test_merge_rejects_bad_entries_and_writes_nothing(locales, entry):
    before = {c: (locales / f"{c}.json").read_text(encoding="utf-8") for c in ("en", "hi", "te")}
    with pytest.raises(ValueError):
        locale_add.merge({"k": entry}, locales)
    assert before == {c: (locales / f"{c}.json").read_text(encoding="utf-8") for c in ("en", "hi", "te")}


def test_merge_rejects_changing_an_existing_key(locales):
    with pytest.raises(ValueError):
        locale_add.merge({"bill.total": {"en": "Sum", "hi": "योग", "te": "మొత్తం"}}, locales)


def test_cli_reads_a_snippet_file(locales, tmp_path, capsys):
    snippet = tmp_path / "s.json"
    snippet.write_text(json.dumps({"x.y": {"en": "A", "hi": "ए", "te": "ఎ"}}, ensure_ascii=False), encoding="utf-8")
    assert locale_add.main([str(snippet), "--locales", str(locales)]) == 0
    assert "x.y" in capsys.readouterr().out
    assert locale_add.main([str(tmp_path / "missing.json"), "--locales", str(locales)]) == 2
```

`tests/ui/test_ui_errors.py`:
```python
import sqlite3

import pytest

from retail import guard, i18n
from retail.services import backup, billing, items, parties, purchases, shop, staff, stock
from retail_ui import errors


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.mark.parametrize("exc,key", [
    (guard.ReadOnlyError("License expired"), "err.read_only"),
    (stock.InsufficientStock("Only 1 in stock"), "err.insufficient_stock"),
    (billing.SerialUnavailable("Serial 'X' is not in stock"), "err.serial_unavailable"),
    (stock.DuplicateSerial("Serial already exists"), "err.duplicate_serial"),
    (backup.BackupError("bad"), "err.backup"),
    (shop.ShopNotSetUp("x"), "err.shop_not_set_up"),
    (billing.BillingError("x"), "err.invalid_input"),
    (items.ItemError("x"), "err.invalid_input"),
    (parties.PartyError("x"), "err.invalid_input"),
    (purchases.PurchaseError("x"), "err.invalid_input"),
    (shop.ShopError("x"), "err.invalid_input"),
    (staff.StaffError("x"), "err.invalid_input"),
    (stock.StockError("x"), "err.invalid_input"),
    (PermissionError("x"), "err.file"),
    (sqlite3.OperationalError("locked"), "err.unexpected"),
    (RuntimeError("boom"), "err.unexpected"),
])
def test_message_for_maps_exception_types_to_translated_text(exc, key):
    assert errors.message_for(exc) == i18n.tr(key)


def test_serial_unavailable_wins_over_its_parent_class():
    assert errors.message_for(billing.SerialUnavailable("x")) != errors.message_for(billing.BillingError("x"))


@pytest.mark.parametrize("code", ["hi", "te"])
def test_messages_are_translated_and_never_contain_the_english_detail(code):
    i18n.set_language(code)
    exc = stock.InsufficientStock("Only 3 in stock")
    text = errors.message_for(exc)
    assert text != i18n.tr("err.unexpected") and "Only 3" not in text
    i18n.set_language("en")
    assert text != errors.message_for(exc)


def test_detail_is_english_and_names_the_type():
    assert errors.detail_for(items.ItemError("Barcode '1' is already used")) == "ItemError: Barcode '1' is already used"


def test_show_error_builds_a_box_with_translated_text_and_details(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    captured = {}
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.update(
        text=self.text(), details=self.detailedText()) or 0)
    errors.show_error(None, items.ItemError("dup"))
    assert captured["text"] == i18n.tr("err.invalid_input") and "ItemError: dup" in captured["details"]
```

In `tests/test_i18n.py` change `SAME_AS_ENGLISH_ALLOWED = {"pay.upi"}` to:
```python
SAME_AS_ENGLISH_ALLOWED = {"pay.upi", "tax.gstin", "tax.cgst", "tax.sgst", "tax.igst", "item.hsn", "item.sku"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_locale_add.py tests/ui/test_ui_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.locale_add'` / `retail_ui.errors`.

- [ ] **Step 3: Implement the tool and the error mapper**

`tools/locale_add.py`:
```python
"""Dev tool: merge new UI strings into the en/hi/te catalogues in one atomic step.

  python -m tools.locale_add snippet.json [--locales retail/locales]

snippet.json: {"some.key": {"en": "...", "hi": "...", "te": "..."}, ...}
"""
import argparse
import json
import string
import sys
from pathlib import Path

LANGS = ("en", "hi", "te")
DEFAULT_DIR = Path("retail/locales")


def _fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def merge(snippet, locales_dir=DEFAULT_DIR):
    locales_dir = Path(locales_dir)
    catalogues = {c: json.loads((locales_dir / f"{c}.json").read_text(encoding="utf-8")) for c in LANGS}
    added = []
    for key, entry in snippet.items():
        if not isinstance(entry, dict) or set(entry) != set(LANGS):
            raise ValueError(f"{key}: needs exactly the languages {LANGS}")
        for code in LANGS:
            if not isinstance(entry[code], str) or not entry[code].strip():
                raise ValueError(f"{key}: empty text for {code}")
        if any(_fields(entry[c]) != _fields(entry["en"]) for c in LANGS):
            raise ValueError(f"{key}: {{placeholders}} differ between languages")
        existing = [catalogues[c].get(key) for c in LANGS]
        if any(v is not None for v in existing):
            if [entry[c] for c in LANGS] != existing:
                raise ValueError(f"{key}: already defined with different text")
            continue
        for code in LANGS:
            catalogues[code][key] = entry[code]
        added.append(key)
    if added:
        for code in LANGS:  # only after every entry validated
            (locales_dir / f"{code}.json").write_text(
                json.dumps(catalogues[code], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


def main(argv=None):
    parser = argparse.ArgumentParser(prog="locale_add")
    parser.add_argument("snippet")
    parser.add_argument("--locales", default=str(DEFAULT_DIR))
    args = parser.parse_args(argv)
    try:
        snippet = json.loads(Path(args.snippet).read_text(encoding="utf-8"))
        added = merge(snippet, args.locales)
    except (OSError, ValueError) as exc:
        print(f"locale_add: {exc}", file=sys.stderr)
        return 2
    print(f"added {len(added)} key(s): {', '.join(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`retail_ui/errors.py`:
```python
"""User-facing error text. Services raise English messages; the UI never shows them. A translated
message is chosen by exception *type*, and the English detail goes to the log and a Details pane."""
import logging

from retail import guard, i18n
from retail.services import backup, billing, items, parties, purchases, shop, staff, stock

log = logging.getLogger("retail_ui")

# order matters: most specific first (SerialUnavailable and InsufficientStock are ValueErrors)
_MAP = (
    (guard.ReadOnlyError, "err.read_only"),
    (stock.InsufficientStock, "err.insufficient_stock"),
    (billing.SerialUnavailable, "err.serial_unavailable"),
    (stock.DuplicateSerial, "err.duplicate_serial"),
    (backup.BackupError, "err.backup"),
    (shop.ShopNotSetUp, "err.shop_not_set_up"),
    ((billing.BillingError, items.ItemError, parties.PartyError, purchases.PurchaseError,
      shop.ShopError, staff.StaffError, stock.StockError), "err.invalid_input"),
    (OSError, "err.file"),
)


def message_for(exc) -> str:
    for types, key in _MAP:
        if isinstance(exc, types):
            return i18n.tr(key)
    return i18n.tr("err.unexpected")


def detail_for(exc) -> str:
    return f"{type(exc).__name__}: {exc}"


def show_error(parent, exc) -> None:
    from PySide6.QtWidgets import QMessageBox  # imported lazily so message_for stays Qt-free

    log.error("handled error shown to user: %s", detail_for(exc), exc_info=exc)
    box = QMessageBox(QMessageBox.Icon.Warning, i18n.tr("err.title"), message_for(exc),
                      QMessageBox.StandardButton.Ok, parent)
    box.setDetailedText(detail_for(exc))
    box.exec()
```

- [ ] **Step 4: Add the strings with the tool**

Create `.superpowers/locale/task4.json` (git-ignored scratch) with exactly:
```json
{
  "err.title": {"en": "Something went wrong", "hi": "कुछ गड़बड़ हो गई", "te": "ఏదో తప్పు జరిగింది"},
  "err.read_only": {"en": "The license has expired, so changes are blocked. You can still view, export and back up your data.", "hi": "लाइसेंस समाप्त हो गया है, इसलिए बदलाव बंद हैं। आप डेटा देख, एक्सपोर्ट और बैकअप कर सकते हैं।", "te": "లైసెన్స్ గడువు ముగిసింది, కాబట్టి మార్పులు నిలిపివేయబడ్డాయి. మీరు డేటాను చూడవచ్చు, ఎక్స్‌పోర్ట్ చేయవచ్చు, బ్యాకప్ తీసుకోవచ్చు."},
  "err.insufficient_stock": {"en": "Not enough stock for this item.", "hi": "इस वस्तु का पर्याप्त स्टॉक नहीं है।", "te": "ఈ వస్తువుకు సరిపడా స్టాక్ లేదు."},
  "err.serial_unavailable": {"en": "That serial / IMEI is not available.", "hi": "यह सीरियल / IMEI उपलब्ध नहीं है।", "te": "ఆ సీరియల్ / IMEI అందుబాటులో లేదు."},
  "err.duplicate_serial": {"en": "That serial / IMEI already exists.", "hi": "यह सीरियल / IMEI पहले से मौजूद है।", "te": "ఆ సీరియల్ / IMEI ఇప్పటికే ఉంది."},
  "err.backup": {"en": "The backup could not be completed or restored. Your current data was not changed.", "hi": "बैकअप पूरा नहीं हो सका या रीस्टोर नहीं हुआ। आपका मौजूदा डेटा नहीं बदला गया।", "te": "బ్యాకప్ పూర్తికాలేదు లేదా రీస్టోర్ కాలేదు. మీ ప్రస్తుత డేటా మారలేదు."},
  "err.shop_not_set_up": {"en": "The shop has not been set up yet.", "hi": "दुकान की सेटिंग अभी पूरी नहीं हुई है।", "te": "దుకాణం సెటప్ ఇంకా పూర్తికాలేదు."},
  "err.invalid_input": {"en": "That input is not valid. Please check it and try again.", "hi": "यह जानकारी सही नहीं है। कृपया जाँचकर फिर कोशिश करें।", "te": "ఈ సమాచారం సరైనది కాదు. దయచేసి పరిశీలించి మళ్లీ ప్రయత్నించండి."},
  "err.file": {"en": "A file could not be read or written. Check the folder and try again.", "hi": "फ़ाइल पढ़ी या लिखी नहीं जा सकी। फ़ोल्डर जाँचकर फिर कोशिश करें।", "te": "ఫైల్‌ను చదవడం లేదా రాయడం సాధ్యం కాలేదు. ఫోల్డర్ పరిశీలించి మళ్లీ ప్రయత్నించండి."},
  "err.unexpected": {"en": "An unexpected problem occurred. Your data is safe; please try again.", "hi": "कोई अनपेक्षित समस्या आई। आपका डेटा सुरक्षित है; कृपया फिर कोशिश करें।", "te": "ఊహించని సమస్య వచ్చింది. మీ డేటా సురక్షితంగా ఉంది; దయచేసి మళ్లీ ప్రయత్నించండి."},
  "common.ok": {"en": "OK", "hi": "ठीक है", "te": "సరే"},
  "common.close": {"en": "Close", "hi": "बंद करें", "te": "మూసివేయి"},
  "common.yes": {"en": "Yes", "hi": "हाँ", "te": "అవును"},
  "common.no": {"en": "No", "hi": "नहीं", "te": "కాదు"},
  "common.add": {"en": "Add", "hi": "जोड़ें", "te": "జోడించు"},
  "common.edit": {"en": "Edit", "hi": "बदलें", "te": "మార్చు"},
  "common.delete": {"en": "Delete", "hi": "हटाएँ", "te": "తొలగించు"},
  "common.refresh": {"en": "Refresh", "hi": "रिफ्रेश", "te": "రిఫ్రెష్"},
  "common.export": {"en": "Export", "hi": "एक्सपोर्ट", "te": "ఎక్స్‌పోర్ట్"},
  "common.name": {"en": "Name", "hi": "नाम", "te": "పేరు"},
  "common.phone": {"en": "Phone", "hi": "फ़ोन", "te": "ఫోన్"},
  "common.date": {"en": "Date", "hi": "तारीख", "te": "తేదీ"},
  "common.from": {"en": "From", "hi": "से", "te": "నుండి"},
  "common.to": {"en": "To", "hi": "तक", "te": "వరకు"},
  "common.amount": {"en": "Amount", "hi": "राशि", "te": "మొత్తం సొమ్ము"},
  "common.note": {"en": "Note", "hi": "टिप्पणी", "te": "గమనిక"},
  "common.details": {"en": "Details", "hi": "विवरण", "te": "వివరాలు"},
  "common.browse": {"en": "Browse…", "hi": "चुनें…", "te": "ఎంచుకోండి…"},
  "common.confirm": {"en": "Are you sure?", "hi": "क्या आप निश्चित हैं?", "te": "మీరు ఖచ్చితంగా ఉన్నారా?"},
  "tax.gstin": {"en": "GSTIN", "hi": "GSTIN", "te": "GSTIN"},
  "tax.cgst": {"en": "CGST", "hi": "CGST", "te": "CGST"},
  "tax.sgst": {"en": "SGST", "hi": "SGST", "te": "SGST"},
  "tax.igst": {"en": "IGST", "hi": "IGST", "te": "IGST"},
  "item.hsn": {"en": "HSN", "hi": "HSN", "te": "HSN"},
  "item.sku": {"en": "SKU", "hi": "SKU", "te": "SKU"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task4.json`
Expected: `added 36 key(s): err.title, …`.

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/test_locale_add.py tests/ui/test_ui_errors.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS (the i18n completeness test now also covers the 36 new keys).

```bash
git add -A
git commit -m "feat: add translated error messages and the locale-merge tool" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: AppSession, per-language fonts and the boot flow

**Files:**
- Create: `retail_ui/session.py`, `retail_ui/fonts.py`, `retail_ui/bootstrap.py`, `tests/ui/test_ui_session.py`, `tests/ui/test_ui_bootstrap.py`, `tests/ui/test_ui_fonts.py`
- Modify: `tests/ui/conftest.py` (add fixtures)

**Interfaces:**
- Consumes: `paths.AppPaths`, `settings.UiSettings/load/save`, `db.open_shop`, `backup.*`, `shop.*`, `license.apply_license/verify_key/save_key`, `i18n.set_language`, `guard`.
- Produces:
  - `session.AppSession(paths, settings, conn, license_state, *, public_key, machine_id)`, a `QObject` with signals `language_changed(str)`, `read_only_changed(bool)`, `data_changed()` and: attributes `paths, settings, conn, license, public_key, machine_id`; properties `read_only`, `backup_dir`; methods `has_shop() -> bool`, `shop() -> Row`, `set_language(code)`, `save_settings()`, `refresh_license()` (re-checks the key file, updates the guard, emits `read_only_changed`), `activate(key) -> LicenseState`, `notify_changed()`, `backup_now() -> BackupResult`, `backup_if_due() -> None` (never raises), `restore_from(path) -> Path | None` (closes the connection, restores, reopens; on failure reopens the old data and re-raises), `close()`.
  - `fonts.choose_family(code, available: set[str]) -> str` (empty string = keep Qt default), `fonts.apply_language_font(app, code) -> str`.
  - `bootstrap.bootstrap(paths, *, public_key, machine_id, request_activation, run_onboarding, today=None) -> AppSession | None`. `request_activation(machine_id, invalid: bool) -> str | None` returns a key or `None` to quit; `run_onboarding(session) -> bool`.
  - Fixtures in `tests/ui/conftest.py`: `paths`, `keypair`, `machine_id`, `make_session(template="grocery", expires="2099-12-31", with_shop=True)` (all sessions are closed at teardown).

- [ ] **Step 1: Add the fixtures**

Append to `tests/ui/conftest.py`:
```python
import pytest

from retail import db, license as lic, segments
from retail.services import shop
from retail_ui.paths import AppPaths
from retail_ui.session import AppSession
from retail_ui.settings import UiSettings
from tools import license_issuer


@pytest.fixture
def paths(tmp_path):
    p = AppPaths(tmp_path / "RetailApp")
    p.ensure()
    return p


@pytest.fixture
def keypair():
    return license_issuer.generate_keypair()  # (private, public)


@pytest.fixture
def machine_id():
    return "RTL-TEST-0000-0000-0001"


@pytest.fixture
def make_session(paths, keypair, machine_id):
    made = []

    def make(*, template="grocery", expires="2099-12-31", with_shop=True):
        private, public = keypair
        lic.save_key(paths.license_path, license_issuer.issue(
            private, machine=machine_id, buyer="Test Shop", expires=expires))
        conn = db.open_shop(paths.db_path, paths.backup_dir)
        state = lic.apply_license(paths.license_path, public, machine_id)
        session = AppSession(paths, UiSettings(), conn, state, public_key=public, machine_id=machine_id)
        if with_shop:
            shop.setup_shop(conn, name="Test Shop", state_code="36")
            segments.apply_template(conn, template)
        made.append(session)
        return session

    yield make
    for session in made:
        try:
            session.close()
        except Exception:  # a test may already have closed the connection
            pass
```

- [ ] **Step 2: Write the failing tests**

`tests/ui/test_ui_session.py`:
```python
from datetime import date

import pytest

from retail import guard, i18n
from retail.services import items, shop
from retail_ui import settings as ui_settings


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def test_session_exposes_shop_and_license(make_session):
    s = make_session()
    assert s.has_shop() and s.shop()["name"] == "Test Shop"
    assert s.license.status == "active" and s.read_only is False
    assert s.backup_dir == s.paths.backup_dir


def test_session_without_shop(make_session):
    s = make_session(with_shop=False)
    assert s.has_shop() is False


def test_set_language_persists_switches_catalogue_and_emits(make_session, qtbot):
    s = make_session()
    with qtbot.waitSignal(s.language_changed) as blocker:
        s.set_language("hi")
    assert blocker.args == ["hi"] and shop.get_shop(s.conn)["language"] == "hi" and i18n.get_language() == "hi"
    with pytest.raises(shop.ShopError):
        s.set_language("fr")
    assert i18n.get_language() == "hi"


def test_custom_backup_dir_and_settings_save(make_session, tmp_path):
    s = make_session()
    s.settings.backup_dir = str(tmp_path / "mybk")
    s.save_settings()
    assert s.backup_dir == tmp_path / "mybk"
    assert ui_settings.load(s.paths.settings_path).backup_dir == str(tmp_path / "mybk")


def test_backup_now_and_backup_if_due(make_session):
    s = make_session()
    result = s.backup_now()
    assert result.path.exists() and result.path.parent == s.backup_dir
    s.backup_if_due()          # a daily backup now exists -> no second daily file
    assert len([p for p in s.backup_dir.glob("daily-*.db")]) == 1


def test_backup_if_due_never_raises(make_session, monkeypatch):
    s = make_session()
    from retail.services import backup
    monkeypatch.setattr(backup, "backup_now", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    s.backup_if_due()          # must swallow the failure (and log it)


def test_extra_backup_dir_gets_a_copy(make_session, tmp_path):
    s = make_session()
    s.settings.extra_backup_dir = str(tmp_path / "usb")
    result = s.backup_now()
    assert (tmp_path / "usb" / result.path.name).exists() and result.extra_error is None


def test_restore_from_swaps_the_database_and_notifies(make_session, qtbot):
    s = make_session()
    snapshot = s.backup_now().path
    items.create_item(s.conn, name="Added later", sell_price_paise=100)
    with qtbot.waitSignal(s.data_changed):
        safety = s.restore_from(snapshot)
    assert safety is not None and safety.exists()
    assert [r["name"] for r in items.list_items(s.conn)] == []          # the new connection sees the old data
    items.create_item(s.conn, name="Works after restore", sell_price_paise=100)


def test_failed_restore_keeps_working_on_the_old_data(make_session, tmp_path):
    from retail.services import backup
    s = make_session()
    items.create_item(s.conn, name="Keep me", sell_price_paise=100)
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database")
    with pytest.raises(backup.BackupError):
        s.restore_from(bad)
    assert [r["name"] for r in items.list_items(s.conn)] == ["Keep me"]   # connection reopened on the old data


def test_activate_saves_only_valid_keys_and_emits(make_session, keypair, machine_id, qtbot):
    from retail import license as lic
    from tools import license_issuer
    s = make_session(expires="2099-12-31")
    good_before = lic.load_key(s.paths.license_path)
    assert s.activate("garbage").status == "invalid"
    assert lic.load_key(s.paths.license_path) == good_before and not guard.is_read_only()  # untouched
    new_key = license_issuer.issue(keypair[0], machine=machine_id, buyer="B", expires="2098-01-01")
    with qtbot.waitSignal(s.read_only_changed):
        state = s.activate(new_key)
    assert state.status == "active" and lic.load_key(s.paths.license_path) == new_key
    assert s.license.expires == "2098-01-01"


def test_expired_license_is_read_only(make_session):
    s = make_session()
    from retail import license as lic
    state = lic.apply_license(s.paths.license_path, s.public_key, s.machine_id, date(2100, 1, 1))
    s.license = state
    assert s.read_only is True


def test_close_closes_the_connection(make_session):
    s = make_session()
    s.close()
    with pytest.raises(Exception):
        s.conn.execute("SELECT 1")
```
`tests/ui/test_ui_fonts.py`:
```python
import pytest

from retail_ui import fonts


@pytest.mark.parametrize("code,available,expected", [
    ("hi", {"Nirmala UI", "Segoe UI"}, "Nirmala UI"),
    ("te", {"Nirmala UI", "Segoe UI"}, "Nirmala UI"),
    ("hi", {"Noto Sans Devanagari"}, "Noto Sans Devanagari"),
    ("te", {"Gautami"}, "Gautami"),
    ("hi", {"Arial"}, ""),
    ("en", {"Segoe UI", "Nirmala UI"}, "Segoe UI"),
    ("en", {"Arial"}, ""),
])
def test_choose_family(code, available, expected):
    assert fonts.choose_family(code, available) == expected


def test_apply_language_font_sets_the_application_font(qtbot, monkeypatch):
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(QFontDatabase, "families", staticmethod(lambda *a: ["Nirmala UI", "Segoe UI"]))
    app = QApplication.instance()
    original = app.font()
    try:
        assert fonts.apply_language_font(app, "te") == "Nirmala UI" and app.font().family() == "Nirmala UI"
        assert fonts.apply_language_font(app, "en") == "Segoe UI"
    finally:
        app.setFont(original)
```

`tests/ui/test_ui_bootstrap.py`:
```python
import pytest

from retail import guard, i18n, license as lic
from retail.services import shop
from retail_ui import bootstrap
from tools import license_issuer


def onboard(name="Boot Shop", language="en"):
    def run(session):
        shop.setup_shop(session.conn, name=name, state_code="36", language=language)
        return True
    return run


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def valid_key(keypair, machine_id, expires="2099-12-31"):
    return license_issuer.issue(keypair[0], machine=machine_id, buyer="B", expires=expires)


def boot(paths, keypair, machine_id, **kwargs):
    kwargs.setdefault("run_onboarding", onboard())
    return bootstrap.bootstrap(paths, public_key=keypair[1], machine_id=machine_id, **kwargs)


def test_first_run_asks_for_a_key_then_onboards(paths, keypair, machine_id):
    asked = []

    def request(mid, invalid):
        asked.append((mid, invalid))
        return valid_key(keypair, machine_id)

    session = boot(paths, keypair, machine_id, request_activation=request)
    try:
        assert asked == [(machine_id, False)]
        assert session.has_shop() and session.shop()["name"] == "Boot Shop" and session.license.status == "active"
        assert lic.load_key(paths.license_path) is not None and not guard.is_read_only()
    finally:
        session.close()


def test_invalid_key_is_asked_again_and_a_bad_key_is_never_saved(paths, keypair, machine_id):
    answers = iter(["garbage", valid_key(keypair, machine_id)])
    flags = []

    def request(mid, invalid):
        flags.append(invalid)
        return next(answers)

    session = boot(paths, keypair, machine_id, request_activation=request)
    try:
        assert flags == [False, True] and session.license.status == "active"
    finally:
        session.close()


def test_quitting_at_activation_returns_none_and_saves_nothing(paths, keypair, machine_id):
    assert boot(paths, keypair, machine_id, request_activation=lambda m, i: None) is None
    assert lic.load_key(paths.license_path) is None


def test_existing_valid_licence_and_shop_skip_both_dialogs(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    first = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("no prompt"))
    first.close()
    second = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("no prompt"),
                  run_onboarding=lambda s: pytest.fail("already set up"))
    try:
        assert second.shop()["name"] == "Boot Shop"
    finally:
        second.close()


def test_expired_licence_opens_read_only(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("x")).close()
    from datetime import date
    session = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("x"),
                   today=date(2100, 1, 1))
    try:
        assert session.read_only and guard.is_read_only() and session.license.status == "expired"
    finally:
        session.close()


def test_cancelled_onboarding_returns_none(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    assert boot(paths, keypair, machine_id, request_activation=lambda m, i: None,
                run_onboarding=lambda s: False) is None


def test_expired_licence_with_no_shop_cannot_be_used(paths, keypair, machine_id):
    from datetime import date
    lic.save_key(paths.license_path, valid_key(keypair, machine_id, expires="2099-12-31"))
    assert boot(paths, keypair, machine_id, request_activation=lambda m, i: None,
                today=date(2100, 1, 1)) is None


def test_language_from_the_shop_is_applied(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    session = boot(paths, keypair, machine_id, request_activation=lambda m, i: None,
                   run_onboarding=onboard(language="te"))
    try:
        assert i18n.get_language() == "te"
    finally:
        session.close()
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_session.py tests/ui/test_ui_bootstrap.py tests/ui/test_ui_fonts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.session'`.

- [ ] **Step 4: Implement**

`retail_ui/session.py`:
```python
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from retail import clock, db, guard, i18n
from retail import license as lic
from retail.services import backup, shop
from retail_ui import settings as ui_settings

log = logging.getLogger("retail_ui")


class AppSession(QObject):
    """Owns the shop connection, licence state and the signals screens listen to."""

    language_changed = Signal(str)
    read_only_changed = Signal(bool)
    data_changed = Signal()

    def __init__(self, paths, settings, conn, license_state, *, public_key, machine_id):
        super().__init__()
        self.paths = paths
        self.settings = settings
        self.conn = conn
        self.license = license_state
        self.public_key = public_key
        self.machine_id = machine_id

    # --- state -------------------------------------------------------------
    @property
    def read_only(self) -> bool:
        return self.license.read_only

    @property
    def backup_dir(self) -> Path:
        return Path(self.settings.backup_dir) if self.settings.backup_dir else self.paths.backup_dir

    def has_shop(self) -> bool:
        return self.conn.execute("SELECT 1 FROM shop WHERE id = 1").fetchone() is not None

    def shop(self):
        return shop.get_shop(self.conn)

    # --- settings / language ---------------------------------------------------
    def save_settings(self) -> None:
        ui_settings.save(self.paths.settings_path, self.settings)

    def set_language(self, code: str) -> None:
        shop.update_shop(self.conn, language=code)  # validates the code and persists it
        i18n.set_language(code)
        self.language_changed.emit(code)

    def notify_changed(self) -> None:
        self.data_changed.emit()

    # --- licence ---------------------------------------------------------------
    def refresh_license(self) -> None:
        self.license = lic.apply_license(self.paths.license_path, self.public_key, self.machine_id)
        self.read_only_changed.emit(self.license.read_only)

    def activate(self, key: str):
        """Verify first; only a valid key is saved. An invalid key changes nothing."""
        state = lic.verify_key(key, self.machine_id, self.public_key, clock.today())
        if state.status == "invalid":
            return state
        lic.save_key(self.paths.license_path, key)
        self.refresh_license()
        return self.license

    # --- backup / restore ------------------------------------------------------
    def _extra_dir(self):
        return Path(self.settings.extra_backup_dir) if self.settings.extra_backup_dir else None

    def backup_now(self):
        return backup.backup_now(self.conn, self.backup_dir, extra_dir=self._extra_dir())

    def backup_if_due(self) -> None:
        """Daily backup; a failure is logged and never blocks the caller (e.g. closing the app)."""
        try:
            if backup.daily_backup_due(self.backup_dir, clock.today()):
                self.backup_now()
        except Exception:
            log.exception("daily backup failed")

    def restore_from(self, path):
        """Replace the live database with a backup. The connection is closed for the swap and always
        reopened, so after a failed restore the app keeps running on the old data."""
        self.conn.close()
        try:
            return backup.restore(path, self.paths.db_path, self.backup_dir, max_version=db.latest_version())
        finally:
            self.conn = db.open_shop(self.paths.db_path, self.backup_dir)
            guard.set_read_only(self.license.read_only)
            self.data_changed.emit()

    def close(self) -> None:
        self.conn.close()
```
(`restore_from` emits `data_changed` in `finally`, so screens refresh after both success and failure; the failing-restore test only needs the connection to be usable.)

`retail_ui/fonts.py`:
```python
import logging

from PySide6.QtGui import QFontDatabase

log = logging.getLogger("retail_ui")

_INDIC = {
    "hi": ("Nirmala UI", "Noto Sans Devanagari", "Mangal"),
    "te": ("Nirmala UI", "Noto Sans Telugu", "Gautami"),
}
_LATIN = ("Segoe UI",)


def choose_family(code, available):
    """First installed family that can draw the language; '' keeps Qt's default."""
    for family in _INDIC.get(code, _LATIN):
        if family in available:
            return family
    return ""


def apply_language_font(app, code):
    family = choose_family(code, set(QFontDatabase.families()))
    if not family and code in _INDIC:
        log.warning("no Devanagari/Telugu-capable font found for %s; text may not render", code)
    font = app.font()
    if family:
        font.setFamily(family)
    font.setPointSize(10)
    app.setFont(font)
    return family
```

`retail_ui/bootstrap.py`:
```python
import logging

from retail import clock, db, i18n
from retail import license as lic
from retail_ui import settings as ui_settings
from retail_ui.session import AppSession

log = logging.getLogger("retail_ui")


def bootstrap(paths, *, public_key, machine_id, request_activation, run_onboarding, today=None):
    """Open the shop database, make sure the licence is usable and the shop is set up.

    request_activation(machine_id, invalid) -> key text, or None to quit.
    run_onboarding(session) -> True when the shop was set up.
    Returns the AppSession, or None when the user quit or the app cannot be used."""
    paths.ensure()
    settings = ui_settings.load(paths.settings_path)
    backup_dir = settings.backup_dir or paths.backup_dir
    conn = db.open_shop(paths.db_path, backup_dir)
    try:
        state = lic.apply_license(paths.license_path, public_key, machine_id, today)
        invalid = False
        while state.status == "invalid":
            key = request_activation(machine_id, invalid)
            if key is None:
                conn.close()
                return None
            candidate = lic.verify_key(key, machine_id, public_key, today or clock.today())
            if candidate.status == "invalid":
                invalid = True
                continue
            lic.save_key(paths.license_path, key)
            state = lic.apply_license(paths.license_path, public_key, machine_id, today)
        session = AppSession(paths, settings, conn, state, public_key=public_key, machine_id=machine_id)
        if not session.has_shop():
            if state.read_only or not run_onboarding(session):
                session.close()
                return None
        i18n.set_language(session.shop()["language"])
        return session
    except BaseException:
        try:
            conn.close()
        except Exception:
            pass
        raise
```
(`conn.close()` on an already-closed sqlite connection is a no-op, so the `except` cleanup is safe even after the explicit closes above.)

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui -v` then the full suite with `-W error::ResourceWarning`.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add AppSession, per-language fonts and the activation/onboarding boot flow" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Activation dialog

**Files:**
- Create: `retail_ui/dialogs/__init__.py` (empty), `retail_ui/dialogs/activation.py`, `retail_ui/widgets/__init__.py` (empty), `retail_ui/widgets/helpers.py`, `tests/ui/test_ui_activation.py`
- Modify: `retail/locales/*.json` (via `tools.locale_add`)

**Interfaces:**
- Consumes: `vendor.whatsapp_request_url/email_request_url`, `i18n.tr`.
- Produces: `helpers.ok_cancel(dialog, ok_key="common.ok", cancel_key="common.cancel") -> (QDialogButtonBox, QPushButton)` (translated, wired to `accept`/`reject`); `ActivationDialog(machine_id, invalid=False, parent=None)` with widgets `machine_edit, copy_button, whatsapp_button, email_button, invalid_label, key_edit, activate_button` and `key() -> str`; `activation.request_activation(machine_id, invalid) -> str | None` (the callable `bootstrap.bootstrap` expects).

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_activation.py`:
```python
import pytest
from PySide6.QtGui import QDesktopServices, QGuiApplication

from retail import i18n
from retail_ui import vendor
from retail_ui.dialogs.activation import ActivationDialog

MID = "RTL-AAAA-BBBB-CCCC-DDDD"


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def test_shows_machine_id_and_disables_activate_until_a_key_is_typed(qtbot):
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    assert d.machine_edit.text() == MID and d.machine_edit.isReadOnly()
    assert not d.activate_button.isEnabled()
    d.key_edit.setPlainText("   ")
    assert not d.activate_button.isEnabled()
    d.key_edit.setPlainText("  abc.def \n")
    assert d.activate_button.isEnabled() and d.key() == "abc.def"


def test_copy_button_copies_the_machine_id(qtbot):
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    d.copy_button.click()
    assert QGuiApplication.clipboard().text() == MID


def test_request_buttons_open_the_vendor_urls(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    d.whatsapp_button.click()
    assert opened and opened[0].startswith("https://wa.me/919866079246?text=")
    assert d.email_button.isHidden() == (vendor.VENDOR_EMAIL == "")


def test_invalid_notice_is_only_shown_after_a_bad_key(qtbot):
    ok = ActivationDialog(MID)
    bad = ActivationDialog(MID, invalid=True)
    qtbot.addWidget(ok)
    qtbot.addWidget(bad)
    assert ok.invalid_label.isHidden() and not bad.invalid_label.isHidden()
    assert bad.invalid_label.text() == i18n.tr("act.invalid")


@pytest.mark.parametrize("code", ["hi", "te"])
def test_dialog_is_translated(qtbot, code):
    i18n.set_language(code)
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    assert d.activate_button.text() == i18n.tr("act.activate") != "Activate"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_activation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.dialogs'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task6.json`:
```json
{
  "act.title": {"en": "Activate", "hi": "सक्रिय करें", "te": "యాక్టివేట్ చేయండి"},
  "act.intro": {"en": "Send this machine ID to get your license key, then paste the key below.", "hi": "लाइसेंस कुंजी पाने के लिए यह मशीन आईडी हमें भेजें, फिर नीचे कुंजी चिपकाएँ।", "te": "లైసెన్స్ కీ పొందడానికి ఈ మెషిన్ ఐడిని మాకు పంపండి, తర్వాత కీని క్రింద అతికించండి."},
  "act.machine_id": {"en": "Machine ID", "hi": "मशीन आईडी", "te": "మెషిన్ ఐడి"},
  "act.copy": {"en": "Copy", "hi": "कॉपी करें", "te": "కాపీ చేయండి"},
  "act.request_email": {"en": "Request by email", "hi": "ईमेल से माँगें", "te": "ఈమెయిల్ ద్వారా అడగండి"},
  "act.request_whatsapp": {"en": "Request on WhatsApp", "hi": "WhatsApp पर माँगें", "te": "WhatsApp లో అడగండి"},
  "act.key": {"en": "License key", "hi": "लाइसेंस कुंजी", "te": "లైసెన్స్ కీ"},
  "act.activate": {"en": "Activate", "hi": "सक्रिय करें", "te": "యాక్టివేట్ చేయండి"},
  "act.quit": {"en": "Quit", "hi": "बाहर निकलें", "te": "నిష్క్రమించు"},
  "act.invalid": {"en": "That key is not valid for this PC.", "hi": "यह कुंजी इस पीसी के लिए सही नहीं है।", "te": "ఈ కీ ఈ PC కి సరైనది కాదు."}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task6.json`
Expected: `added 10 key(s): …`.

- [ ] **Step 4: Implement**

`retail_ui/widgets/helpers.py`:
```python
from PySide6.QtWidgets import QDialogButtonBox, QLabel

from retail.i18n import tr


def ok_cancel(dialog, ok_key="common.ok", cancel_key="common.cancel"):
    box = QDialogButtonBox()
    ok = box.addButton(tr(ok_key), QDialogButtonBox.ButtonRole.AcceptRole)
    box.addButton(tr(cancel_key), QDialogButtonBox.ButtonRole.RejectRole)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box, ok


def error_label(text=""):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #b00020;")
    return label
```

`retail_ui/dialogs/activation.py`:
```python
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from retail.i18n import tr
from retail_ui import APP_NAME, vendor
from retail_ui.widgets.helpers import error_label


class ActivationDialog(QDialog):
    def __init__(self, machine_id, invalid=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — {tr('act.title')}")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        intro = QLabel(tr("act.intro"))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("act.machine_id")))
        self.machine_edit = QLineEdit(machine_id)
        self.machine_edit.setReadOnly(True)
        row.addWidget(self.machine_edit)
        self.copy_button = QPushButton(tr("act.copy"))
        self.copy_button.clicked.connect(lambda: QGuiApplication.clipboard().setText(machine_id))
        row.addWidget(self.copy_button)
        layout.addLayout(row)

        requests = QHBoxLayout()
        self.whatsapp_button = QPushButton(tr("act.request_whatsapp"))
        self.whatsapp_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(vendor.whatsapp_request_url(machine_id))))
        requests.addWidget(self.whatsapp_button)
        self.email_button = QPushButton(tr("act.request_email"))
        email_url = vendor.email_request_url(machine_id)
        self.email_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(email_url)))
        self.email_button.setHidden(email_url is None)
        requests.addWidget(self.email_button)
        layout.addLayout(requests)

        layout.addWidget(QLabel(tr("act.key")))
        self.key_edit = QPlainTextEdit()
        self.key_edit.setFixedHeight(90)
        layout.addWidget(self.key_edit)
        self.invalid_label = error_label(tr("act.invalid"))
        self.invalid_label.setHidden(not invalid)
        layout.addWidget(self.invalid_label)

        buttons = QDialogButtonBox()
        self.activate_button = buttons.addButton(tr("act.activate"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("act.quit"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.activate_button.setEnabled(False)
        self.key_edit.textChanged.connect(lambda: self.activate_button.setEnabled(bool(self.key())))

    def key(self):
        return self.key_edit.toPlainText().strip()


def request_activation(machine_id, invalid):
    """The callable bootstrap.bootstrap() expects: a key, or None when the user quits."""
    dialog = ActivationDialog(machine_id, invalid)
    return dialog.key() if dialog.exec() == QDialog.DialogCode.Accepted else None
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_activation.py tests/test_i18n.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the licence activation dialog" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Onboarding wizard

**Files:**
- Create: `retail_ui/dialogs/onboarding.py`, `tests/ui/test_ui_onboarding.py`
- Modify: `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `shop.setup_shop`, `segments.list_templates/apply_template`, `session.save_settings/set_language/settings`, `states.STATES`, `validators.gstin_error`, `errors.show_error`, `i18n.LANGUAGES`.
- Produces: `onboarding.OnboardingData` (dataclass: `name, state_code="36", gstin="", address="", template="grocery", gst_enabled=True, price_includes_gst=True, oversell_policy="warn", language="en", backup_dir="", extra_backup_dir=""`); `onboarding.apply_onboarding(session, data) -> None` (validates GSTIN, template and backup folders **before** any database write); `OnboardingWizard(session, parent=None)` with pages `language_page, shop_page, segment_page, billing_page, backup_page` and `collect() -> OnboardingData`; `onboarding.run_onboarding(session) -> bool` (the callable `bootstrap.bootstrap` expects). The first page chooses the language and applies it when the user presses Next, so every later page is built (lazily) in that language.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_onboarding.py`:
```python
import pytest

from retail import i18n, segments
from retail.services import shop
from retail_ui.dialogs import onboarding
from retail_ui.dialogs.onboarding import OnboardingData, OnboardingWizard, apply_onboarding


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def data(**kw):
    base = dict(name="Sri Kirana", state_code="36", gstin="36ABCDE1234F1Z5", address="Main Road",
                template="electronics", gst_enabled=True, price_includes_gst=False,
                oversell_policy="block", language="te")
    base.update(kw)
    return OnboardingData(**base)


def test_apply_onboarding_sets_up_shop_template_settings_and_language(make_session, tmp_path):
    s = make_session(with_shop=False)
    apply_onboarding(s, data(backup_dir=str(tmp_path / "bk"), extra_backup_dir=str(tmp_path / "usb")))
    row = s.shop()
    assert (row["name"], row["gstin"], row["template"], row["language"]) == ("Sri Kirana", "36ABCDE1234F1Z5", "electronics", "te")
    assert (row["price_includes_gst"], row["oversell_policy"]) == (0, "block")
    assert segments.feature_enabled(s.conn, "serial") is True
    assert s.settings.backup_dir == str(tmp_path / "bk") and (tmp_path / "bk").is_dir() and (tmp_path / "usb").is_dir()
    assert i18n.get_language() == "te"


def test_gstin_is_normalised_and_blank_gstin_is_stored_as_none(make_session):
    s = make_session(with_shop=False)
    apply_onboarding(s, data(gstin="36abcde1234f1z5", language="en"))
    assert s.shop()["gstin"] == "36ABCDE1234F1Z5"
    s2 = make_session(with_shop=False)  # same db: re-setup replaces the row
    apply_onboarding(s2, data(gstin="  ", language="en"))
    assert s2.shop()["gstin"] is None


@pytest.mark.parametrize("bad", [
    {"gstin": "123"}, {"gstin": "27ABCDE1234F1Z5"}, {"template": "pharmacy"}, {"name": " "},
    {"state_code": "ABC"},
])
def test_invalid_data_is_rejected_before_anything_is_written(make_session, bad):
    s = make_session(with_shop=False)
    with pytest.raises(shop.ShopError):
        apply_onboarding(s, data(**bad))
    assert s.has_shop() is False and s.settings.backup_dir == ""


def test_unwritable_backup_folder_is_rejected_before_any_write(make_session, tmp_path):
    s = make_session(with_shop=False)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OSError):
        apply_onboarding(s, data(backup_dir=str(blocker / "sub")))
    assert s.has_shop() is False


def test_wizard_collects_values_from_its_pages(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    for page_id in w.pageIds():
        w.page(page_id).initializePage()
    w.language_page.combo.setCurrentIndex(w.language_page.combo.findData("hi"))
    w.shop_page.name.setText("  Raju Stores ")
    w.shop_page.state.setCurrentIndex(w.shop_page.state.findData("27"))
    w.shop_page.gstin.setText("27ABCDE1234F1Z5")
    w.shop_page.address.setText("Pune")
    w.segment_page.select("electronics")
    w.billing_page.gst_enabled.setChecked(False)
    w.billing_page.prices_incl.setChecked(False)
    w.billing_page.oversell.setCurrentIndex(w.billing_page.oversell.findData("allow"))
    w.backup_page.backup_dir.setText("D:/bk")
    w.backup_page.extra_dir.setText("E:/usb")
    got = w.collect()
    assert got == OnboardingData(name="Raju Stores", state_code="27", gstin="27ABCDE1234F1Z5", address="Pune",
                                 template="electronics", gst_enabled=False, price_includes_gst=False,
                                 oversell_policy="allow", language="hi", backup_dir="D:/bk", extra_backup_dir="E:/usb")


def test_shop_page_needs_a_name_and_a_matching_gstin(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    page = w.shop_page
    page.initializePage()
    assert not page.isComplete()
    page.name.setText("Shop")
    assert page.isComplete()
    page.gstin.setText("27ABCDE1234F1Z5")   # state is 36 -> mismatch
    assert not page.isComplete() and page.error.text() == i18n.tr("ob.invalid_gstin")
    page.state.setCurrentIndex(page.state.findData("27"))
    assert page.isComplete() and page.error.text() == ""


def test_language_page_applies_the_language_when_leaving_it(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    w.language_page.initializePage()
    w.language_page.combo.setCurrentIndex(w.language_page.combo.findData("te"))
    assert w.language_page.validatePage() is True and i18n.get_language() == "te"
    w.shop_page.initializePage()
    assert w.shop_page.title() == i18n.tr("ob.shop_page")           # built in Telugu


def test_accept_applies_and_a_failure_keeps_the_wizard_open(make_session, qtbot, monkeypatch):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    for page_id in w.pageIds():
        w.page(page_id).initializePage()
    shown = []
    monkeypatch.setattr(onboarding, "show_error", lambda parent, exc: shown.append(exc))
    w.shop_page.name.setText("")
    w.accept()
    assert len(shown) == 1 and not s.has_shop() and w.result() == 0
    w.shop_page.name.setText("Good Shop")
    w.accept()
    assert s.has_shop() and w.result() == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_onboarding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.dialogs.onboarding'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task7.json`:
```json
{
  "ob.title": {"en": "Set up your shop", "hi": "अपनी दुकान सेट करें", "te": "మీ దుకాణాన్ని సెటప్ చేయండి"},
  "ob.shop_page": {"en": "Shop details", "hi": "दुकान की जानकारी", "te": "దుకాణం వివరాలు"},
  "ob.shop_name": {"en": "Shop name", "hi": "दुकान का नाम", "te": "దుకాణం పేరు"},
  "ob.state": {"en": "State", "hi": "राज्य", "te": "రాష్ట్రం"},
  "ob.gstin": {"en": "GSTIN (leave blank if none)", "hi": "GSTIN (न हो तो खाली छोड़ें)", "te": "GSTIN (లేకపోతే ఖాళీగా వదలండి)"},
  "ob.address": {"en": "Address", "hi": "पता", "te": "చిరునామా"},
  "ob.segment_page": {"en": "What do you sell?", "hi": "आप क्या बेचते हैं?", "te": "మీరు ఏమి అమ్ముతారు?"},
  "ob.gst_page": {"en": "Billing", "hi": "बिलिंग", "te": "బిల్లింగ్"},
  "ob.gst_enabled": {"en": "Issue GST invoices (untick for simple estimate bills)", "hi": "GST इनवॉइस बनाएँ (सादे अनुमान बिल के लिए हटाएँ)", "te": "GST ఇన్వాయిస్‌లు ఇవ్వండి (సాధారణ అంచనా బిల్లుల కోసం తీసివేయండి)"},
  "ob.prices_incl": {"en": "Selling prices already include GST (MRP)", "hi": "बिक्री मूल्य में GST पहले से शामिल है (MRP)", "te": "అమ్మకం ధరలో GST ఇప్పటికే కలిసి ఉంది (MRP)"},
  "ob.oversell": {"en": "When stock is short", "hi": "जब स्टॉक कम हो", "te": "స్టాక్ తక్కువగా ఉన్నప్పుడు"},
  "ob.oversell_block": {"en": "Block the sale", "hi": "बिक्री रोकें", "te": "అమ్మకాన్ని ఆపండి"},
  "ob.oversell_warn": {"en": "Warn but allow", "hi": "चेतावनी दें पर बिक्री होने दें", "te": "హెచ్చరించి అమ్మనివ్వండి"},
  "ob.oversell_allow": {"en": "Allow silently", "hi": "चुपचाप बिक्री होने दें", "te": "నిశ్శబ్దంగా అమ్మనివ్వండి"},
  "ob.backup_page": {"en": "Protect your data", "hi": "अपने डेटा की सुरक्षा", "te": "మీ డేటా రక్షణ"},
  "ob.backup_dir": {"en": "Backup folder (blank = default)", "hi": "बैकअप फ़ोल्डर (खाली = डिफ़ॉल्ट)", "te": "బ్యాకప్ ఫోల్డర్ (ఖాళీ = డిఫాల్ట్)"},
  "ob.extra_dir": {"en": "Second copy folder (USB drive or synced folder, recommended)", "hi": "दूसरी कॉपी का फ़ोल्डर (USB ड्राइव या सिंक फ़ोल्डर, सुझावित)", "te": "రెండో కాపీ ఫోల్డర్ (USB డ్రైవ్ లేదా సింక్ ఫోల్డర్, సిఫార్సు)"},
  "ob.backup_hint": {"en": "Your data is backed up automatically every day when you close the app. A second copy on another drive protects you if this PC fails.", "hi": "ऐप बंद करते समय आपका डेटा हर दिन अपने-आप बैकअप होता है। दूसरे ड्राइव पर दूसरी कॉपी इस पीसी के खराब होने पर बचाती है।", "te": "యాప్ మూసినప్పుడు మీ డేటా ప్రతిరోజూ ఆటోమేటిక్‌గా బ్యాకప్ అవుతుంది. మరో డ్రైవ్‌లో రెండో కాపీ ఈ PC చెడిపోతే మిమ్మల్ని కాపాడుతుంది."},
  "ob.invalid_gstin": {"en": "That GSTIN is not valid for the selected state.", "hi": "चुने गए राज्य के लिए यह GSTIN सही नहीं है।", "te": "ఎంచుకున్న రాష్ట్రానికి ఈ GSTIN సరైనది కాదు."},
  "tpl.grocery": {"en": "Grocery / Kirana / General store", "hi": "किराना / जनरल स्टोर", "te": "కిరాణా / జనరల్ స్టోర్"},
  "tpl.electronics": {"en": "Electronics / Mobile / Appliances", "hi": "इलेक्ट्रॉनिक्स / मोबाइल / उपकरण", "te": "ఎలక్ట్రానిక్స్ / మొబైల్ / ఉపకరణాలు"},
  "wiz.next": {"en": "Next >", "hi": "आगे >", "te": "తర్వాత >"},
  "wiz.back": {"en": "< Back", "hi": "< पीछे", "te": "< వెనుకకు"},
  "wiz.finish": {"en": "Finish", "hi": "पूरा करें", "te": "పూర్తి చేయండి"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task7.json`
Expected: `added 23 key(s): …`.

- [ ] **Step 4: Implement**

`retail_ui/dialogs/onboarding.py`:
```python
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout,
                               QWidget, QWizard, QWizardPage)

from retail import i18n, segments
from retail.i18n import tr
from retail.services import shop
from retail_ui import APP_NAME, states, validators
from retail_ui.errors import show_error
from retail_ui.widgets.helpers import error_label


@dataclass
class OnboardingData:
    name: str = ""
    state_code: str = "36"
    gstin: str = ""
    address: str = ""
    template: str = "grocery"
    gst_enabled: bool = True
    price_includes_gst: bool = True
    oversell_policy: str = "warn"
    language: str = "en"
    backup_dir: str = ""
    extra_backup_dir: str = ""


def apply_onboarding(session, data: OnboardingData) -> None:
    """Validate everything first, then write; nothing is written if anything is wrong."""
    if validators.gstin_error(data.gstin, data.state_code):
        raise shop.ShopError("Invalid GSTIN for the selected state")
    if data.template not in segments.list_templates():
        raise shop.ShopError(f"Unknown template {data.template!r}")
    if not (data.name or "").strip():
        raise shop.ShopError("Shop name is required")
    for folder in (data.backup_dir, data.extra_backup_dir):
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)  # OSError here: nothing written yet
    shop.setup_shop(session.conn, name=data.name, state_code=data.state_code,
                    gstin=(data.gstin.strip().upper() or None), address=data.address,
                    template=data.template, gst_enabled=data.gst_enabled,
                    price_includes_gst=data.price_includes_gst, oversell_policy=data.oversell_policy,
                    language=data.language)
    segments.apply_template(session.conn, data.template)
    session.settings.backup_dir = data.backup_dir
    session.settings.extra_backup_dir = data.extra_backup_dir
    session.save_settings()
    session.set_language(data.language)


class _Page(QWizardPage):
    """Pages build their widgets lazily in initializePage so they are created in the language the
    user picked on the first page."""
    title_key = ""

    def __init__(self):
        super().__init__()
        self._built = False

    def initializePage(self):
        if not self._built:
            self.build()
            self._built = True
        if self.title_key:
            self.setTitle(tr(self.title_key))

    def build(self):
        raise NotImplementedError


class LanguagePage(_Page):
    def build(self):
        self.setTitle("Language / भाषा / భాష")
        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.combo.addItem(name, code)
        self.combo.setCurrentIndex(self.combo.findData(i18n.get_language()))
        layout.addWidget(self.combo)

    def initializePage(self):
        super().initializePage()
        self.setTitle("Language / भाषा / భాష")

    def validatePage(self):
        i18n.set_language(self.combo.currentData())
        return True


class ShopPage(_Page):
    title_key = "ob.shop_page"

    def build(self):
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.state = QComboBox()
        for code, name in states.STATES.items():
            self.state.addItem(f"{code} — {name}", code)
        self.state.setCurrentIndex(self.state.findData("36"))
        self.gstin = QLineEdit()
        self.address = QLineEdit()
        self.error = error_label()
        form.addRow(tr("ob.shop_name"), self.name)
        form.addRow(tr("ob.state"), self.state)
        form.addRow(tr("ob.gstin"), self.gstin)
        form.addRow(tr("ob.address"), self.address)
        form.addRow(self.error)
        for signal in (self.name.textChanged, self.gstin.textChanged, self.state.currentIndexChanged):
            signal.connect(lambda *_: self.completeChanged.emit())

    def isComplete(self):
        if not self._built:
            return False
        bad = validators.gstin_error(self.gstin.text(), self.state.currentData())
        self.error.setText(tr("ob.invalid_gstin") if bad else "")
        return bool(self.name.text().strip()) and bad is None


class SegmentPage(_Page):
    title_key = "ob.segment_page"

    def build(self):
        layout = QVBoxLayout(self)
        self.group = QButtonGroup(self)
        self._radios = {}
        for name in segments.list_templates():
            radio = QRadioButton(tr(f"tpl.{name}"))
            self.group.addButton(radio)
            self._radios[name] = radio
            layout.addWidget(radio)
        self.select(segments.list_templates()[0] if "grocery" not in self._radios else "grocery")

    def select(self, name):
        self._radios[name].setChecked(True)

    def selected(self):
        return next(name for name, radio in self._radios.items() if radio.isChecked())


class BillingPage(_Page):
    title_key = "ob.gst_page"

    def build(self):
        form = QFormLayout(self)
        self.gst_enabled = QCheckBox(tr("ob.gst_enabled"))
        self.gst_enabled.setChecked(True)
        self.prices_incl = QCheckBox(tr("ob.prices_incl"))
        self.prices_incl.setChecked(True)
        self.oversell = QComboBox()
        for code in ("block", "warn", "allow"):
            self.oversell.addItem(tr(f"ob.oversell_{code}"), code)
        self.oversell.setCurrentIndex(self.oversell.findData("warn"))
        form.addRow(self.gst_enabled)
        form.addRow(self.prices_incl)
        form.addRow(tr("ob.oversell"), self.oversell)


class BackupPage(_Page):
    title_key = "ob.backup_page"

    def build(self):
        layout = QVBoxLayout(self)
        hint = QLabel(tr("ob.backup_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.backup_dir = QLineEdit()
        self.extra_dir = QLineEdit()
        for label_key, edit in (("ob.backup_dir", self.backup_dir), ("ob.extra_dir", self.extra_dir)):
            layout.addWidget(QLabel(tr(label_key)))
            row = QHBoxLayout()
            row.addWidget(edit)
            browse = QPushButton(tr("common.browse"))
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            row.addWidget(browse)
            container = QWidget()
            container.setLayout(row)
            layout.addWidget(container)

    def _browse(self, edit):
        folder = QFileDialog.getExistingDirectory(self, tr("common.browse"), edit.text())
        if folder:
            edit.setText(folder)


class OnboardingWizard(QWizard):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(f"{APP_NAME}")
        self.language_page, self.shop_page = LanguagePage(), ShopPage()
        self.segment_page, self.billing_page, self.backup_page = SegmentPage(), BillingPage(), BackupPage()
        for page in (self.language_page, self.shop_page, self.segment_page, self.billing_page, self.backup_page):
            self.addPage(page)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

    def initializePage(self, page_id):
        super().initializePage(page_id)
        self.setButtonText(QWizard.WizardButton.NextButton, tr("wiz.next"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("wiz.back"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("wiz.finish"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("common.cancel"))

    def collect(self) -> OnboardingData:
        return OnboardingData(
            name=self.shop_page.name.text().strip(),
            state_code=self.shop_page.state.currentData(),
            gstin=self.shop_page.gstin.text().strip(),
            address=self.shop_page.address.text().strip(),
            template=self.segment_page.selected(),
            gst_enabled=self.billing_page.gst_enabled.isChecked(),
            price_includes_gst=self.billing_page.prices_incl.isChecked(),
            oversell_policy=self.billing_page.oversell.currentData(),
            language=self.language_page.combo.currentData(),
            backup_dir=self.backup_page.backup_dir.text().strip(),
            extra_backup_dir=self.backup_page.extra_dir.text().strip(),
        )

    def accept(self):
        try:
            apply_onboarding(self.session, self.collect())
        except Exception as exc:
            show_error(self, exc)
            return
        super().accept()


def run_onboarding(session) -> bool:
    """The callable bootstrap.bootstrap() expects."""
    return OnboardingWizard(session).exec() == QDialog.DialogCode.Accepted
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_onboarding.py tests/test_i18n.py -v`
Expected: all PASS. (If `QWizard.initializePage` signature differs in the installed PySide6, keep the override but adapt the argument list; the behaviour under test is unchanged.)

```bash
git add -A
git commit -m "feat: add the onboarding wizard (language, shop, segment, billing, backup)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Main window shell, base widgets and the screen registry

**Files:**
- Create: `retail_ui/widgets/base.py`, `retail_ui/main_window.py`, `retail_ui/screens/__init__.py` (empty), `retail_ui/screens/registry.py`, `tests/ui/test_ui_main_window.py`
- Modify: `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `AppSession` signals, `fonts.apply_language_font`, `errors.show_error`, `fmt.date_text`.
- Produces:
  - `base.Screen(session, parent=None)` — `QWidget` with class attribute `nav_key`; methods `bind(widget, key, setter="setText", suffix="") -> widget` (sets the translated text now and again on `retranslate()`), `track(model) -> model`, `retranslate()`, `refresh()`, `apply_read_only(read_only: bool)` (the last three are overridden by screens).
  - `base.RowsModel(header_keys, parent=None)` — `QAbstractTableModel` of pre-formatted strings: `set_rows(rows, ids=None, right_cols=(), highlight=())`, `id_at(row) -> Any`, `retranslate()`; headers are translated from `header_keys`.
  - `main_window.MainWindow(session, screen_classes, parent=None)` with `nav` (QListWidget), `stack`, `banner`, `language_box`, `screens`; closing takes the daily backup (a failure never blocks closing).
  - `registry.all_screens() -> list[type[Screen]]` (empty in this task; every later screen task appends its class here).

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_main_window.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import i18n, license as lic
from retail.services import backup
from retail_ui.main_window import MainWindow
from retail_ui.widgets.base import RowsModel, Screen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        from PySide6.QtGui import QFont
        app.setFont(QFont())


class ScreenA(Screen):
    nav_key = "nav.counter"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.refreshed = self.retranslated = 0
        self.read_only_calls = []

    def refresh(self):
        self.refreshed += 1

    def retranslate(self):
        super().retranslate()
        self.retranslated += 1

    def apply_read_only(self, read_only):
        self.read_only_calls.append(read_only)


class ScreenB(ScreenA):
    nav_key = "nav.items"


def make_window(make_session, qtbot):
    session = make_session()
    window = MainWindow(session, [ScreenA, ScreenB])
    qtbot.addWidget(window)
    return session, window


def test_navigation_lists_translated_screens_and_refreshes_on_switch(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    assert [w.nav.item(i).text() for i in range(w.nav.count())] == [i18n.tr("nav.counter"), i18n.tr("nav.items")]
    first = w.screens[0].refreshed
    w.nav.setCurrentRow(1)
    assert w.stack.currentIndex() == 1 and w.screens[1].refreshed >= 1 and w.screens[0].refreshed == first


def test_data_changed_refreshes_the_visible_screen_only(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    w.nav.setCurrentRow(1)
    a, b = w.screens[0].refreshed, w.screens[1].refreshed
    session.notify_changed()
    assert w.screens[1].refreshed == b + 1 and w.screens[0].refreshed == a


def test_language_switch_retranslates_everything_and_applies_a_font(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    w.language_box.setCurrentIndex(w.language_box.findData("hi"))
    assert i18n.get_language() == "hi" and session.shop()["language"] == "hi"
    assert w.nav.item(0).text() == i18n.tr("nav.counter") != "Counter"
    assert all(s.retranslated == 1 for s in w.screens)
    assert w.status_label.text().startswith(session.shop()["name"])


def test_language_combo_follows_the_session_language(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    session.set_language("te")
    assert w.language_box.currentData() == "te"


def test_read_only_shows_a_banner_and_tells_every_screen(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    assert w.banner.isHidden()
    session.license = lic.LicenseState("expired", expires="2020-01-01")
    session.read_only_changed.emit(True)
    assert not w.banner.isHidden() and w.banner.text() == i18n.tr("license.read_only")
    assert all(s.read_only_calls[-1] is True for s in w.screens)
    session.license = lic.LicenseState("active", expires="2099-01-01")
    session.read_only_changed.emit(False)
    assert w.banner.isHidden() and all(s.read_only_calls[-1] is False for s in w.screens)


def test_window_starts_read_only_when_the_licence_is_expired(make_session, qtbot):
    session = make_session()
    session.license = lic.LicenseState("expired", expires="2020-01-01")
    w = MainWindow(session, [ScreenA])
    qtbot.addWidget(w)
    assert not w.banner.isHidden() and w.screens[0].read_only_calls == [True]


def test_closing_takes_the_daily_backup(make_session, qtbot):
    session, w = make_window(make_session, qtbot)
    assert not list(session.backup_dir.glob("daily-*.db"))
    w.close()
    assert len(list(session.backup_dir.glob("daily-*.db"))) == 1


def test_a_failing_backup_never_blocks_closing(make_session, qtbot, monkeypatch):
    session, w = make_window(make_session, qtbot)
    monkeypatch.setattr(backup, "backup_now", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    assert w.close() is True


def test_bind_retranslates_with_suffix_and_models_follow(make_session, qtbot):
    from PySide6.QtWidgets import QPushButton
    session = make_session()
    screen = ScreenA(session)
    qtbot.addWidget(screen)
    button = screen.bind(QPushButton(), "bill.pay", suffix=" (F12)")
    model = screen.track(RowsModel(["bill.item", "bill.total"]))
    assert button.text() == f"{i18n.tr('bill.pay')} (F12)"
    i18n.set_language("hi")
    screen.retranslate()
    assert button.text() == f"{i18n.tr('bill.pay')} (F12)" and button.text().startswith("भुगतान")
    assert model.headerData(1, Qt.Orientation.Horizontal) == i18n.tr("bill.total")


def test_rows_model_shape_ids_alignment_and_highlight(qtbot):
    m = RowsModel(["bill.item", "bill.total"])
    m.set_rows([("Soap", "₹10.00"), ("Rice", "₹5.00")], ids=[11, 22], right_cols=(1,), highlight=(1,))
    assert (m.rowCount(), m.columnCount()) == (2, 2)
    assert m.data(m.index(0, 0)) == "Soap" and m.id_at(1) == 22 and m.id_at(5) is None
    assert m.data(m.index(0, 1), Qt.ItemDataRole.TextAlignmentRole) & Qt.AlignmentFlag.AlignRight
    assert m.data(m.index(0, 0), Qt.ItemDataRole.BackgroundRole) is None
    assert m.data(m.index(1, 0), Qt.ItemDataRole.BackgroundRole) is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_main_window.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.main_window'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task8.json`:
```json
{
  "nav.counter": {"en": "Counter", "hi": "काउंटर", "te": "కౌంటర్"},
  "nav.items": {"en": "Items", "hi": "वस्तुएँ", "te": "వస్తువులు"},
  "nav.stock": {"en": "Stock & Purchases", "hi": "स्टॉक और खरीद", "te": "స్టాక్ & కొనుగోళ్లు"},
  "nav.parties": {"en": "Customers & Suppliers", "hi": "ग्राहक और सप्लायर", "te": "కస్టమర్లు & సప్లయర్లు"},
  "nav.bills": {"en": "Bills", "hi": "बिल", "te": "బిల్లులు"},
  "nav.reports": {"en": "Reports", "hi": "रिपोर्ट", "te": "రిపోర్టులు"},
  "nav.staff": {"en": "Staff & Expenses", "hi": "स्टाफ और खर्च", "te": "సిబ్బంది & ఖర్చులు"},
  "nav.settings": {"en": "Settings", "hi": "सेटिंग्स", "te": "సెట్టింగ్స్"},
  "status.expires": {"en": "Licensed until {date}", "hi": "लाइसेंस {date} तक", "te": "లైసెన్స్ {date} వరకు"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task8.json`

- [ ] **Step 4: Implement**

`retail_ui/widgets/base.py`:
```python
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QWidget

from retail.i18n import tr


class Screen(QWidget):
    """Base for every navigable screen. Screens never hold business rules; they call services."""

    nav_key = ""

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._bindings = []
        self._models = []

    def bind(self, widget, key, setter="setText", suffix=""):
        """Set a translated text now and again on every retranslate()."""
        self._bindings.append((widget, key, setter, suffix))
        getattr(widget, setter)(tr(key) + suffix)
        return widget

    def track(self, model):
        self._models.append(model)
        return model

    def retranslate(self):
        for widget, key, setter, suffix in self._bindings:
            getattr(widget, setter)(tr(key) + suffix)
        for model in self._models:
            model.retranslate()

    def refresh(self):
        """Reload from the database (called when shown and when data changed)."""

    def apply_read_only(self, read_only):
        """Disable write controls after the licence expires."""


class RowsModel(QAbstractTableModel):
    """A read-only table of already-formatted strings with translated headers."""

    def __init__(self, header_keys, parent=None):
        super().__init__(parent)
        self._keys = list(header_keys)
        self._rows = []
        self._ids = []
        self._right = set()
        self._highlight = set()

    def set_rows(self, rows, ids=None, right_cols=(), highlight=()):
        self.beginResetModel()
        self._rows = [tuple(r) for r in rows]
        self._ids = list(ids) if ids is not None else list(range(len(self._rows)))
        self._right = set(right_cols)
        self._highlight = set(highlight)
        self.endResetModel()

    def id_at(self, row):
        return self._ids[row] if 0 <= row < len(self._ids) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._keys)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in self._right:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and index.row() in self._highlight:
            return QBrush(QColor("#fff3cd"))
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return tr(self._keys[section])
        return None

    def retranslate(self):
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, max(len(self._keys) - 1, 0))
```

`retail_ui/screens/registry.py`:
```python
from retail_ui.widgets.base import Screen


def all_screens() -> list[type[Screen]]:
    """Navigation order. Each screen task appends its class here."""
    return []
```

`retail_ui/main_window.py`:
```python
import logging

from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QStackedWidget, QVBoxLayout, QWidget)

from retail import i18n
from retail.i18n import tr
from retail_ui import APP_NAME, __version__, fmt, fonts
from retail_ui.errors import show_error

log = logging.getLogger("retail_ui")


class MainWindow(QMainWindow):
    def __init__(self, session, screen_classes, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 760)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("background:#b00020;color:white;padding:6px;")
        outer.addWidget(self.banner)

        body = QHBoxLayout()
        side = QVBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        side.addWidget(self.nav)
        self.language_box = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_box.addItem(name, code)
        self.language_box.setCurrentIndex(self.language_box.findData(i18n.get_language()))
        side.addWidget(self.language_box)
        body.addLayout(side)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)

        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)

        self.screens = []
        for cls in screen_classes:
            screen = cls(session)
            self.screens.append(screen)
            self.stack.addWidget(screen)
            self.nav.addItem(QListWidgetItem(tr(cls.nav_key)))

        self.nav.currentRowChanged.connect(self._show_screen)
        self.language_box.currentIndexChanged.connect(self._on_language_chosen)
        session.language_changed.connect(self._on_language)
        session.read_only_changed.connect(self._on_read_only)
        session.data_changed.connect(self._on_data_changed)

        self._update_banner()
        self._update_status()
        for screen in self.screens:
            screen.apply_read_only(session.read_only)
        if self.screens:
            self.nav.setCurrentRow(0)

    # --- navigation / refresh -----------------------------------------------
    def _show_screen(self, row):
        if 0 <= row < len(self.screens):
            self.stack.setCurrentIndex(row)
            self.screens[row].refresh()

    def _on_data_changed(self):
        row = self.stack.currentIndex()
        if 0 <= row < len(self.screens):
            self.screens[row].refresh()

    # --- language ---------------------------------------------------------------
    def _on_language_chosen(self):
        code = self.language_box.currentData()
        if code == i18n.get_language():
            return
        try:
            self.session.set_language(code)
        except Exception as exc:
            show_error(self, exc)
            self._sync_language_box()

    def _sync_language_box(self):
        self.language_box.blockSignals(True)
        self.language_box.setCurrentIndex(self.language_box.findData(i18n.get_language()))
        self.language_box.blockSignals(False)

    def _on_language(self, code):
        self._sync_language_box()
        app = QApplication.instance()
        if app is not None:
            fonts.apply_language_font(app, code)
        for i, screen in enumerate(self.screens):
            self.nav.item(i).setText(tr(screen.nav_key))
            screen.retranslate()
        self._update_banner()
        self._update_status()

    # --- licence -----------------------------------------------------------------
    def _on_read_only(self, read_only):
        self._update_banner()
        self._update_status()
        for screen in self.screens:
            screen.apply_read_only(read_only)

    def _update_banner(self):
        self.banner.setText(tr("license.read_only"))
        self.banner.setHidden(not self.session.read_only)

    def _update_status(self):
        lic_state = self.session.license
        parts = [self.session.shop()["name"] if self.session.has_shop() else APP_NAME]
        if lic_state.expires:
            parts.append(tr("status.expires", date=fmt.date_text(lic_state.expires)))
        parts.append(f"v{__version__}")
        self.status_label.setText("   |   ".join(parts))

    # --- closing -----------------------------------------------------------------
    def closeEvent(self, event):
        self.session.backup_if_due()  # never raises: a backup problem must not trap the user
        event.accept()
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_main_window.py tests/test_i18n.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the main window shell, Screen base class and RowsModel" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Counter logic (Qt-free controller)

The counter's rules in plain Python: what a typed or scanned entry means, which prompt each tracking mode needs, and the hold/resume/pay lifecycle. It talks to the engine only through `holder.conn` (the `AppSession`, so a restored database is picked up automatically).

**Files:**
- Create: `retail_ui/screens/counter_logic.py`, `tests/ui/test_ui_counter_logic.py`

**Interfaces:**
- Consumes: `items.parse_entry/resolve`, `billing.*` (including `get_bill_detail`, `set_line_discount`).
- Produces:
  - `counter_logic.Entry` (frozen dataclass): `kind` in `"ignored" | "added" | "pick" | "serial" | "weight" | "new_item"`, plus `line_id, items (tuple of rows), item, qty_milli=1000, text="", explicit_qty=True`.
  - `CounterController(holder)` with `bill_id: int | None` and: `submit(text) -> Entry`; `add(item, qty_milli, *, serial=None, explicit_qty=True) -> Entry`; `detail() -> dict | None` (`billing.get_bill_detail`); `remove_line(line_id)`; `set_customer(party_id)`; `set_discount(line_id, paise)`; `held_bills() -> list[dict]` (`id, party, total_paise, lines` — non-empty held bills other than the current one); `hold() -> int | None`; `resume(bill_id)`; `discard()`; `pay(payments) -> (bill_id, bill_no)`; `has_lines() -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_counter_logic.py`:
```python
from types import SimpleNamespace

import pytest

from retail import guard
from retail.services import billing, items, parties, stock
from retail_ui.screens.counter_logic import CounterController


@pytest.fixture
def ctl(shop_conn):
    return CounterController(SimpleNamespace(conn=shop_conn))


def stocked(conn, **kw):
    kw.setdefault("sell_price_paise", 11800)
    kw.setdefault("gst_rate_bp", 1800)
    item_id = items.create_item(conn, **kw)
    stock.record(conn, item_id, 50_000, "opening")
    return item_id


def test_barcode_scan_adds_a_line(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    result = ctl.submit("8901")
    assert result.kind == "added" and result.qty_milli == 1000
    assert ctl.detail()["bill"]["total_paise"] == 11800 and ctl.has_lines()


def test_trailing_whitespace_from_a_scanner_is_ignored(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    assert ctl.submit("8901  \r\n").kind == "added"


def test_quantity_prefix(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("3*8901")
    assert ctl.detail()["lines"][0]["qty_milli"] == 3000


@pytest.mark.parametrize("text", ["", "   ", "0*soap", "0.0001*soap"])
def test_empty_and_zero_quantity_entries_are_ignored(shop_conn, ctl, text):
    stocked(shop_conn, name="Soap")
    assert ctl.submit(text).kind == "ignored"
    assert ctl.bill_id is None and billing.list_held(shop_conn) == []


def test_unknown_code_asks_for_a_new_item_and_creates_no_bill(shop_conn, ctl):
    result = ctl.submit("2*999999")
    assert (result.kind, result.text, result.qty_milli) == ("new_item", "999999", 2000)
    assert ctl.bill_id is None


def test_several_name_matches_ask_which_one(shop_conn, ctl):
    stocked(shop_conn, name="Bath soap")
    stocked(shop_conn, name="Hand soap")
    result = ctl.submit("soap")
    assert result.kind == "pick" and [r["name"] for r in result.items] == ["Bath soap", "Hand soap"]
    chosen = result.items[1]
    assert ctl.add(chosen, result.qty_milli, explicit_qty=result.explicit_qty).kind == "added"
    assert ctl.detail()["lines"][0]["item_name"] == "Hand soap"


def test_weighed_item_without_a_typed_quantity_asks_for_weight(shop_conn, ctl):
    rice = stocked(shop_conn, name="Rice", sell_price_paise=6000, gst_rate_bp=0, unit="kg", tracking="weighed")
    result = ctl.submit("rice")
    assert result.kind == "weight" and result.item["id"] == rice and ctl.bill_id is None
    assert ctl.add(result.item, 750).kind == "added"
    assert ctl.detail()["bill"]["total_paise"] == 4500


def test_weighed_item_with_a_typed_quantity_does_not_ask(shop_conn, ctl):
    stocked(shop_conn, name="Rice", sell_price_paise=6000, gst_rate_bp=0, unit="kg", tracking="weighed")
    assert ctl.submit("0.5*rice").kind == "added"


def test_serial_item_asks_for_the_serial_then_adds(shop_conn, ctl):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial")
    unit = stock.add_unit(shop_conn, phone, serial="IMEI1")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    result = ctl.submit("phone")
    assert result.kind == "serial" and result.item["id"] == phone
    added = ctl.add(result.item, 1000, serial=" imei1 ")
    assert added.kind == "added" and ctl.detail()["lines"][0]["serial"] == "IMEI1"


def test_a_failed_add_surfaces_the_engine_error_and_leaves_no_phantom_line(shop_conn, ctl):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial")
    with pytest.raises(billing.SerialUnavailable):
        ctl.add(items.get_item(shop_conn, phone), 1000, serial="NOPE")
    assert not ctl.has_lines()


def test_customer_discount_and_delete_line(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("2*8901")
    line_id = ctl.detail()["lines"][0]["id"]
    ctl.set_discount(line_id, 1800)
    assert ctl.detail()["bill"]["total_paise"] == 21800
    pune = parties.create_party(shop_conn, name="Pune Co", state_code="27")
    ctl.set_customer(pune)
    assert ctl.detail()["bill"]["igst_paise"] > 0 and ctl.detail()["party"]["name"] == "Pune Co"
    ctl.remove_line(line_id)
    assert not ctl.has_lines()


def test_hold_lists_the_bill_and_resume_brings_it_back(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    stocked(shop_conn, name="Tea", barcodes=["8902"])
    ctl.submit("8901")
    first = ctl.hold()
    assert first is not None and ctl.bill_id is None
    ctl.submit("8902")
    held = ctl.held_bills()
    assert [(h["id"], h["lines"]) for h in held] == [(first, 1)]
    second = ctl.bill_id
    ctl.resume(first)                       # the current bill is held automatically
    assert ctl.bill_id == first and [h["id"] for h in ctl.held_bills()] == [second]


def test_hold_of_an_empty_bill_returns_none_and_cancels_it(shop_conn, ctl):
    pune = parties.create_party(shop_conn, name="Pune Co")
    ctl.set_customer(pune)                   # creates a held bill with no lines
    assert ctl.hold() is None and ctl.bill_id is None
    assert billing.list_held(shop_conn) == []


def test_held_bills_ignore_empty_ones(shop_conn, ctl):
    billing.start_bill(shop_conn)           # an empty held bill left by an earlier crash
    assert ctl.held_bills() == []


def test_resume_rejects_unknown_and_non_held_bills(shop_conn, ctl):
    item = stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    bill_id, _ = ctl.pay([("cash", 11800)])
    with pytest.raises(billing.BillingError):
        ctl.resume(bill_id)
    with pytest.raises(billing.BillingError):
        ctl.resume(999)
    assert item


def test_pay_finalizes_resets_and_returns_the_bill_number(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    bill_id, bill_no = ctl.pay([("cash", 11800)])
    assert bill_no == "S000001" and ctl.bill_id is None and not ctl.has_lines()
    assert billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "final"
    with pytest.raises(billing.BillingError):
        ctl.pay([("cash", 1)])              # nothing to pay


def test_a_failed_payment_keeps_the_bill(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    with pytest.raises(billing.BillingError):
        ctl.pay([("cash", 1)])
    assert ctl.has_lines()


def test_discard_cancels_the_current_bill(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    ctl.submit("8901")
    bill_id = ctl.bill_id
    ctl.discard()
    assert ctl.bill_id is None and billing.get_bill(shop_conn, bill_id)["bill"]["status"] == "cancelled"
    ctl.discard()                           # nothing to discard: no error


def test_read_only_blocks_adding(shop_conn, ctl):
    stocked(shop_conn, name="Soap", barcodes=["8901"])
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        ctl.submit("8901")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_counter_logic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.counter_logic'`.

- [ ] **Step 3: Implement**

`retail_ui/screens/counter_logic.py`:
```python
"""What a counter entry means. No Qt here: the screen asks, shows prompts, and calls back in."""
from dataclasses import dataclass

from retail.services import billing, items


@dataclass(frozen=True)
class Entry:
    kind: str                 # ignored | added | pick | serial | weight | new_item
    line_id: int | None = None
    items: tuple = ()
    item: object = None
    qty_milli: int = 1000
    text: str = ""
    explicit_qty: bool = True


class CounterController:
    def __init__(self, holder):
        self.holder = holder  # anything with a .conn (the AppSession): picks up a restored database
        self.bill_id = None

    @property
    def conn(self):
        return self.holder.conn

    # --- entries -----------------------------------------------------------------
    def submit(self, text):
        text = (text or "").strip()
        if not text:
            return Entry("ignored")
        qty, key = items.parse_entry(text)
        if qty <= 0 or not key:
            return Entry("ignored", text=text)
        explicit = key != text            # the user typed a "3*" prefix
        matches = items.resolve(self.conn, key)
        if not matches:
            return Entry("new_item", text=key, qty_milli=qty, explicit_qty=explicit)
        if len(matches) > 1:
            return Entry("pick", items=tuple(matches), text=key, qty_milli=qty, explicit_qty=explicit)
        return self.add(matches[0], qty, explicit_qty=explicit)

    def add(self, item, qty_milli, *, serial=None, explicit_qty=True):
        tracking = item["tracking"]
        if tracking == "serial":
            if not serial:
                return Entry("serial", item=item)
            qty_milli = 1000
        elif tracking == "weighed" and not explicit_qty:
            return Entry("weight", item=item)
        bill_id = self._ensure_bill()
        line_id = billing.add_line(self.conn, bill_id, item["id"], qty_milli, serial=serial)
        return Entry("added", line_id=line_id, item=item, qty_milli=qty_milli)

    def _ensure_bill(self):
        if self.bill_id is None:
            self.bill_id = billing.start_bill(self.conn)
        return self.bill_id

    # --- the current bill -----------------------------------------------------------
    def detail(self):
        return None if self.bill_id is None else billing.get_bill_detail(self.conn, self.bill_id)

    def has_lines(self):
        detail = self.detail()
        return bool(detail and detail["lines"])

    def remove_line(self, line_id):
        billing.remove_line(self.conn, self.bill_id, line_id)

    def set_customer(self, party_id):
        billing.set_party(self.conn, self._ensure_bill(), party_id)

    def set_discount(self, line_id, discount_paise):
        billing.set_line_discount(self.conn, self.bill_id, line_id, discount_paise)

    # --- hold / resume / pay ----------------------------------------------------------
    def held_bills(self):
        rows = []
        for bill in billing.list_held(self.conn):
            if bill["id"] == self.bill_id:
                continue
            detail = billing.get_bill_detail(self.conn, bill["id"])
            if detail["lines"]:
                rows.append({"id": bill["id"], "party": detail["party"]["name"] if detail["party"] else "",
                             "total_paise": bill["total_paise"], "lines": len(detail["lines"])})
        return rows

    def hold(self):
        """Park the current bill; an empty one is cancelled instead. Returns the held bill id."""
        if self.bill_id is None:
            return None
        if not self.has_lines():
            billing.cancel_held(self.conn, self.bill_id)
            self.bill_id = None
            return None
        held, self.bill_id = self.bill_id, None
        return held

    def resume(self, bill_id):
        detail = billing.get_bill_detail(self.conn, bill_id)  # raises BillingError for an unknown bill
        if detail["bill"]["status"] != "held" or detail["bill"]["kind"] != "sale":
            raise billing.BillingError("Only a held sale bill can be resumed")
        if bill_id != self.bill_id:
            self.hold()
            self.bill_id = bill_id

    def discard(self):
        if self.bill_id is not None:
            billing.cancel_held(self.conn, self.bill_id)
            self.bill_id = None

    def pay(self, payments):
        if self.bill_id is None:
            raise billing.BillingError("There is no bill to pay")
        bill_no = billing.finalize(self.conn, self.bill_id, payments)
        bill_id, self.bill_id = self.bill_id, None
        return bill_id, bill_no
```

- [ ] **Step 4: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_counter_logic.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the Qt-free counter controller (entry resolution, hold/resume/pay)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Counter dialogs

**Files:**
- Create: `retail_ui/screens/counter_dialogs.py`, `tests/ui/test_ui_counter_dialogs.py`
- Modify: `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `fmt.*`, `helpers.ok_cancel`, `parties.list_parties/create_party`, `errors.show_error`, `segments.template_settings` (a dict passed in as `template`).
- Produces (all `QDialog`s; tests drive their widgets without `exec()`):
  - `PickItemDialog(items, parent=None)` → `selected_item_id() -> int | None`.
  - `QtyDialog(item_name, parent=None)` → `qty_milli() -> int` (OK enabled only for a valid quantity > 0).
  - `SerialDialog(item_name, parent=None)` → `serial() -> str` (OK enabled only when non-blank).
  - `QuickAddDialog(prefill, template, parent=None)` → `values() -> dict` usable as `items.create_item(conn, **values)` (`name, sell_price_paise, gst_rate_bp, tracking, unit, barcodes`); a numeric prefill of ≥ 6 digits becomes the barcode, anything else the name.
  - `CustomerDialog(conn, parent=None)` → `party_id() -> int | None`, `cleared() -> bool` (walk-in chosen).
  - `DiscountDialog(max_paise, parent=None)` → `discount_paise() -> int` (OK only for `0 ≤ value ≤ max`).
  - `HeldBillsDialog(rows, parent=None)` → `action() -> "resume" | "discard" | None`, `selected_bill_id() -> int | None`.
  - `PayDialog(total_paise, has_customer, features, parent=None)` → `payments() -> list[(mode, paise)]`, `paid_paise`, `remaining_paise`, `is_valid()`; modes shown: cash, upi, card, `emi` when `features["emi"]`, `credit` when a customer is set and `features["udhaar"]`.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_counter_dialogs.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import segments
from retail.services import items, parties
from retail_ui.screens import counter_dialogs as cd


def rows(conn):
    a = items.create_item(conn, name="Bath soap", sell_price_paise=1000)
    b = items.create_item(conn, name="Hand soap", sell_price_paise=2000)
    return items.list_items(conn), a, b


def test_pick_item_dialog(shop_conn, qtbot):
    listed, a, b = rows(shop_conn)
    d = cd.PickItemDialog(listed)
    qtbot.addWidget(d)
    assert d.selected_item_id() == a                      # first row preselected
    d.list.setCurrentRow(1)
    assert d.selected_item_id() == b
    assert "₹20.00" in d.list.item(1).text()


@pytest.mark.parametrize("text,ok,value", [("2", True, 2000), ("0.75", True, 750), ("", False, None),
                                           ("0", False, None), ("abc", False, None), ("-1", False, None)])
def test_qty_dialog(qtbot, text, ok, value):
    d = cd.QtyDialog("Rice")
    qtbot.addWidget(d)
    d.edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.qty_milli() == value


def test_serial_dialog(qtbot):
    d = cd.SerialDialog("Phone")
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.edit.setText("  356938035643809 ")
    assert d.ok_button.isEnabled() and d.serial() == "356938035643809"


def grocery(conn):
    segments.apply_template(conn, "grocery")      # the shop_conn fixture sets no template features
    return segments.template_settings(conn)


def electronics(conn):
    segments.apply_template(conn, "electronics")
    return segments.template_settings(conn)


def test_quick_add_numeric_prefill_becomes_the_barcode(shop_conn, qtbot):
    d = cd.QuickAddDialog("8901719101015", grocery(shop_conn))
    qtbot.addWidget(d)
    assert d.name_edit.text() == "" and d.barcode_edit.text() == "8901719101015"
    assert not d.ok_button.isEnabled()                    # name and price still missing
    d.name_edit.setText(" Parle-G ")
    d.price_edit.setText("₹10")
    assert d.ok_button.isEnabled()
    v = d.values()
    assert v["name"] == "Parle-G" and v["sell_price_paise"] == 1000 and v["barcodes"] == ["8901719101015"]
    assert v["tracking"] == "none" and v["unit"] == "pcs"


def test_quick_add_text_prefill_becomes_the_name_and_gst_defaults_to_zero(shop_conn, qtbot):
    d = cd.QuickAddDialog("rice", grocery(shop_conn))
    qtbot.addWidget(d)
    assert d.name_edit.text() == "rice" and d.barcode_edit.text() == ""
    d.price_edit.setText("60")
    assert d.values()["gst_rate_bp"] == 0 and d.values()["barcodes"] == []


def test_quick_add_offers_only_the_tracking_modes_the_template_enables(shop_conn, qtbot):
    g = cd.QuickAddDialog("x", grocery(shop_conn))
    qtbot.addWidget(g)
    assert [g.tracking_box.itemData(i) for i in range(g.tracking_box.count())] == ["none", "weighed"]
    e = cd.QuickAddDialog("x", electronics(shop_conn))
    qtbot.addWidget(e)
    assert "serial" in [e.tracking_box.itemData(i) for i in range(e.tracking_box.count())]
    assert e.tracking_box.currentData() == "serial"       # the template's default
    g.tracking_box.setCurrentIndex(g.tracking_box.findData("weighed"))
    g.name_edit.setText("Rice")
    g.price_edit.setText("60")
    assert g.values()["unit"] == "kg"


def test_quick_add_gst_slabs_come_from_the_template(shop_conn, qtbot):
    d = cd.QuickAddDialog("x", grocery(shop_conn))
    qtbot.addWidget(d)
    assert [d.gst_box.itemData(i) for i in range(d.gst_box.count())] == [0, 500, 1800, 4000]
    d.gst_box.setCurrentIndex(d.gst_box.findData(1800))
    d.name_edit.setText("Soap")
    d.price_edit.setText("118")
    assert d.values()["gst_rate_bp"] == 1800


def test_customer_dialog_search_select_and_create(shop_conn, qtbot):
    ravi = parties.create_party(shop_conn, name="Ravi", phone="9876500001")
    parties.create_party(shop_conn, name="Wholesale Co", type="supplier")
    d = cd.CustomerDialog(shop_conn)
    qtbot.addWidget(d)
    assert d.list.count() == 1                            # suppliers are not customers
    d.list.setCurrentRow(0)
    assert d.party_id() == ravi and not d.cleared()
    d.search_edit.setText("zzz")
    assert d.list.count() == 0 and d.party_id() is None
    d.new_name.setText("Sita")
    d.new_phone.setText("12345")
    d.add_button.click()
    sita = d.party_id()
    assert sita is not None and parties.list_parties(shop_conn, search="Sita")[0]["phone"] == "12345"


def test_customer_dialog_walk_in_clears_the_customer(shop_conn, qtbot):
    d = cd.CustomerDialog(shop_conn)
    qtbot.addWidget(d)
    d.walk_in_button.click()
    assert d.cleared() and d.party_id() is None


@pytest.mark.parametrize("text,ok,paise", [("0", True, 0), ("₹18", True, 1800), ("18.5", True, 1850),
                                           ("200", False, None), ("-1", False, None), ("x", False, None), ("", False, None)])
def test_discount_dialog(qtbot, text, ok, paise):
    d = cd.DiscountDialog(max_paise=11800)
    qtbot.addWidget(d)
    d.edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.discount_paise() == paise


def test_held_bills_dialog(qtbot):
    held = [{"id": 5, "party": "Ravi", "total_paise": 11800, "lines": 2},
            {"id": 9, "party": "", "total_paise": 500, "lines": 1}]
    d = cd.HeldBillsDialog(held)
    qtbot.addWidget(d)
    assert d.list.count() == 2 and d.selected_bill_id() == 5 and d.action() is None
    d.list.setCurrentRow(1)
    d.resume_button.click()
    assert d.action() == "resume" and d.selected_bill_id() == 9
    d2 = cd.HeldBillsDialog(held)
    qtbot.addWidget(d2)
    d2.discard_button.click()
    assert d2.action() == "discard"
    empty = cd.HeldBillsDialog([])
    qtbot.addWidget(empty)
    assert not empty.resume_button.isEnabled() and empty.selected_bill_id() is None


def test_pay_dialog_cash_is_prefilled_and_valid(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={"emi": False, "udhaar": True})
    qtbot.addWidget(d)
    assert set(d.edits) == {"cash", "upi", "card"}        # no credit without a customer, no EMI
    assert d.edits["cash"].text() == "118.00" and d.is_valid() and d.ok_button.isEnabled()
    assert d.payments() == [("cash", 11800)] and d.remaining_paise == 0


def test_pay_dialog_split_payment_and_balance(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.edits["cash"].setText("50")
    assert d.remaining_paise == 6800 and not d.is_valid() and not d.ok_button.isEnabled()
    d.edits["upi"].setText("68")
    assert d.is_valid() and d.payments() == [("cash", 5000), ("upi", 6800)]


def test_pay_dialog_overpayment_and_garbage_are_invalid(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.edits["upi"].setText("1")
    assert d.remaining_paise == -100 and not d.is_valid()
    d.edits["upi"].setText("abc")
    assert not d.is_valid() and not d.ok_button.isEnabled()


def test_pay_dialog_change_for_cash_given(qtbot):
    d = cd.PayDialog(11800, has_customer=False, features={})
    qtbot.addWidget(d)
    d.cash_given_edit.setText("200")
    assert d.change_paise == 8200
    d.cash_given_edit.setText("50")
    assert d.change_paise == 0                            # not enough cash given: no change shown


def test_pay_dialog_credit_and_emi_depend_on_customer_and_features(qtbot):
    d = cd.PayDialog(11800, has_customer=True, features={"emi": True, "udhaar": True})
    qtbot.addWidget(d)
    assert set(d.edits) == {"cash", "upi", "card", "emi", "credit"}
    d.edits["cash"].setText("0")
    d.edits["credit"].setText("118")
    assert d.payments() == [("credit", 11800)] and d.is_valid()
    no_udhaar = cd.PayDialog(11800, has_customer=True, features={"udhaar": False})
    qtbot.addWidget(no_udhaar)
    assert "credit" not in no_udhaar.edits


def test_pay_dialog_free_bill_is_valid_with_no_payments(qtbot):
    d = cd.PayDialog(0, has_customer=False, features={})
    qtbot.addWidget(d)
    assert d.is_valid() and d.payments() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_counter_dialogs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.counter_dialogs'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task10.json`:
```json
{
  "dlg.pick_title": {"en": "Choose item", "hi": "वस्तु चुनें", "te": "వస్తువును ఎంచుకోండి"},
  "dlg.qty_title": {"en": "Enter quantity", "hi": "मात्रा लिखें", "te": "పరిమాణం నమోదు చేయండి"},
  "dlg.qty_label": {"en": "Quantity", "hi": "मात्रा", "te": "పరిమాణం"},
  "dlg.serial_title": {"en": "Serial / IMEI", "hi": "सीरियल / IMEI", "te": "సీరియల్ / IMEI"},
  "dlg.serial_prompt": {"en": "Scan or type the serial / IMEI number", "hi": "सीरियल / IMEI नंबर स्कैन करें या लिखें", "te": "సీరియల్ / IMEI నంబర్‌ను స్కాన్ చేయండి లేదా టైప్ చేయండి"},
  "dlg.new_item_title": {"en": "New item", "hi": "नई वस्तु", "te": "కొత్త వస్తువు"},
  "dlg.price": {"en": "Selling price", "hi": "बिक्री मूल्य", "te": "అమ్మకం ధర"},
  "dlg.gst_rate": {"en": "GST rate", "hi": "GST दर", "te": "GST రేటు"},
  "dlg.tracking": {"en": "Tracking", "hi": "ट्रैकिंग", "te": "ట్రాకింగ్"},
  "dlg.barcode": {"en": "Barcode", "hi": "बारकोड", "te": "బార్‌కోడ్"},
  "trk.none": {"en": "Counted", "hi": "गिनती वाली", "te": "లెక్కించేవి"},
  "trk.weighed": {"en": "Weighed (kg/litre)", "hi": "तौल वाली (किलो/लीटर)", "te": "తూకం వేసేవి (కిలో/లీటరు)"},
  "trk.batch": {"en": "Batch & expiry", "hi": "बैच और एक्सपायरी", "te": "బ్యాచ్ & ఎక్స్‌పైరీ"},
  "trk.serial": {"en": "Serial / IMEI", "hi": "सीरियल / IMEI", "te": "సీరియల్ / IMEI"},
  "dlg.customer_title": {"en": "Customer", "hi": "ग्राहक", "te": "కస్టమర్"},
  "dlg.walk_in": {"en": "Walk-in (no customer)", "hi": "बिना ग्राहक (नकद)", "te": "కస్టమర్ లేకుండా (నగదు)"},
  "dlg.new_customer": {"en": "New customer", "hi": "नया ग्राहक", "te": "కొత్త కస్టమర్"},
  "dlg.discount_title": {"en": "Discount", "hi": "छूट", "te": "తగ్గింపు"},
  "dlg.discount_prompt": {"en": "Discount amount (₹)", "hi": "छूट की राशि (₹)", "te": "తగ్గింపు మొత్తం (₹)"},
  "dlg.held_title": {"en": "Held bills", "hi": "रोके गए बिल", "te": "ఆపిన బిల్లులు"},
  "dlg.resume": {"en": "Resume", "hi": "फिर शुरू करें", "te": "తిరిగి మొదలుపెట్టు"},
  "dlg.discard": {"en": "Discard bill", "hi": "बिल हटाएँ", "te": "బిల్లును తొలగించు"},
  "dlg.pay_title": {"en": "Payment", "hi": "भुगतान", "te": "చెల్లింపు"},
  "dlg.paid": {"en": "Paid", "hi": "चुकाया", "te": "చెల్లించినది"},
  "dlg.balance": {"en": "Balance", "hi": "बाकी", "te": "మిగిలినది"},
  "dlg.cash_given": {"en": "Cash given", "hi": "नकद मिला", "te": "తీసుకున్న నగదు"},
  "dlg.change": {"en": "Change to return", "hi": "लौटाने की रकम", "te": "తిరిగి ఇవ్వాల్సినది"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task10.json`

- [ ] **Step 4: Implement**

`retail_ui/screens/counter_dialogs.py`:
```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from retail import money
from retail.i18n import tr
from retail.services import parties
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.helpers import ok_cancel


def _valid(parser, text):
    try:
        parser(text)
        return True
    except ValueError:
        return False


class PickItemDialog(QDialog):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.pick_title"))
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for it in items:
            entry = QListWidgetItem(f"{it['name']}  —  {fmt.rupees(it['sell_price_paise'])}")
            entry.setData(Qt.ItemDataRole.UserRole, it["id"])
            self.list.addItem(entry)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(self.list)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)

    def selected_item_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class QtyDialog(QDialog):
    def __init__(self, item_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.qty_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(item_name))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("dlg.qty_label"))
        layout.addWidget(self.edit)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.ok_button.setEnabled(_valid(fmt.parse_qty, self.edit.text()))

    def qty_milli(self):
        return fmt.parse_qty(self.edit.text())


class SerialDialog(QDialog):
    def __init__(self, item_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.serial_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{item_name}\n{tr('dlg.serial_prompt')}"))
        self.edit = QLineEdit()
        layout.addWidget(self.edit)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.edit.textChanged.connect(lambda: self.ok_button.setEnabled(bool(self.serial())))
        self.ok_button.setEnabled(False)

    def serial(self):
        return self.edit.text().strip()


class QuickAddDialog(QDialog):
    def __init__(self, prefill, template, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.new_item_title"))
        features = template.get("features", {})
        form = QFormLayout(self)
        digits = prefill.isdigit() and len(prefill) >= 6
        self.name_edit = QLineEdit("" if digits else prefill)
        self.barcode_edit = QLineEdit(prefill if digits else "")
        self.price_edit = QLineEdit()
        self.gst_box = QComboBox()
        for bp in template.get("gst_slabs_bp", [0]):
            self.gst_box.addItem(f"{bp / 100:g}%", bp)
        self.gst_box.setCurrentIndex(max(self.gst_box.findData(0), 0))
        self.tracking_box = QComboBox()
        allowed = ["none"] + [t for t in ("weighed", "batch", "serial") if features.get(t)]
        for mode in allowed:
            self.tracking_box.addItem(tr(f"trk.{mode}"), mode)
        default = template.get("default_tracking", "none")
        self.tracking_box.setCurrentIndex(max(self.tracking_box.findData(default), 0))
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("dlg.barcode"), self.barcode_edit)
        form.addRow(tr("dlg.price"), self.price_edit)
        form.addRow(tr("dlg.gst_rate"), self.gst_box)
        form.addRow(tr("dlg.tracking"), self.tracking_box)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.name_edit.textChanged.connect(self._check)
        self.price_edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.ok_button.setEnabled(bool(self.name_edit.text().strip())
                                  and _valid(fmt.parse_rupees, self.price_edit.text()))

    def values(self):
        tracking = self.tracking_box.currentData()
        barcode = self.barcode_edit.text().strip()
        return {"name": self.name_edit.text().strip(),
                "sell_price_paise": fmt.parse_rupees(self.price_edit.text()),
                "gst_rate_bp": self.gst_box.currentData(), "tracking": tracking,
                "unit": "kg" if tracking == "weighed" else "pcs",
                "barcodes": [barcode] if barcode else []}


class CustomerDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(tr("dlg.customer_title"))
        self._party_id = None
        self._cleared = False
        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("common.search"))
        layout.addWidget(self.search_edit)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.walk_in_button = QPushButton(tr("dlg.walk_in"))
        layout.addWidget(self.walk_in_button)
        layout.addWidget(QLabel(tr("dlg.new_customer")))
        row = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText(tr("common.name"))
        self.new_phone = QLineEdit()
        self.new_phone.setPlaceholderText(tr("common.phone"))
        self.add_button = QPushButton(tr("common.add"))
        for w in (self.new_name, self.new_phone, self.add_button):
            row.addWidget(w)
        layout.addLayout(row)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.search_edit.textChanged.connect(self._reload)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        self.walk_in_button.clicked.connect(self._walk_in)
        self.add_button.clicked.connect(self._add)
        self._reload()

    def _reload(self):
        self.list.clear()
        for p in parties.list_parties(self.conn, kind="customer", search=self.search_edit.text()):
            item = QListWidgetItem(f"{p['name']}  {p['phone'] or ''}")
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            self.list.addItem(item)

    def _walk_in(self):
        self._cleared = True
        self.accept()

    def _add(self):
        try:
            self._party_id = parties.create_party(self.conn, name=self.new_name.text(),
                                                  phone=self.new_phone.text().strip() or None)
        except Exception as exc:
            show_error(self, exc)
            return
        self.accept()

    def party_id(self):
        if self._party_id is not None:
            return self._party_id
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def cleared(self):
        return self._cleared


class DiscountDialog(QDialog):
    def __init__(self, max_paise, parent=None):
        super().__init__(parent)
        self.max_paise = max_paise
        self.setWindowTitle(tr("dlg.discount_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("dlg.discount_prompt")))
        self.edit = QLineEdit()
        layout.addWidget(self.edit)
        box, self.ok_button = ok_cancel(self)
        layout.addWidget(box)
        self.edit.textChanged.connect(self._check)
        self._check()

    def _amount(self):
        paise = fmt.parse_rupees(self.edit.text())
        if not 0 <= paise <= self.max_paise:
            raise ValueError("out of range")
        return paise

    def _check(self):
        self.ok_button.setEnabled(_valid(lambda _t: self._amount(), self.edit.text()))

    def discount_paise(self):
        return self._amount()


class HeldBillsDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.held_title"))
        self._action = None
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        for r in rows:
            who = r["party"] or tr("dlg.walk_in")
            item = QListWidgetItem(f"#{r['id']}   {who}   {fmt.rupees(r['total_paise'])}   ({r['lines']})")
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.resume_button = QPushButton(tr("dlg.resume"))
        self.discard_button = QPushButton(tr("dlg.discard"))
        close = QPushButton(tr("common.close"))
        for b in (self.resume_button, self.discard_button, close):
            row.addWidget(b)
        layout.addLayout(row)
        self.resume_button.setEnabled(bool(rows))
        self.discard_button.setEnabled(bool(rows))
        self.resume_button.clicked.connect(lambda: self._finish("resume"))
        self.discard_button.clicked.connect(lambda: self._finish("discard"))
        close.clicked.connect(self.reject)

    def _finish(self, action):
        self._action = action
        self.accept()

    def action(self):
        return self._action

    def selected_bill_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class PayDialog(QDialog):
    def __init__(self, total_paise, has_customer, features, parent=None):
        super().__init__(parent)
        self.total_paise = total_paise
        self.setWindowTitle(tr("dlg.pay_title"))
        modes = ["cash", "upi", "card"]
        if features.get("emi"):
            modes.append("emi")
        if has_customer and features.get("udhaar"):
            modes.append("credit")
        form = QFormLayout(self)
        form.addRow(QLabel(f"{tr('bill.total')}: {fmt.rupees(total_paise)}"))
        self.edits = {}
        for mode in modes:
            edit = QLineEdit(money.paise_to_str(total_paise) if mode == "cash" else "")
            edit.textChanged.connect(self._recalc)
            self.edits[mode] = edit
            form.addRow(tr(f"pay.{mode}"), edit)
        self.cash_given_edit = QLineEdit()
        self.cash_given_edit.textChanged.connect(self._recalc)
        form.addRow(tr("dlg.cash_given"), self.cash_given_edit)
        self.balance_label = QLabel()
        self.change_label = QLabel()
        form.addRow(tr("dlg.balance"), self.balance_label)
        form.addRow(tr("dlg.change"), self.change_label)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.paid_paise = 0
        self.remaining_paise = total_paise
        self.change_paise = 0
        self._valid_input = True
        self._recalc()

    def _amount(self, edit):
        text = edit.text().strip()
        return 0 if not text else fmt.parse_rupees(text)

    def _recalc(self):
        try:
            amounts = {mode: self._amount(edit) for mode, edit in self.edits.items()}
            given = self._amount(self.cash_given_edit)
            self._valid_input = all(v >= 0 for v in amounts.values())
        except ValueError:
            self._valid_input = False
            self.ok_button.setEnabled(False)
            return
        self._amounts = amounts
        self.paid_paise = sum(amounts.values())
        self.remaining_paise = self.total_paise - self.paid_paise
        cash = amounts.get("cash", 0)
        self.change_paise = given - cash if given > cash else 0
        self.balance_label.setText(fmt.rupees(self.remaining_paise))
        self.change_label.setText(fmt.rupees(self.change_paise))
        self.ok_button.setEnabled(self.is_valid())

    def is_valid(self):
        return self._valid_input and self.remaining_paise == 0

    def payments(self):
        return [(mode, paise) for mode, paise in self._amounts.items() if paise > 0]
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_counter_dialogs.py tests/test_i18n.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the counter dialogs (pick, quantity, serial, quick-add, customer, discount, held, pay)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The counter screen

**Files:**
- Create: `retail_ui/screens/counter.py`, `tests/ui/test_ui_counter.py`
- Modify: `retail_ui/screens/registry.py` (append `CounterScreen`), `tests/test_i18n.py` (allow-list), `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `CounterController`, all counter dialogs, `RowsModel`, `Screen`, `errors.show_error`, `fmt`, `segments.template_settings/feature_enabled`, `items.create_item/get_item`, `session` signals.
- Produces: `CounterScreen(session)` (`nav_key = "nav.counter"`) with widgets `entry, table, model, total_label, tax_label, customer_label, status_label` and buttons `customer_button, discount_button, hold_button, held_button, discard_button, delete_button, pay_button`; signal `sale_completed(int)` (bill id); `last_bill_id`; methods `submit_text(text)`, `pick_customer()`, `apply_discount()`, `hold_bill()`, `show_held()`, `discard_bill()`, `delete_selected_line()`, `pay()`; and overridable prompt hooks `_ask_pick(items)`, `_ask_qty(item)`, `_ask_serial(item)`, `_ask_new_item(text)`, `_ask_customer()`, `_ask_discount(max_paise)`, `_ask_held(rows)`, `_ask_payments(total_paise, party_id)`, `_confirm(key)` (tests replace these instead of running modal dialogs). Shortcuts: F2 customer, F3 hold, F4 held bills, F5 discount, F8 discard, Delete delete line, F12 pay.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_counter.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import guard, i18n
from retail.services import billing, items, parties, stock
from retail_ui import errors
from retail_ui.screens.counter import CounterScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = CounterScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)      # collect instead of showing a modal box
    return sc


def stocked(conn, **kw):
    kw.setdefault("sell_price_paise", 11800)
    kw.setdefault("gst_rate_bp", 1800)
    item_id = items.create_item(conn, **kw)
    stock.record(conn, item_id, 50_000, "opening")
    return item_id


def type_and_enter(screen, text):
    screen.entry.setText(text)
    screen.entry.returnPressed.emit()


def totals_text(screen):
    return screen.total_label.text()


def test_scanning_a_barcode_adds_a_line_and_refocuses_the_input(screen, qtbot):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    screen.show()
    type_and_enter(screen, "8901")
    assert screen.model.rowCount() == 1 and screen.entry.text() == ""
    assert "₹118.00" in totals_text(screen) and screen.focusWidget() is screen.entry
    row = [screen.model.data(screen.model.index(0, c)) for c in range(screen.model.columnCount())]
    assert row[0] == "Soap" and row[1] == "1" and row[5] == "₹118.00"


def test_quantity_prefix_and_blank_enter(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "")
    type_and_enter(screen, "3*8901")
    assert screen.model.rowCount() == 1 and screen.model.data(screen.model.index(0, 1)) == "3"
    assert "₹354.00" in totals_text(screen)


def test_unknown_code_opens_quick_add_prefilled_then_adds_the_line(screen):
    asked = []
    screen._ask_new_item = lambda text: asked.append(text) or {
        "name": "Parle-G", "sell_price_paise": 1000, "gst_rate_bp": 500, "tracking": "none",
        "unit": "pcs", "barcodes": ["8901719101015"]}
    type_and_enter(screen, "8901719101015")
    assert asked == ["8901719101015"] and screen.model.rowCount() == 1
    assert items.resolve(screen.session.conn, "8901719101015")[0]["name"] == "Parle-G"


def test_cancelling_quick_add_adds_nothing(screen):
    screen._ask_new_item = lambda text: None
    type_and_enter(screen, "999999")
    assert screen.model.rowCount() == 0 and screen.errors == []


def test_several_name_matches_use_the_picker(screen):
    a = stocked(screen.session.conn, name="Bath soap")
    b = stocked(screen.session.conn, name="Hand soap")
    screen._ask_pick = lambda rows: b
    type_and_enter(screen, "soap")
    assert screen.model.data(screen.model.index(0, 0)) == "Hand soap"
    screen._ask_pick = lambda rows: None
    type_and_enter(screen, "soap")
    assert screen.model.rowCount() == 1 and a


def test_weighed_item_asks_for_weight(screen):
    stocked(screen.session.conn, name="Rice", sell_price_paise=6000, gst_rate_bp=0, unit="kg", tracking="weighed")
    screen._ask_qty = lambda item: 750
    type_and_enter(screen, "rice")
    assert screen.model.data(screen.model.index(0, 1)) == "0.75 kg"
    assert "₹45.00" in totals_text(screen)


def test_serial_item_asks_for_serial(screen):
    conn = screen.session.conn
    phone = items.create_item(conn, name="Phone", sell_price_paise=100000, tracking="serial", barcodes=["1234567"])
    unit = stock.add_unit(conn, phone, serial="IMEI1")
    stock.record(conn, phone, 1000, "opening", unit_id=unit)
    screen._ask_serial = lambda item: "imei1"
    type_and_enter(screen, "1234567")
    assert "IMEI1" in screen.model.data(screen.model.index(0, 0))
    screen._ask_serial = lambda item: "WRONG"
    type_and_enter(screen, "1234567")
    assert len(screen.errors) == 1 and screen.model.rowCount() == 1       # engine error shown, bill intact


def test_engine_errors_are_reported_not_raised_and_focus_returns(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    guard.set_read_only(True)
    screen.show()
    type_and_enter(screen, "8901")
    assert len(screen.errors) == 1 and isinstance(screen.errors[0], guard.ReadOnlyError)
    assert errors.message_for(screen.errors[0]) == i18n.tr("err.read_only")
    assert screen.focusWidget() is screen.entry


def test_discount_delete_and_customer(screen):
    conn = screen.session.conn
    stocked(conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "2*8901")
    screen.table.selectRow(0)
    screen._ask_discount = lambda max_paise: 1800
    screen.apply_discount()
    assert "₹218.00" in totals_text(screen) and screen.model.data(screen.model.index(0, 3)) == "₹18.00"
    ravi = parties.create_party(conn, name="Ravi", state_code="27")
    screen._ask_customer = lambda: ("set", ravi)
    screen.pick_customer()
    assert "Ravi" in screen.customer_label.text() and "IGST" in screen.tax_label.text()
    screen._ask_customer = lambda: ("clear", None)
    screen.pick_customer()
    assert "Ravi" not in screen.customer_label.text()
    screen.table.selectRow(0)
    screen.delete_selected_line()
    assert screen.model.rowCount() == 0


def test_hold_resume_and_discard(screen):
    conn = screen.session.conn
    stocked(conn, name="Soap", barcodes=["8901"])
    stocked(conn, name="Tea", barcodes=["8902"], sell_price_paise=500, gst_rate_bp=0)
    type_and_enter(screen, "8901")
    screen.hold_bill()
    assert screen.model.rowCount() == 0 and screen.controller.held_bills()[0]["lines"] == 1
    type_and_enter(screen, "8902")
    held_id = screen.controller.held_bills()[0]["id"]
    screen._ask_held = lambda rows: ("resume", held_id)
    screen.show_held()
    assert screen.model.data(screen.model.index(0, 0)) == "Soap"
    screen._confirm = lambda key: True
    screen.discard_bill()
    assert screen.model.rowCount() == 0
    screen._confirm = lambda key: False
    type_and_enter(screen, "8902")
    screen.discard_bill()
    assert screen.model.rowCount() == 1


def test_held_bills_survive_closing_the_app(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    first = CounterScreen(session)
    qtbot.addWidget(first)
    type_and_enter(first, "8901")
    first.hold_bill()
    second = CounterScreen(session)                   # "restart"
    qtbot.addWidget(second)
    assert [h["lines"] for h in second.controller.held_bills()] == [1]


def test_pay_finalizes_clears_and_announces_the_bill(screen, qtbot):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "8901")
    seen = []
    screen.sale_completed.connect(seen.append)
    screen._ask_payments = lambda total, party_id: [("cash", total)]
    screen.pay()
    assert screen.model.rowCount() == 0 and len(seen) == 1 and screen.last_bill_id == seen[0]
    assert billing.get_bill(screen.session.conn, seen[0])["bill"]["bill_no"] == "S000001"
    assert "S000001" in screen.status_label.text()


def test_cancelled_payment_keeps_the_bill(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "8901")
    screen._ask_payments = lambda total, party_id: None
    screen.pay()
    assert screen.model.rowCount() == 1


def test_paying_an_empty_bill_does_nothing(screen):
    screen._ask_payments = lambda total, party_id: pytest.fail("no dialog for an empty bill")
    screen.pay()
    assert screen.errors == []


def test_language_switch_keeps_the_bill_and_retranslates(screen):
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    type_and_enter(screen, "2*8901")
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.model.rowCount() == 1 and "₹236.00" in totals_text(screen)
    assert screen.model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("bill.item") != "Item"
    assert screen.pay_button.text() == f"{i18n.tr('counter.pay')} (F12)"


def test_read_only_disables_the_write_controls(screen):
    screen.apply_read_only(True)
    for name in ("entry", "customer_button", "discount_button", "hold_button", "held_button",
                 "discard_button", "delete_button", "pay_button"):
        assert not getattr(screen, name).isEnabled(), name
    screen.apply_read_only(False)
    assert screen.entry.isEnabled() and screen.pay_button.isEnabled()


def test_function_key_shortcuts_are_registered(screen):
    assert set(screen.shortcut_keys) == {"F2", "F3", "F4", "F5", "F8", "Del", "F12"}


def test_refresh_after_a_restore_follows_the_new_connection(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    sc = CounterScreen(session)
    qtbot.addWidget(sc)
    type_and_enter(sc, "8901")
    snapshot = session.backup_now().path
    session.restore_from(snapshot)                    # new connection, same data
    sc.refresh()
    assert sc.controller.conn is session.conn and sc.model.rowCount() == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_counter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.counter'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task11.json`:
```json
{
  "counter.entry_hint": {"en": "Scan a barcode or type an item name (use 3* before it for quantity)", "hi": "बारकोड स्कैन करें या वस्तु का नाम लिखें (मात्रा के लिए पहले 3* लिखें)", "te": "బార్‌కోడ్ స్కాన్ చేయండి లేదా వస్తువు పేరు టైప్ చేయండి (పరిమాణానికి ముందు 3* రాయండి)"},
  "counter.customer": {"en": "Customer", "hi": "ग्राहक", "te": "కస్టమర్"},
  "counter.customer_set": {"en": "Customer: {name}", "hi": "ग्राहक: {name}", "te": "కస్టమర్: {name}"},
  "counter.walk_in_label": {"en": "Walk-in customer", "hi": "बिना ग्राहक (नकद)", "te": "కస్టమర్ లేకుండా (నగదు)"},
  "counter.discount": {"en": "Discount", "hi": "छूट", "te": "తగ్గింపు"},
  "counter.hold": {"en": "Hold", "hi": "रोकें", "te": "ఆపు"},
  "counter.held": {"en": "Held bills", "hi": "रोके गए बिल", "te": "ఆపిన బిల్లులు"},
  "counter.discard": {"en": "Discard bill", "hi": "बिल हटाएँ", "te": "బిల్లును తొలగించు"},
  "counter.delete_line": {"en": "Delete line", "hi": "लाइन हटाएँ", "te": "లైన్ తొలగించు"},
  "counter.pay": {"en": "Pay", "hi": "भुगतान", "te": "చెల్లింపు"},
  "counter.gst": {"en": "GST", "hi": "GST", "te": "GST"},
  "counter.saved": {"en": "Bill {bill_no} saved", "hi": "बिल {bill_no} सहेजा गया", "te": "బిల్లు {bill_no} సేవ్ అయింది"},
  "counter.discard_confirm": {"en": "Discard this bill?", "hi": "यह बिल हटाएँ?", "te": "ఈ బిల్లును తొలగించాలా?"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task11.json`
`counter.gst` is the same text as English in hi/te, so also add `"counter.gst"` to the `SAME_AS_ENGLISH_ALLOWED` set in `tests/test_i18n.py` now (it becomes `{"pay.upi", "tax.gstin", "tax.cgst", "tax.sgst", "tax.igst", "item.hsn", "item.sku", "counter.gst"}`).

- [ ] **Step 4: Implement**

`retail_ui/screens/counter.py`:
```python
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableView, QVBoxLayout)

from retail import segments
from retail.i18n import tr
from retail.services import billing, items
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.screens import counter_dialogs as dialogs
from retail_ui.screens.counter_logic import CounterController
from retail_ui.widgets.base import RowsModel, Screen

HEADERS = ["bill.item", "bill.qty", "bill.rate", "bill.discount", "counter.gst", "bill.total"]


class CounterScreen(Screen):
    nav_key = "nav.counter"
    sale_completed = Signal(int)

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self.controller = CounterController(session)
        self.last_bill_id = None
        layout = QVBoxLayout(self)

        self.entry = QLineEdit()
        self.entry.setStyleSheet("font-size: 18px; padding: 6px;")
        self.entry.returnPressed.connect(self._on_enter)
        layout.addWidget(self.entry)
        self.customer_label = QLabel()
        layout.addWidget(self.customer_label)

        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.tax_label = QLabel()
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_label = QLabel()
        layout.addWidget(self.tax_label)
        layout.addWidget(self.total_label)

        row = QHBoxLayout()
        self.customer_button = self._button("counter.customer", " (F2)", self.pick_customer, row)
        self.discount_button = self._button("counter.discount", " (F5)", self.apply_discount, row)
        self.hold_button = self._button("counter.hold", " (F3)", self.hold_bill, row)
        self.held_button = self._button("counter.held", " (F4)", self.show_held, row)
        self.discard_button = self._button("counter.discard", " (F8)", self.discard_bill, row)
        self.delete_button = self._button("counter.delete_line", " (Del)", self.delete_selected_line, row)
        self.pay_button = self._button("counter.pay", " (F12)", self.pay, row)
        self.pay_button.setStyleSheet("font-weight: bold; padding: 8px 18px;")
        layout.addLayout(row)
        layout.addWidget(self.status_label)

        self.shortcut_keys = {}
        for key, handler in (("F2", self.pick_customer), ("F3", self.hold_bill), ("F4", self.show_held),
                             ("F5", self.apply_discount), ("F8", self.discard_bill),
                             ("Del", self.delete_selected_line), ("F12", self.pay)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
            self.shortcut_keys[key] = shortcut

        self.bind(self.entry, "counter.entry_hint", "setPlaceholderText")
        self.retranslate()

    def _button(self, key, suffix, handler, row):
        button = QPushButton()
        self.bind(button, key, suffix=suffix)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    # --- Screen protocol ------------------------------------------------------
    def retranslate(self):
        super().retranslate()
        self._render()

    def refresh(self):
        self._render()
        self.entry.setFocus()

    def apply_read_only(self, read_only):
        for widget in (self.entry, self.customer_button, self.discount_button, self.hold_button,
                       self.held_button, self.discard_button, self.delete_button, self.pay_button):
            widget.setEnabled(not read_only)

    # --- input -----------------------------------------------------------------
    def _on_enter(self):
        text = self.entry.text()
        self.entry.clear()
        self.submit_text(text)

    def submit_text(self, text):
        try:
            self._handle(self.controller.submit(text))
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._render()
            self.entry.setFocus()

    def _handle(self, entry):
        kind = entry.kind
        if kind == "pick":
            item_id = self._ask_pick(entry.items)
            if item_id is not None:
                item = next(i for i in entry.items if i["id"] == item_id)
                self._handle(self.controller.add(item, entry.qty_milli, explicit_qty=entry.explicit_qty))
        elif kind == "weight":
            qty = self._ask_qty(entry.item)
            if qty is not None:
                self._handle(self.controller.add(entry.item, qty, explicit_qty=True))
        elif kind == "serial":
            serial = self._ask_serial(entry.item)
            if serial:
                self._handle(self.controller.add(entry.item, 1000, serial=serial))
        elif kind == "new_item":
            values = self._ask_new_item(entry.text)
            if values is not None:
                item = items.get_item(self.session.conn, items.create_item(self.session.conn, **values))
                self._handle(self.controller.add(item, entry.qty_milli, explicit_qty=entry.explicit_qty))

    # --- actions ----------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._render()
            self.entry.setFocus()

    def _selected_line_id(self):
        rows = self.table.selectionModel().selectedRows()
        index = rows[0] if rows else self.table.currentIndex()
        return self.model.id_at(index.row()) if index.isValid() else None

    def pick_customer(self):
        def run():
            answer = self._ask_customer()
            if answer is None:
                return
            action, party_id = answer
            self.controller.set_customer(party_id if action == "set" else None)
        self._guarded(run)

    def apply_discount(self):
        def run():
            line_id = self._selected_line_id()
            if line_id is None:
                return
            line = next(l for l in self.controller.detail()["lines"] if l["id"] == line_id)
            max_paise = (line["rate_paise"] * line["qty_milli"] + 500) // 1000  # the undiscounted amount
            paise = self._ask_discount(max_paise)
            if paise is not None:
                self.controller.set_discount(line_id, paise)
        self._guarded(run)

    def delete_selected_line(self):
        def run():
            line_id = self._selected_line_id()
            if line_id is not None:
                self.controller.remove_line(line_id)
        self._guarded(run)

    def hold_bill(self):
        self._guarded(self.controller.hold)

    def show_held(self):
        def run():
            answer = self._ask_held(self.controller.held_bills())
            if answer is None:
                return
            action, bill_id = answer
            if action == "resume":
                self.controller.resume(bill_id)
            elif action == "discard":
                billing.cancel_held(self.session.conn, bill_id)
        self._guarded(run)

    def discard_bill(self):
        def run():
            if self.controller.bill_id is not None and self._confirm("counter.discard_confirm"):
                self.controller.discard()
        self._guarded(run)

    def pay(self):
        def run():
            detail = self.controller.detail()
            if not detail or not detail["lines"]:
                return
            total = detail["bill"]["total_paise"]
            party_id = detail["bill"]["party_id"]
            payments = self._ask_payments(total, party_id)
            if payments is None:
                return
            bill_id, bill_no = self.controller.pay(payments)
            self.last_bill_id = bill_id
            self.status_label.setText(tr("counter.saved", bill_no=bill_no))
            self.sale_completed.emit(bill_id)
        self._guarded(run)

    # --- drawing -----------------------------------------------------------------
    def _render(self):
        detail = self.controller.detail()
        if not detail:
            self.model.set_rows([])
            self.total_label.setText(fmt.rupees(0))
            self.tax_label.setText("")
            self.customer_label.setText(tr("counter.walk_in_label"))
            return
        rows, ids = [], []
        for line in detail["lines"]:
            name = line["item_name"] + (f"  [{line['serial']}]" if line["serial"] else "")
            qty = fmt.qty(line["qty_milli"]) + (f" {line['unit']}" if line["tracking"] == "weighed" else "")
            rows.append((name, qty, fmt.rupees(line["rate_paise"]),
                         fmt.rupees(line["discount_paise"]) if line["discount_paise"] else "",
                         f"{line['gst_rate_bp'] / 100:g}%" if detail["bill"]["gst_mode"] == "gst" else "",
                         fmt.rupees(line["total_paise"])))
            ids.append(line["id"])
        self.model.set_rows(rows, ids, right_cols=(1, 2, 3, 4, 5))
        bill = detail["bill"]
        self.total_label.setText(fmt.rupees(bill["total_paise"]))
        parts = []
        if bill["gst_mode"] == "gst":
            for key, column in (("tax.cgst", "cgst_paise"), ("tax.sgst", "sgst_paise"), ("tax.igst", "igst_paise")):
                if bill[column]:
                    parts.append(f"{tr(key)} {fmt.rupees(bill[column])}")
        if bill["round_off_paise"]:
            parts.append(f"{tr('bill.round_off')} {fmt.rupees(bill['round_off_paise'])}")
        self.tax_label.setText("    ".join(parts))
        party = detail["party"]
        self.customer_label.setText(tr("counter.customer_set", name=party["name"]) if party
                                    else tr("counter.walk_in_label"))

    # --- prompts (replaced by tests; each returns None when the user cancels) ------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_pick(self, rows):
        dialog = dialogs.PickItemDialog(rows, self)
        return dialog.selected_item_id() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_qty(self, item):
        dialog = dialogs.QtyDialog(item["name"], self)
        return dialog.qty_milli() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_serial(self, item):
        dialog = dialogs.SerialDialog(item["name"], self)
        return dialog.serial() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_new_item(self, text):
        dialog = dialogs.QuickAddDialog(text, segments.template_settings(self.session.conn), self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_customer(self):
        dialog = dialogs.CustomerDialog(self.session.conn, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return ("clear", None) if dialog.cleared() else (("set", dialog.party_id()) if dialog.party_id() else None)

    def _ask_discount(self, max_paise):
        dialog = dialogs.DiscountDialog(max_paise, self)
        return dialog.discount_paise() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_held(self, rows):
        dialog = dialogs.HeldBillsDialog(rows, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.action() is None:
            return None
        return dialog.action(), dialog.selected_bill_id()

    def _ask_payments(self, total_paise, party_id):
        features = segments.template_settings(self.session.conn).get("features", {})
        dialog = dialogs.PayDialog(total_paise, party_id is not None, features, self)
        return dialog.payments() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _confirm(self, key):
        answer = QMessageBox.question(self, "", tr(key),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes
```
Replace the whole of `retail_ui/screens/registry.py` with:
```python
from retail_ui.screens.counter import CounterScreen
from retail_ui.widgets.base import Screen


def all_screens() -> list[type[Screen]]:
    """Navigation order. Each screen task appends its class here."""
    return [CounterScreen]
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_counter.py tests/test_i18n.py -v` then the full suite with `-W error::ResourceWarning`.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the keyboard-first counter screen" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 12: Bill view and print layouts (thermal 58 / 80 mm and A4)

**Files:**
- Create: `retail_ui/printing/__init__.py` (empty), `retail_ui/printing/bill_view.py`, `retail_ui/printing/render.py`, `tests/ui/test_ui_printing.py`
- Modify: `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `billing.get_bill_detail`, `shop.get_shop`, `segments.template_settings`, `fmt`, `i18n.tr`.
- Produces:
  - `bill_view.LAYOUTS = ("thermal_58", "thermal_80", "a4")`; `bill_view.LineView(name, qty, rate, gst, amount, serial)`; `bill_view.BillView` (frozen dataclass: `layout, title, shop_name, shop_address, shop_gstin, footer, bill_no, date, customer_name, customer_phone, customer_gstin, lines, taxable, cgst, sgst, igst, round_off, total, payments, warranty, show_tax`) — **all fields are already-localised display strings**; `bill_view.build_bill_view(conn, bill_id, *, layout=None) -> BillView` (only finished bills; `layout` defaults to the segment template's `bill_layout`; an unknown layout raises `ValueError`).
  - `render.build_document(view) -> QTextDocument`; `render.make_printer(layout, pdf_path=None) -> QPrinter`; `render.print_view(view, printer) -> None`; `render.export_pdf(view, path) -> Path`.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_printing.py`:
```python
import pytest
from PySide6.QtWidgets import QApplication

from retail import i18n, segments
from retail.services import billing, items, parties, shop, stock
from retail_ui.printing import bill_view, render


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def sale(conn, *, name="Soap", price=11800, rate=1800, qty=2000, payments=None, party_id=None, **item_kw):
    item = items.create_item(conn, name=name, sell_price_paise=price, gst_rate_bp=rate, **item_kw)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    billing.add_line(conn, bill_id, item, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, payments or [("cash", total)])
    return bill_id


def test_view_has_localised_display_strings(shop_conn):
    ravi = parties.create_party(shop_conn, name="Ravi", phone="9876543210", gstin=None)
    bill_id = sale(shop_conn, party_id=ravi)
    v = bill_view.build_bill_view(shop_conn, bill_id)
    assert (v.shop_name, v.bill_no, v.customer_name, v.customer_phone) == ("Test Shop", "S000001", "Ravi", "9876543210")
    assert v.title == i18n.tr("print.invoice") and v.show_tax is True
    assert (v.lines[0].name, v.lines[0].qty, v.lines[0].rate, v.lines[0].gst, v.lines[0].amount) == (
        "Soap", "2", "₹118.00", "18%", "₹236.00")
    assert (v.taxable, v.cgst, v.sgst, v.igst, v.total) == ("₹200.00", "₹18.00", "₹18.00", "", "₹236.00")
    assert v.payments == ((i18n.tr("pay.cash"), "₹236.00"),) and v.warranty == ()
    assert v.date and v.date.count("-") == 2


def test_layout_defaults_from_the_template_and_can_be_overridden(shop_conn):
    segments.apply_template(shop_conn, "grocery")        # shop_conn applies no template by itself
    bill_id = sale(shop_conn)
    assert bill_view.build_bill_view(shop_conn, bill_id).layout == "thermal_80"      # grocery
    assert bill_view.build_bill_view(shop_conn, bill_id, layout="thermal_58").layout == "thermal_58"
    segments.apply_template(shop_conn, "electronics")
    assert bill_view.build_bill_view(shop_conn, bill_id).layout == "a4"
    with pytest.raises(ValueError):
        bill_view.build_bill_view(shop_conn, bill_id, layout="poster")


def test_only_finished_bills_can_be_viewed(shop_conn):
    held = billing.start_bill(shop_conn)
    with pytest.raises(billing.BillingError):
        bill_view.build_bill_view(shop_conn, held)


def test_estimate_bill_shows_no_tax_and_an_estimate_title(shop_conn):
    shop.update_shop(shop_conn, gst_enabled=False)
    v = bill_view.build_bill_view(shop_conn, sale(shop_conn))
    assert v.title == i18n.tr("print.estimate") and v.show_tax is False and v.lines[0].gst == ""


def test_return_bill_title_and_positive_amounts(shop_conn):
    bill_id = sale(shop_conn, qty=2000)
    line_id = billing.get_bill(shop_conn, bill_id)["lines"][0]["id"]
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    v = bill_view.build_bill_view(shop_conn, ret)
    assert v.title == i18n.tr("print.return") and v.bill_no == "R000001" and v.total == "₹118.00"


def test_serial_and_warranty_lines(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial", warranty_months=12)
    unit = stock.add_unit(shop_conn, phone, serial="IMEI1")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="imei1")
    billing.finalize(shop_conn, bill_id, [("cash", 40000), ("upi", 60000)])
    v = bill_view.build_bill_view(shop_conn, bill_id)
    assert v.lines[0].serial == "IMEI1" and v.warranty[0][0] == "IMEI1" and v.warranty[0][1].count("-") == 2
    assert [p[0] for p in v.payments] == [i18n.tr("pay.cash"), i18n.tr("pay.upi")]


def test_weighed_quantity_shows_the_unit(shop_conn):
    v = bill_view.build_bill_view(shop_conn, sale(shop_conn, name="Rice", price=6000, rate=0, qty=750,
                                                  unit="kg", tracking="weighed"))
    assert v.lines[0].qty == "0.75 kg"


@pytest.mark.parametrize("layout", bill_view.LAYOUTS)
def test_document_text_contains_the_bill(shop_conn, qtbot, layout):
    bill_id = sale(shop_conn, name="Soap & <b>Co</b>")
    v = bill_view.build_bill_view(shop_conn, bill_id, layout=layout)
    text = render.build_document(v).toPlainText()
    for expected in ("Test Shop", "S000001", "Soap & <b>Co</b>", "₹236.00", i18n.tr("bill.total"),
                     i18n.tr("print.thanks"), i18n.tr("tax.cgst")):
        assert expected in text, expected


def test_document_is_localised(shop_conn, qtbot):
    bill_id = sale(shop_conn)
    i18n.set_language("hi")
    text = render.build_document(bill_view.build_bill_view(shop_conn, bill_id)).toPlainText()
    assert i18n.tr("bill.total") in text and i18n.tr("print.invoice") in text and "Total" not in text


@pytest.mark.parametrize("layout", bill_view.LAYOUTS)
def test_pdf_export_for_every_layout(shop_conn, qtbot, tmp_path, layout):
    bill_id = sale(shop_conn)
    path = render.export_pdf(bill_view.build_bill_view(shop_conn, bill_id, layout=layout), tmp_path / f"{layout}.pdf")
    data = path.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 1500


def test_very_long_names_and_many_lines_still_render(shop_conn, qtbot, tmp_path):
    bill_id = billing.start_bill(shop_conn)
    for i in range(40):
        item = items.create_item(shop_conn, name=("Very long product name " * 6) + str(i), sell_price_paise=100)
        stock.record(shop_conn, item, 1000, "opening")
        billing.add_line(shop_conn, bill_id, item, 1000)
    total = billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"]
    billing.finalize(shop_conn, bill_id, [("cash", total)])
    for layout in ("thermal_58", "a4"):
        v = bill_view.build_bill_view(shop_conn, bill_id, layout=layout)
        doc = render.build_document(v)
        assert doc.toPlainText().count("Very long product name") == 40 * 6    # the phrase is repeated 6x per name
        assert render.export_pdf(v, tmp_path / f"{layout}.pdf").stat().st_size > 1500


def test_printer_page_sizes(qtbot):
    from PySide6.QtGui import QPageSize
    a4 = render.make_printer("a4")
    assert a4.pageLayout().pageSize().id() == QPageSize.PageSizeId.A4
    for layout, width in (("thermal_58", 58.0), ("thermal_80", 80.0)):
        size = render.make_printer(layout).pageLayout().pageSize().size(QPageSize.Unit.Millimeter)
        assert abs(size.width() - width) < 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_printing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.printing'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task12.json`:
```json
{
  "print.invoice": {"en": "Tax Invoice", "hi": "कर चालान (टैक्स इनवॉइस)", "te": "పన్ను ఇన్వాయిస్"},
  "print.estimate": {"en": "Estimate", "hi": "अनुमान बिल", "te": "అంచనా బిల్లు"},
  "print.return": {"en": "Sale Return", "hi": "बिक्री वापसी", "te": "అమ్మకం వాపసు"},
  "print.bill_no": {"en": "Bill no.", "hi": "बिल नं.", "te": "బిల్లు నం."},
  "print.paid_by": {"en": "Paid by", "hi": "भुगतान का तरीका", "te": "చెల్లింపు విధానం"},
  "print.warranty": {"en": "Warranty till", "hi": "वारंटी तक", "te": "వారంటీ వరకు"},
  "print.thanks": {"en": "Thank you! Visit again.", "hi": "धन्यवाद! फिर पधारें।", "te": "ధన్యవాదాలు! మళ్లీ రండి."},
  "tax.taxable": {"en": "Taxable value", "hi": "करयोग्य मूल्य", "te": "పన్ను విధించదగిన విలువ"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task12.json`

- [ ] **Step 4: Implement**

`retail_ui/printing/bill_view.py`:
```python
"""Everything a printed or sent bill shows, as ready-to-print (already localised) strings."""
from dataclasses import dataclass

from retail import segments
from retail.i18n import tr
from retail.services import billing, shop
from retail_ui import fmt

LAYOUTS = ("thermal_58", "thermal_80", "a4")


@dataclass(frozen=True)
class LineView:
    name: str
    qty: str
    rate: str
    gst: str
    amount: str
    serial: str


@dataclass(frozen=True)
class BillView:
    layout: str
    title: str
    shop_name: str
    shop_address: str
    shop_gstin: str
    footer: str
    bill_no: str
    date: str
    customer_name: str
    customer_phone: str
    customer_gstin: str
    lines: tuple
    taxable: str
    cgst: str
    sgst: str
    igst: str
    round_off: str
    total: str
    payments: tuple     # ((payment-mode label, amount), ...)
    warranty: tuple     # ((serial, valid-until date), ...)
    show_tax: bool


def _money_or_blank(paise):
    return fmt.rupees(paise) if paise else ""


def build_bill_view(conn, bill_id, *, layout=None) -> BillView:
    detail = billing.get_bill_detail(conn, bill_id)
    bill = detail["bill"]
    if bill["status"] != "final":
        raise billing.BillingError("Only a finished bill can be printed")
    if layout is None:
        layout = segments.template_settings(conn).get("bill_layout", "a4")
    if layout not in LAYOUTS:
        raise ValueError(f"Unknown print layout {layout!r}")
    s = shop.get_shop(conn)
    show_tax = bill["gst_mode"] == "gst"
    if bill["kind"] == "sale_return":
        title = tr("print.return")
    else:
        title = tr("print.invoice") if show_tax else tr("print.estimate")
    party = detail["party"]
    lines = tuple(
        LineView(
            name=l["item_name"],
            qty=fmt.qty(l["qty_milli"]) + (f" {l['unit']}" if l["tracking"] == "weighed" else ""),
            rate=fmt.rupees(l["rate_paise"]),
            gst=f"{l['gst_rate_bp'] / 100:g}%" if show_tax and l["gst_rate_bp"] else "",
            amount=fmt.rupees(l["total_paise"]),
            serial=l["serial"] or "",
        )
        for l in detail["lines"]
    )
    return BillView(
        layout=layout, title=title,
        shop_name=s["name"], shop_address=s["address"], shop_gstin=s["gstin"] or "", footer=s["bill_footer"],
        bill_no=bill["bill_no"], date=fmt.date_text(bill["finalized_at"]),
        customer_name=party["name"] if party else "",
        customer_phone=(party["phone"] or "") if party else "",
        customer_gstin=(party["gstin"] or "") if party else "",
        lines=lines,
        taxable=fmt.rupees(bill["taxable_paise"]) if show_tax else "",
        cgst=_money_or_blank(bill["cgst_paise"]) if show_tax else "",
        sgst=_money_or_blank(bill["sgst_paise"]) if show_tax else "",
        igst=_money_or_blank(bill["igst_paise"]) if show_tax else "",
        round_off=_money_or_blank(bill["round_off_paise"]),
        total=fmt.rupees(bill["total_paise"]),
        payments=tuple((tr(f"pay.{p['mode']}"), fmt.rupees(p["amount_paise"])) for p in detail["payments"]),
        warranty=tuple((w["serial"], fmt.date_text(w["end_date"])) for w in detail["warranties"]),
        show_tax=show_tax,
    )
```

`retail_ui/printing/render.py`:
```python
from html import escape as e
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from retail.i18n import tr

_WIDTH_MM = {"thermal_58": 58.0, "thermal_80": 80.0}


def _totals(v):
    rows = []
    if v.show_tax:
        rows.append((tr("tax.taxable"), v.taxable))
        for key, value in (("tax.cgst", v.cgst), ("tax.sgst", v.sgst), ("tax.igst", v.igst)):
            if value:
                rows.append((tr(key), value))
    if v.round_off:
        rows.append((tr("bill.round_off"), v.round_off))
    rows.append((tr("bill.total"), v.total))
    return rows


def _thermal_html(v):
    size = 7 if v.layout == "thermal_58" else 8
    out = [f"<div style='font-size:{size}pt;'>",
           f"<p align='center'><b>{e(v.shop_name)}</b><br>{e(v.shop_address)}"]
    if v.shop_gstin:
        out.append(f"<br>{e(tr('tax.gstin'))}: {e(v.shop_gstin)}")
    out.append(f"</p><hr><p align='center'><b>{e(v.title)}</b></p>")
    out.append(f"<p>{e(tr('print.bill_no'))}: {e(v.bill_no)}<br>{e(tr('common.date'))}: {e(v.date)}")
    if v.customer_name:
        out.append(f"<br>{e(tr('bill.customer'))}: {e(v.customer_name)}")
    out.append("</p><hr><table width='100%' cellspacing='0'>")
    for line in v.lines:
        name = e(line.name)
        if line.serial:
            name += f"<br>{e(tr('trk.serial'))}: {e(line.serial)}"
        out.append(f"<tr><td colspan='2'>{name}</td></tr>")
        out.append(f"<tr><td>{e(line.qty)} x {e(line.rate)}</td>"
                   f"<td align='right'>{e(line.amount)}</td></tr>")
    out.append("</table><hr><table width='100%' cellspacing='0'>")
    for label, value in _totals(v):
        out.append(f"<tr><td>{e(label)}</td><td align='right'><b>{e(value)}</b></td></tr>")
    out.append("</table>")
    if v.payments:
        paid = ", ".join(f"{label} {amount}" for label, amount in v.payments)
        out.append(f"<hr><p>{e(tr('print.paid_by'))}: {e(paid)}</p>")
    for serial, until in v.warranty:
        out.append(f"<p>{e(serial)}: {e(tr('print.warranty'))} {e(until)}</p>")
    if v.footer:
        out.append(f"<p align='center'>{e(v.footer)}</p>")
    out.append(f"<p align='center'>{e(tr('print.thanks'))}</p></div>")
    return "".join(out)


def _a4_html(v):
    out = ["<div style='font-size:10pt;'>",
           f"<h2>{e(v.shop_name)}</h2><p>{e(v.shop_address)}"]
    if v.shop_gstin:
        out.append(f"<br>{e(tr('tax.gstin'))}: {e(v.shop_gstin)}")
    out.append(f"</p><h3>{e(v.title)}</h3>")
    out.append(f"<p>{e(tr('print.bill_no'))}: <b>{e(v.bill_no)}</b> &nbsp;&nbsp; "
               f"{e(tr('common.date'))}: {e(v.date)}</p>")
    if v.customer_name:
        extra = " ".join(x for x in (v.customer_phone, f"{tr('tax.gstin')}: {v.customer_gstin}"
                                     if v.customer_gstin else "") if x)
        out.append(f"<p>{e(tr('bill.customer'))}: <b>{e(v.customer_name)}</b> {e(extra)}</p>")
    out.append("<table width='100%' border='1' cellspacing='0' cellpadding='4'><tr>"
               f"<th>#</th><th align='left'>{e(tr('bill.item'))}</th><th>{e(tr('bill.qty'))}</th>"
               f"<th>{e(tr('bill.rate'))}</th><th>{e(tr('counter.gst'))}</th><th>{e(tr('bill.total'))}</th></tr>")
    for i, line in enumerate(v.lines, 1):
        name = e(line.name)
        if line.serial:
            name += f"<br>{e(tr('trk.serial'))}: {e(line.serial)}"
        out.append(f"<tr><td align='right'>{i}</td><td>{name}</td><td align='right'>{e(line.qty)}</td>"
                   f"<td align='right'>{e(line.rate)}</td><td align='right'>{e(line.gst)}</td>"
                   f"<td align='right'>{e(line.amount)}</td></tr>")
    out.append("</table><br><table align='right' cellspacing='0' cellpadding='3'>")
    for label, value in _totals(v):
        out.append(f"<tr><td>{e(label)}</td><td align='right'><b>{e(value)}</b></td></tr>")
    out.append("</table><br clear='all'>")
    if v.payments:
        paid = ", ".join(f"{label} {amount}" for label, amount in v.payments)
        out.append(f"<p>{e(tr('print.paid_by'))}: {e(paid)}</p>")
    for serial, until in v.warranty:
        out.append(f"<p>{e(tr('trk.serial'))} {e(serial)} — {e(tr('print.warranty'))} {e(until)}</p>")
    if v.footer:
        out.append(f"<p>{e(v.footer)}</p>")
    out.append(f"<p align='center'>{e(tr('print.thanks'))}</p></div>")
    return "".join(out)


def build_document(view) -> QTextDocument:
    doc = QTextDocument()
    app = QApplication.instance()
    if app is not None:
        doc.setDefaultFont(app.font())      # the per-language font chosen at startup
    doc.setHtml(_a4_html(view) if view.layout == "a4" else _thermal_html(view))
    return doc


def make_printer(layout, pdf_path=None) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if pdf_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(pdf_path))
    if layout == "a4":
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        margin = 12.0
    else:
        printer.setPageSize(QPageSize(QSizeF(_WIDTH_MM[layout], 297.0), QPageSize.Unit.Millimeter))
        margin = 2.0
    printer.setPageMargins(QMarginsF(margin, margin, margin, margin), QPageLayout.Unit.Millimeter)
    return printer


def print_view(view, printer) -> None:
    doc = build_document(view)
    doc.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
    doc.print_(printer)


def export_pdf(view, path) -> Path:
    path = Path(path)
    printer = make_printer(view.layout, pdf_path=path)
    print_view(view, printer)
    del printer  # flush and close the file
    return path
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_printing.py tests/test_i18n.py -v`
Expected: all PASS. (If `QTextDocument.print_` is named differently in the installed PySide6, use whichever of `print_`/`print` exists; behaviour is identical.)

```bash
git add -A
git commit -m "feat: add the localised bill view and thermal/A4 print layouts with PDF export" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: WhatsApp bills

**Files:**
- Create: `retail_ui/whatsapp.py`, `tests/ui/test_ui_whatsapp.py`
- Modify: `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `BillView`.
- Produces: `whatsapp.normalise_phone(raw, default_cc="91") -> str | None`; `whatsapp.build_message(view, *, max_lines=20) -> str` (customer and bill details only — shop name, bill number, date, customer name, line items, total, how it was paid; never purchase prices or the shop's GSTIN); `whatsapp.bill_url(view, raw_phone) -> str | None` (a `https://wa.me/<digits>?text=<percent-encoded>` link kept under 1,900 characters by shortening the item list); `whatsapp.open_whatsapp(view, raw_phone, opener=None) -> bool` (`False` when there is no usable number).

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_whatsapp.py`:
```python
import urllib.parse

import pytest

from retail import i18n
from retail_ui import whatsapp
from retail_ui.printing.bill_view import BillView, LineView


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def view(n_lines=2, customer="Ravi", payments=(("Cash", "₹236.00"),)):
    lines = tuple(LineView(f"Item {i}", "2", "₹100.00", "18%", "₹200.00", "") for i in range(n_lines))
    return BillView(layout="a4", title="Tax Invoice", shop_name="Sri Kirana", shop_address="Main Rd",
                    shop_gstin="36ABCDE1234F1Z5", footer="", bill_no="S000007", date="30-09-2026 10:05",
                    customer_name=customer, customer_phone="9876543210", customer_gstin="", lines=lines,
                    taxable="₹200.00", cgst="₹18.00", sgst="₹18.00", igst="", round_off="", total="₹236.00",
                    payments=payments, warranty=(), show_tax=True)


@pytest.mark.parametrize("raw,expected", [
    ("98765 43210", "919876543210"), ("+91 98765-43210", "919876543210"), ("09876543210", "919876543210"),
    ("919876543210", "919876543210"), ("442071234567", "442071234567"), ("", None), (None, None), ("abc", None),
])
def test_normalise_phone(raw, expected):
    assert whatsapp.normalise_phone(raw) == expected


def test_message_has_customer_and_bill_details_only():
    text = whatsapp.build_message(view())
    for expected in ("Sri Kirana", "S000007", "30-09-2026", "Ravi", "Item 0", "₹200.00", "₹236.00", "Cash"):
        assert expected in text, expected
    assert "36ABCDE1234F1Z5" not in text and "GSTIN" not in text      # the shop's tax id is not sent
    assert "Main Rd" not in text


def test_message_without_a_customer_has_no_customer_line():
    assert "None" not in whatsapp.build_message(view(customer=""))


def test_long_bills_are_shortened_with_a_localised_note():
    text = whatsapp.build_message(view(n_lines=30), max_lines=5)
    assert text.count("Item ") == 5 and i18n.tr("whatsapp.more", count=25) in text


def test_url_is_percent_encoded_and_addressed():
    url = whatsapp.bill_url(view(), "98765 43210")
    assert url.startswith("https://wa.me/919876543210?text=")
    assert urllib.parse.unquote(url.split("text=", 1)[1]) == whatsapp.build_message(view())


def test_url_stays_short_even_for_huge_bills_and_non_latin_text():
    i18n.set_language("hi")
    url = whatsapp.bill_url(view(n_lines=120, customer="रवि"), "9876543210")
    assert len(url) <= 1900 and "S000007" in urllib.parse.unquote(url)


def test_no_number_gives_no_url():
    assert whatsapp.bill_url(view(), "") is None and whatsapp.bill_url(view(), "abc") is None


def test_open_whatsapp_uses_the_opener_and_reports_failure():
    opened = []
    assert whatsapp.open_whatsapp(view(), "9876543210", opener=opened.append) is True
    assert opened[0].startswith("https://wa.me/919876543210?text=")
    assert whatsapp.open_whatsapp(view(), "", opener=opened.append) is False and len(opened) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_whatsapp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.whatsapp'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task13.json`:
```json
{
  "whatsapp.more": {"en": "…and {count} more items", "hi": "…और {count} वस्तुएँ", "te": "…ఇంకా {count} వస్తువులు"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task13.json`

- [ ] **Step 4: Implement**

`retail_ui/whatsapp.py`:
```python
"""Send a finished bill through WhatsApp click-to-chat (wa.me). The message is customer and bill
details only; it never contains purchase prices or the shop's own tax id."""
import re
import urllib.parse

from retail.i18n import tr

MAX_URL = 1900


def normalise_phone(raw, default_cc="91"):
    """Digits-only with a country code (a bare 10-digit number is assumed to be Indian)."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None
    if len(digits) == 10:
        return default_cc + digits
    if len(digits) == 11 and digits.startswith("0"):
        return default_cc + digits[1:]
    return digits


def build_message(view, *, max_lines=20):
    out = [view.shop_name, f"{tr('print.bill_no')}: {view.bill_no}   {view.date}"]
    if view.customer_name:
        out.append(f"{tr('bill.customer')}: {view.customer_name}")
    out.append("-" * 16)
    shown = view.lines[:max_lines]
    for line in shown:
        out.append(f"{line.name} x {line.qty} = {line.amount}")
    hidden = len(view.lines) - len(shown)
    if hidden > 0:
        out.append(tr("whatsapp.more", count=hidden))
    out.append("-" * 16)
    out.append(f"{tr('bill.total')}: {view.total}")
    for label, amount in view.payments:
        out.append(f"{label}: {amount}")
    out.append(tr("print.thanks"))
    return "\n".join(out)


def bill_url(view, raw_phone):
    phone = normalise_phone(raw_phone)
    if not phone:
        return None
    url = ""
    for limit in (20, 12, 8, 5, 0):  # shorten the item list until the link is short enough
        text = build_message(view, max_lines=limit)
        url = f"https://wa.me/{phone}?text={urllib.parse.quote(text)}"
        if len(url) <= MAX_URL:
            break
    return url


def open_whatsapp(view, raw_phone, opener=None):
    url = bill_url(view, raw_phone)
    if url is None:
        return False
    if opener is None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        def opener(link):
            QDesktopServices.openUrl(QUrl(link))
    opener(url)
    return True
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_whatsapp.py tests/test_i18n.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add WhatsApp bill links (customer and bill details only)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Bills screen (history, reprint, PDF, WhatsApp, returns) and printing from the counter

**Files:**
- Create: `retail_ui/print_ui.py`, `retail_ui/screens/bills.py`, `tests/ui/test_ui_bills.py`
- Modify: `retail_ui/screens/registry.py`, `retail_ui/screens/counter.py`, `tests/ui/test_ui_counter.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `billing.list_bills/get_bill_detail/returnable_lines/create_return`, `bill_view.build_bill_view`, `render.*`, `whatsapp.*`, `Screen`, `RowsModel`.
- Produces:
  - `print_ui.preview_bill(parent, session, bill_id) -> None` (print preview dialog; layout from `session.settings.print_layout` or the template's), `print_ui.save_pdf(parent, session, bill_id, path=None) -> Path | None` (asks for a path when `None`), `print_ui.send_whatsapp(parent, session, bill_id, phone=None, opener=None) -> bool` (uses the customer's phone, otherwise asks).
  - `bills.ReturnDialog(lines, has_customer, parent=None)` → `returns() -> [(line_id, qty_milli)]`, `refund_mode() -> str`; widgets `rows` (line_id → `QLineEdit` or `QCheckBox`), `refund_box`, `ok_button`.
  - `bills.BillsScreen(session)` (`nav_key = "nav.bills"`) with `from_edit, to_edit, search_edit, table, model, preview_button, pdf_button, whatsapp_button, return_button`; hooks `_ask_return(lines, has_customer) -> (returns, mode) | None`; actions `preview()`, `save_pdf()`, `send_whatsapp()`, `return_items()`.
  - `CounterScreen` gains `print_button`, `print_last()`, shortcut `F10`; with `settings.auto_print` a completed sale opens the preview.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_bills.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import i18n
from retail.services import billing, items, parties, stock
from retail_ui import print_ui
from retail_ui.screens import bills
from retail_ui.screens.bills import BillsScreen, ReturnDialog


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def sell(conn, qty=2000, party_id=None, name="Soap"):
    item = items.create_item(conn, name=name, sell_price_paise=1000)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    line_id = billing.add_line(conn, bill_id, item, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, [("cash", total)])
    return bill_id, line_id


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = BillsScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def cell(sc, row, col):
    return sc.model.data(sc.model.index(row, col))


def test_lists_todays_final_bills_newest_first(screen):
    a, _ = sell(screen.session.conn, name="A")
    b, _ = sell(screen.session.conn, name="B")
    billing.start_bill(screen.session.conn)                      # held: never listed
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["S000002", "S000001"]
    assert cell(screen, 0, 2) == i18n.tr("bills.sale") and cell(screen, 0, 4) == "₹20.00"
    assert a and b


def test_search_filters_by_number_or_customer(screen):
    ravi = parties.create_party(screen.session.conn, name="Ravi")
    sell(screen.session.conn, party_id=ravi, name="A")
    sell(screen.session.conn, name="B")
    screen.search_edit.setText("ravi")
    screen.refresh()
    assert screen.model.rowCount() == 1 and cell(screen, 0, 3) == "Ravi"
    screen.search_edit.setText("s000002")
    screen.refresh()
    assert cell(screen, 0, 0) == "S000002" and cell(screen, 0, 3) == i18n.tr("counter.walk_in_label")


def test_a_bad_date_range_is_reported_not_raised(screen):
    from PySide6.QtCore import QDate
    screen.from_edit.setDate(QDate(2030, 1, 1))
    screen.to_edit.setDate(QDate(2020, 1, 1))
    screen.refresh()
    assert len(screen.errors) == 1 and screen.model.rowCount() == 0


def test_print_pdf_and_whatsapp_actions_use_the_selected_bill(screen, monkeypatch):
    bill_id, _ = sell(screen.session.conn)
    screen.refresh()
    screen.table.selectRow(0)
    calls = []
    monkeypatch.setattr(bills.print_ui, "preview_bill", lambda parent, session, bid: calls.append(("print", bid)))
    monkeypatch.setattr(bills.print_ui, "save_pdf", lambda parent, session, bid, path=None: calls.append(("pdf", bid)))
    monkeypatch.setattr(bills.print_ui, "send_whatsapp", lambda parent, session, bid, **k: calls.append(("wa", bid)))
    screen.preview()
    screen.save_pdf()
    screen.send_whatsapp()
    assert calls == [("print", bill_id), ("pdf", bill_id), ("wa", bill_id)]


def test_actions_do_nothing_without_a_selection(screen, monkeypatch):
    monkeypatch.setattr(bills.print_ui, "preview_bill", lambda *a, **k: pytest.fail("no bill selected"))
    screen.preview()
    screen._ask_return = lambda lines, has_customer: pytest.fail("no bill selected")
    screen.return_items()


def test_return_flow_creates_a_return_and_refreshes(screen):
    bill_id, line_id = sell(screen.session.conn, qty=3000)
    screen.refresh()
    screen.table.selectRow(0)
    asked = []
    screen._ask_return = lambda lines, has_customer: asked.append((lines, has_customer)) or ([(line_id, 1000)], "cash")
    screen.return_items()
    assert asked[0][0][0]["remaining_milli"] == 3000 and asked[0][1] is False
    assert screen.model.rowCount() == 2 and cell(screen, 0, 2) == i18n.tr("bills.return")
    assert stock.on_hand(screen.session.conn, items.list_items(screen.session.conn)[0]["id"]) == 48_000


def test_returning_a_return_bill_is_reported(screen):
    bill_id, line_id = sell(screen.session.conn)
    billing.create_return(screen.session.conn, bill_id, [(line_id, 1000)])
    screen.refresh()
    screen.table.selectRow(0)                                     # the newest row is the return
    screen._ask_return = lambda *a: pytest.fail("a return bill cannot be returned")
    screen.return_items()
    assert len(screen.errors) == 1


def test_read_only_disables_returns_but_not_printing(screen):
    screen.apply_read_only(True)
    assert not screen.return_button.isEnabled()
    assert screen.preview_button.isEnabled() and screen.pdf_button.isEnabled() and screen.whatsapp_button.isEnabled()


def test_language_switch_retranslates_headers(screen):
    i18n.set_language("te")
    screen.retranslate()
    assert screen.model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("print.bill_no")


# ---- the return dialog ---------------------------------------------------------

def lines(*specs):
    return [{"line_id": i + 1, "item_id": i + 1, "item_name": n, "tracking": t, "qty_milli": q,
             "returned_milli": r, "remaining_milli": q - r, "total_paise": 100} for i, (n, t, q, r) in enumerate(specs)]


def test_return_dialog_collects_quantities_and_validates(qtbot):
    d = ReturnDialog(lines(("Soap", "none", 3000, 0), ("Phone", "serial", 1000, 0), ("Tea", "none", 1000, 1000)),
                     has_customer=False)
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled() and d.returns() == []
    d.rows[1].setText("2")
    assert d.returns() == [(1, 2000)] and d.ok_button.isEnabled()
    d.rows[1].setText("4")                                        # more than was sold
    assert not d.ok_button.isEnabled()
    d.rows[1].setText("abc")
    assert not d.ok_button.isEnabled()
    d.rows[1].setText("")
    d.rows[2].setChecked(True)                                    # serial units are returned whole
    assert d.returns() == [(2, 1000)] and d.ok_button.isEnabled()
    assert 3 not in d.rows                                        # nothing left to return on the Tea line


def test_return_dialog_refund_modes(qtbot):
    plain = ReturnDialog(lines(("Soap", "none", 1000, 0)), has_customer=False)
    qtbot.addWidget(plain)
    assert [plain.refund_box.itemData(i) for i in range(plain.refund_box.count())] == ["cash", "upi", "card"]
    with_customer = ReturnDialog(lines(("Soap", "none", 1000, 0)), has_customer=True)
    qtbot.addWidget(with_customer)
    assert "credit" in [with_customer.refund_box.itemData(i) for i in range(with_customer.refund_box.count())]


# ---- print_ui ---------------------------------------------------------------------

def test_save_pdf_writes_a_pdf_to_the_given_path(make_session, qtbot, tmp_path):
    session = make_session()
    bill_id, _ = sell(session.conn)
    path = print_ui.save_pdf(None, session, bill_id, path=tmp_path / "b.pdf")
    assert path.read_bytes().startswith(b"%PDF")


def test_send_whatsapp_prefers_the_customer_phone(make_session, qtbot):
    session = make_session()
    ravi = parties.create_party(session.conn, name="Ravi", phone="98765 43210")
    bill_id, _ = sell(session.conn, party_id=ravi)
    opened = []
    assert print_ui.send_whatsapp(None, session, bill_id, opener=opened.append) is True
    assert opened[0].startswith("https://wa.me/919876543210?text=")


def test_print_layout_setting_overrides_the_template(make_session, qtbot, tmp_path):
    session = make_session()
    session.settings.print_layout = "thermal_58"
    bill_id, _ = sell(session.conn)
    assert print_ui.layout_for(session) == "thermal_58"
    session.settings.print_layout = ""
    assert print_ui.layout_for(session) is None
```
Append to `tests/ui/test_ui_counter.py`:
```python
def test_print_last_opens_the_preview_for_the_last_bill(screen, monkeypatch):
    from retail_ui.screens import counter as counter_module
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    printed = []
    monkeypatch.setattr(counter_module.print_ui, "preview_bill", lambda parent, session, bid: printed.append(bid))
    screen.print_last()
    assert printed == []                                          # nothing sold yet
    type_and_enter(screen, "8901")
    screen._ask_payments = lambda total, party_id: [("cash", total)]
    screen.pay()
    assert printed == []                                          # auto-print is off by default
    screen.print_last()
    assert printed == [screen.last_bill_id]


def test_auto_print_previews_every_completed_sale(screen, monkeypatch):
    from retail_ui.screens import counter as counter_module
    stocked(screen.session.conn, name="Soap", barcodes=["8901"])
    screen.session.settings.auto_print = True
    printed = []
    monkeypatch.setattr(counter_module.print_ui, "preview_bill", lambda parent, session, bid: printed.append(bid))
    type_and_enter(screen, "8901")
    screen._ask_payments = lambda total, party_id: [("cash", total)]
    screen.pay()
    assert printed == [screen.last_bill_id]
```
and change the shortcut assertion in `tests/ui/test_ui_counter.py::test_function_key_shortcuts_are_registered` to `{"F2", "F3", "F4", "F5", "F8", "F10", "Del", "F12"}`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_bills.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.print_ui'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task14.json`:
```json
{
  "bills.type": {"en": "Type", "hi": "प्रकार", "te": "రకం"},
  "bills.sale": {"en": "Sale", "hi": "बिक्री", "te": "అమ్మకం"},
  "bills.return": {"en": "Return", "hi": "वापसी", "te": "వాపసు"},
  "bills.print": {"en": "Print / Preview", "hi": "प्रिंट / प्रीव्यू", "te": "ప్రింట్ / ప్రివ్యూ"},
  "bills.pdf": {"en": "Save as PDF", "hi": "PDF के रूप में सहेजें", "te": "PDF గా సేవ్ చేయండి"},
  "bills.whatsapp": {"en": "Send on WhatsApp", "hi": "WhatsApp पर भेजें", "te": "WhatsApp లో పంపండి"},
  "bills.return_items": {"en": "Return items", "hi": "सामान वापस लें", "te": "సరుకులు వాపసు తీసుకోండి"},
  "bills.refund_mode": {"en": "Refund by", "hi": "रिफ़ंड का तरीका", "te": "రీఫండ్ విధానం"},
  "bills.returned": {"en": "Returned", "hi": "वापस हुआ", "te": "వాపసు అయినది"},
  "bills.remaining": {"en": "Left to return", "hi": "वापसी बाकी", "te": "వాపసు మిగిలినది"},
  "wa.phone_prompt": {"en": "Customer's WhatsApp number", "hi": "ग्राहक का WhatsApp नंबर", "te": "కస్టమర్ WhatsApp నంబర్"},
  "wa.no_phone": {"en": "That is not a usable phone number.", "hi": "यह उपयोगी फ़ोन नंबर नहीं है।", "te": "ఇది సరైన ఫోన్ నంబర్ కాదు."},
  "counter.print_last": {"en": "Print last bill", "hi": "पिछला बिल प्रिंट करें", "te": "చివరి బిల్లు ప్రింట్ చేయండి"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task14.json`

- [ ] **Step 4: Implement**

`retail_ui/print_ui.py`:
```python
from PySide6.QtPrintSupport import QPrintPreviewDialog
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from retail.i18n import tr
from retail_ui import whatsapp
from retail_ui.printing.bill_view import build_bill_view
from retail_ui.printing.render import export_pdf, make_printer, print_view


def layout_for(session):
    """The owner's chosen layout, or None to use the segment template's default."""
    return session.settings.print_layout or None


def _view(session, bill_id):
    return build_bill_view(session.conn, bill_id, layout=layout_for(session))


def preview_bill(parent, session, bill_id):
    view = _view(session, bill_id)
    dialog = QPrintPreviewDialog(make_printer(view.layout), parent)
    dialog.paintRequested.connect(lambda printer: print_view(view, printer))
    dialog.exec()


def save_pdf(parent, session, bill_id, path=None):
    view = _view(session, bill_id)
    if path is None:
        path, _ = QFileDialog.getSaveFileName(parent, tr("bills.pdf"), f"{view.bill_no}.pdf", "PDF (*.pdf)")
        if not path:
            return None
    return export_pdf(view, path)


def send_whatsapp(parent, session, bill_id, phone=None, opener=None):
    view = _view(session, bill_id)
    if phone is None:
        phone = view.customer_phone
    if not whatsapp.normalise_phone(phone):
        phone, accepted = QInputDialog.getText(parent, tr("bills.whatsapp"), tr("wa.phone_prompt"))
        if not accepted:
            return False
    if not whatsapp.open_whatsapp(view, phone, opener=opener):
        QMessageBox.warning(parent, "", tr("wa.no_phone"))
        return False
    return True
```

`retail_ui/screens/bills.py`:
```python
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableView,
                               QVBoxLayout)

from retail.i18n import tr
from retail.services import billing
from retail_ui import fmt, print_ui
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

HEADERS = ["print.bill_no", "common.date", "bills.type", "bill.customer", "bill.total"]


class ReturnDialog(QDialog):
    """One row per original line still holding something to return. Serial units are returned whole."""

    def __init__(self, lines, has_customer, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("bills.return_items"))
        self._lines = {l["line_id"]: l for l in lines if l["remaining_milli"] > 0}
        self.rows = {}
        form = QFormLayout(self)
        for line_id, line in self._lines.items():
            label = (f"{line['item_name']}  ({tr('bills.remaining')}: {fmt.qty(line['remaining_milli'])})")
            if line["tracking"] == "serial":
                widget = QCheckBox()
                widget.toggled.connect(self._check)
            else:
                widget = QLineEdit()
                widget.textChanged.connect(self._check)
            self.rows[line_id] = widget
            form.addRow(label, widget)
        self.refund_box = QComboBox()
        for mode in ("cash", "upi", "card") + (("credit",) if has_customer else ()):
            self.refund_box.addItem(tr(f"pay.{mode}"), mode)
        form.addRow(tr("bills.refund_mode"), self.refund_box)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self._check()

    def _collect(self):
        """[(line_id, qty_milli)] or raises ValueError when any entry is invalid."""
        found = []
        for line_id, widget in self.rows.items():
            line = self._lines[line_id]
            if isinstance(widget, QCheckBox):
                qty = line["remaining_milli"] if widget.isChecked() else 0
            else:
                text = widget.text().strip()
                qty = fmt.parse_qty(text) if text else 0
            if qty > line["remaining_milli"]:
                raise ValueError("more than is left to return")
            if qty:
                found.append((line_id, qty))
        return found

    def _check(self):
        try:
            self.ok_button.setEnabled(bool(self._collect()))
        except ValueError:
            self.ok_button.setEnabled(False)

    def returns(self):
        try:
            return self._collect()
        except ValueError:
            return []

    def refund_mode(self):
        return self.refund_box.currentData()


class BillsScreen(Screen):
    nav_key = "nav.bills"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        today = QDate.currentDate()
        self.from_edit, self.to_edit = QDateEdit(today), QDateEdit(today)
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd-MM-yyyy")
        self.search_edit = QLineEdit()
        self.bind(self.search_edit, "common.search", "setPlaceholderText")
        self.refresh_button = self.bind(QPushButton(), "common.refresh")
        top.addWidget(self.bind(QLabel(), "common.from"))
        top.addWidget(self.from_edit)
        top.addWidget(self.bind(QLabel(), "common.to"))
        top.addWidget(self.to_edit)
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)

        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.preview_button = self._button("bills.print", self.preview, buttons)
        self.pdf_button = self._button("bills.pdf", self.save_pdf, buttons)
        self.whatsapp_button = self._button("bills.whatsapp", self.send_whatsapp, buttons)
        self.return_button = self._button("bills.return_items", self.return_items, buttons)
        layout.addLayout(buttons)

        self.refresh_button.clicked.connect(lambda _=False: self.refresh())
        self.search_edit.returnPressed.connect(self.refresh)

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    # --- Screen protocol ------------------------------------------------------
    def refresh(self):
        try:
            rows = billing.list_bills(self.session.conn, self.from_edit.date().toString(Qt.DateFormat.ISODate),
                                      self.to_edit.date().toString(Qt.DateFormat.ISODate),
                                      search=self.search_edit.text())
        except Exception as exc:
            self.model.set_rows([])
            self._show_error(exc)
            return
        self.model.set_rows(
            [(r["bill_no"], fmt.date_text(r["finalized_at"]),
              tr("bills.return") if r["kind"] == "sale_return" else tr("bills.sale"),
              r["party"] or tr("counter.walk_in_label"), fmt.rupees(r["total_paise"])) for r in rows],
            ids=[r["id"] for r in rows], right_cols=(4,))

    def retranslate(self):
        super().retranslate()
        self.refresh()

    def apply_read_only(self, read_only):
        self.return_button.setEnabled(not read_only)   # printing and sending stay available

    # --- actions ------------------------------------------------------------------
    def _selected_bill_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.id_at(rows[0].row()) if rows else None

    def _run(self, action):
        bill_id = self._selected_bill_id()
        if bill_id is None:
            return
        try:
            action(bill_id)
        except Exception as exc:
            self._show_error(exc)

    def preview(self):
        self._run(lambda bill_id: print_ui.preview_bill(self, self.session, bill_id))

    def save_pdf(self):
        self._run(lambda bill_id: print_ui.save_pdf(self, self.session, bill_id))

    def send_whatsapp(self):
        self._run(lambda bill_id: print_ui.send_whatsapp(self, self.session, bill_id))

    def return_items(self):
        def run(bill_id):
            detail = billing.get_bill_detail(self.session.conn, bill_id)
            lines = billing.returnable_lines(self.session.conn, bill_id)   # raises for a return bill
            answer = self._ask_return(lines, detail["bill"]["party_id"] is not None)
            if answer is None:
                return
            returns, mode = answer
            billing.create_return(self.session.conn, bill_id, returns, refund_mode=mode)
            self.session.notify_changed()
            self.refresh()
        self._run(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_return(self, lines, has_customer):
        dialog = ReturnDialog(lines, has_customer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.returns():
            return None
        return dialog.returns(), dialog.refund_mode()
```

Counter changes in `retail_ui/screens/counter.py`:
1. add `from retail_ui import fmt, print_ui` (replace the existing `from retail_ui import fmt`);
2. after the `self.pay_button` line add `self.print_button = self._button("counter.print_last", " (F10)", self.print_last, row)`;
3. add `("F10", self.print_last),` to the shortcut tuple list (between `("F8", ...)` and `("Del", ...)`);
4. leave `print_button` out of the `apply_read_only` widget tuple (printing the last bill stays available after the licence expires);
5. add the method and the auto-print call:
```python
    def print_last(self):
        if self.last_bill_id is not None:
            self._guarded(lambda: print_ui.preview_bill(self, self.session, self.last_bill_id))
```
and at the end of `pay()`'s inner `run()` (after `self.sale_completed.emit(bill_id)`) add:
```python
            if self.session.settings.auto_print:
                print_ui.preview_bill(self, self.session, bill_id)
```
Replace `retail_ui/screens/registry.py` with:
```python
from retail_ui.screens.bills import BillsScreen
from retail_ui.screens.counter import CounterScreen
from retail_ui.widgets.base import Screen


def all_screens() -> list[type[Screen]]:
    """Navigation order. Each screen task appends its class here."""
    return [CounterScreen, BillsScreen]
```

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_bills.py tests/ui/test_ui_counter.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the bills screen (history, reprint, PDF, WhatsApp, returns) and counter printing" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Items screen

**Files:**
- Create: `retail_ui/screens/items.py`, `tests/ui/test_ui_items.py`
- Modify: `retail/services/items.py` (one helper), `tests/test_support_services.py` (one test), `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Produces: `items.has_stock_history(conn, item_id) -> bool`; `items_screen.ItemDialog(template, item=None, barcodes=(), locked_tracking=False, parent=None)` with widgets `name_edit, sku_edit, hsn_edit, price_edit, buy_edit, gst_box, unit_box, tracking_box, reorder_edit, warranty_spin, barcodes_edit, ok_button` and `values() -> dict` (keys `name, sku, hsn, gst_rate_bp, unit, sell_price_paise, buy_price_paise, reorder_milli, warranty_months, tracking`) and `barcodes() -> list[str]`; `ItemsScreen(session)` (`nav_key = "nav.items"`) with `search_edit, inactive_box, table, model, add_button, edit_button, toggle_button`; hook `_ask_item(item, barcodes, locked_tracking) -> {"values", "barcodes"} | None`; actions `add_item()`, `edit_item()`, `toggle_active()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_support_services.py`:
```python
def test_has_stock_history(shop_conn):
    a = items.create_item(shop_conn, name="A", sell_price_paise=1)
    assert items.has_stock_history(shop_conn, a) is False
    stock.record(shop_conn, a, 1000, "opening")
    assert items.has_stock_history(shop_conn, a) is True
```

`tests/ui/test_ui_items.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import i18n, segments
from retail.services import items, stock
from retail_ui.screens.items import ItemDialog, ItemsScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = ItemsScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def cell(sc, row, col):
    return sc.model.data(sc.model.index(row, col))


def grocery(conn):
    segments.apply_template(conn, "grocery")      # the shop_conn fixture sets no template features
    return segments.template_settings(conn)


def test_dialog_new_item_validation_and_values(shop_conn, qtbot):
    d = ItemDialog(grocery(shop_conn))
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.name_edit.setText(" Soap ")
    d.price_edit.setText("₹118")
    assert d.ok_button.isEnabled()
    d.gst_box.setCurrentIndex(d.gst_box.findData(1800))
    d.sku_edit.setText("S1")
    d.buy_edit.setText("90.50")
    d.reorder_edit.setText("5")
    d.barcodes_edit.setText("111, 222 ,, 111")
    v = d.values()
    assert v == {"name": "Soap", "sku": "S1", "hsn": None, "gst_rate_bp": 1800, "unit": "pcs",
                 "sell_price_paise": 11800, "buy_price_paise": 9050, "reorder_milli": 5000,
                 "warranty_months": 0, "tracking": "none"}
    assert d.barcodes() == ["111", "222"]
    d.buy_edit.setText("x")
    assert not d.ok_button.isEnabled()


def test_dialog_edit_prefills_and_can_lock_tracking(shop_conn, qtbot):
    item_id = items.create_item(shop_conn, name="Rice", sell_price_paise=6000, gst_rate_bp=500, unit="kg",
                                tracking="weighed", sku="R1", hsn="1006", reorder_milli=2500, barcodes=["999"])
    row = items.get_item(shop_conn, item_id)
    d = ItemDialog(grocery(shop_conn), item=row, barcodes=items.item_barcodes(shop_conn, item_id), locked_tracking=True)
    qtbot.addWidget(d)
    assert (d.name_edit.text(), d.sku_edit.text(), d.hsn_edit.text(), d.price_edit.text()) == ("Rice", "R1", "1006", "60.00")
    assert d.gst_box.currentData() == 500 and d.unit_box.currentText() == "kg"
    assert d.tracking_box.currentData() == "weighed" and not d.tracking_box.isEnabled()
    assert d.reorder_edit.text() == "2.5" and d.barcodes_edit.text() == "999"


def test_dialog_keeps_a_gst_rate_that_is_not_in_the_template_slabs(shop_conn, qtbot):
    item_id = items.create_item(shop_conn, name="Old", sell_price_paise=100, gst_rate_bp=1200)
    d = ItemDialog(grocery(shop_conn), item=items.get_item(shop_conn, item_id))
    qtbot.addWidget(d)
    assert d.gst_box.currentData() == 1200


def test_dialog_warranty_field_follows_the_template_feature(shop_conn, qtbot):
    g = ItemDialog(grocery(shop_conn))
    qtbot.addWidget(g)
    assert g.warranty_spin.isHidden()
    segments.apply_template(shop_conn, "electronics")
    e = ItemDialog(segments.template_settings(shop_conn))
    qtbot.addWidget(e)
    assert not e.warranty_spin.isHidden() and e.tracking_box.currentData() == "serial"


def test_screen_lists_items_with_stock_and_highlights_low_stock(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Rice", sell_price_paise=6000, unit="kg", tracking="weighed", reorder_milli=5000)
    b = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, sku="S1")
    stock.record(conn, a, 2000, "opening")
    stock.record(conn, b, 9000, "opening")
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(2)] == ["Rice", "Soap"]
    assert cell(screen, 1, 1) == "S1" and cell(screen, 1, 2) == "₹118.00" and cell(screen, 1, 3) == "18%"
    assert cell(screen, 0, 5) == "2 kg" and cell(screen, 0, 6) == "5 kg"
    assert screen.model.data(screen.model.index(0, 0), Qt.ItemDataRole.BackgroundRole) is not None   # low
    assert screen.model.data(screen.model.index(1, 0), Qt.ItemDataRole.BackgroundRole) is None


def test_search_and_show_inactive(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Rice", sell_price_paise=1)
    items.create_item(conn, name="Soap", sell_price_paise=1)
    items.set_item_active(conn, a, False)
    screen.refresh()
    assert screen.model.rowCount() == 1
    screen.inactive_box.setChecked(True)
    screen.refresh()
    assert screen.model.rowCount() == 2 and i18n.tr("items.inactive") in cell(screen, 0, 0)
    screen.search_edit.setText("soap")
    screen.refresh()
    assert screen.model.rowCount() == 1


def test_add_item_creates_it_with_barcodes(screen):
    values = {"name": "Parle-G", "sku": "P1", "hsn": None, "gst_rate_bp": 500, "unit": "pcs",
              "sell_price_paise": 1000, "buy_price_paise": 800, "reorder_milli": 0, "warranty_months": 0,
              "tracking": "none"}
    screen._ask_item = lambda item, barcodes, locked: {"values": values, "barcodes": ["8901"]}
    screen.add_item()
    assert screen.model.rowCount() == 1 and items.resolve(screen.session.conn, "8901")[0]["name"] == "Parle-G"


def test_edit_item_updates_fields_and_barcodes_and_locks_tracking_after_stock(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Soap", sell_price_paise=100, barcodes=["111"])
    stock.record(conn, a, 1000, "opening")
    screen.refresh()
    screen.table.selectRow(0)
    seen = {}

    def ask(item, barcodes, locked):
        seen.update(name=item["name"], barcodes=barcodes, locked=locked)
        return {"values": {"name": "Soap Big", "sku": "", "hsn": None, "gst_rate_bp": 0, "unit": "pcs",
                           "sell_price_paise": 250, "buy_price_paise": 0, "reorder_milli": 0,
                           "warranty_months": 0, "tracking": "none"}, "barcodes": ["222"]}

    screen._ask_item = ask
    screen.edit_item()
    assert seen == {"name": "Soap", "barcodes": ["111"], "locked": True}
    row = items.get_item(conn, a)
    assert (row["name"], row["sell_price_paise"]) == ("Soap Big", 250) and items.item_barcodes(conn, a) == ["222"]


def test_validation_errors_from_the_engine_are_reported_not_raised(screen):
    conn = screen.session.conn
    items.create_item(conn, name="A", sell_price_paise=1, sku="X")
    values = {"name": "B", "sku": "X", "hsn": None, "gst_rate_bp": 0, "unit": "pcs", "sell_price_paise": 1,
              "buy_price_paise": 0, "reorder_milli": 0, "warranty_months": 0, "tracking": "none"}
    screen._ask_item = lambda item, barcodes, locked: {"values": values, "barcodes": []}
    screen.add_item()
    assert len(screen.errors) == 1 and screen.model.rowCount() == 1


def test_toggle_active_deactivates_and_reactivates(screen):
    a = items.create_item(screen.session.conn, name="Soap", sell_price_paise=1)
    screen.inactive_box.setChecked(True)
    screen.refresh()
    screen.table.selectRow(0)
    screen.toggle_active()
    assert items.get_item(screen.session.conn, a)["active"] == 0
    screen.table.selectRow(0)
    screen.toggle_active()
    assert items.get_item(screen.session.conn, a)["active"] == 1


def test_a_note_appears_when_the_list_is_truncated(screen):
    conn = screen.session.conn
    conn.execute("BEGIN")
    conn.executemany("INSERT INTO item(name, sell_price_paise) VALUES (?,?)",
                     [(f"Item {i:04d}", 100) for i in range(600)])
    conn.execute("COMMIT")
    screen.refresh()
    assert screen.model.rowCount() == 500 and screen.note_label.text() == i18n.tr("items.limit_note")
    screen.search_edit.setText("Item 0599")
    assert screen.model.rowCount() == 1 and screen.note_label.text() == ""


def test_read_only_disables_edits(screen):
    screen.apply_read_only(True)
    assert not any(b.isEnabled() for b in (screen.add_button, screen.edit_button, screen.toggle_button))
    assert screen.search_edit.isEnabled()


def test_language_switch_retranslates(screen):
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("common.name")
    assert screen.add_button.text() == i18n.tr("common.add")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_items.py tests/test_support_services.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'has_stock_history'` / `ModuleNotFoundError: retail_ui.screens.items`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task15.json`:
```json
{
  "items.on_hand": {"en": "On hand", "hi": "स्टॉक में", "te": "స్టాక్‌లో"},
  "items.reorder": {"en": "Reorder at", "hi": "दोबारा मँगाएँ", "te": "మళ్లీ ఆర్డర్ చేయాల్సినది"},
  "items.inactive": {"en": "inactive", "hi": "निष्क्रिय", "te": "నిష్క్రియం"},
  "items.show_inactive": {"en": "Show inactive items", "hi": "निष्क्रिय वस्तुएँ दिखाएँ", "te": "నిష్క్రియ వస్తువులను చూపండి"},
  "items.deactivate": {"en": "Deactivate / Activate", "hi": "निष्क्रिय / सक्रिय करें", "te": "నిష్క్రియం / సక్రియం చేయండి"},
  "items.unit": {"en": "Unit", "hi": "इकाई", "te": "యూనిట్"},
  "items.buy_price": {"en": "Purchase price", "hi": "खरीद मूल्य", "te": "కొనుగోలు ధర"},
  "items.warranty": {"en": "Warranty (months)", "hi": "वारंटी (महीने)", "te": "వారంటీ (నెలలు)"},
  "items.barcodes": {"en": "Barcodes (comma separated)", "hi": "बारकोड (कॉमा से अलग)", "te": "బార్‌కోడ్‌లు (కామాతో వేరు చేయండి)"},
  "items.dialog_title": {"en": "Item", "hi": "वस्तु", "te": "వస్తువు"},
  "items.limit_note": {"en": "Showing the first 500 items — type in the search box to find others.", "hi": "पहली 500 वस्तुएँ दिख रही हैं — दूसरी खोजने के लिए सर्च बॉक्स में लिखें।", "te": "మొదటి 500 వస్తువులు చూపుతున్నాం — ఇతరాలను కనుగొనడానికి సెర్చ్ బాక్స్‌లో టైప్ చేయండి."}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task15.json`

- [ ] **Step 4: Implement**

Append to `retail/services/items.py`:
```python
def has_stock_history(conn, item_id):
    return conn.execute("SELECT 1 FROM stock_movement WHERE item_id = ? LIMIT 1", (item_id,)).fetchone() is not None
```

`retail_ui/screens/items.py`:
```python
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableView, QVBoxLayout)

from retail import money, segments
from retail.i18n import tr
from retail.services import items
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

HEADERS = ["common.name", "item.sku", "dlg.price", "counter.gst", "dlg.tracking", "items.on_hand", "items.reorder"]
LIST_LIMIT = 500


def _valid_or_blank(parser, text):
    if not text.strip():
        return True
    try:
        parser(text)
        return True
    except ValueError:
        return False


class ItemDialog(QDialog):
    def __init__(self, template, item=None, barcodes=(), locked_tracking=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("items.dialog_title"))
        features = template.get("features", {})
        form = QFormLayout(self)
        self.name_edit = QLineEdit(item["name"] if item else "")
        self.sku_edit = QLineEdit((item["sku"] or "") if item else "")
        self.hsn_edit = QLineEdit((item["hsn"] or "") if item else "")
        self.price_edit = QLineEdit(money.paise_to_str(item["sell_price_paise"]) if item else "")
        self.buy_edit = QLineEdit(money.paise_to_str(item["buy_price_paise"]) if item and item["buy_price_paise"] else "")
        self.gst_box = QComboBox()
        slabs = list(template.get("gst_slabs_bp", [0]))
        if item and item["gst_rate_bp"] not in slabs:
            slabs.append(item["gst_rate_bp"])
        for bp in slabs:
            self.gst_box.addItem(f"{bp / 100:g}%", bp)
        self.gst_box.setCurrentIndex(max(self.gst_box.findData(item["gst_rate_bp"] if item else 0), 0))
        self.unit_box = QComboBox()
        self.unit_box.setEditable(True)
        self.unit_box.addItems(template.get("units", ["pcs"]))
        self.unit_box.setCurrentText(item["unit"] if item else self.unit_box.itemText(0))
        self.tracking_box = QComboBox()
        modes = ["none"] + [t for t in ("weighed", "batch", "serial") if features.get(t)]
        if item and item["tracking"] not in modes:
            modes.append(item["tracking"])
        for mode in modes:
            self.tracking_box.addItem(tr(f"trk.{mode}"), mode)
        wanted = item["tracking"] if item else template.get("default_tracking", "none")
        self.tracking_box.setCurrentIndex(max(self.tracking_box.findData(wanted), 0))
        self.tracking_box.setEnabled(not locked_tracking)
        self.reorder_edit = QLineEdit(fmt.qty(item["reorder_milli"]) if item and item["reorder_milli"] else "")
        self.warranty_spin = QSpinBox()
        self.warranty_spin.setRange(0, 120)
        self.warranty_spin.setValue(item["warranty_months"] if item else 0)
        self.barcodes_edit = QLineEdit(", ".join(barcodes))
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("item.sku"), self.sku_edit)
        form.addRow(tr("item.hsn"), self.hsn_edit)
        form.addRow(tr("dlg.price"), self.price_edit)
        form.addRow(tr("items.buy_price"), self.buy_edit)
        form.addRow(tr("dlg.gst_rate"), self.gst_box)
        form.addRow(tr("items.unit"), self.unit_box)
        form.addRow(tr("dlg.tracking"), self.tracking_box)
        form.addRow(tr("items.reorder"), self.reorder_edit)
        self._warranty_label = tr("items.warranty")
        form.addRow(self._warranty_label, self.warranty_spin)
        self.warranty_spin.setHidden(not (features.get("warranty") or (item and item["warranty_months"])))
        form.labelForField(self.warranty_spin).setHidden(self.warranty_spin.isHidden())
        form.addRow(tr("items.barcodes"), self.barcodes_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        for edit in (self.name_edit, self.price_edit, self.buy_edit, self.reorder_edit):
            edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        self.ok_button.setEnabled(
            bool(self.name_edit.text().strip()) and _valid_or_blank(fmt.parse_rupees, self.price_edit.text())
            and bool(self.price_edit.text().strip())
            and _valid_or_blank(fmt.parse_rupees, self.buy_edit.text())
            and _valid_or_blank(fmt.parse_qty, self.reorder_edit.text()))

    def values(self):
        buy, reorder = self.buy_edit.text().strip(), self.reorder_edit.text().strip()
        return {"name": self.name_edit.text().strip(), "sku": self.sku_edit.text().strip(),
                "hsn": self.hsn_edit.text().strip() or None, "gst_rate_bp": self.gst_box.currentData(),
                "unit": self.unit_box.currentText().strip() or "pcs",
                "sell_price_paise": fmt.parse_rupees(self.price_edit.text()),
                "buy_price_paise": fmt.parse_rupees(buy) if buy else 0,
                "reorder_milli": fmt.parse_qty(reorder) if reorder else 0,
                "warranty_months": self.warranty_spin.value(), "tracking": self.tracking_box.currentData()}

    def barcodes(self):
        return list(dict.fromkeys(c.strip() for c in self.barcodes_edit.text().split(",") if c.strip()))


class ItemsScreen(Screen):
    nav_key = "nav.items"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.bind(self.search_edit, "common.search", "setPlaceholderText")
        self.inactive_box = self.bind(QCheckBox(), "items.show_inactive")
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.inactive_box)
        layout.addLayout(top)
        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.note_label = QLabel()
        layout.addWidget(self.note_label)
        row = QHBoxLayout()
        self.add_button = self._button("common.add", self.add_item, row)
        self.edit_button = self._button("common.edit", self.edit_item, row)
        self.toggle_button = self._button("items.deactivate", self.toggle_active, row)
        layout.addLayout(row)
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        self.inactive_box.toggled.connect(lambda _c: self.refresh())

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    def refresh(self):
        rows = items.list_items(self.session.conn, self.search_edit.text(),
                                include_inactive=self.inactive_box.isChecked(), limit=LIST_LIMIT)
        table, ids, low = [], [], []
        for i, r in enumerate(rows):
            unit = f" {r['unit']}" if r["tracking"] == "weighed" else ""
            name = r["name"] + (f"  [{tr('items.inactive')}]" if not r["active"] else "")
            table.append((name, r["sku"] or "", fmt.rupees(r["sell_price_paise"]),
                          f"{r['gst_rate_bp'] / 100:g}%" if r["gst_rate_bp"] else "", tr(f"trk.{r['tracking']}"),
                          fmt.qty(r["on_hand_milli"]) + unit,
                          (fmt.qty(r["reorder_milli"]) + unit) if r["reorder_milli"] else ""))
            ids.append(r["id"])
            if r["reorder_milli"] and r["on_hand_milli"] <= r["reorder_milli"]:
                low.append(i)
        self.model.set_rows(table, ids, right_cols=(2, 3, 5, 6), highlight=low)
        self.note_label.setText(tr("items.limit_note") if len(rows) >= LIST_LIMIT else "")

    def retranslate(self):
        super().retranslate()
        self.refresh()

    def apply_read_only(self, read_only):
        for button in (self.add_button, self.edit_button, self.toggle_button):
            button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _selected_id(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.id_at(rows[0].row()) if rows else None

    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def add_item(self):
        def run():
            answer = self._ask_item(None, [], False)
            if answer is not None:
                v = answer["values"]
                items.create_item(self.session.conn, **{**v, "sku": v["sku"] or None},
                                  barcodes=answer["barcodes"])
        self._guarded(run)

    def edit_item(self):
        def run():
            item_id = self._selected_id()
            if item_id is None:
                return
            conn = self.session.conn
            answer = self._ask_item(items.get_item(conn, item_id), items.item_barcodes(conn, item_id),
                                    items.has_stock_history(conn, item_id))
            if answer is not None:
                items.update_item(conn, item_id, **answer["values"])
                items.set_barcodes(conn, item_id, answer["barcodes"])
        self._guarded(run)

    def toggle_active(self):
        def run():
            item_id = self._selected_id()
            if item_id is not None:
                items.set_item_active(self.session.conn, item_id,
                                      not items.get_item(self.session.conn, item_id)["active"])
        self._guarded(run)

    # --- prompts ------------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_item(self, item, barcodes, locked_tracking):
        dialog = ItemDialog(segments.template_settings(self.session.conn), item, barcodes, locked_tracking, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {"values": dialog.values(), "barcodes": dialog.barcodes()}
```
Replace `retail_ui/screens/registry.py` with the three screens in order `[CounterScreen, BillsScreen, ItemsScreen]` (add `from retail_ui.screens.items import ItemsScreen`).

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_items.py tests/test_support_services.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the items screen with add/edit/deactivate and low-stock highlighting" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Stock and purchases screen

**Files:**
- Create: `retail_ui/widgets/pickers.py`, `retail_ui/screens/stock.py`, `tests/ui/test_ui_stock.py`
- Modify: `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `items.list_items`, `stock.adjust_stock/low_stock/on_hand`, `purchases.create_purchase/list_purchases/PurchaseLine`, `parties.list_parties/create_party`, `money`, `fmt`.
- Produces: `pickers.ItemPicker(conn_getter, parent=None)` (search box + list; `selected_item() -> Row | None`, `reload()`, signal `selection_changed`); `stock.AdjustDialog(item_name, parent=None)` → `qty_milli() -> int` (signed, non-zero), `reason() -> str`; `stock.PurchaseDialog(session, parent=None)` → `supplier_id()`, `invoice_no()`, `date_iso()`, `lines() -> list[PurchaseLine]`, `add_line() -> bool`; `StockScreen(session)` (`nav_key = "nav.stock"`) with a stock tab (`stock_model`, `adjust_button`, `low_label`) and a purchases tab (`purchase_model`, `new_purchase_button`); hooks `_ask_adjust(item) -> (qty_milli, reason) | None`, `_ask_purchase() -> dict | None` (`party_id, invoice_no, date_iso, lines`).

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_stock.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import i18n
from retail.services import items, parties, purchases, stock
from retail_ui.screens.stock import AdjustDialog, PurchaseDialog, StockScreen
from retail_ui.widgets.pickers import ItemPicker


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = StockScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def test_item_picker_searches_and_selects(shop_conn, qtbot):
    a = items.create_item(shop_conn, name="Bath soap", sell_price_paise=1)
    b = items.create_item(shop_conn, name="Rice", sell_price_paise=1)
    p = ItemPicker(lambda: shop_conn)
    qtbot.addWidget(p)
    assert p.list.count() == 2 and p.selected_item() is None
    p.list.setCurrentRow(1)
    assert p.selected_item()["id"] == b
    p.search.setText("soap")
    assert p.list.count() == 1 and p.selected_item() is None
    p.list.setCurrentRow(0)
    assert p.selected_item()["id"] == a


@pytest.mark.parametrize("text,ok,milli", [("5", True, 5000), ("-2.5", True, -2500), ("0", False, None),
                                           ("", False, None), ("abc", False, None)])
def test_adjust_dialog_quantity(qtbot, text, ok, milli):
    d = AdjustDialog("Rice")
    qtbot.addWidget(d)
    d.reason_edit.setText("count")
    d.qty_edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.qty_milli() == milli


def test_adjust_dialog_needs_a_reason(qtbot):
    d = AdjustDialog("Rice")
    qtbot.addWidget(d)
    d.qty_edit.setText("1")
    assert not d.ok_button.isEnabled()
    d.reason_edit.setText("  damaged ")
    assert d.ok_button.isEnabled() and d.reason() == "damaged"


def test_stock_tab_lists_on_hand_and_flags_low_stock(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Rice", sell_price_paise=1, unit="kg", tracking="weighed", reorder_milli=5000)
    b = items.create_item(conn, name="Soap", sell_price_paise=1)
    stock.record(conn, a, 2000, "opening")
    stock.record(conn, b, 9000, "opening")
    screen.refresh()
    assert [screen.stock_model.data(screen.stock_model.index(r, 0)) for r in range(2)] == ["Rice", "Soap"]
    assert screen.stock_model.data(screen.stock_model.index(0, 1)) == "2 kg"
    assert screen.stock_model.data(screen.stock_model.index(0, 3)) == i18n.tr("stock.status_low")
    assert screen.stock_model.data(screen.stock_model.index(1, 3)) == i18n.tr("stock.status_ok")
    assert screen.low_label.text() == i18n.tr("stock.low", count=1)


def test_adjust_flow_changes_stock_and_reports_errors(screen):
    conn = screen.session.conn
    a = items.create_item(conn, name="Soap", sell_price_paise=1)
    stock.record(conn, a, 3000, "opening")
    screen.refresh()
    screen.stock_table.selectRow(0)
    screen._ask_adjust = lambda item: (-1000, "damaged")
    screen.adjust_stock()
    assert stock.on_hand(conn, a) == 2000
    screen._ask_adjust = lambda item: (-9000, "oops")
    screen.adjust_stock()
    assert len(screen.errors) == 1 and stock.on_hand(conn, a) == 2000
    screen._ask_adjust = lambda item: None
    screen.adjust_stock()
    assert stock.on_hand(conn, a) == 2000


def test_adjust_does_nothing_without_a_selection(screen):
    screen._ask_adjust = lambda item: pytest.fail("nothing selected")
    screen.adjust_stock()


def test_purchase_dialog_builds_plain_serial_and_batch_lines(make_session, qtbot):
    s = make_session()
    conn = s.conn
    tea = items.create_item(conn, name="Tea", sell_price_paise=500)
    phone = items.create_item(conn, name="Phone", sell_price_paise=1, tracking="serial")
    milk = items.create_item(conn, name="Milk", sell_price_paise=1, tracking="batch")
    sup = parties.create_party(conn, name="Wholesale", type="supplier")
    d = PurchaseDialog(s)
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled() and d.supplier_id() is None
    d.supplier_box.setCurrentIndex(d.supplier_box.findData(sup))
    d.invoice_edit.setText(" W-1 ")

    def pick(name):
        d.picker.search.setText(name)
        d.picker.list.setCurrentRow(0)

    pick("Tea")
    d.qty_edit.setText("10")
    d.cost_edit.setText("30")
    assert d.add_line() is True and d.ok_button.isEnabled()
    pick("Phone")
    assert not d.serials_edit.isHidden() and d.qty_edit.isHidden()
    d.serials_edit.setPlainText("imei1\n\n imei2 \n")
    d.cost_edit.setText("8000")
    assert d.add_line() is True
    pick("Milk")
    assert not d.batch_edit.isHidden()
    d.qty_edit.setText("6")
    d.cost_edit.setText("50")
    d.batch_edit.setText("B1")
    d.expiry_edit.setText("2026-12-01")
    assert d.add_line() is True
    lines = d.lines()
    assert [(l.item_id, l.qty_milli, l.cost_paise) for l in lines] == [
        (tea, 10000, 3000), (phone, 2000, 800000), (milk, 6000, 5000)]
    assert lines[1].serials == ("imei1", "imei2") and lines[2].batch_no == "B1" and lines[2].expiry == "2026-12-01"
    assert d.invoice_no() == "W-1" and d.supplier_id() == sup and len(d.date_iso()) == 10
    assert d.purchase_model.rowCount() == 3


@pytest.mark.parametrize("setup", [
    dict(name="Tea", qty="", cost="30"), dict(name="Tea", qty="abc", cost="30"), dict(name="Tea", qty="1", cost=""),
    dict(name="Phone", serials="", cost="1"), dict(name="Milk", qty="1", cost="1", batch=""),
])
def test_purchase_dialog_rejects_incomplete_lines(make_session, qtbot, setup):
    s = make_session()
    for name, tracking in (("Tea", "none"), ("Phone", "serial"), ("Milk", "batch")):
        items.create_item(s.conn, name=name, sell_price_paise=1, tracking=tracking)
    d = PurchaseDialog(s)
    qtbot.addWidget(d)
    d.picker.search.setText(setup["name"])
    d.picker.list.setCurrentRow(0)
    d.qty_edit.setText(setup.get("qty", ""))
    d.cost_edit.setText(setup.get("cost", ""))
    d.serials_edit.setPlainText(setup.get("serials", ""))
    d.batch_edit.setText(setup.get("batch", ""))
    assert d.add_line() is False and d.lines() == [] and d.error_label.text() == i18n.tr("err.invalid_input")


def test_purchase_dialog_can_add_a_supplier(make_session, qtbot):
    s = make_session()
    d = PurchaseDialog(s)
    qtbot.addWidget(d)
    d.new_supplier_edit.setText("City Wholesale")
    d.add_supplier_button.click()
    assert d.supplier_box.currentText() == "City Wholesale" and d.supplier_id() is not None


def test_new_purchase_flow_receives_stock_and_lists_the_purchase(screen):
    conn = screen.session.conn
    tea = items.create_item(conn, name="Tea", sell_price_paise=500)
    screen._ask_purchase = lambda: {"party_id": None, "invoice_no": "W1", "date_iso": "2026-09-01",
                                    "lines": [purchases.PurchaseLine(tea, 4000, 300)]}
    screen.new_purchase()
    assert stock.on_hand(conn, tea) == 4000
    assert screen.purchase_model.data(screen.purchase_model.index(0, 1)) == "W1"
    assert screen.purchase_model.data(screen.purchase_model.index(0, 3)) == "₹12.00"


def test_a_failed_purchase_is_reported_and_writes_nothing(screen):
    conn = screen.session.conn
    phone = items.create_item(conn, name="Phone", sell_price_paise=1, tracking="serial")
    screen._ask_purchase = lambda: {"party_id": None, "invoice_no": None, "date_iso": "2026-09-01",
                                    "lines": [purchases.PurchaseLine(phone, 1000, 1, serials=("A",)),
                                              purchases.PurchaseLine(phone, 1000, 1, serials=("a",))]}
    screen.new_purchase()
    assert len(screen.errors) == 1 and stock.on_hand(conn, phone) == 0


def test_read_only_and_language(screen):
    screen.apply_read_only(True)
    assert not screen.adjust_button.isEnabled() and not screen.new_purchase_button.isEnabled()
    i18n.set_language("te")
    screen.retranslate()
    assert screen.stock_model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("common.name")
    assert screen.tabs.tabText(0) == i18n.tr("stock.tab_stock")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_stock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.widgets.pickers'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task16.json`:
```json
{
  "stock.tab_stock": {"en": "Stock", "hi": "स्टॉक", "te": "స్టాక్"},
  "stock.tab_purchases": {"en": "Purchases", "hi": "खरीद", "te": "కొనుగోళ్లు"},
  "stock.status": {"en": "Status", "hi": "स्थिति", "te": "స్థితి"},
  "stock.status_low": {"en": "Low", "hi": "कम", "te": "తక్కువ"},
  "stock.status_ok": {"en": "OK", "hi": "ठीक", "te": "సరే"},
  "stock.adjust": {"en": "Adjust stock", "hi": "स्टॉक सुधारें", "te": "స్టాక్ సవరించండి"},
  "stock.adjust_qty": {"en": "Change (+ add / − remove)", "hi": "बदलाव (+ जोड़ें / − घटाएँ)", "te": "మార్పు (+ చేర్చు / − తగ్గించు)"},
  "stock.reason": {"en": "Reason", "hi": "कारण", "te": "కారణం"},
  "pur.new": {"en": "New purchase", "hi": "नई खरीद", "te": "కొత్త కొనుగోలు"},
  "pur.supplier": {"en": "Supplier", "hi": "सप्लायर", "te": "సప్లయర్"},
  "pur.no_supplier": {"en": "(no supplier)", "hi": "(सप्लायर नहीं)", "te": "(సప్లయర్ లేరు)"},
  "pur.new_supplier": {"en": "New supplier name", "hi": "नए सप्लायर का नाम", "te": "కొత్త సప్లయర్ పేరు"},
  "pur.invoice": {"en": "Invoice no.", "hi": "इनवॉइस नं.", "te": "ఇన్వాయిస్ నం."},
  "pur.add_line": {"en": "Add line", "hi": "लाइन जोड़ें", "te": "లైన్ జోడించు"},
  "pur.cost": {"en": "Cost per unit", "hi": "प्रति इकाई लागत", "te": "యూనిట్ ధర"},
  "pur.serials": {"en": "Serials / IMEIs (one per line)", "hi": "सीरियल / IMEI (हर लाइन में एक)", "te": "సీరియల్ / IMEI (ప్రతి లైన్‌కు ఒకటి)"},
  "pur.batch": {"en": "Batch no.", "hi": "बैच नं.", "te": "బ్యాచ్ నం."},
  "pur.expiry": {"en": "Expiry (YYYY-MM-DD)", "hi": "एक्सपायरी (YYYY-MM-DD)", "te": "ఎక్స్‌పైరీ (YYYY-MM-DD)"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task16.json`

- [ ] **Step 4: Implement**

`retail_ui/widgets/pickers.py`:
```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QVBoxLayout, QWidget

from retail.i18n import tr
from retail.services import items
from retail_ui import fmt


class ItemPicker(QWidget):
    """A search box over a list of items (name, SKU or barcode)."""

    selection_changed = Signal()

    def __init__(self, conn_getter, parent=None):
        super().__init__(parent)
        self._conn = conn_getter
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("common.search"))
        self.list = QListWidget()
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        self.search.textChanged.connect(lambda _t: self.reload())
        self.list.currentRowChanged.connect(lambda _r: self.selection_changed.emit())
        self.reload()

    def reload(self):
        self._rows = items.list_items(self._conn(), self.search.text(), limit=50)
        self.list.blockSignals(True)
        self.list.clear()
        for r in self._rows:
            self.list.addItem(f"{r['name']}    ({fmt.qty(r['on_hand_milli'])})")
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        self.selection_changed.emit()

    def selected_item(self):
        row = self.list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None
```

`retail_ui/screens/stock.py`:
```python
from datetime import date
from decimal import InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableView,
                               QTabWidget, QVBoxLayout, QWidget)

from retail import money
from retail.i18n import tr
from retail.services import items, parties, purchases, stock
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import error_label, ok_cancel
from retail_ui.widgets.pickers import ItemPicker

STOCK_HEADERS = ["common.name", "items.on_hand", "items.reorder", "stock.status"]
PURCHASE_HEADERS = ["common.date", "pur.invoice", "pur.supplier", "bill.total"]
LINE_HEADERS = ["bill.item", "bill.qty", "pur.cost", "bill.total"]


class AdjustDialog(QDialog):
    def __init__(self, item_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("stock.adjust"))
        form = QFormLayout(self)
        form.addRow(QLabel(item_name))
        self.qty_edit = QLineEdit()
        self.reason_edit = QLineEdit()
        form.addRow(tr("stock.adjust_qty"), self.qty_edit)
        form.addRow(tr("stock.reason"), self.reason_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.qty_edit.textChanged.connect(self._check)
        self.reason_edit.textChanged.connect(self._check)
        self._check()

    def _qty(self):
        try:
            milli = money.qty_to_milli(self.qty_edit.text().strip())
        except InvalidOperation as exc:
            raise ValueError("not a quantity") from exc
        if milli == 0:
            raise ValueError("zero")
        return milli

    def _check(self):
        try:
            self._qty()
            self.ok_button.setEnabled(bool(self.reason()))
        except ValueError:
            self.ok_button.setEnabled(False)

    def qty_milli(self):
        return self._qty()

    def reason(self):
        return self.reason_edit.text().strip()


class PurchaseDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._lines = []
        self.setWindowTitle(tr("pur.new"))
        self.setMinimumWidth(640)
        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.supplier_box = QComboBox()
        self.new_supplier_edit = QLineEdit()
        self.new_supplier_edit.setPlaceholderText(tr("pur.new_supplier"))
        self.add_supplier_button = QPushButton(tr("common.add"))
        supplier_row = QHBoxLayout()
        for w in (self.supplier_box, self.new_supplier_edit, self.add_supplier_button):
            supplier_row.addWidget(w)
        form.addRow(tr("pur.supplier"), supplier_row)
        self.invoice_edit = QLineEdit()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(tr("pur.invoice"), self.invoice_edit)
        form.addRow(tr("common.date"), self.date_edit)
        outer.addLayout(form)

        self.picker = ItemPicker(lambda: self.session.conn)
        outer.addWidget(self.picker)
        entry = QFormLayout()
        self.qty_edit = QLineEdit()
        self.cost_edit = QLineEdit()
        self.serials_edit = QPlainTextEdit()
        self.serials_edit.setFixedHeight(60)
        self.batch_edit = QLineEdit()
        self.expiry_edit = QLineEdit()
        self._qty_label = QLabel(tr("bill.qty"))
        entry.addRow(self._qty_label, self.qty_edit)
        entry.addRow(tr("pur.cost"), self.cost_edit)
        self._serials_label = QLabel(tr("pur.serials"))
        entry.addRow(self._serials_label, self.serials_edit)
        self._batch_label, self._expiry_label = QLabel(tr("pur.batch")), QLabel(tr("pur.expiry"))
        entry.addRow(self._batch_label, self.batch_edit)
        entry.addRow(self._expiry_label, self.expiry_edit)
        outer.addLayout(entry)
        self.add_line_button = QPushButton(tr("pur.add_line"))
        self.error_label = error_label()
        outer.addWidget(self.add_line_button)
        outer.addWidget(self.error_label)

        self.purchase_model = RowsModel(LINE_HEADERS)
        table = QTableView()
        table.setModel(self.purchase_model)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(table)
        box, self.ok_button = ok_cancel(self)
        outer.addWidget(box)
        self.ok_button.setEnabled(False)

        self._reload_suppliers()
        self.add_supplier_button.clicked.connect(self._add_supplier)
        self.add_line_button.clicked.connect(lambda _=False: self.add_line())
        self.picker.selection_changed.connect(self._update_fields)
        self._update_fields()

    def _reload_suppliers(self, select=None):
        self.supplier_box.clear()
        self.supplier_box.addItem(tr("pur.no_supplier"), None)
        for p in parties.list_parties(self.session.conn, kind="supplier"):
            self.supplier_box.addItem(p["name"], p["id"])
        if select is not None:
            self.supplier_box.setCurrentIndex(self.supplier_box.findData(select))

    def _add_supplier(self):
        try:
            new_id = parties.create_party(self.session.conn, name=self.new_supplier_edit.text(), type="supplier")
        except Exception as exc:
            show_error(self, exc)
            return
        self.new_supplier_edit.clear()
        self._reload_suppliers(select=new_id)

    def _update_fields(self):
        item = self.picker.selected_item()
        tracking = item["tracking"] if item else "none"
        serial, batch = tracking == "serial", tracking == "batch"
        for widget in (self.qty_edit, self._qty_label):
            widget.setHidden(serial)
        for widget in (self.serials_edit, self._serials_label):
            widget.setHidden(not serial)
        for widget in (self.batch_edit, self._batch_label, self.expiry_edit, self._expiry_label):
            widget.setHidden(not batch)

    def add_line(self):
        item = self.picker.selected_item()
        try:
            if item is None:
                raise ValueError("no item")
            cost = fmt.parse_rupees(self.cost_edit.text())
            tracking = item["tracking"]
            if tracking == "serial":
                serials = tuple(s.strip() for s in self.serials_edit.toPlainText().splitlines() if s.strip())
                if not serials:
                    raise ValueError("no serials")
                line = purchases.PurchaseLine(item["id"], 1000 * len(serials), cost, serials=serials)
            elif tracking == "batch":
                batch = self.batch_edit.text().strip()
                if not batch:
                    raise ValueError("no batch")
                expiry = self.expiry_edit.text().strip() or None
                if expiry is not None:
                    date.fromisoformat(expiry)
                line = purchases.PurchaseLine(item["id"], fmt.parse_qty(self.qty_edit.text()), cost,
                                              batch_no=batch, expiry=expiry)
            else:
                line = purchases.PurchaseLine(item["id"], fmt.parse_qty(self.qty_edit.text()), cost)
        except ValueError:
            self.error_label.setText(tr("err.invalid_input"))
            return False
        self.error_label.setText("")
        self._lines.append((line, item["name"]))
        for edit in (self.qty_edit, self.cost_edit, self.batch_edit, self.expiry_edit):
            edit.clear()
        self.serials_edit.clear()
        self.purchase_model.set_rows(
            [(name, fmt.qty(l.qty_milli), fmt.rupees(l.cost_paise),
              fmt.rupees(money.line_amount(l.cost_paise, l.qty_milli))) for l, name in self._lines],
            right_cols=(1, 2, 3))
        self.ok_button.setEnabled(True)
        return True

    def supplier_id(self):
        return self.supplier_box.currentData()

    def invoice_no(self):
        return self.invoice_edit.text().strip() or None

    def date_iso(self):
        return self.date_edit.date().toString(Qt.DateFormat.ISODate)

    def lines(self):
        return [line for line, _name in self._lines]


class StockScreen(Screen):
    nav_key = "nav.stock"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        stock_page = QWidget()
        sl = QVBoxLayout(stock_page)
        self.low_label = QLabel()
        sl.addWidget(self.low_label)
        self.stock_model = self.track(RowsModel(STOCK_HEADERS))
        self.stock_table = self._table(self.stock_model)
        sl.addWidget(self.stock_table, 1)
        self.adjust_button = self.bind(QPushButton(), "stock.adjust")
        self.adjust_button.clicked.connect(lambda _=False: self.adjust_stock())
        sl.addWidget(self.adjust_button)
        self.tabs.addTab(stock_page, "")

        purchase_page = QWidget()
        pl = QVBoxLayout(purchase_page)
        self.purchase_model = self.track(RowsModel(PURCHASE_HEADERS))
        pl.addWidget(self._table(self.purchase_model), 1)
        self.new_purchase_button = self.bind(QPushButton(), "pur.new")
        self.new_purchase_button.clicked.connect(lambda _=False: self.new_purchase())
        pl.addWidget(self.new_purchase_button)
        self.tabs.addTab(purchase_page, "")
        self._tab_titles()

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    def _tab_titles(self):
        self.tabs.setTabText(0, tr("stock.tab_stock"))
        self.tabs.setTabText(1, tr("stock.tab_purchases"))

    def retranslate(self):
        super().retranslate()
        self._tab_titles()
        self.refresh()

    def refresh(self):
        conn = self.session.conn
        rows, ids, low = [], [], []
        for i, r in enumerate(items.list_items(conn, limit=20000)):
            unit = f" {r['unit']}" if r["tracking"] == "weighed" else ""
            is_low = bool(r["reorder_milli"]) and r["on_hand_milli"] <= r["reorder_milli"]
            rows.append((r["name"], fmt.qty(r["on_hand_milli"]) + unit,
                         (fmt.qty(r["reorder_milli"]) + unit) if r["reorder_milli"] else "",
                         tr("stock.status_low") if is_low else tr("stock.status_ok")))
            ids.append(r["id"])
            if is_low:
                low.append(i)
        self.stock_model.set_rows(rows, ids, right_cols=(1, 2), highlight=low)
        self.low_label.setText(tr("stock.low", count=len(low)) if low else "")
        self.purchase_model.set_rows(
            [(fmt.date_text(p["purchase_date"]), p["invoice_no"] or "", p["supplier"], fmt.rupees(p["total_paise"]))
             for p in purchases.list_purchases(conn)], right_cols=(3,))

    def apply_read_only(self, read_only):
        self.adjust_button.setEnabled(not read_only)
        self.new_purchase_button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def adjust_stock(self):
        def run():
            rows = self.stock_table.selectionModel().selectedRows()
            item_id = self.stock_model.id_at(rows[0].row()) if rows else None
            if item_id is None:
                return
            answer = self._ask_adjust(items.get_item(self.session.conn, item_id))
            if answer is not None:
                stock.adjust_stock(self.session.conn, item_id, *answer)
        self._guarded(run)

    def new_purchase(self):
        def run():
            answer = self._ask_purchase()
            if answer is not None:
                purchases.create_purchase(self.session.conn, **answer)
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_adjust(self, item):
        dialog = AdjustDialog(item["name"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.qty_milli(), dialog.reason()

    def _ask_purchase(self):
        dialog = PurchaseDialog(self.session, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return {"party_id": dialog.supplier_id(), "invoice_no": dialog.invoice_no(),
                "date_iso": dialog.date_iso(), "lines": dialog.lines()}
```
Replace `retail_ui/screens/registry.py` so the list is `[CounterScreen, BillsScreen, ItemsScreen, StockScreen]` (add `from retail_ui.screens.stock import StockScreen`).

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_stock.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the stock and purchases screen with audited adjustments" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Customers and suppliers screen (udhaar)

**Files:**
- Create: `retail_ui/screens/parties.py`, `tests/ui/test_ui_parties.py`
- Modify: `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `parties.list_parties/create_party/update_party/receive_payment/balance`, `states.STATES`, `validators.gstin_error`.
- Produces: `PartyDialog(party=None, parent=None)` (`name_edit, phone_edit, gstin_edit, state_box, type_box, ok_button`; `values() -> dict` with `name, phone, gstin, state_code` plus `type` when adding); `ReceiveDialog(party_name, due_paise, parent=None)` (`amount_edit, mode_box, note_edit, ok_button`; `amount_paise()`, `mode()`, `note()`); `PartiesScreen(session)` (`nav_key = "nav.parties"`) with `view_box` (customers / suppliers / only dues), `search_edit`, `table`, `model`, `add_button, edit_button, receive_button`; hooks `_ask_party(party) -> dict | None`, `_ask_receive(name, due) -> (paise, mode, note) | None`.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_parties.py`:
```python
import pytest
from PySide6.QtCore import Qt

from retail import i18n
from retail.services import billing, items, parties, stock
from retail_ui.screens.parties import PartiesScreen, PartyDialog, ReceiveDialog


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = PartiesScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def cell(sc, row, col):
    return sc.model.data(sc.model.index(row, col))


def owe(conn, party_id, paise):
    item = items.create_item(conn, name=f"Item{paise}", sell_price_paise=paise)
    stock.record(conn, item, 9000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    billing.add_line(conn, bill_id, item, 1000)
    billing.finalize(conn, bill_id, [("credit", billing.get_bill(conn, bill_id)["bill"]["total_paise"])])


def test_party_dialog_validation(qtbot):
    d = PartyDialog()
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.name_edit.setText(" Ravi ")
    assert d.ok_button.isEnabled()
    d.gstin_edit.setText("36ABCDE1234F1Z5")                  # a GSTIN needs a matching state
    assert not d.ok_button.isEnabled()
    d.state_box.setCurrentIndex(d.state_box.findData("36"))
    assert d.ok_button.isEnabled()
    d.phone_edit.setText(" 98765 ")
    d.type_box.setCurrentIndex(d.type_box.findData("supplier"))
    assert d.values() == {"name": "Ravi", "phone": "98765", "gstin": "36ABCDE1234F1Z5", "state_code": "36",
                          "type": "supplier"}


def test_party_dialog_edit_prefills_and_hides_the_type(qtbot, shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", phone="1", state_code="27")
    row = shop_conn.execute("SELECT * FROM party WHERE id=?", (pid,)).fetchone()
    d = PartyDialog(party=row)
    qtbot.addWidget(d)
    assert d.name_edit.text() == "Ravi" and d.state_box.currentData() == "27" and d.type_box.isHidden()
    assert "type" not in d.values()


@pytest.mark.parametrize("text,ok,paise", [("100", True, 10000), ("₹50.5", True, 5050), ("0", False, None),
                                           ("-1", False, None), ("x", False, None), ("", False, None)])
def test_receive_dialog(qtbot, text, ok, paise):
    d = ReceiveDialog("Ravi", 20000)
    qtbot.addWidget(d)
    assert d.amount_edit.text() == "200.00"                   # prefilled with what is due
    d.amount_edit.setText(text)
    assert d.ok_button.isEnabled() is ok
    if ok:
        assert d.amount_paise() == paise and d.mode() == "cash"


def test_customers_tab_shows_balances_and_search(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi", phone="9876500001")
    parties.create_party(conn, name="Sita")
    parties.create_party(conn, name="Wholesale", type="supplier")
    owe(conn, ravi, 5000)
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["Ravi", "Sita"]
    assert cell(screen, 0, 2) == "₹50.00" and cell(screen, 1, 2) == "₹0.00"
    screen.search_edit.setText("98765")
    screen.refresh()
    assert screen.model.rowCount() == 1


def test_suppliers_and_dues_views(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi")
    parties.create_party(conn, name="Sita")
    parties.create_party(conn, name="Wholesale", type="supplier")
    owe(conn, ravi, 5000)
    screen.view_box.setCurrentIndex(screen.view_box.findData("suppliers"))
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["Wholesale"] and cell(screen, 0, 2) == ""
    screen.view_box.setCurrentIndex(screen.view_box.findData("dues"))
    screen.refresh()
    assert [cell(screen, r, 0) for r in range(screen.model.rowCount())] == ["Ravi"]


def test_add_and_edit_flow(screen):
    conn = screen.session.conn
    screen._ask_party = lambda party: {"name": "Ravi", "phone": "1", "gstin": "", "state_code": "36", "type": "customer"}
    screen.add_party()
    assert screen.model.rowCount() == 1 and parties.list_parties(conn)[0]["state_code"] == "36"
    screen.table.selectRow(0)
    seen = []
    screen._ask_party = lambda party: seen.append(party["name"]) or {
        "name": "Ravi K", "phone": "2", "gstin": "", "state_code": "27"}
    screen.edit_party()
    assert seen == ["Ravi"] and cell(screen, 0, 0) == "Ravi K"
    screen.table.selectRow(0)                                     # the refresh cleared the selection
    screen._ask_party = lambda party: {"name": " ", "phone": "", "gstin": "", "state_code": ""}
    screen.edit_party()
    assert len(screen.errors) == 1


def test_receive_payment_reduces_the_balance(screen):
    conn = screen.session.conn
    ravi = parties.create_party(conn, name="Ravi")
    owe(conn, ravi, 5000)
    screen.refresh()
    screen.table.selectRow(0)
    asked = []
    screen._ask_receive = lambda name, due: asked.append((name, due)) or (2000, "upi", "part")
    screen.receive_payment()
    assert asked == [("Ravi", 5000)] and parties.balance(conn, ravi) == 3000 and cell(screen, 0, 2) == "₹30.00"


def test_receive_payment_is_not_offered_for_suppliers_or_without_selection(screen):
    screen._ask_receive = lambda name, due: pytest.fail("no dialog expected")
    screen.receive_payment()
    parties.create_party(screen.session.conn, name="Wholesale", type="supplier")
    screen.view_box.setCurrentIndex(screen.view_box.findData("suppliers"))
    screen.refresh()
    screen.table.selectRow(0)
    screen.receive_payment()


def test_read_only_and_language(screen):
    screen.apply_read_only(True)
    assert not any(b.isEnabled() for b in (screen.add_button, screen.edit_button, screen.receive_button))
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.model.headerData(2, Qt.Orientation.Horizontal) == i18n.tr("party.balance")
    assert screen.view_box.itemText(0) == i18n.tr("party.customers")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_parties.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.parties'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task17.json`:
```json
{
  "party.customers": {"en": "Customers", "hi": "ग्राहक", "te": "కస్టమర్లు"},
  "party.suppliers": {"en": "Suppliers", "hi": "सप्लायर", "te": "సప్లయర్లు"},
  "party.dues": {"en": "Only dues (udhaar)", "hi": "सिर्फ बकाया (उधार)", "te": "బాకీలు మాత్రమే (అప్పు)"},
  "party.balance": {"en": "Balance due", "hi": "बकाया रकम", "te": "బాకీ మొత్తం"},
  "party.type": {"en": "Type", "hi": "प्रकार", "te": "రకం"},
  "party.type_customer": {"en": "Customer", "hi": "ग्राहक", "te": "కస్టమర్"},
  "party.type_supplier": {"en": "Supplier", "hi": "सप्लायर", "te": "సప్లయర్"},
  "party.type_both": {"en": "Both", "hi": "दोनों", "te": "రెండూ"},
  "party.none_state": {"en": "— not set —", "hi": "— तय नहीं —", "te": "— సెట్ చేయలేదు —"},
  "party.receive": {"en": "Receive payment", "hi": "भुगतान लें", "te": "చెల్లింపు స్వీకరించు"},
  "party.dialog_title": {"en": "Customer / supplier", "hi": "ग्राहक / सप्लायर", "te": "కస్టమర్ / సప్లయర్"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task17.json`

- [ ] **Step 4: Implement**

`retail_ui/screens/parties.py`:
```python
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QPushButton, QTableView, QVBoxLayout)

from retail import money
from retail.i18n import tr
from retail.services import parties
from retail_ui import fmt, states, validators
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

HEADERS = ["common.name", "common.phone", "party.balance"]
VIEWS = (("customers", "party.customers"), ("suppliers", "party.suppliers"), ("dues", "party.dues"))


class PartyDialog(QDialog):
    def __init__(self, party=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("party.dialog_title"))
        self._editing = party is not None
        form = QFormLayout(self)
        self.name_edit = QLineEdit(party["name"] if party else "")
        self.phone_edit = QLineEdit((party["phone"] or "") if party else "")
        self.gstin_edit = QLineEdit((party["gstin"] or "") if party else "")
        self.state_box = QComboBox()
        self.state_box.addItem(tr("party.none_state"), "")
        for code, name in states.STATES.items():
            self.state_box.addItem(f"{code} — {name}", code)
        self.state_box.setCurrentIndex(max(self.state_box.findData((party["state_code"] or "") if party else ""), 0))
        self.type_box = QComboBox()
        for kind in ("customer", "supplier", "both"):
            self.type_box.addItem(tr(f"party.type_{kind}"), kind)
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("common.phone"), self.phone_edit)
        form.addRow(tr("tax.gstin"), self.gstin_edit)
        form.addRow(tr("ob.state"), self.state_box)
        form.addRow(tr("party.type"), self.type_box)
        self.type_box.setHidden(self._editing)
        form.labelForField(self.type_box).setHidden(self._editing)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        for signal in (self.name_edit.textChanged, self.gstin_edit.textChanged, self.state_box.currentIndexChanged):
            signal.connect(lambda *_: self._check())
        self._check()

    def _check(self):
        gstin = self.gstin_edit.text().strip()
        gstin_ok = not gstin or (bool(self.state_box.currentData())
                                 and validators.gstin_error(gstin, self.state_box.currentData()) is None)
        self.ok_button.setEnabled(bool(self.name_edit.text().strip()) and gstin_ok)

    def values(self):
        out = {"name": self.name_edit.text().strip(), "phone": self.phone_edit.text().strip(),
               "gstin": self.gstin_edit.text().strip().upper(), "state_code": self.state_box.currentData()}
        if not self._editing:
            out["type"] = self.type_box.currentData()
        return out


class ReceiveDialog(QDialog):
    def __init__(self, party_name, due_paise, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("party.receive"))
        form = QFormLayout(self)
        form.addRow(party_name)
        self.amount_edit = QLineEdit(money.paise_to_str(max(due_paise, 0)))
        self.mode_box = QComboBox()
        for mode in ("cash", "upi", "card"):
            self.mode_box.addItem(tr(f"pay.{mode}"), mode)
        self.note_edit = QLineEdit()
        form.addRow(tr("common.amount"), self.amount_edit)
        form.addRow(tr("dlg.pay_title"), self.mode_box)
        form.addRow(tr("common.note"), self.note_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.amount_edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        try:
            self.ok_button.setEnabled(fmt.parse_rupees(self.amount_edit.text()) > 0)
        except ValueError:
            self.ok_button.setEnabled(False)

    def amount_paise(self):
        return fmt.parse_rupees(self.amount_edit.text())

    def mode(self):
        return self.mode_box.currentData()

    def note(self):
        return self.note_edit.text().strip()


class PartiesScreen(Screen):
    nav_key = "nav.parties"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.view_box = QComboBox()
        for code, key in VIEWS:
            self.view_box.addItem(tr(key), code)
        self.search_edit = QLineEdit()
        self.bind(self.search_edit, "common.search", "setPlaceholderText")
        top.addWidget(self.view_box)
        top.addWidget(self.search_edit, 1)
        layout.addLayout(top)
        self.model = self.track(RowsModel(HEADERS))
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.add_button = self._button("common.add", self.add_party, row)
        self.edit_button = self._button("common.edit", self.edit_party, row)
        self.receive_button = self._button("party.receive", self.receive_payment, row)
        layout.addLayout(row)
        self.view_box.currentIndexChanged.connect(lambda _i: self.refresh())
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        self._rows = {}

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    def _view(self):
        return self.view_box.currentData()

    def refresh(self):
        view = self._view()
        kind = "supplier" if view == "suppliers" else "customer"
        rows = parties.list_parties(self.session.conn, kind=kind, search=self.search_edit.text())
        if view == "dues":
            rows = sorted((r for r in rows if r["balance_paise"] > 0), key=lambda r: -r["balance_paise"])
        self._rows = {r["id"]: r for r in rows}
        self.model.set_rows(
            [(r["name"], r["phone"] or "", "" if view == "suppliers" else fmt.rupees(r["balance_paise"]))
             for r in rows], ids=[r["id"] for r in rows], right_cols=(2,))

    def retranslate(self):
        super().retranslate()
        for i, (_code, key) in enumerate(VIEWS):
            self.view_box.setItemText(i, tr(key))
        self.refresh()

    def apply_read_only(self, read_only):
        for button in (self.add_button, self.edit_button, self.receive_button):
            button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        party_id = self.model.id_at(rows[0].row()) if rows else None
        return self._rows.get(party_id)

    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def add_party(self):
        def run():
            v = self._ask_party(None)
            if v is not None:
                parties.create_party(self.session.conn, name=v["name"], phone=v["phone"] or None,
                                     gstin=v["gstin"] or None, state_code=v["state_code"] or None, type=v["type"])
        self._guarded(run)

    def edit_party(self):
        def run():
            party = self._selected()
            if party is None:
                return
            v = self._ask_party(party)
            if v is not None:
                parties.update_party(self.session.conn, party["id"], name=v["name"], phone=v["phone"] or None,
                                     gstin=v["gstin"] or None, state_code=v["state_code"] or None)
        self._guarded(run)

    def receive_payment(self):
        def run():
            party = self._selected()
            if party is None or self._view() == "suppliers":
                return
            answer = self._ask_receive(party["name"], party["balance_paise"])
            if answer is not None:
                paise, mode, note = answer
                parties.receive_payment(self.session.conn, party["id"], paise, mode=mode, note=note)
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_party(self, party):
        dialog = PartyDialog(party, self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_receive(self, name, due_paise):
        dialog = ReceiveDialog(name, due_paise, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.amount_paise(), dialog.mode(), dialog.note()
```
Replace `retail_ui/screens/registry.py` so the list is `[CounterScreen, BillsScreen, ItemsScreen, StockScreen, PartiesScreen]`.

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_parties.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the customers and suppliers screen with udhaar balances and payments" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 18: Reports screen (sales register, GST summary, daily summary, CSV export)

**Files:**
- Create: `retail_ui/screens/reports.py`, `tests/ui/test_ui_reports.py`
- Modify: `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `reports.sales_register/gst_summary/daily_summary/write_csv/SALES_COLUMNS`.
- Produces: `ReportsScreen(session)` (`nav_key = "nav.reports"`) with `from_edit, to_edit, tabs, sales_model, gst_model, day_model, export_sales_button, export_gst_button, status_label`; actions `export_sales()`, `export_gst()`; hook `_ask_save_path(default_name) -> str | None`. The daily summary is for the **To** date. Exports stay enabled after licence expiry (reports are read-only operations).

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_reports.py`:
```python
import csv

import pytest
from PySide6.QtCore import QDate, Qt

from retail import i18n
from retail.services import billing, items, stock
from retail_ui.screens.reports import ReportsScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = ReportsScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    return sc


def seed(conn):
    """A sale of 2 x Rs 118 (18% GST) and a return of one of them."""
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn)
    line_id = billing.add_line(conn, bill_id, item, 2000)
    billing.finalize(conn, bill_id, [("cash", 23600)])
    billing.create_return(conn, bill_id, [(line_id, 1000)])


def cell(model, row, col):
    return model.data(model.index(row, col))


def test_sales_register_tab(screen):
    seed(screen.session.conn)
    screen.refresh()
    m = screen.sales_model
    assert m.rowCount() == 2
    assert [cell(m, 0, c) for c in (0, 2, 5, 6, 7, 8, 10)] == [
        "S000001", i18n.tr("bills.sale"), "₹200.00", "₹18.00", "₹18.00", "₹0.00", "₹236.00"]
    assert cell(m, 1, 0) == "R000001" and cell(m, 1, 2) == i18n.tr("bills.return") and cell(m, 1, 10) == "-₹118.00"


def test_gst_summary_tab_nets_returns(screen):
    seed(screen.session.conn)
    screen.refresh()
    m = screen.gst_model
    assert m.rowCount() == 1
    assert [cell(m, 0, c) for c in range(5)] == ["18%", "₹100.00", "₹9.00", "₹9.00", "₹0.00"]


def test_daily_summary_tab(screen):
    seed(screen.session.conn)
    screen.refresh()
    m = screen.day_model
    assert [(cell(m, r, 0), cell(m, r, 1)) for r in range(m.rowCount())] == [
        (i18n.tr("rep.sales"), "₹236.00"), (i18n.tr("rep.returns"), "₹118.00"), (i18n.tr("rep.net"), "₹118.00"),
        (i18n.tr("rep.by_mode"), ""), (i18n.tr("pay.cash"), "₹118.00")]


def test_empty_range_shows_empty_tables(screen):
    screen.refresh()
    assert screen.sales_model.rowCount() == 0 and screen.gst_model.rowCount() == 0
    assert cell(screen.day_model, 2, 1) == "₹0.00"


def test_bad_range_is_reported_and_clears_the_tables(screen):
    seed(screen.session.conn)
    screen.refresh()
    screen.from_edit.setDate(QDate(2030, 1, 1))
    screen.to_edit.setDate(QDate(2020, 1, 1))
    screen.refresh()
    assert len(screen.errors) >= 1 and screen.sales_model.rowCount() == 0


def test_export_sales_register_csv(screen, tmp_path):
    seed(screen.session.conn)
    screen.refresh()
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_sales()
    rows = list(csv.DictReader((tmp_path / "sales_register.csv").open(encoding="utf-8-sig")))
    assert [r["bill_no"] for r in rows] == ["S000001", "R000001"] and rows[0]["total"] == "236.00"
    assert rows[1]["total"] == "-118.00" and "sales_register.csv" in screen.status_label.text()


def test_export_gst_summary_csv(screen, tmp_path):
    seed(screen.session.conn)
    screen._ask_save_path = lambda name: str(tmp_path / name)
    screen.export_gst()
    rows = list(csv.DictReader((tmp_path / "gst_summary.csv").open(encoding="utf-8-sig")))
    assert rows == [{"gst_rate_bp": "1800", "taxable": "100.00", "cgst": "9.00", "sgst": "9.00", "igst": "0.00"}]


def test_cancelled_export_writes_nothing(screen, tmp_path):
    screen._ask_save_path = lambda name: None
    screen.export_sales()
    # tmp_path also holds the app's own data folder (RetailApp); nothing else may appear
    assert [p.name for p in tmp_path.iterdir() if p.name != "RetailApp"] == [] and screen.errors == []


def test_unwritable_export_path_is_reported(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen._ask_save_path = lambda name: str(blocker / "sub" / name)
    screen.export_sales()
    assert len(screen.errors) == 1


def test_exports_stay_available_when_read_only_and_headers_retranslate(screen):
    screen.apply_read_only(True)
    assert screen.export_sales_button.isEnabled() and screen.export_gst_button.isEnabled()
    i18n.set_language("te")
    screen.retranslate()
    assert screen.sales_model.headerData(0, Qt.Orientation.Horizontal) == i18n.tr("print.bill_no")
    assert screen.tabs.tabText(0) == i18n.tr("rep.tab_sales")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_reports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.reports'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task18.json`:
```json
{
  "rep.tab_sales": {"en": "Sales register", "hi": "बिक्री रजिस्टर", "te": "అమ్మకాల రిజిస్టర్"},
  "rep.tab_gst": {"en": "GST summary", "hi": "GST सारांश", "te": "GST సారాంశం"},
  "rep.tab_day": {"en": "Daily summary", "hi": "दैनिक सारांश", "te": "రోజువారీ సారాంశం"},
  "rep.rate": {"en": "GST rate", "hi": "GST दर", "te": "GST రేటు"},
  "rep.sales": {"en": "Sales", "hi": "बिक्री", "te": "అమ్మకాలు"},
  "rep.returns": {"en": "Returns", "hi": "वापसी", "te": "వాపసులు"},
  "rep.net": {"en": "Net sales", "hi": "शुद्ध बिक्री", "te": "నికర అమ్మకాలు"},
  "rep.by_mode": {"en": "By payment mode", "hi": "भुगतान के तरीके से", "te": "చెల్లింపు విధానం ప్రకారం"},
  "rep.export_sales": {"en": "Export sales register (CSV)", "hi": "बिक्री रजिस्टर एक्सपोर्ट करें (CSV)", "te": "అమ్మకాల రిజిస్టర్ ఎక్స్‌పోర్ట్ చేయండి (CSV)"},
  "rep.export_gst": {"en": "Export GST summary (CSV)", "hi": "GST सारांश एक्सपोर्ट करें (CSV)", "te": "GST సారాంశం ఎక్స్‌పోర్ట్ చేయండి (CSV)"},
  "rep.exported": {"en": "Saved: {path}", "hi": "सहेजा गया: {path}", "te": "సేవ్ అయింది: {path}"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task18.json`

- [ ] **Step 4: Implement**

`retail_ui/screens/reports.py`:
```python
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QDateEdit, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableView, QTabWidget, QVBoxLayout)

from retail.i18n import tr
from retail.services import reports
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen

SALES_HEADERS = ["print.bill_no", "common.date", "bills.type", "bill.customer", "tax.gstin", "tax.taxable",
                 "tax.cgst", "tax.sgst", "tax.igst", "bill.round_off", "bill.total"]
GST_HEADERS = ["rep.rate", "tax.taxable", "tax.cgst", "tax.sgst", "tax.igst"]
DAY_HEADERS = ["common.name", "common.amount"]
GST_COLUMNS = ["gst_rate_bp", "taxable_paise", "cgst_paise", "sgst_paise", "igst_paise"]


class ReportsScreen(Screen):
    nav_key = "nav.reports"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        today = QDate.currentDate()
        self.from_edit, self.to_edit = QDateEdit(today), QDateEdit(today)
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd-MM-yyyy")
            edit.dateChanged.connect(lambda _d: self.refresh())
        top.addWidget(self.bind(QLabel(), "common.from"))
        top.addWidget(self.from_edit)
        top.addWidget(self.bind(QLabel(), "common.to"))
        top.addWidget(self.to_edit)
        top.addStretch(1)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.sales_model = self.track(RowsModel(SALES_HEADERS))
        self.gst_model = self.track(RowsModel(GST_HEADERS))
        self.day_model = self.track(RowsModel(DAY_HEADERS))
        for model in (self.sales_model, self.gst_model, self.day_model):
            self.tabs.addTab(self._table(model), "")
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.export_sales_button = self.bind(QPushButton(), "rep.export_sales")
        self.export_gst_button = self.bind(QPushButton(), "rep.export_gst")
        self.export_sales_button.clicked.connect(lambda _=False: self.export_sales())
        self.export_gst_button.clicked.connect(lambda _=False: self.export_gst())
        buttons.addWidget(self.export_sales_button)
        buttons.addWidget(self.export_gst_button)
        layout.addLayout(buttons)
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self._tab_titles()

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _tab_titles(self):
        for i, key in enumerate(("rep.tab_sales", "rep.tab_gst", "rep.tab_day")):
            self.tabs.setTabText(i, tr(key))

    def _range(self):
        return (self.from_edit.date().toString(Qt.DateFormat.ISODate),
                self.to_edit.date().toString(Qt.DateFormat.ISODate))

    def retranslate(self):
        super().retranslate()
        self._tab_titles()
        self.refresh()

    def refresh(self):
        conn = self.session.conn
        try:
            start, end = self._range()
            register = reports.sales_register(conn, start, end)
            gst = reports.gst_summary(conn, start, end)
            day = reports.daily_summary(conn, end)
        except Exception as exc:
            for model in (self.sales_model, self.gst_model, self.day_model):
                model.set_rows([])
            self._show_error(exc)
            return
        money_cols = ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "round_off_paise", "total_paise")
        self.sales_model.set_rows(
            [(r["bill_no"], fmt.date_text(r["bill_date"]),
              tr("bills.return") if r["kind"] == "sale_return" else tr("bills.sale"), r["party"], r["gstin"],
              *(fmt.rupees(r[c]) for c in money_cols)) for r in register],
            right_cols=range(5, 11))
        self.gst_model.set_rows(
            [(f"{r['gst_rate_bp'] / 100:g}%", *(fmt.rupees(r[c]) for c in GST_COLUMNS[1:])) for r in gst],
            right_cols=range(1, 5))
        rows = [(tr("rep.sales"), fmt.rupees(day["sales_paise"])),
                (tr("rep.returns"), fmt.rupees(day["returns_paise"])),
                (tr("rep.net"), fmt.rupees(day["net_paise"])),
                (tr("rep.by_mode"), "")]
        rows += [(tr(f"pay.{mode}"), fmt.rupees(amount)) for mode, amount in sorted(day["by_mode"].items())]
        self.day_model.set_rows(rows, right_cols=(1,))

    # --- exports (reports are read-only operations, so these stay enabled after expiry) --------
    def _export(self, default_name, build_rows, columns):
        try:
            path = self._ask_save_path(default_name)
            if not path:
                return
            start, end = self._range()
            reports.write_csv(build_rows(start, end), path, columns)
            self.status_label.setText(tr("rep.exported", path=path))
        except Exception as exc:
            self._show_error(exc)

    def export_sales(self):
        self._export("sales_register.csv", lambda s, e: reports.sales_register(self.session.conn, s, e),
                     reports.SALES_COLUMNS)

    def export_gst(self):
        self._export("gst_summary.csv", lambda s, e: reports.gst_summary(self.session.conn, s, e), GST_COLUMNS)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_save_path(self, default_name):
        path, _ = QFileDialog.getSaveFileName(self, tr("common.export"), default_name, "CSV (*.csv)")
        return path or None
```
Replace `retail_ui/screens/registry.py` list with `[CounterScreen, BillsScreen, ItemsScreen, StockScreen, PartiesScreen, ReportsScreen]` (add the import).

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_reports.py tests/test_i18n.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the reports screen with sales register, GST and daily summaries and CSV export" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Staff and expenses screen

**Files:**
- Create: `retail_ui/screens/staff.py`, `tests/ui/test_ui_staff.py`
- Modify: `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `staff.add_staff/list_staff/add_expense/pay_salary/list_expenses/expense_total/CATEGORIES`.
- Produces: `StaffDialog(parent=None)` (`name_edit, role_edit, salary_edit, ok_button`; `values()` → `name, role, monthly_salary_paise`); `ExpenseDialog(staff_rows, parent=None)` (`date_edit, category_box, amount_edit, note_edit, staff_box, ok_button`; `values()` → `spent_on, category, amount_paise, note, staff_id`); `StaffScreen(session)` (`nav_key = "nav.staff"`) with `tabs, staff_model, expense_model, from_edit, to_edit, total_label, add_staff_button, pay_salary_button, add_expense_button`; hooks `_ask_staff() -> dict | None`, `_ask_expense(staff_rows) -> dict | None`, `_confirm(key) -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_staff.py`:
```python
import pytest
from PySide6.QtCore import QDate, Qt

from retail import clock, i18n
from retail.services import staff
from retail_ui.screens.staff import ExpenseDialog, StaffDialog, StaffScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = StaffScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._confirm = lambda key: True
    return sc


def cell(model, row, col):
    return model.data(model.index(row, col))


def test_staff_dialog(qtbot):
    d = StaffDialog()
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.name_edit.setText(" Anil ")
    d.role_edit.setText("Cashier")
    d.salary_edit.setText("₹12,000")
    assert d.ok_button.isEnabled()
    assert d.values() == {"name": "Anil", "role": "Cashier", "monthly_salary_paise": 1200000}
    d.salary_edit.setText("abc")
    assert not d.ok_button.isEnabled()
    d.salary_edit.setText("")
    assert d.ok_button.isEnabled() and d.values()["monthly_salary_paise"] == 0


def test_expense_dialog(qtbot, shop_conn):
    anil = staff.add_staff(shop_conn, name="Anil", monthly_salary_paise=100)
    d = ExpenseDialog(staff.list_staff(shop_conn))
    qtbot.addWidget(d)
    assert not d.ok_button.isEnabled()
    d.amount_edit.setText("2500")
    d.category_box.setCurrentIndex(d.category_box.findData("rent"))
    d.note_edit.setText(" Sept ")
    d.date_edit.setDate(QDate(2026, 9, 5))
    assert d.ok_button.isEnabled() and d.values() == {
        "spent_on": "2026-09-05", "category": "rent", "amount_paise": 250000, "note": "Sept", "staff_id": None}
    d.staff_box.setCurrentIndex(d.staff_box.findData(anil))
    assert d.values()["staff_id"] == anil
    d.amount_edit.setText("0")
    assert not d.ok_button.isEnabled()


def test_add_staff_and_list(screen):
    screen._ask_staff = lambda: {"name": "Anil", "role": "Cashier", "monthly_salary_paise": 1200000}
    screen.add_staff()
    assert screen.staff_model.rowCount() == 1
    assert [cell(screen.staff_model, 0, c) for c in range(3)] == ["Anil", "Cashier", "₹12,000.00"]


def test_pay_salary_records_an_expense_once_per_month(screen):
    anil = staff.add_staff(screen.session.conn, name="Anil", monthly_salary_paise=1200000)
    screen.refresh()
    screen.staff_table.selectRow(0)
    screen.pay_salary()
    today = clock.today().isoformat()
    assert staff.expense_total(screen.session.conn, today[:8] + "01", today, category="salary") == 1200000
    screen.staff_table.selectRow(0)
    screen.pay_salary()                                        # the same month again
    assert len(screen.errors) == 1 and anil


def test_pay_salary_asks_first_and_needs_a_selection(screen):
    staff.add_staff(screen.session.conn, name="Anil", monthly_salary_paise=100)
    screen.refresh()
    screen._confirm = lambda key: pytest.fail("nothing is selected")
    screen.pay_salary()
    screen.staff_table.selectRow(0)
    screen._confirm = lambda key: False
    screen.pay_salary()
    today = clock.today().isoformat()
    assert staff.expense_total(screen.session.conn, today[:8] + "01", today) == 0


def test_add_expense_updates_the_list_and_total(screen):
    today = clock.today().isoformat()
    screen._ask_expense = lambda staff_rows: {"spent_on": today, "category": "rent", "amount_paise": 1500000,
                                              "note": "Shop rent", "staff_id": None}
    screen.add_expense()
    assert screen.expense_model.rowCount() == 1
    assert [cell(screen.expense_model, 0, c) for c in (1, 3, 4)] == [i18n.tr("exp.cat_rent"), "Shop rent", "₹15,000.00"]
    assert "₹15,000.00" in screen.total_label.text()


def test_invalid_expense_is_reported_not_raised(screen):
    screen._ask_expense = lambda staff_rows: {"spent_on": "2026-09-05", "category": "party", "amount_paise": 1,
                                              "note": "", "staff_id": None}
    screen.add_expense()
    assert len(screen.errors) == 1 and screen.expense_model.rowCount() == 0


def test_expense_range_filters_and_bad_range_is_reported(screen):
    staff.add_expense(screen.session.conn, spent_on="2020-01-10", category="rent", amount_paise=100)
    screen.from_edit.setDate(QDate(2020, 1, 1))
    screen.to_edit.setDate(QDate(2020, 1, 31))
    assert screen.expense_model.rowCount() == 1
    screen.to_edit.setDate(QDate(2019, 1, 1))
    assert len(screen.errors) >= 1


def test_read_only_and_language(screen):
    screen.apply_read_only(True)
    assert not any(b.isEnabled() for b in (screen.add_staff_button, screen.pay_salary_button, screen.add_expense_button))
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.staff_model.headerData(1, Qt.Orientation.Horizontal) == i18n.tr("staff.role")
    assert screen.tabs.tabText(1) == i18n.tr("staff.tab_expenses")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_staff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.staff'`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task19.json`:
```json
{
  "staff.tab_staff": {"en": "Staff", "hi": "स्टाफ", "te": "సిబ్బంది"},
  "staff.tab_expenses": {"en": "Expenses", "hi": "खर्च", "te": "ఖర్చులు"},
  "staff.role": {"en": "Role", "hi": "भूमिका", "te": "పాత్ర"},
  "staff.salary": {"en": "Monthly salary", "hi": "मासिक वेतन", "te": "నెలవారీ జీతం"},
  "staff.add": {"en": "Add staff", "hi": "स्टाफ जोड़ें", "te": "సిబ్బందిని జోడించు"},
  "staff.pay": {"en": "Pay salary", "hi": "वेतन दें", "te": "జీతం చెల్లించు"},
  "staff.pay_confirm": {"en": "Record this month's salary as an expense?", "hi": "इस महीने का वेतन खर्च के रूप में दर्ज करें?", "te": "ఈ నెల జీతాన్ని ఖర్చుగా నమోదు చేయాలా?"},
  "exp.add": {"en": "Add expense", "hi": "खर्च जोड़ें", "te": "ఖర్చు జోడించు"},
  "exp.category": {"en": "Category", "hi": "श्रेणी", "te": "వర్గం"},
  "exp.cat_salary": {"en": "Salary", "hi": "वेतन", "te": "జీతం"},
  "exp.cat_rent": {"en": "Rent", "hi": "किराया", "te": "అద్దె"},
  "exp.cat_electricity": {"en": "Electricity", "hi": "बिजली", "te": "విద్యుత్"},
  "exp.cat_transport": {"en": "Transport", "hi": "परिवहन", "te": "రవాణా"},
  "exp.cat_other": {"en": "Other", "hi": "अन्य", "te": "ఇతరాలు"},
  "exp.staff": {"en": "Staff member (optional)", "hi": "स्टाफ सदस्य (वैकल्पिक)", "te": "సిబ్బంది (ఐచ్ఛికం)"},
  "exp.total": {"en": "Total expenses", "hi": "कुल खर्च", "te": "మొత్తం ఖర్చులు"},
  "exp.no_staff": {"en": "(none)", "hi": "(कोई नहीं)", "te": "(ఎవరూ లేరు)"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task19.json`

- [ ] **Step 4: Implement**

`retail_ui/screens/staff.py`:
```python
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableView, QTabWidget,
                               QVBoxLayout, QWidget)

from retail import clock
from retail.i18n import tr
from retail.services import staff
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen
from retail_ui.widgets.helpers import ok_cancel

STAFF_HEADERS = ["common.name", "staff.role", "staff.salary"]
EXPENSE_HEADERS = ["common.date", "exp.category", "exp.staff", "common.note", "common.amount"]


class StaffDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("staff.add"))
        form = QFormLayout(self)
        self.name_edit, self.role_edit, self.salary_edit = QLineEdit(), QLineEdit(), QLineEdit()
        form.addRow(tr("common.name"), self.name_edit)
        form.addRow(tr("staff.role"), self.role_edit)
        form.addRow(tr("staff.salary"), self.salary_edit)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.name_edit.textChanged.connect(self._check)
        self.salary_edit.textChanged.connect(self._check)
        self._check()

    def _salary(self):
        text = self.salary_edit.text().strip()
        return fmt.parse_rupees(text) if text else 0

    def _check(self):
        try:
            self._salary()
            self.ok_button.setEnabled(bool(self.name_edit.text().strip()))
        except ValueError:
            self.ok_button.setEnabled(False)

    def values(self):
        return {"name": self.name_edit.text().strip(), "role": self.role_edit.text().strip(),
                "monthly_salary_paise": self._salary()}


class ExpenseDialog(QDialog):
    def __init__(self, staff_rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("exp.add"))
        form = QFormLayout(self)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd-MM-yyyy")
        self.category_box = QComboBox()
        for category in staff.CATEGORIES:
            self.category_box.addItem(tr(f"exp.cat_{category}"), category)
        self.amount_edit, self.note_edit = QLineEdit(), QLineEdit()
        self.staff_box = QComboBox()
        self.staff_box.addItem(tr("exp.no_staff"), None)
        for person in staff_rows:
            self.staff_box.addItem(person["name"], person["id"])
        form.addRow(tr("common.date"), self.date_edit)
        form.addRow(tr("exp.category"), self.category_box)
        form.addRow(tr("common.amount"), self.amount_edit)
        form.addRow(tr("common.note"), self.note_edit)
        form.addRow(tr("exp.staff"), self.staff_box)
        box, self.ok_button = ok_cancel(self)
        form.addRow(box)
        self.amount_edit.textChanged.connect(self._check)
        self._check()

    def _check(self):
        try:
            self.ok_button.setEnabled(fmt.parse_rupees(self.amount_edit.text()) > 0)
        except ValueError:
            self.ok_button.setEnabled(False)

    def values(self):
        return {"spent_on": self.date_edit.date().toString(Qt.DateFormat.ISODate),
                "category": self.category_box.currentData(),
                "amount_paise": fmt.parse_rupees(self.amount_edit.text()),
                "note": self.note_edit.text().strip(), "staff_id": self.staff_box.currentData()}


class StaffScreen(Screen):
    nav_key = "nav.staff"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        staff_page = QWidget()
        sl = QVBoxLayout(staff_page)
        self.staff_model = self.track(RowsModel(STAFF_HEADERS))
        self.staff_table = self._table(self.staff_model)
        sl.addWidget(self.staff_table, 1)
        row = QHBoxLayout()
        self.add_staff_button = self._button("staff.add", self.add_staff, row)
        self.pay_salary_button = self._button("staff.pay", self.pay_salary, row)
        sl.addLayout(row)
        self.tabs.addTab(staff_page, "")

        expense_page = QWidget()
        el = QVBoxLayout(expense_page)
        top = QHBoxLayout()
        today = QDate.currentDate()
        self.from_edit, self.to_edit = QDateEdit(QDate(today.year(), today.month(), 1)), QDateEdit(today)
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd-MM-yyyy")
            edit.dateChanged.connect(lambda _d: self.refresh())
        top.addWidget(self.bind(QLabel(), "common.from"))
        top.addWidget(self.from_edit)
        top.addWidget(self.bind(QLabel(), "common.to"))
        top.addWidget(self.to_edit)
        top.addStretch(1)
        el.addLayout(top)
        self.expense_model = self.track(RowsModel(EXPENSE_HEADERS))
        el.addWidget(self._table(self.expense_model), 1)
        self.total_label = QLabel()
        el.addWidget(self.total_label)
        row2 = QHBoxLayout()
        self.add_expense_button = self._button("exp.add", self.add_expense, row2)
        el.addLayout(row2)
        self.tabs.addTab(expense_page, "")
        self._tab_titles()
        self._total = 0

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    def _button(self, key, handler, row):
        button = self.bind(QPushButton(), key)
        button.clicked.connect(lambda _=False: handler())
        row.addWidget(button)
        return button

    def _tab_titles(self):
        self.tabs.setTabText(0, tr("staff.tab_staff"))
        self.tabs.setTabText(1, tr("staff.tab_expenses"))

    def _range(self):
        return (self.from_edit.date().toString(Qt.DateFormat.ISODate),
                self.to_edit.date().toString(Qt.DateFormat.ISODate))

    def retranslate(self):
        super().retranslate()
        self._tab_titles()
        self.refresh()

    def refresh(self):
        conn = self.session.conn
        people = staff.list_staff(conn)
        self.staff_model.set_rows([(p["name"], p["role"], fmt.rupees(p["monthly_salary_paise"])) for p in people],
                                  ids=[p["id"] for p in people], right_cols=(2,))
        try:
            start, end = self._range()
            rows = staff.list_expenses(conn, start, end)
            total = staff.expense_total(conn, start, end)
        except Exception as exc:
            self.expense_model.set_rows([])
            self.total_label.setText("")
            self._show_error(exc)
            return
        self.expense_model.set_rows(
            [(fmt.date_text(r["spent_on"]), tr(f"exp.cat_{r['category']}"), r["staff_name"], r["note"],
              fmt.rupees(r["amount_paise"])) for r in rows], right_cols=(4,))
        self.total_label.setText(f"{tr('exp.total')}: {fmt.rupees(total)}")

    def apply_read_only(self, read_only):
        for button in (self.add_staff_button, self.pay_salary_button, self.add_expense_button):
            button.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def add_staff(self):
        def run():
            v = self._ask_staff()
            if v is not None:
                staff.add_staff(self.session.conn, **v)
        self._guarded(run)

    def pay_salary(self):
        def run():
            rows = self.staff_table.selectionModel().selectedRows()
            staff_id = self.staff_model.id_at(rows[0].row()) if rows else None
            if staff_id is not None and self._confirm("staff.pay_confirm"):
                staff.pay_salary(self.session.conn, staff_id, clock.today().isoformat())
        self._guarded(run)

    def add_expense(self):
        def run():
            v = self._ask_expense(staff.list_staff(self.session.conn))
            if v is not None:
                staff.add_expense(self.session.conn, **v)
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_staff(self):
        dialog = StaffDialog(self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _ask_expense(self, staff_rows):
        dialog = ExpenseDialog(staff_rows, self)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def _confirm(self, key):
        answer = QMessageBox.question(self, "", tr(key),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes
```
Replace `retail_ui/screens/registry.py` list with `[..., ReportsScreen, StaffScreen]` (add the import).

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_staff.py tests/test_i18n.py -v`
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the staff and expenses screen" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 20: Settings screen (shop, billing, segment features, printing, language)

**Files:**
- Create: `retail_ui/screens/settings.py`, `tests/ui/test_ui_settings.py`
- Modify: `retail_ui/session.py` (`set_language` keeps working after expiry), `tests/ui/test_ui_session.py` (one test), `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `shop.update_shop`, `segments.list_templates/apply_template/set_feature/template_settings/feature_enabled`, `session.settings/save_settings/set_language`, `validators.gstin_error`, `states.STATES`.
- Produces: `AppSession.set_language(code)` now **still switches the screen language after the licence expired** (the choice is saved only while writable); `SettingsScreen(session)` (`nav_key = "nav.settings"`) with `name_edit, state_box, gstin_edit, address_edit, footer_edit, save_shop_button, gst_box, incl_box, oversell_box, template_box, apply_template_button, feature_boxes (dict key → QCheckBox), layout_box, auto_print_box, language_box`; actions `save_shop()`; hooks `_confirm(key) -> bool`, `_warn(key) -> None`. Billing switches, feature switches, layout, auto-print and language apply immediately; shop details need **Save**. Printing and language stay available when read-only.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_ui_session.py`:
```python
def test_language_can_still_be_switched_after_the_licence_expires(make_session, qtbot):
    from retail import license as lic
    s = make_session()
    s.license = lic.LicenseState("expired", expires="2020-01-01")
    guard.set_read_only(True)
    with qtbot.waitSignal(s.language_changed):
        s.set_language("te")
    assert i18n.get_language() == "te"
    assert s.shop()["language"] == "en"                      # not saved: the database is read-only
    with pytest.raises(ValueError):
        s.set_language("fr")
```

`tests/ui/test_ui_settings.py`:
```python
import pytest

from retail import i18n, segments
from retail.services import billing, shop
from retail_ui import settings as ui_settings
from retail_ui.screens.settings import SettingsScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = SettingsScreen(session)
    qtbot.addWidget(sc)
    sc.errors, sc.warnings = [], []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._warn = lambda key: sc.warnings.append(key)
    sc._confirm = lambda key: True
    sc.refresh()
    return sc


def audit_count(conn):
    return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def test_refresh_loads_the_current_values_without_writing(screen):
    conn = screen.session.conn
    before = audit_count(conn)
    screen.refresh()
    assert audit_count(conn) == before
    assert screen.name_edit.text() == "Test Shop" and screen.state_box.currentData() == "36"
    assert screen.gst_box.isChecked() and screen.incl_box.isChecked()
    assert screen.oversell_box.currentData() == "warn" and screen.template_box.currentData() == "grocery"
    assert screen.feature_boxes["weighed"].isChecked() and not screen.feature_boxes["serial"].isChecked()
    assert screen.language_box.currentData() == "en"


def test_save_shop_updates_the_details(screen):
    screen.name_edit.setText("  New Name ")
    screen.state_box.setCurrentIndex(screen.state_box.findData("27"))
    screen.gstin_edit.setText("27abcde1234f1z5")
    screen.address_edit.setText("Pune")
    screen.footer_edit.setText("No returns after 7 days")
    screen.save_shop()
    row = shop.get_shop(screen.session.conn)
    assert (row["name"], row["state_code"], row["gstin"], row["address"], row["bill_footer"]) == (
        "New Name", "27", "27ABCDE1234F1Z5", "Pune", "No returns after 7 days")
    assert screen.warnings == [] and screen.errors == []


def test_blank_gstin_is_stored_as_none_and_a_bad_one_is_refused(screen):
    screen.gstin_edit.setText("")
    screen.save_shop()
    assert shop.get_shop(screen.session.conn)["gstin"] is None
    screen.gstin_edit.setText("27ABCDE1234F1Z5")                    # the state is 36
    screen.save_shop()
    assert screen.warnings == ["ob.invalid_gstin"] and shop.get_shop(screen.session.conn)["gstin"] is None


def test_an_empty_shop_name_is_reported_and_nothing_changes(screen):
    screen.name_edit.setText(" ")
    screen.save_shop()
    assert len(screen.errors) == 1 and shop.get_shop(screen.session.conn)["name"] == "Test Shop"
    assert screen.name_edit.text() == "Test Shop"                   # the form reverts to the saved value


def test_billing_switches_apply_immediately(screen):
    screen.gst_box.setChecked(False)
    screen.incl_box.setChecked(False)
    screen.oversell_box.setCurrentIndex(screen.oversell_box.findData("block"))
    row = shop.get_shop(screen.session.conn)
    assert (row["gst_enabled"], row["price_includes_gst"], row["oversell_policy"]) == (0, 0, "block")
    assert billing.get_bill(screen.session.conn, billing.start_bill(screen.session.conn))["bill"]["gst_mode"] == "estimate"


def test_changing_the_segment_asks_first_and_resets_features(screen):
    screen.template_box.setCurrentIndex(screen.template_box.findData("electronics"))
    screen._confirm = lambda key: False
    screen.apply_template_button.click()
    assert shop.get_shop(screen.session.conn)["template"] == "grocery"
    asked = []
    screen._confirm = lambda key: asked.append(key) or True
    screen.apply_template_button.click()
    assert asked == ["set.template_confirm"] and shop.get_shop(screen.session.conn)["template"] == "electronics"
    assert screen.feature_boxes["serial"].isChecked() and screen.feature_boxes["warranty"].isChecked()
    assert not screen.feature_boxes["weighed"].isChecked()


def test_feature_switches_mix_segments(screen):
    screen.feature_boxes["serial"].setChecked(True)
    screen.feature_boxes["weighed"].setChecked(False)
    assert segments.feature_enabled(screen.session.conn, "serial") and not segments.feature_enabled(screen.session.conn, "weighed")


def test_printing_options_are_saved_to_the_settings_file(screen):
    screen.layout_box.setCurrentIndex(screen.layout_box.findData("a4"))
    screen.auto_print_box.setChecked(True)
    saved = ui_settings.load(screen.session.paths.settings_path)
    assert saved.print_layout == "a4" and saved.auto_print is True
    screen.layout_box.setCurrentIndex(screen.layout_box.findData(""))
    assert ui_settings.load(screen.session.paths.settings_path).print_layout == ""


def test_language_choice_switches_and_saves(screen, qtbot):
    with qtbot.waitSignal(screen.session.language_changed):
        screen.language_box.setCurrentIndex(screen.language_box.findData("hi"))
    assert i18n.get_language() == "hi" and shop.get_shop(screen.session.conn)["language"] == "hi"


def test_language_switch_retranslates_the_labels_and_keeps_the_choices(screen):
    screen.session.set_language("te")
    screen.retranslate()
    assert screen.save_shop_button.text() == i18n.tr("set.save")
    assert screen.template_box.itemText(0) == i18n.tr("tpl.electronics")          # templates are listed sorted
    assert screen.template_box.currentData() == "grocery"                          # the choice survives
    assert screen.oversell_box.currentData() == "warn" and screen.language_box.currentData() == "te"


def test_read_only_disables_data_changes_but_not_printing_or_language(screen):
    screen.apply_read_only(True)
    for name in ("name_edit", "state_box", "gstin_edit", "address_edit", "footer_edit", "save_shop_button", "gst_box",
                 "incl_box", "oversell_box", "template_box", "apply_template_button"):
        assert not getattr(screen, name).isEnabled(), name
    assert not any(box.isEnabled() for box in screen.feature_boxes.values())
    assert screen.layout_box.isEnabled() and screen.auto_print_box.isEnabled() and screen.language_box.isEnabled()
    screen.apply_read_only(False)
    assert screen.save_shop_button.isEnabled() and all(b.isEnabled() for b in screen.feature_boxes.values())
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_settings.py tests/ui/test_ui_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.settings'` and the new session test fails with `ReadOnlyError`.

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task20.json`:
```json
{
  "set.shop": {"en": "Shop details", "hi": "दुकान की जानकारी", "te": "దుకాణం వివరాలు"},
  "set.footer": {"en": "Bill footer message", "hi": "बिल के नीचे का संदेश", "te": "బిల్లు క్రింది సందేశం"},
  "set.save": {"en": "Save", "hi": "सहेजें", "te": "సేవ్ చేయండి"},
  "set.billing": {"en": "Billing", "hi": "बिलिंग", "te": "బిల్లింగ్"},
  "set.template": {"en": "Business type", "hi": "व्यापार का प्रकार", "te": "వ్యాపార రకం"},
  "set.apply_template": {"en": "Apply", "hi": "लागू करें", "te": "వర్తింపజేయండి"},
  "set.template_confirm": {"en": "Changing the business type resets the feature switches below to its defaults. Continue?", "hi": "व्यापार का प्रकार बदलने पर नीचे के फ़ीचर स्विच उसके डिफ़ॉल्ट पर लौट जाएँगे। जारी रखें?", "te": "వ్యాపార రకాన్ని మార్చితే క్రింది ఫీచర్ స్విచ్‌లు దాని డిఫాల్ట్‌కు మారతాయి. కొనసాగించాలా?"},
  "set.features": {"en": "Features", "hi": "फ़ीचर", "te": "ఫీచర్లు"},
  "set.printing": {"en": "Printing", "hi": "प्रिंटिंग", "te": "ప్రింటింగ్"},
  "set.layout": {"en": "Bill layout", "hi": "बिल का लेआउट", "te": "బిల్లు లేఅవుట్"},
  "set.layout_auto": {"en": "Automatic (from business type)", "hi": "अपने-आप (व्यापार के प्रकार से)", "te": "ఆటోమేటిక్ (వ్యాపార రకం ప్రకారం)"},
  "set.auto_print": {"en": "Open the print preview after every sale", "hi": "हर बिक्री के बाद प्रिंट प्रीव्यू खोलें", "te": "ప్రతి అమ్మకం తర్వాత ప్రింట్ ప్రివ్యూ తెరవండి"},
  "set.language": {"en": "Language", "hi": "भाषा", "te": "భాష"},
  "feat.weighed": {"en": "Weighed items (kg / litre)", "hi": "तौल वाली वस्तुएँ (किलो / लीटर)", "te": "తూకం వేసే వస్తువులు (కిలో / లీటరు)"},
  "feat.batch": {"en": "Batch & expiry tracking", "hi": "बैच और एक्सपायरी ट्रैकिंग", "te": "బ్యాచ్ & ఎక్స్‌పైరీ ట్రాకింగ్"},
  "feat.serial": {"en": "Serial / IMEI tracking", "hi": "सीरियल / IMEI ट्रैकिंग", "te": "సీరియల్ / IMEI ట్రాకింగ్"},
  "feat.warranty": {"en": "Warranty", "hi": "वारंटी", "te": "వారంటీ"},
  "feat.emi": {"en": "EMI payments", "hi": "EMI भुगतान", "te": "EMI చెల్లింపులు"},
  "feat.udhaar": {"en": "Credit (udhaar) sales", "hi": "उधार बिक्री", "te": "అప్పు అమ్మకాలు"},
  "feat.low_stock_alerts": {"en": "Low-stock alerts", "hi": "कम स्टॉक की सूचना", "te": "తక్కువ స్టాక్ హెచ్చరికలు"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task20.json`

- [ ] **Step 4: Implement**

In `retail_ui/session.py`, add `from retail import clock, db, guard, i18n` (it already imports these) and replace `set_language` with:
```python
    def set_language(self, code: str) -> None:
        """Switch the screen language. After the licence expires the database is read-only, so the
        choice then lasts for this session only instead of being refused."""
        try:
            shop.update_shop(self.conn, language=code)  # validates the code and persists it
        except guard.ReadOnlyError:
            log.info("licence expired: language %s applied for this session only", code)
        i18n.set_language(code)  # raises ValueError for an unsupported code, before anything is emitted
        self.language_changed.emit(code)
```

`retail_ui/screens/settings.py`:
```python
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from retail import i18n, segments
from retail.i18n import tr
from retail.services import shop
from retail_ui import states, validators
from retail_ui.errors import show_error
from retail_ui.widgets.base import Screen

FEATURES = ("weighed", "batch", "serial", "warranty", "emi", "udhaar", "low_stock_alerts")
LAYOUT_LABELS = {"thermal_58": "Thermal 58 mm", "thermal_80": "Thermal 80 mm", "a4": "A4"}


class SettingsScreen(Screen):
    nav_key = "nav.settings"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self._loading = False
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        # --- shop details (needs Save) ----------------------------------------------------
        box, form = self._group("set.shop", layout)
        self.name_edit, self.gstin_edit = QLineEdit(), QLineEdit()
        self.address_edit, self.footer_edit = QLineEdit(), QLineEdit()
        self.state_box = QComboBox()
        for code, name in states.STATES.items():
            self.state_box.addItem(f"{code} — {name}", code)
        self._row(form, "ob.shop_name", self.name_edit)
        self._row(form, "ob.state", self.state_box)
        self._row(form, "tax.gstin", self.gstin_edit)
        self._row(form, "ob.address", self.address_edit)
        self._row(form, "set.footer", self.footer_edit)
        self.save_shop_button = self.bind(QPushButton(), "set.save")
        self.save_shop_button.clicked.connect(lambda _=False: self.save_shop())
        form.addRow(self.save_shop_button)

        # --- billing and features (apply immediately) -----------------------------------------
        box, form = self._group("set.billing", layout)
        self.gst_box = self.bind(QCheckBox(), "ob.gst_enabled")
        self.incl_box = self.bind(QCheckBox(), "ob.prices_incl")
        self.oversell_box = QComboBox()
        self.template_box = QComboBox()
        self.apply_template_button = self.bind(QPushButton(), "set.apply_template")
        form.addRow(self.gst_box)
        form.addRow(self.incl_box)
        self._row(form, "ob.oversell", self.oversell_box)
        self._row(form, "set.template", self.template_box)
        form.addRow(self.apply_template_button)
        features_box, features_form = self._group("set.features", layout)
        self.feature_boxes = {}
        for key in FEATURES:
            check = self.bind(QCheckBox(), f"feat.{key}")
            self.feature_boxes[key] = check
            features_form.addRow(check)
            check.toggled.connect(lambda checked, k=key: self._on_feature(k, checked))

        # --- printing and language (always available) -----------------------------------------
        box, form = self._group("set.printing", layout)
        self.layout_box = QComboBox()
        self.auto_print_box = self.bind(QCheckBox(), "set.auto_print")
        self._row(form, "set.layout", self.layout_box)
        form.addRow(self.auto_print_box)
        box, form = self._group("set.language", layout)
        self.language_box = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_box.addItem(name, code)
        form.addRow(self.language_box)
        layout.addStretch(1)

        self._fill_choices()
        self.gst_box.toggled.connect(lambda _c: self._on_billing())
        self.incl_box.toggled.connect(lambda _c: self._on_billing())
        self.oversell_box.currentIndexChanged.connect(lambda _i: self._on_billing())
        self.apply_template_button.clicked.connect(lambda _=False: self.apply_template())
        self.layout_box.currentIndexChanged.connect(lambda _i: self._on_print())
        self.auto_print_box.toggled.connect(lambda _c: self._on_print())
        self.language_box.currentIndexChanged.connect(lambda _i: self._on_language())

    def _group(self, title_key, layout):
        group = QGroupBox()
        self.bind(group, title_key, "setTitle")
        form = QFormLayout(group)
        layout.addWidget(group)
        return group, form

    def _row(self, form, key, widget):
        form.addRow(self.bind(QLabel(), key), widget)

    def _fill_choices(self):
        """(Re)build the combos whose entries are translated; the current choice is restored by refresh()."""
        self._loading = True
        try:
            for combo in (self.oversell_box, self.template_box, self.layout_box):
                combo.clear()
            for code in ("block", "warn", "allow"):
                self.oversell_box.addItem(tr(f"ob.oversell_{code}"), code)
            for name in segments.list_templates():
                self.template_box.addItem(tr(f"tpl.{name}"), name)
            self.layout_box.addItem(tr("set.layout_auto"), "")
            for code, label in LAYOUT_LABELS.items():
                self.layout_box.addItem(label, code)
        finally:
            self._loading = False

    # --- Screen protocol ------------------------------------------------------
    def retranslate(self):
        super().retranslate()
        self._fill_choices()
        self.refresh()

    def refresh(self):
        self._loading = True
        try:
            s = self.session.shop()
            self.name_edit.setText(s["name"])
            self.state_box.setCurrentIndex(max(self.state_box.findData(s["state_code"]), 0))
            self.gstin_edit.setText(s["gstin"] or "")
            self.address_edit.setText(s["address"])
            self.footer_edit.setText(s["bill_footer"])
            self.gst_box.setChecked(bool(s["gst_enabled"]))
            self.incl_box.setChecked(bool(s["price_includes_gst"]))
            self.oversell_box.setCurrentIndex(max(self.oversell_box.findData(s["oversell_policy"]), 0))
            self.template_box.setCurrentIndex(max(self.template_box.findData(s["template"]), 0))
            for key, check in self.feature_boxes.items():
                check.setChecked(segments.feature_enabled(self.session.conn, key))
            self.layout_box.setCurrentIndex(max(self.layout_box.findData(self.session.settings.print_layout), 0))
            self.auto_print_box.setChecked(self.session.settings.auto_print)
            self.language_box.setCurrentIndex(max(self.language_box.findData(i18n.get_language()), 0))
        finally:
            self._loading = False

    def apply_read_only(self, read_only):
        for widget in (self.name_edit, self.state_box, self.gstin_edit, self.address_edit, self.footer_edit,
                       self.save_shop_button, self.gst_box, self.incl_box, self.oversell_box, self.template_box,
                       self.apply_template_button, *self.feature_boxes.values()):
            widget.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()   # always show what is actually stored

    def save_shop(self):
        def run():
            state = self.state_box.currentData()
            if validators.gstin_error(self.gstin_edit.text(), state):
                self._warn("ob.invalid_gstin")
                return
            shop.update_shop(self.session.conn, name=self.name_edit.text(), state_code=state,
                             gstin=self.gstin_edit.text().strip().upper() or None,
                             address=self.address_edit.text().strip(), bill_footer=self.footer_edit.text().strip())
        self._guarded(run)

    def _on_billing(self):
        if self._loading:
            return
        self._guarded(lambda: shop.update_shop(
            self.session.conn, gst_enabled=self.gst_box.isChecked(), price_includes_gst=self.incl_box.isChecked(),
            oversell_policy=self.oversell_box.currentData()))

    def apply_template(self):
        def run():
            if self._confirm("set.template_confirm"):
                segments.apply_template(self.session.conn, self.template_box.currentData())
        self._guarded(run)

    def _on_feature(self, key, checked):
        if self._loading:
            return
        self._guarded(lambda: segments.set_feature(self.session.conn, key, checked))

    def _on_print(self):
        if self._loading:
            return
        self.session.settings.print_layout = self.layout_box.currentData()
        self.session.settings.auto_print = self.auto_print_box.isChecked()
        self._guarded(self.session.save_settings)

    def _on_language(self):
        if self._loading:
            return
        code = self.language_box.currentData()
        if code != i18n.get_language():
            self._guarded(lambda: self.session.set_language(code))

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _warn(self, key):
        QMessageBox.warning(self, "", tr(key))

    def _confirm(self, key):
        answer = QMessageBox.question(self, "", tr(key),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes
```
Replace `retail_ui/screens/registry.py` list with `[..., StaffScreen, SettingsScreen]` (add the import).

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_settings.py tests/ui/test_ui_session.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the settings screen (shop, billing, segment features, printing, language)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 21: Backup, restore and licence screen

**Files:**
- Create: `retail_ui/screens/data.py`, `tests/ui/test_ui_data.py`
- Modify: `retail_ui/session.py` (re-apply the restored shop's language), `tests/ui/test_ui_session.py` (one test), `retail_ui/screens/registry.py`, `retail/locales/*.json` (via tool)

**Interfaces:**
- Consumes: `session.backup_now/restore_from/activate/save_settings/settings/license/machine_id`, `backup.list_backups`, `fmt.date_text`, `vendor.VENDOR_PHONE`.
- Produces: `AppSession.restore_from` now also re-applies the restored database's language (emits `language_changed` when it differs); `DataScreen(session)` (`nav_key = "nav.data"`) with `backup_dir_edit, extra_dir_edit, save_paths_button, backup_now_button, backups_list, restore_button, buyer_label, expires_label, plan_label, state_label, key_edit, activate_button, copy_button, status_label, about_label`; actions `save_paths()`, `backup_now()`, `restore_selected()`, `activate()`; hook `_confirm(key)`. **Backup, restore, activation and folder settings stay enabled after licence expiry** (they must never trap the owner).

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_ui_session.py`:
```python
def test_restore_reapplies_the_restored_shop_language(make_session, qtbot):
    s = make_session()                        # language "en"
    snapshot = s.backup_now().path
    s.set_language("hi")
    with qtbot.waitSignal(s.language_changed) as blocker:
        s.restore_from(snapshot)
    assert blocker.args == ["en"] and i18n.get_language() == "en"
```

`tests/ui/test_ui_data.py`:
```python
import pytest
from PySide6.QtGui import QGuiApplication

import retail
from retail import i18n
from retail import license as lic
from retail.services import items
from retail_ui import vendor
from retail_ui.screens.data import DataScreen
from tools import license_issuer


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = DataScreen(session)
    qtbot.addWidget(sc)
    sc.errors = []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._confirm = lambda key: True
    sc.refresh()
    return sc


def test_licence_and_about_information(screen):
    assert "Test Shop" in screen.buyer_label.text() and "31-12-2099" in screen.expires_label.text()
    assert i18n.tr("data.status_active") in screen.state_label.text()
    assert vendor.VENDOR_PHONE in screen.about_label.text()
    assert f"v{retail.__version__}" in screen.about_label.text()


def test_expired_licence_is_labelled_read_only(screen):
    screen.session.license = lic.LicenseState("expired", buyer="Test Shop", expires="2020-01-01", plan="standard")
    screen.refresh()
    assert i18n.tr("data.status_expired") in screen.state_label.text()


def test_backup_now_creates_a_file_lists_it_and_says_so(screen):
    screen.backup_now()
    assert screen.backups_list.count() == 1
    name = next(screen.session.backup_dir.glob("daily-*.db")).name
    assert name in screen.status_label.text() and name in screen.backups_list.item(0).text()


def test_a_missing_second_location_is_reported_without_failing_the_backup(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen.session.settings.extra_backup_dir = str(blocker / "usb")
    screen.backup_now()
    assert screen.backups_list.count() == 1 and i18n.tr("data.extra_failed") in screen.status_label.text()


def test_save_paths_creates_folders_and_persists(screen, tmp_path):
    from retail_ui import settings as ui_settings
    screen.backup_dir_edit.setText(str(tmp_path / "bk"))
    screen.extra_dir_edit.setText(str(tmp_path / "usb"))
    screen.save_paths()
    assert (tmp_path / "bk").is_dir() and (tmp_path / "usb").is_dir()
    saved = ui_settings.load(screen.session.paths.settings_path)
    assert (saved.backup_dir, saved.extra_backup_dir) == (str(tmp_path / "bk"), str(tmp_path / "usb"))
    assert screen.errors == []


def test_unwritable_path_is_reported_and_not_saved(screen, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    screen.backup_dir_edit.setText(str(blocker / "sub"))
    screen.save_paths()
    assert len(screen.errors) == 1 and screen.session.settings.backup_dir == ""


def test_restore_replaces_the_data_after_confirmation(screen):
    conn = screen.session.conn
    screen.backup_now()
    items.create_item(conn, name="Added later", sell_price_paise=1)
    screen.backups_list.setCurrentRow(0)
    asked = []
    screen._confirm = lambda key: asked.append(key) or True
    screen.restore_selected()
    assert asked == ["data.restore_confirm"] and items.list_items(screen.session.conn) == []
    assert i18n.tr("data.restored") in screen.status_label.text() and screen.errors == []


def test_declining_the_confirmation_changes_nothing(screen):
    screen.backup_now()
    items.create_item(screen.session.conn, name="Keep", sell_price_paise=1)
    screen.backups_list.setCurrentRow(0)
    screen._confirm = lambda key: False
    screen.restore_selected()
    assert [r["name"] for r in items.list_items(screen.session.conn)] == ["Keep"]


def test_restoring_a_corrupt_file_is_reported_and_keeps_the_data(screen):
    items.create_item(screen.session.conn, name="Keep", sell_price_paise=1)
    bad = screen.session.backup_dir / "daily-20200101-000000.db"
    bad.write_bytes(b"this is not a database")
    screen.refresh()
    screen.backups_list.setCurrentRow(0)
    screen.restore_selected()
    assert len(screen.errors) == 1 and [r["name"] for r in items.list_items(screen.session.conn)] == ["Keep"]


def test_restore_needs_a_selection(screen):
    screen._confirm = lambda key: pytest.fail("nothing is selected")
    screen.restore_selected()


def test_activating_a_valid_key_updates_the_licence(screen, keypair, machine_id):
    key = license_issuer.issue(keypair[0], machine=machine_id, buyer="New Buyer", expires="2098-06-01")
    screen.key_edit.setPlainText(f"  {key}\n")
    screen.activate()
    assert "01-06-2098" in screen.expires_label.text() and screen.key_edit.toPlainText() == ""
    assert i18n.tr("data.key_ok") in screen.status_label.text()


def test_an_invalid_key_changes_nothing(screen):
    screen.key_edit.setPlainText("garbage")
    screen.activate()
    assert i18n.tr("act.invalid") in screen.status_label.text() and "31-12-2099" in screen.expires_label.text()


def test_copy_machine_id(screen):
    screen.copy_button.click()
    assert QGuiApplication.clipboard().text() == screen.session.machine_id


def test_everything_here_stays_available_when_read_only_and_retranslates(screen):
    screen.apply_read_only(True)
    for name in ("save_paths_button", "backup_now_button", "restore_button", "activate_button", "copy_button"):
        assert getattr(screen, name).isEnabled(), name
    i18n.set_language("hi")
    screen.retranslate()
    assert screen.backup_now_button.text() == i18n.tr("data.backup_now")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_data.py tests/ui/test_ui_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.screens.data'`; the new session test fails (no `language_changed` after restore).

- [ ] **Step 3: Add the strings**

Create `.superpowers/locale/task21.json`:
```json
{
  "nav.data": {"en": "Backup & License", "hi": "बैकअप और लाइसेंस", "te": "బ్యాకప్ & లైసెన్స్"},
  "data.paths": {"en": "Backup folders", "hi": "बैकअप फ़ोल्डर", "te": "బ్యాకప్ ఫోల్డర్లు"},
  "data.save_paths": {"en": "Save folders", "hi": "फ़ोल्डर सहेजें", "te": "ఫోల్డర్లను సేవ్ చేయండి"},
  "data.backup_now": {"en": "Back up now", "hi": "अभी बैकअप लें", "te": "ఇప్పుడే బ్యాకప్ తీసుకోండి"},
  "data.backups": {"en": "Available backups", "hi": "उपलब्ध बैकअप", "te": "అందుబాటులో ఉన్న బ్యాకప్‌లు"},
  "data.restore": {"en": "Restore selected backup", "hi": "चुना हुआ बैकअप रीस्टोर करें", "te": "ఎంచుకున్న బ్యాకప్‌ను రీస్టోర్ చేయండి"},
  "data.restore_confirm": {"en": "Restore this backup? Your current data will be replaced (a safety copy is kept).", "hi": "यह बैकअप रीस्टोर करें? आपका मौजूदा डेटा बदल जाएगा (एक सुरक्षा कॉपी रखी जाती है)।", "te": "ఈ బ్యాకప్‌ను రీస్టోర్ చేయాలా? మీ ప్రస్తుత డేటా మారుతుంది (భద్రత కోసం ఒక కాపీ ఉంచబడుతుంది)."},
  "data.backup_done": {"en": "Backup saved: {name}", "hi": "बैकअप सहेजा गया: {name}", "te": "బ్యాకప్ సేవ్ అయింది: {name}"},
  "data.extra_failed": {"en": "The second copy could not be written. Check that the folder or drive is available.", "hi": "दूसरी कॉपी नहीं लिखी जा सकी। जाँचें कि फ़ोल्डर या ड्राइव उपलब्ध है।", "te": "రెండో కాపీ రాయలేకపోయాం. ఫోల్డర్ లేదా డ్రైవ్ అందుబాటులో ఉందో చూడండి."},
  "data.restored": {"en": "Backup restored.", "hi": "बैकअप रीस्टोर हो गया।", "te": "బ్యాకప్ రీస్టోర్ అయింది."},
  "data.license": {"en": "License", "hi": "लाइसेंस", "te": "లైసెన్స్"},
  "data.buyer": {"en": "Licensed to: {name}", "hi": "लाइसेंस धारक: {name}", "te": "లైసెన్స్ పొందినవారు: {name}"},
  "data.expires": {"en": "Valid until: {date}", "hi": "वैध तिथि: {date}", "te": "చెల్లుబాటు తేదీ: {date}"},
  "data.plan": {"en": "Plan: {plan}", "hi": "प्लान: {plan}", "te": "ప్లాన్: {plan}"},
  "data.status_active": {"en": "Active", "hi": "सक्रिय", "te": "క్రియాశీలం"},
  "data.status_expired": {"en": "Expired — read-only", "hi": "समाप्त — केवल देखने के लिए", "te": "గడువు ముగిసింది — చూడటానికి మాత్రమే"},
  "data.new_key": {"en": "Enter a new license key", "hi": "नई लाइसेंस कुंजी डालें", "te": "కొత్త లైసెన్స్ కీ నమోదు చేయండి"},
  "data.key_ok": {"en": "License updated.", "hi": "लाइसेंस अपडेट हो गया।", "te": "లైసెన్స్ నవీకరించబడింది."},
  "data.contact": {"en": "Support: {phone}", "hi": "सहायता: {phone}", "te": "సహాయం: {phone}"}
}
```
Run: `.venv/Scripts/python -m tools.locale_add .superpowers/locale/task21.json`

- [ ] **Step 4: Implement**

In `retail_ui/session.py`, replace the `finally:` block of `restore_from` with:
```python
        finally:
            self.conn = db.open_shop(self.paths.db_path, self.backup_dir)
            guard.set_read_only(self.license.read_only)
            if self.has_shop():  # the restored shop may use a different language
                code = self.shop()["language"]
                if code != i18n.get_language():
                    i18n.set_language(code)
                    self.language_changed.emit(code)
            self.data_changed.emit()
```

`retail_ui/screens/data.py`:
```python
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from retail.i18n import tr
from retail.services import backup
from retail_ui import APP_NAME, __version__, fmt, vendor
from retail_ui.errors import show_error
from retail_ui.widgets.base import Screen


class DataScreen(Screen):
    nav_key = "nav.data"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        paths_box = self._group("data.paths", layout)
        form = QFormLayout(paths_box)
        self.backup_dir_edit, self.extra_dir_edit = QLineEdit(), QLineEdit()
        form.addRow(self.bind(QLabel(), "ob.backup_dir"), self._with_browse(self.backup_dir_edit))
        form.addRow(self.bind(QLabel(), "ob.extra_dir"), self._with_browse(self.extra_dir_edit))
        self.save_paths_button = self.bind(QPushButton(), "data.save_paths")
        self.save_paths_button.clicked.connect(lambda _=False: self.save_paths())
        form.addRow(self.save_paths_button)

        backup_box = self._group("data.backups", layout)
        bl = QVBoxLayout(backup_box)
        self.backups_list = QListWidget()
        bl.addWidget(self.backups_list)
        row = QHBoxLayout()
        self.backup_now_button = self.bind(QPushButton(), "data.backup_now")
        self.restore_button = self.bind(QPushButton(), "data.restore")
        row.addWidget(self.backup_now_button)
        row.addWidget(self.restore_button)
        bl.addLayout(row)
        self.backup_now_button.clicked.connect(lambda _=False: self.backup_now())
        self.restore_button.clicked.connect(lambda _=False: self.restore_selected())

        license_box = self._group("data.license", layout)
        ll = QVBoxLayout(license_box)
        self.buyer_label, self.expires_label = QLabel(), QLabel()
        self.plan_label, self.state_label = QLabel(), QLabel()
        for label in (self.buyer_label, self.expires_label, self.plan_label, self.state_label):
            ll.addWidget(label)
        machine_row = QHBoxLayout()
        machine_row.addWidget(QLabel(f"{tr('act.machine_id')}: {session.machine_id}"))
        self.copy_button = self.bind(QPushButton(), "act.copy")
        self.copy_button.clicked.connect(lambda _=False: QGuiApplication.clipboard().setText(session.machine_id))
        machine_row.addWidget(self.copy_button)
        ll.addLayout(machine_row)
        ll.addWidget(self.bind(QLabel(), "data.new_key"))
        self.key_edit = QPlainTextEdit()
        self.key_edit.setFixedHeight(70)
        ll.addWidget(self.key_edit)
        self.activate_button = self.bind(QPushButton(), "act.activate")
        self.activate_button.clicked.connect(lambda _=False: self.activate())
        ll.addWidget(self.activate_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.about_label = QLabel()
        layout.addWidget(self.status_label)
        layout.addWidget(self.about_label)
        layout.addStretch(1)

    def _group(self, title_key, layout):
        group = QGroupBox()
        self.bind(group, title_key, "setTitle")
        layout.addWidget(group)
        return group

    def _with_browse(self, edit):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit)
        button = self.bind(QPushButton(), "common.browse")
        button.clicked.connect(lambda _=False: self._browse(edit))
        row.addWidget(button)
        return holder

    def _browse(self, edit):
        folder = QFileDialog.getExistingDirectory(self, tr("common.browse"), edit.text())
        if folder:
            edit.setText(folder)

    # --- Screen protocol ------------------------------------------------------
    def retranslate(self):
        super().retranslate()
        self.refresh()

    def refresh(self):
        s = self.session
        self.backup_dir_edit.setText(s.settings.backup_dir)
        self.extra_dir_edit.setText(s.settings.extra_backup_dir)
        self.backups_list.clear()
        for path in backup.list_backups(s.backup_dir):
            item = QListWidgetItem(f"{path.name}    ({path.stat().st_size // 1024} KB)")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.backups_list.addItem(item)
        lic = s.license
        self.buyer_label.setText(tr("data.buyer", name=lic.buyer))
        self.expires_label.setText(tr("data.expires", date=fmt.date_text(lic.expires)))
        self.plan_label.setText(tr("data.plan", plan=lic.plan))
        self.state_label.setText(tr("data.status_active") if lic.status == "active" else tr("data.status_expired"))
        self.about_label.setText(f"{APP_NAME}  v{__version__}    {tr('data.contact', phone=vendor.VENDOR_PHONE)}")

    def apply_read_only(self, read_only):
        """Nothing here is blocked: backups, restores, folders and activation must always work."""

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action):
        try:
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()

    def save_paths(self):
        def run():
            backup_dir, extra = self.backup_dir_edit.text().strip(), self.extra_dir_edit.text().strip()
            for folder in (backup_dir, extra):
                if folder:
                    Path(folder).mkdir(parents=True, exist_ok=True)
            self.session.settings.backup_dir = backup_dir
            self.session.settings.extra_backup_dir = extra
            self.session.save_settings()
        self._guarded(run)

    def backup_now(self):
        def run():
            result = self.session.backup_now()
            message = tr("data.backup_done", name=result.path.name)
            if result.extra_error:
                message += "\n" + tr("data.extra_failed")
            self.status_label.setText(message)
        self._guarded(run)

    def restore_selected(self):
        def run():
            item = self.backups_list.currentItem()
            if item is None or not self._confirm("data.restore_confirm"):
                return
            self.session.restore_from(item.data(Qt.ItemDataRole.UserRole))
            self.status_label.setText(tr("data.restored"))
        self._guarded(run)

    def activate(self):
        def run():
            state = self.session.activate(self.key_edit.toPlainText().strip())
            if state.status == "invalid":
                self.status_label.setText(tr("act.invalid"))
            else:
                self.key_edit.clear()
                self.status_label.setText(tr("data.key_ok"))
        self._guarded(run)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _confirm(self, key):
        answer = QMessageBox.question(self, "", tr(key),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes
```
Replace `retail_ui/screens/registry.py` list with `[..., SettingsScreen, DataScreen]` (add the import) — nine screens in total.

- [ ] **Step 5: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_data.py tests/ui/test_ui_session.py tests/test_i18n.py -v` then the full suite.
Expected: all PASS.

```bash
git add -A
git commit -m "feat: add the backup, restore and licence screen" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 22: Application entry point, self-test and whole-app smoke test

**Files:**
- Create: `retail_ui/app.py`, `retail_ui/__main__.py`, `tests/ui/test_ui_app_smoke.py`
- Modify: `retail_ui/screens/registry.py` (final list)

**Interfaces:**
- Consumes: `bootstrap.bootstrap`, `activation.request_activation`, `onboarding.run_onboarding`, `MainWindow`, `registry.all_screens`, `fonts`, `AppPaths`, `license.get_machine_id`, `public_key.PUBLIC_KEY`.
- Produces: `app.configure_logging(paths) -> logging.Handler`; `app.install_excepthook() -> callable` (logs unhandled exceptions and shows the translated generic message — the app never dies silently or shows a Python traceback); `app.selftest() -> int` (0 = OK: temporary database opens and migrates, public key is 32 bytes, all three catalogues and all templates load; used by the installer build); `app.main(argv=None) -> int`; `python -m retail_ui` runs `main()`. Final `registry.all_screens()` order: Counter, Bills, Items, Stock, Parties, Reports, Staff, Settings, Data.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_ui_app_smoke.py`:
```python
import logging
import sys

import pytest

from retail import guard, i18n
from retail import license as lic
from retail.services import billing, items, parties, stock
from retail_ui import app, errors
from retail_ui.main_window import MainWindow
from retail_ui.screens import registry


@pytest.fixture(autouse=True)
def _reset():
    yield
    i18n.set_language("en")
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    if QApplication.instance():
        QApplication.instance().setFont(QFont())


def test_registry_has_every_screen_in_order():
    assert [cls.nav_key for cls in registry.all_screens()] == [
        "nav.counter", "nav.bills", "nav.items", "nav.stock", "nav.parties", "nav.reports", "nav.staff",
        "nav.settings", "nav.data"]


def test_selftest_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert app.selftest() == 0
    assert app.main(["retail", "--selftest"]) == 0
    assert not (tmp_path / "RetailApp").exists()          # it works in a throw-away folder


def test_selftest_reports_failure(monkeypatch, capsys):
    from retail import segments
    monkeypatch.setattr(segments, "list_templates", lambda: ["does-not-exist"])
    assert app.selftest() == 1
    assert "selftest" in capsys.readouterr().err.lower()


def test_logging_goes_to_a_rotating_file(paths):
    handler = app.configure_logging(paths)
    try:
        logging.getLogger("retail_ui").info("hello log")
        handler.flush()
        assert "hello log" in paths.log_path.read_text(encoding="utf-8")
    finally:
        logging.getLogger("retail_ui").removeHandler(handler)
        handler.close()


def test_the_exception_hook_logs_and_shows_the_translated_message(monkeypatch, caplog):
    shown = []
    monkeypatch.setattr(app, "show_error", lambda parent, exc: shown.append(errors.message_for(exc)))
    old = sys.excepthook
    try:
        hook = app.install_excepthook()
        assert sys.excepthook is hook
        with caplog.at_level(logging.CRITICAL, logger="retail_ui"):
            hook(RuntimeError, RuntimeError("boom"), None)
        assert shown == [i18n.tr("err.unexpected")] and "unhandled" in caplog.text.lower()
    finally:
        sys.excepthook = old


def test_the_exception_hook_survives_a_failure_while_reporting(monkeypatch):
    monkeypatch.setattr(app, "show_error", lambda parent, exc: (_ for _ in ()).throw(RuntimeError("no GUI")))
    old = sys.excepthook
    try:
        app.install_excepthook()(RuntimeError, RuntimeError("boom"), None)   # must not raise
    finally:
        sys.excepthook = old


def build_window(make_session, qtbot, template="grocery"):
    session = make_session(template=template)
    window = MainWindow(session, registry.all_screens())
    qtbot.addWidget(window)
    window.show()
    return session, window


@pytest.mark.parametrize("template", ["grocery", "electronics"])
def test_every_screen_opens_in_every_language_and_in_read_only(make_session, qtbot, template):
    session, window = build_window(make_session, qtbot, template)
    conn = session.conn
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, barcodes=["8901"])
    stock.record(conn, item, 9000, "opening")
    parties.create_party(conn, name="Ravi", phone="9876543210")
    assert window.nav.count() == 9
    for code in ("en", "hi", "te", "en"):
        session.set_language(code)
        for row in range(window.nav.count()):
            window.nav.setCurrentRow(row)
            assert window.nav.item(row).text() == i18n.tr(window.screens[row].nav_key)
    session.license = lic.LicenseState("expired", buyer="B", expires="2020-01-01", plan="standard")
    guard.set_read_only(True)
    session.read_only_changed.emit(True)
    assert not window.banner.isHidden()
    for row in range(window.nav.count()):
        window.nav.setCurrentRow(row)
    window.close()


def test_a_complete_sale_through_the_real_window(make_session, qtbot):
    session, window = build_window(make_session, qtbot)
    conn = session.conn
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, barcodes=["8901"])
    stock.record(conn, item, 9000, "opening")
    counter = window.screens[0]
    counter._show_error = lambda exc: pytest.fail(str(exc))
    counter._ask_payments = lambda total, party_id: [("cash", total)]
    counter.entry.setText("2*8901")
    counter.entry.returnPressed.emit()
    counter.pay()
    assert billing.get_bill(conn, counter.last_bill_id)["bill"]["bill_no"] == "S000001"
    window.nav.setCurrentRow(1)                                    # the Bills screen lists it
    assert window.screens[1].model.rowCount() == 1
    window.close()
    assert list(session.backup_dir.glob("daily-*.db"))             # closing took the daily backup
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_app_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'retail_ui.app'`.

- [ ] **Step 3: Implement**

`retail_ui/app.py`:
```python
import logging
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication

from retail import db, i18n, public_key, segments
from retail import license as lic
from retail_ui import APP_NAME, fonts
from retail_ui.bootstrap import bootstrap
from retail_ui.dialogs.activation import request_activation
from retail_ui.dialogs.onboarding import run_onboarding
from retail_ui.errors import show_error
from retail_ui.main_window import MainWindow
from retail_ui.paths import AppPaths
from retail_ui.screens import registry

log = logging.getLogger("retail_ui")


def configure_logging(paths) -> logging.Handler:
    handler = RotatingFileHandler(paths.log_path, maxBytes=500_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    return handler


def install_excepthook():
    """Unhandled errors are logged and shown as a translated message, never as a traceback."""
    def hook(exc_type, exc, tb):
        log.critical("unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            show_error(None, exc)
        except Exception:
            log.exception("could not show the error to the user")

    sys.excepthook = hook
    return hook


def selftest() -> int:
    """Used by the installer build: 0 = the packaged app can open a database and load its data files."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            paths.ensure()
            conn = db.open_shop(paths.db_path, paths.backup_dir)
            try:
                if db.schema_version(conn) != db.latest_version():
                    raise RuntimeError("database migration did not complete")
            finally:
                conn.close()
        if len(public_key.PUBLIC_KEY) != 32:
            raise RuntimeError("the embedded licence public key is not 32 bytes")
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            i18n.tr("bill.total")
        i18n.set_language(i18n.DEFAULT_LANGUAGE)
        for name in segments.list_templates():
            segments.load(name)
        return 0
    except Exception as exc:
        print(f"selftest failed: {exc}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        return selftest()
    qt_app = QApplication(argv)
    qt_app.setApplicationName(APP_NAME)
    paths = AppPaths.default()
    paths.ensure()
    configure_logging(paths)
    install_excepthook()
    fonts.apply_language_font(qt_app, "en")
    session = bootstrap(paths, public_key=public_key.PUBLIC_KEY, machine_id=lic.get_machine_id(),
                        request_activation=request_activation, run_onboarding=run_onboarding)
    if session is None:
        return 0
    fonts.apply_language_font(qt_app, i18n.get_language())
    window = MainWindow(session, registry.all_screens())
    window.show()
    try:
        return qt_app.exec()
    finally:
        session.close()
```

`retail_ui/__main__.py`:
```python
from retail_ui.app import main

raise SystemExit(main())
```
Replace `retail_ui/screens/registry.py` with the final list:
```python
from retail_ui.screens.bills import BillsScreen
from retail_ui.screens.counter import CounterScreen
from retail_ui.screens.data import DataScreen
from retail_ui.screens.items import ItemsScreen
from retail_ui.screens.parties import PartiesScreen
from retail_ui.screens.reports import ReportsScreen
from retail_ui.screens.settings import SettingsScreen
from retail_ui.screens.staff import StaffScreen
from retail_ui.screens.stock import StockScreen
from retail_ui.widgets.base import Screen


def all_screens() -> list[type[Screen]]:
    """Navigation order."""
    return [CounterScreen, BillsScreen, ItemsScreen, StockScreen, PartiesScreen, ReportsScreen,
            StaffScreen, SettingsScreen, DataScreen]
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_app_smoke.py -v` then the full suite `.venv/Scripts/python -W error::ResourceWarning -m pytest -q`.
Expected: all PASS. If the smoke test finds a runtime error in a screen, fix that screen (with a regression test in its own test file), do not weaken the smoke test.

- [ ] **Step 5: Run the app once by hand and commit**

Run: `.venv/Scripts/python -m retail_ui` — expected: an activation window appears (machine ID shown); close it with Quit. (Do not enter or generate any key here; real keys are issued with `tools.license_issuer` from the vendor's machine.)

```bash
git add -A
git commit -m "feat: add the application entry point, self-test and whole-app smoke test" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 23: Grocery-volume performance check

Spec §10 asks for an early check that a grocery catalogue (thousands of SKUs) stays responsive. These tests pin generous ceilings on a 5,000-item shop so a regression (for example an accidental full-table scan on every keystroke) is caught.

**Files:**
- Create: `tests/ui/test_ui_performance.py`
- Modify: `pyproject.toml` (register the `perf` marker)

**Interfaces:**
- Consumes: the finished screens and engine. No new production code unless a ceiling is missed (see Step 3).

- [ ] **Step 1: Register the marker and write the tests**

In `pyproject.toml` under `[tool.pytest.ini_options]` add:
```toml
markers = ["perf: timing checks with generous ceilings (grocery-sized data)"]
```

`tests/ui/test_ui_performance.py`:
```python
import time

import pytest

from retail.services import billing, items, parties
from retail_ui.screens.counter import CounterScreen
from retail_ui.screens.items import ItemsScreen
from retail_ui.screens.parties import PartiesScreen
from retail_ui.screens.stock import StockScreen

pytestmark = pytest.mark.perf
N_ITEMS = 5000


@pytest.fixture
def big_shop(make_session):
    session = make_session()
    conn = session.conn
    conn.execute("BEGIN")
    conn.executemany("INSERT INTO item(name, sku, sell_price_paise, gst_rate_bp) VALUES (?,?,?,?)",
                     [(f"Product {i:05d}", f"SKU{i:05d}", 1000 + i, 1800) for i in range(N_ITEMS)])
    conn.executemany("INSERT INTO item_barcode(code, item_id) VALUES (?,?)",
                     [(f"890{i:09d}", i + 1) for i in range(N_ITEMS)])
    conn.executemany("INSERT INTO stock_movement(item_id, qty_milli, type, created_at) VALUES (?,?,?,?)",
                     [(i + 1, 100_000, "opening", "2026-01-01T00:00:00") for i in range(N_ITEMS)])
    conn.execute("COMMIT")
    return session


def timed(fn):
    started = time.perf_counter()
    fn()
    return time.perf_counter() - started


def type_and_enter(screen, text):
    screen.entry.setText(text)
    screen.entry.returnPressed.emit()


def test_scanning_a_barcode_is_instant(big_shop, qtbot):
    screen = CounterScreen(big_shop)
    qtbot.addWidget(screen)
    screen._show_error = lambda exc: pytest.fail(str(exc))
    assert timed(lambda: type_and_enter(screen, "890000004999")) < 0.25
    assert screen.model.rowCount() == 1


def test_a_name_search_is_fast_enough_while_typing(big_shop, qtbot):
    screen = CounterScreen(big_shop)
    qtbot.addWidget(screen)
    screen._ask_pick = lambda rows: None
    assert timed(lambda: type_and_enter(screen, "product 04999")) < 0.5


def test_a_sixty_line_bill_builds_and_renders_quickly(big_shop, qtbot):
    screen = CounterScreen(big_shop)
    qtbot.addWidget(screen)
    screen._show_error = lambda exc: pytest.fail(str(exc))

    def build():
        for i in range(60):
            type_and_enter(screen, f"890{i:09d}")

    assert timed(build) < 6.0
    assert screen.model.rowCount() == 60
    assert timed(screen._render) < 0.3


def test_items_and_stock_screens_load_a_five_thousand_item_catalogue(big_shop, qtbot):
    items_screen = ItemsScreen(big_shop)
    stock_screen = StockScreen(big_shop)
    for w in (items_screen, stock_screen):
        qtbot.addWidget(w)
    assert timed(items_screen.refresh) < 1.5 and items_screen.model.rowCount() == 500
    assert timed(stock_screen.refresh) < 4.0 and stock_screen.stock_model.rowCount() == N_ITEMS
    assert timed(lambda: items_screen.search_edit.setText("Product 04999")) < 0.5
    assert items_screen.model.rowCount() == 1


def test_a_big_customer_list_loads(big_shop, qtbot):
    conn = big_shop.conn
    for i in range(500):
        parties.create_party(conn, name=f"Customer {i:04d}", phone=f"98{i:08d}")
    screen = PartiesScreen(big_shop)
    qtbot.addWidget(screen)
    assert timed(screen.refresh) < 3.0 and screen.model.rowCount() == 500


def test_resolving_items_directly_stays_indexed(big_shop):
    conn = big_shop.conn
    assert timed(lambda: [items.resolve(conn, f"890{i:09d}") for i in range(0, N_ITEMS, 50)]) < 0.5
    assert billing.list_held(conn) == []
```

- [ ] **Step 2: Run to see the numbers**

Run: `.venv/Scripts/python -m pytest tests/ui/test_ui_performance.py -v --durations=10`
Expected: all PASS. Note the slowest timings in your report.

- [ ] **Step 3: If a ceiling is missed**

Do **not** raise the ceiling to make the test pass on a slow machine without saying so. First find the cause (for example `items.list_items` scanning `item_barcode` per row, or `billing._retax` growing quadratically with bill length). Fix the cause with a regression test in the owning module's test file, or — if the cause is architectural — stop and report DONE_WITH_CONCERNS with the measured numbers so the owner can decide. A 60-line bill is far beyond a normal kirana bill; if only that test misses, report it rather than hiding it.

- [ ] **Step 4: Run the whole suite and commit**

Run: `.venv/Scripts/python -W error::ResourceWarning -m pytest -q`
Expected: all PASS.

```bash
git add -A
git commit -m "test: add grocery-volume performance checks for the UI" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 24: Windows packaging (PyInstaller build and Inno Setup installer)

The build itself runs on the vendor's Windows machine and cannot be fully automated here; this task creates the files, pins what *can* be tested statically (nothing secret or vendor-only gets packaged, versions agree), and adds a scripted build with a post-build self-test.

**Files:**
- Create: `packaging/retail_app.spec`, `packaging/build.ps1`, `packaging/installer.iss`, `tests/test_packaging_files.py`
- Modify: `.gitignore`, `README.md`

**Interfaces:**
- Produces: `packaging/build.ps1` (runs the tests, builds `dist/RetailApp/RetailApp.exe` with PyInstaller, runs `RetailApp.exe --selftest`, then compiles the installer if Inno Setup's `iscc` is on the PATH); `dist/installer/RetailApp-Setup-<version>.exe`. The installer installs the program under Program Files and **never touches** `%LOCALAPPDATA%\RetailApp\` (database, licence key, settings, backups), so upgrading or uninstalling keeps the shop's data.

- [ ] **Step 1: Write the failing tests**

`tests/test_packaging_files.py`:
```python
import re
from pathlib import Path

import retail

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "packaging" / "retail_app.spec").read_text(encoding="utf-8")
ISS = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
BUILD = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")


def test_vendor_only_code_and_keys_are_not_packaged():
    assert 'excludes=["tools", "tests", "pytest"]' in SPEC
    for text in (SPEC, ISS):
        lowered = text.lower()
        assert "private.key" not in lowered
        assert "\\keys" not in lowered and "/keys" not in lowered
    assert not [l for l in ISS.splitlines() if l.startswith("Source:") and "tools" in l.lower()]


def test_the_spec_bundles_the_data_files_the_app_reads_at_runtime():
    for pattern in ("retail/migrations", "retail/locales", "retail/segments"):
        assert pattern in SPEC
    assert "__main__.py" in SPEC and "console=False" in SPEC


def test_installer_version_matches_the_package_version():
    match = re.search(r'#define\s+AppVersion\s+"([^"]+)"', ISS)
    assert match and match.group(1) == retail.__version__


def test_installer_leaves_the_users_data_alone():
    assert "never" in ISS.lower() and "%LOCALAPPDATA%\\RetailApp" in ISS
    assert "[UninstallDelete]" not in ISS and "[InstallDelete]" not in ISS
    assert not [l for l in ISS.splitlines() if "{localappdata}" in l.lower() and not l.startswith(";")]


def test_the_build_script_runs_tests_and_the_selftest_before_the_installer():
    order = [BUILD.index(marker) for marker in ("pytest", "PyInstaller", "--selftest", "iscc")]
    assert order == sorted(order)
    assert "ExitCode" in BUILD


def test_the_module_entry_point_exists():
    assert (ROOT / "retail_ui" / "__main__.py").read_text(encoding="utf-8").strip().endswith("raise SystemExit(main())")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_packaging_files.py -v`
Expected: FAIL — `FileNotFoundError: ... packaging/retail_app.spec`.

- [ ] **Step 3: Create the packaging files**

`packaging/retail_app.spec`:
```python
# PyInstaller spec — one-folder build of the desktop app.
# Run from the repo root:  .venv\Scripts\python -m PyInstaller --noconfirm --clean packaging\retail_app.spec
# Vendor-only code (tools/) and anything under keys/ are deliberately NOT bundled.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "retail", "migrations", "*.sql"), "retail/migrations"),
    (os.path.join(ROOT, "retail", "locales", "*.json"), "retail/locales"),
    (os.path.join(ROOT, "retail", "segments", "*.json"), "retail/segments"),
]

a = Analysis(
    [os.path.join(ROOT, "retail_ui", "__main__.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["cryptography.hazmat.primitives.asymmetric.ed25519"],
    excludes=["tools", "tests", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RetailApp", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="RetailApp")
```

`packaging/build.ps1`:
```powershell
# Builds the app and (when Inno Setup is installed) the installer. Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

& $python -m pytest -q -W error::ResourceWarning
if ($LASTEXITCODE -ne 0) { throw "tests failed - not building" }

& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\retail_app.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# The windowed exe has no console, so wait for it and read its exit code.
$run = Start-Process -FilePath (Join-Path $root "dist\RetailApp\RetailApp.exe") -ArgumentList "--selftest" -Wait -PassThru
if ($run.ExitCode -ne 0) { throw "the built app failed its --selftest (exit code $($run.ExitCode))" }

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    & $iscc.Source (Join-Path $root "packaging\installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer written to dist\installer"
} else {
    Write-Warning "Inno Setup (iscc) is not on the PATH, so no installer was built. Install it from https://jrsoftware.org/isinfo.php and re-run."
}
```

`packaging/installer.iss`:
```
; Inno Setup script. AppVersion must equal retail.__version__ (tests/test_packaging_files.py checks this).
; The shop's data lives in %LOCALAPPDATA%\RetailApp. This installer never writes, overwrites or deletes
; anything there, so upgrading or uninstalling keeps the database, licence key, settings and backups.
#define AppName "Retail App"
#define AppVersion "0.1.0"

[Setup]
AppId={{8F2C1A64-5B7D-4E39-A0C2-6D41B9E37F58}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\RetailApp
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=RetailApp-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\RetailApp\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\RetailApp.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\RetailApp.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RetailApp.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
```
Add `dist/`, `build/` (already ignored) and `*.spec`-generated artefacts to `.gitignore` if missing: `dist/` and `build/` must be listed.

Add to `README.md`:
```markdown
## Building the installer (Windows)

1. `python -m venv .venv` then `.venv\Scripts\python -m pip install -e ".[dev]"`
2. Install Inno Setup (https://jrsoftware.org/isinfo.php) and make sure `iscc` is on the PATH.
3. `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`
   — runs the tests, builds `dist\RetailApp\RetailApp.exe`, runs its `--selftest`, then writes
   `dist\installer\RetailApp-Setup-<version>.exe`.

The installer keeps the shop's data in `%LOCALAPPDATA%\RetailApp`; upgrading never touches it.
Licence keys are issued with `python -m tools.license_issuer` on the vendor's machine (never shipped).
The installer is not code-signed, so Windows SmartScreen will warn on first run until a signing
certificate is added.
```

- [ ] **Step 4: Run tests, try the build, and commit**

Run: `.venv/Scripts/python -m pytest tests/test_packaging_files.py -v`
Expected: all PASS.

Then on the vendor's Windows machine run `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`.
Expected: tests pass, `dist\RetailApp\RetailApp.exe` appears, the self-test exits 0, and (with Inno Setup installed) `dist\installer\RetailApp-Setup-0.1.0.exe` appears. If PyInstaller reports a missing module at runtime (the self-test fails), add it to `hiddenimports` in the spec and rebuild; record what you added in your report. Do not commit `dist/` or `build/`.

```bash
git add -A
git commit -m "build: add PyInstaller spec, build script and Inno Setup installer" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 25: Manual test checklist and documentation

Spec §9 requires a manual checklist per segment (screens, printers and scanners cannot be fully covered by automated tests). This task writes it, so a human can sign off a release.

**Files:**
- Create: `docs/manual-test-checklist.md`, `tests/test_docs.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

`tests/test_docs.py`:
```python
from pathlib import Path

DOC = (Path(__file__).resolve().parents[1] / "docs" / "manual-test-checklist.md").read_text(encoding="utf-8")


def test_the_checklist_covers_every_segment_and_the_cross_cutting_areas():
    for heading in ("## 1. Install", "## 2. Activation", "## 3. Onboarding", "## 4. Grocery", "## 5. Electronics",
                    "## 6. Languages", "## 7. Licence expiry", "## 8. Backup", "## 9. Hardware", "## 10. Upgrade",
                    "## 11. Sign-off"):
        assert heading in DOC, heading


def test_the_checklist_has_enough_checks_and_none_are_pre_ticked():
    assert len([l for l in DOC.splitlines() if l.startswith("- [ ]")]) >= 60
    assert "[x]" not in DOC.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_docs.py -v`
Expected: FAIL — `FileNotFoundError: ... manual-test-checklist.md`.

- [ ] **Step 3: Write the checklist**

`docs/manual-test-checklist.md`:
```markdown
# Manual test checklist

Run on a clean Windows 10 PC with the real installer, a real barcode scanner, and the printers you support.
Tick every line; write the build version and date at the bottom. Anything that fails blocks the release.

## 1. Install
- [ ] The installer runs on a PC with no Python installed.
- [ ] The app starts from the Start-menu shortcut (and the desktop shortcut if chosen).
- [ ] The window opens with no console box and no error dialog.
- [ ] `%LOCALAPPDATA%\RetailApp\` is created on first run (database, `app.log`, `backups\`).
- [ ] Windows SmartScreen shows the unsigned-app warning only (nothing is blocked outright).

## 2. Activation
- [ ] First run shows the activation window with a Machine ID.
- [ ] Copy copies the Machine ID; the WhatsApp request opens WhatsApp with the ID filled in.
- [ ] A key issued for a different PC is refused with a clear message and the window stays open.
- [ ] A valid key activates; restarting the app does not ask again.
- [ ] Quit at the activation window exits cleanly and creates no shop data.

## 3. Onboarding
- [ ] The first page lets you pick English, Hindi or Telugu and the next pages appear in that language.
- [ ] A GSTIN that does not match the chosen state is refused; a blank GSTIN is accepted.
- [ ] Choosing Grocery enables weighed items and credit; choosing Electronics enables serial, warranty and EMI.
- [ ] The backup page accepts a second folder (USB drive or synced folder) and creates it.
- [ ] Cancelling the wizard exits without creating a shop; finishing opens the Counter.

## 4. Grocery (kirana / general store)
- [ ] Scanning a barcode adds one line and the input is ready for the next scan with no mouse click.
- [ ] `3*` before a scan adds three; Enter on an empty input does nothing.
- [ ] A weighed item (rice) asks for the weight; `0.5*rice` adds half a kilo without asking.
- [ ] An unknown barcode opens New item with the barcode filled in; saving adds the line.
- [ ] Two items with similar names show a chooser.
- [ ] F2 customer, F3 hold, F4 held bills, F5 discount, F8 discard, Del delete line, F12 pay all work.
- [ ] A held bill survives closing and reopening the app.
- [ ] Pay by cash with "cash given" shows the change; split cash + UPI; credit (udhaar) needs a customer.
- [ ] The customer's udhaar balance rises after a credit sale and falls after Receive payment.
- [ ] Low-stock items are highlighted and listed under Stock.
- [ ] A 58 mm and an 80 mm thermal bill print on the real printer with nothing cut off.
- [ ] Return one item from Bills; stock goes back and the refund matches the bill.
- [ ] The Sales register and GST summary add up to the day's bills; CSV opens correctly in Excel.

## 5. Electronics (mobile / appliances)
- [ ] Selling a phone asks for the IMEI; a wrong or already-sold IMEI is refused with a clear message.
- [ ] Scanning the same IMEI twice on one bill is refused.
- [ ] Paying with EMI is offered; the printed A4 invoice lists the IMEI and the warranty end date.
- [ ] A Purchase with several IMEIs (one per line) creates one unit each; a repeated IMEI is refused.
- [ ] Returning a phone puts that IMEI back in stock; serial items can only be returned whole.
- [ ] An inter-state customer's bill shows IGST; an in-state customer's shows CGST + SGST.
- [ ] Selling below stock behaves as the shop's policy says (block / warn / allow).

## 6. Languages
- [ ] Switching to Hindi and Telugu mid-bill keeps the lines and totals and retranslates every screen.
- [ ] Devanagari and Telugu text draws correctly (no empty boxes) on screens, in dialogs and on printed bills.
- [ ] No English text remains on any screen, dialog or error message in Hindi/Telugu (except brand/technical terms).
- [ ] The chosen language is remembered after restarting.
- [ ] A native speaker has reviewed the Hindi and Telugu strings.

## 7. Licence expiry
- [ ] With an expired key the red read-only banner shows and every write control is disabled.
- [ ] Viewing bills, reports, CSV export, printing, backup and restore still work.
- [ ] Trying a blocked action by keyboard shortcut shows a translated message, never an English error.
- [ ] Entering a renewed key under Backup & License re-enables everything without restarting.

## 8. Backup and restore
- [ ] Closing the app creates one `daily-…` backup; closing again the same day does not create another.
- [ ] Back up now creates a file and lists it; the second folder gets a copy.
- [ ] With the second folder unavailable, the backup still succeeds and a clear warning is shown.
- [ ] Restore replaces the data after confirmation and every screen shows the restored data.
- [ ] Restoring a corrupt or unrelated file is refused and the current data is unchanged.
- [ ] After a restore, the app language and licence still work.

## 9. Hardware
- [ ] The barcode scanner works as a keyboard with no driver and no focus problems.
- [ ] 58 mm thermal printer prints a full bill.
- [ ] 80 mm thermal printer prints a full bill.
- [ ] An A4 printer prints a GST invoice.
- [ ] Save as PDF produces a readable file; WhatsApp opens with the bill text for a customer's number.
- [ ] A 5,000-item catalogue stays responsive when scanning and searching.

## 10. Upgrade
- [ ] Installing a newer version over the old one keeps all data, the licence and the settings.
- [ ] A new database migration runs once, after an automatic `pre-migrate` backup.
- [ ] Uninstalling the app leaves `%LOCALAPPDATA%\RetailApp\` in place.

## 11. Sign-off
- [ ] Build version: ________  Date: ________  Tested by: ________
- [ ] Every item above is ticked, or each failure has a ticket and is not a blocker.
```
Add one line to `README.md` under a "Testing" heading: `Automated: .venv\Scripts\python -m pytest. Manual release checklist: docs/manual-test-checklist.md.`

- [ ] **Step 4: Run tests and commit**

Run: `.venv/Scripts/python -m pytest tests/test_docs.py -v` then the whole suite with `-W error::ResourceWarning`.
Expected: all PASS.

```bash
git add -A
git commit -m "docs: add the manual release checklist and testing notes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (spec coverage)

| Spec item | Covered by |
|---|---|
| §6 counter screen: always-focused input, scan/qty-prefix/SKU/name, quick-add | Tasks 9, 10, 11 |
| §6 F-keys (customer, hold, held, discount, pay), hold/resume | Tasks 9, 11 |
| §6 per-tracking prompts (weighed qty, serial/IMEI, batch auto) | Tasks 9, 10, 11 (batch is automatic in the engine) |
| §6 payment modes cash/UPI/card/EMI/credit, split, change | Task 10 |
| §6 print layouts thermal 58/80 + A4 per template; WhatsApp bill | Tasks 12, 13, 14 |
| §6 GST/estimate bills, intra/inter-state display | Tasks 11, 12 (engine computes; UI shows) |
| §7 activation (machine ID, request, key entry, read-only after expiry) | Tasks 5, 6, 8, 20, 21 |
| §7 backup (daily on close, second location prompt, restore, exports) | Tasks 5, 7, 8, 18, 21 |
| §7 installer keeps data, version shown | Tasks 3, 21, 24 |
| §8 en/hi/te, fonts per language, no English leaks, error text | Tasks 4, 5, 8 and every screen task |
| §9 UI smoke tests; manual checklist per segment | Tasks 22, 25 |
| §10 grocery-volume UI performance check | Task 23 |
| Item / stock / purchase / party / staff / report screens | Tasks 15–19 |
| Settings: shop details, billing switches, template + feature mixing | Task 20 |
| Carry-overs from the engine's final review | Task 1 |
| Reviewer finding M9 (translated errors), M3-adjacent restore UX | Tasks 4, 21 |

Placeholder scan: every code step contains full code; strings are added with the locale tool from complete JSON; the only external artefacts are the Inno Setup program and a Windows machine for the final build (stated in Task 24).

Type consistency (checked while writing): `AppSession` members used by screens (`conn, settings, paths, license, machine_id, backup_dir, shop(), has_shop(), set_language, save_settings, backup_now, restore_from, activate, notify_changed`) are all defined in Tasks 5, 20, 21; `Screen.bind/track/retranslate/refresh/apply_read_only` and `RowsModel.set_rows/id_at` are defined in Task 8 and used consistently; every screen's prompt hooks are named `_ask_*`/`_confirm`/`_warn`/`_show_error` and are the only things tests replace; engine APIs called by screens are the ones added in Task 2 (and `items.has_stock_history` in Task 15).

Known limits, stated so they are not surprises: bill lines are not merged; a quick-added item starts with zero stock; Hindi/Telugu text and GST slab values need native/accountant review; the installer is unsigned; there is no automatic update check; the thermal printers go through the Windows print system (no raw ESC/POS).

**Not run:** none of this plan's code has been executed (running it would mean implementing before approval). Qt-specific details most likely to need a one-line adjustment on first run: `QWizard.initializePage` signature, `QTextDocument.print_`, and `QPageSize`/`QPrinter` enum spellings.
