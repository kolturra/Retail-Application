import sqlite3

import pytest

from retail import guard, i18n
from retail.services import backup, billing, items, parties, purchases, shop, staff, stock
from retail_ui import errors


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.mark.parametrize("exc,key", [
    (guard.ReadOnlyError("License expired"), "err.read_only"),
    (stock.InsufficientStock("Only 1 in stock"), "err.insufficient_stock"),
    (billing.SerialUnavailable("Serial 'X' is not in stock"), "err.serial_unavailable"),
    (stock.DuplicateSerial("Serial already exists"), "err.duplicate_serial"),
    (backup.BackupError("bad"), "err.backup"),
    (shop.ShopNotSetUp("x"), "err.shop_not_set_up"),
    (billing.BillingError("x"), "err.invalid_input"),
    (items.ItemError("x"), "err.invalid_input"),
    (parties.PartyError("x"), "err.invalid_input"),
    (purchases.PurchaseError("x"), "err.invalid_input"),
    (shop.ShopError("x"), "err.invalid_input"),
    (staff.StaffError("x"), "err.invalid_input"),
    (stock.StockError("x"), "err.invalid_input"),
    (PermissionError("x"), "err.file"),
    (sqlite3.OperationalError("locked"), "err.unexpected"),
    (RuntimeError("boom"), "err.unexpected"),
])
def test_message_for_maps_exception_types_to_translated_text(exc, key):
    assert errors.message_for(exc) == i18n.tr(key)


def test_serial_unavailable_wins_over_its_parent_class():
    assert errors.message_for(billing.SerialUnavailable("x")) != errors.message_for(billing.BillingError("x"))


@pytest.mark.parametrize("code", ["hi", "te"])
def test_messages_are_translated_and_never_contain_the_english_detail(code):
    i18n.set_language(code)
    exc = stock.InsufficientStock("Only 3 in stock")
    text = errors.message_for(exc)
    assert text != i18n.tr("err.unexpected") and "Only 3" not in text
    i18n.set_language("en")
    assert text != errors.message_for(exc)


def test_detail_is_english_and_names_the_type():
    assert errors.detail_for(items.ItemError("Barcode '1' is already used")) == "ItemError: Barcode '1' is already used"


def test_show_error_builds_a_box_with_translated_text(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    captured = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.append(
        (self.text(), self.informativeText(), [b.text() for b in self.buttons()])) or 0)
    errors.show_error(None, items.ItemError("dup"))
    assert captured == [(i18n.tr("err.invalid_input"), "", [i18n.tr("common.ok"), i18n.tr("common.details")])]


def test_details_button_reveals_the_english_detail_once(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []

    def fake_exec(self):
        shown.append((self.informativeText(), [b.text() for b in self.buttons()]))
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: next((b for b in self.buttons() if b.text() == i18n.tr("common.details")), None))
    errors.show_error(None, items.ItemError("dup"))
    assert len(shown) == 2 and shown[1] == ("ItemError: dup", [i18n.tr("common.ok")])
