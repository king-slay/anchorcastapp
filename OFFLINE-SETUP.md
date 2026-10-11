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
   npm install
   .\setup_whisper.bat
   ```

   `setup_whisper.bat` downloads Python 3.12 and faster-whisper into a
   `python` folder next to the app.
3. Start the app with `npm start`.
4. **Speech model:** Settings › AI & Transcription › Local Whisper Model, choose **Tiny English**
   (tiny.en) on a laptop like the Dell, and download it. Use Base or Small
   English on a stronger computer.
5. **Bible:** Settings › Bible Versions, download or upload the translations
   you use.

## Every service (no internet needed)

```powershell
cd C:\Users\<you>\anchorcastapp
npm start
```

## Checking the reference parser

```powershell
.\python\python.exe -m pip install pytest
.\python\python.exe -m pytest -q tests
```
