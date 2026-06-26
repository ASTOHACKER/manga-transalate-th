"""
Manga Screen Translator v2
- Ctrl+Shift+T: จับภาพจากหน้าจอ → OCR → แปล → overlay ทับข้อความเดิม
- รองรับ API: OpenAI, Gemini, Google Translate (free), 9Router
- รองรับ: ญี่ปุ่น, จีน, เกาหลี, อังกฤษ → ไทย
"""

import sys
import os
import json
import threading
import tkinter as tk
from datetime import datetime
from PIL import ImageGrab, Image, ImageTk, ImageDraw, ImageFont
import customtkinter as ctk
import keyboard
import easyocr
import numpy as np
import cv2
from deep_translator import GoogleTranslator
import urllib.request

# --- DPI Awareness for Windows ---
if os.name == "nt":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# --- UI Theme Palette (Minimalist Dark - Narudom Style) ---
BG_MAIN = "#0c0d12"        # Extremely deep matte slate black
BG_CARD = "#14161e"        # Card background
BG_INPUT = "#1b1d27"       # Textbox/Dropdown background
BORDER_COLOR = "#252936"   # Soft structured border
TEXT_PRIMARY = "#f1f5f9"   # Clean slate white
TEXT_MUTED = "#64748b"     # Neutral muted gray
ACCENT_COLOR = "#34d399"   # Emerald / Mint accent
ACCENT_HOVER = "#059669"   # Muted hover emerald
ACCENT_BG = "#064e3b"      # Dark green highlight
ACCENT_TEXT = "#047857"

# --- Config ---
HOTKEY = "ctrl+shift+t"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

SRC_LANGS = {
    "Japanese": ["ja"],
    "Chinese": ["ch_sim"],
    "Korean": ["ko"],
    "English": ["en"],
    "Japanese + English": ["ja", "en"],
    "Chinese + English": ["ch_sim", "en"],
    "Korean + English": ["ko", "en"],
}
LANG_MAP = {"ja": "ja", "ch_sim": "zh-CN", "ko": "ko", "en": "en"}
LANG_NAMES = {"ja": "Japanese", "ch_sim": "Chinese", "ko": "Korean", "en": "English"}

COMIC_TYPES = ["Manga (Japanese)", "Manhwa (Korean)", "Manhua (Chinese)", "General Comic / English"]

TRANSLATE_BACKENDS = ["Google Translate (Free)", "OpenAI API", "Gemini API", "9Router API"]


