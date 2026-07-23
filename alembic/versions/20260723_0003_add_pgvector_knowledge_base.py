"""add pgvector knowledge base persistence

Revision ID: 20260723_0003
Revises: 20260717_0002
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision: str = "20260723_0003"
down_revision: Union[str, Sequence[str], None] = "20260717_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VECTOR_DIMENSION = 1536


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if not _has_table("collections"):
        op.create_table(
            "collections",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_collections_user_id", "collections", ["user_id"])

    if _has_table("documents"):
        columns = _column_names("documents")
        if "collection_id" not in columns:
            op.add_column(
                "documents",
                sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
            op.create_foreign_key(
                "fk_documents_collection_id_collections",
                "documents",
                "collections",
                ["collection_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "file_size" not in columns:
            op.add_column("documents", sa.Column("file_size", sa.BigInteger(), nullable=True))
        if "content_hash" not in columns:
            op.add_column(
                "documents",
                sa.Column("content_hash", sa.String(length=64), nullable=True),
            )
        if "error_message" not in columns:
            op.add_column("documents", sa.Column("error_message", sa.Text(), nullable=True))

        indexes = _index_names("documents")
        if "ix_documents_collection_id" not in indexes:
            op.create_index("ix_documents_collection_id", "documents", ["collection_id"])
        if "ix_documents_content_hash" not in indexes:
            op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
        if "ix_documents_user_collection" not in indexes:
            op.create_index(
                "ix_documents_user_collection",
                "documents",
                ["user_id", "collection_id"],
            )

    if not _has_table("chunks"):
        op.create_table(
            "chunks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=True),
            sa.Column("char_start", sa.Integer(), nullable=True),
            sa.Column("char_end", sa.Integer(), nullable=True),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
        )
        op.create_index("ix_chunks_collection_id", "chunks", ["collection_id"])
        op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])
        op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
        op.create_index("ix_chunks_document_index", "chunks", ["document_id", "chunk_index"])
        op.create_index("ix_chunks_user_id", "chunks", ["user_id"])
        op.create_index("ix_chunks_user_collection", "chunks", ["user_id", "collection_id"])

    if not _has_table("chunk_embeddings"):
        op.create_table(
            "chunk_embeddings",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("embedding_model", sa.String(length=128), nullable=False),
            sa.Column("embedding_dimension", sa.Integer(), nullable=False),
            sa.Column("embedding", Vector(VECTOR_DIMENSION), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "chunk_id",
                "embedding_model",
                name="uq_chunk_embeddings_chunk_model",
            ),
        )
        op.create_index("ix_chunk_embeddings_chunk_id", "chunk_embeddings", ["chunk_id"])
        op.create_index("ix_chunk_embeddings_collection_id", "chunk_embeddings", ["collection_id"])
        op.create_index("ix_chunk_embeddings_document_id", "chunk_embeddings", ["document_id"])
        op.create_index("ix_chunk_embeddings_user_id", "chunk_embeddings", ["user_id"])
        op.create_index(
            "ix_chunk_embeddings_user_collection",
            "chunk_embeddings",
            ["user_id", "collection_id"],
        )
        if bind.dialect.name == "postgresql":
            op.create_index(
                "ix_chunk_embeddings_embedding_l2",
                "chunk_embeddings",
                ["embedding"],
                postgresql_using="hnsw",
                postgresql_ops={"embedding": "vector_l2_ops"},
            )


def downgrade() -> None:
    if _has_table("chunk_embeddings"):
        indexes = _index_names("chunk_embeddings")
        if "ix_chunk_embeddings_embedding_l2" in indexes:
            op.drop_index("ix_chunk_embeddings_embedding_l2", table_name="chunk_embeddings")
        for name in (
            "ix_chunk_embeddings_user_collection",
            "ix_chunk_embeddings_user_id",
            "ix_chunk_embeddings_document_id",
            "ix_chunk_embeddings_collection_id",
            "ix_chunk_embeddings_chunk_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="chunk_embeddings")
        op.drop_table("chunk_embeddings")

    if _has_table("chunks"):
        indexes = _index_names("chunks")
        for name in (
            "ix_chunks_user_collection",
            "ix_chunks_user_id",
            "ix_chunks_document_index",
            "ix_chunks_document_id",
            "ix_chunks_content_hash",
            "ix_chunks_collection_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="chunks")
        op.drop_table("chunks")

    if _has_table("documents"):
        indexes = _index_names("documents")
        for name in (
            "ix_documents_user_collection",
            "ix_documents_content_hash",
            "ix_documents_collection_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="documents")

        columns = _column_names("documents")
        if "error_message" in columns:
            op.drop_column("documents", "error_message")
        if "content_hash" in columns:
            op.drop_column("documents", "content_hash")
        if "file_size" in columns:
            op.drop_column("documents", "file_size")
        if "collection_id" in columns:
            op.drop_constraint(
                "fk_documents_collection_id_collections",
                "documents",
                type_="foreignkey",
            )
            op.drop_column("documents", "collection_id")

    if _has_table("collections"):
        indexes = _index_names("collections")
        if "ix_collections_user_id" in indexes:
            op.drop_index("ix_collections_user_id", table_name="collections")
        op.drop_table("collections")
