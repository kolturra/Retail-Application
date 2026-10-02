import pytest

from retail import i18n, segments
from retail.services import billing, shop
from retail_ui import settings as ui_settings
from retail_ui.screens.settings import SettingsScreen


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


@pytest.fixture
def screen(make_session, qtbot):
    session = make_session()
    sc = SettingsScreen(session)
    qtbot.addWidget(sc)
    sc.errors, sc.warnings = [], []
    sc._show_error = lambda exc: sc.errors.append(exc)
    sc._warn = lambda key: sc.warnings.append(key)
    sc._confirm = lambda key: True
    sc.refresh()
    return sc


def audit_count(conn):
    return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def test_refresh_loads_the_current_values_without_writing(screen):
    conn = screen.session.conn
    before = audit_count(conn)
    screen.refresh()
    assert audit_count(conn) == before
    assert screen.name_edit.text() == "Test Shop" and screen.state_box.currentData() == "36"
    assert screen.gst_box.isChecked() and screen.incl_box.isChecked()
    assert screen.oversell_box.currentData() == "warn" and screen.template_box.currentData() == "grocery"
    assert screen.feature_boxes["weighed"].isChecked() and not screen.feature_boxes["serial"].isChecked()
    assert screen.language_box.currentData() == "en"


def test_save_shop_updates_the_details(screen):
    screen.name_edit.setText("  New Name ")
    screen.state_box.setCurrentIndex(screen.state_box.findData("27"))
    screen.gstin_edit.setText("27abcde1234f1z5")
    screen.address_edit.setText("Pune")
    screen.footer_edit.setText("No returns after 7 days")
    screen.save_shop()
    row = shop.get_shop(screen.session.conn)
    assert (row["name"], row["state_code"], row["gstin"], row["address"], row["bill_footer"]) == (
        "New Name", "27", "27ABCDE1234F1Z5", "Pune", "No returns after 7 days")
    assert screen.warnings == [] and screen.errors == []


def test_blank_gstin_is_stored_as_none_and_a_bad_one_is_refused(screen):
    screen.gstin_edit.setText("")
    screen.save_shop()
    assert shop.get_shop(screen.session.conn)["gstin"] is None
    screen.gstin_edit.setText("27ABCDE1234F1Z5")                    # the state is 36
    screen.save_shop()
    assert screen.warnings == ["ob.invalid_gstin"] and shop.get_shop(screen.session.conn)["gstin"] is None


def test_an_empty_shop_name_is_reported_and_nothing_changes(screen):
    screen.name_edit.setText(" ")
    screen.save_shop()
    assert len(screen.errors) == 1 and shop.get_shop(screen.session.conn)["name"] == "Test Shop"
    assert screen.name_edit.text() == "Test Shop"                   # the form reverts to the saved value


def test_billing_switches_apply_immediately(screen):
    screen.gst_box.setChecked(False)
    screen.incl_box.setChecked(False)
    screen.oversell_box.setCurrentIndex(screen.oversell_box.findData("block"))
    row = shop.get_shop(screen.session.conn)
    assert (row["gst_enabled"], row["price_includes_gst"], row["oversell_policy"]) == (0, 0, "block")
    assert billing.get_bill(screen.session.conn, billing.start_bill(screen.session.conn))["bill"]["gst_mode"] == "estimate"


def test_changing_the_segment_asks_first_and_resets_features(screen):
    screen.template_box.setCurrentIndex(screen.template_box.findData("electronics"))
    screen._confirm = lambda key: False
    screen.apply_template_button.click()
    assert shop.get_shop(screen.session.conn)["template"] == "grocery"
    asked = []
    screen._confirm = lambda key: asked.append(key) or True
    screen.apply_template_button.click()
    assert asked == ["set.template_confirm"] and shop.get_shop(screen.session.conn)["template"] == "electronics"
    assert screen.feature_boxes["serial"].isChecked() and screen.feature_boxes["warranty"].isChecked()
    assert not screen.feature_boxes["weighed"].isChecked()


def test_feature_switches_mix_segments(screen):
    screen.feature_boxes["serial"].setChecked(True)
    screen.feature_boxes["weighed"].setChecked(False)
    assert segments.feature_enabled(screen.session.conn, "serial") and not segments.feature_enabled(screen.session.conn, "weighed")


