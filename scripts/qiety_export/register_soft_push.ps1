# 注册 qiety soft_snapshots 每日推送任务（11:00 + 23:00）

$ErrorActionPreference = 'Stop'
$TaskName = 'qqsj_soft_push'
$bat = 'D:\cl\qqsj_v2\push_soft_snapshots.bat'

if (-not (Test-Path $bat)) { throw "bat 不存在: $bat" }

# 已存在先删
$old = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($old) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }

$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$bat`"" `
    -WorkingDirectory 'D:\cl\qqsj_v2'
$t1 = New-ScheduledTaskTrigger -Daily -At '11:00'
$t2 = New-ScheduledTaskTrigger -Daily -At '23:00'
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($t1, $t2) `
    -Settings $settings -Description 'qiety 赛前赔率导出并推送 GitHub hit-system-exports (每天2次)' | Out-Null

$t = Get-ScheduledTask -TaskName $TaskName
$i = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host ("registered: {0}  state={1}" -f $t.TaskName, $t.State)
Write-Host ("triggers: {0}" -f (($t.Triggers | ForEach-Object { $_.StartBoundary }) -join ', '))
Write-Host ("next run: {0}" -f $i.NextRunTime)
