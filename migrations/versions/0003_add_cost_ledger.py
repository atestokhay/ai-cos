"""Add cost_ledger table (append-only).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "cost_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("step_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_miss_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "cost_usd", sa.Numeric(precision=18, scale=8), nullable=True
        ),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("price_table_version", sa.Text(), nullable=False),
        sa.Column(
            "peak", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cost_ledger"),
    )
    op.create_index("ix_cost_ledger_model_id", "cost_ledger", ["model_id"])
    op.create_index("ix_cost_ledger_recorded_at", "cost_ledger", ["recorded_at"])

    # D4: app role gets INSERT + SELECT only; no UPDATE or DELETE.
    op.execute("GRANT INSERT, SELECT ON cost_ledger TO app")


def downgrade() -> None:
    op.execute("REVOKE INSERT, SELECT ON cost_ledger FROM app")
    op.drop_index("ix_cost_ledger_recorded_at", table_name="cost_ledger")
    op.drop_index("ix_cost_ledger_model_id", table_name="cost_ledger")
    op.drop_table("cost_ledger")
