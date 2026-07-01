"""Add identifier_hash to onboarding_applications

Revision ID: 004
Revises: 003
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "onboarding_applications",
        sa.Column("identifier_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_onboarding_applications_identifier_hash",
        "onboarding_applications",
        ["identifier_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_onboarding_applications_identifier_hash", table_name="onboarding_applications"
    )
    op.drop_column("onboarding_applications", "identifier_hash")
