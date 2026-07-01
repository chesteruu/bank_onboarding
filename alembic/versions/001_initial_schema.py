"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "onboarding_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), unique=True, index=True),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("account_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft"),
        sa.Column("current_step_key", sa.String(64), nullable=True),
        sa.Column("final_decision", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "step_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("onboarding_applications.id"), index=True),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("answers_json", postgresql.JSONB, server_default="{}"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
    )
    op.create_table(
        "integration_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("onboarding_applications.id"), index=True),
        sa.Column("check_type", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("request_payload_hash", sa.String(64), nullable=False),
        sa.Column("response_json", postgresql.JSONB, server_default="{}"),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("onboarding_applications.id"), index=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), server_default="system"),
        sa.Column("metadata_json", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "resume_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("onboarding_applications.id"), index=True),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("resume_tokens")
    op.drop_table("audit_events")
    op.drop_table("integration_results")
    op.drop_table("step_submissions")
    op.drop_table("onboarding_applications")
