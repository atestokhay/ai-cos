"""Seed DeepSeek model entries into model_registry.

Pricing as of 2024-01 (deepseek-chat V3, deepseek-reasoner):
  deepseek-chat:     input $0.14/M, output $0.28/M, cache_read $0.014/M
  deepseek-reasoner: input $0.55/M, output $2.19/M, cache_read $0.14/M

Revision ID: 0004
Revises: 0003
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None

_NOW = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc).isoformat()

_ROWS = [
    {
        "model_id": "deepseek-chat-v3",
        "provider": "deepseek",
        "provider_model_id": "deepseek-chat",
        "tier": "fast",
        "capabilities": ["text", "tool_calling", "structured_output", "streaming"],
        "context_window": 65536,
        "max_output_tokens": 8192,
        "input_price_per_mtok": "0.14000000",
        "output_price_per_mtok": "0.28000000",
        "cache_read_price_per_mtok": "0.01400000",
        "enabled": True,
        "updated_at": _NOW,
    },
    {
        "model_id": "deepseek-reasoner-r1",
        "provider": "deepseek",
        "provider_model_id": "deepseek-reasoner",
        "tier": "reason",
        "capabilities": ["text", "streaming"],
        "context_window": 65536,
        "max_output_tokens": 32768,
        "input_price_per_mtok": "0.55000000",
        "output_price_per_mtok": "2.19000000",
        "cache_read_price_per_mtok": "0.14000000",
        "enabled": True,
        "updated_at": _NOW,
    },
]

_INSERT = sa.text(
    """
    INSERT INTO model_registry (
        model_id, provider, provider_model_id, tier, capabilities,
        context_window, max_output_tokens,
        input_price_per_mtok, output_price_per_mtok,
        cache_read_price_per_mtok, enabled, updated_at
    ) VALUES (
        :model_id, :provider, :provider_model_id, :tier,
        :capabilities,
        :context_window, :max_output_tokens,
        :input_price_per_mtok, :output_price_per_mtok,
        :cache_read_price_per_mtok, :enabled, :updated_at
    )
    ON CONFLICT (model_id) DO NOTHING
    """
).bindparams(
    sa.bindparam("capabilities", type_=ARRAY(sa.Text))
)


def upgrade() -> None:
    conn = op.get_bind()
    for row in _ROWS:
        conn.execute(_INSERT, row)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM model_registry WHERE provider = 'deepseek'")
    )
