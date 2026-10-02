"""Final fix wave: restore across languages, bill identity after a restore, status bar (I1, M1, M2)."""
import json
import logging
from pathlib import Path

import pytest

from retail import i18n
from retail.services import billing, items, shop, stock
from retail_ui.main_window import MainWindow
from retail_ui.screens import registry
from retail_ui.screens.counter import CounterScreen
from retail_ui.widgets.base import Screen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        app.setFont(QFont())


def make_window(make_session, qtbot):
    session = make_session()
    window = MainWindow(session, registry.all_screens())
    qtbot.addWidget(window)
    window.show()
    return session, window


def stocked(conn, **kw):
    kw.setdefault("sell_price_paise", 11800)
    item_id = items.create_item(conn, **kw)
    stock.record(conn, item_id, 50_000, "opening")
    return item_id


def test_restoring_a_backup_in_another_language_with_an_open_bill(make_session, qtbot):
    session, window = make_window(make_session, qtbot)
    session.set_language("hi")
    snapshot = session.backup_now().path            # a Hindi backup
    session.set_language("en")
    stocked(session.conn, name="Soap", barcodes=["8901"])
    counter = window.screens[0]
    counter.errors = []
    counter._show_error = lambda exc: counter.errors.append(exc)
    counter.submit_text("8901")                      # an open bill that only exists in the English data
    assert counter.controller.bill_id is not None
    session.restore_from(snapshot)                   # must not raise or leave screens half-translated
    assert counter.errors == [] and i18n.get_language() == "hi"
    english = json.loads(Path(i18n.__file__).with_name("locales").joinpath("en.json").read_text(encoding="utf-8"))
    for i, screen in enumerate(window.screens):
        assert window.nav.item(i).text() == i18n.tr(screen.nav_key) != english[screen.nav_key]
    assert window.nav.item(0).text() != "Counter"
    assert counter.total_label.text()                # rendered without error


def test_one_failing_screen_never_stops_the_rest_from_retranslating(make_session, qtbot, caplog):
    class Broken(Screen):
        nav_key = "nav.counter"

        def retranslate(self):
            raise RuntimeError("boom")

    class Fine(Screen):
        nav_key = "nav.items"
        calls = 0

        def retranslate(self):
            Fine.calls += 1

    session = make_session()
    window = MainWindow(session, [Broken, Fine])
    qtbot.addWidget(window)
    with caplog.at_level(logging.ERROR, logger="retail_ui"):
        session.set_language("hi")
    assert Fine.calls == 1 and window.nav.item(1).text() == i18n.tr("nav.items")
    assert any("boom" in (r.exc_text or "") or "retranslate" in r.getMessage() for r in caplog.records)


def test_a_restore_forgets_the_open_and_last_bill(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    snapshot = session.backup_now().path
    counter = CounterScreen(session)
    qtbot.addWidget(counter)
    counter.submit_text("8901")
    assert counter.controller.bill_id is not None
    counter.last_bill_id = 99
    session.restore_from(snapshot)                   # the snapshot has no bills at all
    assert counter.controller.bill_id is None and counter.last_bill_id is None


def test_a_restore_does_not_adopt_an_older_backups_held_bill_with_the_same_id(make_session, qtbot):
    session = make_session()
    stocked(session.conn, name="Soap", barcodes=["8901"])
    counter = CounterScreen(session)
    qtbot.addWidget(counter)
    counter.submit_text("8901")
    held_id = counter.controller.bill_id
    snapshot = session.backup_now().path             # the backup holds a held bill with this id
    counter.submit_text("8901")                      # the live bill (same id) moves on
    session.restore_from(snapshot)
    assert billing.get_bill_detail(session.conn, held_id)["bill"]["status"] == "held"   # it exists again...
    counter.refresh()
    assert counter.controller.bill_id is None                                            # ...but is not adopted


def test_status_bar_follows_shop_edits_and_restores(make_session, qtbot):
    session, window = make_window(make_session, qtbot)
    assert window.status_label.text().startswith("Test Shop")
    snapshot = session.backup_now().path
    shop.update_shop(session.conn, name="Renamed Store")
    session.notify_changed()
    assert window.status_label.text().startswith("Renamed Store")
    session.restore_from(snapshot)
    assert window.status_label.text().startswith("Test Shop")
