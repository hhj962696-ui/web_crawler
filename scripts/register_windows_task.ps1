# 註冊 Windows 工作排程：每日 08:10 執行單次爬蟲（需先建立 venv 並安裝依賴）
# 以系統管理員身分執行：powershell -ExecutionPolicy Bypass -File scripts\register_windows_task.ps1

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$Script = Join-Path $ProjectRoot "scripts\run_scrape_once.py"
$TaskName = "GovProcurementScraperDaily"

if (-not (Test-Path $PythonExe)) {
    Write-Error "找不到 $PythonExe，請先建立虛擬環境並安裝 requirements.txt"
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$Script`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "08:10"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "已註冊工作排程：$TaskName（每日 08:10）"
Write-Host "若要 Web UI + 內建排程常駐，請改執行 scripts\start_app.bat"
