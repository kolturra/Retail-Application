"""The software vendor's own contact details (not the shop's). A blank value is simply not offered."""
import re
import urllib.parse

VENDOR_PHONE = "+91 98660 79246"  # also the vendor's WhatsApp number (same as Kuttu)
VENDOR_EMAIL = ""


def _digits(phone):
    return re.sub(r"\D", "", phone)


def whatsapp_request_url(machine_id):
    text = f"Hello, I need a license key for Retail App. My machine ID is {machine_id}"
    return f"https://wa.me/{_digits(VENDOR_PHONE)}?text={urllib.parse.quote(text)}"


def email_request_url(machine_id):
    if not VENDOR_EMAIL:
        return None
    subject = urllib.parse.quote("Retail App - license request")
    body = urllib.parse.quote(f"Please issue a license key for machine ID {machine_id}")
    return f"mailto:{urllib.parse.quote(VENDOR_EMAIL, safe='@')}?subject={subject}&body={body}"
