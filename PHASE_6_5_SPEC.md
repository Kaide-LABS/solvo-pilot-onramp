# PHASE 6.5 SPEC — Sprint 1 Closure Patches

**Output of Step 2 (Phase 6.5 spec generation).** Consumes the Stage F.3 halt log at `SMOKE_TEST_LOG.md` (commit `3ad64e4`), the `HUMAN_INTERVENTION_REQUEST.md` written at the halt, the Sprint 1 build artefacts (`BUILD_COMPLETE.md`, `PHASE_1_SPEC.md` through `PHASE_6_SPEC.md`), and the live state of the codebase as committed at `98030d2` (path-1 PRD patches). Feeds: a single Step 3A build cycle, a single Step 3B review cycle, and then Sprint 1 closes for real.

---

## §0 — Phase Plan Header

**This is Phase 6.5 of the Sprint 1 build — a closure patch following the Stage F.3 smoke test halt.** Sprint 1 shipped 6 phases ending at `BUILD_COMPLETE.md`. Phase 6.5 fixes three defects that block end-to-end pipeline execution under Celery and prevent Stage F.3–F.5 smoke from running. After Phase 6.5 lands (Step 3A build approved by Step 3B review), Sprint 1 closure is genuinely complete and demo recording is authorized via a Stage F.3–F.5 re-run.

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake. |
| ✅ Phase 2 | 8–20 | Ratesheet schemas, Stage 1 classifier, Stage 2 Excel extractor. |
| ✅ Phase 3 | 20–28 | Stage 3 N=3 Pro ensemble, UN/LOCODE + WCO HS6 reference load. |
| ✅ Phase 4 | 28–36 | EDIFACT, Stage 4 rules engine, audit trail, `/internal/v1/audit`. |
| ✅ Phase 5 | 36–48 | Slack + intake + dispatcher + Phase 4 wiring closure. |
| ✅ Phase 6 | 48–60 | Cloud Run europe-west4 deployment + lifecycle. |
| **Phase 6.5** | post-F.3 halt | **Three closure patches: (1) per-task SQLAlchemy engine to fix Celery cross-loop bug, (2) demo fixtures K+N + 3 broken, (3) `slack_post` outbox enqueue from `_validate`. Plus regression test that would have caught Defect 1.** |

Three defects (referenced by name throughout this spec):

- **Defect 1 — Celery / async-SQLAlchemy loop incompatibility**: `@lru_cache` on `get_async_engine` makes Postgres-touching Celery tasks die with `RuntimeError: got Future attached to a different loop` after the first task per process.
- **Defect 2 — Missing demo fixtures**: `K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` and the three `broken_*` fixtures referenced by Stage F.3 + F.4 don't exist.
- **Defect 3 — Missing `slack_post` outbox enqueue**: dispatcher can deliver `slack_post` events and the Block Kit builder exists, but no caller in the ingest pipeline writes that outbox row. Stage F.3.3's "Slack thread reply within 60 s" is structurally impossible.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 6.5.** Per ULTIMATE_PRD §4.7, the provisional citations (Bai et al. 2305.14336, Ugare et al. 2403.01632, Wan et al. 2408.17017) were re-verified at the Phase 2 and Phase 4 boundaries. Phase 6.5 introduces no new academic claims — it is pure bug-fix and fixture work — so no citation gate runs.

---

## §1 — Files Added or Modified

**Modified:**

