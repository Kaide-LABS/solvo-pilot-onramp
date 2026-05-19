# PHASE 6 SPEC — Solvo Pilot Onramp Sprint 2

**Output of Step 3B (Phase 5 review approved, Phase 6 blueprinted — sprint terminal).** Consumes: `ULTIMATE_PRD.md` §3.2 (region binding), §3.7 (deployment topology), §3.10 (compliance posture, retention windows), `Solvo_Master_PRD.md` §5 (Cloud Run targets), `docs/modernization_log.md`, `PHASE_5_SPEC.md`. Feeds: Step 3A (Codex build of Phase 6) → Step 3B final approval → `BUILD_COMPLETE.md`.

---

## §0 — PHASE PLAN HEADER

**This is Phase 6 of 6 phases in the Sprint 1 build — the final phase.** Phase 5 (Slack + intake + dispatcher + Phase 4 wiring closure) was approved at SHA `6f1d01c`. Approval of Phase 6 triggers `BUILD_COMPLETE.md`, not a Phase 7 spec.

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake. |
| ✅ Phase 2 | 8–20 | Ratesheet schemas, Stage 1 classifier, Stage 2 Excel extractor. |
| ✅ Phase 3 | 20–28 | Stage 3 N=3 Pro ensemble, UN/LOCODE + WCO HS6 reference load. |
| ✅ Phase 4 | 28–36 | EDIFACT, Stage 4 rules engine, audit trail, `/internal/v1/audit`. |
| ✅ Phase 5 | 36–48 | Slack + intake + dispatcher + Phase 4 wiring closure. |
| **Phase 6** | 48–60 | **Cloud Run europe-west4 deployment of three services (api, worker, dispatcher-beat), Cloud SQL Postgres + Memorystore Redis provisioning, GCS bucket + 7-day lifecycle, 90-day Postgres archive job, terraform / gcloud scripts, deploy smoke tests, all 9 acceptance criteria from §3.7 verified, `BUILD_COMPLETE.md`.** |

---

## §1 — FILES ADDED OR MODIFIED

**Added:**

```
infra/
├── README.md                                  # how to bootstrap a fresh GCP project
├── terraform/
│   ├── main.tf                                # provider + project pin
│   ├── network.tf                             # VPC + Serverless VPC Access connector
│   ├── cloud_sql.tf                           # Postgres 17 instance + database + user
│   ├── memorystore.tf                         # Redis 7.4 instance
│   ├── gcs.tf                                 # solvo-onramp-outputs bucket + 7d lifecycle
│   ├── cloud_run.tf                           # api + worker + dispatcher-beat services
│   ├── iam.tf                                 # service-account bindings (3 SAs)
│   ├── secrets.tf                             # Secret Manager refs (Slack, ZDR flag, DB pwd)
│   ├── variables.tf                           # project_id, region (locked europe-west4)
│   └── outputs.tf                             # Cloud Run URLs, Cloud SQL connection name
├── scripts/
│   ├── deploy.sh                              # one-shot terraform apply + image push
│   ├── smoke_check.sh                         # post-deploy curl /v1/health/ready against URL
│   ├── bootstrap_zdr.sh                       # one-shot ops checklist (writes ZDR env var ref)
│   └── archive_90day.py                       # nightly Cloud Run Job: archive 90d-old normalized
└── cloudbuild.yaml                            # gcloud builds submit pipeline (build → push)

apps/api/routes/
└── health.py                                  # (modified) add /v1/health/ready/cloudrun probe

packages/lifecycle/
├── __init__.py
├── archive.py                                 # rolls normalized_payload to GCS Coldline @ 90d
└── retention_enforcer.py                      # asserts retention windows match §3.10.3 at boot

tests/integration/
├── test_cloud_run_smoke.py                    # gated by SOLVO_DEPLOYED_URL env var
└── test_lifecycle_archive.py                  # archive job round-trip against in-process GCS fake

tests/unit/
├── test_retention_enforcer.py                 # one test per retention class (raw/normalized/audit)
└── test_archive_logic.py                      # pure-Python archive selection logic

docs/
├── deployment_runbook.md                      # what ops does to deploy / rollback
└── compliance_attestation.md                  # ISO 27001 / GDPR posture summary (audit-ready)
```

**Modified:**

