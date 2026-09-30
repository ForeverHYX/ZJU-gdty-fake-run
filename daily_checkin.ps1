# Windows 版每日自动打卡: 防重 -> 随机延时 -> 必要时续期 -> 提交
# 用法: powershell -ExecutionPolicy Bypass -File daily_checkin.ps1
# 建议任务计划程序每天定时触发(见 README)
$ErrorActionPreference = "Continue"
$Dir = $PSScriptRoot
Set-Location $Dir
Start-Transcript -Path ("daily_{0}.log" -f (Get-Date -Format yyyyMMdd)) -Append
Write-Host "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 自动打卡启动 ====="

# 定位 python
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" }
      elseif (Get-Command py -ErrorAction SilentlyContinue) { "py -3" }
      else { $null }
if (-not $py) { Write-Host "[X] 未找到 python"; Stop-Transcript; exit 1 }

# 0) 防重
$done = Invoke-Expression "$py check_status.py dedup"
if ($done -eq "YES") {
    Write-Host "[=] 今日已有>=3km完成记录, 跳过本次打卡"
    Stop-Transcript; exit 0
}

# 1) 随机延时 60~2159 秒
$delay = Get-Random -Minimum 60 -Maximum 2160
Write-Host "[*] 随机延时 ${delay}s"
Start-Sleep -Seconds $delay

# 2) token 剩余不足1小时则续期
$rem = [int](Invoke-Expression "$py check_status.py remaining")
Write-Host "[*] token 剩余 ${rem}s"
if ($rem -lt 3600) {
    & powershell -ExecutionPolicy Bypass -File "$Dir\refresh.ps1"
    $rem = [int](Invoke-Expression "$py check_status.py remaining")
}
if ($rem -lt 1500) {
    Write-Host "[!] token 剩余不足, 中止。请打开一次企业咕咚小程序后重跑 refresh.ps1"
    Stop-Transcript; exit 2
}

# 3) 提交(约17分钟)
Write-Host "[*] 开始提交 $(Get-Date -Format HH:mm:ss)"
& $py -u forge2.py
Write-Host "===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 完成 ====="
Stop-Transcript
