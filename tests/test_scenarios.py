"""Cross-module scenarios that mirror the spec's success criteria."""
import csv
from datetime import date

import pytest

from retail import clock, db, guard, license as lic, segments
from retail.services import backup, billing, items, parties, purchases, reports, shop, stock
from retail.services.purchases import PurchaseLine
from tools import license_issuer as issuer

def today():
    return clock.today().isoformat()


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

    summary = {r["gst_rate_bp"]: r for r in reports.gst_summary(conn, today(), today())}
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
    register = reports.sales_register(conn, today(), today())
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
    rows = reports.sales_register(conn, today(), today())
    reports.write_csv(rows, tmp_path / "export.csv", reports.SALES_COLUMNS)   # exports work
    with open(tmp_path / "export.csv", newline="", encoding="utf-8-sig") as handle:
        exported = list(csv.reader(handle))
    assert exported[0] == [c[:-6] if c.endswith("_paise") else c for c in reports.SALES_COLUMNS]
    assert len(exported) >= 2 and exported[1][0].startswith("S")
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
    assert reports.sales_register(conn, today(), today()) == []
    assert billing.finalize(conn, _held_tea_bill(conn, it), [("cash", 500)]) == "S000001"  # numbering restored too
    conn.close()


def _held_tea_bill(conn, item_id):
    bill = billing.start_bill(conn)
    billing.add_line(conn, bill, item_id, 1000)
    return bill


def test_grocery_batch_item_sold_across_two_batches_with_block_policy(db_path, tmp_path):
    conn = db.open_shop(db_path, tmp_path / "bk")
    shop.setup_shop(conn, name="Sri Kirana", state_code="36", oversell_policy="block")
    segments.apply_template(conn, "grocery")
    curd = items.create_item(conn, name="Curd", sell_price_paise=3000, gst_rate_bp=0, tracking="batch")
    purchases.create_purchase(conn, party_id=None, invoice_no="M-1", lines=[
        PurchaseLine(curd, 3_000, 2500, batch_no="B1", expiry="2026-11-01"),
        PurchaseLine(curd, 5_000, 2500, batch_no="B2", expiry="2027-01-01")])
    b1 = stock.find_batch(conn, curd, "B1")
    b2 = stock.find_batch(conn, curd, "B2")

    bill = billing.start_bill(conn)
    billing.add_line(conn, bill, curd, 3_000)                       # earliest expiry first: uses up B1
    billing.add_line(conn, bill, curd, 2_000)                       # B1 exhausted on this bill: B2 auto-picked
    with pytest.raises(stock.InsufficientStock):
        billing.add_line(conn, bill, curd, 4_000)                   # B2 has only 3 left; lines never split
    lines = billing.get_bill(conn, bill)["lines"]
    assert [row["unit_id"] for row in lines] == [b1, b2]
    billing.finalize(conn, bill, [("cash", 15000)])
    assert stock.unit_on_hand(conn, b1) == 0 and stock.unit_on_hand(conn, b2) == 3_000
    conn.close()