- `Dockerfile.api`, `Dockerfile.worker` — add a third `Dockerfile.dispatcher` (or extend worker with a `--beat` flag). Switch base image to `python:3.13-slim-bookworm` and add `--no-install-recommends` for size.
- `apps/api/main.py` — register Cloud Run readiness probe `/v1/health/ready/cloudrun` (lighter than the boot validator readiness; checks only DB + Redis ping, not Vertex AI handshake — Cloud Run probe budgets are short).
- `apps/worker/celery_app.py` — bind beat schedule for `tasks.dispatcher.drain_outbox` (every 5 s) AND `tasks.lifecycle.archive_old` (daily at 02:00 Europe/Amsterdam).
- `packages/core/settings.py` — `expected_alembic_head` stays at `0004_intake_review` (Phase 6 introduces no schema changes); add `gcs_archive_bucket` + `archive_age_days = 90`.
- `pyproject.toml` — no new top-level runtime deps. Dev: add `google-cloud-run` for the smoke test fixture (optional extra).
- `docker-compose.yml` — add a `dispatcher-beat` service mirroring worker's image with `--beat` argument.
- `CHANGELOG.md` — final entry: "Phase 6 — Cloud Run deployment + sprint close".
- `data/_generate.py` — gated by `--prod` flag to refuse running against the prod env (already idempotent; this is paranoia).

---

## §2 — PIP DEPENDENCIES

No new top-level runtime dependencies. The smoke-test fixture optionally uses `google-cloud-run` but only inside `tests/integration/` (which is skipped by default). `pyproject.toml` may add it under `[project.optional-dependencies] integration`.

---

## §3 — PYDANTIC SCHEMAS (Phase 6)

```python
# packages/core/models/lifecycle.py

class ArchiveCandidate(BaseModel):
    """One row selected by retention_enforcer for archive."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=64)
    completed_at: datetime
    archive_blob_name: str = Field(min_length=4, max_length=256)
    source_table: Literal["onramp_outputs", "onramp_audit_log"]


class RetentionAssertion(BaseModel):
    """Boot-time assertion that the live config respects §3.10.3 windows."""

    model_config = ConfigDict(extra="forbid")

    raw_upload_retention_days: Literal[7]            # GCS lifecycle, pinned
    normalized_output_retention_days: Literal[90]    # Postgres → archive at 90
    archived_output_ttl_days: Literal[180]           # Coldline retention floor
    audit_log_retention_days: Literal[365]           # ISO 27001 floor, never below
```

No new BaseModel may compute, derive, or carry a price/rate/margin field. Anti-Replication restated.

---

## §4 — FASTAPI ROUTE SIGNATURES (Phase 6)

### 4.1 `GET /v1/health/ready/cloudrun` (`apps/api/routes/health.py`)

```python
@router.get("/ready/cloudrun", response_model=HealthResponse)
async def cloudrun_readiness(request: Request) -> JSONResponse:
    """Cloud Run readiness — DB + Redis ping only (≤ 3 s budget).

    Distinct from /v1/health/ready (which inspects the full four-validator
    boot result). Cloud Run's default probe is aggressive; this lighter path
    avoids cold-start eviction.
    """
```

- Returns 200 when (a) the connection pool can `SELECT 1` against Postgres within 500 ms AND (b) Redis `PING` returns within 500 ms.
- Returns 503 otherwise.
- Does NOT re-run Vertex AI handshake or §3.10.5 compliance (those ran at boot).

No other new routes in Phase 6. All operator-grade surfaces are Phase 5.

---

## §5 — ALEMBIC MIGRATION

**None in Phase 6.** Schema stays at `0004_intake_review`. Production deployment runs `alembic upgrade head` once at Cloud Run service startup via the `cloudbuild.yaml` migration step — same migration, just executed against Cloud SQL.

---

## §6 — IMPLEMENTATION LOGIC FLOW

### 6.1 Terraform — `europe-west4` Pinned Everywhere

`variables.tf`:

```hcl
variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "europe-west4"
  validation {
    condition     = var.region == "europe-west4"
    error_message = "Region is locked to europe-west4 per ULTIMATE_PRD §3.2."
  }
}
```

`network.tf`: one VPC, one subnet in europe-west4, one Serverless VPC Access connector for Cloud Run → Cloud SQL private IP.

`cloud_sql.tf`: Postgres 17 instance, regional HA disabled (cost — single-zone, daily backup), `database_flags = [{ name = "max_connections", value = "200" }]`. Private IP only. Backup retention 7 days.

