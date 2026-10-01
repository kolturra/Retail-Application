import json
import urllib.parse

import pytest

import retail_ui
from retail_ui import fmt, paths, settings, states, validators, vendor


def test_app_identity():
    assert retail_ui.APP_NAME == "Retail App" and retail_ui.__version__


def test_default_paths_use_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    p = paths.AppPaths.default()
    assert p.root == tmp_path / "RetailApp"
    p.ensure()
    assert p.root.is_dir() and p.backup_dir.is_dir()
    assert p.db_path.name == "shop.db" and p.license_path.name == "license.key"
    assert p.settings_path.name == "settings.json"


def test_settings_round_trip_and_tolerance(tmp_path):
    path = tmp_path / "settings.json"
    assert settings.load(path) == settings.UiSettings()
    s = settings.UiSettings(backup_dir="D:/bk", extra_backup_dir="E:/usb", auto_print=True, print_layout="a4")
    settings.save(path, s)
    assert settings.load(path) == s
    path.write_text("{not json", encoding="utf-8")
    assert settings.load(path) == settings.UiSettings()
    path.write_text(json.dumps({"backup_dir": 5, "auto_print": "yes", "extra": 1}), encoding="utf-8")
    assert settings.load(path) == settings.UiSettings()          # wrong types fall back to defaults
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("paise,text", [
    (0, "₹0.00"), (5, "₹0.05"), (123456, "₹1,234.56"), (12345678, "₹1,23,456.78"),
    (123456789, "₹12,34,567.89"), (-250000, "-₹2,500.00"), (99999, "₹999.99"),
])
def test_rupees_uses_indian_grouping(paise, text):
    assert fmt.rupees(paise) == text


@pytest.mark.parametrize("text,paise", [("₹1,234.50", 123450), (" 12 ", 1200), ("0.5", 50), ("12.345", 1235)])
def test_parse_rupees(text, paise):
    assert fmt.parse_rupees(text) == paise


@pytest.mark.parametrize("text", ["", "abc", "1.2.3", "₹", "--5", "1e5", "1e400", "NaN", "Infinity", "-Infinity", "१२", "5.", ".5"])
def test_parse_rupees_rejects_garbage(text):
    with pytest.raises(ValueError):
        fmt.parse_rupees(text)


def test_qty_helpers():
    assert fmt.qty(750) == "0.75" and fmt.qty(2000) == "2"
    assert fmt.parse_qty("0.75") == 750 and fmt.parse_qty(" 3 ") == 3000
    for bad in ("", "0", "-1", "abc", "0.0001", "1e5", "1e400", "NaN", "Infinity", "-Infinity", "१२", "5.", ".5"):
        with pytest.raises(ValueError):
            fmt.parse_qty(bad)


def test_date_text():
    assert fmt.date_text("2026-09-30") == "30-09-2026"
    assert fmt.date_text("2026-09-30T10:05:09") == "30-09-2026 10:05"
    assert fmt.date_text("") == ""


def test_states_and_gstin_validation():
    assert states.STATES["36"] == "Telangana" and states.STATES["27"] == "Maharashtra" and "28" not in states.STATES
    assert validators.gstin_error("", "36") is None                    # optional
    assert validators.gstin_error("36ABCDE1234F1Z5", "36") is None
    assert validators.gstin_error("36abcde1234f1z5", "36") is None     # case-insensitive
    assert validators.gstin_error("36ABCDE1234F1Z5", "27") is not None  # state prefix mismatch
    assert validators.gstin_error("123", "36") is not None
    assert validators.phone_digits("+91 98765-43210") == "919876543210"
    assert validators.gstin_error("३६ABCDE१२३४F१Z५", "36") is not None   # Devanagari digits rejected
    assert validators.phone_digits("९८६६") == ""


def test_vendor_urls():
    url = vendor.whatsapp_request_url("RTL-AAAA-BBBB-CCCC-DDDD")
    assert url.startswith("https://wa.me/919866079246?text=")
    assert "RTL-AAAA-BBBB-CCCC-DDDD" in urllib.parse.unquote(url)


def test_email_request_url(monkeypatch):
    monkeypatch.setattr(vendor, "VENDOR_EMAIL", "a@b.co")
    url = vendor.email_request_url("RTL-X-1")
    assert url.startswith("mailto:a@b.co?") and "RTL-X-1" in urllib.parse.unquote(url)
    monkeypatch.setattr(vendor, "VENDOR_EMAIL", "")
    assert vendor.email_request_url("RTL-X-1") is None


def test_settings_save_creates_parent_and_cleans_tmp(tmp_path, monkeypatch):
    path = tmp_path / "new" / "dir" / "settings.json"
    settings.save(path, settings.UiSettings(auto_print=True))
    assert settings.load(path).auto_print is True

    def boom(*a, **k):
        raise OSError("nope")
    monkeypatch.setattr(settings.os, "replace", boom)
    with pytest.raises(OSError):
        settings.save(path, settings.UiSettings())
    assert not list(path.parent.glob("*.tmp"))
