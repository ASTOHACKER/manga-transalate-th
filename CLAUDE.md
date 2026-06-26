# CLAUDE.md

## Developer Guide for Manga Screen Translator v2

This project is a Windows Tkinter desktop utility that grabs screen regions, performs OCR, and overlays high-quality Thai translations using OpenAI, Gemini, or a local/remote 9Router Gateway.

### Environment & Executable
- **Python Path:** `C:\Users\narudom\AppData\Local\Programs\Python\Python312\python.exe`
- **Dependencies:** `customtkinter`, `easyocr`, `pillow`, `keyboard`, `deep-translator`, `numpy`, `opencv-python`.
- **Run Script:** `C:\Users\narudom\Desktop\manga-translator\run.bat` (runs silently using `pythonw.exe`).

### Key Code Patterns & Quirks
1. **DPI Awareness (Critical):**
   `ctypes.windll.shcore.SetProcessDpiAwareness(2)` is called at boot. This ensures `ImageGrab.grab` coordinates map 1:1 with screen pixels on high-DPI monitors.
2. **EasyOCR Threading & Safety:**
   `easyocr.Reader` initialization is heavy. It is preloaded in a background thread to prevent UI freezing. Access is guarded by `self.reader_lock`.
3. **9Router Streaming (SSE):**
   9Router gateway returns SSE chunks (`data: ...`). The parser splits and decodes chunks inline instead of doing a direct `json.loads` on raw response.
4. **Manga/Manhwa/Manhua Translation Prompts:**
   The `get_translation_prompt(src_lang_name)` function generates distinct system prompts mapping to the medium's style (Shonen Manga, Modern Webtoon Manhwa, or Cultivation Manhua).
5. **OpenCV Inpainting & Transparent Clipping:**
   - When enabled (`inpaint_enabled`), `cv2.inpaint(..., cv2.INPAINT_TELEA)` deletes original text.
   - **Clipped Bounding-Box Overlay:** The overlay window uses a black transparent background (`-transparentcolor = "black"`). Only the inpainted speech bubble slices (with padding) and the anti-aliased Thai text are drawn. This leaves all non-text areas of the manga 100% visible, preventing any overlay boxes from obscuring the artwork outside the bubbles.
6. **Obsidian Integration:**
   Appends a Markdown table log of every translation batch to `C:\Users\narudom\Documents\Obsidian Vault\Manga Translations.md` if `obsidian_sync` is checked.
7. **Thai Typography:**
   `_wrap_thai_text` uses pixel-width measurements via `font.measure` to wrap Thai text without mid-syllable cuts. Diacritics padding is added to prevent line collisions.
8. **Interactive Peeking:**
   Holding `Ctrl` or `Shift` temporarily sets overlay transparency to `alpha = 0` so the user can quickly peek at the raw text underneath.

### Troubleshooting
- **ModuleNotFoundError ('PIL', 'cv2', etc.):** Ensure you are running with the system Python path, not the hermes virtualenv.
- **TclError (unknown font style "medium"):** Use empty font weight or standard `"bold"`/`"normal"`. Tkinter on Windows does not recognize `"medium"`.
- **Dataroot DataLoader UserWarning:** Safe to ignore (occurs on CPU-only machines running EasyOCR).
