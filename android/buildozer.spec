[app]
title = YT to MP3
package.name = ytmp3
package.domain = io.github.klemenkenda
source.dir = .
source.include_exts = py,png,json
source.exclude_dirs = bin,.buildozer,__pycache__
source.exclude_patterns = build.ps1,*.xml
version = 1.0.0

# av -> ffmpeg + av_codecs (libshine MP3 encoder); the rest is pure Python
requirements = python3,kivy,pyjnius,android,av,yt-dlp,mutagen,certifi

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #1C1C1F

android.permissions = INTERNET, ACCESS_NETWORK_STATE, READ_MEDIA_AUDIO, (name=android.permission.READ_EXTERNAL_STORAGE;maxSdkVersion=32), (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=28)
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.release_artifact = apk
android.debug_artifact = apk

# "Share -> YT to MP3" from the YouTube app; a single instance receives new shares
android.manifest.intent_filters = intent_filters.xml
android.manifest.launch_mode = singleTask
# Android 10 needs legacy storage to write into Music/ via file paths
android.extra_manifest_application_arguments = extra_manifest_application_arguments.xml

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 0
# keep the heavy build tree inside the container volume, not on the Windows bind mount
build_dir = /home/user/.buildozer/ytmp3-build
bin_dir = ./bin
