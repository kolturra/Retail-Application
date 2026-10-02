import pytest

from retail_ui import fonts


@pytest.mark.parametrize("code,available,expected", [
    ("hi", {"Nirmala UI", "Segoe UI"}, "Nirmala UI"),
    ("te", {"Nirmala UI", "Segoe UI"}, "Nirmala UI"),
    ("hi", {"Noto Sans Devanagari"}, "Noto Sans Devanagari"),
    ("te", {"Gautami"}, "Gautami"),
    ("hi", {"Arial"}, ""),
    ("en", {"Segoe UI", "Nirmala UI"}, "Segoe UI"),
    ("en", {"Arial"}, ""),
])
def test_choose_family(code, available, expected):
    assert fonts.choose_family(code, available) == expected


def test_apply_language_font_sets_the_application_font(qtbot, monkeypatch):
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(QFontDatabase, "families", staticmethod(lambda *a: ["Nirmala UI", "Segoe UI"]))
    app = QApplication.instance()
    original = app.font()
    try:
        assert fonts.apply_language_font(app, "te") == "Nirmala UI" and app.font().family() == "Nirmala UI"
        assert fonts.apply_language_font(app, "en") == "Segoe UI"
    finally:
        app.setFont(original)
