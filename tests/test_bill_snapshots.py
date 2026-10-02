import shutil

import pytest

from retail import db
from retail.services import billing, items, parties, shop, stock


def _sale(conn, *, hsn="3401", party_id=None, qty=2000):
    item = items.create_item(conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800, hsn=hsn)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    line_id = billing.add_line(conn, bill_id, item, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, [("cash", total)])
    return item, bill_id, line_id


def test_line_hsn_is_frozen_at_sale_and_survives_an_item_edit(shop_conn):
    item, bill_id, _ = _sale(shop_conn, hsn="3401")
    items.update_item(shop_conn, item, hsn="9999")
    assert billing.get_bill_detail(shop_conn, bill_id)["lines"][0]["hsn"] == "3401"


def test_return_lines_copy_the_original_hsn(shop_conn):
    item, bill_id, line_id = _sale(shop_conn, hsn="3401")
    items.update_item(shop_conn, item, hsn="9999")
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert billing.get_bill_detail(shop_conn, ret)["lines"][0]["hsn"] == "3401"


def test_a_line_without_a_snapshot_falls_back_to_the_item_hsn(shop_conn):
    item, bill_id, _ = _sale(shop_conn, hsn=None)
    shop_conn.execute("UPDATE item SET hsn = '1234' WHERE id = ?", (item,))
    assert billing.get_bill_detail(shop_conn, bill_id)["lines"][0]["hsn"] == "1234"


def test_place_of_supply_is_frozen_on_the_bill_and_copied_to_returns(shop_conn):
    pune = parties.create_party(shop_conn, name="Pune", state_code="27")
    _, bill_id, line_id = _sale(shop_conn, party_id=pune)
    parties.update_party(shop_conn, pune, name="Pune", state_code="36")
    assert billing.get_bill_detail(shop_conn, bill_id)["bill"]["place_of_supply_state"] == "27"
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    assert billing.get_bill_detail(shop_conn, ret)["bill"]["place_of_supply_state"] == "27"


def test_walk_in_sale_and_estimate_snapshots(shop_conn):
    _, bill_id, _ = _sale(shop_conn)
    assert billing.get_bill_detail(shop_conn, bill_id)["bill"]["place_of_supply_state"] == "36"
    shop.update_shop(shop_conn, gst_enabled=False)
    _, est, _ = _sale(shop_conn)
    assert billing.get_bill_detail(shop_conn, est)["bill"]["place_of_supply_state"] is None


def test_migration_applies_to_an_existing_database_with_data(tmp_path):
    only_v1 = tmp_path / "v1"
    only_v1.mkdir()
    shutil.copy(db.MIGRATIONS_DIR / "0001_init.sql", only_v1)
    db_path, backups = tmp_path / "shop.db", tmp_path / "bk"
    conn = db.open_shop(db_path, backups, migrations_dir=only_v1)
    assert db.schema_version(conn) == 1
    shop.setup_shop(conn, name="Old Shop", state_code="36")
    conn.execute("INSERT INTO item(name, hsn, gst_rate_bp) VALUES ('Legacy', '1111', 500)")
    conn.execute("INSERT INTO bill(id, kind, status, gst_mode, created_at) VALUES (1,'sale','held','gst','t')")
    conn.execute("INSERT INTO bill_line(bill_id, item_id, qty_milli, rate_paise, amount_paise, gst_rate_bp)"
                 " VALUES (1, 1, 1000, 100, 100, 500)")
    conn.execute("UPDATE bill SET status='final', bill_no='S000001', finalized_at='t' WHERE id=1")
    conn.close()

    conn = db.open_shop(db_path, backups)            # real migrations
    try:
        assert db.schema_version(conn) == db.latest_version() == 2
        assert list(backups.glob("pre-migrate-*"))   # taken before the migration ran
        detail = billing.get_bill_detail(conn, 1)
        assert detail["lines"][0]["hsn"] == "1111"                      # legacy row: live fallback
        assert detail["bill"]["place_of_supply_state"] is None
        with pytest.raises(Exception, match="immutable"):                # triggers still guard the row
            conn.execute("UPDATE bill_line SET hsn = 'x' WHERE bill_id = 1")
        with pytest.raises(Exception, match="immutable"):
            conn.execute("UPDATE bill SET place_of_supply_state = '01' WHERE id = 1")
    finally:
        conn.close()
