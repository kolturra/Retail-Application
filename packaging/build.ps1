# Builds the app and (when Inno Setup is installed) the installer. Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

& $python -m pytest -q -W error::ResourceWarning
if ($LASTEXITCODE -ne 0) { throw "tests failed - not building" }

& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\retail_app.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# The windowed exe has no console, so wait for it and read its exit code.
$run = Start-Process -FilePath (Join-Path $root "dist\RetailApp\RetailApp.exe") -ArgumentList "--selftest" -Wait -PassThru
if ($run.ExitCode -ne 0) { throw "the built app failed its --selftest (exit code $($run.ExitCode))" }

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if ($iscc) {
    & $iscc.Source (Join-Path $root "packaging\installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer written to dist\installer"
} else {
    Write-Warning "Inno Setup (iscc) is not on the PATH, so no installer was built. Install it from https://jrsoftware.org/isinfo.php and re-run."
}
