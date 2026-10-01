"""Offline license check. One key = one PC. The vendor signs {machine, buyer, expires, plan}
with a private Ed25519 key; the app verifies with the embedded public key. No server needed."""
import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from retail import clock, guard


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def machine_id_from_guid(guid: str) -> str:
    digest = hashlib.sha256(guid.strip().lower().encode("utf-8")).hexdigest().upper()
    return "RTL-" + "-".join(digest[i:i + 4] for i in range(0, 16, 4))


def read_machine_guid() -> str:
    import winreg  # Windows only, imported lazily

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        return winreg.QueryValueEx(key, "MachineGuid")[0]


def get_machine_id() -> str:
    return machine_id_from_guid(read_machine_guid())


@dataclass(frozen=True)
class LicenseState:
    status: str  # 'active' | 'expired' | 'invalid'
    buyer: str = ""
    expires: str = ""
    plan: str = ""
    reason: str = ""

    @property
    def read_only(self) -> bool:
        return self.status != "active"


def _invalid(reason: str) -> LicenseState:
    return LicenseState("invalid", reason=reason)


def verify_key(key: str, machine_id: str, public_key: bytes, today: date) -> LicenseState:
    try:
        payload_b64, signature_b64 = key.strip().split(".")
        payload = b64d(payload_b64)
        Ed25519PublicKey.from_public_bytes(public_key).verify(b64d(signature_b64), payload)
        data = json.loads(payload)
        expires = date.fromisoformat(data["expires"])
    except (ValueError, KeyError, TypeError, AttributeError, InvalidSignature):
        return _invalid("The license key is not valid")
    if data.get("machine") != machine_id:
        return _invalid("This key was issued for a different PC")
    state = "active" if today <= expires else "expired"
    return LicenseState(state, buyer=str(data.get("buyer", "")), expires=data["expires"],
                        plan=str(data.get("plan", "")))


def save_key(path, key: str) -> None:
    Path(path).write_text(key.strip(), encoding="utf-8")


def load_key(path) -> str | None:
    path = Path(path)
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def apply_license(path, public_key: bytes, machine_id: str, today: date | None = None) -> LicenseState:
    """Check the saved key and switch the app to read-only unless the license is active."""
    try:
        key = load_key(path)
    except (OSError, ValueError):
        key = None  # unreadable or corrupt key file counts as no usable key
    state = (
        LicenseState("invalid", reason="No license key has been entered")
        if not key
        else verify_key(key, machine_id, public_key, today or clock.today())
    )
    guard.set_read_only(state.read_only)
    return state
