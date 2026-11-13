@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
echo Web: http://127.0.0.1:18080
"%PYTHON%" web.py
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
popd
exit /b %RESULT%
