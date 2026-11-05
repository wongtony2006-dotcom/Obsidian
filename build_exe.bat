@echo off
REM ============================================================================
REM  Construit l'executable Windows (.exe) de Clairvue.
REM  A lancer SUR WINDOWS (double-clic ou invite de commandes).
REM  Resultat :  dist\Clairvue.exe
REM ============================================================================

cd /d "%~dp0"

if not exist ".venv\" (
    echo Creation de l'environnement virtuel...
    python -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo Installation des dependances (+ PyInstaller)...
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo Generation de l'icone...
python assets\make_icon.py

set ICON_ARGS=
if exist "assets\clairvue.ico" set ICON_ARGS=--icon assets\clairvue.ico --add-data assets\clairvue.ico;.

echo Compilation de l'executable...
pyinstaller --noconfirm --onefile --windowed ^
  --name Clairvue %ICON_ARGS% ^
  --collect-all anthropic ^
  --collect-all pydantic ^
  --hidden-import PIL._tkinter_finder ^
  app.py

echo.
if exist "dist\Clairvue.exe" (
    echo ============================================================
    echo  Termine !  ->  dist\Clairvue.exe
    echo ============================================================
) else (
    echo La compilation a echoue. Lisez les messages ci-dessus.
)
pause
