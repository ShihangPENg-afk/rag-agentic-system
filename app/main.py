from fastapi import FastAPI

from app.api.routes import api_router
from app.api.routes_auth import router as auth_router
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="Industrial Maintenance Agent Platform",
        description="FastAPI service for RAG, LangGraph Agent workflows, pgvector retrieval, and maintenance tool orchestration.",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.include_router(auth_router)
    register_exception_handlers(app)
    return app


app = create_app()
