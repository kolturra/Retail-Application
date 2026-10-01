from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout,
                               QWidget, QWizard, QWizardPage)

from retail import i18n, segments
from retail.i18n import tr
from retail.services import shop
from retail_ui import APP_NAME, states, validators
from retail_ui.errors import show_error
from retail_ui.widgets.helpers import error_label


@dataclass
class OnboardingData:
    name: str = ""
    state_code: str = "36"
    gstin: str = ""
    address: str = ""
    template: str = "grocery"
    gst_enabled: bool = True
    price_includes_gst: bool = True
    oversell_policy: str = "warn"
    language: str = "en"
    backup_dir: str = ""
    extra_backup_dir: str = ""


def apply_onboarding(session, data: OnboardingData) -> None:
    """Validate everything first, then write; nothing is written if anything is wrong."""
    if validators.gstin_error(data.gstin, data.state_code):
        raise shop.ShopError("Invalid GSTIN for the selected state")
    if data.template not in segments.list_templates():
        raise shop.ShopError(f"Unknown template {data.template!r}")
    if not (data.name or "").strip():
        raise shop.ShopError("Shop name is required")
    for folder in (data.backup_dir, data.extra_backup_dir):
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)  # OSError here: nothing written yet
    shop.setup_shop(session.conn, name=data.name, state_code=data.state_code,
                    gstin=(data.gstin.strip().upper() or None), address=data.address,
                    template=data.template, gst_enabled=data.gst_enabled,
                    price_includes_gst=data.price_includes_gst, oversell_policy=data.oversell_policy,
                    language=data.language)
    segments.apply_template(session.conn, data.template)
    session.settings.backup_dir = data.backup_dir
    session.settings.extra_backup_dir = data.extra_backup_dir
    session.save_settings()
    session.set_language(data.language)


class _Page(QWizardPage):
    """Pages build their widgets lazily in initializePage so they are created in the language the
    user picked on the first page."""
    title_key = ""

    def __init__(self):
        super().__init__()
        self._built = False

    def initializePage(self):
        if not self._built:
            self.build()
            self._built = True
        if self.title_key:
            self.setTitle(tr(self.title_key))

    def build(self):
        raise NotImplementedError


class LanguagePage(_Page):
    def build(self):
        self.setTitle("Language / भाषा / భాష")
        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.combo.addItem(name, code)
        self.combo.setCurrentIndex(self.combo.findData(i18n.get_language()))
        layout.addWidget(self.combo)

    def initializePage(self):
        super().initializePage()
        self.setTitle("Language / भाषा / భాష")

    def validatePage(self):
        i18n.set_language(self.combo.currentData())
        return True


class ShopPage(_Page):
    title_key = "ob.shop_page"

    def build(self):
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.state = QComboBox()
        for code, name in states.STATES.items():
            self.state.addItem(f"{code} — {name}", code)
        self.state.setCurrentIndex(self.state.findData("36"))
        self.gstin = QLineEdit()
        self.address = QLineEdit()
        self.error = error_label()
        form.addRow(tr("ob.shop_name"), self.name)
        form.addRow(tr("ob.state"), self.state)
        form.addRow(tr("ob.gstin"), self.gstin)
        form.addRow(tr("ob.address"), self.address)
        form.addRow(self.error)
        for signal in (self.name.textChanged, self.gstin.textChanged, self.state.currentIndexChanged):
            signal.connect(lambda *_: self.completeChanged.emit())

    def isComplete(self):
        if not self._built:
            return False
        bad = validators.gstin_error(self.gstin.text(), self.state.currentData())
        self.error.setText(tr("ob.invalid_gstin") if bad else "")
        return bool(self.name.text().strip()) and bad is None


class SegmentPage(_Page):
    title_key = "ob.segment_page"

    def build(self):
        layout = QVBoxLayout(self)
        self.group = QButtonGroup(self)
        self._radios = {}
        for name in segments.list_templates():
            radio = QRadioButton(tr(f"tpl.{name}"))
            self.group.addButton(radio)
            self._radios[name] = radio
            layout.addWidget(radio)
        self.select(segments.list_templates()[0] if "grocery" not in self._radios else "grocery")

    def select(self, name):
        self._radios[name].setChecked(True)

    def selected(self):
        return next(name for name, radio in self._radios.items() if radio.isChecked())


class BillingPage(_Page):
    title_key = "ob.gst_page"

    def build(self):
        form = QFormLayout(self)
        self.gst_enabled = QCheckBox(tr("ob.gst_enabled"))
        self.gst_enabled.setChecked(True)
        self.prices_incl = QCheckBox(tr("ob.prices_incl"))
        self.prices_incl.setChecked(True)
        self.oversell = QComboBox()
        for code in ("block", "warn", "allow"):
            self.oversell.addItem(tr(f"ob.oversell_{code}"), code)
        self.oversell.setCurrentIndex(self.oversell.findData("warn"))
        form.addRow(self.gst_enabled)
        form.addRow(self.prices_incl)
        form.addRow(tr("ob.oversell"), self.oversell)


class BackupPage(_Page):
    title_key = "ob.backup_page"

    def build(self):
        layout = QVBoxLayout(self)
        hint = QLabel(tr("ob.backup_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.backup_dir = QLineEdit()
        self.extra_dir = QLineEdit()
        for label_key, edit in (("ob.backup_dir", self.backup_dir), ("ob.extra_dir", self.extra_dir)):
            layout.addWidget(QLabel(tr(label_key)))
            row = QHBoxLayout()
            row.addWidget(edit)
            browse = QPushButton(tr("common.browse"))
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            row.addWidget(browse)
            container = QWidget()
            container.setLayout(row)
            layout.addWidget(container)

    def _browse(self, edit):
        folder = QFileDialog.getExistingDirectory(self, tr("common.browse"), edit.text())
        if folder:
            edit.setText(folder)


class OnboardingWizard(QWizard):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle(f"{APP_NAME}")
        self.language_page, self.shop_page = LanguagePage(), ShopPage()
        self.segment_page, self.billing_page, self.backup_page = SegmentPage(), BillingPage(), BackupPage()
        for page in (self.language_page, self.shop_page, self.segment_page, self.billing_page, self.backup_page):
            self.addPage(page)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

    def initializePage(self, page_id):
        super().initializePage(page_id)
        self.setButtonText(QWizard.WizardButton.NextButton, tr("wiz.next"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("wiz.back"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("wiz.finish"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("common.cancel"))

    def collect(self) -> OnboardingData:
        return OnboardingData(
            name=self.shop_page.name.text().strip(),
            state_code=self.shop_page.state.currentData(),
            gstin=self.shop_page.gstin.text().strip(),
            address=self.shop_page.address.text().strip(),
            template=self.segment_page.selected(),
            gst_enabled=self.billing_page.gst_enabled.isChecked(),
            price_includes_gst=self.billing_page.prices_incl.isChecked(),
            oversell_policy=self.billing_page.oversell.currentData(),
            language=self.language_page.combo.currentData(),
            backup_dir=self.backup_page.backup_dir.text().strip(),
            extra_backup_dir=self.backup_page.extra_dir.text().strip(),
        )

    def accept(self):
        try:
            apply_onboarding(self.session, self.collect())
        except Exception as exc:
            show_error(self, exc)
            return
        super().accept()


def run_onboarding(session) -> bool:
    """The callable bootstrap.bootstrap() expects."""
    return OnboardingWizard(session).exec() == QDialog.DialogCode.Accepted
