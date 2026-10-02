"""Read-only switch. Business writes are decorated with @writes so an expired
license blocks them while reads and exports keep working."""
import functools


class ReadOnlyError(RuntimeError):
    """Raised when a write is attempted while the license is expired."""


_read_only = False


def set_read_only(value: bool) -> None:
    global _read_only
    _read_only = value


def is_read_only() -> bool:
    return _read_only


def writes(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if _read_only:
            raise ReadOnlyError("License expired: shop data is read-only.")
        return func(*args, **kwargs)

    return wrapper
