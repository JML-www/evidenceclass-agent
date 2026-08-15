"""add citable pgvector knowledge metadata

Revision ID: 9c4f6b8a21d0
Revises: 7182e15ca38a
Create Date: 2026-08-15 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision: str = "9c4f6b8a21d0"
down_revision: str | None = "7182e15ca38a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    if is_postgresql:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    with op.batch_alter_table("knowledge_documents") as batch:
        batch.add_column(
            sa.Column("source_id", sa.String(length=128), nullable=False, server_default="legacy")
        )
        batch.add_column(
            sa.Column("title", sa.String(length=255), nullable=False, server_default="legacy")
        )
        batch.add_column(
            sa.Column(
                "author_or_organization",
                sa.String(length=255),
                nullable=False,
                server_default="legacy",
            )
        )
        batch.add_column(sa.Column("published_on", sa.Date(), nullable=True))
        batch.add_column(
            sa.Column(
                "authorization_status",
                sa.String(length=32),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch.add_column(
            sa.Column("sha256", sa.String(length=64), nullable=False, server_default="0" * 64)
        )
        batch.add_column(
            sa.Column(
                "visibility_scope",
                sa.String(length=32),
                nullable=False,
                server_default="WORKSPACE",
            )
        )
        batch.add_column(sa.Column("parser_version", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("parse_error", sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE knowledge_documents SET source_id = source WHERE source_id = 'legacy'"))
    op.execute(sa.text("UPDATE knowledge_documents SET title = source WHERE title = 'legacy'"))
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_constraint("uq_knowledge_source_version", type_="unique")
        batch.create_unique_constraint(
            "uq_knowledge_source_version", ["workspace_id", "source_id", "version"]
        )
        batch.create_index(
            "ix_knowledge_documents_scope",
            ["workspace_id", "status", "source_id", "version"],
            unique=False,
        )
    with op.batch_alter_table("knowledge_documents") as batch:
        for column in (
            "source_id",
            "title",
            "author_or_organization",
            "authorization_status",
            "sha256",
            "visibility_scope",
        ):
            batch.alter_column(column, server_default=None)

    with op.batch_alter_table("knowledge_chunks") as batch:
        batch.add_column(
            sa.Column("chunk_id", sa.String(length=128), nullable=False, server_default="legacy")
        )
        batch.add_column(sa.Column("page", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("heading", sa.String(length=1024), nullable=False, server_default="legacy")
        )
        batch.add_column(sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column(
                "content_sha256", sa.String(length=64), nullable=False, server_default="0" * 64
            )
        )
        batch.add_column(
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="1")
        )
    op.execute(sa.text("UPDATE knowledge_chunks SET chunk_id = CAST(id AS VARCHAR)"))
    if is_postgresql:
        op.execute(
            sa.text(
                "UPDATE knowledge_chunks SET embedding = NULL "
                "WHERE embedding IS NOT NULL AND jsonb_array_length(embedding::jsonb) <> 384"
            )
        )
        op.alter_column(
            "knowledge_chunks",
            "embedding",
            existing_type=sa.JSON(),
            type_=Vector(384),
            postgresql_using="embedding::text::vector(384)",
        )
    with op.batch_alter_table("knowledge_chunks") as batch:
        batch.create_unique_constraint("uq_knowledge_chunk_id", ["chunk_id"])
        for column in ("chunk_id", "heading", "ordinal", "content_sha256", "token_count"):
            batch.alter_column(column, server_default=None)
    if is_postgresql:
        op.create_index(
            "ix_knowledge_chunks_embedding_hnsw",
            "knowledge_chunks",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    if is_postgresql:
        op.drop_index("ix_knowledge_chunks_embedding_hnsw", table_name="knowledge_chunks")
        op.alter_column(
            "knowledge_chunks",
            "embedding",
            existing_type=Vector(384),
            type_=sa.JSON(),
            postgresql_using="embedding::text::jsonb",
        )
    with op.batch_alter_table("knowledge_chunks") as batch:
        batch.drop_constraint("uq_knowledge_chunk_id", type_="unique")
        batch.drop_column("token_count")
        batch.drop_column("content_sha256")
        batch.drop_column("ordinal")
        batch.drop_column("heading")
        batch.drop_column("page")
        batch.drop_column("chunk_id")
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_index("ix_knowledge_documents_scope")
        batch.drop_constraint("uq_knowledge_source_version", type_="unique")
        batch.create_unique_constraint(
            "uq_knowledge_source_version", ["workspace_id", "source", "version"]
        )
        batch.drop_column("parse_error")
        batch.drop_column("parser_version")
        batch.drop_column("visibility_scope")
        batch.drop_column("sha256")
        batch.drop_column("authorization_status")
        batch.drop_column("published_on")
        batch.drop_column("author_or_organization")
        batch.drop_column("title")
        batch.drop_column("source_id")
