"""Add per-user application ownership and support multiple dashboard accounts.

Revision ID: bc71d4a9e205
Revises: 9a1c3f5d7e20
Create Date: 2026-10-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "bc71d4a9e205"
down_revision: Union[str, Sequence[str], None] = "9a1c3f5d7e20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_applications_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_applications_owner_user_id_users", "users",
            ["owner_user_id"], ["id"], ondelete="SET NULL",
        )
    # Existing records belong to the first existing dashboard account, if present.
    op.execute(sa.text(
        "UPDATE applications SET owner_user_id = (SELECT MIN(id) FROM users) "
        "WHERE owner_user_id IS NULL AND EXISTS (SELECT 1 FROM users)"
    ))


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("fk_applications_owner_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_applications_owner_user_id")
        batch_op.drop_column("owner_user_id")
