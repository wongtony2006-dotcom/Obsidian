#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assistant Capture d'écran -> Claude  (version OUVERTE et VISIBLE)
================================================================

Cet outil :
  - prend une capture d'écran (région sélectionnée à la souris, ou plein écran),
    ou charge une image depuis un fichier ;
  - l'envoie au modèle Claude (API Anthropic) avec votre question ;
  - affiche la réponse et permet de poser des questions de suivi sur la même image.

Fonctionnalités :
  - Raccourcis clavier GLOBAUX (Windows) : capturer sans revenir dans l'app.
  - Historique persistant des échanges (question/réponse).
  - Export de la conversation ou de l'historique au format Markdown.
  - Choix du modèle dans l'interface (Opus / Sonnet / Haiku).

Cas d'usage prévus : étudier, comprendre un message d'erreur, faire de l'OCR,
résumer, traduire, expliquer un concept affiché à l'écran — pour votre propre usage.

------------------------------------------------------------------------------
PÉRIMÈTRE VOLONTAIRE (à lire)
------------------------------------------------------------------------------
C'est une application NORMALE et VISIBLE. Elle ne contient, et ne contiendra,
AUCUN mécanisme destiné à :
  - se cacher d'un logiciel de surveillance / proctoring,
  - échapper à la détection de l'Alt+Tab ou de la touche Windows,
  - rester invisible lors d'un partage ou d'un enregistrement d'écran.

La fenêtre est une fenêtre d'application classique : elle apparaît dans la barre
des tâches, dans l'Alt+Tab et dans un partage d'écran, exactement comme n'importe
quel autre programme. Les « raccourcis globaux » servent seulement à déclencher
une capture sans cliquer dans la fenêtre — ils ne cachent rien.
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

# --- Dépendances tierces -----------------------------------------------------
try:
    from PIL import Image, ImageGrab, ImageTk
except ImportError:  # pragma: no cover
    sys.exit("Pillow est requis.  Installez-le avec :  pip install Pillow")

try:
    import anthropic
except ImportError:  # pragma: no cover
    sys.exit("Le SDK Anthropic est requis.  Installez-le avec :  pip install anthropic")


# --- Configuration -----------------------------------------------------------
APP_TITLE = "Assistant Capture → Claude"
MAX_TOKENS = 16000  # requête en streaming : large marge

# Modèles proposés dans l'interface : (libellé affiché, identifiant API).
MODELS = [
    ("Opus 5.5 — le plus capable", "claude-opus-5-5"),
    ("Sonnet 5.5 — équilibré", "claude-sonnet-5-5"),
    ("Haiku 5.5 — rapide / économique", "claude-haiku-5-5"),
]
DEFAULT_MODEL_DISPLAY = MODELS[0][0]

# Emplacement de l'historique (dans le dossier personnel de l'utilisateur).
HISTORY_PATH = os.path.join(
    os.path.expanduser("~"), ".screenshot_assistant", "history.json"
)

SYSTEM_PROMPT = (
    "Tu es un assistant qui aide l'utilisateur à comprendre et à répondre à ce "
    "qui se trouve sur une capture d'écran. Analyse l'image fournie et réponds "
    "à la question de l'utilisateur de manière claire, structurée et concise. "
    "Tu peux lire le texte (OCR), expliquer un message d'erreur, résumer, "
    "traduire, ou détailler un raisonnement pas à pas pour aider à comprendre. "
    "Si aucune question précise n'est posée, décris les éléments pertinents à "
    "l'écran et propose ton aide. Réponds dans la langue de l'utilisateur "
    "(français par défaut)."
)

DEFAULT_QUESTION = "Décris ce qu'il y a sur cette capture et propose ton aide."


