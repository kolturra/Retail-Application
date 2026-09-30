# Retail Application — Design Spec

Date: 2026-09-30
Status: Draft for review

## 1. Purpose and scope

A Windows desktop retail application, sold as a product to small shop owners in India (GST). It is the multi-segment successor in spirit to **Kuttu** (fashion/boutique), which stays untouched and is used only as a reference.

**Launch segments**
- Grocery / kirana / general store
- Electronics / mobile / appliances

**Out of scope for v1:** fashion (stays in Kuttu), pharmacy, multi-counter LAN sharing, multi-branch cloud sync, mobile owner app, payment-gateway integration (UPI is recorded as a payment mode only).

**Success criteria**
- A grocery shop can bill fast (scan → quantity → Enter → print) entirely from the keyboard.
- An electronics shop can sell serial/IMEI-tracked items with warranty and print an A4 GST invoice.
- Both run on the same core; segment differences are configuration, not code forks.
- A shop never loses data (automatic backup, migration-safe updates) and is never locked out of its own data (read-only after license expiry).

## 2. Decisions taken

| Topic | Decision |
|---|---|
| Customer | Other small shop owners (a product, not an internal tool) |
| Platform | Windows desktop, one PC per shop, works offline |
| Language / UI | Python, PySide6 (Qt, LGPL, dynamically linked) |
| Storage | SQLite, one file per shop; money stored as integer paise |
| Code reuse | Fresh rebuild; Kuttu is a reference for ideas only (licensing, GST, bill print, backup/undo, i18n, WhatsApp bills) |
| Segments | Data-driven templates (JSON) over one shared schema |
| Languages | English (default), Hindi, Telugu, with a completeness test |
| Plans | Single plan in v1; reserved `plan` field in the license payload |
| Bills | GST invoices and non-GST estimate bills, chosen per shop |
| After license expiry | Read-only mode with full export |

## 3. Architecture

Three layers; dependencies point downward only.

```
UI (PySide6)              screens, dialogs, shortcuts, print preview
   ↓ calls
Services (pure Python)    billing, GST, stock, purchases, parties, reports,
                          backup/undo, licensing
   ↓ uses
Data (SQLite)             repositories, migrations, segment templates
```

- The UI contains no business logic; it calls services and renders results. All rules are testable without a window.
- Services are small, one module per concern.
- Money is integer paise everywhere. Line totals are computed once, then summed, so printed and stored bills always agree.
- Stock is an append-only movement ledger; quantity on hand is derived.
- Finished bills are never edited. Corrections are sale returns or cancelling entries, each written to the audit log.

## 4. Data model

| Table | Purpose |
|---|---|
| `shop` | Name, GSTIN, address, state, bill footer, chosen template, license info |
| `item` | Name, SKU, HSN, GST rate, unit, selling and purchase price, reorder level, `tracking` mode |
| `item_barcode` | Multiple barcodes per item |
| `stock_movement` | Append-only ledger: item, qty (decimal), type (purchase / sale / return / adjustment), reference, date |
| `stock_unit` | For tracked items: one row per serial/IMEI or batch (batch no., expiry) |
| `party` | Customers and suppliers: type, phone, GSTIN, opening balance |
| `bill`, `bill_line` | Sales and sale returns; GST split (CGST+SGST or IGST) stored per line |
| `purchase`, `purchase_line` | Supplier bills feeding the stock ledger |
| `payment` | Cash, UPI, card, EMI, credit; credit creates a party balance (udhaar) |
| `warranty` | Electronics: unit, bill, start and end date |
| `staff`, `expense`, `audit_log` | Salary/rent/expenses; who changed what |

**Item `tracking` modes:** `none` (counted), `weighed` (decimal qty), `batch` (batch and expiry), `serial` (one `stock_unit` per serial/IMEI).

**Migrations:** versioned; each app start applies pending migrations after taking a backup.

## 5. Segment templates

