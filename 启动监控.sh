#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi

echo
echo "=========================================="
echo "  Futures Premium Dashboard"
echo "=========================================="
echo

echo "[1/3] Check Python..."
if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.9+ was not found."
    echo "Install Python first, then run this script again."
    exit 1
fi

$PYTHON_CMD --version

if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment..."
    if ! $PYTHON_CMD -m venv .venv; then
        echo "[ERROR] Failed to create virtual environment."
        echo "Try this manually:"
        echo "  sudo apt install python3-venv"
        exit 1
    fi
fi

PYTHON_CMD=".venv/bin/python"

echo "[2/3] Check dependencies..."
if ! $PYTHON_CMD -m pip show akshare >/dev/null 2>&1; then
    echo "[INFO] Installing requirements..."
    if ! $PYTHON_CMD -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple; then
        echo "[ERROR] Failed to install requirements."
        echo "Try this manually:"
        echo "  $PYTHON_CMD -m pip install -r requirements.txt"
        exit 1
    fi
fi

echo "[3/3] Start web server..."
echo
echo "=========================================="
echo "  Open this address in your browser:"
echo "  http://127.0.0.1:5005"
echo "=========================================="
echo

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://127.0.0.1:5005 >/dev/null 2>&1 || true
fi

$PYTHON_CMD main.py --web --port 5005
