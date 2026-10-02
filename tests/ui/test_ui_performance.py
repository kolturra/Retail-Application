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
