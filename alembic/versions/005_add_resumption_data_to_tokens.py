"""Add resumption_data_json to resume_tokens

Revision ID: 005
Revises: 004
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resume_tokens",
        sa.Column("resumption_data_json", postgresql.JSONB, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("resume_tokens", "resumption_data_json")
