"""Dev tool: merge new UI strings into the en/hi/te catalogues in one atomic step.

  python -m tools.locale_add snippet.json [--locales retail/locales]

snippet.json: {"some.key": {"en": "...", "hi": "...", "te": "..."}, ...}
"""
import argparse
import json
import string
import sys
from pathlib import Path

LANGS = ("en", "hi", "te")
DEFAULT_DIR = Path("retail/locales")


def _fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def merge(snippet, locales_dir=DEFAULT_DIR):
    locales_dir = Path(locales_dir)
    catalogues = {c: json.loads((locales_dir / f"{c}.json").read_text(encoding="utf-8")) for c in LANGS}
    added = []
    for key, entry in snippet.items():
        if not isinstance(entry, dict) or set(entry) != set(LANGS):
            raise ValueError(f"{key}: needs exactly the languages {LANGS}")
        for code in LANGS:
            if not isinstance(entry[code], str) or not entry[code].strip():
                raise ValueError(f"{key}: empty text for {code}")
        if any(_fields(entry[c]) != _fields(entry["en"]) for c in LANGS):
            raise ValueError(f"{key}: {{placeholders}} differ between languages")
        existing = [catalogues[c].get(key) for c in LANGS]
        if any(v is not None for v in existing):
            if [entry[c] for c in LANGS] != existing:
                raise ValueError(f"{key}: already defined with different text")
            continue
        for code in LANGS:
            catalogues[code][key] = entry[code]
        added.append(key)
    if added:
        for code in LANGS:  # only after every entry validated
            (locales_dir / f"{code}.json").write_text(
                json.dumps(catalogues[code], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


def main(argv=None):
    parser = argparse.ArgumentParser(prog="locale_add")
    parser.add_argument("snippet")
    parser.add_argument("--locales", default=str(DEFAULT_DIR))
    args = parser.parse_args(argv)
    try:
        snippet = json.loads(Path(args.snippet).read_text(encoding="utf-8"))
        added = merge(snippet, args.locales)
    except (OSError, ValueError) as exc:
        print(f"locale_add: {exc}", file=sys.stderr)
        return 2
    print(f"added {len(added)} key(s): {', '.join(added)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
