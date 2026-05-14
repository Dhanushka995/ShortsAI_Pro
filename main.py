# =============================================================================
#  ShortsAI Pro - Viral Caption Generator
#  Author  : Chief Architect Edition
#  Version : 1.0.0
#  Stack   : customtkinter | google-generativeai | openai | threading
#
#  PyInstaller build command:
#    pyinstaller --name "ShortsAI Pro" --windowed --collect-all customtkinter \
#                --collect-all google.generativeai --onefile main.py
# =============================================================================

from __future__ import annotations

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

# ── PyInstaller resource path helper ──────────────────────────────────────────
def resource_path(relative_path: str) -> str:
    """Return the absolute path – works both in dev and PyInstaller bundles."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


# ── Lazy-import heavy dependencies so errors surface clearly ──────────────────
try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit(
        "customtkinter not found.  Install with:  pip install customtkinter"
    )

try:
    from google import genai as google_genai
    from google.genai import types as google_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# =============================================================================
#  Constants
# =============================================================================
APP_TITLE        = "ShortsAI Pro – Viral Caption Generator"
WINDOW_SIZE      = "1100x820"
CLIP_COUNT       = 5
RATE_LIMIT_DELAY = 15     # seconds between clips (free-tier RPM guard)
AUTO_PAUSE_DELAY = 65     # seconds to wait after 429 with no backup key

DEFAULT_MODEL    = "gemini-2.0-flash"
DEFAULT_BASE_URL = ""     # empty → native Gemini

VIDEO_TYPES = [
    "Ranking Video (Top 5 to 1)",
    "Normal Compilation",
]

# Colour tokens
CLR_SUCCESS  = "#1DB954"   # green
CLR_ERROR    = "#E53935"   # red
CLR_WARNING  = "#FFA726"   # amber
CLR_ACCENT   = "#1565C0"   # blue
CLR_BTN_NORM = "#1E88E5"
CLR_BTN_DONE = "#2E7D32"
CLR_BTN_HVRN = "#1565C0"
CLR_BTN_HVRD = "#1B5E20"

FONT_MONO = ("Consolas", 12)
FONT_BOLD = ("Segoe UI", 11, "bold")
FONT_SM   = ("Segoe UI", 10)
FONT_LG   = ("Segoe UI", 13, "bold")


# =============================================================================
#  AIClient  – unified wrapper for native Gemini and OpenAI-compatible APIs
# =============================================================================
class AIClient:
    """
    Wraps both google-generativeai (native Gemini File API) and
    openai-compatible endpoints (OpenRouter, Groq, NVIDIA, etc.).

    Selection logic
    ---------------
    • If base_url is empty/None  →  use native Gemini (uploads video via File API)
    • If base_url is provided    →  use openai package pointed at that base URL
    """

    def __init__(
        self,
        api_key:  str,
        base_url: str  = "",
        model:    str  = DEFAULT_MODEL,
    ) -> None:
        self.api_key  = api_key.strip()
        self.base_url = base_url.strip()
        self.model    = model.strip() or DEFAULT_MODEL
        self._is_native_gemini = not self.base_url

    # ------------------------------------------------------------------
    def _get_gemini_client(self):
        if not GOOGLE_GENAI_AVAILABLE:
            raise RuntimeError(
                "google-genai package is not installed.\n"
                "Run: pip install google-genai"
            )
        return google_genai.Client(api_key=self.api_key)

    def _get_openai_client(self):
        if not OPENAI_AVAILABLE:
            raise RuntimeError(
                "openai package is not installed.\n"
                "Run: pip install openai"
            )
        return openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    # ------------------------------------------------------------------
    def validate(self) -> tuple[bool, str]:
        """
        Send a minimal request to verify the key & endpoint.
        Returns (success: bool, message: str).
        """
        try:
            if self._is_native_gemini:
                client   = self._get_gemini_client()
                response = client.models.generate_content(
                    model=self.model,
                    contents="hi",
                )
                _ = response.text          # trigger any lazy parse errors
                return True, "✅ Connected successfully"
            else:
                client = self._get_openai_client()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=5,
                )
                _ = response.choices[0].message.content
                return True, "✅ Connected successfully"

        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                return False, "⚠️ Rate limited (key seems valid)"
            return False, f"🔴 Error: {_truncate(err, 80)}"

    # ------------------------------------------------------------------
    def generate_caption(
        self,
        video_path:  str,
        clip_index:  int,
        topic:       str,
        video_type:  str,
        status_cb:   Optional[callable] = None,
    ) -> str:
        """
        Generate viral captions for a single video clip.

        Parameters
        ----------
        video_path  : full path to the .mp4 file
        clip_index  : 0-based index (0 = clip #1)
        topic       : user-provided topic string
        video_type  : one of VIDEO_TYPES
        status_cb   : optional callback(msg: str) for progress updates

        Returns the raw text response from the model.
        """
        prompt = self._build_prompt(clip_index, topic, video_type)

        if self._is_native_gemini:
            return self._generate_gemini(video_path, prompt, status_cb)
        else:
            return self._generate_openai(video_path, prompt, status_cb)

    # ------------------------------------------------------------------
    def _build_prompt(self, clip_index: int, topic: str, video_type: str) -> str:
        topic_line = f'The video topic is: "{topic}".' if topic.strip() else ""

        if "Ranking" in video_type:
            rank    = CLIP_COUNT - clip_index          # 5,4,3,2,1
            rank_ctx = (
                f"This is clip number {rank} in a Top {CLIP_COUNT} countdown. "
                f"Make the hype and energy match this rank position "
                f"({'ULTIMATE HYPE – this is #1!' if rank == 1 else f'building energy – ranked #{rank}'})."
            )
        else:
            rank_ctx = "This is one clip in a compilation video."

        return (
            f"{topic_line} {rank_ctx}\n\n"
            "Watch the video carefully including audio and visuals. "
            "Give exactly 3 short, punchy, viral English text overlays "
            "(max 2-4 words each) with relevant emojis using modern internet slang. "
            "Also provide a brief Sinhala meaning for each overlay. "
            "Format your response STRICTLY as:\n"
            "1. [English overlay with emoji] | [Sinhala meaning]\n"
            "2. [English overlay with emoji] | [Sinhala meaning]\n"
            "3. [English overlay with emoji] | [Sinhala meaning]\n\n"
            "Do NOT include any extra commentary, explanations, or formatting "
            "outside of this numbered list."
        )

    # ------------------------------------------------------------------
    def _generate_gemini(
        self,
        video_path: str,
        prompt:     str,
        status_cb:  Optional[callable],
    ) -> str:
        client = self._get_gemini_client()

        if status_cb:
            status_cb("📤 Uploading video to Gemini File API…")

        # Upload the video file
        with open(video_path, "rb") as fh:
            uploaded = client.files.upload(
                file=fh,
                config=google_types.UploadFileConfig(
                    mime_type="video/mp4",
                    display_name=os.path.basename(video_path),
                ),
            )

        # Poll until the file is ACTIVE
        if status_cb:
            status_cb("⏳ Processing video on Gemini servers…")

        poll_start = time.time()
        while True:
            file_info = client.files.get(name=uploaded.name)
            state     = file_info.state.name if file_info.state else "UNKNOWN"
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise RuntimeError("Gemini File API: file processing FAILED.")
            if time.time() - poll_start > 300:
                raise TimeoutError("Gemini File API: timed out waiting for ACTIVE state.")
            time.sleep(5)

        if status_cb:
            status_cb("🤖 Generating captions with Gemini…")

        response = client.models.generate_content(
            model=self.model,
            contents=[uploaded, prompt],
        )

        # Best-effort cleanup (non-fatal if it fails)
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

        return response.text

    # ------------------------------------------------------------------
    def _generate_openai(
        self,
        video_path: str,
        prompt:     str,
        status_cb:  Optional[callable],
    ) -> str:
        """
        OpenAI-compatible endpoint.  Video is encoded as base64 data URL
        if the model supports vision, otherwise we send a text-only prompt
        with a note about the file name (works for text-only models).
        """
        client = self._get_openai_client()

        if status_cb:
            status_cb("🤖 Generating captions via custom endpoint…")

        # Try to send as vision (base64).  Some endpoints (Groq, NVIDIA) support it.
        try:
            import base64
            with open(video_path, "rb") as fh:
                video_b64 = base64.b64encode(fh.read()).decode("utf-8")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type":  "text",
                            "text":  prompt,
                        },
                        {
                            "type": "image_url",          # many APIs accept video here too
                            "image_url": {
                                "url": f"data:video/mp4;base64,{video_b64}",
                            },
                        },
                    ],
                }
            ]

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content

        except Exception as vision_err:
            # Fallback: text-only with file context
            if "unsupported" in str(vision_err).lower() or \
               "content_type" in str(vision_err).lower() or \
               "invalid" in str(vision_err).lower():

                file_name = os.path.basename(video_path)
                text_prompt = (
                    f"[Video file: {file_name}]\n\n"
                    "Assume you have watched this video clip. "
                    + prompt
                )
                messages = [{"role": "user", "content": text_prompt}]
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
                return response.choices[0].message.content
            else:
                raise   # re-raise genuine errors (429, auth, etc.)


# =============================================================================
#  Utility helpers
# =============================================================================
def _truncate(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[:max_len] + "…"


def _extract_english(raw_text: str) -> str:
    """
    Extract ONLY the English parts (before the '|') from the numbered list.
    Returns a newline-joined string ready for clipboard pasting into CapCut.
    """
    lines   = []
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Match "1. something | something"  or  "1) something | something"
        if "|" in line:
            english_part = line.split("|")[0]
            # Strip leading "1. " / "1) " numbering
            for sep in (". ", ") ", "- "):
                if sep in english_part:
                    parts = english_part.split(sep, 1)
                    if len(parts) == 2 and parts[0].strip().isdigit():
                        english_part = parts[1]
                        break
            lines.append(english_part.strip())
        elif line:
            lines.append(line)
    return "\n".join(lines) if lines else raw_text.strip()


# =============================================================================
#  ClipRow  – a self-contained row widget: [Upload Btn] [Output Box] [Copy Btn]
# =============================================================================
class ClipRow:
    """Manages one clip slot (upload button + output textbox + copy button)."""

    def __init__(self, parent: ctk.CTkFrame, clip_num: int, app: "ShortsAIPro") -> None:
        self.clip_num   = clip_num
        self.app        = app
        self.video_path = ""

        # ── container row ────────────────────────────────────────────────────
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="x", padx=6, pady=4)
        self.frame.columnconfigure(1, weight=1)

        # ── upload button ─────────────────────────────────────────────────────
        self.upload_btn = ctk.CTkButton(
            self.frame,
            text=f"📁  Upload Clip #{clip_num}",
            width=210,
            height=72,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=CLR_BTN_NORM,
            hover_color=CLR_BTN_HVRN,
            corner_radius=10,
            command=self._browse_video,
        )
        self.upload_btn.grid(row=0, column=0, padx=(0, 10), sticky="ns")

        # ── output textbox ────────────────────────────────────────────────────
        self.output_box = ctk.CTkTextbox(
            self.frame,
            height=72,
            font=FONT_MONO,
            wrap="word",
            corner_radius=8,
            border_width=1,
            border_color="#37474F",
        )
        self.output_box.grid(row=0, column=1, sticky="nsew")
        self.output_box.insert("end", f"── Clip #{clip_num} output will appear here ──")
        self.output_box.configure(state="disabled")

        # ── copy button ───────────────────────────────────────────────────────
        self.copy_btn = ctk.CTkButton(
            self.frame,
            text="📋\nCopy\nEnglish",
            width=72,
            height=72,
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            fg_color="#37474F",
            hover_color="#455A64",
            corner_radius=10,
            command=self._copy_english,
        )
        self.copy_btn.grid(row=0, column=2, padx=(10, 0), sticky="ns")

    # ------------------------------------------------------------------
    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title=f"Select Video Clip #{self.clip_num}",
            filetypes=[("MP4 Video", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.video_path = path
            name            = os.path.basename(path)
            short_name      = _truncate(name, 26)
            self.upload_btn.configure(
                text=f"✅  {short_name}",
                fg_color=CLR_BTN_DONE,
                hover_color=CLR_BTN_HVRD,
            )

    # ------------------------------------------------------------------
    def set_output(self, text: str) -> None:
        """Thread-safe update of the output textbox."""
        def _update():
            self.output_box.configure(state="normal")
            self.output_box.delete("1.0", "end")
            self.output_box.insert("end", text)
            self.output_box.configure(state="disabled")
        self.app.root.after(0, _update)

    # ------------------------------------------------------------------
    def _copy_english(self) -> None:
        raw  = self.output_box.get("1.0", "end").strip()
        if not raw or raw.startswith("──"):
            messagebox.showinfo("Nothing to copy", "No caption generated yet for this clip.")
            return
        english = _extract_english(raw)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(english)
        self.app.root.update()
        # Brief visual feedback
        self.copy_btn.configure(fg_color=CLR_SUCCESS)
        self.app.root.after(1200, lambda: self.copy_btn.configure(fg_color="#37474F"))


# =============================================================================
#  APIRow  – label + key field + base-url field + model field + status label
# =============================================================================
class APIRow:
    """One Primary or Backup API configuration row."""

    def __init__(
        self,
        parent:   ctk.CTkFrame,
        label:    str,
        row:      int,
    ) -> None:
        self.validate_thread: Optional[threading.Thread] = None
        self._debounce_id: Optional[str] = None
        self.parent = parent

        # ── row label ─────────────────────────────────────────────────────────
        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color="#90CAF9",
        ).grid(row=row, column=0, padx=(0, 8), pady=5, sticky="w")

        # ── API Key ───────────────────────────────────────────────────────────
        self.key_var = tk.StringVar()
        self.key_entry = ctk.CTkEntry(
            parent,
            placeholder_text="API Key…",
            textvariable=self.key_var,
            show="•",
            width=230,
            height=34,
            font=FONT_SM,
        )
        self.key_entry.grid(row=row, column=1, padx=4, pady=5, sticky="ew")

        # ── Base URL ──────────────────────────────────────────────────────────
        self.url_var = tk.StringVar()
        self.url_entry = ctk.CTkEntry(
            parent,
            placeholder_text="Base URL (leave blank for native Gemini)",
            textvariable=self.url_var,
            width=280,
            height=34,
            font=FONT_SM,
        )
        self.url_entry.grid(row=row, column=2, padx=4, pady=5, sticky="ew")

        # ── Model Name ────────────────────────────────────────────────────────
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_entry = ctk.CTkEntry(
            parent,
            placeholder_text="Model name",
            textvariable=self.model_var,
            width=190,
            height=34,
            font=FONT_SM,
        )
        self.model_entry.grid(row=row, column=3, padx=4, pady=5, sticky="ew")

        # ── Status label ──────────────────────────────────────────────────────
        self.status_lbl = ctk.CTkLabel(
            parent,
            text="🔴 Not Connected",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=CLR_ERROR,
            width=190,
            anchor="w",
        )
        self.status_lbl.grid(row=row, column=4, padx=(6, 0), pady=5, sticky="w")

        # ── Live validation trigger ───────────────────────────────────────────
        self.key_var.trace_add("write", self._on_key_changed)

    # ------------------------------------------------------------------
    def _on_key_changed(self, *_args) -> None:
        """Debounce: validate 900 ms after the user stops typing."""
        if self._debounce_id:
            try:
                self.parent.after_cancel(self._debounce_id)
            except Exception:
                pass
        key = self.key_var.get().strip()
        if not key:
            self.status_lbl.configure(text="🔴 Not Connected", text_color=CLR_ERROR)
            return
        self.status_lbl.configure(text="🔵 Validating…", text_color="#64B5F6")
        self._debounce_id = self.parent.after(900, self._start_validate_thread)

    # ------------------------------------------------------------------
    def _start_validate_thread(self) -> None:
        t = threading.Thread(target=self._validate_worker, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    def _validate_worker(self) -> None:
        key      = self.key_var.get().strip()
        base_url = self.url_var.get().strip()
        model    = self.model_var.get().strip() or DEFAULT_MODEL
        if not key:
            return
        try:
            client = AIClient(api_key=key, base_url=base_url, model=model)
            ok, msg = client.validate()
        except Exception as exc:
            ok  = False
            msg = f"🔴 {_truncate(str(exc), 70)}"

        color = CLR_SUCCESS if ok else (CLR_WARNING if "Rate" in msg else CLR_ERROR)
        self.parent.after(0, lambda: self.status_lbl.configure(
            text=msg, text_color=color
        ))

    # ------------------------------------------------------------------
    @property
    def key(self) -> str:
        return self.key_var.get().strip()

    @property
    def base_url(self) -> str:
        return self.url_var.get().strip()

    @property
    def model(self) -> str:
        return self.model_var.get().strip() or DEFAULT_MODEL

    def is_configured(self) -> bool:
        return bool(self.key)

    def get_client(self) -> AIClient:
        return AIClient(api_key=self.key, base_url=self.base_url, model=self.model)


# =============================================================================
#  ShortsAIPro  – main application window
# =============================================================================
class ShortsAIPro:
    """Main application class. Owns the CTk root and all child widgets."""

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(True, True)
        self.root.minsize(900, 700)

        self._is_generating = False
        self._clip_rows: list[ClipRow] = []

        self._build_ui()

    # ==================================================================
    #  UI CONSTRUCTION
    # ==================================================================
    def _build_ui(self) -> None:
        # ── Title bar ─────────────────────────────────────────────────────────
        title_bar = ctk.CTkFrame(self.root, fg_color="#0D1B2A", height=56, corner_radius=0)
        title_bar.pack(fill="x", side="top")

        ctk.CTkLabel(
            title_bar,
            text="⚡  ShortsAI Pro",
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color="#42A5F5",
        ).pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            title_bar,
            text="Viral Caption Generator  •  Powered by Gemini & OpenAI-compatible APIs",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#78909C",
        ).pack(side="left", pady=12)

        # ── Main scroll area ──────────────────────────────────────────────────
        main_frame = ctk.CTkScrollableFrame(
            self.root,
            fg_color="#0A1929",
            scrollbar_button_color="#1E3A5F",
            scrollbar_button_hover_color="#2979FF",
        )
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Clip rows section ─────────────────────────────────────────────────
        clips_header = ctk.CTkFrame(main_frame, fg_color="#0D1B2A", corner_radius=10)
        clips_header.pack(fill="x", padx=14, pady=(14, 0))

        ctk.CTkLabel(
            clips_header,
            text="🎬  Video Clips  ›  Upload up to 5 MP4 clips",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#90CAF9",
        ).pack(anchor="w", padx=14, pady=10)

        clips_frame = ctk.CTkFrame(main_frame, fg_color="#0D1B2A", corner_radius=10)
        clips_frame.pack(fill="x", padx=14, pady=(2, 10))

        for i in range(1, CLIP_COUNT + 1):
            row = ClipRow(clips_frame, i, self)
            self._clip_rows.append(row)
            if i < CLIP_COUNT:
                sep = ctk.CTkFrame(clips_frame, height=1, fg_color="#1E3A5F")
                sep.pack(fill="x", padx=10, pady=0)

        # ── Settings section ──────────────────────────────────────────────────
        settings_card = ctk.CTkFrame(main_frame, fg_color="#0D1B2A", corner_radius=10)
        settings_card.pack(fill="x", padx=14, pady=(4, 4))

        ctk.CTkLabel(
            settings_card,
            text="⚙️  API Configuration & Settings",
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            text_color="#90CAF9",
        ).grid(row=0, column=0, columnspan=5, padx=14, pady=(12, 4), sticky="w")

        # Column weights for settings grid
        for col, w in enumerate([0, 1, 2, 1, 0]):
            settings_card.columnconfigure(col, weight=w, minsize=10)

        # ── Row 1: Primary API ─────────────────────────────────────────────────
        self.primary_api = APIRow(settings_card, "🔑 Primary API", row=1)

        # ── Row 2: Backup API ──────────────────────────────────────────────────
        self.backup_api  = APIRow(settings_card, "🛡️  Backup API",  row=2)

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(settings_card, height=1, fg_color="#1E3A5F").grid(
            row=3, column=0, columnspan=5, sticky="ew", padx=14, pady=6
        )

        # ── Row 3: Video Context ──────────────────────────────────────────────
        ctk.CTkLabel(
            settings_card,
            text="🎯 Video Topic:",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color="#90CAF9",
        ).grid(row=4, column=0, padx=(14, 8), pady=8, sticky="w")

        self.topic_var   = tk.StringVar()
        self.topic_entry = ctk.CTkEntry(
            settings_card,
            placeholder_text='e.g. "Top 5 Angry Cats"',
            textvariable=self.topic_var,
            height=36,
            font=FONT_SM,
        )
        self.topic_entry.grid(row=4, column=1, columnspan=2, padx=4, pady=8, sticky="ew")

        ctk.CTkLabel(
            settings_card,
            text="🎞️ Video Type:",
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color="#90CAF9",
        ).grid(row=4, column=3, padx=(16, 8), pady=8, sticky="w")

        self.video_type_var = tk.StringVar(value=VIDEO_TYPES[0])
        self.type_dropdown  = ctk.CTkOptionMenu(
            settings_card,
            variable=self.video_type_var,
            values=VIDEO_TYPES,
            height=36,
            font=FONT_SM,
            fg_color="#1565C0",
            button_color="#1E88E5",
            button_hover_color="#1565C0",
            dropdown_fg_color="#0D1B2A",
        )
        self.type_dropdown.grid(row=4, column=4, padx=(0, 14), pady=8, sticky="ew")

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(settings_card, height=1, fg_color="#1E3A5F").grid(
            row=5, column=0, columnspan=5, sticky="ew", padx=14, pady=4
        )

        # ── Row 4: Generate button + status ───────────────────────────────────
        btn_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        btn_frame.grid(row=6, column=0, columnspan=5, padx=14, pady=(8, 14), sticky="ew")

        self.generate_btn = ctk.CTkButton(
            btn_frame,
            text="🚀  GENERATE CAPTIONS",
            height=52,
            font=ctk.CTkFont("Segoe UI", 15, "bold"),
            fg_color="#1565C0",
            hover_color="#0D47A1",
            corner_radius=12,
            command=self._on_generate_clicked,
        )
        self.generate_btn.pack(fill="x", pady=(0, 8))

        self.global_status = ctk.CTkLabel(
            btn_frame,
            text="🟡 Idle – upload clips and configure your API key to begin.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#90A4AE",
            wraplength=900,
            justify="left",
        )
        self.global_status.pack(anchor="w")

        # ── Footer ────────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self.root, fg_color="#060E1A", height=28, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        ctk.CTkLabel(
            footer,
            text="ShortsAI Pro v1.0  •  Rate-limit protection: 15s between clips | 65s auto-pause on 429  •  CapCut-ready output",
            font=ctk.CTkFont("Segoe UI", 9),
            text_color="#37474F",
        ).pack(pady=5)

    # ==================================================================
    #  EVENT HANDLERS
    # ==================================================================
    def _on_generate_clicked(self) -> None:
        if self._is_generating:
            messagebox.showwarning(
                "In Progress",
                "Generation is already in progress. Please wait.",
            )
            return

        # Collect valid clips
        clips = [
            (row.clip_num - 1, row.video_path, row)
            for row in self._clip_rows
            if row.video_path
        ]

        if not clips:
            messagebox.showerror("No Clips", "Please upload at least one video clip.")
            return

        if not self.primary_api.is_configured():
            messagebox.showerror(
                "No API Key",
                "Please enter a Primary API Key before generating.",
            )
            return

        # Disable button and fire background thread
        self._is_generating = True
        self.generate_btn.configure(
            state="disabled",
            text="⏳  Generating…",
            fg_color="#37474F",
        )
        self._set_status("🔄 Starting caption generation…", "#64B5F6")

        t = threading.Thread(
            target=self._generation_worker,
            args=(clips,),
            daemon=True,
        )
        t.start()

    # ==================================================================
    #  CORE GENERATION WORKER  (runs in a background thread)
    # ==================================================================
    def _generation_worker(
        self,
        clips: list[tuple[int, str, ClipRow]],
    ) -> None:
        """
        Processes each clip sequentially with:
        • Primary API first
        • Fallback to Backup API on 429
        • 15-second inter-clip delay (rate-limit guard)
        • 65-second auto-pause if both APIs hit rate limits
        """
        topic      = self.topic_var.get().strip()
        video_type = self.video_type_var.get()

        for position, (clip_idx, video_path, clip_row) in enumerate(clips):
            clip_label = f"Clip #{clip_row.clip_num}"
            self._set_status(f"🎬 Processing {clip_label}…", "#64B5F6")

            success = self._process_single_clip(
                clip_idx=clip_idx,
                video_path=video_path,
                clip_row=clip_row,
                clip_label=clip_label,
                topic=topic,
                video_type=video_type,
            )

            # Inter-clip rate-limit delay (skip after last clip)
            if position < len(clips) - 1:
                if success:
                    self._countdown_status(
                        RATE_LIMIT_DELAY,
                        "⏱️ Waiting {remaining}s to prevent API rate limits…",
                        "#FFA726",
                    )
                else:
                    # Still wait a bit even on error to be safe
                    self._countdown_status(
                        5,
                        "⏸️ Brief pause before next clip… {remaining}s",
                        "#78909C",
                    )

        # Done!
        self._set_status(
            "✅ All captions generated! Use the 📋 Copy English buttons to grab captions for CapCut.",
            CLR_SUCCESS,
        )
        self.root.after(0, self._reset_generate_btn)
        self._is_generating = False

    # ------------------------------------------------------------------
    def _process_single_clip(
        self,
        clip_idx:   int,
        video_path: str,
        clip_row:   ClipRow,
        clip_label: str,
        topic:      str,
        video_type: str,
    ) -> bool:
        """
        Try Primary → Backup → Auto-pause flow for one clip.
        Returns True if generation succeeded, False otherwise.
        """

        def status_cb(msg: str) -> None:
            self._set_status(f"[{clip_label}] {msg}", "#64B5F6")

        # ── Attempt with Primary key ──────────────────────────────────────────
        try:
            client = self.primary_api.get_client()
            result = client.generate_caption(
                video_path=video_path,
                clip_index=clip_idx,
                topic=topic,
                video_type=video_type,
                status_cb=status_cb,
            )
            clip_row.set_output(result)
            self._set_status(f"✅ {clip_label} done!", CLR_SUCCESS)
            return True

        except Exception as primary_err:
            err_str = str(primary_err)
            is_rate_limit = (
                "429" in err_str
                or "quota" in err_str.lower()
                or "rate" in err_str.lower()
                or "Resource has been exhausted" in err_str
            )

            if is_rate_limit:
                # ── Try Backup Key ────────────────────────────────────────────
                if self.backup_api.is_configured():
                    self._set_status(
                        f"⚠️ Primary rate-limited. Switching to Backup Key for {clip_label}…",
                        CLR_WARNING,
                    )
                    try:
                        backup_client = self.backup_api.get_client()
                        result = backup_client.generate_caption(
                            video_path=video_path,
                            clip_index=clip_idx,
                            topic=topic,
                            video_type=video_type,
                            status_cb=status_cb,
                        )
                        clip_row.set_output(result)
                        self._set_status(
                            f"✅ {clip_label} done via Backup Key!", CLR_SUCCESS
                        )
                        return True

                    except Exception as backup_err:
                        backup_err_str = str(backup_err)
                        backup_is_429  = (
                            "429" in backup_err_str
                            or "quota" in backup_err_str.lower()
                            or "rate" in backup_err_str.lower()
                        )
                        if backup_is_429:
                            clip_row.set_output(
                                f"⚠️ Both APIs rate-limited. Will retry after auto-pause.\n"
                                f"Primary error: {_truncate(err_str, 120)}\n"
                                f"Backup error : {_truncate(backup_err_str, 120)}"
                            )
                            self._countdown_status(
                                AUTO_PAUSE_DELAY,
                                "🛑 Rate Limit Hit. Auto-Pausing {remaining}s…",
                                CLR_ERROR,
                            )
                            # Retry with primary after pause
                            try:
                                client2 = self.primary_api.get_client()
                                result  = client2.generate_caption(
                                    video_path=video_path,
                                    clip_index=clip_idx,
                                    topic=topic,
                                    video_type=video_type,
                                    status_cb=status_cb,
                                )
                                clip_row.set_output(result)
                                self._set_status(
                                    f"✅ {clip_label} done after auto-pause!", CLR_SUCCESS
                                )
                                return True
                            except Exception as retry_err:
                                clip_row.set_output(
                                    f"❌ Failed after auto-pause.\nError: {_truncate(str(retry_err), 200)}"
                                )
                                self._set_status(
                                    f"❌ {clip_label} failed even after auto-pause.", CLR_ERROR
                                )
                                return False
                        else:
                            clip_row.set_output(
                                f"❌ Backup API error:\n{_truncate(backup_err_str, 300)}"
                            )
                            self._set_status(
                                f"❌ {clip_label} – Backup API failed.", CLR_ERROR
                            )
                            return False

                else:
                    # No backup key → auto-pause, then retry
                    clip_row.set_output(
                        f"⚠️ Rate limited. No backup key configured.\n"
                        f"Auto-pausing for {AUTO_PAUSE_DELAY}s then retrying…"
                    )
                    self._countdown_status(
                        AUTO_PAUSE_DELAY,
                        "🛑 Rate Limit Hit. Auto-Pausing {remaining}s (no backup key)…",
                        CLR_ERROR,
                    )
                    try:
                        client2 = self.primary_api.get_client()
                        result  = client2.generate_caption(
                            video_path=video_path,
                            clip_index=clip_idx,
                            topic=topic,
                            video_type=video_type,
                            status_cb=status_cb,
                        )
                        clip_row.set_output(result)
                        self._set_status(
                            f"✅ {clip_label} done after auto-pause!", CLR_SUCCESS
                        )
                        return True
                    except Exception as retry_err:
                        clip_row.set_output(
                            f"❌ Failed after auto-pause:\n{_truncate(str(retry_err), 200)}"
                        )
                        self._set_status(
                            f"❌ {clip_label} failed again.", CLR_ERROR
                        )
                        return False

            else:
                # Non-rate-limit error (auth, file not found, etc.)
                clip_row.set_output(
                    f"❌ Error processing {clip_label}:\n{_truncate(err_str, 400)}"
                )
                self._set_status(
                    f"❌ {clip_label} – {_truncate(err_str, 80)}", CLR_ERROR
                )
                return False

    # ==================================================================
    #  UI HELPERS
    # ==================================================================
    def _set_status(self, text: str, color: str = "#90A4AE") -> None:
        """Thread-safe status label update."""
        self.root.after(
            0,
            lambda: self.global_status.configure(text=text, text_color=color),
        )

    def _countdown_status(self, seconds: int, template: str, color: str) -> None:
        """
        Block the worker thread for `seconds`, updating the status label
        every second with a countdown.  Template may include {remaining}.
        """
        for remaining in range(seconds, 0, -1):
            msg = template.format(remaining=remaining)
            self._set_status(msg, color)
            time.sleep(1)

    def _reset_generate_btn(self) -> None:
        self.generate_btn.configure(
            state="normal",
            text="🚀  GENERATE CAPTIONS",
            fg_color="#1565C0",
        )

    # ==================================================================
    #  ENTRY POINT
    # ==================================================================
    def run(self) -> None:
        self.root.mainloop()


# =============================================================================
#  __main__
# =============================================================================
if __name__ == "__main__":
    app = ShortsAIPro()
    app.run()
