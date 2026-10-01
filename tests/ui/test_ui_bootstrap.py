import pytest

from retail import guard, i18n, license as lic
from retail.services import shop
from retail_ui import bootstrap
from tools import license_issuer


def onboard(name="Boot Shop", language="en"):
    def run(session):
        shop.setup_shop(session.conn, name=name, state_code="36", language=language)
        return True
    return run


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    i18n.set_language("en")


def valid_key(keypair, machine_id, expires="2099-12-31"):
    return license_issuer.issue(keypair[0], machine=machine_id, buyer="B", expires=expires)


def boot(paths, keypair, machine_id, **kwargs):
    kwargs.setdefault("run_onboarding", onboard())
    return bootstrap.bootstrap(paths, public_key=keypair[1], machine_id=machine_id, **kwargs)


def test_first_run_asks_for_a_key_then_onboards(paths, keypair, machine_id):
    asked = []

    def request(mid, invalid):
        asked.append((mid, invalid))
        return valid_key(keypair, machine_id)

    session = boot(paths, keypair, machine_id, request_activation=request)
    try:
        assert asked == [(machine_id, False)]
        assert session.has_shop() and session.shop()["name"] == "Boot Shop" and session.license.status == "active"
        assert lic.load_key(paths.license_path) is not None and not guard.is_read_only()
    finally:
        session.close()


def test_invalid_key_is_asked_again_and_a_bad_key_is_never_saved(paths, keypair, machine_id):
    answers = iter(["garbage", valid_key(keypair, machine_id)])
    flags = []

    def request(mid, invalid):
        flags.append(invalid)
        return next(answers)

    session = boot(paths, keypair, machine_id, request_activation=request)
    try:
        assert flags == [False, True] and session.license.status == "active"
    finally:
        session.close()


def test_quitting_at_activation_returns_none_and_saves_nothing(paths, keypair, machine_id):
    assert boot(paths, keypair, machine_id, request_activation=lambda m, i: None) is None
    assert lic.load_key(paths.license_path) is None


def test_existing_valid_licence_and_shop_skip_both_dialogs(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    first = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("no prompt"))
    first.close()
    second = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("no prompt"),
                  run_onboarding=lambda s: pytest.fail("already set up"))
    try:
        assert second.shop()["name"] == "Boot Shop"
    finally:
        second.close()


def test_expired_licence_opens_read_only(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("x")).close()
    from datetime import date
    session = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("x"),
                   today=date(2100, 1, 1))
    try:
        assert session.read_only and guard.is_read_only() and session.license.status == "expired"
    finally:
        session.close()


def test_cancelled_onboarding_returns_none(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    assert boot(paths, keypair, machine_id, request_activation=lambda m, i: None,
                run_onboarding=lambda s: False) is None


def test_expired_licence_with_no_shop_returns_a_read_only_session_without_a_shop(paths, keypair, machine_id):
    from datetime import date
    lic.save_key(paths.license_path, valid_key(keypair, machine_id, expires="2099-12-31"))
    session = boot(paths, keypair, machine_id, request_activation=lambda m, i: pytest.fail("no prompt"),
                   run_onboarding=lambda s: pytest.fail("writes are blocked"), today=date(2100, 1, 1))
    try:
        assert session.has_shop() is False and session.read_only is True
        assert session.conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        session.close()


def test_quitting_at_activation_closes_the_connection(paths, keypair, machine_id):
    assert boot(paths, keypair, machine_id, request_activation=lambda m, i: None) is None
    paths.db_path.unlink()  # fails on Windows if the connection were left open


def test_onboarding_error_propagates_and_closes_the_connection(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))

    def boom(session):
        raise RuntimeError("onboarding failed")

    with pytest.raises(RuntimeError, match="onboarding failed"):
        boot(paths, keypair, machine_id, request_activation=lambda m, i: None, run_onboarding=boom)
    paths.db_path.unlink()


def test_language_from_the_shop_is_applied(paths, keypair, machine_id):
    lic.save_key(paths.license_path, valid_key(keypair, machine_id))
    session = boot(paths, keypair, machine_id, request_activation=lambda m, i: None,
                   run_onboarding=onboard(language="te"))
    try:
        assert i18n.get_language() == "te"
    finally:
        session.close()
