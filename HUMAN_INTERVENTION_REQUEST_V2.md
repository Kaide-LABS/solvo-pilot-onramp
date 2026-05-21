# Human Intervention Required — Step 4 Stage F.3 re-run (post Phase 6.5 closure)

Run started: 2026-05-21 (after Phase 6.5 approval at commit `e99cfb4`).
Stage: F.3 — Magic Moment × 3 against K+N 50-lane fixture.
Outcome: **Stage F.3 BLOCKED.** F.3 Run 1 failed; Runs 2-3 not attempted.

Phase 6.5 fixed the three named defects (SQLAlchemy cross-loop, missing fixtures, missing slack_post enqueue). The smoke re-run has now surfaced **four additional defects** that none of Phases 1-6, the Stage F.3 halt log, or the Phase 6.5 review caught — and one structural mismatch between the spec's F.3 budget and the K+N fixture size.

The reasonable next step is human review before more Vertex AI spend.

---

## Defects surfaced (in order of discovery)

### Defect 4 — `docker-compose.yml` lacks a shared staging volume

**Symptom.** First job submission worked at the API but the worker died immediately with `FileNotFoundError: '/tmp/onramp/<job_id>/<filename>'`. The API writes uploaded payloads to its own container's local `/tmp/onramp`; the worker is a separate container with a separate filesystem.

**Root cause.** `docker-compose.yml` mounts `gcp-adc` and (for postgres) `pgdata`, but no shared volume backs `/tmp/onramp`. Either Phase 5 (intake route) or Phase 6 (compose topology) should have caught this. The acceptance criteria for Phase 6 included "Cloud Run europe-west4 deployment + lifecycle" — Cloud Run would use GCS for staging, masking the gap on the deployment target but breaking the local compose stack on which F.3 runs.

**My patch (applied in this run, not committed).** Added a named volume `staging` mounted at `/tmp/onramp` to both `api` and `worker` services.

```yaml
# docker-compose.yml
services:
  api:
    volumes:
      - ${USERPROFILE:-${HOME}}/AppData/Roaming/gcloud:/gcp-adc:ro
      - staging:/tmp/onramp        # NEW
  worker:
    volumes:
      - ${USERPROFILE:-${HOME}}/AppData/Roaming/gcloud:/gcp-adc:ro
      - staging:/tmp/onramp        # NEW
volumes:
  pgdata:
  staging:                          # NEW
```

This patch is in the working tree. Needs to be committed if accepted.

### Defect 5 — `get_vertex_client` cache replicates the Defect-1 cross-loop bug

**Symptom.** Second job submission got past extraction (the staging file was readable after the volume fix) but the `_extract` Celery task died at the very first `client.aio.models.generate_content(...)` call with:

```
RuntimeError: Event loop is closed
```

…surfacing through `httpcore._async.connection_pool` cleanup. The traceback came from a `_close_connections` call inside the httpx pool that the genai SDK owns internally.

**Root cause.** `packages/compliance/vertex_client.py:get_vertex_client` was a module-level singleton cached by `(gcp_project_id, vertex_location)`. The Vertex AI handshake at boot (one of the four boot validators) populated this cache against the boot-validator's `asyncio.run` loop, which then closed. Celery's prefork model copies the parent process's module memory into each `ForkPoolWorker`, so when a forked worker invoked the first `_extract` task, it inherited an httpx async client whose connection pool's connections were bound to the parent's closed loop. The first `aclose`-on-error attempt during connection cleanup blew up.

This is **exactly the same Defect-1 pattern** as the SQLAlchemy engine bug Phase 6.5 fixed — just on a different cached client. The Phase 6.5 spec didn't catch it because the Stage F.3 halt traceback at commit `3ad64e4` only showed the SQLAlchemy path; the Vertex client path only surfaces once the SQLAlchemy path is fixed.