- `packages/core/db/session.py` — remove `@lru_cache` from `get_async_engine`; rename to `make_async_engine` to signal the caller-owns-disposal contract. Add a separate `get_lifespan_engine()` thin wrapper for the FastAPI lifespan that mutates `app.state.engine`.
- `packages/ingest/tasks.py` — restructure the four task async cores (`_classify`, `_extract`, `_normalize`, `_validate`) to construct + dispose their own engine. Also add the `slack_post` outbox row write inside `_validate` immediately after the existing `audit_log` write (single transaction).
- `packages/dispatcher/outbox_worker.py` — apply the same per-call engine pattern to `_drain_once`.
- `apps/api/main.py` — explicit engine lifecycle in the lifespan: construct via `make_async_engine` at startup, attach to `app.state`, `await app.state.db_engine.dispose()` at shutdown. Boot validators continue to use a session derived from this engine.
- `packages/core/db/session.py:get_async_session` — FastAPI dependency reads `app.state.db_engine` instead of calling `get_async_engine()` (the dependency function signature needs a `Request` parameter or an engine pulled from a contextvar — spec keeps both paths open; build agent picks the cleanest).
- `apps/api/routes/health.py` — readiness endpoint that uses the lifespan engine continues to work unchanged; spec calls this out only to confirm no regression.
- `tests/conftest.py` — fixture that supplies a per-test engine via `make_async_engine`, disposed in teardown.
- `data/_generate.py` — extended to generate K+N + 3 broken fixtures, deterministic via fixed RNG seed.
- `fixtures/_generate.py` — left as-is (the existing demo-fixture generator for `01..05_*.xlsx`); spec does NOT merge the two generators.

**Added:**

- `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` — 50-lane K+N-style synthetic ratesheet (specified in §6.2 below).
- `fixtures/broken_impossible_port_codes.xlsx` — 5 lanes, 2 with invalid UN/LOCODE.
- `fixtures/broken_negative_rates.xlsx` — 4 lanes, 1 with negative `base_rate_usd`.
- `fixtures/broken_malformed_edifact.edi` — valid PRICAT envelope with corrupted UNH segment.
- `tests/integration/test_pipeline_e2e.py` — Celery-driven end-to-end regression test that would have caught Defect 1.

**Deleted:** none.

> **Note on prompt-spec path drift:** the Step 2 prompt referenced `apps/worker/tasks.py`. The actual ingest task module is `packages/ingest/tasks.py` (registered into Celery via `apps/worker/celery_app.py:autodiscover_tasks(packages=["packages.ingest"], related_name="tasks")`). All references in this spec use the real path.

---

## §2 — Pip Dependencies

**No new top-level dependencies.** All fixes use the existing dependency set.

Dev/test extras may benefit from `pytest-celery>=1.0` for the e2e regression test, but the test can be written without it (using `task.apply_async` with `task_always_eager=False` against the running compose worker). Build agent: prefer the no-new-deps path. If pytest-celery is unavoidable, halt and add a one-line update to `docs/modernization_log.md` §12.

---

## §3 — Pydantic Schemas

**No new schemas.** The `slack_post` outbox event payload already has a shape contract from Phase 5 (`packages/dispatcher/delivery.py:deliver_slack_post` consumes `channel`, `blocks`, `text` keys). The `audit_log` outbox row continues to use the existing structure from Phase 4.

---

## §4 — FastAPI Route Signatures

**No route changes.** All defects live in the Celery worker path (`packages/ingest/tasks.py`, `packages/dispatcher/outbox_worker.py`). The FastAPI ingress at `/v1/intake/jobs` is unchanged.

---

## §5 — Alembic Migration

**No migration.** Phase 6.5 is runtime / behaviour fixes only. The terminal migration head stays at `0004_intake_review`.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 1 Fix: Per-Task SQLAlchemy Engine

**Problem (precise statement).** `packages/core/db/session.py:get_async_engine()` is decorated with `@lru_cache(maxsize=1)`. The function returns the same `AsyncEngine` instance for every caller. SQLAlchemy's async pool holds `asyncpg` connections; each connection is bound to whichever `asyncio` event loop opened it.

In FastAPI this is fine: the entire process runs under one event loop, owned by the lifespan handler. Connections opened during boot validators are reusable through the request-handling lifetime of the same loop.

In Celery this is broken. Each task entry calls `asyncio.run(...)` to drive its async core. `asyncio.run` constructs a fresh loop, runs the coroutine, then closes the loop. The lru-cached engine returned to task N has connections bound to task N-1's (now-closed) loop. The first pool checkout in task N triggers a connection `ping` that calls into asyncpg's protocol, which calls `loop.create_task(...)` — and the loop is closed → `RuntimeError: got Future attached to a different loop` (sometimes surfaces as `Event loop is closed`).

