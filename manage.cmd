@echo off
rem Register / unregister the Orange MCP server in AI clients.
rem   manage.cmd                      -> opens the window
rem   manage.cmd status               -> show registration state
rem   manage.cmd install   [--client claude,codex] [--dry-run] [--force]
rem   manage.cmd uninstall [--client claude,codex] [--dry-run] [--force]
setlocal
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
if "%~1"=="" (
    start "" "%PY:python.exe=pythonw.exe%" "%~dp0manage.py" gui
) else (
    "%PY%" "%~dp0manage.py" %*
)
