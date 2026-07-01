"""Add flow_segments table."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: str | None = "006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flow_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onboarding_applications.id"),
            index=True,
        ),
        sa.Column("segment_key", sa.String(64), nullable=False),
        sa.Column("orchestrator_id", sa.String(64), nullable=False),
        sa.Column("component_flow_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("internal_step_key", sa.String(64), nullable=True),
        sa.Column("internal_total_steps", sa.Integer(), server_default="1"),
        sa.Column("percent", sa.Integer(), server_default="0"),
        sa.Column("sequence", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_flow_segments_app_segment",
        "flow_segments",
        ["application_id", "segment_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_flow_segments_app_segment", table_name="flow_segments")
    op.drop_table("flow_segments")
