import pytest

from retail.services import gst


def test_inclusive_intra_state_splits_evenly():
    t = gst.split_line(11800, 1800, inclusive=True, intra_state=True)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total) == (10000, 900, 900, 0, 11800)


def test_exclusive_inter_state_uses_igst():
    t = gst.split_line(10000, 1800, inclusive=False, intra_state=False)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total) == (10000, 0, 0, 1800, 11800)


def test_odd_paise_tax_gives_extra_paisa_to_sgst():
    t = gst.split_line(100, 500, inclusive=True, intra_state=True)
    assert (t.taxable, t.cgst, t.sgst, t.total) == (95, 2, 3, 100)


def test_zero_rate_has_no_tax():
    t = gst.split_line(5000, 0, inclusive=True, intra_state=True)
    assert (t.taxable, t.cgst, t.sgst, t.igst, t.total) == (5000, 0, 0, 0, 5000)


@pytest.mark.parametrize("amount", [1, 99, 1049, 11799, 123457])
@pytest.mark.parametrize("rate", [500, 1800, 4000])
def test_parts_always_sum_to_total(amount, rate):
    for inclusive in (True, False):
        for intra in (True, False):
            t = gst.split_line(amount, rate, inclusive=inclusive, intra_state=intra)
            assert t.taxable + t.cgst + t.sgst + t.igst == t.total


def test_is_intra_state():
    assert gst.is_intra_state("36", "36") is True
    assert gst.is_intra_state("36", "27") is False
    assert gst.is_intra_state("36", None) is True
    assert gst.is_intra_state("36", "") is True