def test_printing_options_are_saved_to_the_settings_file(screen):
    screen.layout_box.setCurrentIndex(screen.layout_box.findData("a4"))
    screen.auto_print_box.setChecked(True)
    saved = ui_settings.load(screen.session.paths.settings_path)
    assert saved.print_layout == "a4" and saved.auto_print is True
    screen.layout_box.setCurrentIndex(screen.layout_box.findData(""))
    assert ui_settings.load(screen.session.paths.settings_path).print_layout == ""


def test_language_choice_switches_and_saves(screen, qtbot):
    with qtbot.waitSignal(screen.session.language_changed):
        screen.language_box.setCurrentIndex(screen.language_box.findData("hi"))
    assert i18n.get_language() == "hi" and shop.get_shop(screen.session.conn)["language"] == "hi"


def test_language_switch_retranslates_the_labels_and_keeps_the_choices(screen):
    screen.session.set_language("te")
    screen.retranslate()
    assert screen.save_shop_button.text() == i18n.tr("set.save")
    assert screen.template_box.itemText(0) == i18n.tr("tpl.electronics")          # templates are listed sorted
    assert screen.template_box.currentData() == "grocery"                          # the choice survives
    assert screen.oversell_box.currentData() == "warn" and screen.language_box.currentData() == "te"


def test_read_only_disables_data_changes_but_not_printing_or_language(screen):
    screen.apply_read_only(True)
    for name in ("name_edit", "state_box", "gstin_edit", "address_edit", "footer_edit", "save_shop_button", "gst_box",
                 "incl_box", "oversell_box", "template_box", "apply_template_button"):
        assert not getattr(screen, name).isEnabled(), name
    assert not any(box.isEnabled() for box in screen.feature_boxes.values())
    assert screen.layout_box.isEnabled() and screen.auto_print_box.isEnabled() and screen.language_box.isEnabled()
    screen.apply_read_only(False)
    assert screen.save_shop_button.isEnabled() and all(b.isEnabled() for b in screen.feature_boxes.values())


def test_translated_labels_differ_from_english(screen):
    en = screen.save_shop_button.text()
    screen.session.set_language("hi")
    screen.retranslate()
    assert screen.save_shop_button.text() != en and screen.feature_boxes["serial"].text() != "Serial / IMEI tracking"


def _expire(screen):
    from retail import guard, license as lic
    screen.session.license = lic.LicenseState("expired", expires="2020-01-01")
    guard.set_read_only(True)
    screen.apply_read_only(True)


def test_read_only_handlers_are_blocked_and_widgets_revert(screen):
    _expire(screen)
    try:
        screen.gst_box.setChecked(False)
        screen.feature_boxes["serial"].setChecked(True)
        screen.name_edit.setText("Other")
        screen.save_shop()
        screen.template_box.setCurrentIndex(screen.template_box.findData("electronics"))
        screen.apply_template_button.click()
    finally:
        from retail import guard
        guard.set_read_only(False)
    row = shop.get_shop(screen.session.conn)
    assert row["gst_enabled"] == 1 and row["name"] == "Test Shop" and row["template"] == "grocery"
    assert not segments.feature_enabled(screen.session.conn, "serial")
    assert screen.errors == [] and screen.gst_box.isChecked() and not screen.feature_boxes["serial"].isChecked()


def test_language_and_printing_still_work_when_read_only(screen, qtbot):
    from retail import guard
    _expire(screen)
    try:
        with qtbot.waitSignal(screen.session.language_changed):
            screen.language_box.setCurrentIndex(screen.language_box.findData("te"))
        screen.auto_print_box.setChecked(True)
    finally:
        guard.set_read_only(False)
    assert i18n.get_language() == "te" and screen.errors == []
    assert shop.get_shop(screen.session.conn)["language"] == "en"
    assert ui_settings.load(screen.session.paths.settings_path).auto_print is True


def test_engine_rejection_reverts_the_switch_and_reports(screen, monkeypatch):
    def boom(*a, **k):
        raise segments.SegmentError("nope") if hasattr(segments, "SegmentError") else ValueError("nope")
    monkeypatch.setattr(segments, "set_feature", boom)
    screen.feature_boxes["serial"].setChecked(True)
    assert len(screen.errors) == 1 and not screen.feature_boxes["serial"].isChecked()


def test_settings_screen_is_registered_before_the_data_screen():
    from retail_ui.screens.registry import all_screens
    assert all_screens()[-2] is SettingsScreen
