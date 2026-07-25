"""add document ownership sessions and messages

Revision ID: 20260717_0002
Revises: 20260717_0001
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260717_0002"
down_revision: Union[str, Sequence[str], None] = "20260717_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _column_names(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_key_names(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk["name"]}


def upgrade() -> None:
    if not _has_table("documents"):
        op.create_table(
            "documents",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column(
                "content_type",
                sa.String(length=100),
                nullable=False,
                server_default="application/pdf",
            ),
            sa.Column("chunks_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        columns = _column_names("documents")
        if "user_id" not in columns:
            op.add_column(
                "documents",
                sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
        if "content_type" not in columns:
            op.add_column(
                "documents",
                sa.Column(
                    "content_type",
                    sa.String(length=100),
                    nullable=False,
                    server_default="application/pdf",
                ),
            )

        foreign_keys = _foreign_key_names("documents")
        if "fk_documents_user_id_users" not in foreign_keys:
            op.create_foreign_key(
                "fk_documents_user_id_users",
                "documents",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )

    indexes = _index_names("documents")
    if "ix_documents_user_id" not in indexes:
        op.create_index("ix_documents_user_id", "documents", ["user_id"])

    if not _has_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    if not _has_table("messages"):
        op.create_table(
            "messages",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_messages_session_id", "messages", ["session_id"])


def downgrade() -> None:
    if _has_table("messages"):
        indexes = _index_names("messages")
        if "ix_messages_session_id" in indexes:
            op.drop_index("ix_messages_session_id", table_name="messages")
        op.drop_table("messages")

    if _has_table("sessions"):
        indexes = _index_names("sessions")
        if "ix_sessions_user_id" in indexes:
            op.drop_index("ix_sessions_user_id", table_name="sessions")
        op.drop_table("sessions")

    if _has_table("documents"):
        indexes = _index_names("documents")
        if "ix_documents_user_id" in indexes:
            op.drop_index("ix_documents_user_id", table_name="documents")

        foreign_keys = _foreign_key_names("documents")
        if "fk_documents_user_id_users" in foreign_keys:
            op.drop_constraint("fk_documents_user_id_users", "documents", type_="foreignkey")

        columns = _column_names("documents")
        if "content_type" in columns:
            op.drop_column("documents", "content_type")
        if "user_id" in columns:
            op.drop_column("documents", "user_id")
