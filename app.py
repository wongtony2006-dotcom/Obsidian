#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clairvue — Assistant d'écran intelligent  (version OUVERTE et VISIBLE)
=====================================================================

Clairvue prend une capture d'écran (région, plein écran, ou image chargée),
l'envoie à Claude (API Anthropic) et répond à vos questions : explication,
résumé, OCR, traduction, aide sur une erreur ou du code, pas à pas…

Fonctionnalités principales :
  - Modes spéciaux (macros intégrées) : Expliquer, Résumer, OCR, Traduire,
    Corriger, Expliquer l'erreur, Expliquer le code, Tableau → données, Pas à pas.
  - Macros personnalisées (vos propres prompts réutilisables).
  - Raccourcis clavier GLOBAUX (Windows) + « lancer à la capture ».
  - Historique persistant + export Markdown.
  - Choix du modèle (Opus / Sonnet / Haiku), de l'effort et de la langue.
  - Thème clair / sombre, « toujours au-dessus », copier / enregistrer / stop.

------------------------------------------------------------------------------
PÉRIMÈTRE VOLONTAIRE (à lire)
------------------------------------------------------------------------------
Application NORMALE et VISIBLE. AUCUN mécanisme destiné à se cacher d'un
logiciel de surveillance, à échapper à la détection de l'Alt+Tab / de la touche
Windows, ou à rester invisible lors d'un partage ou enregistrement d'écran.
Les raccourcis globaux servent seulement à déclencher une capture sans cliquer
dans la fenêtre — ils ne cachent rien.
"""

import base64
import datetime
import io
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageGrab, ImageTk
except ImportError:  # pragma: no cover
    sys.exit("Pillow est requis.  Installez-le avec :  pip install Pillow")

try:
    import anthropic
except ImportError:  # pragma: no cover
    sys.exit("Le SDK Anthropic est requis.  Installez-le avec :  pip install anthropic")


# --- Constantes & configuration ---------------------------------------------
APP_NAME = "Clairvue"
APP_TAGLINE = "Assistant d'écran intelligent"
APP_VERSION = "1.1"
MAX_TOKENS = 16000

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".clairvue")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
HISTORY_PATH = os.path.join(CONFIG_DIR, "history.json")
MACROS_PATH = os.path.join(CONFIG_DIR, "macros.json")

MODELS = [
    ("Opus 5.5 — le plus capable", "claude-opus-5-5"),
    ("Sonnet 5.5 — équilibré", "claude-sonnet-5-5"),
    ("Haiku 5.5 — rapide / économique", "claude-haiku-5-5"),
]
EFFORTS = [("Rapide", "low"), ("Standard", "medium"), ("Approfondi", "high")]
LANGUAGES = ["Auto", "Français", "English", "Español", "Deutsch", "Italiano"]

BASE_SYSTEM = (
    "Tu es Clairvue, un assistant qui aide l'utilisateur à comprendre et à "
    "répondre à ce qui se trouve sur une capture d'écran. Analyse l'image "
    "fournie et réponds de manière claire, structurée et concise. Tu peux lire "
    "le texte (OCR), expliquer un message d'erreur, résumer, traduire, ou "
    "détailler un raisonnement. Si aucune question n'est posée, décris les "
    "éléments pertinents et propose ton aide. Réponds dans la langue de "
    "l'utilisateur (français par défaut)."
)

# Modes intégrés (macros). id, nom, emoji, instruction (ajoutée au système),
# question par défaut (utilisée si le champ est vide / au lancement auto).
BUILTIN_MODES = [
    {"id": "chat", "name": "Discussion", "emoji": "💬", "instruction": "", "question": ""},
    {"id": "explain", "name": "Expliquer", "emoji": "🧠",
     "instruction": "Explique clairement et de façon pédagogique ce qui est à l'écran.",
     "question": "Explique ce qui est à l'écran."},
    {"id": "summary", "name": "Résumer", "emoji": "📝",
     "instruction": "Résume le contenu à l'écran en points clés concis.",
     "question": "Résume le contenu à l'écran."},
    {"id": "ocr", "name": "Extraire le texte", "emoji": "📄",
     "instruction": "Transcris fidèlement tout le texte visible, sans commentaire ni "
                    "reformulation. Conserve la structure (titres, listes, tableaux en Markdown).",
     "question": "Extrais tout le texte de l'image."},
    {"id": "translate", "name": "Traduire", "emoji": "🌐",
     "instruction": "Traduis le texte visible. Donne uniquement la traduction en conservant la mise en forme.",
     "question": "Traduis le texte de l'image."},
    {"id": "proofread", "name": "Corriger", "emoji": "✅",
     "instruction": "Corrige l'orthographe, la grammaire et le style du texte visible. "
                    "Donne d'abord la version corrigée, puis la liste des corrections.",
     "question": "Corrige le texte à l'écran."},
    {"id": "error", "name": "Expliquer l'erreur", "emoji": "🐞",
     "instruction": "Il y a probablement un message d'erreur ou du code. Explique la cause "
                    "probable et propose une correction concrète, étape par étape.",
     "question": "Explique cette erreur et comment la corriger."},
    {"id": "code", "name": "Expliquer le code", "emoji": "💻",
     "instruction": "Explique le code affiché : rôle, fonctionnement, points d'attention, bugs potentiels.",
     "question": "Explique ce code."},
    {"id": "table", "name": "Tableau → données", "emoji": "📊",
     "instruction": "Extrais les tableaux/données visibles sous forme de tableau Markdown, "
                    "et propose l'équivalent CSV.",
     "question": "Extrais les données sous forme de tableau."},
    {"id": "steps", "name": "Pas à pas", "emoji": "🪜",
     "instruction": "Réponds de façon pédagogique en détaillant le raisonnement étape par étape, "
                    "pas seulement le résultat.",
     "question": "Explique / résous étape par étape ce qui est à l'écran."},
]

DEFAULT_QUESTION = "Décris ce qu'il y a sur cette capture et propose ton aide."

PALETTES = {
    "light": {
        "bg": "#f3f4f6", "panel": "#ffffff", "fg": "#1b1f24", "muted": "#6b7280",
        "accent": "#2f6fed", "accent_fg": "#ffffff", "border": "#d7dbe0",
        "text_bg": "#ffffff", "text_fg": "#1b1f24",
        "user": "#15803d", "assistant": "#1d4ed8", "error": "#b00020", "info": "#6b7280",
    },
    "dark": {
        "bg": "#13161b", "panel": "#1e242c", "fg": "#e6e8eb", "muted": "#9aa4b2",
        "accent": "#4b8bff", "accent_fg": "#0b0d10", "border": "#2d343d",
        "text_bg": "#0f1216", "text_fg": "#e6e8eb",
        "user": "#4ade80", "assistant": "#8ab0ff", "error": "#ff6b6b", "info": "#9aa4b2",
    },
}


# --- Utilitaires -------------------------------------------------------------
def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def load_dotenv_simple(path: str = ".env") -> None:
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def pil_to_base64_png(img: "Image.Image") -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


# --- Historique --------------------------------------------------------------
class HistoryStore:
    def __init__(self, path):
        self.path = path
        data = read_json(path, [])
        self.entries = data if isinstance(data, list) else []

    def add(self, model, mode, question, answer):
        self.entries.append({
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": model, "mode": mode, "question": question, "answer": answer,
        })
        write_json(self.path, self.entries)

    def clear(self):
        self.entries = []
        write_json(self.path, self.entries)


# --- Raccourcis clavier globaux (Windows) -----------------------------------
class WindowsGlobalHotkeys(threading.Thread):
    WM_HOTKEY = 0x0312
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_NOREPEAT = 0x4000

    def __init__(self, bindings, dispatch, on_status=None):
        super().__init__(daemon=True)
        self.bindings = bindings
        self.dispatch = dispatch
        self.on_status = on_status

    def run(self):  # pragma: no cover (Windows)
        import ctypes
        from ctypes import wintypes

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT),
            ]

        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL

        id_to_action = {}
        for hid, mod, vk, action in self.bindings:
            if user32.RegisterHotKey(None, hid, mod | self.MOD_NOREPEAT, vk):
                id_to_action[hid] = action
            elif self.on_status:
                self.on_status(f"Raccourci global « {action} » indisponible (déjà pris ?).")

        if not id_to_action:
            return

        msg = MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret in (0, -1):
                break
            if msg.message == self.WM_HOTKEY:
                action = id_to_action.get(int(msg.wParam))
                if action:
                    self.dispatch(action)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# --- Sélecteur de région -----------------------------------------------------
class RegionSelector:
    def __init__(self, root, on_done, on_cancel):
        self.on_done, self.on_cancel = on_done, on_cancel
        self.start = None
        self.top = tk.Toplevel(root)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-alpha", 0.25)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="black", cursor="cross")
        self.canvas = tk.Canvas(self.top, bg="black", highlightthickness=0, cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            self.top.winfo_screenwidth() // 2, 40,
            text="Glissez pour sélectionner une zone  •  Échap pour annuler",
            fill="white", font=("Segoe UI", 16),
        )
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.top.bind("<Escape>", lambda _e: self._cancel())
        self.top.focus_force()

    def _press(self, e):
        self.start = (e.x, e.y)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#4ea1ff", width=2)

    def _drag(self, e):
        if self.rect is not None and self.start is not None:
            self.canvas.coords(self.rect, self.start[0], self.start[1], e.x, e.y)

    def _release(self, e):
        if self.start is None:
            return self._cancel()
        x1, y1 = self.start
        bbox = (min(x1, e.x), min(y1, e.y), max(x1, e.x), max(y1, e.y))
        self.top.destroy()
        if (bbox[2] - bbox[0]) < 5 or (bbox[3] - bbox[1]) < 5:
            self.on_cancel()
        else:
            self.on_done(bbox)

    def _cancel(self):
        self.top.destroy()
        self.on_cancel()


# --- Application -------------------------------------------------------------
class Clairvue:
    def __init__(self, root):
        self.root = root
        self.cfg = read_json(CONFIG_PATH, {})
        macros = read_json(MACROS_PATH, [])
        self.macros = macros if isinstance(macros, list) else []
        self.history = HistoryStore(HISTORY_PATH)

        # État conversation
        self.messages = []
        self.current_image = None
        self.pending_image_turn = False
        self.current_turns = []
        self._last_question = ""
        self._assistant_buffer = ""
        self.busy = False
        self.cancel_event = threading.Event()
        self._preview_ref = None

        # Files inter-threads
        self.q = queue.Queue()
        self.hotkey_queue = queue.Queue()

        # Variables UI (restaurées depuis la config)
        self.theme = self.cfg.get("theme", "light")
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.model_var = tk.StringVar(value=self.cfg.get("model", MODELS[0][0]))
        self.effort_var = tk.StringVar(value=self.cfg.get("effort", EFFORTS[1][0]))
        self.language_var = tk.StringVar(value=self.cfg.get("language", "Auto"))
        self.mode_var = tk.StringVar()
        self.auto_run_var = tk.BooleanVar(value=self.cfg.get("auto_run", False))
        self.on_top_var = tk.BooleanVar(value=self.cfg.get("always_on_top", False))
        self.show_key_var = tk.BooleanVar(value=False)

        self.current_mode = self._resolve_mode(self.cfg.get("mode_ref", ["builtin", "chat"]))

        self.root.title(f"{APP_NAME} — {APP_TAGLINE}")
        if self.cfg.get("geometry"):
            try:
                self.root.geometry(self.cfg["geometry"])
            except tk.TclError:
                self.root.geometry("1040x780")
        else:
            self.root.geometry("1040x780")
        self.root.minsize(860, 600)
        self._set_window_icon()

        self._build_menu()
        self._build_ui()
        self.apply_theme()
        self._refresh_modes()
        self.root.attributes("-topmost", self.on_top_var.get())

        self._start_global_hotkeys()
        self.root.after(80, self._pump_hotkey)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- Modes --------------------------------------------------------------
    def _all_modes(self):
        out = [dict(m, custom=False) for m in BUILTIN_MODES]
        for m in self.macros:
            out.append({
                "id": "custom:" + m.get("name", ""), "name": m.get("name", "Macro"),
                "emoji": "⭐", "instruction": m.get("instruction", ""),
                "question": m.get("question", ""), "custom": True,
            })
        return out

    def _mode_label(self, m):
        return f"{m.get('emoji', '•')} {m['name']}"

    def _resolve_mode(self, ref):
        kind, key = (ref + ["builtin", "chat"])[:2] if isinstance(ref, list) else ("builtin", "chat")
        for m in self._all_modes():
            if kind == "builtin" and not m["custom"] and m["id"] == key:
                return m
            if kind == "custom" and m["custom"] and m["name"] == key:
                return m
        return self._all_modes()[0]

    def _mode_ref(self, m):
        return ["custom", m["name"]] if m.get("custom") else ["builtin", m["id"]]

    def _refresh_modes(self):
        modes = self._all_modes()
        self._labels_to_mode = {self._mode_label(m): m for m in modes}
        labels = list(self._labels_to_mode.keys())
        self.mode_combo.configure(values=labels)
        # garde la sélection si possible
        cur_label = self._mode_label(self.current_mode)
        if cur_label not in labels:
            self.current_mode = modes[0]
            cur_label = self._mode_label(self.current_mode)
        self.mode_var.set(cur_label)

    def _on_mode_change(self, _evt=None):
        m = self._labels_to_mode.get(self.mode_var.get())
        if m:
            self.current_mode = m

    # ---- Menu ---------------------------------------------------------------
    def _build_menu(self):
        bar = tk.Menu(self.root)

        m_file = tk.Menu(bar, tearoff=0)
        m_file.add_command(label="Exporter la conversation (Markdown)…", command=self.export_current_markdown)
        m_file.add_command(label="Enregistrer la capture…", command=self.save_capture)
        m_file.add_separator()
        m_file.add_command(label="Quitter", command=self._on_close)
        bar.add_cascade(label="Fichier", menu=m_file)

        m_hist = tk.Menu(bar, tearoff=0)
        m_hist.add_command(label="Voir l'historique…", command=self.show_history)
        m_hist.add_command(label="Exporter l'historique (Markdown)…", command=self.export_history_markdown)
        m_hist.add_separator()
        m_hist.add_command(label="Effacer l'historique", command=self.clear_history)
        bar.add_cascade(label="Historique", menu=m_hist)

        m_macro = tk.Menu(bar, tearoff=0)
        m_macro.add_command(label="Gérer les macros…", command=self.manage_macros)
        bar.add_cascade(label="Macros", menu=m_macro)

        m_view = tk.Menu(bar, tearoff=0)
        m_view.add_command(label="Basculer thème clair / sombre", command=self.toggle_theme)
        m_view.add_checkbutton(label="Toujours au-dessus", variable=self.on_top_var, command=self._apply_on_top)
        bar.add_cascade(label="Affichage", menu=m_view)

        m_help = tk.Menu(bar, tearoff=0)
        m_help.add_command(label="À propos", command=self._about)
        bar.add_cascade(label="Aide", menu=m_help)

        self.root.config(menu=bar)

    def _about(self):
        messagebox.showinfo(
            "À propos",
            f"{APP_NAME} v{APP_VERSION} — {APP_TAGLINE}\n\n"
            "Assistant capture d'écran → Claude (API Anthropic).\n"
            "Application normale et visible : aucun mécanisme de dissimulation "
            "ni de contournement de détection (Alt+Tab, touche Windows, partage d'écran).\n\n"
            "Raccourcis globaux (Windows) :\n"
            "  • Ctrl+Shift+S : capturer une région\n"
            "  • Ctrl+Shift+F : capturer tout l'écran\n"
            "Ctrl+Entrée : envoyer la question.",
        )

    # ---- Interface ----------------------------------------------------------
    def _build_ui(self):
        # En-tête : marque + réglages
        header = ttk.Frame(self.root, style="TFrame")
        header.pack(fill="x", padx=12, pady=(10, 4))
        brand = ttk.Frame(header, style="TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text="🔎 " + APP_NAME, style="Header.TLabel").pack(side="left")
        ttk.Label(brand, text="  " + APP_TAGLINE, style="Muted.TLabel").pack(side="left", padx=(6, 0))

        settings = ttk.Frame(header, style="TFrame")
        settings.pack(side="right")
        ttk.Label(settings, text="Modèle").grid(row=0, column=0, padx=(0, 4))
        ttk.Combobox(settings, textvariable=self.model_var, state="readonly",
                     values=[n for n, _ in MODELS], width=26).grid(row=0, column=1, padx=(0, 10))
        ttk.Label(settings, text="Effort").grid(row=0, column=2, padx=(0, 4))
        ttk.Combobox(settings, textvariable=self.effort_var, state="readonly",
                     values=[d for d, _ in EFFORTS], width=12).grid(row=0, column=3, padx=(0, 10))
        ttk.Label(settings, text="Langue").grid(row=0, column=4, padx=(0, 4))
        ttk.Combobox(settings, textvariable=self.language_var, state="readonly",
                     values=LANGUAGES, width=10).grid(row=0, column=5, padx=(0, 10))
        self.theme_btn = ttk.Button(settings, text="☾", width=3, command=self.toggle_theme)
        self.theme_btn.grid(row=0, column=6)

        # Ligne clé API
        apirow = ttk.Frame(self.root, style="TFrame")
        apirow.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Label(apirow, text="Clé API Anthropic :").pack(side="left")
        self.api_entry = ttk.Entry(apirow, textvariable=self.api_key_var, show="•", width=40)
        self.api_entry.pack(side="left", padx=6)
        ttk.Checkbutton(apirow, text="Afficher", variable=self.show_key_var,
                        command=self._toggle_key).pack(side="left")

        # Corps : sidebar | conversation
        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill="both", expand=True, padx=12, pady=4)

        side = ttk.Frame(body, style="Panel.TFrame")
        side.pack(side="left", fill="y", padx=(0, 10))

        ttk.Label(side, text="CAPTURE", style="Muted.TLabel").pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Button(side, text="📐  Région  (Ctrl+Shift+S)", command=self.capture_region).pack(fill="x", padx=10, pady=2)
        ttk.Button(side, text="🖥  Plein écran  (Ctrl+Shift+F)", command=self.capture_fullscreen).pack(fill="x", padx=10, pady=2)
        ttk.Button(side, text="📂  Charger une image…", command=self.load_image).pack(fill="x", padx=10, pady=2)

        self.preview_label = tk.Label(side, text="(aucune image)", width=34, height=12,
                                      anchor="center", bd=1, relief="groove")
        self.preview_label.pack(padx=10, pady=10)

        ttk.Label(side, text="MODE / MACRO", style="Muted.TLabel").pack(anchor="w", padx=10, pady=(4, 2))
        self.mode_combo = ttk.Combobox(side, textvariable=self.mode_var, state="readonly", width=32)
        self.mode_combo.pack(fill="x", padx=10, pady=2)
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)
        ttk.Button(side, text="▶  Lancer le mode", command=self.run_mode).pack(fill="x", padx=10, pady=2)
        ttk.Checkbutton(side, text="Lancer à la capture", variable=self.auto_run_var).pack(anchor="w", padx=10, pady=2)
        ttk.Button(side, text="➕  Gérer les macros…", command=self.manage_macros).pack(fill="x", padx=10, pady=(2, 10))

        # Conversation
        convo = ttk.Frame(body, style="TFrame")
        convo.pack(side="left", fill="both", expand=True)
        self.transcript = tk.Text(convo, wrap="word", state="disabled",
                                  font=("Segoe UI", 10), bd=0, padx=10, pady=8)
        tscroll = ttk.Scrollbar(convo, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=tscroll.set)
        self.transcript.pack(side="left", fill="both", expand=True)
        tscroll.pack(side="right", fill="y")

        # Bas : question + actions
        bottom = ttk.Frame(self.root, style="TFrame")
        bottom.pack(fill="x", padx=12, pady=(4, 6))
        self.question = tk.Text(bottom, height=3, wrap="word", font=("Segoe UI", 10), bd=0, padx=8, pady=6)
        self.question.pack(side="left", fill="x", expand=True)
        self.question.bind("<Control-Return>", self._on_ctrl_return)
        btns = ttk.Frame(bottom, style="TFrame")
        btns.pack(side="left", padx=(8, 0), fill="y")
        self.send_btn = ttk.Button(btns, text="Demander  (Ctrl+⏎)", style="Accent.TButton", command=self.ask)
        self.send_btn.pack(fill="x")
        self.stop_btn = ttk.Button(btns, text="⏹ Stop", command=self.stop_generation, state="disabled")
        self.stop_btn.pack(fill="x", pady=(4, 0))

        actions = ttk.Frame(self.root, style="TFrame")
        actions.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Button(actions, text="📋 Copier la réponse", command=self.copy_response).pack(side="left")
        ttk.Button(actions, text="💾 Enregistrer la capture", command=self.save_capture).pack(side="left", padx=6)
        ttk.Button(actions, text="♻ Nouvelle conversation", command=self.reset_conversation).pack(side="right")

        self.status = tk.Label(self.root, text="Prêt.", anchor="w", bd=0, padx=12, pady=4)
        self.status.pack(fill="x", side="bottom")

        self._log_info("Bienvenue sur Clairvue. Capturez une zone, choisissez un mode, puis Ctrl+Entrée.")

    def _set_window_icon(self):
        if sys.platform != "win32":
            return
        for cand in (resource_path("clairvue.ico"),
                     resource_path(os.path.join("assets", "clairvue.ico")),
                     os.path.join("assets", "clairvue.ico")):
            if os.path.isfile(cand):
                try:
                    self.root.iconbitmap(cand)
                    return
                except Exception:
                    pass

    def _on_ctrl_return(self, _e):
        self.ask()
        return "break"

    def _toggle_key(self):
        self.api_entry.configure(show="" if self.show_key_var.get() else "•")

    # ---- Thème --------------------------------------------------------------
    def apply_theme(self):
        p = PALETTES[self.theme]
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.root.configure(bg=p["bg"])
        self.root.option_add("*TCombobox*Listbox.background", p["panel"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])

        style.configure(".", background=p["bg"], foreground=p["fg"],
                        fieldbackground=p["panel"], bordercolor=p["border"])
        style.configure("TFrame", background=p["bg"])
        style.configure("Panel.TFrame", background=p["panel"])
        style.configure("TLabel", background=p["bg"], foreground=p["fg"])
        style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 8, "bold"))
        style.configure("Header.TLabel", background=p["bg"], foreground=p["fg"], font=("Segoe UI Semibold", 17))
        style.configure("TButton", background=p["panel"], foreground=p["fg"],
                        bordercolor=p["border"], focuscolor=p["accent"], padding=6)
        style.map("TButton", background=[("active", p["border"])])
        style.configure("Accent.TButton", background=p["accent"], foreground=p["accent_fg"], padding=8)
        style.map("Accent.TButton", background=[("active", p["accent"]), ("disabled", p["border"])])
        style.configure("TCheckbutton", background=p["panel"], foreground=p["fg"])
        style.map("TCheckbutton", background=[("active", p["panel"])])
        style.configure("TCombobox", fieldbackground=p["panel"], background=p["panel"],
                        foreground=p["fg"], arrowcolor=p["fg"])

        for txt in (self.transcript, self.question):
            txt.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"],
                          selectbackground=p["accent"], selectforeground=p["accent_fg"],
                          highlightthickness=1, highlightbackground=p["border"], highlightcolor=p["border"])
        self.transcript.tag_configure("user", foreground=p["user"], font=("Segoe UI", 10, "bold"))
        self.transcript.tag_configure("assistant", foreground=p["assistant"], font=("Segoe UI", 10, "bold"))
        self.transcript.tag_configure("info", foreground=p["info"], font=("Segoe UI", 9, "italic"))
        self.transcript.tag_configure("error", foreground=p["error"])
        self.preview_label.configure(bg=p["panel"], fg=p["muted"])
        self.status.configure(bg=p["panel"], fg=p["muted"])
        # checkbuttons de la sidebar sont sur Panel ; corrige leur fond
        style.configure("TCheckbutton", background=p["panel"])

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.theme_btn.configure(text="☀" if self.theme == "dark" else "☾")
        self.apply_theme()

    def _apply_on_top(self):
        self.root.attributes("-topmost", self.on_top_var.get())

    # ---- Raccourcis globaux -------------------------------------------------
    def _start_global_hotkeys(self):
        if sys.platform != "win32":
            return
        mod = WindowsGlobalHotkeys.MOD_CONTROL | WindowsGlobalHotkeys.MOD_SHIFT
        bindings = [(1, mod, 0x53, "region"), (2, mod, 0x46, "fullscreen")]  # S, F
        WindowsGlobalHotkeys(
            bindings,
            dispatch=lambda a: self.hotkey_queue.put(("action", a)),
            on_status=lambda t: self.hotkey_queue.put(("status", t)),
        ).start()

    def _pump_hotkey(self):
        try:
            while True:
                kind, val = self.hotkey_queue.get_nowait()
                if kind == "action" and not self.busy:
                    if val == "region":
                        self.capture_region()
                    elif val == "fullscreen":
                        self.capture_fullscreen()
                elif kind == "status":
                    self._set_status(val)
        except queue.Empty:
            pass
        self.root.after(80, self._pump_hotkey)

    # ---- Transcription ------------------------------------------------------
    def _write(self, text, tag=None):
        self.transcript.configure(state="normal")
        self.transcript.insert("end", text, tag) if tag else self.transcript.insert("end", text)
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _log_info(self, text):
        self._write(f"\nℹ {text}\n", "info")

    def _set_status(self, text):
        self.status.configure(text=text)

    # ---- Captures -----------------------------------------------------------
    def capture_region(self):
        if self.busy:
            return
        self.root.withdraw()
        self.root.after(200, lambda: RegionSelector(self.root, self._grab_region, self._restore_window))

    def _grab_region(self, bbox):
        self.root.after(120, lambda: self._do_grab_region(bbox))

    def _do_grab_region(self, bbox):
        try:
            img = ImageGrab.grab(bbox=bbox)
        except Exception as exc:
            self._restore_window()
            return messagebox.showerror("Capture impossible", str(exc))
        self._restore_window()
        self._set_image(img, "Région capturée.", auto=True)

    def capture_fullscreen(self):
        if self.busy:
            return
        self.root.withdraw()
        self.root.after(250, self._do_grab_fullscreen)

    def _do_grab_fullscreen(self):
        try:
            img = ImageGrab.grab(all_screens=True)
        except TypeError:
            img = ImageGrab.grab()
        except Exception as exc:
            self._restore_window()
            return messagebox.showerror("Capture impossible", str(exc))
        self._restore_window()
        self._set_image(img, "Écran complet capturé.", auto=True)

    def load_image(self):
        path = filedialog.askopenfilename(
            title="Choisir une image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
        except Exception as exc:
            return messagebox.showerror("Ouverture impossible", str(exc))
        self._set_image(img, f"Image chargée : {os.path.basename(path)}", auto=False)

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _set_image(self, img, status, auto):
        self.current_image = img
        self.pending_image_turn = True
        self.messages = []
        self.current_turns = []
        self._update_preview(img)
        self._set_status(status)
        self._log_info(status)
        if auto and self.auto_run_var.get():
            self.ask()

    def _update_preview(self, img):
        thumb = img.copy()
        thumb.thumbnail((300, 440))
        self._preview_ref = ImageTk.PhotoImage(thumb)
        self.preview_label.configure(image=self._preview_ref, text="")

    # ---- Appel à Claude -----------------------------------------------------
    def _current_model_id(self):
        for n, mid in MODELS:
            if n == self.model_var.get():
                return mid
        return MODELS[0][1]

    def _current_effort(self):
        for d, v in EFFORTS:
            if d == self.effort_var.get():
                return v
        return "medium"

    def _effective_system(self):
        parts = [BASE_SYSTEM]
        if self.current_mode.get("instruction"):
            parts.append(f"Mode « {self.current_mode['name']} » : {self.current_mode['instruction']}")
        lang = self.language_var.get()
        if lang and lang != "Auto":
            parts.append(f"Réponds en {lang}.")
        return "\n\n".join(parts)

    def run_mode(self):
        if self.current_image is None:
            return messagebox.showinfo("Aucune image", "Capturez ou chargez d'abord une image.")
        self.ask(use_mode_question=True)

    def ask(self, use_mode_question=False):
        if self.busy:
            return
        if self.current_image is None:
            return messagebox.showinfo("Aucune image", "Capturez ou chargez d'abord une image.")

        typed = self.question.get("1.0", "end").strip()
        mode_q = self.current_mode.get("question", "")
        if use_mode_question:
            question = mode_q or typed or DEFAULT_QUESTION
        else:
            question = typed or mode_q or DEFAULT_QUESTION

        self._last_question = question
        self.active_system = self._effective_system()
        self.active_effort = self._current_effort()
        self.active_model = self._current_model_id()
        self.active_mode_name = self.current_mode["name"]

        if self.pending_image_turn:
            content = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": pil_to_base64_png(self.current_image)}},
                {"type": "text", "text": question},
            ]
            self._added_image_this_turn = True
        else:
            content = question
            self._added_image_this_turn = False

        self.messages.append({"role": "user", "content": content})
        self.current_turns.append({"role": "user", "text": question})

        self._write("\n🧑 Vous : ", "user")
        self._write(question + "\n")
        self._write(f"\n🤖 Claude · {self.active_model} · {self.active_mode_name} : ", "assistant")

        self.question.delete("1.0", "end")
        self._assistant_buffer = ""
        self.cancel_event.clear()
        self._set_busy(True)
        threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(50, self._poll_queue)

    def _make_client(self):
        key = self.api_key_var.get().strip()
        return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    def _worker(self):
        try:
            client = self._make_client()
            acc, cancelled, final = [], False, None
            with client.messages.stream(
                model=self.active_model, max_tokens=MAX_TOKENS,
                system=self.active_system, messages=self.messages,
                output_config={"effort": self.active_effort},
            ) as stream:
                for chunk in stream.text_stream:
                    if self.cancel_event.is_set():
                        cancelled = True
                        break
                    acc.append(chunk)
                    self.q.put(("delta", chunk))
                if not cancelled:
                    final = stream.get_final_message()
            if cancelled:
                self.q.put(("cancelled", "".join(acc)))
            else:
                self.q.put(("final", final))
        except anthropic.AuthenticationError:
            self.q.put(("error", "Clé API invalide ou manquante. Renseignez une clé Anthropic valide."))
        except anthropic.RateLimitError:
            self.q.put(("error", "Limite de requêtes atteinte. Réessayez dans un instant."))
        except anthropic.APIConnectionError:
            self.q.put(("error", "Erreur réseau. Vérifiez votre connexion Internet."))
        except Exception as exc:  # pragma: no cover
            self.q.put(("error", f"{type(exc).__name__}: {exc}"))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "delta":
                    self._write(payload)
                elif kind == "final":
                    self.messages.append({"role": "assistant", "content": payload.content})
                    answer = "".join(b.text for b in payload.content if getattr(b, "type", None) == "text")
                    self.current_turns.append({"role": "assistant", "text": answer})
                    self.history.add(self.active_model, self.active_mode_name, self._last_question, answer)
                    self.pending_image_turn = False
                    self._write("\n")
                    self._set_busy(False)
                    self._set_status("Réponse reçue. Question de suivi possible.")
                    return
                elif kind == "cancelled":
                    if payload:
                        self.messages.append({"role": "assistant", "content": payload})
                        self.current_turns.append({"role": "assistant", "text": payload})
                        self.pending_image_turn = False
                    else:
                        self._rollback_user_turn()
                    self._write("\n⏹ (interrompu)\n", "info")
                    self._set_busy(False)
                    self._set_status("Génération interrompue.")
                    return
                elif kind == "error":
                    self._rollback_user_turn()
                    self._write("\n")
                    self._write(f"⚠ {payload}\n", "error")
                    self._set_busy(False)
                    self._set_status("Erreur.")
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _rollback_user_turn(self):
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
        if self.current_turns and self.current_turns[-1]["role"] == "user":
            self.current_turns.pop()
        if getattr(self, "_added_image_this_turn", False):
            self.pending_image_turn = True

    def stop_generation(self):
        if self.busy:
            self.cancel_event.set()
            self._set_status("Interruption…")

    def _set_busy(self, busy):
        self.busy = busy
        self.send_btn.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")
        self._set_status("Claude réfléchit…" if busy else "Prêt.")

    def reset_conversation(self):
        self.messages = []
        self.current_turns = []
        self.pending_image_turn = self.current_image is not None
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._log_info("Conversation réinitialisée." + (" Image conservée." if self.current_image else ""))

    # ---- Actions ------------------------------------------------------------
    def copy_response(self):
        answers = [t["text"] for t in self.current_turns if t["role"] == "assistant"]
        if not answers:
            return messagebox.showinfo("Rien à copier", "Aucune réponse à copier.")
        self.root.clipboard_clear()
        self.root.clipboard_append(answers[-1])
        self._set_status("Dernière réponse copiée dans le presse-papiers.")

    def save_capture(self):
        if self.current_image is None:
            return messagebox.showinfo("Aucune image", "Aucune capture à enregistrer.")
        path = filedialog.asksaveasfilename(
            title="Enregistrer la capture", defaultextension=".png",
            initialfile="capture.png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not path:
            return
        try:
            img = self.current_image
            if path.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
            img.save(path)
        except Exception as exc:
            return messagebox.showerror("Échec", str(exc))
        self._set_status(f"Capture enregistrée : {path}")

    # ---- Export Markdown ----------------------------------------------------
    @staticmethod
    def _turns_markdown(turns, title, model=None):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"# {title}", "", f"*Exporté le {now}*"]
        if model:
            lines += ["", f"**Modèle :** {model}"]
        lines.append("")
        for t in turns:
            lines += ["## 🧑 Vous" if t["role"] == "user" else "## 🤖 Claude", "", t["text"].rstrip(), ""]
        return "\n".join(lines)

    def export_current_markdown(self):
        if not self.current_turns:
            return messagebox.showinfo("Rien à exporter", "La conversation est vide.")
        path = filedialog.asksaveasfilename(title="Exporter la conversation", defaultextension=".md",
                                            initialfile="conversation.md", filetypes=[("Markdown", "*.md")])
        if path:
            self._save_text(path, self._turns_markdown(self.current_turns, f"{APP_NAME} — Conversation",
                                                       getattr(self, "active_model", None)))

    def export_history_markdown(self):
        if not self.history.entries:
            return messagebox.showinfo("Historique vide", "Aucun échange enregistré.")
        path = filedialog.asksaveasfilename(title="Exporter l'historique", defaultextension=".md",
                                            initialfile="historique.md", filetypes=[("Markdown", "*.md")])
        if not path:
            return
        lines = [f"# {APP_NAME} — Historique des échanges", ""]
        for e in self.history.entries:
            lines += [f"## {e.get('time','')} — {e.get('model','')} — {e.get('mode','')}", "",
                      "**🧑 Vous :**", "", e.get("question", "").rstrip(), "",
                      "**🤖 Claude :**", "", e.get("answer", "").rstrip(), "", "---", ""]
        self._save_text(path, "\n".join(lines))

    def _save_text(self, path, text):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            return messagebox.showerror("Échec de l'export", str(exc))
        self._set_status(f"Exporté : {path}")
        messagebox.showinfo("Export réussi", f"Fichier écrit :\n{path}")

    # ---- Fenêtre historique -------------------------------------------------
    def show_history(self):
        if not self.history.entries:
            return messagebox.showinfo("Historique vide", "Aucun échange enregistré.")
        win = tk.Toplevel(self.root)
        win.title("Historique des échanges")
        win.geometry("860x580")
        paned = ttk.Panedwindow(win, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(paned)
        listbox = tk.Listbox(left, width=44, activestyle="dotbox")
        lsb = ttk.Scrollbar(left, command=listbox.yview)
        listbox.configure(yscrollcommand=lsb.set)
        listbox.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        paned.add(left, weight=1)
        right = ttk.Frame(paned)
        detail = tk.Text(right, wrap="word", state="disabled", font=("Segoe UI", 10))
        dsb = ttk.Scrollbar(right, command=detail.yview)
        detail.configure(yscrollcommand=dsb.set)
        detail.pack(side="left", fill="both", expand=True)
        dsb.pack(side="right", fill="y")
        paned.add(right, weight=3)

        entries = list(reversed(self.history.entries))
        for e in entries:
            q = (e.get("question", "") or "").replace("\n", " ")
            listbox.insert("end", f"{e.get('time','')} · {e.get('mode','')} · {q[:36]}")

        def on_select(_e=None):
            sel = listbox.curselection()
            if not sel:
                return
            e = entries[sel[0]]
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("end", f"{e.get('time','')} — {e.get('model','')} — {e.get('mode','')}\n\n")
            detail.insert("end", "🧑 Vous :\n" + e.get("question", "") + "\n\n")
            detail.insert("end", "🤖 Claude :\n" + e.get("answer", "") + "\n")
            detail.configure(state="disabled")

        listbox.bind("<<ListboxSelect>>", on_select)
        listbox.selection_set(0)
        on_select()
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar, text="Exporter (Markdown)…", command=self.export_history_markdown).pack(side="left")
        ttk.Button(bar, text="Fermer", command=win.destroy).pack(side="right")

    def clear_history(self):
        if not self.history.entries:
            return messagebox.showinfo("Historique vide", "Rien à effacer.")
        if messagebox.askyesno("Effacer", "Supprimer définitivement tout l'historique ?"):
            self.history.clear()
            self._set_status("Historique effacé.")

    # ---- Gestionnaire de macros --------------------------------------------
    def manage_macros(self):
        win = tk.Toplevel(self.root)
        win.title("Macros personnalisées")
        win.geometry("640x460")

        listbox = tk.Listbox(win, height=8)
        listbox.pack(fill="x", padx=10, pady=(10, 6))

        def reload_list():
            listbox.delete(0, "end")
            for m in self.macros:
                listbox.insert("end", m.get("name", "(sans nom)"))

        reload_list()

        form = ttk.Frame(win)
        form.pack(fill="both", expand=True, padx=10, pady=6)
        ttk.Label(form, text="Nom").grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar()
        ttk.Entry(form, textvariable=name_var, width=40).grid(row=0, column=1, sticky="we", pady=2)
        ttk.Label(form, text="Instruction (donnée à Claude)").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        instr = tk.Text(form, height=5, wrap="word")
        instr.grid(row=1, column=1, sticky="we", pady=2)
        ttk.Label(form, text="Question par défaut").grid(row=2, column=0, sticky="w")
        q_var = tk.StringVar()
        ttk.Entry(form, textvariable=q_var, width=40).grid(row=2, column=1, sticky="we", pady=2)
        form.columnconfigure(1, weight=1)

        def on_select(_e=None):
            sel = listbox.curselection()
            if not sel:
                return
            m = self.macros[sel[0]]
            name_var.set(m.get("name", ""))
            instr.delete("1.0", "end")
            instr.insert("1.0", m.get("instruction", ""))
            q_var.set(m.get("question", ""))

        listbox.bind("<<ListboxSelect>>", on_select)

        def save():
            name = name_var.get().strip()
            if not name:
                return messagebox.showinfo("Nom requis", "Donnez un nom à la macro.", parent=win)
            macro = {"name": name, "instruction": instr.get("1.0", "end").strip(), "question": q_var.get().strip()}
            for i, m in enumerate(self.macros):
                if m.get("name") == name:
                    self.macros[i] = macro
                    break
            else:
                self.macros.append(macro)
            write_json(MACROS_PATH, self.macros)
            reload_list()
            self._refresh_modes()
            self._set_status(f"Macro « {name} » enregistrée.")

        def delete():
            sel = listbox.curselection()
            if not sel:
                return
            name = self.macros[sel[0]].get("name", "")
            del self.macros[sel[0]]
            write_json(MACROS_PATH, self.macros)
            reload_list()
            self._refresh_modes()
            self._set_status(f"Macro « {name} » supprimée.")

        def new():
            listbox.selection_clear(0, "end")
            name_var.set("")
            instr.delete("1.0", "end")
            q_var.set("")

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="Nouveau", command=new).pack(side="left")
        ttk.Button(bar, text="Enregistrer", command=save).pack(side="left", padx=6)
        ttk.Button(bar, text="Supprimer", command=delete).pack(side="left")
        ttk.Button(bar, text="Fermer", command=win.destroy).pack(side="right")

    # ---- Fermeture ----------------------------------------------------------
    def _on_close(self):
        self.cfg.update({
            "theme": self.theme,
            "model": self.model_var.get(),
            "effort": self.effort_var.get(),
            "language": self.language_var.get(),
            "auto_run": bool(self.auto_run_var.get()),
            "always_on_top": bool(self.on_top_var.get()),
            "mode_ref": self._mode_ref(self.current_mode),
            "geometry": self.root.geometry(),
        })
        write_json(CONFIG_PATH, self.cfg)
        self.root.destroy()


def main():
    enable_dpi_awareness()
    load_dotenv_simple()
    root = tk.Tk()
    Clairvue(root)
    root.mainloop()


if __name__ == "__main__":
    main()
