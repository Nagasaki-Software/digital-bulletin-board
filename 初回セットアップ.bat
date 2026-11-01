@echo off
cd /d "%~dp0"
echo ============================================
echo  デジタル掲示板 初回セットアップ
echo ============================================
echo.

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
    where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
    echo [エラー] Python が見つかりません。
    echo https://www.python.org/ から Python 3.10 以降をインストールしてください。
    echo インストール時は「Add Python to PATH」に必ずチェックを入れてください。
    pause
    exit /b 1
)

echo Python を確認しました。実行環境を作成します...
%PYCMD% -m venv .venv
if errorlevel 1 (
    echo [エラー] 実行環境の作成に失敗しました。
    pause
    exit /b 1
)

echo 必要な部品をインストールします。インターネット接続が必要です...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [エラー] 部品のインストールに失敗しました。
    echo インターネット接続を確認して、もう一度実行してください。
    pause
    exit /b 1
)

echo.
echo ============================================
echo  セットアップが完了しました。
echo  次回からは「起動.bat」をダブルクリックしてください。
echo ============================================
pause
