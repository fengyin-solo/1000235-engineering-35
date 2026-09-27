"""能效报告计算流水线：分析周期、系统效率、损失构成从同一份基准数据推导。

流水线可重复执行：每轮先把上一轮生成的报告整批隔离到归档表，
新结果全部算完再一次性替换发布；计算中途失败时旧结果原样保留。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.store import store

BASELINE_MODULE = "energy_baseline"  # 基准数据：逐日发电与损失明细
REPORT_MODULE = "energy_saving"  # 对外提供的能效报告
ARCHIVE_MODULE = "energy_saving_archive"  # 隔离区：被替换掉的旧结果

GENERATED_BY = "能效流水线"

# 基准记录必须齐全的字段，缺了就没法保证三份产出同源
BASELINE_REQUIRED = ["电站编号", "记录日期", "峰值日照时数", "装机容量kWp", "实际发电量kWh"]
LOSS_FIELDS = ["组件损失kWh", "逆变器损失kWh", "线路损失kWh", "灰尘遮挡kWh", "停机损失kWh"]


class BaselineError(RuntimeError):
    """基准数据缺失或字段不全：把问题攒成清单一次性抛出。"""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("；".join(problems))


@dataclass(frozen=True)
class PipelineSummary:
    """一轮流水线的结果：批次号、分析周期、隔离与新增数量。"""

    batch: str
    period: str
    generated: int
    isolated: int
    plants: list[str] = field(default_factory=list)


class EnergyReportPipeline:
    def __init__(self, data_store: Any = store) -> None:
        self._store = data_store

    def run(self) -> PipelineSummary:
        """完整跑一轮：取数 -> 计算 -> 隔离旧结果 -> 替换发布。"""
        snapshot = self.load_baseline()  # 取数失败直接中止，旧结果不动
        reports = self.build_reports(snapshot)  # 纯计算，不碰仓库
        batch = self._next_batch()
        isolated = self._publish(reports, batch)
        return PipelineSummary(
            batch=batch,
            period=self.derive_period(snapshot),
            generated=len(reports),
            isolated=isolated,
            plants=[report["电站编号"] for report in reports],
        )

    # 阶段一：取数 —— 同一份快照喂给周期、效率、损失三段计算
    def load_baseline(self) -> list[dict[str, Any]]:
        rows = [dict(row) for row in self._store.rows(BASELINE_MODULE)]
        problems: list[str] = []
        if not rows:
            problems.append(f"基准数据表 {BASELINE_MODULE} 为空")
        for row in rows:
            missing = [name for name in BASELINE_REQUIRED + LOSS_FIELDS if row.get(name) in (None, "")]
            if missing:
                problems.append(f"基准记录 {row.get('id', '?')} 缺字段：{'、'.join(missing)}")
        if problems:
            raise BaselineError(problems)
        return rows

    # 阶段二：分析周期取基准数据覆盖的日期跨度
    @staticmethod
    def derive_period(snapshot: list[dict[str, Any]]) -> str:
        dates = sorted(str(row["记录日期"]) for row in snapshot)
        return f"{dates[0]} ~ {dates[-1]}"

    # 阶段三/四：按电站聚合，系统效率与损失构成读的是同一份快照
    def build_reports(
        self,
        snapshot: list[dict[str, Any]],
        plants: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in snapshot:
            plant = str(row["电站编号"])
            if plants is not None and plant not in plants:
                continue
            groups.setdefault(plant, []).append(row)
        return [
            self._plant_report(plant, rows, self.derive_period(rows))
            for plant, rows in sorted(groups.items())
        ]

    def compute_for_plant(self, plant: str) -> dict[str, Any]:
        """给单条报告算一份结果，与整轮流水线共用同一份基准数据和算法。"""
        snapshot = self.load_baseline()
        rows = [row for row in snapshot if str(row["电站编号"]) == plant]
        if not rows:
            raise BaselineError([f"基准数据中没有电站 {plant} 的记录"])
        return self._plant_report(plant, rows, self.derive_period(rows))

    @staticmethod
    def _plant_report(plant: str, rows: list[dict[str, Any]], period: str) -> dict[str, Any]:
        theoretical = sum(float(row["峰值日照时数"]) * float(row["装机容量kWp"]) for row in rows)
        actual = sum(float(row["实际发电量kWh"]) for row in rows)
        losses = {name: sum(float(row[name]) for row in rows) for name in LOSS_FIELDS}
        total_loss = sum(losses.values())
        efficiency = actual / theoretical if theoretical else 0.0
        parts = [
            f"{name[:-3]} {value:.1f}kWh（{value / total_loss:.1%}）" if total_loss else f"{name[:-3]} 0.0kWh"
            for name, value in losses.items()
        ]
        return {
            "电站编号": plant,
            "分析周期": period,
            "理论发电量": f"{theoretical:.1f} kWh",
            "实际发电量": f"{actual:.1f} kWh",
            "系统效率": f"{efficiency:.2%}",
            "损失分析": "；".join(parts),
        }

    # 阶段五：先隔离再替换 —— 旧结果整批进归档区，新结果整批上线
    def _publish(self, reports: list[dict[str, Any]], batch: str) -> int:
        current = self._store.rows(REPORT_MODULE)
        archive = self._store.rows(ARCHIVE_MODULE)
        stale = [row for row in current if row.get("数据来源") == GENERATED_BY]
        kept = [row for row in current if row.get("数据来源") != GENERATED_BY]
        for row in stale:
            archived = dict(row)
            archived["归档id"] = len(archive) + 1
            archived["隔离批次"] = batch
            archive.append(archived)
        next_id = max([int(row.get("id", 0)) for row in kept + archive] + [0]) + 1
        fresh = []
        for seq, report in enumerate(reports):
            fresh.append({
                "id": next_id + seq,
                "status": "已生成",
                "pending": True,
                "abnormal": False,
                "报告编号": f"ENER-{batch}-{seq + 1:02d}",
                **report,
                "报告状态": "已生成",
                "数据来源": GENERATED_BY,
                "批次号": batch,
            })
        current[:] = kept + fresh
        return len(stale)

    def _next_batch(self) -> str:
        seen = []
        for module in (REPORT_MODULE, ARCHIVE_MODULE):
            seen.extend(str(row.get("批次号", "")) for row in self._store.rows(module))
        serials = [
            int(tag.split("-", 1)[1])
            for tag in seen
            if tag.startswith("RUN-") and tag.split("-", 1)[1].isdigit()
        ]
        return f"RUN-{max(serials, default=0) + 1:04d}"


pipeline = EnergyReportPipeline()