# --- Petites fonctions utilitaires ------------------------------------------
def enable_dpi_awareness() -> None:
    """Sur Windows, aligne les coordonnées Tk sur les pixels physiques."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def load_dotenv_simple(path: str = ".env") -> None:
    """Charge un fichier .env minimal (CLE=valeur) dans os.environ."""
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


def pil_to_base64_png(img: "Image.Image") -> str:
    """Encode une image PIL en PNG base64 (sans retour à la ligne)."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


# --- Historique persistant ---------------------------------------------------
class HistoryStore:
    """Stocke les échanges (question/réponse) dans un fichier JSON."""

    def __init__(self, path: str):
        self.path = path
        self.entries = []
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                self.entries = data
        except (OSError, ValueError):
            self.entries = []

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.entries, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add(self, model: str, question: str, answer: str):
        self.entries.append(
            {
                "time": datetime.datetime.now().isoformat(timespec="seconds"),
                "model": model,
                "question": question,
                "answer": answer,
            }
        )
        self.save()

    def clear(self):
        self.entries = []
        self.save()


# --- Raccourcis clavier globaux (Windows) -----------------------------------
class WindowsGlobalHotkeys(threading.Thread):
    """Enregistre des raccourcis clavier globaux via l'API Win32 RegisterHotKey.

    Chaque pression envoie le nom d'action à ``dispatch`` (thread-safe : il ne
    fait qu'alimenter une file lue par le thread de l'interface).
    """

    WM_HOTKEY = 0x0312
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    def __init__(self, bindings, dispatch, on_status=None):
        super().__init__(daemon=True)
        # bindings : liste de (id, modificateurs, code_touche_virtuelle, action)
        self.bindings = bindings
        self.dispatch = dispatch
        self.on_status = on_status

    def run(self):  # pragma: no cover (dépend de Windows)
        import ctypes
        from ctypes import wintypes

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]

        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
        ]
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


# --- Sélecteur de région (overlay plein écran) ------------------------------
class RegionSelector:
    """Surface semi-transparente ; l'utilisateur trace un rectangle."""

    def __init__(self, root: tk.Tk, on_done, on_cancel):
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.start = None

        self.top = tk.Toplevel(root)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-alpha", 0.25)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="black", cursor="cross")

        self.canvas = tk.Canvas(self.top, bg="black", highlightthickness=0, cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            self.top.winfo_screenwidth() // 2,
            40,
            text="Glissez pour sélectionner une zone  •  Échap pour annuler",
            fill="white",
            font=("Segoe UI", 16),
        )
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.top.bind("<Escape>", lambda _e: self._cancel())
        self.top.focus_force()

    def _on_press(self, event):
        self.start = (event.x, event.y)
        self.rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#4ea1ff", width=2
        )

    def _on_drag(self, event):
        if self.rect is not None and self.start is not None:
            self.canvas.coords(self.rect, self.start[0], self.start[1], event.x, event.y)

    def _on_release(self, event):
        if self.start is None:
            self._cancel()
            return
        x1, y1 = self.start
        x2, y2 = event.x, event.y
        bbox = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        self.top.destroy()
        if (bbox[2] - bbox[0]) < 5 or (bbox[3] - bbox[1]) < 5:
            self.on_cancel()
        else:
            self.on_done(bbox)

    def _cancel(self):
        self.top.destroy()
        self.on_cancel()


