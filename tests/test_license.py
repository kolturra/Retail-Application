import re
import sys
from datetime import date

import pytest

from retail import guard
from retail import license as lic
from tools import license_issuer as issuer

MACHINE = "RTL-AAAA-BBBB-CCCC-DDDD"
TODAY = date(2026, 9, 30)


@pytest.fixture
def keys():
    return issuer.generate_keypair()


def make_key(priv, *, machine=MACHINE, expires="2027-09-30", buyer="Sri Kirana", plan="standard"):
    return issuer.issue(priv, machine=machine, buyer=buyer, expires=expires, plan=plan)


def test_valid_key_is_active(keys):
    priv, pub = keys
    state = lic.verify_key(make_key(priv), MACHINE, pub, TODAY)
    assert state.status == "active" and not state.read_only
    assert (state.buyer, state.expires, state.plan) == ("Sri Kirana", "2027-09-30", "standard")


def test_last_day_is_valid_and_next_day_is_expired(keys):
    priv, pub = keys
    key = make_key(priv, expires="2027-09-30")
    assert lic.verify_key(key, MACHINE, pub, date(2027, 9, 30)).status == "active"
    expired = lic.verify_key(key, MACHINE, pub, date(2027, 10, 1))
    assert expired.status == "expired" and expired.read_only and expired.buyer == "Sri Kirana"


def test_key_for_another_pc_is_invalid(keys):
    priv, pub = keys
    state = lic.verify_key(make_key(priv, machine="RTL-1111-2222-3333-4444"), MACHINE, pub, TODAY)
    assert state.status == "invalid" and state.read_only and state.reason


def test_tampered_payload_is_invalid(keys):
    priv, pub = keys
    payload, sig = make_key(priv).split(".")
    forged = lic.b64e(lic.b64d(payload).replace(b"2027", b"2099")) + "." + sig
    assert lic.verify_key(forged, MACHINE, pub, TODAY).status == "invalid"


def test_key_signed_by_someone_else_is_invalid(keys):
    priv, _ = keys
    _, other_pub = issuer.generate_keypair()
    assert lic.verify_key(make_key(priv), MACHINE, other_pub, TODAY).status == "invalid"


@pytest.mark.parametrize("garbage", ["", "abc", "a.b", ".....", "!!!.???", " ", "a.b.c", "తె.x"])
def test_garbage_never_raises(keys, garbage):
    _, pub = keys
    assert lic.verify_key(garbage, MACHINE, pub, TODAY).status == "invalid"


def test_key_with_bad_expiry_is_invalid(keys):
    priv, pub = keys
    payload = b'{"buyer":"x","expires":"never","machine":"%s","plan":"p"}' % MACHINE.encode()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    sig = Ed25519PrivateKey.from_private_bytes(priv).sign(payload)
    key = lic.b64e(payload) + "." + lic.b64e(sig)
    assert lic.verify_key(key, MACHINE, pub, TODAY).status == "invalid"


def test_machine_id_is_stable_and_well_formed():
    a = lic.machine_id_from_guid("  ABCD-1234  ")
    assert re.fullmatch(r"RTL-[0-9A-F]{4}(-[0-9A-F]{4}){3}", a)
    assert a == lic.machine_id_from_guid("abcd-1234")
    assert a != lic.machine_id_from_guid("abcd-1235")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry only")
def test_real_machine_id_on_windows():
    assert re.fullmatch(r"RTL-[0-9A-F]{4}(-[0-9A-F]{4}){3}", lic.get_machine_id())


def test_apply_license_sets_read_only_guard(keys, tmp_path):
    priv, pub = keys
    path = tmp_path / "license.key"
    assert lic.load_key(path) is None
    assert lic.apply_license(path, pub, MACHINE, TODAY).status == "invalid"   # no key yet
    assert guard.is_read_only() is True
    lic.save_key(path, make_key(priv))
    assert lic.apply_license(path, pub, MACHINE, TODAY).status == "active"
    assert guard.is_read_only() is False
    assert lic.apply_license(path, pub, MACHINE, date(2028, 1, 1)).status == "expired"
    assert guard.is_read_only() is True


def test_embedded_public_key_is_a_32_byte_ed25519_key():
    from retail import public_key
    assert len(public_key.PUBLIC_KEY) == 32


def test_cli_gen_keys_then_issue_verifies(tmp_path, monkeypatch, capsys):
    (tmp_path / "retail").mkdir()
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys"]) == 0
    assert issuer.main(["gen-keys", "--out", "keys"]) == 1          # never overwrite a private key
    capsys.readouterr()
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "Test", "--expires", "2027-01-01"]) == 0
    key = capsys.readouterr().out.strip()
    ns = {}
    exec((tmp_path / "retail" / "public_key.py").read_text(encoding="utf-8"), ns)
    assert lic.verify_key(key, MACHINE, ns["PUBLIC_KEY"], TODAY).status == "active"
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "T", "--expires", "01/01/2027"]) == 2


@pytest.mark.parametrize("kwargs", [
    {"expires": "never"}, {"expires": "01/01/2027"}, {"expires": None}, {"expires": 20270101},
    {"machine": ""}, {"machine": "  "}, {"buyer": ""}, {"buyer": None},
])
def test_issue_validates_inputs(keys, kwargs):
    priv, _ = keys
    args = {"machine": MACHINE, "buyer": "Test", "expires": "2027-01-01", **kwargs}
    with pytest.raises(ValueError):
        issuer.issue(priv, **args)


@pytest.mark.parametrize("garbage", [None, 123, b"x.y"])
def test_non_string_key_never_raises(keys, garbage):
    _, pub = keys
    assert lic.verify_key(garbage, MACHINE, pub, TODAY).status == "invalid"


def test_apply_license_survives_corrupt_key_file(keys, tmp_path):
    _, pub = keys
    path = tmp_path / "license.key"
    path.write_bytes(bytes([0xff, 0xfe, 0x00, 0x80]))
    assert lic.apply_license(path, pub, MACHINE, TODAY).status == "invalid"
    assert guard.is_read_only() is True
