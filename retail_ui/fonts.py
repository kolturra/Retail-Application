import logging

from PySide6.QtGui import QFontDatabase

log = logging.getLogger("retail_ui")

_INDIC = {
    "hi": ("Nirmala UI", "Noto Sans Devanagari", "Mangal"),
    "te": ("Nirmala UI", "Noto Sans Telugu", "Gautami"),
}
_LATIN = ("Segoe UI",)


def choose_family(code, available):
    """First installed family that can draw the language; '' keeps Qt's default."""
    for family in _INDIC.get(code, _LATIN):
        if family in available:
            return family
    return ""


def apply_language_font(app, code):
    family = choose_family(code, set(QFontDatabase.families()))
    if not family and code in _INDIC:
        log.warning("no Devanagari/Telugu-capable font found for %s; text may not render", code)
    font = app.font()
    if family:
        font.setFamily(family)
    font.setPointSize(10)
    app.setFont(font)
    return family
