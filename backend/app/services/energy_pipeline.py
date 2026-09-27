"""能效报告计算流水线：分析周期、系统效率、损失构成都从同一份基准数据推出。

流水线可重复执行，每次运行分四步：
1. 读取基准数据（``app.baseline.ENERGY_BASELINE``），按电站分组；
2. 在暂存区算出每座电站的分析周期、理论/实际发电量、系统效率与损失构成，不碰仓库；
3. 把当前发布的旧报告整体隔离进归档表（打上隔离时间与运行编号）；
4. 用暂存结果整体替换发布表——隔离与替换在同一把锁里完成，列表不会出现新旧混排。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.baseline import ENERGY_BASELINE, LOSS_FIELDS
from app.store import store

PUBLISH_MODULE = "energy_saving"
ARCHIVE_MODULE = "energy_saving_archive"
OTHER_LOSS_LABEL = "其他损失"

_lock = threading.Lock()
_runs: list[dict[str, Any]] = []


def _stage_reports() -> list[dict[str, Any]]:
    """只读基准数据，在暂存区算出报告行；这一步不修改仓库。"""
    by_plant: dict[str, list[dict[str, Any]]] = {}
    for row in ENERGY_BASELINE:
        by_plant.setdefault(str(row["电站编号"]), []).append(row)

    staged: list[dict[str, Any]] = []
    for index, plant in enumerate(sorted(by_plant), start=1):
        rows = by_plant[plant]
        dates = sorted(str(row["日期"]) for row in rows)
        theoretical = sum(float(row["辐照度"]) * float(row["装机容量"]) for row in rows)
        actual = sum(float(row["实际发电量"]) for row in rows)
        losses = {field: sum(float(row[field]) for row in rows) for field in LOSS_FIELDS}
        other = theoretical - actual - sum(losses.values())
        efficiency = actual / theoretical * 100 if theoretical else 0.0

        parts = [
            f"{field.removesuffix('损失')} {value:.1f} kWh（{value / theoretical * 100:.1f}%）"
            for field, value in losses.items()
        ]
        parts.append(f"{OTHER_LOSS_LABEL} {other:.1f} kWh（{other / theoretical * 100:.1f}%）")

        staged.append({
            "id": index,
            "报告编号": f"ENER-{index:04d}",
            "电站编号": plant,
            "分析周期": f"{dates[0]} ~ {dates[-1]}",
            "理论发电量": f"{theoretical:.1f} kWh",
            "实际发电量": f"{actual:.1f} kWh",
            "系统效率": f"{efficiency:.1f}%",
            "损失分析": "、".join(parts),
            "报告状态": "已生成",
            "status": "已生成",
            "pending": True,
            "abnormal": other < 0,
        })
    return staged


def run_pipeline(trigger: str = "manual") -> dict[str, Any]:
    """执行一次完整流水线：暂存计算 → 隔离旧结果 → 整体替换，返回本次运行摘要。"""
    with _lock:
        run_id = f"RUN-{len(_runs) + 1:04d}"
        started = datetime.now().isoformat(timespec="seconds")
        staged = _stage_reports()
        for row in staged:
            row["pipeline_run"] = run_id
        isolated = store.isolate_and_replace(
            PUBLISH_MODULE,
            ARCHIVE_MODULE,
            staged,
            stamp={"pipeline_run": run_id, "隔离时间": started, "隔离原因": "流水线重跑，旧结果先隔离再替换"},
        )
        run = {
            "run_id": run_id,
            "trigger": trigger,
            "started_at": started,
            "baseline_rows": len(ENERGY_BASELINE),
            "published": len(staged),
            "isolated": isolated,
            "status": "成功",
        }
        _runs.append(run)
        return run


def pipeline_runs() -> list[dict[str, Any]]:
    """历次运行记录，新的排在前面。"""
    return list(reversed(_runs))


def archived_reports() -> list[dict[str, Any]]:
    """被隔离的历史报告：重跑前的旧结果在这里可查，但不再参与列表。"""
    return store.rows(ARCHIVE_MODULE)
