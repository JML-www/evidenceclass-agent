"""Retire the stage-3 persistence probe table when it exists.

The probe creates this table dynamically instead of declaring it in the
application metadata.  ``IF EXISTS``/``IF NOT EXISTS`` keeps the migration
safe for both databases that ran the probe and fresh databases.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "9aa292a27041"
down_revision: Union[str, None] = "e8814e4a9c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stage3_persistence_probe")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stage3_persistence_probe (
            token VARCHAR(128) PRIMARY KEY
        )
        """
    )
