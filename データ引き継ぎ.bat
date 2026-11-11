@echo off
cd /d "%~dp0"
rem 古い版のフォルダから、入力した内容・設定・PDF などを、このフォルダへ写す。古いフォルダは変えない
rem 古いフォルダをこの bat へドラッグしても、実行してから場所を入れてもよい

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
    where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
    echo [エラー] Python が見つかりません。
    echo https://www.python.org/ から Python 3.10 以降をインストールしてください。
    pause
    exit /b 1
)

if "%~1"=="" (
    %PYCMD% -I migrate.py
) else (
    %PYCMD% -I migrate.py "%~1"
)
pause
