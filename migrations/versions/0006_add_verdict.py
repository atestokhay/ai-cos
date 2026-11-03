"""Add verdict table.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "verdict",
        sa.Column("id", sa.UUID(), nullable=False),
        # step_id is nullable; FK deferred until the step table exists (Phase 4+).
        sa.Column("step_id", sa.UUID(), nullable=True),
        sa.Column("action_hash", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("redacted_arguments", sa.Text(), nullable=False),
        sa.Column("permission_level", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verdict"),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["policy_version.id"],
            name="fk_verdict_policy_version",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_verdict_tool", "verdict", ["tool"])
    op.create_index("ix_verdict_decision", "verdict", ["decision"])

    # D4: governance role gets INSERT + SELECT. app role receives no access.
    op.execute("GRANT INSERT, SELECT ON verdict TO governance")


def downgrade() -> None:
    op.execute("REVOKE INSERT, SELECT ON verdict FROM governance")
    op.drop_index("ix_verdict_decision", table_name="verdict")
    op.drop_index("ix_verdict_tool", table_name="verdict")
    op.drop_table("verdict")
