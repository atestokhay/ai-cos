"""Add emergency_state table.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None

_LEVEL_CHECK = (
    "level IN ('agent_quarantine','department_pause','company_wide_stop')"
)


def upgrade() -> None:
    op.create_table(
        "emergency_state",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("who", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("cleared_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_emergency_state"),
        sa.CheckConstraint(_LEVEL_CHECK, name="ck_emergency_state_level"),
    )

    # D4: governance role gets SELECT; read by Gateway admission checks.
    # app role receives no access.
    op.execute("GRANT SELECT ON emergency_state TO governance")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON emergency_state FROM governance")
    op.drop_table("emergency_state")
