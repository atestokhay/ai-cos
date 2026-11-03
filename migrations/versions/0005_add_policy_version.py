"""Add policy_version table.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "policy_version",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("git_commit", sa.Text(), nullable=False),
        sa.Column(
            "activation_time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_version"),
    )

    # D4: governance role gets INSERT + SELECT (records active policy from Git).
    # app role receives no access.
    op.execute("GRANT INSERT, SELECT ON policy_version TO governance")


def downgrade() -> None:
    op.execute("REVOKE INSERT, SELECT ON policy_version FROM governance")
    op.drop_table("policy_version")
