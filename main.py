"""
Engine Number OCR Scanner
-------------------------
Flow:
  1. Take a picture with the camera OR upload an image from the gallery.
  2. Image is preprocessed (grayscale, contrast, sharpen) for better OCR.
  3. OCR engine reads the text and extracts the engine number stamped on metal.
  4. Result is shown in an EDITABLE field -> user confirms / fixes it.
  5. Saved records are stored locally (JSON) and listed in History.

OCR engine: OCR.space API (engine 2 - best for alphanumeric serials).
A free demo key is bundled; put your own free key in Settings for production
(get one at https://ocr.space/ocrapi/freekey).
"""

import json
import os
import re
import threading
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

import requests

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ---------------------------------------------------------------- constants
OCR_API_URL = "https://api.ocr.space/parse/image"
DEFAULT_API_KEY = "helloworld"  # OCR.space free demo key (rate limited)

PRIMARY = (0.13, 0.46, 0.85, 1)
SUCCESS = (0.16, 0.65, 0.35, 1)
DANGER = (0.8, 0.25, 0.25, 1)
DARK_BG = (0.08, 0.09, 0.12, 1)
CARD_BG = (0.13, 0.15, 0.19, 1)

Window.clearcolor = DARK_BG

IS_ANDROID = platform == "android"

if IS_ANDROID:
    from android.permissions import request_permissions, Permission  # noqa
    from android.storage import app_storage_path  # noqa


# ---------------------------------------------------------------- helpers
def app_dir():
    """Writable private dir for records & temp photos."""
    if IS_ANDROID:
        return app_storage_path()
    d = os.path.join(os.path.expanduser("~"), ".engine_ocr")
    os.makedirs(d, exist_ok=True)
    return d


RECORDS_FILE = os.path.join(app_dir(), "engine_records.json")
SETTINGS_FILE = os.path.join(app_dir(), "settings.json")


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def preprocess_image(src_path):
    """Enhance the photo so stamped metal text OCRs better.
    Returns path of the processed JPEG (or the original if PIL missing)."""
    if not HAS_PIL:
        return src_path
    try:
        img = Image.open(src_path)
        img = ImageOps.exif_transpose(img)          # fix camera rotation
        img = img.convert("L")                       # grayscale
        # upscale small images - OCR likes >= ~1000px wide
        if img.width < 1200:
            ratio = 1200.0 / img.width
            img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)
        img = ImageOps.autocontrast(img, cutoff=2)    # stretch contrast
        img = ImageEnhance.Contrast(img).enhance(1.6)
        img = img.filter(ImageFilter.SHARPEN)
        out = os.path.join(app_dir(), "ocr_input.jpg")
        img.save(out, "JPEG", quality=92)
        return out
    except Exception:
        return src_path


# Characters OCR commonly confuses on stamped metal
AMBIGUOUS = {"O": "0", "I": "1", "S": "5", "B": "8"}


def extract_engine_numbers(raw_text):
    """Pull likely engine/serial numbers out of OCR text.

    Engine numbers are typically 6-20 chars, alphanumeric, usually a mix of
    letters and digits (e.g. HA10ENJGK05870, 52WVC10305).
    Returns a ranked list of candidates (best first).
    """
    if not raw_text:
        return []
    # join characters OCR split with spaces inside a serial, then tokenize
    tokens = re.findall(r"[A-Z0-9\-\*]{4,}", raw_text.upper())
    candidates = []
    for tok in tokens:
        clean = tok.replace("*", "").replace("-", "")
        if not (6 <= len(clean) <= 20):
            continue
        has_digit = any(c.isdigit() for c in clean)
        has_alpha = any(c.isalpha() for c in clean)
        score = len(clean)
        if has_digit and has_alpha:
            score += 10          # classic engine-number pattern
        elif has_digit:
            score += 4           # purely numeric serials exist too
        else:
            continue             # pure words -> not a serial
        candidates.append((score, clean))
    candidates.sort(key=lambda x: -x[0])
    seen, ranked = set(), []
    for _, c in candidates:
        if c not in seen:
            seen.add(c)
            ranked.append(c)
    return ranked


