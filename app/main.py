from fastapi import FastAPI

from app.api.routes import api_router
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG PDF 智能问答系统",
        description="基于FastAPI的PDF知识库问答服务",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app


app = create_app()