The Stage F.3 halt log captured this trace from the dispatcher's `_drain_once` task; the same bug fires from every ingest task on its second-and-onwards invocation.

**Fix (precise statement).**

1. **Rename and unbind the cache**: rewrite `packages/core/db/session.py:get_async_engine()` as `make_async_engine(settings: Settings) -> AsyncEngine` with no caching. Each call constructs a new engine. Caller owns disposal.

   ```python
   def make_async_engine(settings: Settings | None = None) -> AsyncEngine:
       """Construct a fresh AsyncEngine. Caller is responsible for disposal.

       NOT @lru_cache'd — each Celery task needs its own engine bound to its
       own asyncio loop. The FastAPI lifespan owns its engine separately via
       `apps/api/main.py:lifespan`.
       """
       settings = settings or get_settings()
       return create_async_engine(
           settings.postgres_dsn_async,
           pool_size=5,
           max_overflow=5,
           pool_pre_ping=True,
           future=True,
       )
   ```

2. **FastAPI lifespan owns one engine for the whole process**. In `apps/api/main.py:lifespan`:

   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI) -> AsyncIterator[None]:
       settings = get_settings()
       configure_logging(settings)
       app.state.db_engine = make_async_engine(settings)
       try:
           results = await run_all_boot_validators(settings)
           app.state.boot_results = results
           failed = [r for r in results if not r.passed]
           if failed:
               raise SystemExit(failed[0].exit_code_on_failure)
           yield
       finally:
           await app.state.db_engine.dispose()
   ```

3. **`get_async_session` becomes engine-aware** so request handlers continue to work:

   ```python
   async def get_async_session(request: Request) -> AsyncIterator[AsyncSession]:
       engine: AsyncEngine = request.app.state.db_engine
       factory = async_sessionmaker(engine, expire_on_commit=False)
       async with factory() as session:
           yield session
   ```

   Boot validators currently call `make_async_engine` themselves inside their async cores (e.g., the alembic-head and un_locode validators). Those call sites must be updated to *use the lifespan engine* by accepting an `AsyncEngine` parameter, OR — simpler — keep calling `make_async_engine` themselves and dispose at the end of their coro. Build agent: pick the smaller diff. The validators run once at startup so the per-validator engine cost is irrelevant.

4. **Every Celery task that touches Postgres uses the construct + dispose pattern.** The four ingest tasks plus the dispatcher drain:

   | Module | Function | Currently uses | Phase 6.5 pattern |
   |---|---|---|---|
   | `packages/ingest/tasks.py` | `_classify` | `get_async_engine()` lru-cached | `engine = make_async_engine(); try: ... ; finally: await engine.dispose()` |
   | `packages/ingest/tasks.py` | `_extract` | same | same |
   | `packages/ingest/tasks.py` | `_normalize` | same | same |
   | `packages/ingest/tasks.py` | `_validate` | same | same |
   | `packages/dispatcher/outbox_worker.py` | `_drain_once` | same | same |

   Pattern for every one (illustrative for `_classify`):

   ```python
   async def _classify(job_id: str, staging_path: str) -> str:
       settings = get_settings()
       engine = make_async_engine(settings)
       try:
           factory = async_sessionmaker(engine, expire_on_commit=False)
           # existing body using factory()
           ...
           return detected_format
       finally:
           await engine.dispose()
   ```

   Each task ends with `await engine.dispose()`, after which `asyncio.run()` cleans up the loop.

5. **Cost.** Per-task engine construction is roughly 30–80 ms of TCP+TLS handshake (when `pool_pre_ping=True` runs its first ping). Across the four-task ingest chain that is 120–320 ms total overhead per job. The dispatcher drains the outbox every 5 seconds, so its engine overhead is ~80 ms × 12 = ~1 s/min of redundant connection churn. Acceptable for demo scale; revisit for production by switching to a process-wide loop-resident engine (Option C in `HUMAN_INTERVENTION_REQUEST.md`) when the engagement requires it.

### §6.2 — Defect 2 Fix: Missing Demo Fixtures

`data/_generate.py` already exists and produces deterministic synthetic UN/LOCODE + HS6 reference CSVs. Phase 6.5 extends it (or — if cleaner — adds a sibling module under `data/` invoked from the same `__main__` block) to emit the four new fixture files into `fixtures/`. Determinism: seed all `random` calls with a fixed constant (e.g., `random.seed(0x5010-06-2026)`) so re-runs are byte-identical.

#### `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` — 50-lane Magic Moment

Single-sheet workbook. 50 data rows + 5 merged-cell rate-tier header rows interleaved. ~50 columns total. Built via `openpyxl`.

**Columns:**
- `origin_port` — mix of clean UN/LOCODE (`DEHAM`, `NLRTM`, `USNYC`, …) and obfuscated forms (`Hamburg DE`, `Hambourg`, `Rotterdam (NL)`, `New York NY`, …) at ~40/60 ratio.
- `destination_port` — same mix.
- `equipment_type` — random pick from `{20DV, 40DV, 40HC, 40RF}` (note: the running schema accepts `{20GP, 40GP, 40HC, 20RF, 40RF, OOG, BULK}` — `20DV`/`40DV` are intentional obfuscations the LLM should normalize to `20GP`/`40GP`).
- `base_rate_usd` — float between 800 and 9500, two decimals.
- `effective_date` — half ISO format (`2026-04-01`), half prose (`Apr 1 2026`, `1 April 2026`).
- `expiry_date` — mix of valid future dates, `Q2 2026`, `Q3 2026`, blanks, and the deliberate-past entry described below.
- Surcharge columns: `BAF`, `CAF`, `PSS`, `GRI`, `IMO`, `War_Risk`, `Document_Fee` — random `0.00`–`450.00`, some left blank.
- Five free-text "carrier notes" columns with prose like "Subject to availability, contact account exec for spot rate" — these should be ignored by the extractor.

**Merged header rows** at row indices 1, 12, 24, 36, 47 with text like "STANDARD RATES", "VOLUME CUSTOMER RATES", "SPOT RATES Q2 2026", "RF / TEMP-CONTROLLED", "BUNKER UPLIFTS — POST APR 15".

**Three deliberate breakages** embedded among the 50:

- **Lane 23** — `origin_port = "ZZZZZ"`. Impossible UN/LOCODE. Expected outcome: deterministically rejected by Stage 4 rules engine with citation matching pattern `port_unknown_unlocode`.
- **Lane 31** — `base_rate_usd = -1500.00`. Negative rate. Expected outcome: deterministically rejected by Stage 4 with citation matching `negative_base_rate`.
- **Lane 47** — `expiry_date = "Feb 1 2025"` (in the past). Expected outcome: deterministically flagged via `validity_window_in_the_past` rule.

**Expected pipeline output** (acceptance criteria for the Magic Moment run):
- ~45 normalized lanes (50 - 3 rejected - 1-2 expected ensemble disagreements)
- ~2 flagged for review (Lane 47 + 1 obfuscated-port flag)
- ~3 deterministically rejected (Lanes 23, 31, plus typically 1 from ensemble disagreement that escalated through correction)

These counts are targets; the smoke test allows ±5% on normalized count and ±2 on flagged/rejected counts because LLM sampling is non-deterministic at temps 0.5/0.9.

#### `fixtures/broken_impossible_port_codes.xlsx` — 5 lanes, 2 rejection-triggering

Single sheet. 5 data rows, no merged cells.

- Lanes 1, 2, 4: clean (`DEHAM→USNYC`, `NLRTM→SGSIN`, `USLAX→JPYOK`).
- Lane 3: `origin_port = "ZZZZZ"`.
- Lane 5: `destination_port = "QQQQQ"`.

Expected: 3 normalized, 2 rejected with `rule_id = "port_unknown_unlocode"` and `rule_description` containing the specific bad code.

#### `fixtures/broken_negative_rates.xlsx` — 4 lanes, 1 rejection-triggering

Single sheet. 4 data rows.

- Lanes 1–3: clean with `base_rate_usd` ∈ {1850.00, 2450.00, 3100.00}.
- Lane 4: `base_rate_usd = -2400.00`.

Expected: 3 normalized, 1 rejected with `rule_id = "negative_base_rate"` and `rule_description` containing the literal negative value.

#### `fixtures/broken_malformed_edifact.edi` — Corrupted PRICAT

Plain-text EDIFACT file. Valid `UNB` envelope and trailer `UNZ`. UNH segment uses an invalid version qualifier: `UNH+1+PRICAT:D:01B:UN:EAN999` (the valid form is `UNH+1+PRICAT:D:96A:UN:EAN007`).

Expected: parsing fails inside `packages/ingest/edifact_extractor.py` deterministic Stage-1 / Stage-2 path BEFORE any LLM call. The job lands with status `failed` and the failure payload's `rejection_reason` cites the specific UNH segment in error text (e.g., `"EDIFACT structural validation failed at segment UNH+1+PRICAT:D:01B:UN:EAN999"`).

#### Determinism contract

`data/_generate.py` must be re-runnable. Running it twice in a clean repo produces byte-identical XLSX + EDI files. openpyxl's default behaviour stamps a workbook creation timestamp into the file — disable this by setting `wb.properties.created = datetime(2026, 5, 1, 0, 0, 0)` and `wb.properties.modified = datetime(2026, 5, 1, 0, 0, 0)` before save. All RNG calls use `random.Random(0xKAIDE5010)` so synthetic port codes / rates / surcharges are reproducible.

### §6.3 — Defect 3 Fix: `slack_post` Outbox Enqueue from `_validate`

**Problem (precise statement).** `packages/dispatcher/delivery.py:deliver_slack_post` exists and calls `WebClient.chat_postMessage`. `packages/slack/block_kit.py:build_summary_blocks` exists and produces the Block Kit JSON. `packages/ingest/outbox.py:OutboxEventType` registers `slack_post`. The dispatcher polls the outbox every 5 s and dispatches by event type.

But nothing in the ingest pipeline writes the `slack_post` row. The `_validate` task in `packages/ingest/tasks.py` writes an `audit_log` row with `stage="validated"` and stops there. The Slack thread reply specified in Phase 5 spec §6.6 is a dead end.

**Fix (precise statement).** Inside `_validate`, after the existing `audit_log` enqueue but inside the same `session.begin()` block (transactional-outbox invariant), enqueue a `slack_post` row whose payload contains the Block Kit blocks already constructed from the `NormalizedRatesheet` output.

Illustrative diff (around the existing `_validate` body):

```python
# ... existing imports remain
from packages.slack.block_kit import build_summary_blocks
# (signed URL helper already imported in Phase 5 for the result-url route;
#  re-use the same generator here to attach the download link)
from packages.storage.signed_url import generate_v4_signed_url

