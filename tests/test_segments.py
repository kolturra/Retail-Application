import pytest

from retail import guard, segments
from retail.services import items, shop

REQUIRED = {"name", "label", "default_tracking", "units", "bill_layout", "gst_slabs_bp", "features"}
FEATURES = {"weighed", "batch", "serial", "warranty", "emi", "udhaar", "low_stock_alerts"}


def test_shipped_templates():
    assert segments.list_templates() == ["electronics", "grocery"]


@pytest.mark.parametrize("name", ["grocery", "electronics"])
def test_template_files_are_well_formed(name):
    t = segments.load(name)
    assert REQUIRED <= set(t) and t["name"] == name
    assert t["default_tracking"] in items.TRACKING
    assert set(t["features"]) == FEATURES and all(isinstance(v, bool) for v in t["features"].values())
    assert t["gst_slabs_bp"] == sorted(t["gst_slabs_bp"]) and 0 in t["gst_slabs_bp"]
    assert t["bill_layout"] in {"thermal_58", "thermal_80", "a4"}


def test_template_intent():
    g, e = segments.load("grocery"), segments.load("electronics")
    assert g["features"]["weighed"] and g["features"]["udhaar"] and not g["features"]["serial"]
    assert e["features"]["serial"] and e["features"]["warranty"] and e["features"]["emi"]
    assert e["default_tracking"] == "serial" and e["bill_layout"] == "a4"


def test_unknown_template_raises():
    with pytest.raises(segments.UnknownTemplate):
        segments.load("pharmacy")
    with pytest.raises(segments.UnknownTemplate):
        segments.load("../secret")


def test_apply_template_and_read_back(shop_conn):
    segments.apply_template(shop_conn, "electronics")
    assert shop.get_shop(shop_conn)["template"] == "electronics"
    assert segments.template_settings(shop_conn)["default_tracking"] == "serial"
    assert segments.feature_enabled(shop_conn, "warranty") is True
    assert segments.feature_enabled(shop_conn, "weighed") is False


def test_shop_can_mix_features_from_both_segments(shop_conn):
    segments.apply_template(shop_conn, "grocery")
    assert segments.feature_enabled(shop_conn, "serial") is False
    segments.set_feature(shop_conn, "serial", True)
    segments.set_feature(shop_conn, "warranty", True)
    assert segments.feature_enabled(shop_conn, "serial") and segments.feature_enabled(shop_conn, "weighed")
    with pytest.raises(segments.UnknownTemplate):
        segments.set_feature(shop_conn, "teleport", True)


def test_feature_enabled_is_false_before_any_template_applied(shop_conn):
    assert segments.feature_enabled(shop_conn, "serial") is False
    assert segments.template_settings(shop_conn) == {}


def test_apply_template_blocked_when_read_only(shop_conn):
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        segments.apply_template(shop_conn, "grocery")


@pytest.mark.parametrize("bad", [0, 1, "yes", None])
def test_set_feature_requires_real_bool(shop_conn, bad):
    segments.apply_template(shop_conn, "grocery")
    with pytest.raises(ValueError):
        segments.set_feature(shop_conn, "serial", bad)
    assert segments.feature_enabled(shop_conn, "serial") is False
