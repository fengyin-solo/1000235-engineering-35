"""光伏电站运维管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health

启动顺序有硬约束：先过构建依赖检查（缺失就列清单并中止），再跑首次能效流水线，
两步都成功服务才开始接请求。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.preflight import find_missing_dependencies
from app.routers import ROUTERS
from app.services.energy_pipeline import run_pipeline
from app.store import store


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    missing = find_missing_dependencies()
    if missing:
        raise RuntimeError(f"构建依赖缺失，停止启动：{'、'.join(missing)}")
    run_pipeline(trigger="startup")
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
