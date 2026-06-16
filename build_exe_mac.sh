#!/usr/bin/env bash
# ================================================
# ABAP Code Analyser — сборка .app для macOS
# ================================================
set -e

echo ""
echo "================================================"
echo "  ABAP Code Analyser — сборка приложения macOS"
echo "================================================"
echo ""

# Проверяем Python
if ! command -v python3 &>/dev/null; then
    echo "[ОШИБКА] Python 3 не найден. Установите с python.org или через Homebrew:"
    echo "         brew install python"
    exit 1
fi

echo "[1/4] Python найден: $(python3 --version)"
echo ""

# Устанавливаем PyInstaller
echo "[2/4] Устанавливаем PyInstaller..."
pip3 install pyinstaller --quiet --upgrade
echo "      Готово."
echo ""

# Собираем
echo "[3/4] Собираем .app (1-2 минуты)..."
pyinstaller --onefile \
            --windowed \
            --name "ABAP_Analyser" \
            main.py

echo ""
echo "[4/4] Готово!"
echo ""
echo "================================================"
echo "  Ваш файл: dist/ABAP_Analyser"
echo "  На macOS: dist/ABAP_Analyser.app"
echo "  Запускайте двойным кликом."
echo "================================================"
echo ""

# Открываем папку в Finder
open dist/ 2>/dev/null || true
