from fastapi import FastAPI

from app.api.routes import api_router
from app.api.routes_auth import router as auth_router
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG PDF 智能问答系统",
        description="基于FastAPI的PDF知识库问答服务",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.include_router(auth_router)
    register_exception_handlers(app)
    return app


app = create_app()
