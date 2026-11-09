@echo off
chcp 65001 >nul
title Hanoi IT Job Radar Bot Manager

:menu
cls
echo ==========================================================
echo        🤖 HANOI IT JOB RADAR - TRÌNH ĐIỀU KHIỂN (WINDOWS)
echo ==========================================================
echo.
echo   [1] 🚀 Chạy bot ngay
echo   [2] 🛑 Tắt toàn bộ tiến trình bot và Chrome
echo   [3] 📄 Xem 30 dòng log gần nhất
echo   [0] 🚪 Thoát
echo.
echo ==========================================================
set /p choice="👉 Nhập lựa chọn của bạn [0-3]: "

if "%choice%"=="1" goto :check_setup
if "%choice%"=="2" goto :stop_bot
if "%choice%"=="3" goto :view_log
if "%choice%"=="0" exit /b 0
goto :menu

:check_setup
if exist venv\Scripts\python.exe goto :start_bot

echo.
echo ==========================================================
echo   LẦN ĐẦU CHẠY: ĐANG KHỞI TẠO MÔI TRƯỜNG VIRTUALENV
echo ==========================================================
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Không tìm thấy Python trên máy! Vui lòng cài Python trước.
    pause
    goto :menu
)

echo [1/3] Đang tạo môi trường ảo (venv)...
python -m venv venv
echo [2/3] Đang cài đặt thư viện phụ thuộc...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\pip.exe install -r requirements.txt
echo [3/3] Đang tải Chromium cho Playwright...
venv\Scripts\playwright.exe install chromium
if not exist .env copy .env.example .env

:start_bot
echo.
echo 🚀 Đang khởi chạy bot (Nhấn Ctrl + C để dừng)...
venv\Scripts\python.exe main.py
pause
goto :menu

:stop_bot
echo.
echo 🛑 Đang tắt toàn bộ tiến trình Python và Chromium...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM chrome.exe >nul 2>&1
echo ✅ Đã dừng toàn bộ bot và giải phóng tài nguyên!
pause
goto :menu

:view_log
echo.
echo 📄 30 dòng log gần nhất:
echo ----------------------------------------------------------
if exist logs\app.log (
    powershell -Command "Get-Content logs\app.log -Tail 30"
) else (
    echo Chưa có file logs\app.log
)
echo ----------------------------------------------------------
pause
goto :menu
