"""intake_review — onramp_intake_reviews.

Implements PHASE_5_SPEC.md §5.

Revision ID: 0004_intake_review
Revises: 0003_audit_trail
Create Date: 2026-05-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_intake_review"
down_revision: str | None = "0003_audit_trail"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create operator-review acknowledgement table."""
    op.create_table(
        "onramp_intake_reviews",
        sa.Column("review_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lane_id", sa.Text, nullable=False),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("operator_email", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("job_id", "lane_id", name="uq_intake_review_one_per_lane"),
    )
    op.create_index("ix_intake_review_job", "onramp_intake_reviews", ["job_id"])


def downgrade() -> None:
    """Drop intake review table."""
    op.drop_index("ix_intake_review_job", table_name="onramp_intake_reviews")
    op.drop_table("onramp_intake_reviews")
