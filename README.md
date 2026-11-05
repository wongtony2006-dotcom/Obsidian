# Assistant Capture d'écran → Claude

Une application de bureau **Windows** qui permet de :

1. **Prendre une capture d'écran** — une région sélectionnée à la souris, ou tout l'écran — (ou charger une image existante) ;
2. **Poser une question** sur cette capture ;
3. **Obtenir une réponse de Claude** (API Anthropic) : explication, résumé, OCR (lecture du texte), traduction, aide à la compréhension d'un message d'erreur, raisonnement pas à pas…

Les questions de suivi fonctionnent sur la même image (la conversation garde le contexte). Une nouvelle capture démarre une nouvelle conversation.

---

## ⚠️ Périmètre de l'outil (important)

C'est une application **normale et visible**, pensée comme un outil d'**étude et de productivité pour votre propre usage**.

Elle **ne contient aucun mécanisme** destiné à :

- se cacher d'un logiciel de surveillance / proctoring ;
- contourner la détection de l'**Alt+Tab** ou de la **touche Windows** ;
- rester invisible lors d'un **partage** ou d'un **enregistrement d'écran**.

La fenêtre se comporte comme n'importe quel programme : elle apparaît dans la barre des tâches, dans l'Alt+Tab et dans un partage d'écran. Si vous devez utiliser un outil d'aide, faites-le dans un cadre où cela est autorisé.

---

## Prérequis

- **Windows 10/11**
- **Python 3.9+** ([python.org](https://www.python.org/downloads/) — cochez « Add Python to PATH » à l'installation)
- Une **clé API Anthropic** — [console.anthropic.com](https://console.anthropic.com/)

## Installation & lancement

### Option simple (recommandée)

Double-cliquez sur **`run.bat`**. Au premier lancement, il crée un environnement virtuel, installe les dépendances, puis démarre l'application.

### Option manuelle

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Configurer la clé API

Trois possibilités (la première trouvée est utilisée) :

1. **Dans l'application** : collez la clé dans le champ « Clé API Anthropic » en haut de la fenêtre.
2. **Fichier `.env`** : copiez `.env.example` en `.env` et renseignez `ANTHROPIC_API_KEY`. (Le fichier `.env` est ignoré par git.)
3. **Variable d'environnement** `ANTHROPIC_API_KEY` :
   ```bat
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
   (rouvrez le terminal après `setx`).

## Utilisation

1. Cliquez sur **📐 Capturer une région** (puis glissez pour sélectionner), **🖥 Capturer tout l'écran**, ou **📂 Charger une image…**
2. Tapez votre question dans le champ du bas.
3. Cliquez **Demander à Claude** (ou **Ctrl+Entrée**).
4. La réponse s'affiche en continu (streaming). Vous pouvez enchaîner des questions de suivi.
5. **♻ Nouvelle conversation** repart de zéro (l'image en cours est conservée).

## Détails techniques

- **Modèle** : `claude-opus-5-5` (le plus capable), via le SDK officiel `anthropic`.
- **Vision** : l'image est envoyée en bloc `image` (PNG base64) avec la question.
- **Streaming** : la réponse arrive en continu ; l'appel tourne dans un thread séparé pour ne pas bloquer l'interface.
- **DPI** : l'app se déclare « DPI-aware » sur Windows pour que la zone sélectionnée corresponde aux pixels réellement capturés.

### Notes

- La **sélection de région** cible l'écran principal. Pour les configurations multi-écrans, utilisez **Capturer tout l'écran** (qui inclut les écrans secondaires) puis recadrez si besoin.
- Rien n'est envoyé nulle part tant que vous ne cliquez pas sur « Demander à Claude ». La capture reste locale jusque-là. En cliquant, l'image est transmise à l'API Anthropic pour obtenir la réponse.

## Structure du projet

```
.
├── app.py             # Application (interface Tkinter + appels API)
├── requirements.txt   # Dépendances Python
├── run.bat            # Lanceur Windows (venv + install + run)
├── .env.example       # Modèle de configuration de la clé API
├── .gitignore
└── README.md
```

## Dépannage

| Problème | Piste |
|---|---|
| « Clé API invalide ou manquante » | Vérifiez la clé dans le champ, le `.env`, ou la variable d'environnement. |
| La zone capturée est décalée | Fermez puis relancez l'app (la prise en compte du DPI se fait au démarrage). |
| `ModuleNotFoundError` | Activez le venv et relancez `pip install -r requirements.txt`. |
| Capture noire / vide | Certaines fenêtres protégées (lecteurs vidéo DRM) ne sont pas capturables par l'OS. |
