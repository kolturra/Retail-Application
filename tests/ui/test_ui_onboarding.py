import pytest

from retail import i18n, segments
from retail.services import shop
from retail_ui.dialogs import onboarding
from retail_ui.dialogs.onboarding import OnboardingData, OnboardingWizard, apply_onboarding


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def data(**kw):
    base = dict(name="Sri Kirana", state_code="36", gstin="36ABCDE1234F1Z5", address="Main Road",
                template="electronics", gst_enabled=True, price_includes_gst=False,
                oversell_policy="block", language="te")
    base.update(kw)
    return OnboardingData(**base)


def test_apply_onboarding_sets_up_shop_template_settings_and_language(make_session, tmp_path):
    s = make_session(with_shop=False)
    apply_onboarding(s, data(backup_dir=str(tmp_path / "bk"), extra_backup_dir=str(tmp_path / "usb")))
    row = s.shop()
    assert (row["name"], row["gstin"], row["template"], row["language"]) == ("Sri Kirana", "36ABCDE1234F1Z5", "electronics", "te")
    assert (row["price_includes_gst"], row["oversell_policy"]) == (0, "block")
    assert segments.feature_enabled(s.conn, "serial") is True
    assert s.settings.backup_dir == str(tmp_path / "bk") and (tmp_path / "bk").is_dir() and (tmp_path / "usb").is_dir()
    assert i18n.get_language() == "te"


def test_gstin_is_normalised_and_blank_gstin_is_stored_as_none(make_session):
    s = make_session(with_shop=False)
    apply_onboarding(s, data(gstin="36abcde1234f1z5", language="en"))
    assert s.shop()["gstin"] == "36ABCDE1234F1Z5"
    s2 = make_session(with_shop=False)  # same db: re-setup replaces the row
    apply_onboarding(s2, data(gstin="  ", language="en"))
    assert s2.shop()["gstin"] is None


@pytest.mark.parametrize("bad", [
    {"gstin": "123"}, {"gstin": "27ABCDE1234F1Z5"}, {"template": "pharmacy"}, {"name": " "},
    {"state_code": "ABC"},
])
def test_invalid_data_is_rejected_before_anything_is_written(make_session, bad):
    s = make_session(with_shop=False)
    with pytest.raises(shop.ShopError):
        apply_onboarding(s, data(**bad))
    assert s.has_shop() is False and s.settings.backup_dir == ""


def test_unwritable_backup_folder_is_rejected_before_any_write(make_session, tmp_path):
    s = make_session(with_shop=False)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OSError):
        apply_onboarding(s, data(backup_dir=str(blocker / "sub")))
    assert s.has_shop() is False


def test_wizard_collects_values_from_its_pages(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    for page_id in w.pageIds():
        w.page(page_id).initializePage()
    w.language_page.combo.setCurrentIndex(w.language_page.combo.findData("hi"))
    w.shop_page.name.setText("  Raju Stores ")
    w.shop_page.state.setCurrentIndex(w.shop_page.state.findData("27"))
    w.shop_page.gstin.setText("27ABCDE1234F1Z5")
    w.shop_page.address.setText("Pune")
    w.segment_page.select("electronics")
    w.billing_page.gst_enabled.setChecked(False)
    w.billing_page.prices_incl.setChecked(False)
    w.billing_page.oversell.setCurrentIndex(w.billing_page.oversell.findData("allow"))
    w.backup_page.backup_dir.setText("D:/bk")
    w.backup_page.extra_dir.setText("E:/usb")
    got = w.collect()
    assert got == OnboardingData(name="Raju Stores", state_code="27", gstin="27ABCDE1234F1Z5", address="Pune",
                                 template="electronics", gst_enabled=False, price_includes_gst=False,
                                 oversell_policy="allow", language="hi", backup_dir="D:/bk", extra_backup_dir="E:/usb")


def test_shop_page_needs_a_name_and_a_matching_gstin(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    page = w.shop_page
    page.initializePage()
    assert not page.isComplete()
    page.name.setText("Shop")
    assert page.isComplete()
    page.gstin.setText("27ABCDE1234F1Z5")   # state is 36 -> mismatch
    assert not page.isComplete() and page.error.text() == i18n.tr("ob.invalid_gstin")
    page.state.setCurrentIndex(page.state.findData("27"))
    assert page.isComplete() and page.error.text() == ""


def test_language_page_applies_the_language_when_leaving_it(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    w.language_page.initializePage()
    w.language_page.combo.setCurrentIndex(w.language_page.combo.findData("te"))
    assert w.language_page.validatePage() is True and i18n.get_language() == "te"
    w.shop_page.initializePage()
    assert w.shop_page.title() == i18n.tr("ob.shop_page")           # built in Telugu


def test_accept_applies_and_a_failure_keeps_the_wizard_open(make_session, qtbot, monkeypatch):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    for page_id in w.pageIds():
        w.page(page_id).initializePage()
    shown = []
    monkeypatch.setattr(onboarding, "show_error", lambda parent, exc: shown.append(exc))
    w.shop_page.name.setText("")
    w.accept()
    assert len(shown) == 1 and not s.has_shop() and w.result() == 0
    w.shop_page.name.setText("Good Shop")
    w.accept()
    assert s.has_shop() and w.result() == 1


def _fill_english(w):
    for page_id in w.pageIds():
        w.page(page_id).initializePage()
    w.shop_page.name.setText("Raju Stores")
    w.shop_page.address.setText("Pune")
    w.segment_page.select("electronics")
    w.billing_page.gst_enabled.setChecked(False)


def test_changing_language_after_going_back_rebuilds_pages_and_keeps_values(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    _fill_english(w)
    w.language_page.initializePage()
    w.language_page.combo.setCurrentIndex(w.language_page.combo.findData("hi"))
    assert w.language_page.validatePage() is True
    for page in (w.shop_page, w.segment_page, w.billing_page, w.backup_page):
        page.initializePage()
    assert i18n.get_language() == "hi"
    assert w.shop_page.title() == i18n.tr("ob.shop_page")
    assert w.billing_page.oversell.itemText(0) == i18n.tr("ob.oversell_block")
    got = w.collect()
    assert (got.name, got.address, got.template, got.gst_enabled, got.language) == (
        "Raju Stores", "Pune", "electronics", False, "hi")
    assert w.shop_page.name.text() == "Raju Stores" and w.shop_page.state.currentData() == "36"


def test_unchanged_language_does_not_reset_pages(make_session, qtbot):
    s = make_session(with_shop=False)
    w = OnboardingWizard(s)
    qtbot.addWidget(w)
    _fill_english(w)
    name_widget = w.shop_page.name
    w.language_page.initializePage()
    assert w.language_page.validatePage() is True
    assert w.shop_page._built and w.shop_page.name is name_widget and w._pending is None


def test_onboarding_persists_ui_settings(make_session, tmp_path):
    from retail_ui import settings as ui_settings
    s = make_session(with_shop=False)
    apply_onboarding(s, data(backup_dir=str(tmp_path / "bk"), extra_backup_dir=str(tmp_path / "usb")))
    loaded = ui_settings.load(s.paths.settings_path)
    assert (loaded.backup_dir, loaded.extra_backup_dir) == (str(tmp_path / "bk"), str(tmp_path / "usb"))
