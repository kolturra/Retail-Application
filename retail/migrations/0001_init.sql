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

-- Immutability: stock ledger and audit log are append-only; finalized bills are frozen.
CREATE TRIGGER trg_stock_movement_no_update BEFORE UPDATE ON stock_movement
BEGIN SELECT RAISE(ABORT, 'stock_movement is append-only'); END;
CREATE TRIGGER trg_stock_movement_no_delete BEFORE DELETE ON stock_movement
BEGIN SELECT RAISE(ABORT, 'stock_movement is append-only'); END;

CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TRIGGER trg_bill_final_no_update BEFORE UPDATE ON bill WHEN OLD.status = 'final'
BEGIN SELECT RAISE(ABORT, 'finalized bill is immutable'); END;
CREATE TRIGGER trg_bill_final_no_delete BEFORE DELETE ON bill WHEN OLD.status = 'final'
BEGIN SELECT RAISE(ABORT, 'finalized bill is immutable'); END;

CREATE TRIGGER trg_bill_line_final_no_insert BEFORE INSERT ON bill_line
WHEN (SELECT status FROM bill WHERE id = NEW.bill_id) = 'final'
BEGIN SELECT RAISE(ABORT, 'finalized bill is immutable'); END;
CREATE TRIGGER trg_bill_line_final_no_update BEFORE UPDATE ON bill_line
WHEN (SELECT status FROM bill WHERE id = OLD.bill_id) = 'final'
BEGIN SELECT RAISE(ABORT, 'finalized bill is immutable'); END;
CREATE TRIGGER trg_bill_line_final_no_delete BEFORE DELETE ON bill_line
WHEN (SELECT status FROM bill WHERE id = OLD.bill_id) = 'final'
BEGIN SELECT RAISE(ABORT, 'finalized bill is immutable'); END;
