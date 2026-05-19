"""initial — five Phase 1 tables.

Implements PHASE_1_SPEC.md §5.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create onramp_jobs, onramp_outputs, onramp_outbox, onramp_conformal_scores, lane_graph_states."""
    op.create_table(
        "onramp_jobs",
        sa.Column("job_id", sa.Text, primary_key=True),
        sa.Column("prospect_id", sa.Text, nullable=False),
        sa.Column("prospect_name", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            comment="pending|extracting|normalizing|validating|completed|failed",
        ),
        sa.Column("input_hash", sa.Text, nullable=False, unique=True),
        sa.Column("source_format", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_onramp_jobs_prospect_id", "onramp_jobs", ["prospect_id"])
    op.create_index("ix_onramp_jobs_status", "onramp_jobs", ["status"])

    op.create_table(
        "onramp_outputs",
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("normalized_payload", postgresql.JSONB, nullable=False),
        sa.Column("lane_count", sa.Integer, nullable=False),
        sa.Column("flagged_count", sa.Integer, nullable=False),
        sa.Column("rejected_count", sa.Integer, nullable=False),
    )

    op.create_table(
        "onramp_outbox",
        sa.Column("outbox_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.Text,
            nullable=False,
            comment="slack_post|webhook_callback|audit_log|signed_url_create",
        ),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_onramp_outbox_pending",
        "onramp_outbox",
        ["next_retry_at"],
        postgresql_where=sa.text("delivered_at IS NULL"),
    )

    op.create_table(
        "onramp_conformal_scores",
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lane_id", sa.Text, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("ensemble_votes", postgresql.JSONB, nullable=False),
        sa.PrimaryKeyConstraint("job_id", "lane_id"),
    )

    op.create_table(
        "lane_graph_states",
        sa.Column(
            "job_id",
            sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lane_id", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            comment=(
                "parsed|extracted|candidate_normalized|needs_reference_lookup|"
                "needs_human_review|validated|rejected"
            ),
        ),
        sa.Column("state_json", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("job_id", "lane_id", "version"),
    )
    op.create_index(
        "ix_lane_graph_states_job",
        "lane_graph_states",
        ["job_id", sa.text("updated_at DESC")],
    )


def downgrade() -> None:
    """Drop all Phase 1 tables in reverse dependency order."""
    op.drop_index("ix_lane_graph_states_job", table_name="lane_graph_states")
    op.drop_table("lane_graph_states")
    op.drop_table("onramp_conformal_scores")
    op.drop_index("ix_onramp_outbox_pending", table_name="onramp_outbox")
    op.drop_table("onramp_outbox")
    op.drop_table("onramp_outputs")
    op.drop_index("ix_onramp_jobs_status", table_name="onramp_jobs")
    op.drop_index("ix_onramp_jobs_prospect_id", table_name="onramp_jobs")
    op.drop_table("onramp_jobs")
