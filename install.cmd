@echo off
@echo off
where py >nul 2>&1
if not errorlevel 1 goto use_py
where python >nul 2>&1
if errorlevel 1 (
  echo FAIL  需要 Python 3。 1>&2
  exit /b 2
)
python "%~dp0install_cli.py" %*
exit /b %errorlevel%

:use_py
py -3 "%~dp0install_cli.py" %*
exit /b %errorlevel%
