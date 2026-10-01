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


@pytest.mark.parametrize("qty,cost", [(True, 100), (1000.0, 100), ("1000", 100), (1000, True), (1000, 1.5), (1000, None)])
def test_purchase_line_numbers_must_be_plain_ints(shop_conn, qty, cost):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(tea, qty, cost)])
    assert shop_conn.execute("SELECT COUNT(*) FROM purchase").fetchone()[0] == 0


def test_malformed_later_line_writes_nothing(shop_conn):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    with pytest.raises(PurchaseError):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(tea, 1000, 100), PurchaseLine(tea, 1000.0, 100)])
    assert stock.on_hand(shop_conn, tea) == 0
    assert shop_conn.execute("SELECT COUNT(*) FROM purchase").fetchone()[0] == 0


def test_unknown_party_rejected(shop_conn):
    tea = items.create_item(shop_conn, name="Tea", sell_price_paise=500)
    with pytest.raises(PurchaseError, match="No such party"):
        purchases.create_purchase(shop_conn, party_id=999, invoice_no=None,
                                  lines=[PurchaseLine(tea, 1000, 100)])
    assert shop_conn.execute("SELECT COUNT(*) FROM purchase").fetchone()[0] == 0


def test_serials_duplicating_after_normalisation_fail_atomically(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=1000000, tracking="serial")
    with pytest.raises(stock.DuplicateSerial):
        purchases.create_purchase(shop_conn, party_id=None, invoice_no=None,
                                  lines=[PurchaseLine(phone, 2000, 1, serials=("a1", " A1 "))])
    assert stock.on_hand(shop_conn, phone) == 0
    assert shop_conn.execute("SELECT COUNT(*) FROM stock_unit").fetchone()[0] == 0
    assert shop_conn.execute("SELECT COUNT(*) FROM purchase").fetchone()[0] == 0
