"""Add enhanced investigation report fields missing from older databases.

Revision ID: e7f1a2b3c4d5
Revises: d4e8f2a91c60
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "e7f1a2b3c4d5"
down_revision = "d4e8f2a91c60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older installations created investigation_reports with only the original
    # report fields. Add every enhanced model field that is absent, without
    # disturbing columns or data that already exist.
    bind = op.get_bind()
    inspector = inspect(bind)
    if "investigation_reports" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("investigation_reports")}
    additions = [
        ("incident_summary", sa.Text(), False, ""),
        ("downstream_services", sa.JSON(), True, None),
        ("timeline_summary", sa.JSON(), True, None),
        ("alternative_hypotheses", sa.JSON(), True, None),
        ("supporting_evidence", sa.JSON(), True, None),
        ("evidence_mapping", sa.JSON(), True, None),
        ("stack_trace_locations", sa.JSON(), True, None),
        ("confidence_factors", sa.JSON(), True, None),
        ("uncertainty_notes", sa.Text(), True, None),
        ("verification_steps", sa.JSON(), True, None),
        ("investigation_steps", sa.JSON(), True, None),
        ("events_analyzed", sa.Integer(), False, 0),
        ("events_cited", sa.Integer(), False, 0),
        ("model_used", sa.String(length=100), True, None),
    ]

    for name, column_type, nullable, default in additions:
        if name in existing:
            continue
        kwargs = {"nullable": nullable}
        if default is not None:
            kwargs["server_default"] = sa.text(repr(default)) if isinstance(default, str) else sa.text(str(default))
        op.add_column(
            "investigation_reports",
            sa.Column(name, column_type, **kwargs),
        )


def downgrade() -> None:
    # Intentionally non-destructive: these fields may contain investigation
    # data written by a newer application version.
    pass