def ocr_space(image_path, api_key):
    """Call OCR.space. Returns (full_text, error_msg)."""
    try:
        with open(image_path, "rb") as fh:
            resp = requests.post(
                OCR_API_URL,
                files={"file": ("image.jpg", fh, "image/jpeg")},
                data={
                    "apikey": api_key,
                    "language": "eng",
                    "OCREngine": "2",       # engine 2: best for serials
                    "scale": "true",
                    "detectOrientation": "true",
                    "isOverlayRequired": "false",
                },
                timeout=60,
            )
        data = resp.json()
        if data.get("IsErroredOnProcessing"):
            msg = data.get("ErrorMessage") or ["OCR processing error"]
            if isinstance(msg, list):
                msg = "; ".join(str(m) for m in msg)
            return "", str(msg)
        results = data.get("ParsedResults") or []
        text = "\n".join(r.get("ParsedText", "") for r in results)
        return text.strip(), None
    except requests.exceptions.ConnectionError:
        return "", "No internet connection. OCR needs internet."
    except Exception as exc:  # noqa
        return "", "OCR failed: %s" % exc


# ---------------------------------------------------------------- widgets
class FlatButton(Button):
    def __init__(self, bg=PRIMARY, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("background_color", bg)
        kw.setdefault("font_size", dp(17))
        kw.setdefault("bold", True)
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(56))
        super().__init__(**kw)


class TitleBar(BoxLayout):
    def __init__(self, title, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(52), padding=[dp(12), 0], **kw)
        self.add_widget(Label(text="[b]%s[/b]" % title, markup=True,
                              font_size=dp(20), halign="left",
                              valign="middle", color=(1, 1, 1, 1)))


def toast(text, title="Info"):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    content.add_widget(Label(text=text, font_size=dp(15)))
    btn = FlatButton(text="OK", height=dp(44))
    content.add_widget(btn)
    pop = Popup(title=title, content=content,
                size_hint=(0.85, None), height=dp(220))
    btn.bind(on_release=pop.dismiss)
    pop.open()


# ---------------------------------------------------------------- screens
class HomeScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(14))

        root.add_widget(Label(
            text="[b]ENGINE NUMBER\nOCR SCANNER[/b]", markup=True,
            font_size=dp(28), halign="center", size_hint_y=None,
            height=dp(110), color=(1, 1, 1, 1)))
        root.add_widget(Label(
            text="Scan the engine number stamped on metal.\n"
                 "Take a photo or upload an image.",
            font_size=dp(14), halign="center", size_hint_y=None,
            height=dp(60), color=(0.7, 0.75, 0.8, 1)))

        cam = FlatButton(text="📷  TAKE PICTURE", height=dp(64))
        cam.bind(on_release=self.take_picture)
        root.add_widget(cam)

        up = FlatButton(text="🖼  UPLOAD IMAGE", height=dp(64),
                        bg=(0.25, 0.3, 0.4, 1))
        up.bind(on_release=lambda *_: setattr(self.manager, "current", "picker"))
        root.add_widget(up)

        hist = FlatButton(text="🗂  SAVED RECORDS", height=dp(56),
                          bg=(0.2, 0.22, 0.28, 1))
        hist.bind(on_release=self.open_history)
        root.add_widget(hist)

        setting = FlatButton(text="⚙  OCR API KEY", height=dp(48),
                             bg=(0.17, 0.18, 0.22, 1))
        setting.bind(on_release=self.open_settings)
        root.add_widget(setting)

        root.add_widget(Label(
            text="Tip: fill the frame with the engine number,\n"
                 "good light, hold steady.",
            font_size=dp(12), color=(0.5, 0.55, 0.6, 1)))
        self.add_widget(root)

    # ---- camera via plyer
    def take_picture(self, *_):
        photo = os.path.join(app_dir(), "camera_%s.jpg"
                             % datetime.now().strftime("%H%M%S"))
        try:
            from plyer import camera
            camera.take_picture(filename=photo,
                                on_complete=self._on_photo)
        except Exception as exc:
            toast("Camera not available here:\n%s\n\nUse Upload Image instead."
                  % exc, "Camera")

    def _on_photo(self, path):
        if path and os.path.exists(path):
            Clock.schedule_once(lambda *_: self._go_scan(path), 0)
        return False

    def _go_scan(self, path):
        scan = self.manager.get_screen("scan")
        scan.set_image(path)
        self.manager.current = "scan"

    def open_history(self, *_):
        self.manager.get_screen("history").refresh()
        self.manager.current = "history"

    def open_settings(self, *_):
        settings = load_json(SETTINGS_FILE, {})
        content = BoxLayout(orientation="vertical", padding=dp(12),
                            spacing=dp(10))
        content.add_widget(Label(
            text="OCR.space API key\n(free key: ocr.space/ocrapi/freekey)",
            font_size=dp(13), size_hint_y=None, height=dp(50)))
        ti = TextInput(text=settings.get("api_key", ""),
                       hint_text="leave empty = demo key",
                       multiline=False, size_hint_y=None, height=dp(48),
                       font_size=dp(16))
        content.add_widget(ti)
        btn = FlatButton(text="SAVE KEY", bg=SUCCESS, height=dp(48))
        content.add_widget(btn)
        pop = Popup(title="Settings", content=content,
                    size_hint=(0.9, None), height=dp(260))

        def _save(*_):
            settings["api_key"] = ti.text.strip()
            save_json(SETTINGS_FILE, settings)
            pop.dismiss()
            toast("API key saved.")
        btn.bind(on_release=_save)
        pop.open()


