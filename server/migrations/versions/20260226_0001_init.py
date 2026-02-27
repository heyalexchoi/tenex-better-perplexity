from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260226_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
    )
    op.create_table(
        "message",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("session.id"), nullable=False, index=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agenteventrecord",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("session.id"), nullable=False, index=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agenteventrecord")
    op.drop_table("message")
    op.drop_table("session")
