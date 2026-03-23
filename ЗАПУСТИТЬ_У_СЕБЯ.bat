@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Устанавливаю библиотеки...
python -m pip install -q -r requirements.txt
echo.
echo Запускаю приложение. Браузер откроется на http://localhost:8501
echo Закрой это окно — чтобы остановить сервер.
echo.
python -m streamlit run main.py
pause
