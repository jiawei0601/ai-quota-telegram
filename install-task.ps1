# 註冊 Windows 工作排程「AiQuotaReport」：每日 08:00 起每 3 小時查一次，持續 14 小時（08/11/14/17/20）。
# 以隱藏視窗執行，不會跳黑窗。錯過的時段會在開機／登入後補跑一次。
# 用法（PowerShell）： .\install-task.ps1            # 註冊或更新
#                    .\install-task.ps1 -Remove    # 移除
#                    .\install-task.ps1 -StartAt 09:00 -IntervalHours 2 -DurationHours 12
param(
    [string]$StartAt = "08:00",
    [int]$IntervalHours = 3,
    [int]$DurationHours = 14,
    [string]$TaskName = "AiQuotaReport",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "已移除排程 $TaskName"
    exit 0
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $here "run-hidden.vbs"
Get-Command python -ErrorAction Stop | Out-Null   # 確認 PATH 找得到 python

# 工作目錄設為本目錄，命令列不需再包引號（wscript 不支援巢狀引號跳脫）
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument ('"' + $vbs + '" "python ai_quota_report.py"') -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Daily -At $StartAt
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $StartAt `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Hours $DurationHours)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "已註冊排程 $TaskName：每日 $StartAt 起每 $IntervalHours 小時、持續 $DurationHours 小時"
Write-Host "下次執行：" (Get-ScheduledTaskInfo $TaskName).NextRunTime
