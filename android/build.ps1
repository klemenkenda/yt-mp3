# Build the Android APK with Buildozer in Docker (no Android SDK/JDK needed on Windows).
#   .\android\build.ps1           release APK, signed with the keystore below
#   .\android\build.ps1 -Debug    debug APK
#
# The SDK/NDK and build tree live in the Docker volume "yt-mp3-buildozer".
# The first build downloads ~3 GB and takes 30-60 min; later builds are much faster.
#
# Release signing: keystore + password are kept OUTSIDE the repo in
#   %USERPROFILE%\.yt-mp3-android\  (release.keystore, keystore.pass)
# and created on the first release build. Back them up: updates must be signed with the same key.
param([switch]$Debug)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$image = "kivy/buildozer:latest"
$volume = "yt-mp3-buildozer"

# 1. Copy the shared core (not the desktop GUI) next to main.py
$core = Join-Path $here "yt_mp3"
if (Test-Path $core) { Remove-Item $core -Recurse -Force }
New-Item -ItemType Directory $core | Out-Null
foreach ($f in "__init__.py", "converter.py", "downloader.py", "resolver.py", "util.py", "worker.py", "ytdl.py") {
    Copy-Item (Join-Path $here "..\src\yt_mp3\$f") $core
}

# 2. Icons
$py = Join-Path $here "..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
if (-not (Test-Path (Join-Path $here "icon.png"))) { & $py (Join-Path $here "..\tools\make_icon.py") --android }

# 3. Build
$dockerArgs = @("run", "--rm", "-v", "${volume}:/home/user/.buildozer", "-v", "${here}:/home/user/hostcwd")
if ($Debug) {
    $mode = "debug"
} else {
    $mode = "release"
    $keyDir = Join-Path $env:USERPROFILE ".yt-mp3-android"
    $keystore = Join-Path $keyDir "release.keystore"
    $passFile = Join-Path $keyDir "keystore.pass"
    if (-not (Test-Path $keystore)) {
        New-Item -ItemType Directory -Force $keyDir | Out-Null
        $pass = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
        [IO.File]::WriteAllText($passFile, $pass)
        docker run --rm -v "${keyDir}:/keys" --entrypoint keytool $image `
            -genkeypair -keystore /keys/release.keystore -alias ytmp3 -keyalg RSA -keysize 4096 -validity 10000 `
            -storepass $pass -keypass $pass -dname "CN=YT to MP3, O=klemenkenda"
        if ($LASTEXITCODE -ne 0) { throw "keytool failed" }
        Write-Host "Created $keystore - BACK IT UP together with keystore.pass"
    }
    if (-not (Test-Path $passFile)) { throw "$keystore exists but $passFile is missing" }
    $pass = [IO.File]::ReadAllText($passFile).Trim()
    $dockerArgs += @("-v", "${keyDir}:/keys:ro",
        "-e", "P4A_RELEASE_KEYSTORE=/keys/release.keystore", "-e", "P4A_RELEASE_KEYALIAS=ytmp3",
        "-e", "P4A_RELEASE_KEYSTORE_PASSWD=$pass", "-e", "P4A_RELEASE_KEYALIAS_PASSWD=$pass")
}
docker @dockerArgs $image android $mode
if ($LASTEXITCODE -ne 0) { throw "buildozer failed" }
Get-ChildItem (Join-Path $here "bin") -Filter *.apk | Sort-Object LastWriteTime | Select-Object -Last 1 Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
