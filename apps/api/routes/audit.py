"""Internal audit-trail route. Implements PHASE_4_SPEC.md §4.1 + §6.7.

Mounted under /internal/v1/audit, excluded from /docs. Bearer-token gated.
Every successful read writes an onramp_access_log outbox event in the same
transaction as the SELECT — transactional outbox invariant from §3.4.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.base import OnrampAuditLog, OnrampJob
from packages.core.db.session import get_async_session
from packages.core.models.audit import AuditLogEntry
from packages.core.settings import Settings, get_settings
from packages.ingest.outbox import enqueue_outbox_event

router = APIRouter()


async def require_internal_service_account(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate the Bearer token. Return the principal string on success."""
    expected = settings.internal_admin_token
    if not expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    presented = authorization.removeprefix("Bearer ").strip()
    if presented != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return settings.internal_admin_principal


@router.get(
    "/{job_id}",
    response_model=list[AuditLogEntry],
    responses={403: {"description": "forbidden"}, 404: {"description": "not_found"}},
    include_in_schema=False,
)
async def audit_log(
    job_id: str,
    principal: str = Depends(require_internal_service_account),
    session: AsyncSession = Depends(get_async_session),
) -> list[AuditLogEntry]:
    """Return the append-only audit trail for job_id, oldest→newest.

    Side effect: writes one onramp_access_log outbox event in the same
    transaction as the SELECT — read attempts ARE auditable.
    """
    async with session.begin():
        job = (
            await session.execute(select(OnrampJob.job_id).where(OnrampJob.job_id == job_id))
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
        rows = (
            (
                await session.execute(
                    select(OnrampAuditLog)
                    .where(OnrampAuditLog.job_id == job_id)
                    .order_by(OnrampAuditLog.occurred_at.asc())
                )
            )
            .scalars()
            .all()
        )

        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="access_log",
            payload={
                "principal": principal,
                "route": "/internal/v1/audit/{id}",
                "accessed_at": datetime.now(UTC).isoformat(),
                "response_status": 200,
                "row_count": len(rows),
            },
        )

    return [
        AuditLogEntry(
            audit_id=row.audit_id,
            job_id=row.job_id,
            actor=row.actor,  # type: ignore[arg-type]
            action=row.action,  # type: ignore[arg-type]
            payload=row.payload,
            actor_principal=row.actor_principal,
            occurred_at=row.occurred_at,
            request_id=row.request_id,
        )
        for row in rows
    ]
