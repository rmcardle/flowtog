@echo off
set SCRIPT_PATH=%~dp0.
call "%SCRIPT_PATH%\activate.cmd"
setlocal
set PYTHONPATH=%SCRIPT_PATH%\src;%PYTHONPATH%
python.exe -m flowtog --edit %*
endlocal
set RESULT=%ERRORLEVEL%
call deactivate.bat
exit /b %RESULT%
