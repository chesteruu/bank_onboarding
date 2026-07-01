"""Add trace tables

Revision ID: 002
Revises: 001
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flow_trace",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onboarding_applications.id"),
            index=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), server_default="system"),
        sa.Column("metadata_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "integration_trace",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onboarding_applications.id"),
            index=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), server_default="system"),
        sa.Column("metadata_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "decision_trace",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onboarding_applications.id"),
            index=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), server_default="system"),
        sa.Column("metadata_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("decision_trace")
    op.drop_table("integration_trace")
    op.drop_table("flow_trace")
