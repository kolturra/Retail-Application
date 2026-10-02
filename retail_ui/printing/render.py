from html import escape as e
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from retail.i18n import tr

_WIDTH_MM = {"thermal_58": 58.0, "thermal_80": 80.0}


def _totals(v):
    rows = []
    if v.show_tax:
        rows.append((tr("tax.taxable"), v.taxable))
        for key, value in (("tax.cgst", v.cgst), ("tax.sgst", v.sgst), ("tax.igst", v.igst)):
            if value:
                rows.append((tr(key), value))
    if v.round_off:
        rows.append((tr("bill.round_off"), v.round_off))
    rows.append((tr("bill.total"), v.total))
    return rows


def _thermal_html(v):
    size = 7 if v.layout == "thermal_58" else 8
    out = [f"<div style='font-size:{size}pt;'>",
           f"<p align='center'><b>{e(v.shop_name)}</b><br>{e(v.shop_address)}"]
    if v.shop_gstin:
        out.append(f"<br>{e(tr('tax.gstin'))}: {e(v.shop_gstin)}")
    out.append(f"</p><hr><p align='center'><b>{e(v.title)}</b></p>")
    out.append(f"<p>{e(tr('print.bill_no'))}: {e(v.bill_no)}<br>{e(tr('common.date'))}: {e(v.date)}")
    if v.customer_name:
        out.append(f"<br>{e(tr('bill.customer'))}: {e(v.customer_name)}")
    out.append("</p><hr><table width='100%' cellspacing='0'>")
    for line in v.lines:
        name = e(line.name)
        if line.serial:
            name += f"<br>{e(tr('trk.serial'))}: {e(line.serial)}"
        out.append(f"<tr><td colspan='2'>{name}</td></tr>")
        out.append(f"<tr><td>{e(line.qty)} x {e(line.rate)}</td>"
                   f"<td align='right'>{e(line.amount)}</td></tr>")
    out.append("</table><hr><table width='100%' cellspacing='0'>")
    for label, value in _totals(v):
        out.append(f"<tr><td>{e(label)}</td><td align='right'><b>{e(value)}</b></td></tr>")
    out.append("</table>")
    if v.payments:
        paid = ", ".join(f"{label} {amount}" for label, amount in v.payments)
        out.append(f"<hr><p>{e(tr('print.paid_by'))}: {e(paid)}</p>")
    for serial, until in v.warranty:
        out.append(f"<p>{e(serial)}: {e(tr('print.warranty'))} {e(until)}</p>")
    if v.footer:
        out.append(f"<p align='center'>{e(v.footer)}</p>")
    out.append(f"<p align='center'>{e(tr('print.thanks'))}</p></div>")
    return "".join(out)


def _a4_html(v):
    out = ["<div style='font-size:10pt;'>",
           f"<h2>{e(v.shop_name)}</h2><p>{e(v.shop_address)}"]
    if v.shop_gstin:
        out.append(f"<br>{e(tr('tax.gstin'))}: {e(v.shop_gstin)}")
    out.append(f"</p><h3>{e(v.title)}</h3>")
    out.append(f"<p>{e(tr('print.bill_no'))}: <b>{e(v.bill_no)}</b> &nbsp;&nbsp; "
               f"{e(tr('common.date'))}: {e(v.date)}")
    if v.place_of_supply:
        out.append(f"<br>{e(tr('bill.place_of_supply'))}: {e(v.place_of_supply)}")
    out.append("</p>")
    if v.customer_name:
        extra = " ".join(x for x in (v.customer_phone, f"{tr('tax.gstin')}: {v.customer_gstin}"
                                     if v.customer_gstin else "") if x)
        out.append(f"<p>{e(tr('bill.customer'))}: <b>{e(v.customer_name)}</b> {e(extra)}</p>")
    out.append("<table width='100%' border='1' cellspacing='0' cellpadding='4'><tr>"
               f"<th>#</th><th align='left'>{e(tr('bill.item'))}</th><th>{e(tr('bill.hsn'))}</th><th>{e(tr('bill.qty'))}</th>"
               f"<th>{e(tr('bill.rate'))}</th><th>{e(tr('counter.gst'))}</th><th>{e(tr('bill.total'))}</th></tr>")
    for i, line in enumerate(v.lines, 1):
        name = e(line.name)
        if line.serial:
            name += f"<br>{e(tr('trk.serial'))}: {e(line.serial)}"
        out.append(f"<tr><td align='right'>{i}</td><td>{name}</td><td>{e(line.hsn)}</td><td align='right'>{e(line.qty)}</td>"
                   f"<td align='right'>{e(line.rate)}</td><td align='right'>{e(line.gst)}</td>"
                   f"<td align='right'>{e(line.amount)}</td></tr>")
    out.append("</table><br><table align='right' cellspacing='0' cellpadding='3'>")
    for label, value in _totals(v):
        out.append(f"<tr><td>{e(label)}</td><td align='right'><b>{e(value)}</b></td></tr>")
    out.append("</table><br clear='all'>")
    if v.payments:
        paid = ", ".join(f"{label} {amount}" for label, amount in v.payments)
        out.append(f"<p>{e(tr('print.paid_by'))}: {e(paid)}</p>")
    for serial, until in v.warranty:
        out.append(f"<p>{e(tr('trk.serial'))} {e(serial)} — {e(tr('print.warranty'))} {e(until)}</p>")
    if v.footer:
        out.append(f"<p>{e(v.footer)}</p>")
    out.append(f"<p align='center'>{e(tr('print.thanks'))}</p></div>")
    return "".join(out)


def build_document(view) -> QTextDocument:
    doc = QTextDocument()
    app = QApplication.instance()
    if app is not None:
        doc.setDefaultFont(app.font())      # the per-language font chosen at startup
    doc.setHtml(_a4_html(view) if view.layout == "a4" else _thermal_html(view))
    return doc


def make_printer(layout, pdf_path=None) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if pdf_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(pdf_path))
    if layout == "a4":
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        margin = 12.0
    else:
        printer.setPageSize(QPageSize(QSizeF(_WIDTH_MM[layout], 297.0), QPageSize.Unit.Millimeter))
        margin = 2.0
    printer.setPageMargins(QMarginsF(margin, margin, margin, margin), QPageLayout.Unit.Millimeter)
    return printer


def print_view(view, printer) -> None:
    doc = build_document(view)
    doc.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
    doc.print_(printer)


def export_pdf(view, path) -> Path:
    path = Path(path)
    printer = make_printer(view.layout, pdf_path=path)
    print_view(view, printer)
    del printer  # flush and close the file
    return path
