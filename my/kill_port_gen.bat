@echo off
chcp 65001 > nul
echo Port 7862 を使用しているプロセスを検索しています...

rem netstatの結果から指定ポートで待機中(LISTENING)のPIDを取得してkillする
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :7862 ^| findstr LISTENING') do (
    echo PID: %%a を強制終了します。
    taskkill /F /PID %%a
)

echo.
echo 処理が完了しました。
pause
