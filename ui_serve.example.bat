@echo off
rem CERBERUS UI — arranque local. Copia este fichero a ui_serve.bat si quieres.
rem Bind 127.0.0.1, token de sesion en runs\.ui_token. No exponer fuera de localhost.
cd /d "%~dp0"
.venv\Scripts\python.exe scripts\ui_serve.py %*
