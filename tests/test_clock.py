from datetime import date

from retail import clock


def test_add_months_clamps_to_month_end():
    assert clock.add_months(date(2026, 1, 31), 12) == date(2027, 1, 31)
    assert clock.add_months(date(2028, 2, 29), 12) == date(2029, 2, 28)
    assert clock.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert clock.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_now_iso_shape():
    stamp = clock.now_iso()
    assert len(stamp) == 19 and stamp[10] == "T"
