"""Add model_registry table.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_model_id", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("capabilities", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "input_price_per_mtok", sa.Numeric(precision=18, scale=8), nullable=False
        ),
        sa.Column(
            "output_price_per_mtok", sa.Numeric(precision=18, scale=8), nullable=False
        ),
        sa.Column(
            "cache_read_price_per_mtok",
            sa.Numeric(precision=18, scale=8),
            nullable=False,
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_id", name="pk_model_registry"),
        sa.UniqueConstraint(
            "provider",
            "provider_model_id",
            name="uq_model_registry_provider_model",
        ),
    )

    op.execute(
        "GRANT SELECT ON model_registry TO app"
    )


def downgrade() -> None:
    op.execute("REVOKE SELECT ON model_registry FROM app")
    op.drop_table("model_registry")