`memorystore.tf`: Redis 7.4, Standard tier, single-zone. 1 GB memory cap (Sprint 2 workload is sub-100 MB).

`gcs.tf`: bucket `solvo-onramp-outputs` with location `EU` (multi-region for redundancy) and a `lifecycle_rule { condition { age = 7 } action { type = "Delete" } }` on the **raw uploads** prefix. The normalized-output prefix uses a different lifecycle rule: `90 day → Coldline`, `180 day → Delete`.

`cloud_run.tf`: three services — `solvo-onramp-api`, `solvo-onramp-worker`, `solvo-onramp-dispatcher-beat`. Each uses its own service account (least privilege). All bind to the VPC connector. `region = "europe-west4"` everywhere.

`iam.tf`: three service accounts.
- `api-sa` → `roles/cloudsql.client`, `roles/redis.editor`, `roles/aiplatform.user`, `roles/secretmanager.secretAccessor`, `roles/storage.objectViewer` (read normalized blobs), `roles/iam.serviceAccountTokenCreator` for the signed-URL signer.
- `worker-sa` → same as api-sa plus `roles/storage.objectAdmin` (write blobs).
- `dispatcher-sa` → `roles/cloudsql.client`, `roles/redis.editor`, `roles/secretmanager.secretAccessor`, `roles/storage.objectAdmin`.
- A dedicated `gcs-signer-sa` → `roles/iam.serviceAccountTokenCreator` chain for signed-URL generation; `Settings.gcs_signer_service_account` points to this principal.

`secrets.tf`: Secret Manager entries for `slack_signing_secret`, `slack_bot_token`, `postgres_password`, `internal_admin_token`. Cloud Run revisions mount these as `--set-secrets`. `VERTEX_AI_ZDR_ENROLLED=true` is set directly on Cloud Run env (not a secret — a non-sensitive boolean) once the ZDR enrollment is confirmed (ops checklist `bootstrap_zdr.sh`).

### 6.2 Image Build (`cloudbuild.yaml`)

```yaml
steps:
  - id: build-api
    name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "europe-west4-docker.pkg.dev/$PROJECT_ID/solvo/api:$SHORT_SHA",
           "-f", "Dockerfile.api", "."]
  - id: build-worker
    name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "europe-west4-docker.pkg.dev/$PROJECT_ID/solvo/worker:$SHORT_SHA",
           "-f", "Dockerfile.worker", "."]
  - id: build-dispatcher
    name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "europe-west4-docker.pkg.dev/$PROJECT_ID/solvo/dispatcher:$SHORT_SHA",
           "-f", "Dockerfile.dispatcher", "."]
  - id: push
    name: gcr.io/cloud-builders/docker
    args: ["push", "europe-west4-docker.pkg.dev/$PROJECT_ID/solvo/--all-tags"]
  - id: migrate
    name: europe-west4-docker.pkg.dev/$PROJECT_ID/solvo/api:$SHORT_SHA
    entrypoint: alembic
    args: ["upgrade", "head"]
  - id: deploy-api
    name: gcr.io/cloud-builders/gcloud
    args: ["run", "deploy", "solvo-onramp-api",
           "--image", "europe-west4-docker.pkg.dev/$PROJECT_ID/solvo/api:$SHORT_SHA",
           "--region", "europe-west4",
           "--no-allow-unauthenticated"]
  # ... worker + dispatcher deploys identical
```

Migration runs **between push and deploy**. Cloud Run will not flip traffic to a revision built against a migration that hasn't applied — manual ordering guarantees this.

### 6.3 90-day Archive Job (`packages/lifecycle/archive.py`)

```python
async def archive_completed_jobs(*, age_days: int, session: AsyncSession, settings: Settings) -> int:
    """Select onramp_outputs rows older than age_days (default 90), upload their
    normalized_payload JSON to gs://{gcs_archive_bucket}/jobs/{job_id}.json.gz,
    then DELETE the row from onramp_outputs.

    Idempotent: rows already archived (gs:// blob exists) are skipped.
    onramp_audit_log rows are NEVER archived — they live forever per §3.10.3.
    Returns the count of jobs archived in this run.
    """
```

Wired as a Celery task (`tasks.lifecycle.archive_old`) with a daily beat schedule. The archive bucket has a 180-day Coldline lifecycle (per `Settings.archived_output_ttl_days = 180`).

