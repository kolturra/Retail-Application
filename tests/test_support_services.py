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
