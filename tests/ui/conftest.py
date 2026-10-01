import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # forced: a shell value must not open real windows

import pytest

from retail import db, license as lic, segments
from retail.services import shop
from retail_ui.paths import AppPaths
from retail_ui.session import AppSession
from retail_ui.settings import UiSettings
from tools import license_issuer


@pytest.fixture
def paths(tmp_path):
    p = AppPaths(tmp_path / "RetailApp")
    p.ensure()
    return p


@pytest.fixture
def keypair():
    return license_issuer.generate_keypair()  # (private, public)


@pytest.fixture
def machine_id():
    return "RTL-TEST-0000-0000-0001"


@pytest.fixture
def make_session(paths, keypair, machine_id):
    made = []

    def make(*, template="grocery", expires="2099-12-31", with_shop=True):
        private, public = keypair
        lic.save_key(paths.license_path, license_issuer.issue(
            private, machine=machine_id, buyer="Test Shop", expires=expires))
        conn = db.open_shop(paths.db_path, paths.backup_dir)
        state = lic.apply_license(paths.license_path, public, machine_id)
        session = AppSession(paths, UiSettings(), conn, state, public_key=public, machine_id=machine_id)
        if with_shop:
            shop.setup_shop(conn, name="Test Shop", state_code="36")
            segments.apply_template(conn, template)
        made.append(session)
        return session

    yield make
    for session in made:
        try:
            session.close()
        except Exception:  # a test may already have closed the connection
            pass
