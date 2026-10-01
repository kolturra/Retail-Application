from pathlib import Path

from PySide6.QtPrintSupport import QPrintPreviewDialog
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from retail.i18n import tr
from retail_ui import whatsapp
from retail_ui.printing.bill_view import build_bill_view
from retail_ui.printing.render import export_pdf, make_printer, print_view


def layout_for(session):
    """The owner's chosen layout, or None to use the segment template's default."""
    return session.settings.print_layout or None


def _view(session, bill_id):
    return build_bill_view(session.conn, bill_id, layout=layout_for(session))


def preview_bill(parent, session, bill_id):
    view = _view(session, bill_id)
    dialog = QPrintPreviewDialog(make_printer(view.layout), parent)
    dialog.paintRequested.connect(lambda printer: print_view(view, printer))
    dialog.exec()


def save_pdf(parent, session, bill_id, path=None):
    view = _view(session, bill_id)
    if path is None:
        path, _ = QFileDialog.getSaveFileName(parent, tr("bills.pdf"), f"{view.bill_no}.pdf", "PDF (*.pdf)")
        if not path:
            return None
    path = Path(path)
    export_pdf(view, path)
    if not path.exists() or path.stat().st_size == 0:     # export_pdf cannot detect a failed write
        raise OSError(f"Could not write {path}")
    return path


def send_whatsapp(parent, session, bill_id, phone=None, opener=None):
    view = _view(session, bill_id)
    if phone is None:
        phone = view.customer_phone
    if not whatsapp.normalise_phone(phone):
        phone, accepted = QInputDialog.getText(parent, tr("bills.whatsapp"), tr("wa.phone_prompt"))
        if not accepted:
            return False
    if not whatsapp.open_whatsapp(view, phone, opener=opener):
        QMessageBox.warning(parent, "", tr("wa.no_phone"))
        return False
    return True
