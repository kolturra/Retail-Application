from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QDateEdit, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableView, QTabWidget, QVBoxLayout)

from retail.i18n import tr
from retail.services import reports
from retail_ui import fmt
from retail_ui.errors import show_error
from retail_ui.widgets.base import RowsModel, Screen

SALES_HEADERS = ["print.bill_no", "common.date", "bills.type", "bill.customer", "tax.gstin", "tax.taxable",
                 "tax.cgst", "tax.sgst", "tax.igst", "bill.round_off", "bill.total"]
GST_HEADERS = ["rep.rate", "tax.taxable", "tax.cgst", "tax.sgst", "tax.igst"]
DAY_HEADERS = ["common.name", "common.amount"]
GST_COLUMNS = ["gst_rate_bp", "taxable_paise", "cgst_paise", "sgst_paise", "igst_paise"]


class ReportsScreen(Screen):
    nav_key = "nav.reports"

    def __init__(self, session, parent=None):
        super().__init__(session, parent)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        today = QDate.currentDate()
        self.from_edit, self.to_edit = QDateEdit(today), QDateEdit(today)
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd-MM-yyyy")
            edit.dateChanged.connect(lambda _d: self.refresh())
        top.addWidget(self.bind(QLabel(), "common.from"))
        top.addWidget(self.from_edit)
        top.addWidget(self.bind(QLabel(), "common.to"))
        top.addWidget(self.to_edit)
        top.addStretch(1)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.sales_model = self.track(RowsModel(SALES_HEADERS))
        self.gst_model = self.track(RowsModel(GST_HEADERS))
        self.day_model = self.track(RowsModel(DAY_HEADERS))
        for model in (self.sales_model, self.gst_model, self.day_model):
            self.tabs.addTab(self._table(model), "")
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.export_sales_button = self.bind(QPushButton(), "rep.export_sales")
        self.export_gst_button = self.bind(QPushButton(), "rep.export_gst")
        self.export_sales_button.clicked.connect(lambda _=False: self.export_sales())
        self.export_gst_button.clicked.connect(lambda _=False: self.export_gst())
        self.export_stock_button = self.bind(QPushButton(), "rep.export_stock")
        self.export_ledger_button = self.bind(QPushButton(), "rep.export_customer_ledgers")
        self.export_stock_button.clicked.connect(lambda _=False: self.export_stock())
        self.export_ledger_button.clicked.connect(lambda _=False: self.export_ledger())
        for button in (self.export_sales_button, self.export_gst_button, self.export_stock_button,
                       self.export_ledger_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self._tab_titles()

    def _table(self, model):
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _tab_titles(self):
        for i, key in enumerate(("rep.tab_sales", "rep.tab_gst", "rep.tab_day")):
            self.tabs.setTabText(i, tr(key))

    def _range(self):
        return (self.from_edit.date().toString(Qt.DateFormat.ISODate),
                self.to_edit.date().toString(Qt.DateFormat.ISODate))

    def retranslate(self):
        super().retranslate()
        self._tab_titles()
        self.status_label.clear()
        self.refresh()

    def _clear_tables(self):
        for model in (self.sales_model, self.gst_model, self.day_model):
            model.set_rows([])

    def _mode_text(self, mode):
        try:
            return tr(f"pay.{mode}")
        except KeyError:
            return str(mode)

    def refresh(self):
        conn = self.session.conn
        start, end = self._range()
        if start > end:
            self._clear_tables()
            self.status_label.setText(tr("rep.bad_range"))
            return
        self.status_label.clear()
        try:
            register = reports.sales_register(conn, start, end)
            gst = reports.gst_summary(conn, start, end)
            day = reports.daily_summary(conn, end)
        except Exception as exc:
            self._clear_tables()
            self._show_error(exc)
            return
        money_cols = ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "round_off_paise", "total_paise")
        self.sales_model.set_rows(
            [(r["bill_no"], fmt.date_text(r["bill_date"]),
              tr("bills.return") if r["kind"] == "sale_return" else tr("bills.sale"), r["party"], r["gstin"],
              *(fmt.rupees(r[c]) for c in money_cols)) for r in register],
            right_cols=range(5, 11))
        self.gst_model.set_rows(
            [(f"{r['gst_rate_bp'] / 100:g}%", *(fmt.rupees(r[c]) for c in GST_COLUMNS[1:])) for r in gst],
            right_cols=range(1, 5))
        rows = [(tr("rep.sales"), fmt.rupees(day["sales_paise"])),
                (tr("rep.returns"), fmt.rupees(day["returns_paise"])),
                (tr("rep.net"), fmt.rupees(day["net_paise"])),
                (tr("rep.by_mode"), "")]
        rows += [(self._mode_text(mode), fmt.rupees(amount)) for mode, amount in sorted(day["by_mode"].items())]
        self.day_model.set_rows(rows, right_cols=(1,))

    # --- exports (reports are read-only operations, so these stay enabled after expiry) --------
    def _export(self, default_name, build_rows, columns):
        try:
            path = self._ask_save_path(default_name)
            if not path:
                return
            start, end = self._range()
            reports.write_csv(build_rows(start, end), path, columns)
            self.status_label.setText(tr("rep.exported", path=path))
        except Exception as exc:
            self._show_error(exc)

    def export_sales(self):
        self._export("sales_register.csv", lambda s, e: reports.sales_register(self.session.conn, s, e),
                     reports.SALES_COLUMNS)

    def export_gst(self):
        self._export("gst_summary.csv", lambda s, e: reports.gst_summary(self.session.conn, s, e), GST_COLUMNS)

    def export_stock(self):
        """Whole stock register as of now (not date-ranged)."""
        self._export("stock_register.csv", lambda s, e: reports.stock_register(self.session.conn),
                     reports.STOCK_COLUMNS)

    def export_ledger(self):
        """All customer ledgers (not date-ranged: a running balance needs the full history)."""
        self._export("customer_ledgers.csv", lambda s, e: reports.party_ledger(self.session.conn),
                     reports.LEDGER_COLUMNS)

    # --- prompts ----------------------------------------------------------------------
    def _show_error(self, exc):
        show_error(self, exc)

    def _ask_save_path(self, default_name):
        path, _ = QFileDialog.getSaveFileName(self, tr("common.export"), default_name, "CSV (*.csv)")
        return path or None