class PickerScreen(Screen):
    """Gallery / file browser to upload an existing image."""
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical")
        root.add_widget(TitleBar("Choose an image"))

        start = "/storage/emulated/0" if IS_ANDROID else os.path.expanduser("~")
        if not os.path.isdir(start):
            start = "/"
        self.chooser = FileChooserIconView(
            path=start,
            filters=["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp",
                     "*.JPG", "*.JPEG", "*.PNG"])
        root.add_widget(self.chooser)

        row = BoxLayout(size_hint_y=None, height=dp(60),
                        spacing=dp(10), padding=dp(8))
        back = FlatButton(text="BACK", bg=(0.3, 0.3, 0.35, 1), height=dp(48))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "home"))
        ok = FlatButton(text="USE THIS IMAGE", bg=SUCCESS, height=dp(48))
        ok.bind(on_release=self.choose)
        row.add_widget(back)
        row.add_widget(ok)
        root.add_widget(row)
        self.add_widget(root)

    def choose(self, *_):
        if not self.chooser.selection:
            toast("Tap an image first, then press USE THIS IMAGE.")
            return
        path = self.chooser.selection[0]
        scan = self.manager.get_screen("scan")
        scan.set_image(path)
        self.manager.current = "scan"


class ScanScreen(Screen):
    """Shows the picture, runs OCR, lets the user edit & save the result."""
    image_path = StringProperty("")

    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        root.add_widget(TitleBar("Scan engine number"))

        self.img = KivyImage(allow_stretch=True, size_hint_y=0.42)
        root.add_widget(self.img)

        self.status = Label(text="Press SCAN to read the engine number.",
                            font_size=dp(14), size_hint_y=None, height=dp(30),
                            color=(0.75, 0.8, 0.85, 1))
        root.add_widget(self.status)

        root.add_widget(Label(text="Engine number (edit if needed):",
                              font_size=dp(13), size_hint_y=None,
                              height=dp(22), color=(0.6, 0.65, 0.7, 1)))
        self.result = TextInput(text="", multiline=False,
                                font_size=dp(24), halign="center",
                                size_hint_y=None, height=dp(56),
                                background_color=CARD_BG,
                                foreground_color=(0.4, 1, 0.6, 1))
        root.add_widget(self.result)

        self.alt_label = Label(text="", font_size=dp(12), size_hint_y=None,
                               height=dp(40), color=(0.55, 0.6, 0.65, 1))
        root.add_widget(self.alt_label)

        self.scan_btn = FlatButton(text="🔍  SCAN (OCR)")
        self.scan_btn.bind(on_release=self.run_ocr)
        root.add_widget(self.scan_btn)

        row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(10))
        back = FlatButton(text="BACK", bg=(0.3, 0.3, 0.35, 1))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "home"))
        self.save_btn = FlatButton(text="💾  SAVE & FINISH", bg=SUCCESS)
        self.save_btn.bind(on_release=self.save_record)
        row.add_widget(back)
        row.add_widget(self.save_btn)
        root.add_widget(row)
        self.add_widget(root)

    def set_image(self, path):
        self.image_path = path
        self.img.source = path
        self.img.reload()
        self.result.text = ""
        self.alt_label.text = ""
        self.status.text = "Press SCAN to read the engine number."
        self.status.color = (0.75, 0.8, 0.85, 1)

    def run_ocr(self, *_):
        if not self.image_path:
            toast("No image selected.")
            return
        self.scan_btn.disabled = True
        self.scan_btn.text = "⏳  SCANNING..."
        self.status.text = "Enhancing image & running OCR..."
        threading.Thread(target=self._ocr_worker, daemon=True).start()

    def _ocr_worker(self):
        processed = preprocess_image(self.image_path)
        key = load_json(SETTINGS_FILE, {}).get("api_key") or DEFAULT_API_KEY
        text, err = ocr_space(processed, key)
        candidates = extract_engine_numbers(text)
        self._ocr_done(text, err, candidates)

    @mainthread
    def _ocr_done(self, text, err, candidates):
        self.scan_btn.disabled = False
        self.scan_btn.text = "🔍  SCAN AGAIN"
        if err:
            self.status.text = err
            self.status.color = DANGER
            return
        if candidates:
            self.result.text = candidates[0]
            self.status.text = "✔ Engine number detected — verify & edit below."
            self.status.color = (0.4, 1, 0.6, 1)
            if len(candidates) > 1:
                self.alt_label.text = ("Other matches: "
                                       + ", ".join(candidates[1:4])
                                       + "   (tap field to edit)")
        elif text:
            self.result.text = ""
            self.status.text = ("Text found but no serial pattern. "
                                "Raw text: %s" % text[:80])
            self.status.color = (1, 0.8, 0.3, 1)
        else:
            self.status.text = ("No text detected. Retake photo closer, "
                                "with better light.")
            self.status.color = DANGER

    def save_record(self, *_):
        number = self.result.text.strip().upper()
        if not number:
            toast("Engine number is empty.\nScan first or type it manually.")
            return
        records = load_json(RECORDS_FILE, [])
        records.insert(0, {
            "engine_number": number,
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "image": self.image_path,
        })
        save_json(RECORDS_FILE, records)
        toast("Saved!\n\nEngine No: %s" % number, "✔ Finished")
        self.manager.current = "home"


class HistoryScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(TitleBar("Saved records"))
        self.scroll = ScrollView()
        self.listbox = BoxLayout(orientation="vertical", size_hint_y=None,
                                 spacing=dp(6), padding=[0, dp(4)])
        self.listbox.bind(minimum_height=self.listbox.setter("height"))
        self.scroll.add_widget(self.listbox)
        root.add_widget(self.scroll)

        back = FlatButton(text="BACK", bg=(0.3, 0.3, 0.35, 1))
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "home"))
        root.add_widget(back)
        self.add_widget(root)

    def refresh(self):
        self.listbox.clear_widgets()
        records = load_json(RECORDS_FILE, [])
        if not records:
            self.listbox.add_widget(Label(
                text="No records yet.", size_hint_y=None, height=dp(40),
                color=(0.6, 0.6, 0.65, 1)))
            return
        for rec in records:
            card = BoxLayout(orientation="vertical", size_hint_y=None,
                             height=dp(64), padding=[dp(10), dp(4)])
            card.add_widget(Label(
                text="[b]%s[/b]" % rec.get("engine_number", "?"),
                markup=True, font_size=dp(19), halign="left",
                color=(0.4, 1, 0.6, 1)))
            card.add_widget(Label(
                text=rec.get("datetime", ""), font_size=dp(12),
                color=(0.55, 0.6, 0.65, 1)))
            self.listbox.add_widget(card)


# ---------------------------------------------------------------- app
class EngineOCRApp(App):
    title = "Engine Number OCR"

    def build(self):
        if IS_ANDROID:
            request_permissions([
                Permission.CAMERA,
                Permission.INTERNET,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_MEDIA_IMAGES,
            ])
        sm = ScreenManager(transition=SlideTransition(duration=0.18))
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(PickerScreen(name="picker"))
        sm.add_widget(ScanScreen(name="scan"))
        sm.add_widget(HistoryScreen(name="history"))
        return sm


if __name__ == "__main__":
    EngineOCRApp().run()
