"""add stage 7 runtime checkpoint and review audit fields

Revision ID: d70a6e2f31b4
Revises: 9c4f6b8a21d0
Create Date: 2026-08-18 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d70a6e2f31b4"
down_revision: str | None = "9c4f6b8a21d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("checkpoint_state_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("plan_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("prompt_version", sa.String(length=64), nullable=True))

    with op.batch_alter_table("review_items") as batch:
        batch.add_column(sa.Column("reviewer_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("note", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "original_payload_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.add_column(sa.Column("revised_payload_json", sa.JSON(), nullable=True))
    with op.batch_alter_table("review_items") as batch:
        batch.alter_column("revision", server_default=None)
        batch.alter_column("original_payload_json", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("review_items") as batch:
        batch.drop_column("revised_payload_json")
        batch.drop_column("original_payload_json")
        batch.drop_column("revision")
        batch.drop_column("note")
        batch.drop_column("decided_at")
        batch.drop_column("reviewer_id")

    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("prompt_version")
        batch.drop_column("plan_json")
        batch.drop_column("checkpoint_state_json")
