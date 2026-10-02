import csv

import pytest

from retail import clock, guard
from retail.services import billing, items, parties, reports, shop, stock

def _read_dicts(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def today():
    return clock.today().isoformat()


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
    rows = reports.sales_register(shop_conn, today(), today())
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
    assert len(reports.sales_register(shop_conn, today(), today())) == 3
    assert reports.sales_register(shop_conn, "2001-01-01", "2001-12-31") == []
    assert held


def test_gst_summary_groups_by_rate_and_nets_returns(shop_conn):
    seed(shop_conn)
    summary = {r["gst_rate_bp"]: r for r in reports.gst_summary(shop_conn, today(), today())}
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
    assert reports.gst_summary(shop_conn, today(), today()) == []
    assert len(reports.sales_register(shop_conn, today(), today())) == 1


def test_daily_summary(shop_conn):
    seed(shop_conn)
    s = reports.daily_summary(shop_conn, today())
    assert (s["sales_paise"], s["returns_paise"], s["net_paise"]) == (45900, 11800, 34100)
    assert s["by_mode"] == {"cash": 34100 - 11800, "credit": 11800}


def test_write_csv_converts_paise_and_opens_in_excel(shop_conn, tmp_path):
    seed(shop_conn)
    path = tmp_path / "register.csv"
    reports.write_csv(reports.sales_register(shop_conn, today(), today()), path, reports.SALES_COLUMNS)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = _read_dicts(path)
    assert rows[0]["bill_no"] == "S000001" and rows[0]["total"] == "341.00"
    assert rows[2]["total"] == "-118.00" and "total_paise" not in rows[0]


def test_reports_still_work_when_license_is_expired(shop_conn, tmp_path):
    seed(shop_conn)
    guard.set_read_only(True)
    assert len(reports.sales_register(shop_conn, today(), today())) == 3
    reports.write_csv(reports.sales_register(shop_conn, today(), today()), tmp_path / "x.csv", reports.SALES_COLUMNS)
    assert (tmp_path / "x.csv").exists()


def test_write_csv_neutralises_formula_injection_in_text_cells(tmp_path):
    rows = [{"bill_no": "=1+1", "party": "=cmd|' /C calc'!A0", "gstin": "@x", "note": "+5",
             "other": "-3", "total_paise": -11800, "n": 7}]
    path = tmp_path / "inj.csv"
    reports.write_csv(rows, path, ["bill_no", "party", "gstin", "note", "other", "total_paise", "n"])
    out = _read_dicts(path)[0]
    assert out["party"] == "'=cmd|' /C calc'!A0"
    assert (out["bill_no"], out["gstin"], out["note"], out["other"]) == ("'=1+1", "'@x", "'+5", "'-3")
    assert out["total"] == "-118.00"  # numeric paise columns are never prefixed
    assert out["n"] == "7"


def test_ranges_are_validated(shop_conn):
    for fn in (reports.sales_register, reports.gst_summary):
        with pytest.raises(ValueError):
            fn(shop_conn, "2026-02-01", "2026-01-01")
        with pytest.raises(ValueError):
            fn(shop_conn, "2026-13-01", "2026-14-01")
        with pytest.raises(ValueError):
            fn(shop_conn, "yesterday", today())
        with pytest.raises(ValueError):
            fn(shop_conn, None, today())
    with pytest.raises(ValueError):
        reports.daily_summary(shop_conn, "2026-02-30")
    with pytest.raises(ValueError):
        reports.daily_summary(shop_conn, 20260201)


@pytest.mark.parametrize("cell", ["\tcmd", "\rcmd"])
def test_write_csv_neutralises_tab_and_cr_prefixed_cells(tmp_path, cell):
    path = tmp_path / "tabcr.csv"
    reports.write_csv([{"party": cell}], path, ["party"])
    with open(path, newline="", encoding="utf-8-sig") as handle:
        out = list(csv.reader(handle))
    assert out[1][0] == "'" + cell


def test_write_csv_quoting_round_trip(tmp_path):
    text = 'A, "B"\nC'
    path = tmp_path / "rt.csv"
    reports.write_csv([{"party": text, "total_paise": 150}], path, ["party", "total_paise"])
    with open(path, newline="", encoding="utf-8-sig") as handle:
        out = list(csv.reader(handle))
    assert out[0] == ["party", "total"]
    assert out[1] == [text, "1.50"]


def test_stock_register_lists_items_with_derived_on_hand(shop_conn, tmp_path):
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, buy_price_paise=9000,
                             sku="SO-1", reorder_milli=5000)
    items.create_item(shop_conn, name="=evil", sell_price_paise=100)
    stock.record(shop_conn, soap, 12_500, "opening")
    rows = reports.stock_register(shop_conn)
    assert [r["item"] for r in rows] == ["=evil", "Soap"]
    assert rows[1]["on_hand_milli"] == 12_500 and rows[0]["on_hand_milli"] == 0 and rows[0]["sku"] == ""
    path = tmp_path / "stock.csv"
    reports.write_csv(rows, path, reports.STOCK_COLUMNS)
    out = _read_dicts(path)
    assert out[0]["item"] == "'=evil"
    assert out[1] == {"item": "Soap", "sku": "SO-1", "unit": "pcs", "active": "yes", "on_hand": "12.5",
                      "reorder": "5", "buy_price": "90.00", "sell_price": "118.00"}


