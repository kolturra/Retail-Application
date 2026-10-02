from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from retail import i18n, segments
from retail.i18n import tr
from retail.services import shop
from retail_ui import states, validators
from retail_ui.errors import show_error
from retail_ui.widgets import helpers
from retail_ui.widgets.base import Screen

FEATURES = ("weighed", "batch", "serial", "warranty", "emi", "udhaar", "low_stock_alerts")
LAYOUT_LABELS = {"thermal_58": "Thermal 58 mm", "thermal_80": "Thermal 80 mm", "a4": "A4"}


class SettingsScreen(Screen):
    nav_key = "nav.settings"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        self._loading = False
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)

        # --- shop details (needs Save) ----------------------------------------------------
        box, form = self._group("set.shop", layout)
        self.name_edit, self.gstin_edit = QLineEdit(), QLineEdit()
        self.address_edit, self.footer_edit = QLineEdit(), QLineEdit()
        self.state_box = QComboBox()
        for code, name in states.STATES.items():
            self.state_box.addItem(f"{code} — {name}", code)
        self._row(form, "ob.shop_name", self.name_edit)
        self._row(form, "ob.state", self.state_box)
        self._row(form, "tax.gstin", self.gstin_edit)
        self._row(form, "ob.address", self.address_edit)
        self._row(form, "set.footer", self.footer_edit)
        self.save_shop_button = self.bind(QPushButton(), "set.save")
        self.save_shop_button.clicked.connect(lambda _=False: self.save_shop())
        form.addRow(self.save_shop_button)

        # --- billing and features (apply immediately) -----------------------------------------
        box, form = self._group("set.billing", layout)
        self.gst_box = self.bind(QCheckBox(), "ob.gst_enabled")
        self.incl_box = self.bind(QCheckBox(), "ob.prices_incl")
        self.oversell_box = QComboBox()
        self.template_box = QComboBox()
        self.apply_template_button = self.bind(QPushButton(), "set.apply_template")
        form.addRow(self.gst_box)
        form.addRow(self.incl_box)
        self._row(form, "ob.oversell", self.oversell_box)
        self._row(form, "set.template", self.template_box)
        form.addRow(self.apply_template_button)
        features_box, features_form = self._group("set.features", layout)
        self.feature_boxes = {}
        for key in FEATURES:
            check = self.bind(QCheckBox(), f"feat.{key}")
            self.feature_boxes[key] = check
            features_form.addRow(check)
            check.toggled.connect(lambda checked, k=key: self._on_feature(k, checked))

        # --- printing and language (always available) -----------------------------------------
        box, form = self._group("set.printing", layout)
        self.layout_box = QComboBox()
        self.auto_print_box = self.bind(QCheckBox(), "set.auto_print")
        self._row(form, "set.layout", self.layout_box)
        form.addRow(self.auto_print_box)
        box, form = self._group("set.language", layout)
        self.language_box = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.language_box.addItem(name, code)
        form.addRow(self.language_box)
        layout.addStretch(1)

        self._fill_choices()
        self.gst_box.toggled.connect(lambda _c: self._on_billing())
        self.incl_box.toggled.connect(lambda _c: self._on_billing())
        self.oversell_box.currentIndexChanged.connect(lambda _i: self._on_billing())
        self.apply_template_button.clicked.connect(lambda _=False: self.apply_template())
        self.layout_box.currentIndexChanged.connect(lambda _i: self._on_print())
        self.auto_print_box.toggled.connect(lambda _c: self._on_print())
        self.language_box.currentIndexChanged.connect(lambda _i: self._on_language())
        self.apply_read_only(session.read_only)

    def _group(self, title_key, layout):
        group = QGroupBox()
        self.bind(group, title_key, "setTitle")
        form = QFormLayout(group)
        layout.addWidget(group)
        return group, form

    def _row(self, form, key, widget):
        form.addRow(self.bind(QLabel(), key), widget)

    def _fill_choices(self):
        """(Re)build the combos whose entries are translated; the current choice is restored by refresh()."""
        self._loading = True
        try:
            for combo in (self.oversell_box, self.template_box, self.layout_box):
                combo.clear()
            for code in ("block", "warn", "allow"):
                self.oversell_box.addItem(tr(f"ob.oversell_{code}"), code)
            for name in segments.list_templates():
                self.template_box.addItem(tr(f"tpl.{name}"), name)
            self.layout_box.addItem(tr("set.layout_auto"), "")
            for code, label in LAYOUT_LABELS.items():
                self.layout_box.addItem(label, code)
        finally:
            self._loading = False

    # --- Screen protocol ------------------------------------------------------
    def retranslate(self):
        super().retranslate()
        self._fill_choices()
        self.refresh()

    def refresh(self):
        self._loading = True
        try:
            s = self.session.shop()
            self.name_edit.setText(s["name"])
            self.state_box.setCurrentIndex(max(self.state_box.findData(s["state_code"]), 0))
            self.gstin_edit.setText(s["gstin"] or "")
            self.address_edit.setText(s["address"])
            self.footer_edit.setText(s["bill_footer"])
            self.gst_box.setChecked(bool(s["gst_enabled"]))
            self.incl_box.setChecked(bool(s["price_includes_gst"]))
            self.oversell_box.setCurrentIndex(max(self.oversell_box.findData(s["oversell_policy"]), 0))
            self.template_box.setCurrentIndex(max(self.template_box.findData(s["template"]), 0))
            for key, check in self.feature_boxes.items():
                check.setChecked(segments.feature_enabled(self.session.conn, key))
            self.layout_box.setCurrentIndex(max(self.layout_box.findData(self.session.settings.print_layout), 0))
            self.auto_print_box.setChecked(self.session.settings.auto_print)
            self.language_box.setCurrentIndex(max(self.language_box.findData(i18n.get_language()), 0))
        finally:
            self._loading = False

    def apply_read_only(self, read_only):
        for widget in (self.name_edit, self.state_box, self.gstin_edit, self.address_edit, self.footer_edit,
                       self.save_shop_button, self.gst_box, self.incl_box, self.oversell_box, self.template_box,
                       self.apply_template_button, *self.feature_boxes.values()):
            widget.setEnabled(not read_only)

    # --- actions ------------------------------------------------------------------
    def _guarded(self, action, writes=True):
        try:
            if writes and self.session.read_only:
                return          # the controls are disabled; this blocks any other route to a write
            action()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self.refresh()   # always show what is actually stored

    def save_shop(self):
        def run():
            state = self.state_box.currentData()
            if validators.gstin_error(self.gstin_edit.text(), state):
                self._warn("ob.invalid_gstin")
                return
            shop.update_shop(self.session.conn, name=self.name_edit.text(), state_code=state,
                             gstin=self.gstin_edit.text().strip().upper() or None,
                             address=self.address_edit.text().strip(), bill_footer=self.footer_edit.text().strip())
        self._guarded(run)

    def _on_billing(self):
        if self._loading:
            return
        self._guarded(lambda: shop.update_shop(
            self.session.conn, gst_enabled=self.gst_box.isChecked(), price_includes_gst=self.incl_box.isChecked(),
            oversell_policy=self.oversell_box.currentData()))

    def apply_template(self):
        chosen = self.template_box.currentData()
        declined = []

        def run():
            if self._confirm("set.template_confirm"):
                segments.apply_template(self.session.conn, chosen)
            else:
                declined.append(True)
        self._guarded(run)
        if declined:   # keep the user's pick in the box so a second click can confirm it
            self._loading = True
            try:
                self.template_box.setCurrentIndex(max(self.template_box.findData(chosen), 0))
            finally:
                self._loading = False

    def _on_feature(self, key, checked):
        if self._loading:
            return
        self._guarded(lambda: segments.set_feature(self.session.conn, key, checked))

    def _on_print(self):
        if self._loading:
            return
        self.session.settings.print_layout = self.layout_box.currentData()
        self.session.settings.auto_print = self.auto_print_box.isChecked()
        self._guarded(self.session.save_settings, writes=False)

    def _on_language(self):
        if self._loading:
            return
        code = self.language_box.currentData()
        if code != i18n.get_language():
            self._guarded(lambda: self.session.set_language(code), writes=False)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _warn(self, key):
        helpers.warn(self, key)

    def _confirm(self, key):
        return helpers.confirm(self, key)
