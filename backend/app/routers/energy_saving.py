"""能效分析接口：维护能效报告，覆盖生成报告、审阅确认、归档报告等动作。"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.energy_pipeline import BaselineError, pipeline
from app.services.energy_saving import EnergySavingService

router = APIRouter(prefix="/api/energy_saving", tags=["能效分析"])

service = EnergySavingService()

LIST_FIELDS = ["报告编号", "电站编号", "分析周期", "理论发电量", "实际发电量", "系统效率", "损失分析", "报告状态"]
STATUSES = ["待生成", "已生成", "已审阅", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按报告编号检索"),
    status: str | None = Query(default=None, description="待生成、已生成、已审阅、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按报告编号与状态过滤能效分析列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出能效分析清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "energy_saving", "total": total, "items": items}


@router.post("/pipeline/run", response_model=ActionResult)
def run_pipeline() -> ActionResult:
    """重跑能效流水线：旧结果先整批隔离归档，再从同一份基准数据重算并替换发布。"""
    try:
        summary = pipeline.run()
    except BaselineError as exc:
        return ActionResult(ok=False, message=f"能效流水线中止：{exc}")
    return ActionResult(
        ok=True,
        message=(
            f"能效流水线 {summary.batch} 完成：隔离旧结果 {summary.isolated} 条，"
            f"发布新报告 {summary.generated} 条（分析周期 {summary.period}）"
        ),
        entry=asdict(summary),
    )


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条能效报告明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"能效报告 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条能效报告，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="能效报告已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条能效报告执行生成报告、审阅确认、归档报告；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
