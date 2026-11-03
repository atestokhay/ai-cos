"""Add budget table.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None

_SCOPE_CHECK = (
    "scope IN ('run','task','project','department','day','month')"
)


def upgrade() -> None:
    op.create_table(
        "budget",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("cap", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("set_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_budget"),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_budget_scope"),
    )
    op.create_index("ix_budget_scope_scope_id", "budget", ["scope", "scope_id"])

    # D4: governance role gets SELECT only; caps are set outside the app role.
    # app role receives no access.
    op.execute("GRANT SELECT ON budget TO governance")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON budget FROM governance")
    op.drop_index("ix_budget_scope_scope_id", table_name="budget")
    op.drop_table("budget")