### 6.4 Retention Enforcer (`packages/lifecycle/retention_enforcer.py`)

Added to the §3.10.5 boot validator as a sub-check (validator 4 extended). Loads `RetentionAssertion` from `settings.retention_config_path` (JSON) and asserts the four Literal-pinned values match the live GCS lifecycle rules + Cloud SQL backup retention. Mismatches fail boot with exit code 4.

This makes accidental relaxation of the §3.10.3 retention floors a fail-fast condition.

### 6.5 Cloud Run Readiness vs Boot Validators

The boot validators (Phase 1) are invariant. Phase 6 adds a **lighter** Cloud Run readiness probe `/v1/health/ready/cloudrun` because the full boot validator path takes 8–15 s and Cloud Run's default probe deadline is 4 s. The lighter path checks only DB + Redis pings. Cloud Run uses this for traffic gating; the boot validators still gate the **container startup** itself via the lifespan handler.

### 6.6 Deploy Smoke Tests (`tests/integration/test_cloud_run_smoke.py`)

Gated by `SOLVO_DEPLOYED_URL` env var:

- `GET /v1/health` → 200 with `status="healthy"` and `region="europe-west4"`.
- `GET /v1/health/ready/cloudrun` → 200 within 3 s.
- `POST /v1/intake/jobs` with `fixtures/01_clean_excel.xlsx` → 202.
- Poll `GET /v1/intake/jobs/{id}` until `status="completed"` or 120 s timeout.
- `GET /v1/intake/jobs/{id}/result-url` → 200 with a signed URL whose `expires_at - now < 901 s`.
- Internal audit route returns 403 without the bearer, 200 with it.

These are run **once after deploy** in `scripts/smoke_check.sh`. The 9-criterion suite below assembles these into the build-complete attestation.

---

## §7 — CROSS-PHASE INTEGRATION REQUIREMENTS

- **Boot validators (Phase 1).** All four still gate container startup. Validator 4 now also checks `RetentionAssertion` per §6.4.
- **§3.10.3 retention windows.** GCS lifecycle rules and Cloud SQL backup retention must match the four Literal-pinned values in `RetentionAssertion`. Terraform pins them; the boot validator double-checks them.
- **Phase 5 dispatcher.** The `tasks.dispatcher.drain_outbox` task continues to run every 5 s. Phase 6 adds `tasks.lifecycle.archive_old` to the beat schedule (daily 02:00 Europe/Amsterdam).
- **All prior tests (140) still pass.** Phase 6 adds infra files and one new endpoint; no schema, no model, no task name changes.
- **No new LLM call sites.** Phase 6 is pure infra + lifecycle.
- **Anti-Replication.** Cloud Run deployment surfaces zero new code that touches pricing.
- **No exposed external endpoints beyond what Phase 5 shipped.** `--no-allow-unauthenticated` on all three Cloud Run services. IAP / OAuth proxy is the access path for human ingress; Slack webhook is the only authenticated public surface (HMAC-gated).

---

## §8 — PHASE 6 ACCEPTANCE CRITERIA (the 9-criterion suite)

These are the sprint-terminal criteria. ALL must pass for approval. They are captured verbatim in `BUILD_COMPLETE.md` upon approval.

1. **Container startup boot validators pass on Cloud Run.** `gcloud run services logs read solvo-onramp-api` shows all four validators succeeded (`vertex_ai_handshake`, `postgres_alembic_head`, `un_locode_table_integrity` count ≥ 100k, `vertex_ai_compliance_handshake`). Exit codes 1–4 verified by deliberately misconfiguring each in a dev project.
2. **End-to-end pipeline runs against a real fixture on Cloud Run.** Submit `01_clean_excel.xlsx` via `POST /v1/intake/jobs`, poll until `completed`, fetch the result-url, download and validate against `NormalizedRatesheet`.
3. **Conformal scoring fires on a no-majority synthetic.** Pre-seed a job where Stage 3 returns 1-1-1; observe `correction_triggered=1` in the audit_log row and `clarifications >= 1`.
4. **EDIFACT path produces lanes.** Submit `06_edifact_pricat.edi` and verify ≥ 1 lane in the output JSON.
5. **Signed URL TTL = 900 s exactly.** Inspect the returned `expires_at - now()` from `/v1/intake/jobs/{id}/result-url`.
6. **Slack signature verification.** Hit `POST /v1/webhooks/slack` with a missing signature → 401; with a 6-minute-old timestamp → 403.
7. **`/internal/v1/audit/{job_id}` gated.** Without bearer → 403. With bearer → 200 + an `onramp_access_log` row appears within 30 s (after dispatcher drains the outbox).
8. **Retention assertion.** Boot validator 4 fails (exit 4) when the terraform-applied GCS lifecycle rule is mutated out of band to `age = 30` on raw uploads (instead of 7). Re-applying terraform restores boot.
9. **All 140 unit tests + integration suite pass.** `pytest tests/unit` returns 140 pass, `SOLVO_DEPLOYED_URL=https://… pytest tests/integration` returns 0 failures.

