# Running this fork on a church laptop

This fork reads spoken Bible references with `scripture_parser` (from Live
Scripture Assistant) inside the speech server, and needs no registration.
Internet is needed once, for the setup below; after that the app runs offline.

## One-time setup (with internet)

1. Install Node.js LTS from https://nodejs.org (accept the defaults).
2. In PowerShell:

   ```powershell
   cd C:\Users\<you>
   git clone https://github.com/king-slay/anchorcastapp.git
   cd anchorcastapp
   git checkout claude/our-reference-parser
   npm.cmd install
   node node_modules\electron\install.js
   .\setup_whisper.bat
   ```

   Use `npm.cmd` rather than `npm`: Windows often blocks plain `npm` with
   "running scripts is disabled". Newer npm (11.19 and later) skips
   Electron's own download step and says so in an `install-scripts`
   warning; the `node ... install.js` line runs that step.
   `Test-Path node_modules\electron\dist\electron.exe` should print `True`.

   `setup_whisper.bat` downloads Python 3.12 and faster-whisper into a
   `python` folder next to the app.
   If `setup_whisper.bat` stops at "Downloading portable Python", press
   Ctrl+C and do its steps by hand (this also skips the 480 MB Small model):

   ```powershell
   curl.exe -L -o python312.zip https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
   mkdir python
   tar -xf python312.zip -C python
   del python312.zip
   (Get-Content python\python312._pth) -replace '#import site','import site' | Set-Content python\python312._pth
   curl.exe -L -o get-pip.py https://bootstrap.pypa.io/get-pip.py
   .\python\python.exe get-pip.py --no-warn-script-location
   del get-pip.py
   .\python\python.exe -m pip install faster-whisper --no-warn-script-location
   .\python\python.exe -c "from faster_whisper import WhisperModel; WhisperModel('tiny.en', device='cpu', compute_type='int8'); print('OK')"
   ```
3. Start the app with `npm.cmd start`.
4. **Speech model:** Settings › AI & Transcription › Local Whisper Model, choose **Tiny English**
   (tiny.en) on a laptop like the Dell, and download it. Use Base or Small
   English on a stronger computer.
5. **Bible:** Settings › Bible Versions, download or upload the translations
   you use.

## Every service (no internet needed)

```powershell
cd C:\Users\<you>\anchorcastapp
npm.cmd start
```

## Checking the reference parser

```powershell
.\python\python.exe -m pip install pytest
.\python\python.exe -m pytest -q tests
```
