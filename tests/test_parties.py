import pytest

from retail.services import parties


def test_create_party_and_opening_balance(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", phone="9876543210", state_code="36",
                               opening_balance_paise=25000)
    assert parties.balance(shop_conn, pid) == 25000


def test_receive_payment_reduces_balance(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi", opening_balance_paise=25000)
    parties.receive_payment(shop_conn, pid, 10000, mode="upi", note="part payment")
    assert parties.balance(shop_conn, pid) == 15000


@pytest.mark.parametrize("amount", [0, -5])
def test_receive_payment_requires_positive_amount(shop_conn, amount):
    pid = parties.create_party(shop_conn, name="Ravi")
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, pid, amount)


def test_receive_payment_rejects_bad_mode_and_unknown_party(shop_conn):
    pid = parties.create_party(shop_conn, name="Ravi")
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, pid, 100, mode="credit")
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, 999, 100)


def test_create_party_validation(shop_conn):
    with pytest.raises(parties.PartyError):
        parties.create_party(shop_conn, name=" ")
    with pytest.raises(parties.PartyError):
        parties.create_party(shop_conn, name="X", type="alien")


def test_list_dues_orders_largest_first_and_hides_zero(shop_conn):
    a = parties.create_party(shop_conn, name="A", opening_balance_paise=100)
    b = parties.create_party(shop_conn, name="B", opening_balance_paise=900)
    parties.create_party(shop_conn, name="C")
    dues = parties.list_dues(shop_conn)
    assert [d["name"] for d in dues] == ["B", "A"]
    assert dues[0]["balance_paise"] == 900 and dues[0]["party_id"] == b and a


@pytest.mark.parametrize("bad", [True, 1.5, "100", None])
def test_create_party_rejects_non_int_opening_balance(shop_conn, bad):
    with pytest.raises(parties.PartyError):
        parties.create_party(shop_conn, name="Ravi", opening_balance_paise=bad)
    assert shop_conn.execute("SELECT COUNT(*) FROM party").fetchone()[0] == 0


@pytest.mark.parametrize("bad", [True, 100.0, "100", None])
def test_receive_payment_rejects_non_int_amount(shop_conn, bad):
    pid = parties.create_party(shop_conn, name="Ravi", opening_balance_paise=500)
    with pytest.raises(parties.PartyError):
        parties.receive_payment(shop_conn, pid, bad)
    assert parties.balance(shop_conn, pid) == 500


def test_balance_unknown_party_raises(shop_conn):
    with pytest.raises(parties.PartyError):
        parties.balance(shop_conn, 999)