def load_config():
    defaults = {
        "backend": "Google Translate (Free)", 
        "api_key": "", 
        "model": "", 
        "base_url": "",
        "ninerouter_url": "http://localhost:20128",
        "ninerouter_key": "sk-...",
        "ninerouter_model": "my-combo",
        "font_family": "Leelawadee UI",
        "max_font_size": 24,
        "font_weight": "bold",
        "obsidian_sync": False,
        "obsidian_path": "C:\\Users\\narudom\\Documents\\Obsidian Vault",
        "inpaint_enabled": True,
        "comic_type": "Manga (Japanese)"
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            defaults.update(d)
        except Exception:
            pass
    return defaults


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# --- Translation backends ---

def get_translation_prompt(comic_type):
    base_instruction = (
        "You are an expert comic translator. Translate the given JSON array of texts to Thai. "
        "Crucial: Polish and rephrase the wording ('เกาสำนวนไทย') so it reads naturally, effortlessly, and holds high literary flow in Thai. "
        "Strictly avoid word-for-word literal translations (e.g., do not translate 'What brings you here?' as 'อะไรนำคุณมาที่นี่', instead use 'มีธุระอะไรคู่ควรมาที่นี่' or 'ลมอะไรพัดมาล่ะ'). "
        "The dialogue must sound like a professional human-localized comic book, not a machine. Keep it punchy, concise, and easy to read. "
        "Return a JSON object with a single key 'translations' containing the array of translated strings in the exact same order."
    )
    
    if "Manga" in comic_type:
        return base_instruction + (
            "\nStyle: Japanese Manga (Shonen/Seinen/Delinquent style).\n"
            "Guidelines:\n"
            "1. Use natural, highly stylized manga pronouns: 'แก', 'นาย', 'ฉัน', 'พวกมัน', 'คุณ' based on character relationships.\n"
            "2. Localize delinquent/street slang naturally: 'old fart' -> 'ตาแก่นี่', 'juvie' -> 'สถานพินิจ', 'up to no good' -> 'หาเรื่องใส่ตัว/ทำเรื่องชั่ว'.\n"
            "3. Rephrase short dialogues to carry emotional weight: 'Right.' -> 'นั่นสินะ/เอาล่ะ'."
        )
    elif "Manhwa" in comic_type:
        return base_instruction + (
            "\nStyle: Korean Manhwa (Modern Webtoon, Romance Fantasy, or Hunter/System style).\n"
            "Guidelines:\n"
            "1. Use modern polished webtoon pronouns: 'พี่' (Hyung/Oppa), 'เธอ', 'ฉัน', 'นาย'.\n"
            "2. Rephrase system/game terms to fit localized context beautifully.\n"
            "3. Keep the dialogue emotional, trendy, and casual, reading like a high-budget Webtoon translation."
        )
    elif "Manhua" in comic_type:
        return base_instruction + (
            "\nStyle: Chinese Manhua (Wuxia, Cultivation, or Modern CEO romance).\n"
            "Guidelines:\n"
            "1. Use polished historical/martial arts pronouns and titles: 'ศิษย์พี่', 'นายน้อย', 'ผู้อาวุโส', 'ใต้เท้า', 'ข้า', 'เจ้า'.\n"
            "2. Cultivation terms should sound grand and poetic (e.g., 'Sect' -> 'สำนัก', 'Qi' -> 'ลมปราณ').\n"
            "3. Tone should be grand, dramatic, and flow like a classic novel translation."
        )
    else:
        return base_instruction + (
            "\nStyle: General Comic/Manga.\n"
            "Guidelines:\n"
            "1. Keep it punchy and fit for speech bubbles.\n"
            "2. Avoid literal/robotic translations. Match the character's emotion."
        )


def translate_google(texts, src_lang_code):
    src = LANG_MAP.get(src_lang_code, "auto")
    translator = GoogleTranslator(source=src, target="th")
    try:
        return translator.translate_batch(texts)
    except Exception:
        return [translator.translate(t) for t in texts]


def translate_openai(texts, comic_type, api_key, model=None, base_url=None):
    model = model or "gpt-4o-mini"
    url = (base_url.rstrip("/") if base_url else "https://api.openai.com/v1") + "/chat/completions"

    payload = json.dumps({
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": get_translation_prompt(comic_type)},
            {"role": "user", "content": json.dumps({"texts": texts}, ensure_ascii=False)}
        ],
        "temperature": 0.3
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    res_content = data["choices"][0]["message"]["content"].strip()
    return json.loads(res_content)["translations"]


def translate_gemini(texts, comic_type, api_key, model=None):
    model = model or "gemini-2.0-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": (
            f"{get_translation_prompt(comic_type)}\n"
            f"Input JSON: {json.dumps({'texts': texts}, ensure_ascii=False)}"
        )}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    
    res_content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    return json.loads(res_content)["translations"]


def translate_ninerouter(texts, comic_type, url, key, model):
    endpoint = (url.rstrip("/") if url else "http://localhost:20128") + "/v1/chat/completions"
    
    payload = json.dumps({
        "model": model or "my-combo",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": get_translation_prompt(comic_type)},
            {"role": "user", "content": json.dumps({"texts": texts}, ensure_ascii=False)}
        ],
        "temperature": 0.3
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if key and key != "sk-...":
        headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(endpoint, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        response_data = resp.read()
        
        # Handle SSE/Streaming response if 9Router returns chunks by default
        decoded = response_data.decode("utf-8")
        if "data: " in decoded:
            full_content = ""
            for line in decoded.split("\n"):
                if line.startswith("data: ") and not line.endswith("[DONE]"):
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            full_content += delta["content"]
                    except Exception:
                        pass
            res_content = full_content.strip()
        else:
            data = json.loads(decoded)
            res_content = data["choices"][0]["message"]["content"].strip()
            
    return json.loads(res_content)["translations"]


def do_translate(texts, src_lang_code, cfg):
    backend = cfg.get("backend", "Google Translate (Free)")
    comic_type = cfg.get("comic_type", "Manga (Japanese)")

    try:
        if backend == "9Router API":
            return translate_ninerouter(
                texts, comic_type, 
                cfg.get("ninerouter_url"), 
                cfg.get("ninerouter_key"), 
                cfg.get("ninerouter_model")
            )
        elif backend == "OpenAI API" and cfg.get("api_key"):
            return translate_openai(texts, comic_type, cfg["api_key"], cfg.get("model"), cfg.get("base_url"))
        elif backend == "Gemini API" and cfg.get("api_key"):
            return translate_gemini(texts, comic_type, cfg["api_key"], cfg.get("model"))
    except Exception as e:
        pass
    return translate_google(texts, src_lang_code)


# --- Screen selector ---

class ScreenSelector(tk.Toplevel):
    def __init__(self, on_select):
        super().__init__()
        self.on_select = on_select
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.25)
        self.configure(bg="black")
        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda e: self.cancel())
        self.start_x = self.start_y = 0
        self.rect = None

    def cancel(self):
        self.destroy()

    def on_press(self, e):
        self.start_x, self.start_y = e.x, e.y
        if self.rect:
            self.canvas.delete(self.rect)

    def on_drag(self, e):
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, e.x, e.y,
            outline="#00ff88", width=2, dash=(4, 4)
        )

    def on_release(self, e):
        sx = self.winfo_rootx()
        sy = self.winfo_rooty()
        x0 = min(self.start_x, e.x) + sx
        y0 = min(self.start_y, e.y) + sy
        x1 = max(self.start_x, e.x) + sx
        y1 = max(self.start_y, e.y) + sy
        self.destroy()
        if x1 - x0 > 10 and y1 - y0 > 10:
            self.on_select((x0, y0, x1, y1))


# --- Overlay window: shows translated text on top of original ---

