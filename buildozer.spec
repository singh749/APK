[app]
# ---------------------------------------------------------------- identity
title = Engine Number OCR
package.name = engineocr
package.domain = org.singh749

# ---------------------------------------------------------------- sources
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json
source.exclude_dirs = tests, bin, .buildozer, .github

version = 1.0.0

# ---------------------------------------------------------------- python deps
# requests needs: urllib3, charset-normalizer, idna, certifi
requirements = python3,kivy,requests,urllib3,charset-normalizer,idna,certifi,pillow,plyer,android

orientation = portrait
fullscreen = 0

# ---------------------------------------------------------------- android
android.permissions = CAMERA,INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES

android.api = 33
android.minapi = 24
android.ndk_api = 24

android.archs = arm64-v8a,armeabi-v7a

android.allow_backup = True
android.accept_sdk_license = True

# AndroidX needed by plyer camera on modern devices
android.enable_androidx = True

# ---------------------------------------------------------------- p4a
p4a.branch = master
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
