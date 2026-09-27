#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
# 构建依赖缺失时在这里停止启动，并由 preflight 列出缺失项
.venv/bin/python -m app.preflight
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
