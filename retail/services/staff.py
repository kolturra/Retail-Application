from datetime import date

from retail import clock
from retail.db import transaction
from retail.guard import writes
from retail.services import audit

CATEGORIES = ("salary", "rent", "electricity", "transport", "other")


class StaffError(ValueError):
    pass


def _check_date(text):
    try:
        canonical = date.fromisoformat(text).isoformat() == text
    except (TypeError, ValueError) as exc:
        raise StaffError("Dates must look like 2026-09-30") from exc
    if not canonical:
        raise StaffError("Dates must look like 2026-09-30")


def _check_int(value, label):
    if type(value) is not int:
        raise StaffError(f"{label} must be a whole number of paise")


@writes
def add_staff(conn, *, name, role="", monthly_salary_paise=0):
    name = (name or "").strip()
    if not name:
        raise StaffError("Staff name is required")
    _check_int(monthly_salary_paise, "Salary")
    if monthly_salary_paise < 0:
        raise StaffError("Salary cannot be negative")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO staff(name, role, monthly_salary_paise) VALUES (?,?,?)",
            (name, role, monthly_salary_paise),
        )
        audit.log(conn, "create", "staff", cur.lastrowid, name)
    return cur.lastrowid


def list_staff(conn, active_only=True):
    sql = "SELECT * FROM staff" + (" WHERE active = 1" if active_only else "") + " ORDER BY name"
    return conn.execute(sql).fetchall()


@writes
def add_expense(conn, *, spent_on, category, amount_paise, note="", staff_id=None):
    _check_date(spent_on)
    if category not in CATEGORIES:
        raise StaffError(f"category must be one of {CATEGORIES}")
    _check_int(amount_paise, "Amount")
    if amount_paise <= 0:
        raise StaffError("Amount must be greater than zero")
    with transaction(conn):
        if staff_id is not None and conn.execute(
            "SELECT 1 FROM staff WHERE id = ?", (staff_id,)
        ).fetchone() is None:
            raise StaffError("No such staff member")
        if category == "salary" and staff_id is not None:
            month = spent_on[:7]
            if conn.execute(
                "SELECT 1 FROM expense WHERE staff_id = ? AND category = 'salary' AND substr(spent_on, 1, 7) = ?",
                (staff_id, month),
            ).fetchone():
                raise StaffError(f"Salary for {month} was already recorded")
        cur = conn.execute(
            "INSERT INTO expense(spent_on, category, amount_paise, note, staff_id) VALUES (?,?,?,?,?)",
            (spent_on, category, amount_paise, note, staff_id),
        )
        audit.log(conn, "create", "expense", cur.lastrowid, f"{category} {amount_paise}")
    return cur.lastrowid


@writes
def pay_salary(conn, staff_id, spent_on=None):
    spent_on = spent_on or clock.today().isoformat()
    _check_date(spent_on)
    with transaction(conn):
        person = conn.execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
        if person is None:
            raise StaffError("No such staff member")
        if person["monthly_salary_paise"] <= 0:
            raise StaffError("This staff member has no monthly salary set")
        if not person["active"]:
            raise StaffError("Staff member is inactive")
        return add_expense(conn, spent_on=spent_on, category="salary",
                           amount_paise=person["monthly_salary_paise"], note=f"Salary {spent_on[:7]}",
                           staff_id=staff_id)


def expense_total(conn, start, end, category=None):
    _check_date(start)
    _check_date(end)
    if start > end:
        raise StaffError("Start date must not be after end date")
    if category is not None and category not in CATEGORIES:
        raise StaffError(f"category must be one of {CATEGORIES}")
    sql = "SELECT COALESCE(SUM(amount_paise), 0) FROM expense WHERE spent_on BETWEEN ? AND ?"
    params = [start, end]
    if category:
        sql += " AND category = ?"
        params.append(category)
    return conn.execute(sql, params).fetchone()[0]
