import urllib.parse

import pytest

from retail import i18n
from retail_ui import whatsapp
from retail_ui.printing.bill_view import BillView, LineView


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def view(n_lines=2, customer="Ravi", payments=(("Cash", "₹236.00"),)):
    lines = tuple(LineView(f"Item {i}", "2", "₹100.00", "18%", "₹200.00", "") for i in range(n_lines))
    return BillView(layout="a4", title="Tax Invoice", shop_name="Sri Kirana", shop_address="Main Rd",
                    shop_gstin="36ABCDE1234F1Z5", footer="", bill_no="S000007", date="30-09-2026 10:05",
                    customer_name=customer, customer_phone="9876543210", customer_gstin="", lines=lines,
                    taxable="₹200.00", cgst="₹18.00", sgst="₹18.00", igst="", round_off="", total="₹236.00",
                    payments=payments, warranty=(), show_tax=True)


@pytest.mark.parametrize("raw,expected", [
    ("98765 43210", "919876543210"), ("+91 98765-43210", "919876543210"), ("09876543210", "919876543210"),
    ("919876543210", "919876543210"), ("442071234567", "442071234567"), ("", None), (None, None), ("abc", None),
    ("९८७६५४३२१०", None),   # Devanagari digits are not ASCII digits
])
def test_normalise_phone(raw, expected):
    assert whatsapp.normalise_phone(raw) == expected


def test_message_has_customer_and_bill_details_only():
    text = whatsapp.build_message(view())
    for expected in ("Sri Kirana", "S000007", "30-09-2026", "Ravi", "Item 0", "₹200.00", "₹236.00", "Cash"):
        assert expected in text, expected
    assert "36ABCDE1234F1Z5" not in text and "GSTIN" not in text      # the shop's tax id is not sent
    assert "Main Rd" not in text


def test_message_without_a_customer_has_no_customer_line():
    assert "None" not in whatsapp.build_message(view(customer=""))


def test_long_bills_are_shortened_with_a_localised_note():
    text = whatsapp.build_message(view(n_lines=30), max_lines=5)
    assert text.count("Item ") == 5 and i18n.tr("whatsapp.more", count=25) in text


def test_url_is_percent_encoded_and_addressed():
    url = whatsapp.bill_url(view(), "98765 43210")
    assert url.startswith("https://wa.me/919876543210?text=")
    assert urllib.parse.unquote(url.split("text=", 1)[1]) == whatsapp.build_message(view())


def test_url_stays_short_even_for_huge_bills_and_non_latin_text():
    i18n.set_language("hi")
    url = whatsapp.bill_url(view(n_lines=120, customer="रवि"), "9876543210")
    assert len(url) <= 1900 and "S000007" in urllib.parse.unquote(url)


def test_no_number_gives_no_url():
    assert whatsapp.bill_url(view(), "") is None and whatsapp.bill_url(view(), "abc") is None


def test_open_whatsapp_uses_the_opener_and_reports_failure():
    opened = []
    assert whatsapp.open_whatsapp(view(), "9876543210", opener=opened.append) is True
    assert opened[0].startswith("https://wa.me/919876543210?text=")
    assert whatsapp.open_whatsapp(view(), "", opener=opened.append) is False and len(opened) == 1
