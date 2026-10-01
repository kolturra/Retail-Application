"""User-facing error text. Services raise English messages; the UI never shows them. A translated
message is chosen by exception *type*, and the English detail goes to the log and a Details pane."""
import logging

from retail import guard, i18n
from retail.services import backup, billing, items, parties, purchases, shop, staff, stock

log = logging.getLogger("retail_ui")

# order matters: most specific first (SerialUnavailable and InsufficientStock are ValueErrors)
_MAP = (
    (guard.ReadOnlyError, "err.read_only"),
    (stock.InsufficientStock, "err.insufficient_stock"),
    (billing.SerialUnavailable, "err.serial_unavailable"),
    (stock.DuplicateSerial, "err.duplicate_serial"),
    (backup.BackupError, "err.backup"),
    (shop.ShopNotSetUp, "err.shop_not_set_up"),
    ((billing.BillingError, items.ItemError, parties.PartyError, purchases.PurchaseError,
      shop.ShopError, staff.StaffError, stock.StockError), "err.invalid_input"),
    (OSError, "err.file"),
)


def message_for(exc) -> str:
    for types, key in _MAP:
        if isinstance(exc, types):
            return i18n.tr(key)
    return i18n.tr("err.unexpected")


def detail_for(exc) -> str:
    return f"{type(exc).__name__}: {exc}"


def show_error(parent, exc) -> None:
    from PySide6.QtWidgets import QMessageBox  # imported lazily so message_for stays Qt-free

    log.error("handled error shown to user: %s", detail_for(exc), exc_info=exc)
    box = QMessageBox(QMessageBox.Icon.Warning, i18n.tr("err.title"), message_for(exc),
                      QMessageBox.StandardButton.Ok, parent)
    box.setDetailedText(detail_for(exc))
    box.exec()
