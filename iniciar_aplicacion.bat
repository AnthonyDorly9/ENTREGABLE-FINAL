@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Iniciando Trazo, el lector de digitos manuscritos...
echo Cuando diga "Running on http://127.0.0.1:5000" la aplicacion esta lista.
start "" "http://127.0.0.1:5000"
python app.py
pause
