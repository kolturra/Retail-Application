import pytest

from retail import guard


@guard.writes
def _write():
    return "written"


def test_writes_pass_when_writable():
    assert _write() == "written"


def test_writes_blocked_when_read_only():
    guard.set_read_only(True)
    with pytest.raises(guard.ReadOnlyError):
        _write()
    assert guard.is_read_only() is True
