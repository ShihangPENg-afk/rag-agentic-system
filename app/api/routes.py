from fastapi import APIRouter

from app.api import (
    health,
    knowledge_base,
    routes_feedback,
    routes_agent,
    routes_chat,
    routes_documents,
    upload,
)

api_router = APIRouter()
api_router.include_router(upload.router)
api_router.include_router(routes_chat.router)
api_router.include_router(routes_agent.router)
api_router.include_router(routes_feedback.router)
api_router.include_router(routes_documents.router)
api_router.include_router(knowledge_base.router)
api_router.include_router(health.router)
