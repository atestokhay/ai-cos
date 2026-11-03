"""Add approval table (1:0..1 with verdict).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None

# approval.status values match ApprovalStatus enum:
# pending | approved | rejected | expired | consumed
_STATUS_CHECK = "status IN ('pending','approved','rejected','expired','consumed')"


def upgrade() -> None:
    op.create_table(
        "approval",
        sa.Column("id", sa.UUID(), nullable=False),
        # Unique FK to verdict: 1:0..1 cardinality.
        sa.Column("verdict_id", sa.UUID(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("risk_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "expiry",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("consumed_time", sa.DateTime(timezone=True), nullable=True),
        # Passkey WebAuthn integration deferred; column present for schema stability.
        sa.Column("passkey_assertion_reference", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval"),
        sa.ForeignKeyConstraint(
            ["verdict_id"],
            ["verdict.id"],
            name="fk_approval_verdict",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("verdict_id", name="uq_approval_verdict_id"),
        sa.CheckConstraint(_STATUS_CHECK, name="ck_approval_status"),
    )
    op.create_index("ix_approval_status", "approval", ["status"])
    op.create_index("ix_approval_expiry", "approval", ["expiry"])

    # D4: governance role gets INSERT + SELECT + UPDATE (for status transitions).
    # app role receives no access.
    op.execute("GRANT INSERT, SELECT, UPDATE ON approval TO governance")


def downgrade() -> None:
    op.execute("REVOKE INSERT, SELECT, UPDATE ON approval FROM governance")
    op.drop_index("ix_approval_expiry", table_name="approval")
    op.drop_index("ix_approval_status", table_name="approval")
    op.drop_table("approval")