**My patch (applied in this run, not committed).** Removed the `_client_cache` from `packages/compliance/vertex_client.py`. Every call to `get_vertex_client(settings)` now constructs a fresh `genai.Client`, mirroring the Phase 6.5 `make_async_engine` contract.

```python
def get_vertex_client(settings: Settings) -> Client:
    """Construct a fresh Vertex AI client bound to the configured location.

    NOT cached. The genai Client wraps an httpx AsyncClient whose connections
    are bound to the asyncio loop that opens them. Under Celery's prefork +
    `asyncio.run`-per-task model — same Defect-1 vector as the SQLAlchemy
    engine fix in PHASE_6_5_SPEC §6.1 — a module-level cache lets a child
    process inherit a client whose pooled connections reference the parent's
    (closed) boot-validator loop, surfacing as `Event loop is closed` on the
    first task call. Per-call construction avoids the cross-loop hazard.
    """
    from google import genai
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.vertex_location,
    )
```

Trade-off recorded: per-task client construction adds gRPC channel setup overhead. Acceptable for demo scale; deserves a worker-process-resident-loop refactor (Option C from the original `HUMAN_INTERVENTION_REQUEST.md`) for production.

This patch is in the working tree. Needs to be committed if accepted.

### Defect 6 — `_normalize` failure handler rolls back its own status update

**Symptom.** When the Stage 3 N=3 ensemble hits an `EnsembleError` (e.g., a Pro-call timeout at one of the three temperatures), `_normalize` re-raises and the Celery task is marked failed by Celery, but the **job row** stays at `status='normalizing'` forever. Polling `/v1/intake/jobs/{id}` never sees `failed`. The API has no way to surface the failure to the operator.

**Root cause.** In `packages/ingest/tasks.py:_normalize`, the failure-handler block is:

```python
async with factory() as session, session.begin():
    try:
        updated, consensus_results = await normalize_lanes(...)
    except EnsembleError as exc:
        await update_job_status(session, job_id, new_status="failed", completed=True)
        _log.warning("normalize_lanes: job=%s failed: %s", job_id, exc)
        raise          # <-- raises out of session.begin() → transaction rolled back
```

`session.begin()` is an async context manager that commits on clean exit and **rolls back on any exception**. The `raise` after `update_job_status` triggers a rollback, undoing the status update. The same pattern exists in `_extract` and is almost certainly broken there too (not yet observed because Defects 4 + 5 masked it).

**No patch applied.** The fix needs design judgment: either (a) commit the failure-status write in a separate prior transaction then re-raise from outside the `session.begin()` block, or (b) catch the EnsembleError outside the `session.begin()` and write the failure status in a fresh transaction. Option (b) is cleaner and matches the pattern PHASE_4 used in `_validate`. I did not apply a patch because this is a defect spanning multiple Celery tasks and deserves a unified fix.

### Defect 7 (structural, not a bug) — F.3 acceptance budget vs K+N fixture size

**Symptom.** F.3 acceptance criterion #1 is "Total runtime under 90 seconds." On the run that got past extraction, the job spent 28 s in extracting, then **5+ minutes in normalizing** before the EnsembleError hit. Worker logs show the N=3 Pro ensemble making ~150 generateContent calls (50 lanes × 3 temperatures) at typical latency 3-10 s each over the global endpoint. End-to-end normalize-only latency would be at minimum 7-10 minutes even on the happy path.

**Why this is structural, not a bug.** PHASE_6_5_SPEC §6.3 itself says: *"End-to-end latency from POST /v1/intake/jobs to Slack message visible: typically 30–60 s for a 3-lane fixture."* The K+N fixture is **50 lanes**, ~17× the 3-lane benchmark. Naïvely scaling gives 8.5-17 minutes per Magic Moment run. There is no plausible way to land 50 lanes through an N=3 Pro ensemble in 90 seconds — the spec's F.3.1 acceptance is mathematically incompatible with the fixture size unless concurrency is dramatically increased (currently the ensemble is sequential per lane in `normalizer.py`).