# --- Application principale ---------------------------------------------------
class ScreenshotAssistant:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("960x760")
        self.root.minsize(760, 580)

        # État de la conversation
        self.messages = []           # historique envoyé à l'API
        self.current_image = None    # dernière image PIL capturée/chargée
        self.pending_image_turn = False
        self.current_turns = []      # transcription texte (pour export)
        self._last_question = ""
        self.active_model = MODELS[0][1]
        self._preview_ref = None
        self.busy = False

        # Files inter-threads
        self.q: "queue.Queue" = queue.Queue()          # réponses API
        self.hotkey_queue: "queue.Queue" = queue.Queue()  # raccourcis globaux

        # Historique persistant
        self.history = HistoryStore(HISTORY_PATH)

        self._build_menu()
        self._build_ui()

        # Raccourcis clavier globaux (Windows uniquement)
        self._start_global_hotkeys()
        self.root.after(80, self._pump_hotkey)

    # ---- Menu ---------------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Exporter la conversation (Markdown)…", command=self.export_current_markdown)
        m_file.add_separator()
        m_file.add_command(label="Quitter", command=self.root.destroy)
        menubar.add_cascade(label="Fichier", menu=m_file)

        m_hist = tk.Menu(menubar, tearoff=0)
        m_hist.add_command(label="Voir l'historique…", command=self.show_history)
        m_hist.add_command(label="Exporter l'historique (Markdown)…", command=self.export_history_markdown)
        m_hist.add_separator()
        m_hist.add_command(label="Effacer l'historique", command=self.clear_history)
        menubar.add_cascade(label="Historique", menu=m_hist)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="À propos", command=self._about)
        menubar.add_cascade(label="Aide", menu=m_help)

        self.root.config(menu=menubar)

    def _about(self):
        messagebox.showinfo(
            "À propos",
            APP_TITLE + "\n\n"
            "Assistant capture d'écran → Claude (API Anthropic).\n"
            "Application normale et visible : aucun mécanisme de dissimulation "
            "ni de contournement de détection (Alt+Tab, touche Windows, "
            "partage d'écran).\n\n"
            "Raccourcis globaux (Windows) :\n"
            "  • Ctrl+Shift+S : capturer une région\n"
            "  • Ctrl+Shift+F : capturer tout l'écran",
        )

    # ---- Construction de l'interface ---------------------------------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        # Ligne 1 : clé API + modèle
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Clé API :").pack(side="left")
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.api_entry = ttk.Entry(top, textvariable=self.api_key_var, show="•", width=34)
        self.api_entry.pack(side="left", padx=6)
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Afficher", variable=self.show_key_var, command=self._toggle_key).pack(side="left")

        ttk.Label(top, text="Modèle :").pack(side="left", padx=(16, 4))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL_DISPLAY)
        self.model_combo = ttk.Combobox(
            top, textvariable=self.model_var, state="readonly",
            values=[name for name, _ in MODELS], width=30,
        )
        self.model_combo.pack(side="left")

        # Ligne 2 : actions de capture
        actions = ttk.Frame(self.root)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="📐 Capturer une région", command=self.capture_region).pack(side="left")
        ttk.Button(actions, text="🖥 Capturer tout l'écran", command=self.capture_fullscreen).pack(side="left", padx=6)
        ttk.Button(actions, text="📂 Charger une image…", command=self.load_image).pack(side="left")
        ttk.Button(actions, text="♻ Nouvelle conversation", command=self.reset_conversation).pack(side="right")

        # Ligne 3 : rappel des raccourcis globaux
        hint = ttk.Label(
            self.root,
            text="Raccourcis globaux (Windows) :  Ctrl+Shift+S = région   •   Ctrl+Shift+F = plein écran",
            foreground="#666666",
        )
        hint.pack(fill="x", padx=8)

        # Zone centrale : aperçu + transcription
        center = ttk.Frame(self.root)
        center.pack(fill="both", expand=True, **pad)

        left = ttk.LabelFrame(center, text="Aperçu de la capture")
        left.pack(side="left", fill="y")
        self.preview_label = ttk.Label(left, text="(aucune image)", anchor="center", width=34)
        self.preview_label.pack(padx=8, pady=8, fill="both", expand=True)

        right = ttk.LabelFrame(center, text="Conversation")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.transcript = tk.Text(right, wrap="word", state="disabled", font=("Segoe UI", 10))
        scroll = ttk.Scrollbar(right, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scroll.set)
        self.transcript.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll.pack(side="right", fill="y", pady=6)

        self.transcript.tag_configure("user", foreground="#1a6e1a", font=("Segoe UI", 10, "bold"))
        self.transcript.tag_configure("claude", foreground="#1456b8", font=("Segoe UI", 10, "bold"))
        self.transcript.tag_configure("info", foreground="#888888", font=("Segoe UI", 9, "italic"))
        self.transcript.tag_configure("error", foreground="#b00020")

        # Bas : question + envoi
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        self.question = tk.Text(bottom, height=3, wrap="word", font=("Segoe UI", 10))
        self.question.pack(side="left", fill="x", expand=True)
        self.question.bind("<Control-Return>", self._on_ctrl_return)
        self.send_btn = ttk.Button(bottom, text="Demander à Claude\n(Ctrl+Entrée)", command=self.ask)
        self.send_btn.pack(side="left", padx=6, fill="y")

        self.status = ttk.Label(self.root, text="Prêt.", anchor="w", relief="sunken")
        self.status.pack(fill="x", side="bottom")

        self._log_info(
            "Astuce : capturez une région ou tout l'écran, tapez votre question, "
            "puis Ctrl+Entrée. Une nouvelle capture démarre une nouvelle conversation."
        )

    def _on_ctrl_return(self, _event):
        self.ask()
        return "break"  # empêche l'insertion d'un saut de ligne dans le champ

    def _toggle_key(self):
        self.api_entry.configure(show="" if self.show_key_var.get() else "•")

    # ---- Raccourcis globaux : démarrage + pompe ----------------------------
    def _start_global_hotkeys(self):
        if sys.platform != "win32":
            return
        VK_S, VK_F = 0x53, 0x46
        mod = WindowsGlobalHotkeys.MOD_CONTROL | WindowsGlobalHotkeys.MOD_SHIFT
        bindings = [
            (1, mod, VK_S, "region"),
            (2, mod, VK_F, "fullscreen"),
        ]
        hk = WindowsGlobalHotkeys(
            bindings,
            dispatch=lambda action: self.hotkey_queue.put(("action", action)),
            on_status=lambda text: self.hotkey_queue.put(("status", text)),
        )
        hk.start()

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
                    self._log_info(val)
        except queue.Empty:
            pass
        self.root.after(80, self._pump_hotkey)

    # ---- Journalisation dans la transcription ------------------------------
    def _write(self, text: str, tag: str = None):
        self.transcript.configure(state="normal")
        if tag:
            self.transcript.insert("end", text, tag)
        else:
            self.transcript.insert("end", text)
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _log_info(self, text: str):
        self._write(f"\nℹ {text}\n", "info")

    def _set_status(self, text: str):
        self.status.configure(text=text)

    # ---- Captures ----------------------------------------------------------
    def capture_region(self):
        if self.busy:
            return
        self.root.withdraw()
        self.root.after(200, self._launch_region_selector)

    def _launch_region_selector(self):
        RegionSelector(self.root, on_done=self._grab_region, on_cancel=self._restore_window)

    def _grab_region(self, bbox):
        self.root.after(120, lambda: self._do_grab_region(bbox))

    def _do_grab_region(self, bbox):
        try:
            img = ImageGrab.grab(bbox=bbox)
        except Exception as exc:
            self._restore_window()
            messagebox.showerror("Capture impossible", str(exc))
            return
        self._restore_window()
        self._set_image(img, "Région capturée.")

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
            messagebox.showerror("Capture impossible", str(exc))
            return
        self._restore_window()
        self._set_image(img, "Écran complet capturé.")

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
            messagebox.showerror("Ouverture impossible", str(exc))
            return
        self._set_image(img, f"Image chargée : {os.path.basename(path)}")

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _set_image(self, img: "Image.Image", status: str):
        self.current_image = img
        self.pending_image_turn = True
        self.messages = []        # nouvelle image -> nouvelle conversation
        self.current_turns = []
        self._update_preview(img)
        self._set_status(status)
        self._log_info(status + " Posez votre question ci-dessous.")

    def _update_preview(self, img: "Image.Image"):
        thumb = img.copy()
        thumb.thumbnail((300, 440))
        self._preview_ref = ImageTk.PhotoImage(thumb)
        self.preview_label.configure(image=self._preview_ref, text="")

    # ---- Envoi à Claude ----------------------------------------------------
    def _current_model_id(self) -> str:
        disp = self.model_var.get()
        for name, mid in MODELS:
            if name == disp:
                return mid
        return MODELS[0][1]

    def ask(self):
        if self.busy:
            return
        if self.current_image is None:
            messagebox.showinfo("Aucune image", "Capturez ou chargez d'abord une image.")
            return

        question = self.question.get("1.0", "end").strip() or DEFAULT_QUESTION
        self._last_question = question
        self.active_model = self._current_model_id()  # figé pour ce tour (thread-safe)

        if self.pending_image_turn:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": pil_to_base64_png(self.current_image),
                    },
                },
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
        self._write(f"\n🤖 Claude ({self.active_model}) : ", "claude")

        self.question.delete("1.0", "end")
        self._set_busy(True)

        threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(50, self._poll_queue)

    def _make_client(self) -> "anthropic.Anthropic":
        key = self.api_key_var.get().strip()
        if key:
            return anthropic.Anthropic(api_key=key)
        return anthropic.Anthropic()  # ANTHROPIC_API_KEY env / profil `ant auth login`

    def _worker(self):
        """Thread de travail : appel API en streaming."""
        try:
            client = self._make_client()
            with client.messages.stream(
                model=self.active_model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=self.messages,
            ) as stream:
                for chunk in stream.text_stream:
                    self.q.put(("delta", chunk))
                final = stream.get_final_message()
            self.q.put(("final", final))
        except anthropic.AuthenticationError:
            self.q.put(("error", "Clé API invalide ou manquante. Renseignez une clé Anthropic valide."))
        except anthropic.RateLimitError:
            self.q.put(("error", "Limite de requêtes atteinte. Réessayez dans quelques instants."))
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
                    # Conserve la réponse complète (y compris blocs de pensée)
                    # pour les questions de suivi -> « preserved thinking ».
                    self.messages.append({"role": "assistant", "content": payload.content})
                    answer = "".join(
                        b.text for b in payload.content if getattr(b, "type", None) == "text"
                    )
                    self.current_turns.append({"role": "assistant", "text": answer})
                    self.history.add(self.active_model, self._last_question, answer)
                    self.pending_image_turn = False
                    self._write("\n")
                    self._set_busy(False)
                    self._set_status("Réponse reçue. Vous pouvez poser une question de suivi.")
                    return
                elif kind == "error":
                    # Annule le tour utilisateur pour permettre un nouvel essai.
                    if self.messages and self.messages[-1]["role"] == "user":
                        self.messages.pop()
                    if self.current_turns and self.current_turns[-1]["role"] == "user":
                        self.current_turns.pop()
                    if getattr(self, "_added_image_this_turn", False):
                        self.pending_image_turn = True
                    self._write("\n")
                    self._write(f"⚠ {payload}\n", "error")
                    self._set_busy(False)
                    self._set_status("Erreur.")
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.send_btn.configure(state="disabled" if busy else "normal")
        self._set_status("Claude réfléchit…" if busy else "Prêt.")

    def reset_conversation(self):
        self.messages = []
        self.current_turns = []
        self.pending_image_turn = self.current_image is not None
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._log_info(
            "Conversation réinitialisée."
            + (" L'image actuelle est conservée." if self.current_image else "")
        )
        self._set_status("Conversation réinitialisée.")

    # ---- Export Markdown ---------------------------------------------------
    @staticmethod
    def _turns_to_markdown(turns, title: str, model: str = None) -> str:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"# {title}", "", f"*Exporté le {now}*"]
        if model:
            lines += [f"", f"**Modèle :** {model}"]
        lines.append("")
        for t in turns:
            head = "## 🧑 Vous" if t["role"] == "user" else "## 🤖 Claude"
            lines += [head, "", t["text"].rstrip(), ""]
        return "\n".join(lines)

    def export_current_markdown(self):
        if not self.current_turns:
            messagebox.showinfo("Rien à exporter", "La conversation est vide.")
            return
        path = filedialog.asksaveasfilename(
            title="Exporter la conversation",
            defaultextension=".md",
            initialfile="conversation.md",
            filetypes=[("Markdown", "*.md"), ("Tous", "*.*")],
        )
        if not path:
            return
        md = self._turns_to_markdown(self.current_turns, "Conversation", self.active_model)
        self._save_text(path, md)

    def export_history_markdown(self):
        if not self.history.entries:
            messagebox.showinfo("Historique vide", "Aucun échange enregistré.")
            return
        path = filedialog.asksaveasfilename(
            title="Exporter l'historique",
            defaultextension=".md",
            initialfile="historique.md",
            filetypes=[("Markdown", "*.md"), ("Tous", "*.*")],
        )
        if not path:
            return
        lines = ["# Historique des échanges", ""]
        for e in self.history.entries:
            lines += [
                f"## {e.get('time', '')} — {e.get('model', '')}",
                "",
                "**🧑 Vous :**",
                "",
                e.get("question", "").rstrip(),
                "",
                "**🤖 Claude :**",
                "",
                e.get("answer", "").rstrip(),
                "",
                "---",
                "",
            ]
        self._save_text(path, "\n".join(lines))

    def _save_text(self, path: str, text: str):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            messagebox.showerror("Échec de l'export", str(exc))
            return
        self._set_status(f"Exporté : {path}")
        messagebox.showinfo("Export réussi", f"Fichier écrit :\n{path}")

    # ---- Fenêtre historique ------------------------------------------------
    def show_history(self):
        if not self.history.entries:
            messagebox.showinfo("Historique vide", "Aucun échange enregistré pour l'instant.")
            return

        win = tk.Toplevel(self.root)
        win.title("Historique des échanges")
        win.geometry("820x560")

        paned = ttk.Panedwindow(win, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(paned)
        listbox = tk.Listbox(left, width=42, activestyle="dotbox")
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

        # Plus récent en haut
        entries = list(reversed(self.history.entries))
        for e in entries:
            q = (e.get("question", "") or "").replace("\n", " ")
            label = f"{e.get('time', '')} · {e.get('model', '').split('-')[1] if '-' in e.get('model','') else e.get('model','')} · {q[:40]}"
            listbox.insert("end", label)

        def on_select(_evt=None):
            sel = listbox.curselection()
            if not sel:
                return
            e = entries[sel[0]]
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("end", f"{e.get('time','')}  —  {e.get('model','')}\n\n", ())
            detail.insert("end", "🧑 Vous :\n", ())
            detail.insert("end", e.get("question", "") + "\n\n")
            detail.insert("end", "🤖 Claude :\n", ())
            detail.insert("end", e.get("answer", "") + "\n")
            detail.configure(state="disabled")

        listbox.bind("<<ListboxSelect>>", on_select)
        listbox.selection_set(0)
        on_select()

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="Exporter l'historique (Markdown)…", command=self.export_history_markdown).pack(side="left")
        ttk.Button(btns, text="Fermer", command=win.destroy).pack(side="right")

    def clear_history(self):
        if not self.history.entries:
            messagebox.showinfo("Historique vide", "Il n'y a rien à effacer.")
            return
        if messagebox.askyesno("Effacer l'historique", "Supprimer définitivement tout l'historique ?"):
            self.history.clear()
            self._set_status("Historique effacé.")


def main():
    enable_dpi_awareness()
    load_dotenv_simple()
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    ScreenshotAssistant(root)
    root.mainloop()


if __name__ == "__main__":
    main()
