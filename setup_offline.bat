@echo off
:: One-time speech setup for this fork, using curl.exe (built into Windows 10
:: and 11) instead of setup_whisper.bat's hidden downloads, which can stall.
:: Puts Python 3.12 in .\python, installs faster-whisper and downloads one
:: speech model: tiny.en unless another is named, e.g. setup_offline.bat base.en
:: Safe to run again: finished steps are skipped.
setlocal
cd /d "%~dp0"
set "PY=%~dp0python\python.exe"
set "MODEL=%~1"
if "%MODEL%"=="" set "MODEL=tiny.en"
set "PYTHON_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"
set "GETPIP_URL=https://bootstrap.pypa.io/get-pip.py"

if exist "%PY%" goto :pip
echo [1/4] Downloading Python 3.12 (about 11 MB)...
curl.exe -L --fail --retry 3 -o python312.zip "%PYTHON_URL%" || goto :failed
if not exist python mkdir python
tar -xf python312.zip -C python || goto :failed
del python312.zip
powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content 'python\python312._pth') -replace '#import site','import site' | Set-Content 'python\python312._pth'" || goto :failed

:pip
"%PY%" -m pip --version >nul 2>&1 && goto :engine
echo [2/4] Installing pip...
curl.exe -L --fail --retry 3 -o get-pip.py "%GETPIP_URL%" || goto :failed
"%PY%" get-pip.py --no-warn-script-location || goto :failed
del get-pip.py

:engine
echo [3/4] Installing the speech engine (about 150 MB)...
"%PY%" -m pip install faster-whisper --no-warn-script-location || goto :failed

echo [4/4] Downloading the %MODEL% speech model...
"%PY%" -c "from faster_whisper import WhisperModel; WhisperModel('%MODEL%', device='cpu', compute_type='int8'); print('[OK] Speech is ready')" || goto :failed
echo.
echo Setup complete. Start the app with:  npm.cmd start
exit /b 0

:failed
echo.
echo Setup stopped. Check the internet connection, then run setup_offline.bat again.
exit /b 1
