@echo off
REM Lance l'assistant capture d'ecran -> Claude sur Windows.
REM Double-cliquez sur ce fichier, ou lancez-le depuis une invite de commandes.

cd /d "%~dp0"

REM Cree un environnement virtuel au premier lancement.
if not exist ".venv\" (
    echo Creation de l'environnement virtuel...
    python -m venv .venv
    call ".venv\Scripts\activate.bat"
    echo Installation des dependances...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call ".venv\Scripts\activate.bat"
)

python app.py
