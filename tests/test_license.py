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


def make_key(priv, *, machine=MACHINE, expires="2099-09-30", buyer="Sri Kirana", plan="standard"):
    return issuer.issue(priv, machine=machine, buyer=buyer, expires=expires, plan=plan)


def test_valid_key_is_active(keys):
    priv, pub = keys
    state = lic.verify_key(make_key(priv), MACHINE, pub, TODAY)
    assert state.status == "active" and not state.read_only
    assert (state.buyer, state.expires, state.plan) == ("Sri Kirana", "2099-09-30", "standard")


def test_last_day_is_valid_and_next_day_is_expired(keys):
    priv, pub = keys
    key = make_key(priv, expires="2099-09-30")
    assert lic.verify_key(key, MACHINE, pub, date(2099, 9, 30)).status == "active"
    expired = lic.verify_key(key, MACHINE, pub, date(2099, 10, 1))
    assert expired.status == "expired" and expired.read_only and expired.buyer == "Sri Kirana"


def test_key_for_another_pc_is_invalid(keys):
    priv, pub = keys
    state = lic.verify_key(make_key(priv, machine="RTL-1111-2222-3333-4444"), MACHINE, pub, TODAY)
    assert state.status == "invalid" and state.read_only and state.reason


def test_tampered_payload_is_invalid(keys):
    priv, pub = keys
    payload, sig = make_key(priv).split(".")
    forged = lic.b64e(lic.b64d(payload).replace(b"2099", b"2100")) + "." + sig
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
    assert lic.apply_license(path, pub, MACHINE, date(2100, 1, 1)).status == "expired"
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
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "Test", "--expires", "2099-01-01"]) == 0
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
    args = {"machine": MACHINE, "buyer": "Test", "expires": "2099-01-01", **kwargs}
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


def test_gen_keys_requires_retail_dir_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys"]) == 2
    assert not (tmp_path / "keys" / "private.key").exists()
    assert "retail" in capsys.readouterr().err


def test_gen_keys_never_overwrites_existing_key(tmp_path, monkeypatch):
    (tmp_path / "retail").mkdir()
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "private.key").write_text("original", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys"]) == 1
    assert (tmp_path / "keys" / "private.key").read_text(encoding="utf-8") == "original"


def test_issue_cli_missing_key_file_is_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "T", "--expires", "2099-01-01"]) == 2
    assert "private key" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("content", ["not-hex-SECRETCONTENT", "abcd", "", "zz" * 32])
def test_issue_cli_bad_key_content_is_clean_error_and_not_echoed(tmp_path, monkeypatch, capsys, content):
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "private.key").write_text(content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "T", "--expires", "2099-01-01"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SECRETCONTENT" not in captured.err and (not content or content not in captured.err)


def test_issue_strips_machine_and_buyer_before_signing(keys):
    import base64, json
    priv, _ = keys
    key = issuer.issue(priv, machine=f"  {MACHINE} ", buyer="  Sri Kirana\n", expires="2099-01-01")
    payload = key.split(".")[0]
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert data["machine"] == MACHINE and data["buyer"] == "Sri Kirana"


@pytest.mark.parametrize("plan", ["", "  ", None, 5, b"standard"])
def test_issue_requires_non_empty_string_plan(keys, plan):
    priv, _ = keys
    with pytest.raises(ValueError):
        issuer.issue(priv, machine=MACHINE, buyer="T", expires="2099-01-01", plan=plan)


FAR_FUTURE = "2099-12-31"


def _project(tmp_path, public_text=None):
    (tmp_path / "retail").mkdir()
    if public_text is not None:
        (tmp_path / "retail" / "public_key.py").write_text(public_text, encoding="utf-8")
    return tmp_path / "retail" / "public_key.py", tmp_path / "keys" / "private.key"


def test_gen_keys_refuses_to_replace_an_existing_public_key(tmp_path, monkeypatch, capsys):
    public, private = _project(tmp_path, 'PUBLIC_KEY = bytes.fromhex("00")\n')
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys"]) == 1
    err = capsys.readouterr().err
    assert "public_key.py" in err and "--force" in err
    assert public.read_text(encoding="utf-8") == 'PUBLIC_KEY = bytes.fromhex("00")\n'
    assert not private.exists()


def test_gen_keys_force_replaces_public_key_but_never_a_private_key(tmp_path, monkeypatch):
    public, private = _project(tmp_path, 'PUBLIC_KEY = bytes.fromhex("00")\n')
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys", "--force"]) == 0
    assert private.exists() and "00" not in public.read_text(encoding="utf-8").split("fromhex")[1][:6]
    before = (public.read_text(encoding="utf-8"), private.read_text(encoding="utf-8"))
    assert issuer.main(["gen-keys", "--out", "keys", "--force"]) == 1
    assert (public.read_text(encoding="utf-8"), private.read_text(encoding="utf-8")) == before


def test_gen_keys_treats_an_empty_public_key_file_as_absent(tmp_path, monkeypatch):
    public, private = _project(tmp_path, "")
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["gen-keys", "--out", "keys"]) == 0
    assert "PUBLIC_KEY" in public.read_text(encoding="utf-8") and private.exists()


@pytest.mark.parametrize("expires", ["2099-1-31", "2099-01-31T00:00", " 2099-01-31", "20990131", "2000-01-01"])
def test_issue_requires_canonical_future_expiry(keys, expires):
    priv, _ = keys
    with pytest.raises(ValueError):
        issuer.issue(priv, machine=MACHINE, buyer="T", expires=expires)


def test_issue_cli_rejects_past_expiry_with_exit_2(tmp_path, monkeypatch, capsys):
    priv, _ = issuer.generate_keypair()
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "private.key").write_text(priv.hex(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "T", "--expires", "2000-01-01"]) == 2
    assert capsys.readouterr().out == ""
    assert issuer.main(["issue", "--machine", MACHINE, "--buyer", "T", "--expires", FAR_FUTURE]) == 0
