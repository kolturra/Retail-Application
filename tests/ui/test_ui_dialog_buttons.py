"""I2: every button in confirmation / error / input boxes comes from the catalogue (never Qt's English)."""
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from retail import i18n
from retail_ui import errors
from retail_ui.widgets import helpers

ENGLISH = json.loads(Path(i18n.__file__).with_name("locales").joinpath("en.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def texts(box):
    return [b.text() for b in box.buttons()]


@pytest.mark.parametrize("code", ["hi", "te"])
def test_confirm_box_buttons_are_translated(qtbot, code):
    i18n.set_language(code)
    box, yes = helpers.build_confirm_box(None, "data.restore_confirm")
    qtbot.addWidget(box)
    assert texts(box) == [i18n.tr("common.yes"), i18n.tr("common.no")]
    assert yes.text() == i18n.tr("common.yes") != ENGLISH["common.yes"]
    assert i18n.tr("common.no") != ENGLISH["common.no"] and box.text() == i18n.tr("data.restore_confirm")
    assert box.defaultButton().text() == i18n.tr("common.no")      # a stray Enter never confirms
    assert box.standardButtons() == QMessageBox.StandardButton.NoButton


@pytest.mark.parametrize("code", ["hi", "te"])
@pytest.mark.parametrize("warning", [False, True])
def test_notice_box_has_a_translated_ok(qtbot, code, warning):
    i18n.set_language(code)
    box, ok = helpers.build_notice_box(None, "data.restart_notice", warning=warning)
    qtbot.addWidget(box)
    assert texts(box) == [i18n.tr("common.ok")] and ok.text() != ENGLISH["common.ok"]


@pytest.mark.parametrize("code", ["hi", "te"])
def test_error_box_has_translated_ok_and_details_and_no_stock_buttons(qtbot, code):
    i18n.set_language(code)
    box, details = errors.build_error_box(None, RuntimeError("boom"))
    qtbot.addWidget(box)
    assert texts(box) == [i18n.tr("common.ok"), i18n.tr("common.details")]
    assert details.text() == i18n.tr("common.details") != ENGLISH["common.details"]
    assert box.detailedText() == "" and box.windowTitle() == i18n.tr("err.title")


@pytest.mark.parametrize("code", ["hi", "te"])
def test_text_dialog_has_translated_ok_and_cancel(qtbot, code):
    i18n.set_language(code)
    dialog = helpers.build_text_dialog(None, "bills.whatsapp", "wa.phone_prompt")
    qtbot.addWidget(dialog)
    assert dialog.okButtonText() == i18n.tr("common.ok") != ENGLISH["common.ok"]
    assert dialog.cancelButtonText() == i18n.tr("common.cancel") != ENGLISH["common.cancel"]
    assert dialog.labelText() == i18n.tr("wa.phone_prompt")


def test_text_dialog_real_buttons_are_translated(qtbot):
    from PySide6.QtWidgets import QPushButton
    i18n.set_language("te")
    dialog = helpers.build_text_dialog(None, "bills.whatsapp", "wa.phone_prompt")
    qtbot.addWidget(dialog)
    assert sorted(b.text() for b in dialog.findChildren(QPushButton)) == sorted(
        [i18n.tr("common.ok"), i18n.tr("common.cancel")])


@pytest.mark.parametrize("module,cls", [("counter", "CounterScreen"), ("data", "DataScreen"),
                                        ("settings", "SettingsScreen"), ("staff", "StaffScreen")])
def test_screen_confirm_hooks_use_the_translated_helper(make_session, qtbot, monkeypatch, module, cls):
    import importlib
    screen_cls = getattr(importlib.import_module(f"retail_ui.screens.{module}"), cls)
    asked = []
    monkeypatch.setattr(helpers, "confirm", lambda parent, key: asked.append(key) or True)
    screen = screen_cls(make_session())
    qtbot.addWidget(screen)
    assert screen._confirm("common.confirm") is True and asked == ["common.confirm"]
