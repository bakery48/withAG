@echo off
rem withAG: ファイアウォールで待ち受けポートの受信を許可する
rem 使い方: ダブルクリック (既定 8765) / 別ポートなら allow_firewall.bat 9000
chcp 65001 >nul
setlocal

set PORT=%~1
if "%PORT%"=="" set PORT=8765

rem 管理者権限が無ければ、UAC を出して自分自身を開き直す
net session >nul 2>&1
if errorlevel 1 (
  echo [withAG] 管理者権限が必要です。確認ダイアログで「はい」を押してください。
  powershell -NoProfile -Command "Start-Process -FilePath %~f0 -ArgumentList %PORT% -Verb RunAs"
  goto :eof
)

rem 同名の規則が残っていると重複するので一度消してから作る
netsh advfirewall firewall delete rule name="withAG" >nul 2>&1
netsh advfirewall firewall add rule name="withAG" dir=in action=allow protocol=TCP localport=%PORT% profile=private,domain
if errorlevel 1 (
  echo [withAG] 規則の追加に失敗しました。
  pause
  goto :eof
)

echo.
echo [withAG] ポート %PORT% の受信を許可しました（プライベート / ドメイン ネットワーク）。
echo [withAG] スマホから開けるか試してください。
pause
