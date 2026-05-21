# Human Intervention Required — Step 4 Smoke Test (Stage F.3 structurally blocked)

Run started: 2026-05-21 (after Stage F.2 PASSED at commit `dfaf079`)
Stage: F.3 — first Magic Moment probe
Failure mode: **SQLAlchemy async engine + Celery task loop incompatibility**. Job submits to `pending`, classify_format_task is picked up, but the SQLAlchemy connection-pool ping inside the task hits `RuntimeError: got Future attached to a different loop` because the `@lru_cache`-d engine was instantiated against a different `asyncio.run()` loop than the one Celery is currently executing under. The task dies silently before any status transition commits; the job stays at `pending` forever.

---

## What I tried

1. **Preflight green**: all 5 containers healthy; `/v1/health` returns 200 with all 4 boot validators passing (cached state from the earlier `dfaf079` commit).
2. **One Magic Moment probe** against `fixtures/01_clean_excel.xlsx`:
   - `POST /v1/intake/jobs` returned `{job_id, status=pending, submitted_by=ops@kaide.so}` — ingress works.
   - Polled `/v1/intake/jobs/{id}` for 90 s — status stayed `pending`.
   - Worker logs surfaced the root-cause traceback (excerpt):

```
RuntimeError: Task <Task pending name='Task-2159'
  coro=<_drain_once() running at /app/packages/dispatcher/outbox_worker.py:95>
  cb=[_run_until_complete_cb() at /usr/local/lib/python3.13/asyncio/base_events.py:181]>
  got Future <Future pending cb=[BaseProtocol._on_waiter_completed()]>
  attached to a different loop
```

The stack walks through `asyncpg.protocol.protocol.BaseProtocol.query` → `sqlalchemy.dialects.postgresql.asyncpg.ping` → `pool._dialect._do_ping_w_event` → `pool._ConnectionFairy._checkout` → triggered the first time the task tries to acquire a session.

---

## Root cause

`packages/core/db/session.py` defines `get_async_engine()` with `@lru_cache(maxsize=1)`. This works fine for FastAPI (one event loop for the lifespan), but Celery's task workers each call `asyncio.run(...)` which spins up a fresh loop per task. The lru_cache returns the same engine, but its connection pool holds connections bound to whichever loop opened them — usually the first task's loop. Every subsequent task hitting the engine triggers the cross-loop error.

The same bug will fire in `_classify`, `_extract`, `_normalize`, `_validate`, AND the dispatcher's `_drain_once` — any task that touches Postgres. The dispatcher's drain happens to be the first to die because the beat schedule fires it every 5 s, but the ingest pipeline is equally broken.

---

## Why this needs human judgment

Three intersecting gaps make Stage F.3–F.5 unrunnable as written, and the right fix scope is a sprint-level decision, not an inline patch:

### 1. SQLAlchemy/Celery loop incompatibility (real code bug, blocks all F.3+)

The fix is non-trivial:

- **Option A — Per-task engine**: remove `@lru_cache` from `get_async_engine`, instantiate a fresh `AsyncEngine` inside every Celery task's async core, and `await engine.dispose()` at the end. Costs a connection open per task (~30–80 ms per task) and changes the FastAPI lifespan to manage its engine separately.
- **Option B — Switch tasks to sync SQLAlchemy**: keep async in FastAPI, use sync engine + psycopg in Celery tasks. Lowest async-surface-area, fastest fix, but requires duplicating repository helpers in a sync path.
- **Option C — Single-engine-per-process via Celery `worker_process_init` signal**: bind engine to the worker process's persistent event loop (would need to run an asyncio loop on a thread for the lifetime of the worker). Most performant, most code.

Recommendation: **Option A**, scoped as a Phase 6 follow-up patch. ~80 LOC, 3 modules touched (`session.py`, `tasks.py`, `outbox_worker.py`).

### 2. Smoke-test fixtures don't exist

The prompt's Stage F.3 + F.4 references these fixtures:

