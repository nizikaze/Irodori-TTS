@echo off
chcp 65001 > nul

rem 引数からポート番号を取得
set PORT=%1

rem 引数が指定されていない場合は対話式で入力を求める
if "%PORT%"=="" (
    set /p PORT="強制終了したいポート番号を入力してください: "
)

rem それでも空の場合は終了
if "%PORT%"=="" (
    echo ポート番号が指定されませんでした。処理を中止します。
    pause
    exit /b
)

echo.
echo Port %PORT% を使用しているプロセスを検索しています...

set FOUND=0
rem netstatの結果から指定ポートで待機中(LISTENING)のPIDを取得してkillする
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
    echo PID: %%a を強制終了します。
    taskkill /F /PID %%a
    set FOUND=1
)

if "%FOUND%"=="0" (
    echo Port %PORT% で待機中(LISTENING)のプロセスは見つかりませんでした。
)

echo.
echo 処理が完了しました。
pause
