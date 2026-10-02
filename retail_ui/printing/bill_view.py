"""Everything a printed or sent bill shows, as ready-to-print (already localised) strings."""
from dataclasses import dataclass

from retail import segments
from retail.i18n import tr
from retail.services import billing, gst, shop
from retail_ui import fmt, states

LAYOUTS = ("thermal_58", "thermal_80", "a4")


@dataclass(frozen=True)
class LineView:
    name: str
    qty: str
    rate: str
    gst: str
    amount: str
    serial: str
    hsn: str = ""


@dataclass(frozen=True)
class BillView:
    layout: str
    title: str
    shop_name: str
    shop_address: str
    shop_gstin: str
    footer: str
    bill_no: str
    date: str
    customer_name: str
    customer_phone: str
    customer_gstin: str
    lines: tuple
    taxable: str
    cgst: str
    sgst: str
    igst: str
    round_off: str
    total: str
    payments: tuple     # ((payment-mode label, amount), ...)
    warranty: tuple     # ((serial, valid-until date), ...)
    show_tax: bool
    place_of_supply: str = ""      # "36 - Telangana"; blank on an estimate


def _money_or_blank(paise):
    return fmt.rupees(paise) if paise else ""


def _place_of_supply(bill, shop_row, party):
    # frozen on the bill at sale; bills from before the snapshot fall back to the live state
    code = bill["place_of_supply_state"] or gst.place_of_supply(
        shop_row["state_code"], party["state_code"] if party else None)
    name = states.STATES.get(code)
    return f"{code} - {name}" if name else str(code or "")


def build_bill_view(conn, bill_id, *, layout=None) -> BillView:
    detail = billing.get_bill_detail(conn, bill_id)
    bill = detail["bill"]
    if bill["status"] != "final":
        raise billing.BillingError("Only a finished bill can be printed")
    if layout is None:
        layout = segments.template_settings(conn).get("bill_layout", "a4")
    if layout not in LAYOUTS:
        raise ValueError(f"Unknown print layout {layout!r}")
    s = shop.get_shop(conn)
    show_tax = bill["gst_mode"] == "gst"
    if bill["kind"] == "sale_return":
        title = tr("print.return")
    else:
        title = tr("print.invoice") if show_tax else tr("print.estimate")
    party = detail["party"]
    lines = tuple(
        LineView(
            name=l["item_name"],
            qty=fmt.qty(l["qty_milli"]) + (f" {l['unit']}" if l["tracking"] == "weighed" else ""),
            rate=fmt.rupees(l["rate_paise"]),
            gst=f"{l['gst_rate_bp'] / 100:g}%" if show_tax and l["gst_rate_bp"] else "",
            amount=fmt.rupees(l["total_paise"]),
            serial=l["serial"] or "",
            hsn=l["hsn"] or "",
        )
        for l in detail["lines"]
    )
    return BillView(
        layout=layout, title=title,
        shop_name=s["name"], shop_address=s["address"], shop_gstin=s["gstin"] or "", footer=s["bill_footer"],
        bill_no=bill["bill_no"], date=fmt.date_text(bill["finalized_at"]),
        customer_name=party["name"] if party else "",
        customer_phone=(party["phone"] or "") if party else "",
        customer_gstin=(party["gstin"] or "") if party else "",
        lines=lines,
        taxable=fmt.rupees(bill["taxable_paise"]) if show_tax else "",
        cgst=_money_or_blank(bill["cgst_paise"]) if show_tax else "",
        sgst=_money_or_blank(bill["sgst_paise"]) if show_tax else "",
        igst=_money_or_blank(bill["igst_paise"]) if show_tax else "",
        round_off=_money_or_blank(bill["round_off_paise"]),
        total=fmt.rupees(bill["total_paise"]),
        payments=tuple((tr(f"pay.{p['mode']}"), fmt.rupees(p["amount_paise"])) for p in detail["payments"]),
        warranty=tuple((w["serial"], fmt.date_text(w["end_date"])) for w in detail["warranties"]),
        show_tax=show_tax, place_of_supply=_place_of_supply(bill, s, party) if show_tax else "",
    )