async def _validate(job_id: str) -> None:
    settings = get_settings()
    engine = make_async_engine(settings)
    try:
        # ... existing rules_engine + conformal + correction + clarification ...

        async with factory() as session, session.begin():
            await insert_output(session, job_id=job_id, payload=validated_payload)
            await update_job_status(session, job_id, new_status="completed", completed=True)

            await enqueue_outbox_event(
                session,
                job_id=job_id,
                event_type="audit_log",
                payload={"stage": "validated", ...},  # unchanged
            )

            # NEW — Phase 6.5
            signed_url, _expires = await generate_v4_signed_url(
                bucket=settings.gcs_bucket_outputs,
                blob_name=f"jobs/{job_id}/normalized_ratesheet.json",
                service_account=settings.gcs_signer_service_account,
            )
            summary_blocks = build_summary_blocks(
                rs=validated_payload,
                signed_url=signed_url,
                expires_at_iso=_expires.isoformat(),
            )
            await enqueue_outbox_event(
                session,
                job_id=job_id,
                event_type="slack_post",
                payload={
                    "channel": job_row.requested_slack_channel,  # populated by intake route
                    "blocks": summary_blocks,
                    "text": f"Solvo Onramp result for {job_row.prospect_name}",
                },
            )
    finally:
        await engine.dispose()
