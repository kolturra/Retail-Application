"""Send a finished bill through WhatsApp click-to-chat (wa.me). The message is customer and bill
details only; it never contains purchase prices or the shop's own tax id."""
import re
import urllib.parse

from retail.i18n import tr

MAX_URL = 1900


def normalise_phone(raw, default_cc="91"):
    """Digits-only with a country code (a bare 10-digit number is assumed to be Indian)."""
    digits = re.sub(r"[^0-9]", "", raw or "")   # ASCII digits only
    if not digits:
        return None
    if len(digits) == 10:
        return default_cc + digits
    if len(digits) == 11 and digits.startswith("0"):
        return default_cc + digits[1:]
    return digits


def build_message(view, *, max_lines=20):
    out = [view.shop_name, f"{tr('print.bill_no')}: {view.bill_no}   {view.date}"]
    if view.customer_name:
        out.append(f"{tr('bill.customer')}: {view.customer_name}")
    out.append("-" * 16)
    shown = view.lines[:max_lines]
    for line in shown:
        out.append(f"{line.name} x {line.qty} = {line.amount}")
    hidden = len(view.lines) - len(shown)
    if hidden > 0:
        out.append(tr("whatsapp.more", count=hidden))
    out.append("-" * 16)
    out.append(f"{tr('bill.total')}: {view.total}")
    for label, amount in view.payments:
        out.append(f"{label}: {amount}")
    out.append(tr("print.thanks"))
    return "\n".join(out)


def bill_url(view, raw_phone):
    phone = normalise_phone(raw_phone)
    if not phone:
        return None
    url = ""
    for limit in (20, 12, 8, 5, 0):  # shorten the item list until the link is short enough
        text = build_message(view, max_lines=limit)
        url = f"https://wa.me/{phone}?text={urllib.parse.quote(text)}"
        if len(url) <= MAX_URL:
            break
    return url


def open_whatsapp(view, raw_phone, opener=None):
    url = bill_url(view, raw_phone)
    if url is None:
        return False
    if opener is None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        def opener(link):
            QDesktopServices.openUrl(QUrl(link))
    opener(url)
    return True
