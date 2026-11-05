# PowerShell Installer for AGY CFO & Finance Suite (PS 5.1 / PS 7)
$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  AGY CFO & Finance Suite Installer (Plugin + 87 Skills + Skill-Finder)" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

$SrcDir = $PSScriptRoot
python -B (Join-Path $SrcDir "install.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Installation failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
