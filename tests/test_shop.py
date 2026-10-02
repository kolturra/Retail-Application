import pytest

from retail import guard
from retail.services import shop


def test_setup_and_get_shop(conn):
    shop.setup_shop(conn, name="Sri Kirana", state_code="36", gstin="36ABCDE1234F1Z5")
    s = shop.get_shop(conn)
    assert s["name"] == "Sri Kirana"
    assert s["template"] == "grocery"
    assert s["price_includes_gst"] == 1 and s["gst_enabled"] == 1
    assert s["oversell_policy"] == "warn"


def test_get_shop_before_setup_raises(conn):
    with pytest.raises(shop.ShopNotSetUp):
        shop.get_shop(conn)


@pytest.mark.parametrize("kwargs", [
    {"name": "", "state_code": "36"},
    {"name": "X", "state_code": "ABC"},
    {"name": "X", "state_code": "3"},
    {"name": "X", "state_code": "36", "oversell_policy": "maybe"},
    {"name": "X", "state_code": "36", "language": "fr"},
])
def test_setup_rejects_bad_input(conn, kwargs):
    with pytest.raises(shop.ShopError):
        shop.setup_shop(conn, **kwargs)


def test_setup_blocked_when_read_only(conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        shop.setup_shop(conn, name="X", state_code="36")
