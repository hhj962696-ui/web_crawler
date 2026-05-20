@echo off
chcp 65001 >nul
cd /d "%~dp0.."

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo.
echo  政府採購爬蟲 - 命令列測試選單
echo  ================================
echo   1  查看狀態
echo   2  測試 Discord
echo   3  執行爬蟲
echo   4  列出最近案件
echo   5  匯出 CSV
echo   0  離開
echo.

set /p choice=請輸入選項:

if "%choice%"=="1" python scripts\cli.py status & goto end
if "%choice%"=="2" python scripts\cli.py test-discord & goto end
if "%choice%"=="3" python scripts\cli.py scrape & goto end
if "%choice%"=="4" python scripts\cli.py list --limit 20 & goto end
if "%choice%"=="5" python scripts\cli.py export -o tenders_export.csv & goto end
if "%choice%"=="0" goto end

echo 無效選項

:end
echo.
pause
