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
