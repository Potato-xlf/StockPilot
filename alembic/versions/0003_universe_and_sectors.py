"""add quote universe and sector rotation tables"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stocks",
        sa.Column(
            "quote_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute("UPDATE stocks SET quote_enabled = true")
    op.create_index("ix_stocks_quote_enabled", "stocks", ["quote_enabled"])

    op.create_table(
        "sectors",
        sa.Column("sector_type", sa.String(16), primary_key=True),
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="akshare"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sectors_name", "sectors", ["name"])

    op.create_table(
        "sector_members",
        sa.Column("sector_type", sa.String(16), primary_key=True),
        sa.Column("sector_code", sa.String(16), primary_key=True),
        sa.Column("symbol", sa.String(6), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="akshare"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["sector_type", "sector_code"],
            ["sectors.sector_type", "sectors.code"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["symbol"], ["stocks.symbol"], ondelete="CASCADE"),
    )
    op.create_index("ix_sector_members_symbol", "sector_members", ["symbol"])

    op.create_table(
        "sector_snapshots",
        sa.Column("sector_type", sa.String(16), primary_key=True),
        sa.Column("sector_code", sa.String(16), primary_key=True),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("latest_price", sa.Numeric(18, 4)),
        sa.Column("pct_change", sa.Numeric(12, 4)),
        sa.Column("turnover_rate", sa.Numeric(12, 4)),
        sa.Column("total_market_cap", sa.Numeric(24, 2)),
        sa.Column("advancers", sa.Integer()),
        sa.Column("decliners", sa.Integer()),
        sa.Column("leading_stock", sa.String(64)),
        sa.Column("leading_stock_pct", sa.Numeric(12, 4)),
        sa.Column("source", sa.String(32), nullable=False, server_default="akshare"),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["sector_type", "sector_code"],
            ["sectors.sector_type", "sectors.code"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_sector_snapshots_trade_date", "sector_snapshots", ["trade_date"]
    )

    op.create_table(
        "sector_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sector_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sector_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_sectors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(512)),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_sector_sync_runs_status", "sector_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_table("sector_sync_runs")
    op.drop_table("sector_snapshots")
    op.drop_table("sector_members")
    op.drop_table("sectors")
    op.drop_index("ix_stocks_quote_enabled", table_name="stocks")
    op.drop_column("stocks", "quote_enabled")
