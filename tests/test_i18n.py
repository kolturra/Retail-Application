import json
import string
from pathlib import Path

import pytest

from retail import i18n

LOCALES = Path(i18n.__file__).parent / "locales"
SAME_AS_ENGLISH_ALLOWED = {"pay.upi", "tax.gstin", "tax.cgst", "tax.sgst", "tax.igst", "item.hsn", "item.sku", "counter.gst"}


def load(code):
    return json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.fixture(autouse=True)
def _reset_language():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def test_languages_are_english_hindi_telugu():
    assert list(i18n.LANGUAGES) == ["en", "hi", "te"]
    assert i18n.LANGUAGES["hi"] == "हिन्दी" and i18n.LANGUAGES["te"] == "తెలుగు"
    assert i18n.DEFAULT_LANGUAGE == "en"


@pytest.mark.parametrize("code", ["hi", "te"])
def test_translation_is_complete_no_english_leaks(code):
    en, other = load("en"), load(code)
    assert set(other) == set(en), f"{code} keys differ: {set(en) ^ set(other)}"
    for key, text in other.items():
        assert text.strip(), f"{code}:{key} is empty"
        assert fields(text) == fields(en[key]), f"{code}:{key} placeholders differ from English"
        if key not in SAME_AS_ENGLISH_ALLOWED:
            assert text != en[key], f"{code}:{key} is still English"


def test_english_values_are_non_empty():
    assert all(v.strip() for v in load("en").values())


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ValueError(f"duplicate keys: {sorted(dupes)}")
    return dict(pairs)


@pytest.mark.parametrize("code", ["en", "hi", "te"])
def test_locale_files_are_clean_utf8_json(code):
    raw = (LOCALES / f"{code}.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{code}.json has a BOM"
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    assert isinstance(data, dict) and data


def test_tr_switches_language():
    assert i18n.tr("bill.total") == "Total"
    i18n.set_language("hi")
    assert i18n.get_language() == "hi" and i18n.tr("bill.total") == "कुल"
    i18n.set_language("te")
    assert i18n.tr("bill.total") == "మొత్తం"


def test_tr_formats_placeholders():
    assert i18n.tr("stock.low", count=3) == "3 items are low on stock"
    i18n.set_language("hi")
    assert "3" in i18n.tr("stock.low", count=3)


def test_unknown_language_and_key_raise():
    with pytest.raises(ValueError):
        i18n.set_language("fr")
    with pytest.raises(KeyError):
        i18n.tr("does.not.exist")
    assert i18n.get_language() == "en"


def test_missing_translation_falls_back_to_english(monkeypatch):
    i18n.set_language("hi")
    monkeypatch.setitem(i18n._catalogues, "hi", {})   # simulate an incomplete catalogue
    assert i18n.tr("bill.total") == "Total"
