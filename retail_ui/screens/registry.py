from retail_ui.screens.bills import BillsScreen
from retail_ui.screens.counter import CounterScreen
from retail_ui.screens.items import ItemsScreen
from retail_ui.screens.parties import PartiesScreen
from retail_ui.screens.reports import ReportsScreen
from retail_ui.screens.stock import StockScreen
from retail_ui.widgets.base import Screen


def all_screens() -> list[type[Screen]]:
    """Navigation order. Each screen task appends its class here."""
    return [CounterScreen, BillsScreen, ItemsScreen, StockScreen, PartiesScreen, ReportsScreen]
