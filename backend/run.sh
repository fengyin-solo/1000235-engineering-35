#!/usr/bin/env bash
# 启动顺序：自检构建依赖 -> 依赖齐备才启动报告服务。
# 任何一项缺失都会停止启动，并把缺失项打印出来。
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "启动中止：缺失构建依赖 python3，请先安装 Python 3" >&2
  exit 1
fi

# 虚拟环境不存在、或解释器已失效（比如从别的机器拷贝过来）时重建
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "" >/dev/null 2>&1; then
  echo "虚拟环境缺失或已失效，正在重建 .venv ..."
  rm -rf .venv
  if ! python3 -m venv .venv; then
    echo "启动中止：无法创建虚拟环境，缺失构建依赖 python3-venv（Debian/Ubuntu 请执行 apt install python3-venv）" >&2
    exit 1
  fi
fi

# 依赖缺失时先按 requirements.txt 补装一次，再自检仍缺失就列出清单并停止
if ! .venv/bin/python -m app.bootstrap >/dev/null 2>&1; then
  .venv/bin/pip install -q -r requirements.txt || true
fi
if ! .venv/bin/python -m app.bootstrap; then
  exit 1
fi

# 自检全部通过，才提供报告服务
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
