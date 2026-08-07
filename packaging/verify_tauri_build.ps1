# JARVIS OS -- Windows packaging verification (M22 Task Group E)
#
# STATUS: written and reasoned through, NOT yet run against a real
# build -- there is no Rust toolchain on the machine this was written
# on, so `npm run tauri build` has never produced an installer for this
# script to check. See MILESTONE_REPORT.md's Task Group C and Task
# Group E entries for the full honest status.
#
# What this does: turns as much of the Build Verification Tasks list
# (MILESTONE_REPORT.md, Task Group C S:9) into mechanical pass/fail
# checks as a build's own output can prove without installing it --
# the installer artifact exists, its version metadata matches this
# project's single source of truth, its product/publisher fields are
# real values rather than a template's defaults, and the icon actually
# shipped is not the placeholder Task Group C found and Task Group E
# replaced.
#
# What this deliberately does NOT do: install the application, click
# through the wizard, or confirm the Desktop/Start Menu shortcuts exist.
# Those need a real install, and a verification script that runs on a
# build machine should not perform one as a side effect -- that step
# stays manual, tracked as its own row in the Build Verification Tasks
# table this script does not replace, only shrinks.
#
# Usage (from a real Windows machine with the Rust toolchain, after
# `npm run tauri build` has run, from the `frontend/` directory):
#   ..\packaging\verify_tauri_build.ps1
#
# The default bundle path below is Tauri v2's standard convention
# (<crate>/target/<profile>/bundle/<format>/). It has not been
# confirmed against a real build from this project specifically --
# override -BundleDir if the first real run finds it wrong, and please
# correct this default for whoever runs it next.

param(
    [string]$BundleDir = "src-tauri/target/release/bundle/nsis",
    [string]$RepoRoot = ".."
)

$ErrorActionPreference = "Stop"
$script:failures = @()

function Check {
    param([string]$Name, [bool]$Condition, [string]$Detail)
    if ($Condition) {
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Name -- $Detail" -ForegroundColor Red
        $script:failures += $Name
    }
}

Write-Host "== JARVIS OS Tauri/NSIS build verification ==" -ForegroundColor Cyan
Write-Host "Bundle directory: $BundleDir"
Write-Host ""

# 1. The installer artifact was actually produced.
#    (Build Verification Tasks #1-2: build the installer, confirm it
#    builds successfully.)
$installers = @()
if (Test-Path $BundleDir) {
    $installers = @(Get-ChildItem -Path $BundleDir -Filter "*.exe" -ErrorAction SilentlyContinue)
}
Check "NSIS installer produced" ($installers.Count -eq 1) `
    "expected exactly one .exe in '$BundleDir', found $($installers.Count). Run 'npm run tauri build' from frontend/ first, or pass -BundleDir if Tauri wrote it somewhere else."

if ($installers.Count -eq 1) {
    $installer = $installers[0]
    $versionInfo = $installer.VersionInfo

    # 2. Version metadata matches this project's single source of truth.
    #    (Build Verification Task #6: installer metadata.)
    $pyprojectPath = Join-Path $RepoRoot "pyproject.toml"
    $expectedVersion = $null
    if (Test-Path $pyprojectPath) {
        $match = Select-String -Path $pyprojectPath -Pattern '^version = "([^"]+)"' | Select-Object -First 1
        if ($match) { $expectedVersion = $match.Matches[0].Groups[1].Value }
    }
    if ($expectedVersion) {
        Check "Installer version matches pyproject.toml ($expectedVersion)" `
            ($versionInfo.ProductVersion -like "$expectedVersion*") `
            "installer reports ProductVersion '$($versionInfo.ProductVersion)'"
    } else {
        Write-Host "[SKIP] Installer version check -- could not read pyproject.toml at '$pyprojectPath'" -ForegroundColor Yellow
    }

    # 3. Product/publisher metadata is real, not a tauri.conf.json
    #    template default. (Build Verification Task #6.)
    Check "Product name is 'JARVIS OS'" ($versionInfo.ProductName -eq "JARVIS OS") `
        "found '$($versionInfo.ProductName)'"
    Check "Publisher is set" (-not [string]::IsNullOrWhiteSpace($versionInfo.CompanyName)) `
        "CompanyName is empty"

    Write-Host ""
    Write-Host "Installer: $($installer.FullName)"
    Write-Host ("Size: {0:N1} MB" -f ($installer.Length / 1MB))
} else {
    Write-Host ""
    Write-Host "Skipping version/metadata checks -- no installer to inspect." -ForegroundColor Yellow
}

# 4. The application icon actually shipped is not Tauri's placeholder.
#    A repo-state check, not a build-output check, included here
#    because it is exactly the class of regression that "the file
#    exists" would miss and only opening or measuring it catches --
#    the same lesson Task Group C's own audit found the hard way.
#
#    A negative match against the placeholder's own known size, not a
#    magnitude heuristic ("small enough to be real"): that heuristic
#    was tried first and immediately broke on its own real icon, once
#    Task Group E's hybrid .ico (small frames from the simplified
#    variant, large frames from the approved master logo) turned out
#    *larger* than the placeholder it replaced. This project's actual
#    icon size is expected to keep changing as the artwork does; the
#    placeholder's size is the one number that will not.
Write-Host ""
$iconPath = Join-Path $RepoRoot "frontend/src-tauri/icons/icon.ico"
if (Test-Path $iconPath) {
    $iconBytes = (Get-Item $iconPath).Length
    # Tauri's placeholder icon.ico was exactly 37,710 bytes in this
    # project's own git history before Task Group E replaced it.
    $placeholderSize = 37710
    Check "Application icon is not Tauri's default placeholder" `
        ($iconBytes -ne $placeholderSize) `
        "icon.ico is exactly $iconBytes bytes, matching the known placeholder's size"
} else {
    Write-Host "[SKIP] Icon check -- '$iconPath' not found" -ForegroundColor Yellow
}

Write-Host ""
if ($script:failures.Count -eq 0) {
    Write-Host "All mechanical checks passed." -ForegroundColor Green
    Write-Host "Still manual: shortcuts, uninstall entry, Launch/Open Folder, the" -ForegroundColor Yellow
    Write-Host "provisioning bridge end to end -- see the Build Verification Tasks" -ForegroundColor Yellow
    Write-Host "table in MILESTONE_REPORT.md." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "$($script:failures.Count) check(s) failed: $($script:failures -join ', ')" -ForegroundColor Red
    exit 1
}
