# Assistant Capture d'écran → Claude

Une application de bureau **Windows** qui permet de :

1. **Prendre une capture d'écran** — une région sélectionnée à la souris, ou tout l'écran — (ou charger une image existante) ;
2. **Poser une question** sur cette capture ;
3. **Obtenir une réponse de Claude** (API Anthropic) : explication, résumé, OCR (lecture du texte), traduction, aide à la compréhension d'un message d'erreur, raisonnement pas à pas…

### Fonctionnalités

- 🖱️ **Capture** : région (glisser à la souris), plein écran, ou image chargée depuis un fichier.
- ⌨️ **Raccourcis clavier globaux** (Windows) : déclencher une capture sans cliquer dans la fenêtre.
  - `Ctrl+Shift+S` → capturer une région
  - `Ctrl+Shift+F` → capturer tout l'écran
- 💬 **Questions de suivi** : la conversation garde le contexte de l'image.
- 🗂️ **Historique persistant** des échanges (question/réponse), consultable dans l'app.
- 📝 **Export Markdown** de la conversation en cours ou de tout l'historique.
- 🧠 **Choix du modèle** dans l'interface : Opus 5.5 / Sonnet 5.5 / Haiku 5.5.

---

## ⚠️ Périmètre de l'outil (important)

C'est une application **normale et visible**, pensée comme un outil d'**étude et de productivité pour votre propre usage**.

Elle **ne contient aucun mécanisme** destiné à :

- se cacher d'un logiciel de surveillance / proctoring ;
- contourner la détection de l'**Alt+Tab** ou de la **touche Windows** ;
- rester invisible lors d'un **partage** ou d'un **enregistrement d'écran**.

Les « raccourcis globaux » servent seulement à lancer une capture sans revenir dans la fenêtre — ils ne cachent rien. La fenêtre se comporte comme n'importe quel programme : elle apparaît dans la barre des tâches, dans l'Alt+Tab et dans un partage d'écran.

---

## Obtenir l'exécutable (.exe)

Il y a deux façons d'avoir le `.exe` Windows.

### A) Le laisser compiler par GitHub (recommandé — aucune installation)

À chaque push sur la branche, un **workflow GitHub Actions** compile le `.exe` sur une machine Windows.

1. Ouvrez l'onglet **Actions** du dépôt sur GitHub.
2. Ouvrez le dernier run **« Build Windows EXE »** (vous pouvez aussi le lancer à la main via **Run workflow**).
3. En bas de la page du run, section **Artifacts**, téléchargez **`AssistantCaptureClaude-windows`** (une archive contenant `AssistantCaptureClaude.exe`).

> Astuce : pour attacher le `.exe` directement à une **Release**, créez une release/tag — le workflow y joindra l'exécutable automatiquement.

### B) Le compiler soi-même sur Windows

Double-cliquez sur **`build_exe.bat`**. Il crée un environnement virtuel, installe les dépendances + PyInstaller, et produit :

```
dist\AssistantCaptureClaude.exe
```

(Équivalent en ligne de commande : voir le contenu de `build_exe.bat`.)

---

## Lancer sans compiler (depuis les sources)

### Prérequis

- **Windows 10/11**
- **Python 3.9+** ([python.org](https://www.python.org/downloads/) — cochez « Add Python to PATH »)
- Une **clé API Anthropic** — [console.anthropic.com](https://console.anthropic.com/)

### Démarrage

Double-cliquez sur **`run.bat`** (crée le venv, installe les dépendances, démarre l'app).

Ou manuellement :

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## Configurer la clé API

Trois possibilités (la première trouvée est utilisée) :

1. **Dans l'application** : collez la clé dans le champ « Clé API » en haut de la fenêtre.
2. **Fichier `.env`** : copiez `.env.example` en `.env` et renseignez `ANTHROPIC_API_KEY`. (Ignoré par git.)
3. **Variable d'environnement** `ANTHROPIC_API_KEY` :
   ```bat
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
   (rouvrez le terminal après `setx`).

> Pour le `.exe`, utilisez le champ dans l'app ou la variable d'environnement (le `.env` doit se trouver à côté de l'exe).

---

## Utilisation

1. Choisissez éventuellement le **modèle** (menu déroulant en haut).
2. **Capturez** : bouton 📐/🖥, un raccourci global (`Ctrl+Shift+S` / `Ctrl+Shift+F`), ou chargez une image.
3. Tapez votre question en bas et cliquez **Demander à Claude** (ou **Ctrl+Entrée**).
4. La réponse s'affiche en continu (streaming). Enchaînez des questions de suivi.
5. **♻ Nouvelle conversation** repart de zéro (l'image en cours est conservée).
6. **Historique** (menu) : revoir les échanges passés. **Fichier → Exporter…** pour un `.md`.

---

## Détails techniques

- **Modèles** : `claude-opus-5-5` (défaut), `claude-sonnet-5-5`, `claude-haiku-5-5`, via le SDK officiel `anthropic`.
- **Vision** : l'image est envoyée en bloc `image` (PNG base64) avec la question.
- **Streaming** dans un thread séparé ; l'interface reste réactive.
- **Raccourcis globaux** : API Win32 `RegisterHotKey` (Windows uniquement), dans un thread dédié, communiqués à l'interface via une file thread-safe.
- **Historique** : fichier JSON dans `~/.screenshot_assistant/history.json`.
- **DPI** : l'app se déclare « DPI-aware » pour que la zone sélectionnée corresponde aux pixels capturés.

### Notes

- La **sélection de région** cible l'écran principal. En multi-écrans, utilisez **Capturer tout l'écran** puis recadrez.
- Rien n'est envoyé tant que vous ne cliquez pas sur « Demander à Claude ». En cliquant, l'image est transmise à l'API Anthropic pour obtenir la réponse.

## Structure du projet

```
.
├── app.py                              # Application (UI Tkinter + appels API)
├── requirements.txt                    # Dépendances Python
├── run.bat                             # Lanceur Windows (venv + install + run)
├── build_exe.bat                       # Construit dist\AssistantCaptureClaude.exe
├── .github/workflows/build-windows.yml # CI : compile le .exe sur Windows
├── .env.example                        # Modèle de configuration de la clé API
├── .gitignore
└── README.md
```

## Dépannage

| Problème | Piste |
|---|---|
| « Clé API invalide ou manquante » | Vérifiez la clé (champ, `.env`, ou variable d'environnement). |
| Raccourci global « indisponible » | Un autre logiciel l'utilise déjà ; fermez-le ou ignorez (les boutons marchent). |
| La zone capturée est décalée | Relancez l'app (la prise en compte du DPI se fait au démarrage). |
| `ModuleNotFoundError` | Activez le venv et relancez `pip install -r requirements.txt`. |
| Capture noire / vide | Certaines fenêtres protégées (vidéo DRM) ne sont pas capturables par l'OS. |
| L'antivirus signale le `.exe` | Faux positif courant des exe PyInstaller « onefile ». Préférez le build GitHub Actions, ou lancez depuis les sources. |
