# NeoAqua preflight for Windows / PowerShell.
#
#   cd E:\neoaqua\neoaqua-v15.4.2\neoaqua
#   powershell -ExecutionPolicy Bypass -File .\preflight.ps1
#
# Mirrors what the Frappe Cloud image build rejects.

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$failed = $false

Write-Host "1/3  merge conflict markers"
$pattern = '^(<{7}|={7}|>{7}|\|{7})( |$)'
$hits = Get-ChildItem -Recurse -File -Include *.py,*.js,*.json,*.md,*.txt,*.toml,*.css,*.html |
        Where-Object { $_.FullName -notmatch '\\(\.git|node_modules|__pycache__)\\' } |
        Select-String -Pattern $pattern
if ($hits) {
    foreach ($h in $hits) {
        Write-Host ("     {0}:{1}  {2}" -f $h.Path, $h.LineNumber, $h.Line) -ForegroundColor Red
    }
    Write-Host "     FOUND - resolve these before pushing" -ForegroundColor Red
    $failed = $true
} else {
    Write-Host "     clean" -ForegroundColor Green
}

Write-Host "2/3  python compiles"
$py = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command python3 -ErrorAction SilentlyContinue)
if (-not $py) {
    Write-Host "     python not on PATH - skipped" -ForegroundColor Yellow
} else {
    & $py.Source -m compileall -q neoaqua | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $py.Source -m compileall -q neoaqua
        Write-Host "     FAILED" -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host "     clean" -ForegroundColor Green
    }
}

Write-Host "3/3  structural guard"
if ($py -and (Test-Path "verify_tree.py")) {
    & $py.Source verify_tree.py
    if ($LASTEXITCODE -ne 0) { $failed = $true }
} else {
    Write-Host "     skipped" -ForegroundColor Yellow
}

Write-Host ""
if ($failed) {
    Write-Host "DO NOT PUSH - fix the above first." -ForegroundColor Red
    exit 1
}
Write-Host "Safe to push." -ForegroundColor Green
exit 0
