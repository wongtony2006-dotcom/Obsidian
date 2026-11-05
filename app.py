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
quel autre programme.
"""

import base64
import io
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
MODEL_ID = "claude-opus-5-5"          # modèle par défaut (le plus capable)
MAX_TOKENS = 16000                    # requête en streaming : large marge
APP_TITLE = "Assistant Capture → Claude"

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

DEFAULT_QUESTION = (
    "Décris ce qu'il y a sur cette capture et propose ton aide."
)


# --- Petites fonctions utilitaires ------------------------------------------
def enable_dpi_awareness() -> None:
    """Sur Windows, aligne les coordonnées Tk sur les pixels physiques.

    Sans cela, la mise à l'échelle de l'affichage (125 %, 150 %...) décale la
    zone sélectionnée par rapport à ce qui est réellement capturé.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            # Per-Monitor-Aware v2 (Windows 10+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def load_dotenv_simple(path: str = ".env") -> None:
    """Charge un fichier .env minimal (CLE=valeur) dans os.environ.

    Évite une dépendance supplémentaire ; les variables déjà définies dans
    l'environnement ne sont pas écrasées.
    """
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


# --- Sélecteur de région (overlay plein écran) ------------------------------
class RegionSelector:
    """Affiche une surface semi-transparente ; l'utilisateur trace un rectangle.

    Appelle ``on_done(bbox)`` avec (x1, y1, x2, y2) en pixels écran, ou
    ``on_cancel()`` si l'utilisateur appuie sur Échap / annule.
    """

    def __init__(self, root: tk.Tk, on_done, on_cancel):
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.start = None

        self.top = tk.Toplevel(root)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-alpha", 0.25)
        self.top.attributes("-topmost", True)
        self.top.configure(bg="black", cursor="cross")

        self.canvas = tk.Canvas(
            self.top, bg="black", highlightthickness=0, cursor="cross"
        )
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
        # Zone trop petite -> on considère que c'est une annulation.
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
        self.root.geometry("900x720")
        self.root.minsize(720, 560)

        # État de la conversation
        self.messages = []          # historique envoyé à l'API
        self.current_image = None   # dernière image PIL capturée/chargée
        self.pending_image_turn = False  # l'image doit être jointe au prochain tour
        self._preview_ref = None    # garde une réf. du thumbnail Tk
        self.busy = False

        # File de communication thread de travail -> thread UI
        self.q: "queue.Queue" = queue.Queue()

        self._build_ui()

    # ---- Construction de l'interface ---------------------------------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        # Barre du haut : clé API
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Clé API Anthropic :").pack(side="left")
        self.api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.api_entry = ttk.Entry(top, textvariable=self.api_key_var, show="•", width=42)
        self.api_entry.pack(side="left", padx=6)
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top, text="Afficher", variable=self.show_key_var, command=self._toggle_key
        ).pack(side="left")

        # Barre d'actions : captures
        actions = ttk.Frame(self.root)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="📐 Capturer une région", command=self.capture_region).pack(side="left")
        ttk.Button(actions, text="🖥 Capturer tout l'écran", command=self.capture_fullscreen).pack(side="left", padx=6)
        ttk.Button(actions, text="📂 Charger une image…", command=self.load_image).pack(side="left")
        ttk.Button(actions, text="♻ Nouvelle conversation", command=self.reset_conversation).pack(side="right")

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

        # Barre du bas : question + envoi
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
        # Laisse à la fenêtre le temps de disparaître avant l'overlay.
        self.root.after(200, self._launch_region_selector)

    def _launch_region_selector(self):
        RegionSelector(self.root, on_done=self._grab_region, on_cancel=self._restore_window)

    def _grab_region(self, bbox):
        # Laisse l'overlay disparaître avant la capture.
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
            # all_screens=True : prend aussi les écrans secondaires sous Windows.
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
        # Nouvelle image -> nouvelle conversation (contexte propre).
        self.messages = []
        self._update_preview(img)
        self._set_status(status)
        self._log_info(status + " Posez votre question ci-dessous.")

    def _update_preview(self, img: "Image.Image"):
        thumb = img.copy()
        thumb.thumbnail((300, 420))
        self._preview_ref = ImageTk.PhotoImage(thumb)
        self.preview_label.configure(image=self._preview_ref, text="")

    # ---- Envoi à Claude ----------------------------------------------------
    def ask(self):
        if self.busy:
            return
        if self.current_image is None:
            messagebox.showinfo("Aucune image", "Capturez ou chargez d'abord une image.")
            return

        question = self.question.get("1.0", "end").strip() or DEFAULT_QUESTION

        # Construit le tour utilisateur (image jointe uniquement au 1er tour).
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

        self._write(f"\n🧑 Vous : ", "user")
        self._write(question + "\n")
        self._write("\n🤖 Claude : ", "claude")

        self.question.delete("1.0", "end")
        self._set_busy(True)

        threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(50, self._poll_queue)

    def _make_client(self) -> "anthropic.Anthropic":
        key = self.api_key_var.get().strip()
        if key:
            return anthropic.Anthropic(api_key=key)
        # Sinon : ANTHROPIC_API_KEY de l'environnement, ou profil `ant auth login`.
        return anthropic.Anthropic()

    def _worker(self):
        """Thread de travail : effectue l'appel API en streaming."""
        try:
            client = self._make_client()
            with client.messages.stream(
                model=MODEL_ID,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=self.messages,
                # Pensée adaptive par défaut (on ne force rien) ; effort = medium
                # par défaut sur ce modèle, ce qui convient à une Q/R rapide.
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
                    self.pending_image_turn = False
                    self._write("\n")
                    self._set_busy(False)
                    self._set_status("Réponse reçue. Vous pouvez poser une question de suivi.")
                    return
                elif kind == "error":
                    # Annule le tour utilisateur ajouté pour permettre un nouvel essai.
                    if self.messages and self.messages[-1]["role"] == "user":
                        self.messages.pop()
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
        state = "disabled" if busy else "normal"
        self.send_btn.configure(state=state)
        self._set_status("Claude réfléchit…" if busy else "Prêt.")

    def reset_conversation(self):
        self.messages = []
        self.pending_image_turn = self.current_image is not None
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._log_info("Conversation réinitialisée." + (" L'image actuelle est conservée." if self.current_image else ""))
        self._set_status("Conversation réinitialisée.")


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
