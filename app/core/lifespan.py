import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.init_db import create_tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        create_tables()
        logger.info("PostgreSQL 表结构已就绪")
    except Exception as e:
        logger.warning("数据库暂不可用，跳过建表（核心 RAG 功能不受影响）: %s", e)
    yield
