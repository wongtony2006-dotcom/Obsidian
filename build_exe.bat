@echo off
REM ============================================================================
REM  Construit l'executable Windows (.exe) de l'assistant capture -> Claude.
REM  A lancer SUR WINDOWS (double-clic ou depuis une invite de commandes).
REM  Resultat :  dist\AssistantCaptureClaude.exe
REM ============================================================================

cd /d "%~dp0"

REM --- Environnement virtuel + dependances ------------------------------------
if not exist ".venv\" (
    echo Creation de l'environnement virtuel...
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo Installation des dependances (+ PyInstaller)...
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

REM --- Compilation ------------------------------------------------------------
echo Compilation de l'executable...
pyinstaller --noconfirm --onefile --windowed ^
  --name AssistantCaptureClaude ^
  --collect-all anthropic ^
  --collect-all pydantic ^
  --hidden-import PIL._tkinter_finder ^
  app.py

echo.
if exist "dist\AssistantCaptureClaude.exe" (
    echo ============================================================
    echo  Termine !  ->  dist\AssistantCaptureClaude.exe
    echo ============================================================
) else (
    echo La compilation a echoue. Lisez les messages ci-dessus.
)
pause
