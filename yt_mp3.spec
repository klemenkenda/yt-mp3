# PyInstaller spec: single-file, windowed yt-mp3.exe
# Build with:  .\build.ps1   (or: pyinstaller yt_mp3.spec)
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = [("assets/icon.ico", "assets"), ("assets/Roboto-Regular.ttf", "assets"), ("assets/Roboto-Bold.ttf", "assets")]
binaries = []
hiddenimports = []

# PyAV ships FFmpeg DLLs (incl. LAME) inside the wheel
for pkg in ("av",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("customtkinter")
# yt-dlp loads extractors/plugins dynamically; yt_dlp_ejs ships JS challenge solvers as data
hiddenimports += collect_submodules("yt_dlp")
try:
    datas += collect_data_files("yt_dlp_ejs")
    hiddenimports += collect_submodules("yt_dlp_ejs")
except Exception:
    pass

a = Analysis(
    ["src/yt_mp3/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["numpy", "pytest", "matplotlib", "PIL", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="yt-mp3",
    icon="assets/icon.ico",
    console=False,
    upx=False,  # UPX-compressed exes trigger more antivirus false positives
    version="version_info.txt",
)
