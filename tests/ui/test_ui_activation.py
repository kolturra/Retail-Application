import pytest
from PySide6.QtGui import QDesktopServices, QGuiApplication

from retail import i18n
from retail_ui import vendor
from retail_ui.dialogs.activation import ActivationDialog

MID = "RTL-AAAA-BBBB-CCCC-DDDD"


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def test_shows_machine_id_and_disables_activate_until_a_key_is_typed(qtbot):
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    assert d.machine_edit.text() == MID and d.machine_edit.isReadOnly()
    assert not d.activate_button.isEnabled()
    d.key_edit.setPlainText("   ")
    assert not d.activate_button.isEnabled()
    d.key_edit.setPlainText("  abc.def \n")
    assert d.activate_button.isEnabled() and d.key() == "abc.def"


def test_copy_button_copies_the_machine_id(qtbot):
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    d.copy_button.click()
    assert QGuiApplication.clipboard().text() == MID


def test_request_buttons_open_the_vendor_urls(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    d.whatsapp_button.click()
    assert opened and opened[0].startswith("https://wa.me/919866079246?text=")
    assert d.email_button.isHidden() == (vendor.VENDOR_EMAIL == "")


def test_invalid_notice_is_only_shown_after_a_bad_key(qtbot):
    ok = ActivationDialog(MID)
    bad = ActivationDialog(MID, invalid=True)
    qtbot.addWidget(ok)
    qtbot.addWidget(bad)
    assert ok.invalid_label.isHidden() and not bad.invalid_label.isHidden()
    assert bad.invalid_label.text() == i18n.tr("act.invalid")


@pytest.mark.parametrize("code", ["hi", "te"])
def test_dialog_is_translated(qtbot, code):
    i18n.set_language(code)
    d = ActivationDialog(MID)
    qtbot.addWidget(d)
    assert d.activate_button.text() == i18n.tr("act.activate") != "Activate"
