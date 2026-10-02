import pytest

from retail import money


def test_rupees_to_paise_is_exact_for_float_noise():
    assert money.rupees_to_paise(0.1 + 0.2) == 30
    assert money.rupees_to_paise("10.005") == 1001
    assert money.rupees_to_paise(59) == 5900


def test_paise_to_str():
    assert money.paise_to_str(5) == "0.05"
    assert money.paise_to_str(12345) == "123.45"
    assert money.paise_to_str(-12345) == "-123.45"
    assert money.paise_to_str(0) == "0.00"


def test_quantity_helpers():
    assert money.qty_to_milli("0.75") == 750
    assert money.qty_to_milli(3) == 3000
    assert money.milli_to_str(750) == "0.75"
    assert money.milli_to_str(2000) == "2"
    assert money.milli_to_str(1500) == "1.5"


@pytest.mark.parametrize(
    "rate,qty,expected",
    [(10000, 750, 7500), (3333, 500, 1667), (11800, 1000, 11800), (100, 3000, 300)],
)
def test_line_amount_rounds_half_up(rate, qty, expected):
    assert money.line_amount(rate, qty) == expected


@pytest.mark.parametrize(
    "total,expected",
    [(10049, (10000, -49)), (10050, (10100, 50)), (10000, (10000, 0)), (0, (0, 0))],
)
def test_round_to_rupee(total, expected):
    assert money.round_to_rupee(total) == expected
