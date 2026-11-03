"""Grant INSERT on policy_version to governance role.

Migration 0005 originally granted only SELECT. The governance layer also needs
INSERT to record the active policy version when Git-sourced policy is activated.
This migration corrects that grant for existing volumes; fresh volumes get the
correct grant directly from 0005.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("GRANT INSERT ON policy_version TO governance")


def downgrade() -> None:
    op.execute("REVOKE INSERT ON policy_version FROM governance")