**Options for human to choose from:**
- **(a)** Relax F.3.1 to a realistic budget (e.g., 600 s / 10 min) and re-run.
- **(b)** Concurrent ensemble per lane (parallelize the N=3 calls) AND parallel lanes, accepting larger Vertex AI burst rate.
- **(c)** Shrink the Magic Moment fixture to ~10-15 lanes — still impressive on screen, fits the budget.
- **(d)** Lower-cost demo configuration: drop the N=3 ensemble for the demo path (gated by a `DEMO_MODE` env var), keep N=3 for production.

I have no spec mandate to pick (a)–(d) autonomously. This is a product decision.

### Pro-call timeout (not necessarily a defect, but worth flagging)

The failing Run 1 didn't time out on a polling deadline — it failed inside the ensemble call at temperature 0.1 with `Pro call timeout at T=0.1` from `packages/ingest/normalizer.py:129`. The actual SDK call window was unclear; could be a transient `aiplatform.googleapis.com/global` cold-start. May not reproduce in subsequent runs. But the failure-handler defect (Defect 6) means even transient timeouts can wedge a job permanently — that part is real.

---

## What I patched in this run

Both patches are in the working tree, **not committed**. Files modified:

```
docker-compose.yml                       (Defect 4: shared staging volume)
packages/compliance/vertex_client.py     (Defect 5: remove cross-loop cache)
```

If accepted as-is, the commit message should be:

```
fix: Step 4 F.3 re-run patches — shared staging volume, Vertex client cache removal

Two Defect-1-class cross-loop bugs surfaced during the Phase 6.5 post-closure
smoke re-run, in addition to a missing docker-compose volume that should have
landed in Phase 5/6. Patches:

- docker-compose.yml: add named volume `staging` mounted at /tmp/onramp on
  api + worker. Required for the intake → worker handoff in the local
  compose stack. Cloud Run uses GCS so this gap was masked on the deploy
  target but breaks the local smoke run.
- packages/compliance/vertex_client.py: remove the module-level
  `_client_cache`. The genai SDK's internal httpx AsyncClient holds
  connections bound to the loop that opened them. Same cross-loop hazard as
  the SQLAlchemy engine fix in PHASE_6_5_SPEC §6.1. Per-call construction
  matches the Phase 6.5 contract.
```

## What I did NOT patch

- **Defect 6** (failure-handler rollback in `_normalize` and likely `_extract` / `_validate`). Needs a unified fix design across all four ingest tasks.
- **Defect 7** (structural F.3 budget vs fixture mismatch). Needs product decision.

---

## State of the stack on disk

- `git status` after the run shows uncommitted edits to `docker-compose.yml` and `packages/compliance/vertex_client.py` (Defects 4 and 5 patches), and a stuck job row at `status='normalizing'` in postgres (from Defect 6).
- Container images: `solvo_demo-api`, `solvo_demo-worker`, `solvo_demo-dispatcher` were rebuilt with the vertex_client patch.
- No commits were made during this Step 4 re-run.
- Vertex AI cost: rough estimate **$3–7 USD** for the partial Run 1 (50 lanes × ~2-3 Pro calls per lane completed before the timeout). The bulk of Pro calls returned 200 OK before the timeout cut the run short.

## Next actions for the human

1. Decide whether to commit the two patches as-written, or refactor differently.
2. Decide on Defect 6 fix design and apply across `_extract`, `_normalize`, `_validate`.
3. Decide on Defect 7 path (relax budget / parallelize / shrink fixture / demo-mode flag).
4. Once 1-3 land, this Step 4 re-run can resume from Stage F.3 Run 1.

Demo recording is **NOT** authorized. The compose stack runs end-to-end through Stage 2 extraction; Stage 3 normalization is structurally too slow and has a stuck-state defect.
