@echo off
setlocal
set "WEB_SCRIPT=%~dp0web.py"
rem Hold the process handle so its PID cannot be reused during the ownership check.
powershell.exe -NoProfile -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$listener = Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq 18080 -and $_.LocalAddress -in '127.0.0.1', '0.0.0.0' };" ^
    "if (!$listener) { Write-Host 'Web is not running.'; exit 0 };" ^
    "$target = Get-Process -Id $listener.OwningProcess; $null = $target.Handle;" ^
    "$process = Get-CimInstance Win32_Process -Filter ('ProcessId = {0}' -f $target.Id);" ^
    "$scriptArg = [regex]::Escape([char]34 + $env:WEB_SCRIPT + [char]34);" ^
    "if ($process.Name -ne 'python.exe' -or $process.CommandLine -notmatch ('^(?:\x22[^\x22]+\x22|\S+)\s+' + $scriptArg + '\s*$')) { throw 'Port 18080 is not owned by this launcher. Stop it from its original window.' };" ^
    "Stop-Process -InputObject $target; if (!$target.WaitForExit(5000)) { throw 'Web did not exit.' }; Write-Host 'Web stopped.'"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
