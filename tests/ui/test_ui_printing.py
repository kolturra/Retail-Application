import pytest
from PySide6.QtWidgets import QApplication

from retail import i18n, segments
from retail.services import billing, items, parties, shop, stock
from retail_ui.printing import bill_view, render


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def sale(conn, *, name="Soap", price=11800, rate=1800, qty=2000, payments=None, party_id=None, **item_kw):
    item = items.create_item(conn, name=name, sell_price_paise=price, gst_rate_bp=rate, **item_kw)
    stock.record(conn, item, 50_000, "opening")
    bill_id = billing.start_bill(conn, party_id=party_id)
    billing.add_line(conn, bill_id, item, qty)
    total = billing.get_bill(conn, bill_id)["bill"]["total_paise"]
    billing.finalize(conn, bill_id, payments or [("cash", total)])
    return bill_id


def test_view_has_localised_display_strings(shop_conn):
    ravi = parties.create_party(shop_conn, name="Ravi", phone="9876543210", gstin=None)
    bill_id = sale(shop_conn, party_id=ravi)
    v = bill_view.build_bill_view(shop_conn, bill_id)
    assert (v.shop_name, v.bill_no, v.customer_name, v.customer_phone) == ("Test Shop", "S000001", "Ravi", "9876543210")
    assert v.title == i18n.tr("print.invoice") and v.show_tax is True
    assert (v.lines[0].name, v.lines[0].qty, v.lines[0].rate, v.lines[0].gst, v.lines[0].amount) == (
        "Soap", "2", "₹118.00", "18%", "₹236.00")
    assert (v.taxable, v.cgst, v.sgst, v.igst, v.total) == ("₹200.00", "₹18.00", "₹18.00", "", "₹236.00")
    assert v.payments == ((i18n.tr("pay.cash"), "₹236.00"),) and v.warranty == ()
    assert v.date and v.date.count("-") == 2


def test_layout_defaults_from_the_template_and_can_be_overridden(shop_conn):
    segments.apply_template(shop_conn, "grocery")        # shop_conn applies no template by itself
    bill_id = sale(shop_conn)
    assert bill_view.build_bill_view(shop_conn, bill_id).layout == "thermal_80"      # grocery
    assert bill_view.build_bill_view(shop_conn, bill_id, layout="thermal_58").layout == "thermal_58"
    segments.apply_template(shop_conn, "electronics")
    assert bill_view.build_bill_view(shop_conn, bill_id).layout == "a4"
    with pytest.raises(ValueError):
        bill_view.build_bill_view(shop_conn, bill_id, layout="poster")


def test_only_finished_bills_can_be_viewed(shop_conn):
    held = billing.start_bill(shop_conn)
    with pytest.raises(billing.BillingError):
        bill_view.build_bill_view(shop_conn, held)


def test_estimate_bill_shows_no_tax_and_an_estimate_title(shop_conn):
    shop.update_shop(shop_conn, gst_enabled=False)
    v = bill_view.build_bill_view(shop_conn, sale(shop_conn))
    assert v.title == i18n.tr("print.estimate") and v.show_tax is False and v.lines[0].gst == ""


def test_return_bill_title_and_positive_amounts(shop_conn):
    bill_id = sale(shop_conn, qty=2000)
    line_id = billing.get_bill(shop_conn, bill_id)["lines"][0]["id"]
    ret = billing.create_return(shop_conn, bill_id, [(line_id, 1000)])
    v = bill_view.build_bill_view(shop_conn, ret)
    assert v.title == i18n.tr("print.return") and v.bill_no == "R000001" and v.total == "₹118.00"


def test_serial_and_warranty_lines(shop_conn):
    phone = items.create_item(shop_conn, name="Phone", sell_price_paise=100000, tracking="serial", warranty_months=12)
    unit = stock.add_unit(shop_conn, phone, serial="IMEI1")
    stock.record(shop_conn, phone, 1000, "opening", unit_id=unit)
    bill_id = billing.start_bill(shop_conn)
    billing.add_line(shop_conn, bill_id, phone, 1000, serial="imei1")
    billing.finalize(shop_conn, bill_id, [("cash", 40000), ("upi", 60000)])
    v = bill_view.build_bill_view(shop_conn, bill_id)
    assert v.lines[0].serial == "IMEI1" and v.warranty[0][0] == "IMEI1" and v.warranty[0][1].count("-") == 2
    assert [p[0] for p in v.payments] == [i18n.tr("pay.cash"), i18n.tr("pay.upi")]


def test_weighed_quantity_shows_the_unit(shop_conn):
    v = bill_view.build_bill_view(shop_conn, sale(shop_conn, name="Rice", price=6000, rate=0, qty=750,
                                                  unit="kg", tracking="weighed"))
    assert v.lines[0].qty == "0.75 kg"


@pytest.mark.parametrize("layout", bill_view.LAYOUTS)
def test_document_text_contains_the_bill(shop_conn, qtbot, layout):
    bill_id = sale(shop_conn, name="Soap & <b>Co</b>")
    v = bill_view.build_bill_view(shop_conn, bill_id, layout=layout)
    text = render.build_document(v).toPlainText()
    for expected in ("Test Shop", "S000001", "Soap & <b>Co</b>", "₹236.00", i18n.tr("bill.total"),
                     i18n.tr("print.thanks"), i18n.tr("tax.cgst")):
        assert expected in text, expected


def test_document_is_localised(shop_conn, qtbot):
    bill_id = sale(shop_conn)
    i18n.set_language("hi")
    text = render.build_document(bill_view.build_bill_view(shop_conn, bill_id)).toPlainText()
    assert i18n.tr("bill.total") in text and i18n.tr("print.invoice") in text and "Total" not in text


@pytest.mark.parametrize("layout", bill_view.LAYOUTS)
def test_pdf_export_for_every_layout(shop_conn, qtbot, tmp_path, layout):
    bill_id = sale(shop_conn)
    path = render.export_pdf(bill_view.build_bill_view(shop_conn, bill_id, layout=layout), tmp_path / f"{layout}.pdf")
    data = path.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 1500


def test_very_long_names_and_many_lines_still_render(shop_conn, qtbot, tmp_path):
    bill_id = billing.start_bill(shop_conn)
    for i in range(40):
        item = items.create_item(shop_conn, name=("Very long product name " * 6) + str(i), sell_price_paise=100)
        stock.record(shop_conn, item, 1000, "opening")
        billing.add_line(shop_conn, bill_id, item, 1000)
    total = billing.get_bill(shop_conn, bill_id)["bill"]["total_paise"]
    billing.finalize(shop_conn, bill_id, [("cash", total)])
    for layout in ("thermal_58", "a4"):
        v = bill_view.build_bill_view(shop_conn, bill_id, layout=layout)
        doc = render.build_document(v)
        assert doc.toPlainText().count("Very long product name") == 40 * 6    # the phrase is repeated 6x per name
        assert render.export_pdf(v, tmp_path / f"{layout}.pdf").stat().st_size > 1500


def test_printer_page_sizes(qtbot):
    from PySide6.QtGui import QPageSize
    a4 = render.make_printer("a4")
    assert a4.pageLayout().pageSize().id() == QPageSize.PageSizeId.A4
    for layout, width in (("thermal_58", 58.0), ("thermal_80", 80.0)):
        size = render.make_printer(layout).pageLayout().pageSize().size(QPageSize.Unit.Millimeter)
        assert abs(size.width() - width) < 0.5