- `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` — narrative fixture from Master PRD §3.3, 247 lanes, never built.
- `fixtures/broken_impossible_port_codes.xlsx` — never built.
- `fixtures/broken_negative_rates.xlsx` — never built.
- `fixtures/broken_malformed_edifact.edi` — never built.

What ships: `01_clean_excel.xlsx`..`05_mixed_units.xlsx` + `06_edifact_pricat.edi`. The clean fixture is 3 lanes, not 247 — F.3.2 lane-count expectations (~247 ±5%, ~4 flagged, ~2 rejected) can't be measured.

**Recommendation:** generate a 50-lane K+N-style messy fixture + 3 broken fixtures. ~20 min of Python via the existing `data/_generate.py` pattern. Or accept that F.3 measures the 3-lane case and adjust expectations accordingly.

### 3. Slack-post outbox emit code path is missing

Stage F.3.3 requires "Slack thread reply within 60s of job submission." The dispatcher *can* deliver `slack_post` events (`packages/dispatcher/delivery.py:deliver_slack_post` exists and the `slack_post` literal is registered in `OutboxEventType`), but **no caller writes a `slack_post` outbox row from the ingest pipeline**. The `_validate` task in `tasks.py` writes an `audit_log` outbox row with `stage="validated"`, but doesn't enqueue a Slack post.

Phase 5 spec §6.6 said "All Slack outbound calls go through the outbox (write `slack_post` event → dispatcher delivers). **No direct synchronous Slack POST from a request handler**." — the write side was never implemented. The slack handlers in `packages/slack/handlers.py` return ephemeral payloads but never trigger a result post for completed jobs.

**Recommendation:** add a `slack_post` outbox enqueue at the end of `_validate` after the `audit_log` insert. ~15 LOC patch. Block Kit summary builder already exists in `packages/slack/block_kit.py`.

### 4. API-contract mismatch in the prompt's smoke-test scripts (not blocking, easy to adapt)

The prompt's curl commands use `-F file=@..., -F prospect_id=..., -F prospect_name=...` with `X-Admin-Token` header on the public-facing `/v1/intake/jobs` and `/v1/intake/jobs/{id}/result-url` routes. Actual implementation:

- File field is `upload`, not `file`.
- Required form fields: `prospect_id, prospect_name, operator_email, requested_slack_channel, priority` (the prompt only sends two).
- No `X-Admin-Token` header on `/v1/intake/*` (only `/internal/v1/audit/{id}` requires `Authorization: Bearer`).
- Result-URL JSON returns `url`, not `signed_url`.

This is fixable inline (I'd just adapt the script as I did for the probe), but mentioning so the smoke-test script can be reconciled with the build for future runs.

---

## What I'd recommend (recommendation, not auto-applied)

Three changes, in this order, before re-attempting F.3:

1. **Fix Option A above** — per-task engine in Celery tasks. Treat as a "Sprint 1 closure patch" — same shape as the Phase 6 review patches.
2. **Generate the missing fixtures** — K+N 50-lane + 3 broken fixtures via `data/_generate.py` pattern.
3. **Wire the `slack_post` enqueue** in `_validate` after the audit_log row.

Estimated total: ~3 hours of work + ~$5 of Vertex credit to verify. Then a clean F.3–F.5 run becomes feasible.

The compose-stack work and PRD path-1 patches (commits `dfaf079` and `98030d2`) are already committed and don't need re-doing.

---

## Cost incurred so far this session

Boot validator probes hit Vertex AI ~6 times during the iterative debug cycle (each `docker compose run` for diagnosis + 4 final lifespan starts). Estimated ~$0.10 in Flash + Pro calls. No actual pipeline runs landed; the one Magic Moment probe got stuck before extraction fired.

---

## Resume instructions

After Option A + fixtures + slack-post enqueue land:

```bash
cd c:/Users/hp/Solvo_demo
git rm HUMAN_INTERVENTION_REQUEST.md
docker compose build api worker
docker compose up -d --wait
# Re-run Stage F.3 with the now-existing K+N fixture
```
