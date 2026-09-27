"""启动前自检：构建依赖缺失时列出清单并以非零码退出，自检通过才放行服务启动。

只依赖标准库，保证环境残缺时这个检查器本身也能跑起来：
    python -m app.bootstrap
"""
from __future__ import annotations

import importlib.util
import sys

# 模块名 -> requirements.txt 里的依赖名，缺失时按依赖名提示
REQUIRED_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "pydantic": "pydantic",
}


def missing_dependencies() -> list[str]:
    """返回缺失的依赖清单；空列表表示自检通过。"""
    return [
        package
        for module, package in REQUIRED_MODULES.items()
        if importlib.util.find_spec(module) is None
    ]


def main() -> int:
    missing = missing_dependencies()
    if missing:
        print(f"启动中止：缺失构建依赖 {'、'.join(missing)}", file=sys.stderr)
        print("请先执行 make install 或 pip install -r requirements.txt 再启动", file=sys.stderr)
        return 1
    print("依赖自检通过：fastapi、uvicorn、pydantic 均已就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
