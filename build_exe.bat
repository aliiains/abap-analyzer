@echo off
title Building ABAP Analyser EXE

echo.
echo ================================================
echo   ABAP Code Analyser - Building EXE
echo ================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found.
    echo Install Python 3.10+ from python.org
    echo Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/4] Python found:
python --version
echo.

echo [2/4] Installing PyInstaller...
python -m pip install pyinstaller --upgrade --quiet
echo Done.
echo.

echo [3/4] Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ABAP_Analyser.spec del /f ABAP_Analyser.spec
echo Done.
echo.

echo [4/4] Building EXE (1-3 minutes)...
echo.

python -m PyInstaller --onefile --windowed --name ABAP_Analyser --hidden-import tkinter --hidden-import tkinter.ttk --hidden-import tkinter.messagebox --hidden-import tkinter.filedialog --collect-submodules tkinter main.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed. See output above.
    echo Try running: python build_exe.py
    pause
    exit /b 1
)

echo.
echo ================================================
echo   SUCCESS! File created: dist\ABAP_Analyser.exe
echo ================================================
echo.

explorer dist

pause
