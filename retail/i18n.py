"""Screen-language catalogue: English (default), Hindi, Telugu. Keys are stable ids.
tests/test_i18n.py fails if hi/te are missing a key, so English cannot leak into translated screens."""
import json
from pathlib import Path

LANGUAGES = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు"}
DEFAULT_LANGUAGE = "en"
_DIR = Path(__file__).parent / "locales"
_catalogues: dict[str, dict[str, str]] = {}
_current = DEFAULT_LANGUAGE


def _load(code: str) -> dict[str, str]:
    if code not in _catalogues:
        _catalogues[code] = json.loads((_DIR / f"{code}.json").read_text(encoding="utf-8"))
    return _catalogues[code]


def set_language(code: str) -> None:
    global _current
    if code not in LANGUAGES:
        raise ValueError(f"Unsupported language {code!r}")
    _current = code


def get_language() -> str:
    return _current


def tr(key: str, **values) -> str:
    text = _load(_current).get(key)
    if text is None:
        text = _load(DEFAULT_LANGUAGE)[key]  # KeyError here means the key is undefined everywhere
    return text.format(**values) if values else text
