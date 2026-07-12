"""initial market data tables"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("symbol", sa.String(6), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("exchange", sa.String(8), nullable=False),
        sa.Column("list_status", sa.String(16), nullable=False, server_default="listed"),
        sa.Column("source", sa.String(32), nullable=False, server_default="akshare"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_stocks_exchange", "stocks", ["exchange"])
    op.create_table(
        "trading_calendars",
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("exchange", sa.String(8), primary_key=True),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
    )
    op.create_table(
        "daily_quotes",
        sa.Column(
            "symbol",
            sa.String(6),
            sa.ForeignKey("stocks.symbol", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.Numeric(24, 2), nullable=False),
        sa.Column("amount", sa.Numeric(24, 2)),
        sa.Column("amplitude", sa.Numeric(12, 4)),
        sa.Column("pct_change", sa.Numeric(12, 4)),
        sa.Column("change", sa.Numeric(18, 4)),
        sa.Column("turnover_rate", sa.Numeric(12, 4)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_daily_quotes_trade_date", "daily_quotes", ["trade_date"])


def downgrade() -> None:
    op.drop_table("daily_quotes")
    op.drop_table("trading_calendars")
    op.drop_table("stocks")
