"""Add device_id to onboarding_applications

Revision ID: 003
Revises: 002
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "onboarding_applications",
        sa.Column("device_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_onboarding_applications_device_id",
        "onboarding_applications",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_onboarding_applications_device_id", table_name="onboarding_applications")
    op.drop_column("onboarding_applications", "device_id")
