# Windows daily entry: refresh token, check existing records, wait, then submit.
$ErrorActionPreference = 'Stop'
$Dir = $PSScriptRoot
Set-Location $Dir

$python = Get-Command python -ErrorAction SilentlyContinue
$pyPrefix = @()
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
    $pyPrefix = @('-3')
}
if (-not $python) { throw 'Python 3 was not found' }
$pyExe = $python.Source

Start-Transcript -Path (Join-Path $Dir ("daily_{0}.log" -f (Get-Date -Format yyyyMMdd))) -Append
try {
    $remaining = & $pyExe @pyPrefix check_status.py remaining
    if ($LASTEXITCODE -ne 0) { throw 'Could not read token expiry' }
    $remaining = [int]$remaining
    if ($remaining -lt 7200) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Dir 'refresh.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Token refresh failed' }
        $remaining = & $pyExe @pyPrefix check_status.py remaining
        if ($LASTEXITCODE -ne 0) { throw 'Could not read refreshed token expiry' }
        $remaining = [int]$remaining
    }
    if ($remaining -lt 7200) { throw 'Token has less than two hours remaining' }

    $done = & $pyExe @pyPrefix check_status.py dedup
    if ($LASTEXITCODE -ne 0) { throw 'Could not query existing records' }
    if ($done -eq 'YES') {
        Write-Host 'A qualifying record already exists today; skipping.'
    } elseif ($done -ne 'NO') {
        throw 'Cannot determine whether a qualifying record already exists'
    } else {
        $delay = Get-Random -Minimum 60 -Maximum 2160
        Write-Host "Waiting $delay seconds before submission."
        Start-Sleep -Seconds $delay
        $remaining = & $pyExe @pyPrefix check_status.py remaining
        if ($LASTEXITCODE -ne 0 -or [int]$remaining -lt 1500) {
            throw 'Token validity is too short for submission'
        }
        & $pyExe @pyPrefix -u forge2.py
        if ($LASTEXITCODE -ne 0) { throw "Submission failed with exit code $LASTEXITCODE" }
    }
} finally {
    Stop-Transcript
}
