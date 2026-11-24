$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$Spec = Join-Path $ProjectRoot "TF3 Early Start Manager.spec"

Write-Host ""
Write-Host "=========================================="
Write-Host " TF3 Early Start Manager - Release Build"
Write-Host "=========================================="
Write-Host ""

# Look for a virtual environment in common locations.
$PythonCandidates = @(
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $ProjectRoot -Parent) ".venv\Scripts\python.exe")
)

$Python = $PythonCandidates |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $Python) {
    throw "No .venv Python interpreter found."
}

if (-not (Test-Path $Spec)) {
    throw "PyInstaller spec not found: $Spec"
}

Write-Host "Project:"
Write-Host "  $ProjectRoot"

Write-Host ""
Write-Host "Python:"
Write-Host "  $Python"

Write-Host ""
Write-Host "Cleaning previous build..."

Remove-Item (Join-Path $ProjectRoot "build") `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Remove-Item (Join-Path $ProjectRoot "dist") `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

Write-Host "Building..."

Push-Location $ProjectRoot

try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        $Spec

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$ReleaseDir = Join-Path $ProjectRoot "dist\TF3 Early Start Manager"
$Exe = Join-Path $ReleaseDir "TF3 Early Start Manager.exe"

if (-not (Test-Path $Exe)) {
    throw "Build finished, but executable was not found: $Exe"
}

Write-Host ""
Write-Host "=========================================="
Write-Host " BUILD SUCCESSFUL"
Write-Host "=========================================="
Write-Host ""
Write-Host "Release:"
Write-Host "  $ReleaseDir"
Write-Host ""
Write-Host "Executable:"
Write-Host "  $Exe"
Write-Host ""