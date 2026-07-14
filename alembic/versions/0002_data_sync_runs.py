"""add data sync run tracking"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_days", sa.Integer(), nullable=False),
        sa.Column("stock_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_symbols", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(512)),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_data_sync_runs_status", "data_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_table("data_sync_runs")
