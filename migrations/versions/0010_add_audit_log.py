"""Add audit_log table (append-only, hash-chained).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

# SHA-256 of the empty string; used as the previous_row_hash for the very first row.
SENTINEL_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        # SHA-256 of the previous row's canonical fields; first row stores SENTINEL_HASH.
        sa.Column("previous_row_hash", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_recorded_at", "audit_log", ["recorded_at"])

    # D4: governance role gets INSERT + SELECT only; no UPDATE or DELETE (append-only).
    # app role receives no access.
    op.execute("GRANT INSERT, SELECT ON audit_log TO governance")


def downgrade() -> None:
    op.execute("REVOKE INSERT, SELECT ON audit_log FROM governance")
    op.drop_index("ix_audit_log_recorded_at", table_name="audit_log")
    op.drop_table("audit_log")
