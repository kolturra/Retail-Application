import json

import pytest

from tools import locale_add


@pytest.fixture
def locales(tmp_path):
    for code, text in (("en", "Total"), ("hi", "कुल"), ("te", "మొత్తం")):
        (tmp_path / f"{code}.json").write_text(json.dumps({"bill.total": text}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def load(locales, code):
    return json.loads((locales / f"{code}.json").read_text(encoding="utf-8"))


def test_merge_adds_keys_to_all_three_files(locales):
    added = locale_add.merge({"a.b": {"en": "Hello", "hi": "नमस्ते", "te": "హలో"}}, locales)
    assert added == ["a.b"]
    assert load(locales, "hi")["a.b"] == "नमस्ते" and load(locales, "te")["bill.total"] == "మొత్తం"
    assert (locales / "en.json").read_text(encoding="utf-8").endswith("}\n")


def test_merge_is_idempotent_for_identical_values(locales):
    snippet = {"a.b": {"en": "Hello", "hi": "नमस्ते", "te": "హలో"}}
    locale_add.merge(snippet, locales)
    assert locale_add.merge(snippet, locales) == []


@pytest.mark.parametrize("entry", [
    {"en": "x", "hi": "y"},                                  # missing te
    {"en": "x", "hi": "", "te": "z"},                        # empty
    {"en": "{n} items", "hi": "वस्तुएँ", "te": "{n} వస్తువులు"},  # placeholder mismatch
    {"en": "x", "hi": "y", "te": "z", "fr": "w"},            # unknown language
])
def test_merge_rejects_bad_entries_and_writes_nothing(locales, entry):
    before = {c: (locales / f"{c}.json").read_text(encoding="utf-8") for c in ("en", "hi", "te")}
    with pytest.raises(ValueError):
        locale_add.merge({"k": entry}, locales)
    assert before == {c: (locales / f"{c}.json").read_text(encoding="utf-8") for c in ("en", "hi", "te")}


def test_merge_rejects_changing_an_existing_key(locales):
    with pytest.raises(ValueError):
        locale_add.merge({"bill.total": {"en": "Sum", "hi": "योग", "te": "మొత్తం"}}, locales)


def test_cli_reads_a_snippet_file(locales, tmp_path, capsys):
    snippet = tmp_path / "s.json"
    snippet.write_text(json.dumps({"x.y": {"en": "A", "hi": "ए", "te": "ఎ"}}, ensure_ascii=False), encoding="utf-8")
    assert locale_add.main([str(snippet), "--locales", str(locales)]) == 0
    assert "x.y" in capsys.readouterr().out
    assert locale_add.main([str(tmp_path / "missing.json"), "--locales", str(locales)]) == 2
