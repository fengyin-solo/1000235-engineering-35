"""启动前依赖检查：构建依赖缺失时停止启动并指出缺失项。

run.sh 在拉起 uvicorn 之前先执行 ``python -m app.preflight``；应用 lifespan 里会再查一次，
防止绕过脚本直接启动。检查本身只依赖标准库，缺任何第三方包都能跑出缺失清单。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"

# 发行包名 → 导入名；不在表里的按包名转模块名（小写、中划线换下划线）处理
_DIST_TO_IMPORT = {
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "pydantic": "pydantic",
}

_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)(\[[^\]]*\])?")


def _parse_requirement(line: str) -> str | None:
    """从 requirements.txt 的一行里取出发行包名；注释和空行返回 None。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    match = _REQUIREMENT_RE.match(line)
    return match.group(1) if match else None


def find_missing_dependencies(requirements: Path | None = None) -> list[str]:
    """对照 requirements.txt 逐项检查，返回缺失的依赖（保留原始写法，方便直接安装）。"""
    path = requirements or REQUIREMENTS
    missing: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        dist = _parse_requirement(raw)
        if dist is None:
            continue
        module = _DIST_TO_IMPORT.get(dist.lower(), dist.lower().replace("-", "_"))
        if importlib.util.find_spec(module) is None:
            missing.append(raw.strip())
    return missing


def main() -> int:
    missing = find_missing_dependencies()
    if missing:
        print("构建依赖缺失，停止启动。缺少以下依赖：", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        print("请先执行：pip install -r requirements.txt", file=sys.stderr)
        return 1
    print("构建依赖检查通过，继续启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
