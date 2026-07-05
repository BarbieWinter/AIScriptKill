"""
FastAPI 主应用
AI Script Kill Engine API Gateway
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载资源，关闭时清理"""
    # 启动：初始化数据库连接、加载剧本包索引
    yield
    # 关闭：清理连接


app = FastAPI(
    title="AI Script Kill Engine",
    version="0.1.0",
    description="AI 沉浸式悬疑互动剧游戏引擎 API",
    lifespan=lifespan,
)

# CORS：允许前端开发服务器跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "aiscriptkill", "version": "0.1.0"}
