"""Declarative base + ORM models matching migration 0001_initial.

Implements PHASE_1_SPEC.md §5. ORM models exist so the alembic_head boot
validator can reflect against a stable target; Phase 1 does not perform any
CRUD on these tables.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base for all SQLAlchemy ORM models."""


class OnrampJob(Base):
    """Job lifecycle row. Created at ingress, mutated through pipeline stages."""

    __tablename__ = "onramp_jobs"

    job_id: Mapped[str] = mapped_column(Text, primary_key=True)
    prospect_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    prospect_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_format: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OnrampOutput(Base):
    """Normalized JSON output produced by a completed job."""

    __tablename__ = "onramp_outputs"

    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"), primary_key=True
    )
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    lane_count: Mapped[int] = mapped_column(Integer, nullable=False)
    flagged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False)


class OnrampOutbox(Base):
    """Transactional outbox: external side-effects committed atomically with job state."""

    __tablename__ = "onramp_outbox"

    outbox_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OnrampConformalScore(Base):
    """Per-lane conformal confidence scores (0.0–1.0) plus ensemble votes."""

    __tablename__ = "onramp_conformal_scores"
    __table_args__ = (PrimaryKeyConstraint("job_id", "lane_id"),)

    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"), nullable=False
    )
    lane_id: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    ensemble_votes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class LaneGraphState(Base):
    """LangGraph per-lane transition audit log. See ULTIMATE_PRD §3.6."""

    __tablename__ = "lane_graph_states"
    __table_args__ = (PrimaryKeyConstraint("job_id", "lane_id", "version"),)

    job_id: Mapped[str] = mapped_column(
        Text, ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"), nullable=False
    )
    lane_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
