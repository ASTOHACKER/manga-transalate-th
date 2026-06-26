# Workspace Context: Manga Screen Translator v2

## Description
A lightweight Python desktop application that captures a selected screen region, extracts text via OCR, translates it to Thai, and overlays the translated text seamlessly back onto the screen. Designed for reading foreign-language manga/comics.

## Tech Stack
- **Language:** Python 3.12+
- **GUI:** `customtkinter` (Modern dark-themed Tkinter), standard `tkinter` for overlays.
- **OCR & Pre-processing:** `easyocr` (PyTorch-based offline OCR) with **2x spatial LANCZOS upscaling** for high-accuracy recognition on small/handwritten fonts.
- **Translation:** `deep-translator` (Google Translate free), custom `urllib` API calls for OpenAI, Gemini, and local/remote **9Router AI gateway** (defaulting to combo models like `my-combo`).
- **Typography & Formatting:** `pythainlp` for authentic grammatical Thai word wrapping, preventing vowel separation, and custom font mapping supporting premium Thai fonts.
- **Image Processing:** `opencv-python` for contour-based smart bubble expansion, inpainting, and specialized SFX layout formatting.
- **Integration:** **Obsidian Vault** synchronization for saving translation logs and building a personal bilingual vocabulary database.
- **Hotkeys / Controls:** `keyboard` for global hotkey, `Pillow` (PIL) for screen grabbing.

## File Structure
- `translator.py`: Main application code (settings, OCR, 9Router streaming parser, OpenCV Telea Inpainting, smart Thai text wrapping).
- `run.bat`: Quick-launch script using `pythonw.exe` to run the app silently without showing a terminal window.
- `config.json` (gitignored/local): Stores API keys, selected backend, custom models, and appearance/Obsidian sync preferences.
- `AGENTS.md`: Agent guidelines, core rules, and developer quick start.
- `CLAUDE.md`: System specs, code patterns (DPI, Thread safety, SSE streaming, Inpainting, Obsidian), and troubleshooting.

## Key Workflows
1. **Trigger Capture:** Press `Ctrl+Shift+T` globally or click **📷 Capture** in the UI.
2. **Select Region:** Click and drag a box over the manga panel. Press `Escape` to cancel.
3. **2x Upscaling & Paragraph OCR:** 
   - Image is cropped to the selected bounding box.
   - Upscaled 2x to improve accuracy on tiny/handwritten texts.
   - EasyOCR extracts text blocks with coordinates using `paragraph=True` to group lines into single speech bubbles.
4. **API / 9Router Translation & Contextual Engine:**
   - Texts are sent in a clean JSON format array to preserve order and structure.
   - Standard APIs or the local 9Router gateway (at `http://localhost:20128` using combo models like `my-combo`) translate the array to Thai.
   - The engine parses and translates using **5 Golden Localization Rules** (Dynamic character voice, localized puns, SFX classification, space optimization/summarization, and natural spoken Thai) to bypass typical OCR noise.
   - Adapts prompt dynamic styling for **Manga**, **Manhwa**, and **Manhua** automatically.
5. **Obsidian Sync & History Logging:**
   - When enabled in the Appearance tab, translations are saved as a structured Markdown table in the user's Obsidian Vault at `C:\Users\narudom\Documents\Obsidian Vault\Manga Translations.md`.
6. **Appearance & Interactive Peeking:**
   - Custom fonts (`font_family`), maximum size (`max_font_size`), and font weights (`bold` / `normal`) are configurable and persistent. Supports premium fonts with automatic Windows fallback.
   - Users can hold **Ctrl** or **Shift** to temporarily hide the translation overlay and peek at the original manga text.
7. **OpenCV Smart Inpainting & Overlay Render:** 
   - **Smart Speech Bubble Contour Detection:** Uses OpenCV grayscale, thresholding, and contour analysis to locate the exact physical boundaries of speech bubbles, expanding bounding boxes to fit text cleanly without overlapping lines.
   - Telea algorithm deletes original foreign text using surrounding line art pixels, making a seamless canvas.
   - If disabled, renders a matching rounded-corner bubble background to cover the original text.
   - **Specialized SFX Typesetting:** Implicitly detects translated sound effects (`[SFX: ...]`), renders them using stylized handwriting fonts (e.g. Sriracha, Pattaya) in bright golden-yellow with heavy dark orange strokes, and bypasses inpainting to preserve the underlying manga action lines.
   - **Transparent Canvas Clipping:** Renders inpainted background chunks and translated Thai text onto a fully transparent window layer. Only the speech bubble bounding box areas are drawn, keeping the original artwork outside the bubbles 100% visible and untouched.
   - Translated Thai is rendered with appropriate dark/light text color, custom font, and automatic scaling/wrapping.