class OverlayWindow(tk.Toplevel):
    def __init__(self, bbox, blocks, orig_img, inpainted_img, cfg=None):
        super().__init__()
        self.cfg = cfg or load_config()
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0
        self.geometry(f"{w}x{h}+{x0}+{y0}")

        self.attributes("-alpha", 0.95)
        self.configure(bg="black")
        self.wm_attributes("-transparentcolor", "black")

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0, width=w, height=h)
        self.canvas.pack(fill="both", expand=True)

        # Draw the background image on the canvas (inpainted or original based on setting)
        self.bg_photo = ImageTk.PhotoImage(inpainted_img)
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")

        for block in blocks:
            self._draw_block(block, orig_img)

        # Keyboard Peeking bindings
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        
        self.canvas.bind("<Button-1>", lambda e: self.destroy())
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<space>", lambda e: self.destroy())
        self.after(30000, self._safe_destroy)

    def _safe_destroy(self):
        try:
            self.destroy()
        except Exception:
            pass

    def _on_key_press(self, event):
        # Hold Shift or Control to quickly peek at the original page
        if event.keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R"):
            self.attributes("-alpha", 0.0)

    def _on_key_release(self, event):
        if event.keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R"):
            self.attributes("-alpha", 0.95)

    def _wrap_thai_text(self, text, font, max_width):
        """
        Smart Thai Word Wrapping algorithm.
        Ensures words flow naturally inside speech bubbles without cutting mid-syllable.
        Uses a dynamic width dictionary to measure pixel dimensions accurately.
        """
        max_width = max(max_width, 35)
        lines = []
        paragraphs = text.split('\n')
        
        for para in paragraphs:
            # Tokenize Thai words cleanly (splitting on spaces first, then processing)
            tokens = para.split(' ')
            for token in tokens:
                if not token:
                    continue
                
                current_line = ""
                # Sub-segment long Thai compound tokens to prevent overflow
                i = 0
                while i < len(token):
                    # We look forward to build a syllable/word part
                    # Thai vowels and diacritics shouldn't be separated at the beginning of a line
                    char = token[i]
                    test_line = current_line + char
                    
                    # If it fits within the speech bubble width
                    if font.measure(test_line) <= max_width:
                        current_line = test_line
                        i += 1
                    else:
                        # If current_line is empty, we must force the single character to avoid infinite loop
                        if not current_line:
                            current_line = char
                            i += 1
                        lines.append(current_line)
                        current_line = ""
                
                if current_line:
                    lines.append(current_line)
                    
        return "\n".join(lines)

    def _draw_block(self, block, orig_img):
        box = block["box"]
        text = block["text"]

        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        bx0, by0 = min(xs), min(ys)
        bx1, by1 = max(xs), max(ys)
        bw = bx1 - bx0
        bh = by1 - by0

        if bw < 5 or bh < 5:
            return

        # Smart Background color extraction for high contrast text color selection
        bg_color = (255, 255, 255)
        try:
            crop = orig_img.crop((bx0, by0, bx1, by1))
            crop_np = np.array(crop)
            bg_color = np.median(crop_np[:, :, :3].reshape(-1, 3), axis=0).astype(int)
        except Exception:
            pass
        
        luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
        text_color = "#000000" if luminance > 130 else "#ffffff"

        # Dynamic Font Scaling & Professional Thai Typography
        font_family = self.cfg.get("font_family", "Leelawadee UI")
        max_size = int(self.cfg.get("max_font_size", 24))
        font_weight = self.cfg.get("font_weight", "bold")

        # Start with a safe, balanced font size proportional to bubble height
        font_size = max(10, min(int(bh * 0.45), max_size))
        
        import tkinter.font as tkfont
        try:
            font_obj = tkfont.Font(family=font_family, size=font_size, weight=font_weight)
        except Exception:
            font_obj = tkfont.Font(family="Segoe UI", size=font_size, weight="bold")
            font_family = "Segoe UI"

        # Wrap text using the smart Thai wrapping engine
        wrapped_text = self._wrap_thai_text(text, font_obj, bw - 10)

        # Precise line height and spacing calculation to avoid collision of Thai diacritics
        line_height = font_obj.metrics("linespace")
        # Add slight breathing room for Thai vowels/tonal marks (15% padding)
        line_spacing_pad = max(2, int(line_height * 0.15))
        effective_line_height = line_height + line_spacing_pad
        
        lines = wrapped_text.count("\n") + 1
        total_height = lines * effective_line_height
        
        # Prevent vertical overflow: scale down font size if wrapped height exceeds bubble boundary
        attempts = 0
        while (total_height > bh or font_obj.measure(wrapped_text.split('\n')[0]) > bw) and font_size > 8 and attempts < 6:
            font_size -= 2
            font_obj = tkfont.Font(family=font_family, size=font_size, weight=font_weight)
            wrapped_text = self._wrap_thai_text(text, font_obj, bw - 10)
            line_height = font_obj.metrics("linespace")
            effective_line_height = line_height + max(2, int(line_height * 0.15))
            lines = wrapped_text.count("\n") + 1
            total_height = lines * effective_line_height
            attempts += 1

        # Draw a fallback rounded rectangle bubble if inpainting is disabled to ensure text readability
        if not self.cfg.get("inpaint_enabled", True):
            bg_hex = f"#{bg_color[0]:02x}{bg_color[1]:02x}{bg_color[2]:02x}"
            pad = 4
            rx0, ry0, rx1, ry1 = bx0 - pad, by0 - pad, bx1 + pad, by1 + pad
            rw, rh = rx1 - rx0, ry1 - ry0
            radius = min(14, rw // 4, rh // 4)
            if radius < 3:
                self.canvas.create_rectangle(rx0, ry0, rx1, ry1, fill=bg_hex, outline="", width=0)
            else:
                self.canvas.create_rectangle(rx0 + radius, ry0, rx1 - radius, ry1, fill=bg_hex, outline="", width=0)
                self.canvas.create_rectangle(rx0, ry0 + radius, rx1, ry1 - radius, fill=bg_hex, outline="", width=0)
                self.canvas.create_oval(rx0, ry0, rx0 + 2 * radius, ry0 + 2 * radius, fill=bg_hex, outline="", width=0)
                self.canvas.create_oval(rx1 - 2 * radius, ry0, rx1, ry0 + 2 * radius, fill=bg_hex, outline="", width=0)
                self.canvas.create_oval(rx0, ry1 - 2 * radius, rx0 + 2 * radius, ry1, fill=bg_hex, outline="", width=0)
                self.canvas.create_oval(rx1 - 2 * radius, ry1 - 2 * radius, rx1, ry1, fill=bg_hex, outline="", width=0)

        # Center alignment (both Horizontal and Vertical) inside the bounding box
        cx = (bx0 + bx1) / 2
        cy = (by0 + by1) / 2

        # Draw centered text onto the canvas with proper padding to avoid diacritic overlap
        self.canvas.create_text(
            cx, cy, text=wrapped_text,
            fill=text_color, font=font_obj,
            width=bw - 6, anchor="center", justify="center"
        )


# --- Main App ---

class TranslatorApp:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("📖 Manga Translator v2")
        self.root.geometry("560x690") # Slightly taller to accommodate the new style dropdown
        self.root.configure(fg_color=BG_MAIN)
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)

        self.reader = None
        self.reader_lock = threading.Lock()
        self.is_processing = False
        self.current_lang_key = "Japanese"
        self.cfg = load_config()
        self.overlay = None

        self._build_ui()
        self._register_hotkey()
        
        threading.Thread(target=self._preload_ocr, daemon=True).start()

    def _build_ui(self):
        # --- Top Header ---
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 6))
        ctk.CTkLabel(
            header, 
            text="📖 Manga Translator v2",
            font=("Segoe UI", 16), 
            text_color=TEXT_PRIMARY
        ).pack(side="left")
        
        # Elegant Shortcut Badge
        badge_frame = ctk.CTkFrame(header, fg_color=BG_INPUT, border_color=BORDER_COLOR, border_width=1, corner_radius=6)
        badge_frame.pack(side="right")
        ctk.CTkLabel(
            badge_frame, 
            text=HOTKEY.upper(), 
            font=("Segoe UI Semibold", 10),
            text_color=TEXT_MUTED,
            padx=8,
            pady=2
        ).pack()

        # --- Control bar (Language & Capture) ---
        control_card = ctk.CTkFrame(self.root, fg_color=BG_CARD, border_color=BORDER_COLOR, border_width=1, corner_radius=10)
        control_card.pack(fill="x", padx=20, pady=8)

        # Row 1: Language Source Selection
        inner_control = ctk.CTkFrame(control_card, fg_color="transparent")
        inner_control.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkLabel(inner_control, text="Source:", font=("Segoe UI", 12), text_color=TEXT_MUTED).pack(side="left", padx=(4, 8))
        self.lang_var = ctk.StringVar(value="Japanese")
        self.lang_menu = ctk.CTkOptionMenu(
            inner_control, 
            variable=self.lang_var, 
            values=list(SRC_LANGS.keys()),
            width=150, 
            command=self._on_lang_change,
            fg_color=BG_INPUT,
            button_color=BG_INPUT,
            button_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=BORDER_COLOR,
            corner_radius=6
        )
        self.lang_menu.pack(side="left")
        
        ctk.CTkLabel(inner_control, text="→  Thai", font=("Segoe UI Semibold", 12), text_color=ACCENT_COLOR).pack(side="left", padx=16)
        
        self.capture_btn = ctk.CTkButton(
            inner_control, 
            text="📷 Capture Screen", 
            width=130, 
            command=self._start_capture,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            text_color="#0b0d12",
            font=("Segoe UI Semibold", 12),
            corner_radius=6
        )
        self.capture_btn.pack(side="right", padx=(0, 4))

        # Row 2: Dynamic Comic Style Selector (Manga / Manhwa / Manhua)
        inner_style = ctk.CTkFrame(control_card, fg_color="transparent")
        inner_style.pack(fill="x", padx=12, pady=(4, 12))
        
        ctk.CTkLabel(inner_style, text="Translation Style:", font=("Segoe UI", 11), text_color=TEXT_MUTED).pack(side="left", padx=(4, 8))
        self.style_var = ctk.StringVar(value=self.cfg.get("comic_type", "Manga (Japanese)"))
        self.style_menu = ctk.CTkOptionMenu(
            inner_style, 
            variable=self.style_var, 
            values=COMIC_TYPES,
            width=220, 
            fg_color=BG_INPUT,
            button_color=BG_INPUT,
            button_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=BORDER_COLOR,
            corner_radius=6
        )
        self.style_menu.pack(side="left")

        # --- Settings Tabs ---
        self.tabview = ctk.CTkTabview(
            self.root, 
            height=260,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_INPUT,
            segmented_button_selected_color=BORDER_COLOR,
            segmented_button_selected_hover_color=BORDER_COLOR,
            segmented_button_unselected_color=BG_INPUT,
            segmented_button_unselected_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            corner_radius=10
        )
        self.tabview.pack(fill="x", padx=20, pady=8)
        
        tab_standard = self.tabview.add("Standard API")
        tab_9router = self.tabview.add("9Router Gateway")
        tab_appearance = self.tabview.add("Appearance")

        # --- Standard API tab ---
        r1 = ctk.CTkFrame(tab_standard, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(r1, text="Backend:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=70, anchor="w").pack(side="left")
        self.backend_var = ctk.StringVar(value=self.cfg.get("backend", TRANSLATE_BACKENDS[0]))
        self.backend_menu = ctk.CTkOptionMenu(
            r1, 
            variable=self.backend_var, 
            values=TRANSLATE_BACKENDS,
            width=220, 
            command=self._on_backend_change,
            fg_color=BG_INPUT,
            button_color=BG_INPUT,
            button_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=BORDER_COLOR,
            corner_radius=6
        )
        self.backend_menu.pack(side="left", padx=8)

        r2 = ctk.CTkFrame(tab_standard, fg_color="transparent")
        r2.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(r2, text="API Key:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=70, anchor="w").pack(side="left")
        self.key_entry = ctk.CTkEntry(
            r2, 
            show="•", 
            width=280, 
            placeholder_text="sk-... or AIza...",
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.key_entry.pack(side="left", padx=8)
        if self.cfg.get("api_key"):
            self.key_entry.insert(0, self.cfg["api_key"])

        r3 = ctk.CTkFrame(tab_standard, fg_color="transparent")
        r3.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(r3, text="Model:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=70, anchor="w").pack(side="left")
        self.model_entry = ctk.CTkEntry(
            r3, 
            width=200, 
            placeholder_text="auto (gpt-4o-mini / gemini-2.0-flash-lite)",
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.model_entry.pack(side="left", padx=8)
        if self.cfg.get("model"):
            self.model_entry.insert(0, self.cfg["model"])

        r4 = ctk.CTkFrame(tab_standard, fg_color="transparent")
        r4.pack(fill="x", padx=12, pady=(4, 12))
        ctk.CTkLabel(r4, text="Base URL:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=70, anchor="w").pack(side="left")
        self.url_entry = ctk.CTkEntry(
            r4, 
            width=280, 
            placeholder_text="(OpenAI only) custom endpoint",
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.url_entry.pack(side="left", padx=8)
        if self.cfg.get("base_url"):
            self.url_entry.insert(0, self.cfg["base_url"])

        # --- 9Router tab ---
        nr1 = ctk.CTkFrame(tab_9router, fg_color="transparent")
        nr1.pack(fill="x", padx=12, pady=(16, 4))
        ctk.CTkLabel(nr1, text="Gateway URL:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=80, anchor="w").pack(side="left")
        self.nr_url_entry = ctk.CTkEntry(
            nr1, 
            width=280, 
            placeholder_text="http://localhost:20128",
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.nr_url_entry.pack(side="left", padx=8)
        self.nr_url_entry.insert(0, self.cfg.get("ninerouter_url", "http://localhost:20128"))

        nr2 = ctk.CTkFrame(tab_9router, fg_color="transparent")
        nr2.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(nr2, text="Router Key:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=80, anchor="w").pack(side="left")
        self.nr_key_entry = ctk.CTkEntry(
            nr2, 
            show="•", 
            width=280, 
            placeholder_text="sk-...",
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.nr_key_entry.pack(side="left", padx=8)
        self.nr_key_entry.insert(0, self.cfg.get("ninerouter_key", "sk-..."))

        nr3 = ctk.CTkFrame(tab_9router, fg_color="transparent")
        nr3.pack(fill="x", padx=12, pady=(4, 16))
        ctk.CTkLabel(nr3, text="Combo Model:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=80, anchor="w").pack(side="left")
        self.nr_model_entry = ctk.CTkEntry(
            nr3, 
            width=200, 
            placeholder_text="my-combo",
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.nr_model_entry.pack(side="left", padx=8)
        self.nr_model_entry.insert(0, self.cfg.get("ninerouter_model", "my-combo"))

        # --- Appearance tab ---
        ap_scroll = ctk.CTkScrollableFrame(tab_appearance, fg_color="transparent", height=170)
        ap_scroll.pack(fill="both", expand=True)

        ap1 = ctk.CTkFrame(ap_scroll, fg_color="transparent")
        ap1.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(ap1, text="Font Family:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left")
        self.font_family_var = ctk.StringVar(value=self.cfg.get("font_family", "Leelawadee UI"))
        self.font_family_combo = ctk.CTkComboBox(
            ap1,
            variable=self.font_family_var,
            values=["Leelawadee UI", "Segoe UI", "Tahoma", "Arial", "Cordia New", "Angsana New", "Microsoft Sans Serif"],
            width=200,
            fg_color=BG_INPUT,
            button_color=BG_INPUT,
            button_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=BORDER_COLOR,
            corner_radius=6
        )
        self.font_family_combo.pack(side="left", padx=8)

        ap2 = ctk.CTkFrame(ap_scroll, fg_color="transparent")
        ap2.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(ap2, text="Max Font Size:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left")
        self.font_size_var = ctk.StringVar(value=str(self.cfg.get("max_font_size", 24)))
        self.font_size_combo = ctk.CTkComboBox(
            ap2,
            variable=self.font_size_var,
            values=["16", "20", "24", "28", "32", "36", "40", "48"],
            width=100,
            fg_color=BG_INPUT,
            button_color=BG_INPUT,
            button_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=BORDER_COLOR,
            corner_radius=6
        )
        self.font_size_combo.pack(side="left", padx=8)

        ap3 = ctk.CTkFrame(ap_scroll, fg_color="transparent")
        ap3.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(ap3, text="Font Weight:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left")
        self.font_weight_var = ctk.StringVar(value=self.cfg.get("font_weight", "bold"))
        self.font_weight_menu = ctk.CTkOptionMenu(
            ap3,
            variable=self.font_weight_var,
            values=["bold", "normal"],
            width=120,
            fg_color=BG_INPUT,
            button_color=BG_INPUT,
            button_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            dropdown_hover_color=BORDER_COLOR,
            corner_radius=6
        )
        self.font_weight_menu.pack(side="left", padx=8)

        # Inpainting Toggle
        ap_inpaint = ctk.CTkFrame(ap_scroll, fg_color="transparent")
        ap_inpaint.pack(fill="x", padx=4, pady=4)
        self.inpaint_var = tk.BooleanVar(value=self.cfg.get("inpaint_enabled", True))
        self.inpaint_cb = ctk.CTkCheckBox(
            ap_inpaint, 
            text="Enable OpenCV Smart Inpainting (ลบตัวอักษรลายเส้นเนียนกริบ)", 
            variable=self.inpaint_var,
            text_color=TEXT_PRIMARY,
            font=("Segoe UI", 11),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            corner_radius=4
        )
        self.inpaint_cb.pack(side="left")

        # Obsidian Sync Feature Layout
        ap4 = ctk.CTkFrame(ap_scroll, fg_color="transparent")
        ap4.pack(fill="x", padx=4, pady=4)
        self.obsidian_sync_var = tk.BooleanVar(value=self.cfg.get("obsidian_sync", False))
        self.obsidian_sync_cb = ctk.CTkCheckBox(
            ap4, 
            text="Sync history to Obsidian Vault", 
            variable=self.obsidian_sync_var,
            text_color=TEXT_PRIMARY,
            font=("Segoe UI", 11),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            corner_radius=4
        )
        self.obsidian_sync_cb.pack(side="left")

        ap5 = ctk.CTkFrame(ap_scroll, fg_color="transparent")
        ap5.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(ap5, text="Obsidian Path:", font=("Segoe UI", 11), text_color=TEXT_MUTED, width=110, anchor="w").pack(side="left")
        self.obsidian_path_entry = ctk.CTkEntry(
            ap5, 
            width=260, 
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6
        )
        self.obsidian_path_entry.pack(side="left", padx=8)
        self.obsidian_path_entry.insert(0, self.cfg.get("obsidian_path", "C:\\Users\\narudom\\Documents\\Obsidian Vault"))

        # Switch default tab based on config
        if self.cfg.get("backend") == "9Router API":
            self.tabview.set("9Router Gateway")
        else:
            self.tabview.set("Standard API")

        # Save Button
        self.save_btn = ctk.CTkButton(
            self.root, 
            text="💾 Save Configurations", 
            width=150, 
            command=self._save_settings,
            fg_color=BG_INPUT,
            hover_color=BORDER_COLOR,
            border_width=1,
            border_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            font=("Segoe UI Semibold", 11),
            corner_radius=6
        )
        self.save_btn.pack(pady=4)

        # --- Logs Area ---
        log_label_row = ctk.CTkFrame(self.root, fg_color="transparent")
        log_label_row.pack(fill="x", padx=20, pady=(8, 0))
        ctk.CTkLabel(
            log_label_row, 
            text="SYSTEM LOGS", 
            font=("Segoe UI Semibold", 10), 
            text_color=TEXT_MUTED
        ).pack(side="left")

        self.log_box = ctk.CTkTextbox(
            self.root, 
            height=130, 
            font=("Consolas", 10), 
            fg_color=BG_CARD,
            text_color=TEXT_PRIMARY,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=8
        )
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(4, 8))

        # --- Footer Status Bar ---
        footer_line = ctk.CTkFrame(self.root, height=1, fg_color=BORDER_COLOR)
        footer_line.pack(fill="x", padx=20, pady=(4, 0))

        footer = ctk.CTkFrame(self.root, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(6, 10))

        # Colored status dot (indicator)
        self.status_dot = ctk.CTkLabel(
            footer, 
            text="●", 
            font=("Segoe UI", 12), 
            text_color=ACCENT_COLOR
        )
        self.status_dot.pack(side="left", padx=(0, 6))

        self.status = ctk.CTkLabel(
            footer, 
            text="Initializing OCR model...", 
            font=("Segoe UI", 11), 
            text_color=TEXT_MUTED
        )
        self.status.pack(side="left")

        # Premium Nong Kung Signoff
        self.nong_kung_label = ctk.CTkLabel(
            footer, 
            text="น้องกุ้ง Engine 🦐", 
            font=("Segoe UI Italic", 11), 
            text_color=TEXT_MUTED
        )
        self.nong_kung_label.pack(side="right")

    def _preload_ocr(self):
        with self.reader_lock:
            if self.reader is None:
                self._log("Preloading default OCR model...")
                try:
                    lang_codes = SRC_LANGS[self.current_lang_key]
                    self.reader = easyocr.Reader(lang_codes, gpu=True)
                    self._log("OCR model preloaded ✓")
                    self._set_status("Ready — press Ctrl+Shift+T to capture", "ready")
                except Exception as e:
                    self._log(f"Failed to preload OCR: {e}")
                    self._set_status("OCR load failed. Click Capture or switch language to retry.", "error")

    def _log(self, msg):
        def _do():
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
        self.root.after(0, _do)

    def _on_lang_change(self, val):
        self.current_lang_key = val
        self._set_status(f"Switching language to {val}...", "process")
        self._log(f"Language changed to {val}. Reloading OCR in background...")
        
        # Auto-match Comic Style dropdown based on language source to assist the user
        if val == "Japanese":
            self.style_var.set("Manga (Japanese)")
        elif val == "Korean":
            self.style_var.set("Manhwa (Korean)")
        elif val == "Chinese":
            self.style_var.set("Manhua (Chinese)")
        
        def reload():
            with self.reader_lock:
                try:
                    lang_codes = SRC_LANGS[val]
                    self.reader = easyocr.Reader(lang_codes, gpu=True)
                    self._log(f"OCR model loaded for {val} ✓")
                    self._set_status("Ready — press Ctrl+Shift+T to capture", "ready")
                except Exception as e:
                    self._log(f"Failed to load OCR for {val}: {e}")
                    self._set_status("OCR load failed", "error")
        
        threading.Thread(target=reload, daemon=True).start()

    def _on_backend_change(self, val):
        self.cfg["backend"] = val

    def _save_settings(self):
        self.cfg["backend"] = self.backend_var.get()
        self.cfg["api_key"] = self.key_entry.get().strip()
        self.cfg["model"] = self.model_entry.get().strip()
        self.cfg["base_url"] = self.url_entry.get().strip()
        
        self.cfg["ninerouter_url"] = self.nr_url_entry.get().strip()
        self.cfg["ninerouter_key"] = self.nr_key_entry.get().strip()
        self.cfg["ninerouter_model"] = self.nr_model_entry.get().strip()
        
        # Save appearance settings
        self.cfg["font_family"] = self.font_family_combo.get().strip()
        try:
            self.cfg["max_font_size"] = int(self.font_size_combo.get().strip())
        except ValueError:
            self.cfg["max_font_size"] = 24
        self.cfg["font_weight"] = self.font_weight_var.get()
        
        # Save Inpainting setting
        self.cfg["inpaint_enabled"] = self.inpaint_var.get()
        
        # Save comic type setting (Manual selection)
        self.cfg["comic_type"] = self.style_var.get()
        
        # Save Obsidian settings
        self.cfg["obsidian_sync"] = self.obsidian_sync_var.get()
        self.cfg["obsidian_path"] = self.obsidian_path_entry.get().strip()
        
        save_config(self.cfg)
        self._set_status("Settings saved ✓", "success")
        self._log(f"Saved: backend={self.cfg['backend']}, style={self.cfg['comic_type']}, inpaint={self.cfg['inpaint_enabled']}")

    def _set_status(self, msg, state="ready"):
        color_map = {
            "ready": ACCENT_COLOR,
            "process": "#f59e0b",  # Orange
            "error": "#f87171",    # Soft Red
            "success": "#34d399"   # Emerald Green
        }
        dot_color = color_map.get(state, ACCENT_COLOR)
        def _do():
            self.status.configure(text=msg)
            self.status_dot.configure(text_color=dot_color)
        self.root.after(0, _do)

    def _register_hotkey(self):
        keyboard.add_hotkey(HOTKEY, lambda: self.root.after(0, self._start_capture))

    def _sync_to_obsidian(self, blocks):
        if not self.cfg.get("obsidian_sync", False):
            return
        
        obsidian_vault = self.cfg.get("obsidian_path", "").strip()
        if not obsidian_vault or not os.path.exists(obsidian_vault):
            self._log("Obsidian Error: Vault path does not exist!")
            return

        target_file = os.path.join(obsidian_vault, "Manga Translations.md")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lang = self.current_lang_key
        
        content = f"\n### 📖 Translation Log - {timestamp} ({lang})\n"
        content += "| Original Text | Thai Translation |\n"
        content += "| --- | --- |\n"
        for b in blocks:
            orig = b["original"].replace("\n", " ").replace("|", "\\|")
            trans = b["text"].replace("\n", " ").replace("|", "\\|")
            content += f"| {orig} | {trans} |\n"
            
        try:
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(content)
            self._log(f"Obsidian: Synced {len(blocks)} translations ✓")
        except Exception as ex:
            self._log(f"Obsidian Sync Failed: {ex}")

    def _start_capture(self):
        if self.is_processing:
            return
        if self.overlay:
            try:
                self.overlay.destroy()
            except Exception:
                pass
        self.root.withdraw()
        self.root.after(250, self._open_selector)

    def _open_selector(self):
        sel = ScreenSelector(self._on_region_selected)
        sel.wait_window()
        if not hasattr(self, '_capture_fired') or not self._capture_fired:
            self.root.deiconify()
        self._capture_fired = False

    def _on_region_selected(self, bbox):
        self._capture_fired = True
        self.root.deiconify()
        self.root.lift()
        self.is_processing = True
        self.capture_btn.configure(state="disabled")
        threading.Thread(target=self._process, args=(bbox,), daemon=True).start()

    def _process(self, bbox):
        try:
            self._set_status("Capturing...", "process")
            self._log(f"Region: {bbox}")

            img = ImageGrab.grab(bbox=bbox)

            self._set_status("Running OCR...", "process")
            
            with self.reader_lock:
                if self.reader is None:
                    self._set_status("Loading OCR model...", "process")
                    self._log("Loading OCR model...")
                    lang_codes = SRC_LANGS[self.current_lang_key]
                    self.reader = easyocr.Reader(lang_codes, gpu=True)
                    self._log("OCR model loaded ✓")
                reader = self.reader

            w, h = img.size
            try:
                resample_filter = Image.Resampling.LANCZOS
            except AttributeError:
                resample_filter = Image.LANCZOS
            img_large = img.resize((w * 2, h * 2), resample_filter)
            img_np = np.array(img_large)
            
            results = reader.readtext(img_np, detail=1, paragraph=True)

            scaled_results = []
            for item in results:
                if len(item) == 2:
                    box, orig_text = item
                    conf = 1.0
                else:
                    box, orig_text, conf = item
                scaled_box = [[p[0] / 2, p[1] / 2] for p in box]
                scaled_results.append((scaled_box, orig_text, conf))
            results = scaled_results

            if not results:
                self._set_status("No text detected", "ready")
                self._log("No text found in region")
                return

            self._log(f"Found {len(results)} text blocks")
            self._set_status("Translating...", "process")

            self.cfg = load_config()

            blocks = []
            all_texts = [r[1] for r in results]
            primary_lang = SRC_LANGS[self.current_lang_key][0]

            try:
                translated_parts = do_translate(all_texts, primary_lang, self.cfg)
            except Exception as e:
                self._log(f"Translation error: {e}")
                self._set_status(f"Error: {e}", "error")
                return

            if len(translated_parts) != len(results):
                self._log(f"Warning: Translation count mismatch (got {len(translated_parts)}, expected {len(results)})")
                while len(translated_parts) < len(results):
                    translated_parts.append("...")

            for i, (box, orig_text, conf) in enumerate(results):
                trans = translated_parts[i] if i < len(translated_parts) else orig_text
                blocks.append({"box": box, "text": trans, "original": orig_text})
                self._log(f"  [{orig_text}] → [{trans}]")

            # --- OpenCV Smart Inpainting (ลบตัวอักษรเดิมด้วย AI ลายเส้น) ---
            inpainted_img = img
            if self.cfg.get("inpaint_enabled", True):
                self._set_status("Inpainting background...", "process")
                try:
                    # Convert PIL Image to OpenCV Format (BGR)
                    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    
                    # Create a black mask (same size as image)
                    mask = np.zeros(cv_img.shape[:2], dtype=np.uint8)
                    
                    # Draw white rectangles on mask where text blocks are located
                    for b in blocks:
                        box = b["box"]
                        xs = [p[0] for p in box]
                        ys = [p[1] for p in box]
                        bx0, by0 = int(min(xs)), int(min(ys))
                        bx1, by1 = int(max(xs)), int(max(ys))
                        
                        # Add padding to ensure the text boundary is fully covered
                        pad = 2
                        cv2.rectangle(
                            mask, 
                            (max(0, bx0 - pad), max(0, by0 - pad)), 
                            (min(w, bx1 + pad), min(h, by1 + pad)), 
                            255, 
                            -1
                        )
                    
                    # Run OpenCV Inpainting (Telea algorithm - works exceptionally well for manga line art)
                    inpainted_cv = cv2.inpaint(cv_img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
                    
                    # Convert back to PIL Image
                    inpainted_img = Image.fromarray(cv2.cvtColor(inpainted_cv, cv2.COLOR_BGR2RGB))
                    self._log("Background Inpainted successfully ✓")
                except Exception as ie:
                    self._log(f"Inpainting failed: {ie}, falling back to original image")
                    inpainted_img = img

            # Sync to Obsidian if enabled
            self._sync_to_obsidian(blocks)

            def show_overlay():
                self.overlay = OverlayWindow(bbox, blocks, img, inpainted_img, self.cfg)
                self._set_status(f"Done ✓ — {len(blocks)} blocks translated", "success")
            self.root.after(0, show_overlay)

        except Exception as ex:
            self._log(f"Process error: {ex}")
            self._set_status(f"Error: {ex}", "error")
        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.capture_btn.configure(state="normal"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = TranslatorApp()
    app.run()
