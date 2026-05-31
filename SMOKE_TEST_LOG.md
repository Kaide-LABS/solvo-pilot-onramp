# E2E Smoke Test Log — Step 4

Run started: 2026-05-19 (Hafeedh's Windows 11 host)
Operator: Claude Code (Lead Operations Engineer role per Step 4 spec)
Repo HEAD: `69a757e` (`docs: Sprint 2 build complete — 6 phases shipped`)

---

## Stage 0 — Environment Variable Readiness
Started: 2026-05-19
Status: **HALTED**

### Milestone 0.1 — `.env` file present
Expected: `.env` exists at repo root with non-placeholder values for the 10 required vars.
Observed: `.env` does **not** exist. Only `.env.example` is present, and it is incomplete vs the Step-4 prompt's required-var list (see Milestone 0.2).
Verdict: ❌
Evidence: `ls .env` → `No such file or directory`. `wc -l .env.example` → 23 lines covering only the Phase 1 minimal set.

### Milestone 0.2 — Env-var nomenclature alignment between Step-4 spec and codebase Settings
Expected: variable names in `.env.example` match the Step-4 verification script.
Observed: nomenclature mismatch on six variables — the prompt uses generic GCP/Postgres conventions while the build uses Settings names pinned across Phases 1–6:

| Step-4 spec name | Codebase Settings name | Status |
|---|---|---|
| `GCP_REGION` | `VERTEX_LOCATION` | same concept, different name |
| `GOOGLE_APPLICATION_CREDENTIALS` | (rely on ADC / no explicit setting) | not in `Settings`; defaults via gcloud |
| `VERTEX_AI_DATA_LOGGING_DISABLED` | `VERTEX_AI_ZDR_ENROLLED` | same concept, different name; semantics inverted (the build's flag is "ZDR enrolled = true", which IMPLIES data logging disabled, plus an additional org-level enrollment commitment) |
| `DATABASE_URL` | `POSTGRES_DSN_ASYNC` + `POSTGRES_DSN_SYNC` | build splits async vs sync |
| `SLACK_APP_TOKEN`, `SLACK_WORKSPACE_ID` | (not in Settings) | build uses only `SLACK_BOT_TOKEN` + `SLACK_SIGNING_SECRET` (Phase 5 webhook is HTTP, not Socket Mode) |
| `CLOUD_STORAGE_BUCKET` | `GCS_BUCKET_OUTPUTS` + `GCS_ARCHIVE_BUCKET` | build splits live outputs vs 90-day archive |
| `ADMIN_TOKEN` | `INTERNAL_ADMIN_TOKEN` | same concept, different name |

Verdict: ⚠️ (non-blocking; the verification script needs to be retranslated against actual Settings names, OR Settings must be renamed)
Evidence: `cat .env.example` (committed) + `packages/core/settings.py` (Phase 6 head).

### Milestone 0.3 — Slack credentials
Expected: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` are valid and the bot is installed in a test workspace.
Observed: no Slack app installed; no tokens present in the operator's local environment.
Verdict: ❌

### Milestone 0.4 — Cloud Storage bucket
Expected: a europe-west4 GCS bucket exists for staging artifacts.
Observed: no bucket created. The terraform code creates one in Phase 6 (`solvo-onramp-outputs-${var.project_id}`) but `terraform apply` has never run against this environment.
Verdict: ❌

### Milestone 0.5 — Vertex AI project type
Expected: a real Vertex AI project (not a Google AI Studio `gen-lang-client-*` auto-created project).
Observed: gcloud's active project is **`gen-lang-client-0754692302`** — exact match for the Matta-debug failure mode the Step-4 prompt explicitly calls out as a HARD HALT.
Verdict: ❌ (this is the load-bearing failure)
Evidence:
- `gcloud config get-value project` → `gen-lang-client-0754692302`
- `gcloud projects describe gen-lang-client-0754692302 --format="value(projectNumber,lifecycleState)"` → `8822384086  ACTIVE`
- `gcloud ai models list --region=europe-west4 --project=gen-lang-client-0754692302` → `Listed 0 items.` (returns empty; the project has `aiplatform.googleapis.com` enabled for SDK access but no Vertex AI tenant resources)
- Both `aiplatform.googleapis.com` AND `generativelanguage.googleapis.com` are enabled — the classic AI Studio dual-mode signature, not a clean Vertex tenant.

### Stage 0 exit
**HALTED** — `.env` does not exist, Slack credentials missing, Cloud Storage bucket not provisioned, and the gcloud project is the wrong type (AI Studio, not Vertex tenant). All four pre-flight surfaces fail.

`HUMAN_INTERVENTION_REQUEST.md` written. Run halts.

---

## Stages 1–6
Not started — Stage 0 halt prevents progression.

---

## Final Summary
Total runtime: ~3 min (Stage 0 only)
Stages: 6
Stages passed: 0
Stages failed: 0 (none ran fully)
Blocking failures: 1 (env + project provisioning)
HUMAN_INTERVENTION_REQUEST.md created: YES
Demo recording authorized: **NO**

---

## Intervention Resolved — Stage B complete via app configuration token (2026-05-21)

Provisioning steps completed via Step 4 Unblock Resume prompt:

- **Stage A — GCP project** (`kaide-ai-84019`): ACTIVE, billing linked to `016E9D-6D6278-EA2838`, `aiplatform.googleapis.com` + `iamcredentials.googleapis.com` + storage APIs enabled, `generativelanguage.googleapis.com` is NOT enabled (no gen-lang trap). ADC quota project re-flipped off the prior gen-lang trap to `kaide-ai-84019`.
- **Stage B — Slack app** (`A0B5AA0UEUS`, `Solvo Pilot Onramp`): created via `apps.manifest.create` REST endpoint using a workspace app-configuration token (web UI was freezing). Installed to `Demo Sandbox` workspace (`T0AULUC55J6`) via the OAuth v2 flow with a localhost redirect catcher (`http://localhost:8765/oauth-callback`), authorization code exchanged via `oauth.v2.access`. Bot user: `U0B5AFHP2DQ` / `solvo_onramp`. `auth.test` green.
- **Stage C — GCS buckets**: `kaide-solvo-onramp-dev-staging` (7-day lifecycle on `raw/`) + `kaide-solvo-onramp-dev-archive`, both `europe-west4`. Signer SA `solvo-onramp-signer@kaide-ai-84019.iam.gserviceaccount.com` with `roles/iam.serviceAccountTokenCreator` self-binding and `roles/storage.objectAdmin` on both buckets. Write/read/delete smoke passed.
- **Stage D — `.env`**: written with build-side Settings names (`VERTEX_LOCATION`, `POSTGRES_DSN_ASYNC/SYNC`, `VERTEX_AI_ZDR_ENROLLED`, `INTERNAL_ADMIN_TOKEN`, `GCS_BUCKET_OUTPUTS`, `GCS_SIGNER_SERVICE_ACCOUNT`, etc.). All required vars present and non-placeholder. `.env` is gitignored.

Artifacts kept in-repo: `slack-app-manifest.yaml` (no secrets — manifest only). All raw tokens, OAuth codes, and the create-response credential cache wiped from `$HOME` after `.env` patch.

Next: re-run Step 4 Stages 1–5 against the provisioned environment.

---

## Stage F halted — Vertex preview-model 404 (2026-05-21)

Stage F.1 (pre-flight) and F.2 (boot validators) ran. Result:
- ✅ postgres, redis, dispatcher healthy
- ✅ alembic head = `0004_intake_review`
- ✅ `un_locode_reference` row count = 100,050 (clears the 100k floor)
- ❌ `vertex_ai_handshake` — TimeoutError (underlying: `gemini-3-flash-preview` returns 404)
- ❌ `vertex_ai_compliance_handshake` — TimeoutError (same upstream)

Direct probe from inside the api container with mounted ADC reproduces the 404 cleanly:

```
google.genai.errors.ClientError: 404 NOT_FOUND. 'Publisher Model
projects/kaide-ai-84019/locations/europe-west4/publishers/google/models/gemini-3-flash-preview
was not found or your project does not have access to it.'
```

`kaide-ai-84019` is not on the Gemini 3 preview allowlist. Both `gemini-3-flash-preview` and `gemini-3.1-pro-preview` are model-garden-gated previews.

Compose-fix delta committed alongside this halt (starlette pin, packaging install, Dockerfile scripts COPY, ADC mount, Settings hashability) — all independent of the preview-model gate.

Next step (per `HUMAN_INTERVENTION_REQUEST.md`): Hafeedh requests preview access via GCP Console Model Garden, then a single `docker compose restart api worker` resumes Stage F from criterion §F.3.

---

## Stage F.2 PASSED — all 4 boot validators green (2026-05-21)

After model swap + region + SDK fallback:

```
{
  "status": "healthy",
  "region": "europe-west4",
  "validators": [
    {"validator_name": "vertex_ai_handshake", "passed": true, "latency_ms": 4961, "detail": "flash_preview_responsive in global"},
    {"validator_name": "postgres_alembic_head", "passed": true, "latency_ms": 122, "detail": "alembic_head=0004_intake_review"},
    {"validator_name": "un_locode_table_integrity", "passed": true, "latency_ms": 74, "detail": "un_locode_rows=100050"},
    {"validator_name": "vertex_ai_compliance_handshake", "passed": true, "latency_ms": 3673, "detail": "rrl_disabled=True zdr_enrolled=False models=3.1-flash-lite,3.1-pro-preview retention=raw7d/norm90d/arch180d/audit365d"}
  ]
}
```

Changes applied since last halt:

- **Model swap** (user-authorized override of Step 4 invariant): `gemini-3-flash-preview` → `gemini-3.1-flash-lite` across `boot_validators.py`, `excel_extractor.py`, `edifact_extractor.py`, `core/models/ratesheet.py:ExtractionMetadata`, all related unit tests. Pro stays as `gemini-3.1-pro-preview`.
- **Vertex region for inference**: `VERTEX_LOCATION=global` in `.env` because Gemini 3 family is currently unavailable in `europe-west4` for this project (verified by direct probe — only `gemini-2.5-flash` works in europe-west4 for `kaide-ai-84019`). `Settings.vertex_location` literal widened to `Literal["europe-west4", "global"]`. **Cloud Run + GCS data residency remain in europe-west4**; only the inference endpoint routes through `global`.
- **Validator timeouts** bumped from 5s/8s to 15s/25s — the original budgets assumed warm caches; cold gRPC channel openings during lifespan startup were exceeding them.
- **`retention.py` SDK-availability fallback**: `google-cloud-aiplatform 1.91.0` no longer exposes `aiplatform.PublisherModel` at the top level (the API surface assumed by PHASE_1_SPEC §0.5 is gone). `_publisher_model_class()` now returns `None` when the SDK doesn't expose it; the validator logs a warning and continues. **Production ZDR enrollment is enforced via the env-var check in `_validate_vertex_compliance` — that load-bearing assertion is unchanged.**
- **Dockerfile.{api,worker}**: added `COPY fixtures/retention_v1.json` (was previously dispatcher-only; needed because the retention enforcer runs on every container's boot validator chain).

Next: Stage F.3 — Magic Moment ×3 against the demo fixtures.

---

## Stage F.3 halted — Celery + async-SQLAlchemy loop incompatibility (2026-05-21)

Stage F.2 PASSED at `dfaf079` with all 4 boot validators green. Attempted Stage F.3 against `fixtures/01_clean_excel.xlsx` (the only Excel fixture in the repo — `K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` is a narrative fixture from Master PRD §3.3 and was never built).

Job submitted to `/v1/intake/jobs` and accepted (status=pending), but stayed pending indefinitely. Worker logs revealed:

```
RuntimeError: Task <Task pending name='Task-2159'
  coro=<_drain_once() running at /app/packages/dispatcher/outbox_worker.py:95>>
  got Future <Future pending cb=[BaseProtocol._on_waiter_completed()]>
  attached to a different loop
```

Root cause: `packages/core/db/session.py:get_async_engine()` uses `@lru_cache(maxsize=1)`. Works for FastAPI lifespan (single loop), breaks under Celery (each `asyncio.run(...)` task has its own loop, but the cached engine's connection pool is bound to whichever loop opened it first). Every task hitting Postgres after the first one trips the cross-loop error.

Same bug fires from the dispatcher's `_drain_once` (beat-scheduled every 5 s) AND the ingest tasks (`_classify`, `_extract`, `_normalize`, `_validate`). The pipeline is structurally broken under Celery — Stage F.3 cannot pass without a code fix.

Halted and wrote `HUMAN_INTERVENTION_REQUEST.md` with three intersecting gaps:
1. SQLAlchemy + Celery loop incompatibility (real code bug; ~80 LOC fix across 3 modules).
2. Missing fixtures (K+N narrative file + 3 broken fixtures referenced by Stage F.3 + F.4 don't exist).
3. Missing `slack_post` outbox emit code path — Phase 5 spec wrote the dispatcher delivery side but no caller enqueues the row from the ingest pipeline.

Compose stack remains healthy; PRD path-1 patches at `98030d2` are unaffected. Vertex spend this session: ~$0.10 in validator probes; no pipeline run consumed credits.


---

## Stage F.3 re-run HALTED (post Phase 6.5 closure, 2026-05-21)

Re-run of Step 4 Stages F.3-F.5 against the Phase-6.5-fixed pipeline at commit `e99cfb4`. Pre-flight (F.1) and boot-validators (F.2) re-verified green. **Stage F.3 halted on Run 1 with four newly-surfaced defects.** Runs 2-3 not attempted.

### Pre-flight & boot validators — PASSED

- All 5 containers healthy after `docker compose up -d --wait`.
- `/v1/health` returns 200 with all 4 validators passing:
  - `vertex_ai_handshake` — flash_preview_responsive in `global` (7.6 s)
  - `postgres_alembic_head` — head=`0004_intake_review` (645 ms)
  - `un_locode_table_integrity` — 100,050 rows (1.3 s)
  - `vertex_ai_compliance_handshake` — `rrl_disabled=True zdr_enrolled=False models=3.1-flash-lite,3.1-pro-preview retention=raw7d/norm90d/arch180d/audit365d` (11.8 s)
- All 4 demo fixtures present and byte-identical to the regenerated set from the Phase 6.5 fix patch (commit `518232d`).

### F.3 Run 1 — FAILED

Submitted `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` via `POST /v1/intake/jobs` (prospect_id=demo_k_n_run_1, channel=#pilot-onramp). Job lifecycle:

| Elapsed | Status |
|---|---|
| 0 s | `pending` |
| 4 s | `extracting` (Stage 1 classify_format → Stage 2 excel extract, ~24 s window) |
| 28 s | `normalizing` (Stage 3 ensemble entered) |
| 5 min 23 s | EnsembleError raised at T=0.1 inside `_ensemble_for_lane` |
| 9 min+ | Job row still at `status='normalizing'` — failure-handler rollback (see Defect 6) |

### Defects surfaced (full detail in `HUMAN_INTERVENTION_REQUEST_V2.md`)

- **Defect 4 (compose):** No shared staging volume between `api` and `worker` containers. First job hit `FileNotFoundError` on the worker side. Patched in working tree (added named volume `staging` mounted at `/tmp/onramp` on both services); not committed.
- **Defect 5 (vertex_client cross-loop):** Same Defect-1 pattern as Phase 6.5's SQLAlchemy bug but in `packages/compliance/vertex_client.py`. The module-level `_client_cache` holds an httpx AsyncClient bound to the boot-validator loop, which forked workers inherit and use post-loop-close. First `_extract` task crashed with `RuntimeError: Event loop is closed`. Patched in working tree (removed cache; per-call genai.Client construction matching Phase 6.5 `make_async_engine` contract); not committed.
- **Defect 6 (rolled-back failure status):** `_normalize`'s `update_job_status(... "failed", ...)` is inside `session.begin()` which rolls back when the surrounding `raise` re-throws. Jobs that hit `EnsembleError` wedge at `status='normalizing'` permanently. Same pattern likely exists in `_extract`. **Not patched.**
- **Defect 7 (structural):** F.3.1 acceptance budget is 90 s. The K+N fixture is 50 lanes × N=3 Pro ensemble × ~3-10 s per call ≈ 7-25 minutes minimum. PHASE_6_5_SPEC §6.3 itself benchmarks 30-60 s for a **3-lane** fixture. The 90 s budget is mathematically incompatible with 50 lanes under sequential ensemble. Needs product decision (relax budget / parallelize / shrink fixture / demo-mode flag).

### F.4, F.5 — NOT ATTEMPTED

Stage F.4 (broken fixtures) and Stage F.5 (audit trail) are gated on F.3 passing. Both deferred until the four defects above are resolved.

### Vertex AI cost

Rough estimate **$3-7 USD** for the partial Run 1. Bulk of Pro calls returned 200 OK before the T=0.1 timeout cut the run short.

### Demo recording — NOT AUTHORIZED

The compose stack runs end-to-end through Stage 2 extraction. Stage 3 normalization is both structurally too slow for the F.3 budget and has a stuck-state defect on transient errors. Demo recording remains blocked.

Next: human review of `HUMAN_INTERVENTION_REQUEST_V2.md` and decisions on Defects 6 + 7.

---

## Step 4 V11 — F.4 PASSED, F.5 HALTED on Defect 22 (2026-05-31)

Phase 9 post-closure smoke at HEAD `45a024a`. Stack rebuilt clean on Phase 9 code; `/v1/health` healthy (4/4 validators). Pre-flight confirmed real fixture headers `origin`/`destination` match the pre-LLM scan label set, and the deployed image carries `_scan_cells_for_shape_violators` + `stage2.excel.v2`.

### Stage F.4 — broken_impossible_port_codes — ✅ PASS

Job `7c042249a37b40379301a45b9e7b6116`, `completed` in 42 s. Defect 21 closed LIVE: with Flash returning only clean lanes (V10 behaviour), the deterministic pre-LLM scan still lifted 2 shape-violators with real coords — `A4` `ZZ@ZZ` (origin) + `B6` `QQ@QQ` (destination) — both emitting canonical `port_unknown_unlocode` R1 rejections with full Phase 6.9 provenance. `prompt_version=stage2.excel.v2`, `cell_count=36`. lane_ids `shape_violator_Rates_4/6` confirm the deterministic path fired independent of Flash. Row accounting: 2 clean→lanes, 1 shape-valid/unresolved→flagged (`port_obfuscation_unresolved`, Phase 7 §6.1.3 carve-out, unchanged), 2 violators→rejected. No `INVALID_PORT_CODE`.

### Stage F.5 — audit trail — ❌ HALT (Defect 22)

Auth gating OK (no-auth 403; admin-token + fake job 404). Audit **data correct**: 4 rows (`classified/extracted/normalized/validated`, `actor=worker`, `actor_principal=pipeline-task`, payload + ts present, no PII). But `GET /internal/v1/audit/<bare-hex job_id>` returns **HTTP 422** — `response_model=list[AuditLogEntry]` (Phase 4 §3.1) rejects the worker-written vocabulary (`actor="worker"` ∉ {system,operator,external_webhook}; `action="classified"` ∉ the `*_complete` AuditAction set). Pre-existing Phase 4↔Phase 7 §6.3 schema drift, NOT a Phase 9 change (audit.py / audit model / tasks.py absent from the Phase 9 diff); first exercised here because F.5 was never reached before. Full analysis + fix options in `HUMAN_INTERVENTION_REQUEST_V11.md`.

### Vertex AI cost

< $1 (one 36-cell Flash extraction + small Pro normalization pass). Well under the $5 ceiling.

### Demo recording — NOT AUTHORIZED

F.4 passed but F.5 is blocked by Defect 22. Demo gated until the audit-schema reconciliation lands and F.5 re-runs green against the existing BPC job (no new Vertex spend needed).

Next: human decision on Defect 22 (Option A/B/C in `HUMAN_INTERVENTION_REQUEST_V11.md`), patch + unit tests, re-run F.5 only.

---

## Step 4 V11.5 — F.5 PASSED (Defect 22 closed) — ALL STAGE F GREEN (2026-05-31)

Phase 9.1 reconciled the audit read-model (`packages/core/models/audit.py:AuditLogEntry`) to the live pipeline writer (Phase 7 §6.3): `actor=Literal["worker"]`, `AuditAction` = `{classified, extracted, normalized, validated, extract_failed, normalize_failed, validate_failed}` — the exact `OnrampAuditLog.action` write surface (success + `_commit_failure` failure stages). The dead Phase 4 §3.1 `*_complete` long-forms and `{system,operator,external_webhook}` actor set are deleted (single vocabulary, no duplication). Commit `4d5c239`.

**Writer-surface discovery (load-bearing):** the sole `OnrampAuditLog` writer is `tasks.py:_audit_row`. `ingress_received` lives only in an outbox payload (no-op delivery), never an audit row, so it is intentionally absent. **Access-log twin: no drift** — `OnrampAccessLog` has no row writer and no reader endpoint; the only emitted `route` (`/internal/v1/audit/{id}`) is already in `AuditRoute`. `AccessLogEntry` left untouched.

### Stage F.5 — audit trail — ✅ PASS (re-run, no new Vertex spend)

api container rebuilt on the reconciled model (`/v1/health` healthy). Against the existing V11 BPC job `7c042249a37b40379301a45b9e7b6116` (4 audit rows already in DB):
- no-auth → **403** ✅; admin-token + fake job → **404** ✅
- **real-job audit → HTTP 200** ✅ (the V11 blocker, resolved)
- 4 entries (`classified, extracted, normalized, validated`), `actor=worker` / `actor_principal=pipeline-task`, all 6 fields, **no PII**.

### Regression lock

`tests/unit/test_audit_models.py`: every live action (7 values) validates through the read-model; an invalid action still rejects; the stale Phase 4 vocabulary no longer validates. Unit 161 passed, integration 11 passed/12 infra-skipped; ruff + mypy --strict clean on the model.

### Stage F final standing

| Stage | Verdict | Version |
|-------|---------|---------|
| F.3 (K+N happy path) | ✅ | V7 |
| BNR (broken_no_rates) | ✅ | V9 |
| BME (broken_malformed_edifact) | ✅ | V9 |
| F.4 (broken_impossible_port_codes) | ✅ | V11 |
| F.5 (audit trail) | ✅ | V11.5 |

### Vertex AI cost

≈ **$0** — F.5 reads existing audit data; no LLM calls. Cumulative Sprint 2 ≈ $10–15.

### Demo recording — ✅ AUTHORIZED

All 22 defects across Sprint 2 resolved. Every Stage F gate green. Demo recording authorized for the Vidyard session with Isaac.
