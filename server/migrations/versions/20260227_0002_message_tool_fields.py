from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260227_0002"
down_revision = "20260226_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message", sa.Column("tool_name", sa.String(), nullable=True))
    op.add_column("message", sa.Column("tool_call_id", sa.String(), nullable=True))
    op.add_column("message", sa.Column("meta_json", sa.Text(), nullable=True))
    op.create_index("ix_message_tool_name", "message", ["tool_name"])
    op.create_index("ix_message_tool_call_id", "message", ["tool_call_id"])


def downgrade() -> None:
    op.drop_index("ix_message_tool_call_id", table_name="message")
    op.drop_index("ix_message_tool_name", table_name="message")
    op.drop_column("message", "meta_json")
    op.drop_column("message", "tool_call_id")
    op.drop_column("message", "tool_name")
