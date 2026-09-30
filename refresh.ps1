# Windows 版 token 续期: 开代理 -> 等用户打开小程序 -> 抓新 token -> 关代理
# 用法: powershell -ExecutionPolicy Bypass -File refresh.ps1
# 前提: mitmproxy(pip install mitmproxy) + CA 已导入信任(管理员执行一次):
#   certutil -addstore -f ROOT mitmca\mitmproxy-ca-cert.cer
$ErrorActionPreference = "Continue"
$Dir = $PSScriptRoot
Set-Location $Dir

function Enable-Proxy {
    $reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    Set-ItemProperty $reg -Name ProxyServer -Value '127.0.0.1:8080'
    Set-ItemProperty $reg -Name ProxyEnable -Value 1
    netsh winhttp set proxy 127.0.0.1:8080 | Out-Null
}
function Disable-Proxy {
    $reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    Set-ItemProperty $reg -Name ProxyEnable -Value 0
    netsh winhttp reset proxy | Out-Null
}

Remove-Item "$Dir\token.fresh" -ErrorAction SilentlyContinue
Get-Process mitmdump -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1

$p = Start-Process -NoNewWindow -PassThru mitmdump -ArgumentList @(
    '-s', "$Dir\token_grab.py",
    '--listen-port', '8080',
    '--set', "confdir=$Dir\mitmca",
    '--set', 'block_global=false',
    '--allow-hosts', 'codoon|igofit'
) -RedirectStandardOutput "$Dir\mitm_refresh.log" -RedirectStandardError "$Dir\mitm_refresh.err.log"
Start-Sleep 4
if ($p.HasExited) {
    Write-Host "[X] mitmdump 启动失败, 看mitm_refresh.err.log" -ForegroundColor Red
    exit 1
}
Enable-Proxy
Write-Host "[*] 代理已开(只截获 *.codoon.com, 其他直通)。请打开一次【企业咕咚】小程序, 等首页加载..." -ForegroundColor Yellow

$ok = $false
for ($i = 0; $i -lt 120; $i++) {
    if (Test-Path "$Dir\token.fresh") { $ok = $true; break }
    Start-Sleep 1
}
Disable-Proxy
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Get-Process mitmdump -ErrorAction SilentlyContinue | Stop-Process -Force

if ($ok) {
    Remove-Item "$Dir\token.fresh" -ErrorAction SilentlyContinue
    Write-Host "[OK] token 续期完成(25小时有效), 代理已关闭" -ForegroundColor Green
    exit 0
} else {
    Write-Host "[X] 120秒内没抓到登录——确认小程序已打开且旧token已过期(没过期不会重新登录)" -ForegroundColor Red
    exit 1
}
