"""光伏电站运维管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.services.energy_pipeline import pipeline
from app.store import store


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动即跑一轮能效流水线：基准数据缺失时抛错中止启动，
    # 只有流水线成功，报告服务才开始对外提供
    summary = pipeline.run()
    print(
        f"能效流水线就绪：{summary.batch} 分析周期 {summary.period}，"
        f"发布报告 {summary.generated} 条，隔离旧结果 {summary.isolated} 条"
    )
    yield


app = FastAPI(title="光伏电站运维管理平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
