# Retail App

Multi-segment retail desktop app (grocery, electronics). See `docs/superpowers/specs/`.

Setup: `python -m venv .venv`, then `.venv/Scripts/python -m pip install -e ".[dev]"`.
Tests: `.venv/Scripts/python -m pytest`.

## Building the installer (Windows)

1. `python -m venv .venv` then `.venv\Scripts\python -m pip install -e ".[dev]"`
2. Install Inno Setup 6.3 or newer, the script uses `x64compatible` and `{autopf}` (https://jrsoftware.org/isinfo.php) and make sure `iscc` is on the PATH.
3. `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`
   — runs the tests, builds `dist\RetailApp\RetailApp.exe`, runs its `--selftest`, then writes
   `dist\installer\RetailApp-Setup-0.1.0.exe` (the version in the file name is `retail.__version__`).

The installer keeps the shop's data in `%LOCALAPPDATA%\RetailApp`; upgrading never touches it.
Nothing from `keys/`, `tools/`, `tests/`, `docs/` or `.superpowers/` is packaged.
Licence keys are issued with `python -m tools.license_issuer` on the vendor's machine (never shipped).
The installer is not code-signed, so Windows SmartScreen will warn on first run until a signing
certificate is added.

The build has not been run yet: the PyInstaller spec and the Inno Setup script are untested, and
`hiddenimports` may need additions once the first build is launched by hand on a clean PC.
`--selftest` never creates a QApplication, so only a manual launch proves the Qt platform plugin is bundled.

## Testing

Automated: `.venv\Scripts\python -m pytest`. Manual release checklist: `docs/manual-test-checklist.md`.

## Known limitations and open follow-ups

- GST slabs `[0, 5, 18, 40]` should be verified with an accountant.
- "Retail App" is a working name, and the vendor phone number is Kuttu's number; confirm both before release.
- CSV export headers are in English.
- `parse_qty` and `parse_rupees` round extra decimal places.
- Hindi and Telugu strings are drafts awaiting native-speaker review; state names are shown in English.
- There is no automatic update; upgrades are done by running a newer installer.
- The installer is unsigned (SmartScreen warning).
- One PC per shop; there is no multi-PC sync.
- Thermal receipts go through the Windows print system with a 297 mm page height; roll feed and cut are unverified on hardware.
