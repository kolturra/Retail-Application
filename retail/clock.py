"""Single home for time so tests can pass explicit dates."""
import calendar
from datetime import date, datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> date:
    return date.today()


def add_months(d: date, months: int) -> date:
    carry, month0 = divmod(d.month - 1 + months, 12)
    year, month = d.year + carry, month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))