```

**Contract details:**

- The `channel` field comes from `OnrampJob.requested_slack_channel`. Phase 5 `intake.py` already stamps this on the job row from the `IntakeJobRequest.requested_slack_channel` form field, so `_validate` can read it from the existing job row before the outbox enqueue. If the build agent finds that `requested_slack_channel` is NOT persisted (Phase 5 might have only captured it in-memory) — flag and halt; that's an unannounced sub-defect of Phase 5 that needs its own ticket.
- The signed-URL TTL is the locked 900 s from `packages/storage/signed_url.py:SIGNED_URL_TTL_SECONDS`. The Block Kit summary shows the expiry time so the recipient knows.
- The Block Kit blocks must obey the Anti-Replication invariant: zero raw rate values embedded. `build_summary_blocks` already enforces this with the test in `tests/unit/test_block_kit.py`; the new caller doesn't change that.
- The `slack_post` row commits **in the same transaction** as the `onramp_outputs` upsert and the `audit_log` row. This preserves the transactional-outbox invariant from baseline §2.4 — if the validation rolls back, no Slack post leaks.

**Expected behaviour after the fix:** dispatcher's 5-second beat picks up the row within at most 5 s of validation commit. `deliver_slack_post` posts the Block Kit message to the channel from the job row. End-to-end latency from `POST /v1/intake/jobs` to Slack message visible: typically 30–60 s for a 3-lane fixture (most of it is the N=3 Pro ensemble + signed-URL generation).

### §6.4 — Regression Test: `tests/integration/test_pipeline_e2e.py`

**Why this matters more than the fix itself.** The reason Defect 1 escaped Sprint 1's 6-phase review is that no test exercised a Celery task touching Postgres after another Celery task had already touched Postgres in the same process. Unit tests mock the engine. Phase 5's `test_outbox_worker.py` only asserts static behaviour (backoff schedule, lock pattern). Phase 6 acceptance criteria are all infrastructure smoke; they don't drive a real job through Celery. Phase 6.5 closes this gap with a single integration test that would have caught all three defects.

**Test outline:**

1. Use `docker compose up -d postgres redis` and the api+worker images already built (the test is gated by `SOLVO_RUN_E2E_TESTS=1` env var, matching the pattern from Phase 3's `test_reference_load.py`).
2. Pre-load reference data (UN/LOCODE + HS6) via the existing scripts.
3. Submit `fixtures/01_clean_excel.xlsx` against the running `solvo_demo-api` via `POST /v1/intake/jobs` with all required form fields (`prospect_id`, `prospect_name`, `operator_email`, `requested_slack_channel`, `priority`).
4. Poll `/v1/intake/jobs/{id}` until `status=completed` or 90 s timeout.
5. Assert: status reached `completed`. Without the Defect 1 fix, this stays at `pending` indefinitely.
6. Query Postgres directly for the job's outbox rows. Assert exactly one `audit_log` row with `stage=validated` and exactly one `slack_post` row with the expected channel + non-empty `blocks`. Without the Defect 3 fix, the `slack_post` row is missing.
7. Stub `packages.slack.client.get_slack_client` to a recording mock for the duration of the test. Run one tick of the dispatcher (`docker compose exec dispatcher celery -A apps.worker.celery_app call tasks.dispatcher.drain_outbox` or equivalent). Assert the mock recorded a `chat_postMessage` call with `channel=<the requested channel>` and `blocks=<non-empty>`.

The test is **gated** behind an env var because it requires a live docker-compose stack and would burn ~$0.30 of Vertex AI per run.

---

## §7 — Cross-Phase Integration Requirements

Phase 6.5 must NOT break:

- **Phase 1 boot validators.** The four-validator chain still runs from the FastAPI lifespan and the Celery worker boot, returning a `HealthResponse` with all four `passed=true` from `/v1/health`. The session module change must not change the validator API.
- **Phase 4 audit_log writes.** The `_validate` task still writes the `audit_log` outbox row with the existing `stage=validated` payload shape. Phase 6.5 only **adds** the `slack_post` row alongside it.
- **Phase 5 dispatcher delivery code.** `packages/dispatcher/delivery.py:deliver_slack_post` is unchanged. The `slack_post` event type literal in `packages/ingest/outbox.py:OutboxEventType` is unchanged.
- **Phase 6 Cloud Run deployment topology.** This is a code-only patch; `infra/terraform/`, `cloudbuild.yaml`, and the three Dockerfiles are unchanged.
- **Anti-Replication boundary.** No pricing logic, no model substitutions (gemini-3.1-flash-lite and gemini-3.1-pro-preview remain pinned), no region drift (Cloud Run + storage stay in europe-west4; Vertex AI inference stays at `location='global'` per the path-1 PRD patches at commit `98030d2`).
- **Transactional outbox invariant.** The new `slack_post` row commits in the same `session.begin()` block as the existing `audit_log` row and the `onramp_outputs` upsert.

---

## §8 — Phase 6.5 Acceptance Criteria

Step 3B advances to `BUILD_COMPLETE.md` (final close) only when ALL of the following are true:

1. **No `@lru_cache` on the engine constructor.** `git grep "@lru_cache" packages/core/db/session.py` returns zero matches.
2. **Function renamed.** `packages/core/db/session.py` exposes `make_async_engine(settings: Settings | None = None) -> AsyncEngine`. All call sites import the new name.
3. **Every Postgres-touching Celery task uses construct + dispose.** Static grep: `grep -E "engine = make_async_engine|await engine.dispose" packages/ingest/tasks.py packages/dispatcher/outbox_worker.py` shows the pattern in `_classify`, `_extract`, `_normalize`, `_validate`, `_drain_once` (5 occurrences each).
4. **FastAPI lifespan owns one engine.** `apps/api/main.py:lifespan` calls `make_async_engine` exactly once at startup and `app.state.db_engine.dispose()` exactly once at shutdown.
5. **`_validate` writes both audit and slack rows.** A `git diff` of `packages/ingest/tasks.py:_validate` against the pre-Phase-6.5 commit shows the new `enqueue_outbox_event(... event_type="slack_post" ...)` call inside the same `session.begin()` block as the existing `audit_log` write.
6. **All four new fixtures exist.** `ls fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx fixtures/broken_impossible_port_codes.xlsx fixtures/broken_negative_rates.xlsx fixtures/broken_malformed_edifact.edi` returns four entries.
7. **Fixtures are deterministic.** Running `python data/_generate.py` twice in a clean checkout produces byte-identical files for all four (verifiable via `sha256sum`).
8. **`tests/integration/test_pipeline_e2e.py` exists and passes** when run with `SOLVO_RUN_E2E_TESTS=1` against a running compose stack. The test fails (in a documented way) against the pre-Phase-6.5 code, proving it's a real regression guard.
9. **Pre-existing unit tests still pass.** `pytest tests/unit -q` returns zero failures.
10. **Lint + types clean.** `ruff check .` returns 0; `mypy --strict packages/core packages/compliance packages/ingest packages/reference packages/slack packages/storage packages/dispatcher packages/lifecycle apps/api` returns 0.
11. **Secret scan clean.** `gitleaks detect --no-banner --no-git --source .` returns zero findings.
12. **Stage F.3 re-run readiness.** After Step 3A builds and Step 3B reviews Phase 6.5, a single re-run of Stage F.3 (Magic Moment × 3 against the K+N fixture) is the next gate. Phase 6.5 acceptance does NOT require running F.3; F.3 is the post-approval validation.

---

## §9 — Explicit NON-GOALS for Phase 6.5

- **No model string changes.** Gemini 3.1-flash-lite (Stage 2) and Gemini 3.1-pro-preview (Stage 3) stay pinned.
- **No region changes.** `VERTEX_LOCATION=global` for inference stays; europe-west4 for Cloud Run + storage stays.
- **No PRD additions.** Master PRD §5 and ULTIMATE_PRD §3.10 already reflect the path-1 routing per commit `98030d2`. No further edits.
- **No new Postgres tables.** `audit_log` and `outbox` tables stay as-is.
- **No Slack scope additions.** Existing bot scopes (chat:write, chat:write.public, files:read, files:write, channels:history, groups:history, im:history, im:write, users:read) are sufficient.
- **No customer-side deployment.** Phase 2 ladder per ULTIMATE_PRD §3.10.6 stays deferred.
- **No expansion of Phase 5 dispatcher delivery code.** The `deliver_slack_post`, `deliver_webhook_callback`, etc. functions are unchanged. Phase 6.5 only adds a caller for one event type that already exists.
- **No Stage F.3–F.5 execution.** Phase 6.5 closes only when builds + tests pass; the actual smoke re-run that authorizes demo recording is a separate Step 4 cycle after Phase 6.5 is approved.
- **No new fixture types.** Only the four new XLSX/EDI files specified in §6.2. No JSON fixtures, no PDF fixtures, no email (.eml) fixtures (email ingress is Phase 2 deferred work — out of scope for the sprint).
- **No Phase 7.** Sprint 1 ends at Phase 6.5 close. Subsequent engagement-side work (Procurement Lens at month 2, etc.) starts a fresh sprint cadence.

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do not touch `PHASE_1_SPEC.md` through `PHASE_6_SPEC.md`. They are historical and are committed at their own SHAs.
- Do not rename `apps/worker/celery_app.py`, `packages/ingest/tasks.py`, or `packages/dispatcher/outbox_worker.py`. Adjust their internals only.
- Do not introduce a worker-process-resident asyncio loop (Option C from `HUMAN_INTERVENTION_REQUEST.md`). That's a more invasive refactor that deserves a dedicated phase if the demo-scale per-task engine cost becomes a real concern.
- Do not add a second event-loop layer (e.g., trio, anyio bridges) — Celery + `asyncio.run` + per-task engine is the agreed Phase 6.5 shape.
- Do not extend the smoke-test fixture set beyond the four specified files. Edge cases beyond those are scope creep.
- Do not commit any fixture larger than 100 KB. The K+N fixture should land at ~30–50 KB given 50 rows × ~50 columns × ~10 bytes/cell + openpyxl overhead. If actual size exceeds the cap, halt and report — likely an openpyxl style-bloat issue worth diagnosing rather than papering over.

---

## §11 — Hard Invariants (Restated)

- Every Pydantic BaseModel uses `model_config = ConfigDict(extra="forbid")`.
- All Vertex AI calls bind to `location='global'` (path-1 routing) with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation (dev permissive on ZDR enrollment, production requires `VERTEX_AI_ZDR_ENROLLED=true`).
- Container-boot validators fail-fast on misconfiguration (the four from §3.10).
- Anti-Replication boundary: no pricing, no POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing logic, no rate / margin / recommendation computation.
- Transactional outbox: outbox rows commit in the same transaction as job state updates.
- Redis distributed locks use `SET NX EX` pattern (not Redlock, not WATCH/MULTI).
- N=3 Pro ensemble at temperatures (0.1, 0.5, 0.9) with majority-vote consensus stays exactly as Phase 3 shipped.

---

*End of Phase 6.5 Spec. Next: Step 3A executes against this spec (one build cycle); Step 3B reviews (one review cycle); on approval, Sprint 1 closes for real and Stage F.3–F.5 re-run is the path to demo authorization.*
