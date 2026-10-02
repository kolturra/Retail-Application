"""What a counter entry means. No Qt here: the screen asks, shows prompts, and calls back in."""
from dataclasses import dataclass

from retail.services import billing, items, shop, stock


@dataclass(frozen=True)
class Entry:
    kind: str                 # ignored | added | pick | serial | weight | new_item
    line_id: int | None = None
    items: tuple = ()
    item: object = None
    qty_milli: int = 1000
    text: str = ""
    explicit_qty: bool = True
    warn: bool = False        # the shop warns on short stock and this item is now over what is on hand


class CounterController:
    def __init__(self, holder):
        self.holder = holder  # anything with a .conn (the AppSession): picks up a restored database
        self.bill_id = None

    @property
    def conn(self):
        return self.holder.conn

    # --- entries -----------------------------------------------------------------
    def submit(self, text):
        text = (text or "").strip()
        if not text:
            return Entry("ignored")
        qty, key = items.parse_entry(text)
        if qty <= 0 or not key:
            return Entry("ignored", text=text)
        explicit = key != text            # the user typed a "3*" prefix
        matches = items.resolve(self.conn, key)
        if not matches:
            return Entry("new_item", text=key, qty_milli=qty, explicit_qty=explicit)
        if len(matches) > 1:
            return Entry("pick", items=tuple(matches), text=key, qty_milli=qty, explicit_qty=explicit)
        return self.add(matches[0], qty, explicit_qty=explicit)

    def add(self, item, qty_milli, *, serial=None, explicit_qty=True):
        tracking = item["tracking"]
        if tracking == "serial":
            if not serial:
                return Entry("serial", item=item)
            qty_milli = 1000
        elif tracking == "weighed" and not explicit_qty:
            return Entry("weight", item=item)
        bill_id = self._ensure_bill()
        line_id = billing.add_line(self.conn, bill_id, item["id"], qty_milli, serial=serial)
        return Entry("added", line_id=line_id, item=item, qty_milli=qty_milli, warn=self._short_stock(bill_id, item))

    def _short_stock(self, bill_id, item):
        """True when the shop's policy is 'warn' and the bill now holds more of this item than is in stock.
        ('block' is refused by the engine before this point and 'allow' never warns.)"""
        policy = shop.get_shop(self.conn)["oversell_policy"]
        if policy != "warn":
            return False
        on_bill = self.conn.execute("SELECT COALESCE(SUM(qty_milli), 0) FROM bill_line WHERE bill_id = ? AND item_id = ?",
                                    (bill_id, item["id"])).fetchone()[0]
        return stock.check_available(self.conn, item["id"], on_bill, policy) == "warn"

    def _ensure_bill(self):
        if self.bill_id is None:
            self.bill_id = billing.start_bill(self.conn)
        return self.bill_id

    # --- the current bill -----------------------------------------------------------
    def detail(self):
        return None if self.bill_id is None else billing.get_bill_detail(self.conn, self.bill_id)

    def has_lines(self):
        detail = self.detail()
        return bool(detail and detail["lines"])

    def remove_line(self, line_id):
        billing.remove_line(self.conn, self.bill_id, line_id)

    def batch_options(self, line_id):
        """(current_unit_id, choices) for a batch-tracked line, or None when the line has no batch to change."""
        line = next((l for l in (self.detail() or {"lines": []})["lines"] if l["id"] == line_id), None)
        if line is None or line["tracking"] != "batch":
            return None
        return line["unit_id"], stock.batch_choices(self.conn, line["item_id"], include_unit_id=line["unit_id"])

    def set_line_batch(self, line_id, unit_id):
        billing.set_line_batch(self.conn, self.bill_id, line_id, unit_id)

    def set_customer(self, party_id):
        billing.set_party(self.conn, self._ensure_bill(), party_id)

    def set_discount(self, line_id, discount_paise):
        billing.set_line_discount(self.conn, self.bill_id, line_id, discount_paise)

    # --- hold / resume / pay ----------------------------------------------------------
    def held_bills(self):
        rows = []
        for bill in billing.list_held(self.conn):
            if bill["id"] == self.bill_id:
                continue
            detail = billing.get_bill_detail(self.conn, bill["id"])
            if detail["lines"]:
                rows.append({"id": bill["id"], "party": detail["party"]["name"] if detail["party"] else "",
                             "total_paise": bill["total_paise"], "lines": len(detail["lines"])})
        return rows

    def hold(self):
        """Park the current bill; an empty one is cancelled instead. Returns the held bill id."""
        if self.bill_id is None:
            return None
        if not self.has_lines():
            billing.cancel_held(self.conn, self.bill_id)
            self.bill_id = None
            return None
        held, self.bill_id = self.bill_id, None
        return held

    def resume(self, bill_id):
        detail = billing.get_bill_detail(self.conn, bill_id)  # raises BillingError for an unknown bill
        if detail["bill"]["status"] != "held" or detail["bill"]["kind"] != "sale":
            raise billing.BillingError("Only a held sale bill can be resumed")
        if bill_id != self.bill_id:
            self.hold()
            self.bill_id = bill_id

    def discard(self):
        if self.bill_id is not None:
            billing.cancel_held(self.conn, self.bill_id)
            self.bill_id = None

    def pay(self, payments):
        if self.bill_id is None:
            raise billing.BillingError("There is no bill to pay")
        bill_no = billing.finalize(self.conn, self.bill_id, payments)
        bill_id, self.bill_id = self.bill_id, None
        return bill_id, bill_no
