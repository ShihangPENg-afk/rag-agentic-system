#!/usr/bin/env python3
"""
Verify PostgreSQL + pgvector persistence without calling an LLM.

What this script checks:
1. Creates a small test document payload.
2. Splits it into chunks and generates embeddings through the configured provider.
3. Persists document/chunks/embeddings into PostgreSQL + pgvector.
4. Simulates a service restart by clearing the in-memory registry and disposing DB pool.
5. Retrieves relevant chunks from pgvector without re-uploading/rebuilding FAISS.

By default, if no real DashScope API key is configured, the script uses
EMBEDDING_PROVIDER=fake so it can run offline.
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
import uuid
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _has_real_dashscope_key() -> bool:
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    return bool(key and key != "your_dashscope_api_key_here")


def configure_environment() -> None:
    load_dotenv(ROOT / ".env")

    provider = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
    if provider == "fake":
        return

    if not _has_real_dashscope_key():
        os.environ["EMBEDDING_PROVIDER"] = "fake"


def log_step(message: str) -> None:
    print(f"\n==> {message}")


def log_ok(message: str) -> None:
    print(f"✅ {message}")


def fail(message: str) -> int:
    print(f"\n❌ {message}", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify pgvector persistence and retrieval without LLM calls.",
    )
    parser.add_argument(
        "--query",
        default="How does the sentinel turbo compressor use pgvector persistence?",
        help="Query used for pgvector retrieval.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of chunks to retrieve.",
    )
    return parser.parse_args()


def main() -> int:
    configure_environment()
    args = parse_args()

    from sqlalchemy import func, select

    from app.db.init_db import create_tables
    from app.db.session import SessionLocal, engine
    from app.models import Chunk, ChunkEmbedding, Document, User
    from app.repositories.vector_repository import persist_document_chunks_embeddings
    from app.retrievers.retriever_v2_pgvector import retrieve_similar_chunks
    from app.services.embedding_service import (
        get_embedding_model_name,
        get_embedding_provider,
        get_embeddings,
    )
    from app.services.index_service import split_text
    from app.services.kb_registry import clear_all_knowledge_bases, count_knowledge_bases

    database_url = os.getenv("DATABASE_URL", "")
    provider = get_embedding_provider()

    print("pgvector persistence verification")
    print(f"Project root: {ROOT}")
    print(f"DATABASE_URL: {database_url}")
    print(f"EMBEDDING_PROVIDER: {provider.name}")
    print(f"EMBEDDING_MODEL_NAME: {get_embedding_model_name()}")

    if engine.dialect.name != "postgresql":
        return fail(
            "当前 DATABASE_URL 不是 PostgreSQL。请先启动 pgvector PostgreSQL，并设置 DATABASE_URL。"
        )

    log_step("确保 PostgreSQL vector extension 和表结构可用")
    create_tables()
    log_ok("数据库结构已就绪")

    document_text = textwrap.dedent(
        """
        Sentinel turbo compressor maintenance note.

        This verification document proves that chunks and embeddings are persisted
        in PostgreSQL with pgvector. After the in-memory FAISS registry is cleared,
        pgvector retrieval should still return this compressor persistence chunk.
        """
    ).strip()

    log_step("切分测试文档并生成 embedding")
    chunks = split_text(document_text)
    if not chunks:
        return fail("测试文档切块结果为空")

    embeddings, dimension = get_embeddings(chunks)
    if len(embeddings) != len(chunks):
        return fail(f"embedding 数量与 chunk 数量不一致: {len(embeddings)} != {len(chunks)}")

    log_ok(f"生成 chunks={len(chunks)}, embeddings={len(embeddings)}, dimension={dimension}")

    log_step("写入 documents / chunks / chunk_embeddings")
    filename = f"pgvector-persistence-check-{uuid.uuid4().hex[:8]}.txt"
    verification_user_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.add(
            User(
                id=verification_user_id,
                email=f"pgvector-verify-{verification_user_id.hex[:12]}@example.com",
                hashed_password="verify-script-only",
            )
        )
        db.flush()
        persisted = persist_document_chunks_embeddings(
            db,
            filename=filename,
            content_type="text/plain",
            chunks=chunks,
            embeddings=embeddings,
            user_id=verification_user_id,
            file_size=len(document_text.encode("utf-8")),
            content_hash=None,
            embedding_dimension=dimension,
        )
        document = persisted["document"]
        collection = persisted["collection"]
        document_id = str(document.id)
        collection_id = str(collection.id)
    finally:
        db.close()

    log_ok(f"document_id={document_id}")
    log_ok(f"collection_id={collection_id}")
    log_ok(f"user_id={verification_user_id}")

    log_step("模拟服务重启：清空内存知识库 registry，并关闭当前数据库连接池")
    cleared_count = clear_all_knowledge_bases()
    engine.dispose()
    log_ok(f"已清空内存知识库数量: {cleared_count}")
    log_ok(f"当前内存知识库数量: {count_knowledge_bases()}")

    log_step("重新打开数据库会话，确认持久化记录仍存在")
    db = SessionLocal()
    try:
        db_document = db.get(Document, uuid.UUID(document_id))
        chunk_count = db.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
        embedding_count = db.scalar(
            select(func.count())
            .select_from(ChunkEmbedding)
            .where(ChunkEmbedding.document_id == document_id)
        )
    finally:
        db.close()

    if db_document is None:
        return fail("重启模拟后未找到 document 记录")
    if chunk_count != len(chunks) or embedding_count != len(embeddings):
        return fail(
            f"持久化数量不匹配: chunks={chunk_count}, embeddings={embedding_count}"
        )
    log_ok(f"数据库记录仍存在: chunks={chunk_count}, embeddings={embedding_count}")

    log_step("不重新上传文档，直接从 pgvector 检索相关 chunk")
    results, error = retrieve_similar_chunks(
        query=args.query,
        user_id=verification_user_id,
        document_id=document_id,
        collection_id=collection_id,
        limit=args.limit,
    )
    if error is not None:
        return fail(f"pgvector 检索失败: {error}")
    if not results:
        return fail("pgvector 未返回任何 chunk")

    first = results[0]
    if first["document_id"] != document_id:
        return fail(f"检索返回了错误 document_id: {first['document_id']}")

    print("\n检索结果:")
    for index, item in enumerate(results, 1):
        preview = " ".join(str(item["content"]).split())[:180]
        print(
            f"{index}. chunk_id={item['chunk_id']} "
            f"document_id={item['document_id']} "
            f"score={item['score']:.4f} "
            f"distance={item['distance']:.4f}"
        )
        print(f"   content={preview}")

    log_ok("验证完成：未重新上传文档，pgvector 仍可检索到持久化 chunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
