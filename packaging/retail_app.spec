# PyInstaller spec — one-folder build of the desktop app.
# Run from the repo root:  .venv\Scripts\python -m PyInstaller --noconfirm --clean packaging\retail_app.spec
# Vendor-only code (tools/) and anything under keys/ are deliberately NOT bundled.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "retail", "migrations", "*.sql"), "retail/migrations"),
    (os.path.join(ROOT, "retail", "locales", "*.json"), "retail/locales"),
    (os.path.join(ROOT, "retail", "segments", "*.json"), "retail/segments"),
]

a = Analysis(
    [os.path.join(ROOT, "retail_ui", "__main__.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["cryptography.hazmat.primitives.asymmetric.ed25519"],
    excludes=["tools", "tests", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="RetailApp", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="RetailApp")
