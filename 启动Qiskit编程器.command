#!/bin/zsh

set -e
PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

if [[ ! -x .venv/bin/python ]]; then
    echo "尚未安装本地环境。请先运行："
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -r requirements.txt"
    read "?按回车退出…"
    exit 1
fi

exec .venv/bin/python qiskit_ide.py
