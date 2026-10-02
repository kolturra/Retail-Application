import re
from pathlib import Path

import retail
import retail_ui

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "packaging" / "retail_app.spec").read_text(encoding="utf-8")
ISS = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
BUILD = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_vendor_only_code_and_keys_are_not_packaged():
    assert 'excludes=["tools", "tests", "pytest"]' in SPEC
    for text in (SPEC, ISS):
        lowered = text.lower()
        assert "private.key" not in lowered
        assert "\\keys" not in lowered and "/keys" not in lowered
    assert not [l for l in ISS.splitlines() if l.startswith("Source:") and "tools" in l.lower()]


def test_spec_and_installer_package_only_the_built_app_and_runtime_data():
    sources = [l for l in ISS.splitlines() if l.startswith("Source:")]
    assert sources and all("..\\dist\\RetailApp\\" in l for l in sources)
    data_lines = [l for l in SPEC.splitlines() if l.strip().startswith("(os.path.join(ROOT")]
    assert data_lines and all('"retail"' in l for l in data_lines)
    for text in (SPEC, ISS):
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(("#", ";")))
        for banned in ("keys", "tools", "tests", ".superpowers", "docs"):
            if text is SPEC and banned in ("tools", "tests"):
                continue  # named only in excludes=[...], which is pinned above
            assert banned not in code.lower(), banned


def test_the_spec_bundles_the_data_files_the_app_reads_at_runtime():
    for pattern in ("retail/migrations", "retail/locales", "retail/segments"):
        assert pattern in SPEC
    assert "__main__.py" in SPEC and "console=False" in SPEC


def test_installer_version_matches_the_package_version():
    match = re.search(r'#define\s+AppVersion\s+"([^"]+)"', ISS)
    assert match and match.group(1) == retail.__version__


def test_all_versions_agree():
    match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT, re.M)
    assert match and match.group(1) == retail.__version__
    assert retail_ui.__version__ == retail.__version__
    assert f"RetailApp-Setup-{retail.__version__}.exe" in README


def test_installer_leaves_the_users_data_alone():
    assert "never" in ISS.lower() and "%LOCALAPPDATA%\\RetailApp" in ISS
    assert "[UninstallDelete]" not in ISS and "[InstallDelete]" not in ISS
    assert not [l for l in ISS.splitlines() if "{localappdata}" in l.lower() and not l.startswith(";")]


def test_the_build_script_runs_tests_and_the_selftest_before_the_installer():
    order = [BUILD.index(marker) for marker in ("pytest", "PyInstaller", "--selftest", "iscc")]
    assert order == sorted(order)
    assert "ExitCode" in BUILD


def test_readme_documents_the_unsigned_installer():
    assert "not code-signed" in README and "SmartScreen" in README


def test_the_module_entry_point_exists():
    assert (ROOT / "retail_ui" / "__main__.py").read_text(encoding="utf-8").strip().endswith("raise SystemExit(main())")
