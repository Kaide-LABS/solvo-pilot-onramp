"""audit_trail — onramp_audit_log + onramp_access_log.

Implements PHASE_4_SPEC.md §5.

Revision ID: 0003_audit_trail
Revises: 0002_reference_data
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_audit_trail"
down_revision: str | None = "0002_reference_data"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only audit + access log tables."""
    op.create_table(
        "onramp_audit_log",
        sa.Column("audit_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("actor_principal", sa.Text, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("request_id", sa.Text, nullable=True),
    )
    op.create_index("ix_onramp_audit_log_job", "onramp_audit_log", ["job_id", "occurred_at"])

    op.create_table(
        "onramp_access_log",
        sa.Column("access_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal", sa.Text, nullable=False),
        sa.Column("route", sa.Text, nullable=False),
        sa.Column(
            "accessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("response_status", sa.Integer, nullable=False),
    )
    op.create_index("ix_onramp_access_log_job", "onramp_access_log", ["job_id", "accessed_at"])


def downgrade() -> None:
    """Drop audit + access log tables."""
    op.drop_index("ix_onramp_access_log_job", table_name="onramp_access_log")
    op.drop_table("onramp_access_log")
    op.drop_index("ix_onramp_audit_log_job", table_name="onramp_audit_log")
    op.drop_table("onramp_audit_log")
