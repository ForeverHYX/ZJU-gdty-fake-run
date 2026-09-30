# Windows token refresh: temporarily proxy WeChat, then restore the user's proxy.
$ErrorActionPreference = 'Stop'
$Dir = $PSScriptRoot
$reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
$previous = Get-ItemProperty -Path $reg
$hadServer = $previous.PSObject.Properties.Name -contains 'ProxyServer'
$hadEnable = $previous.PSObject.Properties.Name -contains 'ProxyEnable'
$mitmdump = (Get-Command mitmdump -ErrorAction Stop).Source
$process = $null
$proxyChanged = $false
$captured = $false

try {
    Remove-Item -LiteralPath (Join-Path $Dir 'token.fresh') -ErrorAction SilentlyContinue
    $process = Start-Process -FilePath $mitmdump -WindowStyle Hidden -PassThru -ArgumentList @(
        '-s', (Join-Path $Dir 'token_grab.py'),
        '--listen-port', '8080',
        '--set', "confdir=$Dir\mitmca",
        '--set', 'block_global=false',
        '--allow-hosts', 'codoon|igofit'
    ) -RedirectStandardOutput (Join-Path $Dir 'mitm_refresh.log') -RedirectStandardError (Join-Path $Dir 'mitm_refresh.err.log')
    Start-Sleep -Seconds 4
    if ($process.HasExited) { throw 'mitmdump failed to start; see mitm_refresh.err.log' }

    $proxyChanged = $true
    Set-ItemProperty -Path $reg -Name ProxyServer -Value '127.0.0.1:8080'
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
    Write-Host 'Proxy is active. Open the enterprise Codoon mini program in WeChat.'
    for ($i = 0; $i -lt 120; $i++) {
        if (Test-Path (Join-Path $Dir 'token.fresh')) { $captured = $true; break }
        if ($process.HasExited) { throw 'mitmdump exited before a token was captured' }
        Start-Sleep -Seconds 1
    }
} finally {
    try {
        if ($proxyChanged) {
            if ($hadServer) { Set-ItemProperty -Path $reg -Name ProxyServer -Value $previous.ProxyServer }
            else { Remove-ItemProperty -Path $reg -Name ProxyServer -ErrorAction SilentlyContinue }
            if ($hadEnable) { Set-ItemProperty -Path $reg -Name ProxyEnable -Value $previous.ProxyEnable }
            else { Remove-ItemProperty -Path $reg -Name ProxyEnable -ErrorAction SilentlyContinue }
        }
    } finally {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        if ($captured) {
            Remove-Item -LiteralPath (Join-Path $Dir 'token.fresh') -ErrorAction SilentlyContinue
        }
    }
}

if (-not $captured) { throw 'No fresh token was captured within 120 seconds' }
Write-Host 'Token captured and previous proxy settings restored.'
