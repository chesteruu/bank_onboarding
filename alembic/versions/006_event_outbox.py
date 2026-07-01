"""Add event outbox table."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("routing_key", sa.String(256), nullable=False),
        sa.Column("payload_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0"),
    )
    op.create_index("ix_event_outbox_published_at", "event_outbox", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_event_outbox_published_at", table_name="event_outbox")
    op.drop_table("event_outbox")
