@echo off
set SCRIPT_PATH=%~dp0.
set SCRIPT_NAME=%~nx0
call "%SCRIPT_PATH%\activate.cmd"
setlocal
set PYTHONPATH=%SCRIPT_PATH%\src;%PYTHONPATH%

for /f "tokens=1,*" %%A in ("%*") do python.exe -m "cProfile" -o "%~n1.profile" -m "%~n1" %%B
if %ERRORLEVEL% equ 0 goto snakeviz
echo %SCRIPT_NAME%: Failed to run cProfile >&2
exit /b 1

:snakeviz
snakeviz.exe "%~n1.profile"

endlocal
set RESULT=%ERRORLEVEL%
call deactivate.bat
exit /b %RESULT%
