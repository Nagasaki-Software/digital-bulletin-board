@echo off
cd /d "%~dp0"

if "%~1"=="openbrowser" goto :openbrowser

if not exist ".venv\Scripts\python.exe" (
    echo [エラー] .venv が見つかりません。
    echo 先に「初回セットアップ.bat」をダブルクリックしてください。
    pause
    exit /b 1
)
echo デジタル掲示板を起動します。この黒い窓は閉じないでください。
echo 終了するときは、この窓で Ctrl + C を押してください。
echo.
start /min "" "%~f0" openbrowser
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:openbrowser
rem サーバーが応答するまで最大60秒（1秒ごと）待つ。応答しなくてもブラウザは開く
rem 開く先のポートは server_port.txt から毎回読む（ポートが使用中だと別の番号で起動するため）。ファイルが無いときは5100
rem /api/health の返事に digital-bulletin-board が入っていたら、このアプリが起動したと判断する
set /a TRIES=0
:waitloop
set "PORT=5100"
if exist "server_port.txt" set /p PORT=<"server_port.txt"
echo %PORT%|findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "PORT=5100"
curl.exe -s --max-time 2 http://localhost:%PORT%/api/health | findstr /c:"digital-bulletin-board" >nul
if not errorlevel 1 goto :ready
set /a TRIES+=1
if %TRIES% geq 60 goto :ready
timeout /t 1 /nobreak >nul
goto :waitloop

:ready
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" goto :fallback
start "" "%EDGE%" http://localhost:%PORT%
exit /b 0

:fallback
start "" http://localhost:%PORT%
exit /b 0
