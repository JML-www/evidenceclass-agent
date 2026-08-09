"""extend model call audit fields

Revision ID: 7182e15ca38a
Revises: c3199b4a77d9
Create Date: 2026-08-09 21:45:45.975108
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7182e15ca38a'
down_revision: Union[str, None] = 'c3199b4a77d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("model_calls") as batch:
        batch.add_column(sa.Column("model_revision", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column(
                "config_version",
                sa.String(length=64),
                nullable=False,
                server_default="unknown",
            )
        )
        batch.add_column(
            sa.Column("characters", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("audio_seconds", sa.Float(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("cost_known", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("raw_response_ref", sa.String(length=1024), nullable=True))
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="SUCCEEDED",
            )
        )
        batch.add_column(sa.Column("error_code", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1")
        )
        batch.alter_column("cost", existing_type=sa.Float(), nullable=True)
    with op.batch_alter_table("model_calls") as batch:
        for column in (
            "config_version",
            "characters",
            "audio_seconds",
            "cost_known",
            "status",
            "attempt",
        ):
            batch.alter_column(column, server_default=None)


def downgrade() -> None:
    op.execute(sa.text("UPDATE model_calls SET cost = 0 WHERE cost IS NULL"))
    with op.batch_alter_table("model_calls") as batch:
        batch.alter_column("cost", existing_type=sa.Float(), nullable=False)
        batch.drop_column("attempt")
        batch.drop_column("error_code")
        batch.drop_column("status")
        batch.drop_column("raw_response_ref")
        batch.drop_column("cost_known")
        batch.drop_column("audio_seconds")
        batch.drop_column("characters")
        batch.drop_column("config_version")
        batch.drop_column("model_revision")
