@echo off
rem withAG 起動スクリプト (Windows)
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [withAG] 仮想環境を作成します...
  py -3 -m venv .venv || python -m venv .venv || goto :err
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
)

if not exist "config.toml" (
  echo [withAG] config.toml がありません。config.example.toml をコピーします。
  copy config.example.toml config.toml >nul
  echo [withAG] config.toml を編集してから、もう一度実行してください。
  notepad config.toml
  goto :eof
)

".venv\Scripts\python.exe" run.py %*
goto :eof

:err
echo [withAG] セットアップに失敗しました。
pause
