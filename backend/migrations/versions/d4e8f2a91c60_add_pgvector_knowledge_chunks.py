"""Add application-scoped pgvector knowledge chunks for persistent RAG.

Revision ID: d4e8f2a91c60
Revises: bc71d4a9e205
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "d4e8f2a91c60"
down_revision = "bc71d4a9e205"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.String(length=36), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="runbook"),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_chunks_application_id", "knowledge_chunks", ["application_id"])
    op.create_index("ix_knowledge_chunks_content_hash", "knowledge_chunks", ["content_hash"], unique=True)
    op.execute("CREATE INDEX ix_knowledge_chunks_embedding_cosine ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")


def downgrade():
    op.drop_index("ix_knowledge_chunks_embedding_cosine", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_content_hash", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_application_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
