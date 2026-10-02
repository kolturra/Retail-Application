import shutil

import pytest

from retail import db
from retail.services import billing, gst, items, parties, shop, stock


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


def test_no_hsn_at_sale_is_stored_as_blank_and_stays_blank(shop_conn):
    item, bill_id, _ = _sale(shop_conn, hsn=None)
    shop_conn.execute("UPDATE item SET hsn = '1234' WHERE id = ?", (item,))
    assert billing.get_bill_detail(shop_conn, bill_id)["lines"][0]["hsn"] == ""


def test_a_legacy_null_line_hsn_falls_back_to_the_item_hsn(shop_conn):
    item = items.create_item(shop_conn, name="Old", sell_price_paise=100, hsn="1234")
    stock.record(shop_conn, item, 5000, "opening")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, item, 1000)
    shop_conn.execute("UPDATE bill_line SET hsn = NULL WHERE bill_id = ?", (bill_id,))   # as before 0002
    billing.finalize(shop_conn, bill_id, [("cash", billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"])])
    assert billing.get_bill_detail(shop_conn, bill_id)["lines"][0]["hsn"] == "1234"


def _split_agrees_with_place(conn, bill_id):
    bill = billing.get_bill_detail(conn, bill_id)["bill"]
    intra = gst.is_intra_state(shop.get_shop(conn)["state_code"], bill["place_of_supply_state"])
    assert intra == (bill["igst_paise"] == 0 and bill["cgst_paise"] > 0), dict(bill)
    return bill


def test_party_state_edited_while_held_keeps_place_and_split_consistent(shop_conn):
    ravi = parties.create_party(shop_conn, name="Ravi", state_code="36")
    item = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(shop_conn, item, 50_000, "opening")
    bill_id = billing.start_bill(shop_conn, party_id=ravi)
    billing.add_line(shop_conn, bill_id, item, 2000)
    parties.update_party(shop_conn, ravi, name="Ravi", state_code="27")      # edited while the bill is held
    billing.add_line(shop_conn, bill_id, item, 1000)                          # any retax picks it up
    billing.finalize(shop_conn, bill_id, [("cash", billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"])])
    bill = _split_agrees_with_place(shop_conn, bill_id)
    assert bill["place_of_supply_state"] == "27" and bill["igst_paise"] > 0
    parties.update_party(shop_conn, ravi, name="Ravi", state_code="36")      # later edits change nothing
    assert billing.get_bill_detail(shop_conn, bill_id)["bill"]["place_of_supply_state"] == "27"


def test_set_party_and_back_to_walk_in_stays_consistent(shop_conn):
    pune = parties.create_party(shop_conn, name="Pune", state_code="27")
    item = items.create_item(shop_conn, name="Soap", sell_price_paise=11800, gst_rate_bp=1800)
    stock.record(shop_conn, item, 50_000, "opening")
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, item, 1000)
    billing.set_party(shop_conn, bill_id, pune)
    assert _split_agrees_with_place(shop_conn, bill_id)["place_of_supply_state"] == "27"
    billing.set_party(shop_conn, bill_id, None)
    billing.finalize(shop_conn, bill_id, [("cash", billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"])])
    assert _split_agrees_with_place(shop_conn, bill_id)["place_of_supply_state"] == "36"


def test_party_without_a_state_is_intra_state_at_the_shop_state(shop_conn):
    nostate = parties.create_party(shop_conn, name="NoState")
    _, bill_id, _ = _sale(shop_conn, party_id=nostate)
    assert _split_agrees_with_place(shop_conn, bill_id)["place_of_supply_state"] == "36"


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
