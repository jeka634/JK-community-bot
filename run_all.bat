@echo off
REM Запуск backend TON Connect в отдельном окне
start "TON Connect Backend" cmd /k "python ton_connect_backend.py"
REM Запуск Telegram-бота в текущем окне
python main.py 