Additional non-counted but mandatory checks:

- `ruff check .` returns 0.
- `mypy --strict packages/core packages/compliance packages/ingest packages/reference packages/slack packages/storage packages/dispatcher packages/lifecycle apps/api` returns 0.
- `gitleaks detect --no-banner --no-git --source .` returns zero findings.
- Anti-Replication grep returns zero matches.
- §3.10.5 compliance handshake passes in production (`VERTEX_AI_ZDR_ENROLLED=true`).

---

## §9 — EXPLICIT NON-GOALS FOR PHASE 6

The executor MUST NOT implement the following in Phase 6:

- **No new pipeline features.** Phase 6 ships exactly what Phases 1–5 produced, on Cloud Run. Any "while we're here" pipeline change is scope creep and a HARD KILL.
- **No schema migrations.** `0004_intake_review` is the terminal head.
- **No new LLM call sites or model changes.** Phase 6 introduces zero `generate_content` calls.
- **No widening of the Phase 3 (N=3) or Phase 4 (N=2) temperature pins.** Triples remain locked.
- **No new public endpoints.** Cloud Run services run with `--no-allow-unauthenticated`. The only public surface is `POST /v1/webhooks/slack` (HMAC-gated).
- **No demo recording, no Vidyard upload, no outreach automation.** Per the demo handoff line below, Hafeedh records the 4–5 minute Vidyard walkthrough manually after Phase 6 approval.
- **No multi-region or DR replication.** Cloud SQL stays single-zone; this is a pilot. Phase N+1 (out of scope) may revisit.
- **No production billing alarms, paging integrations, dashboards.** Out of scope for the pilot; ops adds them manually per the deployment runbook.
- **No customer-facing branding, no public web UI.** The frontend is `outreach_bundle.md` + the Vidyard recording; the API is the only deliverable surface.
- **No CI/CD GitHub Actions workflows beyond what Phase 1 set up.** Cloud Build (`cloudbuild.yaml`) is the deploy automation; GitHub Actions remain for lint/test only.
- **No POMDP, no Bayesian RL, no value iteration, no Constrained MDP, no belief-state inference, no active learning, no price/rate/margin/recommendation/market-clearing logic.** (Anti-Replication invariant — final restatement for the sprint.)

---

## §10 — SPECIAL CASE: `BUILD_COMPLETE.md` ON APPROVAL

When Step 3B approves Phase 6, **do not generate `PHASE_7_SPEC.md`**. Instead, write `BUILD_COMPLETE.md` containing:

- Confirmation: all 6 phases built and approved with the corresponding `chore: Phase N review approved` SHAs.
- Full 9-criterion acceptance suite results from §8 above.
- Cloud Run deployment URL (from `terraform output cloud_run_api_url`).
- GitHub commit SHA at sprint completion (the `chore: Phase 6 review approved` SHA).
- Nia index ID (`9ae50d60-0de8-4f58-b755-2a118fab6651`).
- Citation re-verification audit summary: PHASE_2_SPEC §0.5 (Bai PROVISIONAL), PHASE_4_SPEC §0.5 (Ugare PROVISIONAL + Wan PROVISIONAL).
- Handoff to Hafeedh: record the 4–5 minute Vidyard walkthrough per `outreach_bundle.md`.

Commit `BUILD_COMPLETE.md` with message: `docs: Sprint 2 build complete — 6 phases shipped (Sprint 2 close)`.

---

*End of Phase 6 Spec. Next: Step 3A executes against this spec; Step 3B reviews and writes `BUILD_COMPLETE.md` (no Phase 7 spec).*
