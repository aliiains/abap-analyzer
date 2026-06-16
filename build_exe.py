"""
Build script for ABAP Code Analyser.
Run with: python build_exe.py

Works on Windows, macOS, and Linux.
Requires Python 3.10+ with pip available.
"""

import subprocess
import sys
import os
import shutil


def run(cmd, description):
    print(f"\n>>> {description}")
    print(f"    Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"\n[ERROR] Step failed: {description}")
        sys.exit(1)
    print(f"    Done.")


def main():
    print()
    print("=" * 50)
    print("  ABAP Code Analyser - Build Script")
    print("=" * 50)

    # Check Python version
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"[ERROR] Python 3.10+ required. Found: {sys.version}")
        sys.exit(1)
    print(f"\n[OK] Python {version.major}.{version.minor}.{version.micro}")

    # Install PyInstaller
    run(
        [sys.executable, "-m", "pip", "install", "pyinstaller", "--upgrade", "--quiet"],
        "Installing PyInstaller"
    )

    # Clean previous build
    print("\n>>> Cleaning old build files...")
    for folder in ("build", "dist"):
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"    Removed: {folder}/")
    for spec_file in ("ABAP_Analyser.spec",):
        if os.path.exists(spec_file):
            os.remove(spec_file)
            print(f"    Removed: {spec_file}")

    # Build
    run(
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name", "ABAP_Analyser",
            "--hidden-import", "tkinter",
            "--hidden-import", "tkinter.ttk",
            "--hidden-import", "tkinter.messagebox",
            "--hidden-import", "tkinter.filedialog",
            "--collect-submodules", "tkinter",
            "main.py",
        ],
        "Building executable (this takes 1-3 minutes)"
    )

    # Result
    exe_name = "ABAP_Analyser.exe" if sys.platform == "win32" else "ABAP_Analyser"
    exe_path = os.path.join("dist", exe_name)

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print()
        print("=" * 50)
        print("  SUCCESS!")
        print(f"  File: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
        print("=" * 50)
        print()
    else:
        print("\n[ERROR] EXE not found after build. Check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