Shipped as JSON; a template only presets settings and enables screens, never changes the schema. A shop can enable features from both (e.g. a general store selling loose rice and phones).

- `grocery.json`: default tracking none/weighed; units kg/g/pcs/litre; thermal fast-bill layout; low-stock alerts; udhaar on; common GST slabs preloaded.
- `electronics.json`: default tracking serial; warranty on; EMI payment mode; exchange/return flow; A4 invoice layout with serials and warranty terms; service notes.

## 6. Billing flow and counter experience

**Counter screen (keyboard-first)**
- Always-focused input: barcode scan, item code/name search, or quantity prefix (`3*` then scan). Scanners work as keyboards, so no special driver is needed.
- Fast line table (item, qty, rate, discount, GST, amount); arrow keys, Delete, F-keys for discount, customer, hold bill, pay.
- Large running totals: subtotal, GST split, round-off, grand total.
- Payment: cash with change, UPI, card, credit, or split; then print/WhatsApp; a new bill opens automatically.
- Hold and resume bills.

**Input resolution (one service function):** barcode → exact SKU → name search → quick-add (three fields) if not found.

**Per-tracking behaviour:** `none` add and continue; `weighed` focus quantity; `serial` prompt for IMEI/serial, validate in-stock and unsold, lock to line, set warranty at payment; `batch` auto-select earliest expiry, overridable.

**Rules (service layer)**
- Intra-state → CGST+SGST; inter-state → IGST, from shop and customer state.
- Selling below stock is a per-shop setting: block, warn or allow.
- Printing: thermal 58mm/80mm and A4, chosen per template.
- Non-GST estimate bills supported per shop setting.

## 7. Licensing, updates, backup

**Licensing (offline, extends Kuttu's model)**
- Machine ID derived from the Windows MachineGuid; the shop sends it to the vendor; the vendor returns a key signed with an Ed25519 private key; the app verifies with an embedded public key.
- Signed payload adds **expiry date** and **plan** (single plan in v1, field reserved).
- On expiry: read-only mode with full export; the owner is never locked out of their data.
- A separate key-issuer tool holds the private key and is never shipped. Its secure storage and backup is a stated operational risk.
- Accepted limit: determined users can bypass offline licensing; the aim is to stop casual key sharing.

**Updates**
- A new installer replaces the app and keeps the shop's database; migrations run on next launch after an automatic backup.
- The app displays its version. A later optional check may read a single static "latest version" file (no accounts, no tracking).

**Backup / restore**
- Automatic daily backup (on close, and before any migration or restore), last N kept.
- One-click restore, with a safety copy of current data first.
- Optional second location (USB or synced folder), prompted at onboarding.
- Exports: bills, stock, party ledgers to Excel/CSV; GSTR-1-style sales register for accountants.

## 8. Internationalisation

English (default), Hindi, Telugu. Language codes `en`, `hi`, `te`; each language shown in its own script. String catalogue mechanism modelled on Kuttu's `kuttu_i18n`, built in from day one. A test fails if Hindi or Telugu is missing any string, so English cannot leak into translated screens. Fonts with Devanagari and Telugu scripts must be bundled or selected per language.

## 9. Testing

- Service layer unit-tested without UI (GST splits, rounding in paise, stock ledger, tracking rules, returns, license verification, migrations).
- Migration tests: upgrade from every prior schema version with representative data.
- i18n completeness test (see section 8).
- UI smoke tests for the counter flow; manual test checklist per segment.

## 10. Open items and risks

- Pricing model and plan tiers beyond a single plan are undecided (payload field is reserved).
- Private signing key custody is a single point of failure for licensing.
- Grocery volumes (thousands of SKUs, hundreds of bills a day) need a performance check on the item search and table views early in the build.
- Regulatory details (e-invoicing thresholds, GSTR exports) should be verified against current GST rules before release.
- Exact thermal printer and barcode scanner models to test against are not yet chosen.
