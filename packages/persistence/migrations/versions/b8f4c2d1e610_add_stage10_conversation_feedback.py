"""add stage-10 conversation answers, summaries, and immutable feedback audit"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8f4c2d1e610"
down_revision: str | None = "9aa292a27041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("summary_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("summary_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("summary_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("summary_source_start", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("summary_source_end", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.alter_column("summary_version", server_default=None)

    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("evidence_available", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("source", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("limitations", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("boundary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.alter_column("evidence_available", server_default=None)
        batch.alter_column("limitations", server_default=None)
        batch.alter_column("boundary_json", server_default=None)

    op.create_table(
        "review_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("original_payload_json", sa.JSON(), nullable=False),
        sa.Column("revised_payload_json", sa.JSON(), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["review_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_audits_job_created", "review_audits", ["job_id", "created_at"])
    op.create_index("ix_review_audits_reviewer_created", "review_audits", ["reviewer_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_review_audits_reviewer_created", table_name="review_audits")
    op.drop_index("ix_review_audits_job_created", table_name="review_audits")
    op.drop_table("review_audits")
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("boundary_json")
        batch.drop_column("limitations")
        batch.drop_column("source")
        batch.drop_column("evidence_available")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("summary_updated_at")
        batch.drop_column("summary_source_end")
        batch.drop_column("summary_source_start")
        batch.drop_column("summary_hash")
        batch.drop_column("summary_version")
        batch.drop_column("summary_json")
