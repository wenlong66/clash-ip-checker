@echo off
setlocal
pushd "%~dp0" || exit /b 1
call .\stop_web.bat
if not errorlevel 1 call .\start_web.bat
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
