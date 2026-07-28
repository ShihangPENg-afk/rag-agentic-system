import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.init_db import create_tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        create_tables()
        logger.info("数据库迁移/表结构已就绪")
    except Exception as e:
        logger.exception("数据库初始化失败: %s", e)
        raise
    yield
