from retail import clock
from retail.db import transaction
from retail.guard import writes
from retail.services import audit

_TYPES = ("customer", "supplier", "both")
_RECEIVE_MODES = ("cash", "upi", "card")


class PartyError(ValueError):
    pass


def _is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


@writes
def create_party(conn, *, name, phone=None, gstin=None, state_code=None, type="customer",
                 opening_balance_paise=0):
    name = (name or "").strip()
    if not name:
        raise PartyError("Party name is required")
    if type not in _TYPES:
        raise PartyError(f"type must be one of {_TYPES}")
    if not _is_plain_int(opening_balance_paise):
        raise PartyError("opening_balance_paise must be a whole number of paise")
    with transaction(conn):
        cur = conn.execute(
            """INSERT INTO party(name, phone, gstin, state_code, type, opening_balance_paise)
               VALUES (?,?,?,?,?,?)""",
            (name, phone, gstin, state_code, type, opening_balance_paise),
        )
        audit.log(conn, "create", "party", cur.lastrowid, name)
    return cur.lastrowid


def balance(conn, party_id):
    """Positive means the party owes the shop (udhaar)."""
    row = conn.execute(
        """SELECT p.opening_balance_paise
             + COALESCE((SELECT SUM(CASE b.kind WHEN 'sale' THEN pay.amount_paise
                                                ELSE -pay.amount_paise END)
                         FROM payment pay JOIN bill b ON b.id = pay.bill_id
                         WHERE b.party_id = p.id AND b.status = 'final' AND pay.mode = 'credit'), 0)
             - COALESCE((SELECT SUM(amount_paise) FROM party_payment WHERE party_id = p.id), 0)
           FROM party p WHERE p.id = ?""",
        (party_id,),
    ).fetchone()
    if row is None:
        raise PartyError("No such party")
    return row[0]


@writes
def receive_payment(conn, party_id, amount_paise, mode="cash", note=""):
    if not _is_plain_int(amount_paise):
        raise PartyError("amount_paise must be a whole number of paise")
    if amount_paise <= 0:
        raise PartyError("Payment must be greater than zero")
    if mode not in _RECEIVE_MODES:
        raise PartyError(f"mode must be one of {_RECEIVE_MODES}")
    with transaction(conn):
        if conn.execute("SELECT 1 FROM party WHERE id = ?", (party_id,)).fetchone() is None:
            raise PartyError("No such party")
        cur = conn.execute(
            "INSERT INTO party_payment(party_id, amount_paise, mode, note, created_at) VALUES (?,?,?,?,?)",
            (party_id, amount_paise, mode, note, clock.now_iso()),
        )
        audit.log(conn, "receive_payment", "party", party_id, f"{amount_paise} via {mode}")
    return cur.lastrowid


def list_dues(conn):
    dues = []
    for p in conn.execute("SELECT id, name, phone FROM party WHERE type IN ('customer','both')").fetchall():
        bal = balance(conn, p["id"])
        if bal > 0:
            dues.append({"party_id": p["id"], "name": p["name"], "phone": p["phone"], "balance_paise": bal})
    return sorted(dues, key=lambda d: (-d["balance_paise"], d["name"]))
