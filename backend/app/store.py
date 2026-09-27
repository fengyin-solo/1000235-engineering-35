"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
流水线归档表这类内部表不进模块清单与概览看板，只能按名字直取。
"""
from __future__ import annotations

import threading
from typing import Any

from app.seed import SEED_ROWS

# 流水线隔离区这类内部表：不对看板暴露，只供业务代码按名读写
INTERNAL_MODULES = {"energy_saving_archive"}


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(name for name in self._tables if name not in INTERNAL_MODULES)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def isolate_and_replace(
        self,
        source: str,
        archive: str,
        new_rows: list[dict[str, Any]],
        *,
        stamp: dict[str, Any],
    ) -> int:
        """把 source 现有行打上戳整体隔离进 archive，再用 new_rows 替换。

        隔离与替换在同一把锁里完成，读列表的任何时刻都只会看到一份完整结果。
        返回被隔离的行数。
        """
        with self._lock:
            current = self._tables.setdefault(source, [])
            isolated = [{**row, **stamp} for row in current]
            self._tables.setdefault(archive, []).extend(isolated)
            self._tables[source] = [dict(row) for row in new_rows]
            return len(isolated)

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
