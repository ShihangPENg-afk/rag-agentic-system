from fastapi import APIRouter

from app.api import chat, documents, health, knowledge_base, upload

api_router = APIRouter()
api_router.include_router(upload.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(knowledge_base.router)
api_router.include_router(health.router)
