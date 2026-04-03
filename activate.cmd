@echo off
set SCRIPT_PATH=%~dp0.
set SCRIPT_NAME=%~nx0
set VENV_DIR=%SCRIPT_PATH%\.venv
set ACTIVATE_SCRIPT=%VENV_DIR%\Scripts\activate.bat
set PYLAUNCHER=%WINDIR%\py.exe

if not exist "%ACTIVATE_SCRIPT%" goto noactivate
call "%ACTIVATE_SCRIPT%"
exit /b 0

:noactivate
if not exist "%PYLAUNCHER%" goto nopylauncher
set PYTHON=%PYLAUNCHER%
goto createvenv

:nopylauncher
where python.exe >nul 2>&1
if %ERRORLEVEL% equ 0 goto pythoninpath
echo %SCRIPT_NAME%: Failed to locate Python >&2
exit /b 1

:pythoninpath
set PYTHON=python.exe

:createvenv
"%PYTHON%" -m venv "%VENV_DIR%"
if %ERRORLEVEL% equ 0 goto activate
echo %SCRIPT_NAME%: Failed to create virtual environment >&2
exit /b 2

:activate
call "%ACTIVATE_SCRIPT%"

pip install setuptools wheel
if %ERRORLEVEL% equ 0 goto installreqs
echo %SCRIPT_NAME%: Failed to install setuptools >&2
call deactivate.bat
exit /b 3

:installreqs
pip install -e "%SCRIPT_PATH%"
if %ERRORLEVEL% equ 0 goto end
echo %SCRIPT_NAME%: Failed to install required packages >&2
call deactivate.bat
exit /b 4

:end
exit /b 0
