@echo off
rem Start WOLF on Windows: double-click this file.
rem First run: sets everything up and asks for your Claude API key. Later runs: just starts.
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo WOLF needs Python 3.10 or newer.
  echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this again.
  pause & exit /b 1
)
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" || (
  echo WOLF needs Python 3.10 or newer. Install it from https://www.python.org/downloads/
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Setting up WOLF ^(first run takes a minute^)...
  %PY% -m venv .venv || (pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip > ".venv\install.log" 2>&1
)
rem Every start: install anything new WOLF needs (quick when nothing changed).
".venv\Scripts\python.exe" -m pip install -e . >> ".venv\install.log" 2>&1 || (
  echo Setup failed. Details are in .venv\install.log
  pause & exit /b 1
)

rem Add --host 0.0.0.0 to use WOLF from your phone on the same Wi-Fi.
".venv\Scripts\wolf.exe" serve --open %*
pause
