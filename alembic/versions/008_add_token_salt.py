"""Add token_salt to resume_tokens

Revision ID: 008
Revises: 007
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_tokens",
        sa.Column("token_salt", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resume_tokens", "token_salt")
