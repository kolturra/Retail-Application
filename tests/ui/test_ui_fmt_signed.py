import pytest

from retail_ui import fmt


@pytest.mark.parametrize("text", ["1e3", "1_0", "1.0004", "", "abc", "0", "-0", "١"])
def test_parse_signed_qty_rejects(text):
    with pytest.raises(ValueError):
        fmt.parse_signed_qty(text)


@pytest.mark.parametrize("text,milli", [("-2.5", -2500), ("3", 3000), ("+3", 3000), ("0.001", 1)])
def test_parse_signed_qty_accepts(text, milli):
    assert fmt.parse_signed_qty(text) == milli
