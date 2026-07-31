# JARVIS OS -- Windows build script (Milestone 5.5 packaging foundation)
#
# STATUS: written and reasoned through, NOT yet run on real Windows
# hardware -- there was no Windows build environment available to
# actually execute this and verify the resulting .exe. See
# docs/PACKAGING.md for the full honest status.
#
# Usage (from a real Windows machine, PowerShell, repo root):
#   .\packaging\build_windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "== JARVIS OS Windows build ==" -ForegroundColor Cyan

# 1. Editable install with dev extras (pulls in PyInstaller).
Write-Host "-- Installing dependencies --"
pip install -e ".[dev]"

# 2. Playwright needs its own browser binaries downloaded separately --
#    PyInstaller bundles the Python package, not these.
Write-Host "-- Installing Playwright browser binaries --"
python -m playwright install chromium

# 3. Clean previous build artifacts.
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }

# 4. Run PyInstaller against the spec file.
Write-Host "-- Running PyInstaller --"
pyinstaller packaging/jarvis.spec --clean --noconfirm

# 5. Code signing (RC1, section 3) -- optional, gracefully skipped for
#    development builds. Configure via environment variables:
#      JARVIS_SIGN_CERT_PATH   -- path to a .pfx/.p12 code-signing cert
#      JARVIS_SIGN_CERT_PASSWORD
#      JARVIS_SIGN_TIMESTAMP_URL  (defaults to DigiCert's RFC 3161 server)
#    No cert configured -> unsigned build, clearly flagged, not a
#    silent failure. This script never fails the whole build just
#    because signing wasn't set up.
$certPath = $env:JARVIS_SIGN_CERT_PATH
if ($certPath -and (Test-Path $certPath)) {
    Write-Host "-- Signing executable --"
    $timestampUrl = if ($env:JARVIS_SIGN_TIMESTAMP_URL) { $env:JARVIS_SIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }
    signtool sign /f "$certPath" /p "$env:JARVIS_SIGN_CERT_PASSWORD" /tr "$timestampUrl" /td sha256 /fd sha256 "dist\JarvisOS\JarvisOS.exe"
    Write-Host "Executable signed." -ForegroundColor Green
} else {
    Write-Host "-- Skipping code signing (no JARVIS_SIGN_CERT_PATH configured) --" -ForegroundColor Yellow
    Write-Host "   This is expected for local/development builds. A release" -ForegroundColor Yellow
    Write-Host "   build should be signed -- see docs/PACKAGING.md." -ForegroundColor Yellow
}

Write-Host "== Build complete: dist/JarvisOS/JarvisOS.exe ==" -ForegroundColor Green
Write-Host "NOTE: wrapping this in a real installer (packaging/jarvis_installer.iss," -ForegroundColor Yellow
Write-Host "  requires Inno Setup) and, if not already done above, code-signing" -ForegroundColor Yellow
Write-Host "  are tracked as open work -- see docs/PACKAGING.md." -ForegroundColor Yellow
