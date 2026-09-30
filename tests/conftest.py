import pytest

from retail import db, guard


@pytest.fixture(autouse=True)
def _writable():
    guard.set_read_only(False)
    yield
    guard.set_read_only(False)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "shop.db"


@pytest.fixture
def conn(db_path):
    connection = db.connect(db_path)
    db.migrate(connection)
    yield connection
    connection.close()


from retail.services import shop as _shop


@pytest.fixture
def shop_conn(conn):
    _shop.setup_shop(conn, name="Test Shop", state_code="36")
    return conn
