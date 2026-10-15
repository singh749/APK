# 🔧 Engine Number OCR Scanner (Android · Python · Kivy)

Android app that reads the **engine number stamped on metal** from a photo.

## App flow

1. **📷 Take Picture** (camera) or **🖼 Upload Image** (gallery)
2. Image is auto-enhanced (grayscale → contrast → sharpen) for better OCR
3. **🔍 Scan** — OCR reads the text and extracts the engine-number pattern
4. The detected number appears in an **editable field** → verify / correct it
   *(no OCR on earth is 100% on stamped metal — this confirm step makes your
   saved data 100% correct)*
5. **💾 Save & Finish** — record is stored with date & time
6. **🗂 Saved Records** — view all previously saved engine numbers

## OCR engine

Uses the **OCR.space API** (Engine 2 — optimised for alphanumeric serials).
A free demo key is bundled. For real use, get your own **free** key at
<https://ocr.space/ocrapi/freekey> and enter it in the app under
**⚙ OCR API KEY**. Internet is required for scanning.

## Build (CI/CD)

Every push triggers **GitHub Actions** (`.github/workflows/build-apk.yml`):

1. Go to the **Actions** tab of this repo
2. Open the latest **Build Android APK** run
3. Download the **engine-ocr-apk** artifact (zip) → inside is the `.apk`
4. Copy it to your phone and install (allow "unknown sources")

First build takes ~30–50 min (downloads Android SDK/NDK); later builds are
faster thanks to caching.

## Run on desktop (for testing)

```bash
pip install -r requirements.txt
python main.py
```

## Project files

| File | Purpose |
|---|---|
| `main.py` | Kivy app (UI, camera, OCR, records) |
| `buildozer.spec` | Android packaging config (permissions, deps) |
| `.github/workflows/build-apk.yml` | CI/CD — builds the APK automatically |

## Tips for accurate scans

- Fill the frame with the engine number only
- Good light, no glare, hold steady
- Clean the metal surface if dusty/oily
