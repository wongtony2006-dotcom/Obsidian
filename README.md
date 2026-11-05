# 🔎 Clairvue — Assistant d'écran intelligent

**Clairvue** prend une capture d'écran (région, plein écran, ou image chargée),
l'envoie à **Claude** (API Anthropic) et répond à vos questions : explication,
résumé, OCR, traduction, aide sur une erreur ou du code, raisonnement pas à pas…

C'est un outil d'**étude et de productivité**, pour votre propre usage.

---

## ✨ Fonctionnalités

- **Capture** : région (glisser à la souris), plein écran, ou image depuis un fichier.
- **Modes spéciaux (macros intégrées)** — un clic pour :
  - 🧠 Expliquer · 📝 Résumer · 📄 Extraire le texte (OCR) · 🌐 Traduire
  - ✅ Corriger · 🐞 Expliquer l'erreur · 💻 Expliquer le code · 📊 Tableau → données · 🪜 Pas à pas
- **Macros personnalisées** : créez vos propres prompts réutilisables (menu *Macros*).
- **Raccourcis clavier globaux** (Windows) :
  - `Ctrl+Shift+S` → capturer une région
  - `Ctrl+Shift+F` → capturer tout l'écran
  - *Lancer à la capture* : la question part automatiquement avec le mode choisi.
- **Conversation** : questions de suivi avec contexte de l'image.
- **Historique persistant** + **export Markdown** (conversation ou historique complet).
- **Réglages** : modèle (Opus / Sonnet / Haiku), effort (rapide / standard / approfondi),
  langue de réponse, **thème clair / sombre**, **toujours au-dessus**.
- **Confort** : copier la réponse, enregistrer la capture, **stop** pour interrompre une génération.

Les réglages, l'historique et les macros sont enregistrés dans `~/.clairvue/`.

---

## ⚠️ Périmètre de l'outil (important)

Application **normale et visible**. Elle **ne contient aucun mécanisme** destiné à :

- se cacher d'un logiciel de surveillance / proctoring ;
- contourner la détection de l'**Alt+Tab** ou de la **touche Windows** ;
- rester invisible lors d'un **partage** ou **enregistrement d'écran**.

Les « raccourcis globaux » servent seulement à lancer une capture sans cliquer dans la fenêtre — ils ne cachent rien. La fenêtre apparaît dans la barre des tâches, dans l'Alt+Tab et dans un partage d'écran, comme tout programme.

---

## ⬇️ Obtenir l'exécutable (.exe)

### A) Depuis les Releases (recommandé)

Téléchargez **`Clairvue.exe`** depuis la page des **Releases** :
→ https://github.com/wongtony2006-dotcom/Obsidian/releases

C'est un exécutable **autonome** (Python embarqué) : aucun installation requise. Lancez-le, saisissez votre clé API Anthropic, c'est prêt.

### B) Le laisser compiler par GitHub Actions

À chaque push, le workflow **« Build Clairvue (Windows EXE) »** compile l'exe sur Windows.
Onglet **Actions** → dernier run → section **Artifacts** → **`Clairvue-windows`**.
(Ou **Run workflow** manuellement : renseignez un *tag* pour créer une Release.)

### C) Le compiler soi-même

Double-cliquez sur **`build_exe.bat`** → génère `dist\Clairvue.exe`.

---

## ▶️ Lancer depuis les sources

### Prérequis
- **Windows 10/11**, **Python 3.9+** ([python.org](https://www.python.org/downloads/), cochez « Add Python to PATH »)
- Une **clé API Anthropic** — [console.anthropic.com](https://console.anthropic.com/)

### Démarrage
Double-cliquez sur **`run.bat`**, ou :

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## 🔑 Configurer la clé API

Trois possibilités (la première trouvée est utilisée) :

1. **Dans l'application** : champ « Clé API Anthropic » en haut.
2. **Fichier `.env`** : copiez `.env.example` en `.env` et renseignez `ANTHROPIC_API_KEY` (à côté de l'exe pour la version compilée).
3. **Variable d'environnement** : `setx ANTHROPIC_API_KEY "sk-ant-..."` (rouvrez le terminal ensuite).

---

## 🧭 Utilisation

1. Réglez le **modèle**, l'**effort**, la **langue** (en-tête) et le **mode** (barre de gauche).
2. **Capturez** (bouton, ou `Ctrl+Shift+S` / `Ctrl+Shift+F`, ou chargez une image).
3. Tapez votre question et **Demander** (ou `Ctrl+Entrée`) — ou **▶ Lancer le mode** pour utiliser la question par défaut du mode.
4. La réponse s'affiche en streaming ; **⏹ Stop** pour l'interrompre.
5. **Historique** / **Fichier → Exporter** pour revoir ou exporter vos échanges.

---

## 🛠️ Détails techniques

- **Modèles** : `claude-opus-5-5` (défaut), `claude-sonnet-5-5`, `claude-haiku-5-5` — SDK officiel `anthropic`, vision en PNG base64, réponse en **streaming** (thread séparé).
- **Effort** : `output_config.effort` = low / medium / high.
- **Modes** = instructions ajoutées au *system prompt* ; **macros** = modes définis par vous.
- **Raccourcis globaux** : API Win32 `RegisterHotKey` (thread dédié → file thread-safe).
- **Icône** : générée par `assets/make_icon.py`, intégrée à l'exe.
- **DPI-aware** : la zone sélectionnée correspond aux pixels capturés.

### Notes
- La sélection de **région** cible l'écran principal ; en multi-écrans, utilisez **plein écran** puis recadrez.
- Rien n'est envoyé tant que vous ne lancez pas une demande. L'image part alors vers l'API Anthropic pour obtenir la réponse.

---

## 🗂️ Structure du projet

```
.
├── app.py                              # Application Clairvue (UI + logique + API)
├── assets/
│   ├── make_icon.py                    # Génère l'icône
│   ├── clairvue.ico / clairvue.png     # Icône de l'app
├── requirements.txt                    # Dépendances Python
├── run.bat                             # Lanceur depuis les sources
├── build_exe.bat                       # Construit dist\Clairvue.exe
├── .github/workflows/build-windows.yml # CI : compile l'exe + Release
├── .env.example                        # Modèle de clé API
├── .gitignore
└── README.md
```

## 🩺 Dépannage

| Problème | Piste |
|---|---|
| « Clé API invalide ou manquante » | Vérifiez la clé (champ, `.env`, ou variable d'environnement). |
| Raccourci global « indisponible » | Un autre logiciel l'utilise ; les boutons fonctionnent toujours. |
| Zone capturée décalée | Relancez l'app (le DPI est pris en compte au démarrage). |
| `ModuleNotFoundError` | Activez le venv puis `pip install -r requirements.txt`. |
| Capture noire / vide | Fenêtres protégées (vidéo DRM) non capturables par l'OS. |
| L'antivirus signale le `.exe` | Faux positif courant des exe PyInstaller « onefile » ; préférez la Release ou les sources. |