def test_party_ledger_running_balance_matches_balance(shop_conn, tmp_path):
    a, b = seed(shop_conn)
    pune = shop_conn.execute("SELECT id FROM party").fetchone()["id"]
    parties.receive_payment(shop_conn, pune, 3000, mode="upi")
    rows = reports.party_ledger(shop_conn)
    assert [(r["entry"], r["debit_paise"], r["credit_paise"], r["balance_paise"]) for r in rows] == [
        ("opening", 0, 0, 0), ("credit_sale", 11800, 0, 11800), ("payment", 0, 3000, 8800)]
    assert rows[1]["ref"] == "S000002" and rows[2]["ref"] == "upi"
    assert rows[-1]["balance_paise"] == parties.balance(shop_conn, pune)
    path = tmp_path / "ledger.csv"
    reports.write_csv(rows, path, reports.LEDGER_COLUMNS)
    out = _read_dicts(path)
    assert out[1]["debit"] == "118.00" and out[2]["balance"] == "88.00" and out[0]["party"] == "Pune Traders"


def test_party_ledger_opening_balance_and_credit_return(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", opening_balance_paise=5000)
    parties.create_party(shop_conn, name="Zed")
    soap = items.create_item(shop_conn, name="Soap", sell_price_paise=10000)
    stock.record(shop_conn, soap, 10_000, "opening")
    bill = billing.start_bill(shop_conn, party_id=pid)
    line = billing.add_line(shop_conn, bill, soap, 2000)
    billing.finalize(shop_conn, bill, [("credit", 20000)])
    billing.create_return(shop_conn, bill, [(line, 1000)], refund_mode="credit")
    rows = [r for r in reports.party_ledger(shop_conn) if r["party"] == "Ravi"]
    assert [r["entry"] for r in rows] == ["opening", "credit_sale", "credit_return"]
    assert rows[0]["balance_paise"] == 5000 and rows[-1]["balance_paise"] == parties.balance(shop_conn, pid) == 15000
    assert [r["party"] for r in reports.party_ledger(shop_conn)][-1] == "Zed"


def test_stock_and_ledger_reports_work_when_expired(shop_conn):
    seed(shop_conn)
    guard.set_read_only(True)
    assert reports.stock_register(shop_conn) and reports.party_ledger(shop_conn)


def test_party_ledger_lists_customers_and_both_but_not_suppliers(shop_conn):
    from retail.services import purchases
    supplier = parties.create_party(shop_conn, name="Mill Co", type="supplier")
    both = parties.create_party(shop_conn, name="Both Co", type="both", opening_balance_paise=100)
    parties.create_party(shop_conn, name="Cust", type="customer")
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    purchases.create_purchase(shop_conn, party_id=supplier, invoice_no="P1",
                              lines=[purchases.PurchaseLine(tea, 10_000, 350)])
    names = [r["party"] for r in reports.party_ledger(shop_conn)]
    assert names == ["Both Co", "Cust"]
