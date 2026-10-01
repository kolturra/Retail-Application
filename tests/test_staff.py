import pytest

from retail import guard
from retail.services import staff
from retail.services.staff import StaffError


def test_add_and_list_staff(shop_conn):
    a = staff.add_staff(shop_conn, name="Anil", role="Cashier", monthly_salary_paise=1200000)
    b = staff.add_staff(shop_conn, name="Bala")
    shop_conn.execute("UPDATE staff SET active = 0 WHERE id = ?", (b,))
    assert [r["name"] for r in staff.list_staff(shop_conn)] == ["Anil"]
    assert {r["id"] for r in staff.list_staff(shop_conn, active_only=False)} == {a, b}


@pytest.mark.parametrize("kwargs", [
    {"name": " "},
    {"name": "X", "monthly_salary_paise": -1},
    {"name": "X", "monthly_salary_paise": True},
    {"name": "X", "monthly_salary_paise": 10.5},
    {"name": "X", "monthly_salary_paise": "100"},
    {"name": "X", "monthly_salary_paise": None},
])
def test_staff_validation(shop_conn, kwargs):
    with pytest.raises(StaffError):
        staff.add_staff(shop_conn, **kwargs)


def test_expenses_and_totals(shop_conn):
    staff.add_expense(shop_conn, spent_on="2026-09-05", category="rent", amount_paise=1500000)
    staff.add_expense(shop_conn, spent_on="2026-09-10", category="electricity", amount_paise=250000, note="Aug bill")
    staff.add_expense(shop_conn, spent_on="2026-10-01", category="rent", amount_paise=1500000)
    assert staff.expense_total(shop_conn, "2026-09-01", "2026-09-30") == 1750000
    assert staff.expense_total(shop_conn, "2026-09-01", "2026-10-31", category="rent") == 3000000


@pytest.mark.parametrize("kwargs", [
    {"spent_on": "2026-09-05", "category": "party", "amount_paise": 100},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": 0},
    {"spent_on": "05/09/2026", "category": "rent", "amount_paise": 100},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": True},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": 100.5},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": "100"},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": None},
    {"spent_on": "2026-09-05", "category": "rent", "amount_paise": 100, "staff_id": 999},
])
def test_expense_validation(shop_conn, kwargs):
    with pytest.raises(StaffError):
        staff.add_expense(shop_conn, **kwargs)


@pytest.mark.parametrize("start,end", [
    ("2026-09-30", "2026-09-01"),
    ("garbage", "2026-09-30"),
    ("2026-09-01", "30/09/2026"),
    (None, "2026-09-30"),
])
def test_expense_total_validates_dates(shop_conn, start, end):
    with pytest.raises(StaffError):
        staff.expense_total(shop_conn, start, end)


def test_pay_salary_records_expense_once_per_month(shop_conn):
    a = staff.add_staff(shop_conn, name="Anil", monthly_salary_paise=1200000)
    staff.pay_salary(shop_conn, a, "2026-09-30")
    assert staff.expense_total(shop_conn, "2026-09-01", "2026-09-30", category="salary") == 1200000
    with pytest.raises(StaffError):
        staff.pay_salary(shop_conn, a, "2026-09-15")
    staff.pay_salary(shop_conn, a, "2026-10-31")
    assert staff.expense_total(shop_conn, "2026-01-01", "2026-12-31", category="salary") == 2400000


def test_pay_salary_needs_a_salary_and_a_real_person(shop_conn):
    unpaid = staff.add_staff(shop_conn, name="Intern")
    with pytest.raises(StaffError):
        staff.pay_salary(shop_conn, unpaid, "2026-09-30")
    with pytest.raises(StaffError):
        staff.pay_salary(shop_conn, 999, "2026-09-30")


def test_writes_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        staff.add_staff(shop_conn, name="X")
