# Build dist\yt-mp3.exe
#   .\build.ps1            build (creates .venv if missing, always pulls the latest yt-dlp)
#   .\build.ps1 -SkipTests skip pytest
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"

& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet --upgrade -r requirements-dev.txt
& $py -m pip install --quiet --upgrade "yt-dlp[default]"   # YouTube changes often; always ship the newest
& $py -c "import yt_dlp; print('yt-dlp', yt_dlp.version.__version__)"

if (-not (Test-Path assets\icon.ico)) { & $py tools\make_icon.py }

if (-not $SkipTests) {
    & $py -m pytest -q -m "not network"
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
}

& $py -m PyInstaller --noconfirm --clean yt_mp3.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Get-Item dist\yt-mp3.exe | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
