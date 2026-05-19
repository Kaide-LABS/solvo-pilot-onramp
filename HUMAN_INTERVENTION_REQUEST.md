# Human Intervention Required

Run started: 2026-05-19
Stage: 0 (env readiness) — halted before Stage 1
Failure mode: No `.env` file, no Slack app, no GCS bucket, and the active gcloud project is a Google AI Studio `gen-lang-client-*` auto-project rather than a real Vertex AI tenant (the Matta-debug failure mode).

---

## What I tried

1. `ls .env` → `No such file or directory`. The repo ships only `.env.example` with 13 Phase-1 vars; Phase 5/6 added Slack + GCS + admin-token vars that have **no corresponding rows** in the example.
2. `gcloud config get-value project` → `gen-lang-client-0754692302`.
3. `gcloud projects describe gen-lang-client-0754692302 --format="value(projectNumber,lifecycleState)"` → `8822384086  ACTIVE` (project exists, but…)
4. `gcloud ai models list --region=europe-west4 --project=gen-lang-client-0754692302` → `Listed 0 items.` (consistent with AI Studio auto-project behavior — Vertex AI SDK calls *may* route through the Global generative endpoint, but regional europe-west4 binding required by ULTIMATE_PRD §3.2 is unreliable on this project type).
5. `gcloud services list --enabled --project=gen-lang-client-0754692302` → both `aiplatform.googleapis.com` AND `generativelanguage.googleapis.com` are enabled. Having both is the AI-Studio dual-mode signature.
6. No Slack OAuth app installed for this workspace. No `xoxb-*` token in the shell environment.
7. No `solvo-onramp-outputs-*` bucket exists in any project this account can list.

---

## Why this needs human judgment

Five separate provisioning steps are required, each of which involves Hafeedh-level credentials, billing, contracts, or workspace administration:

1. **Provision a real Vertex AI project** (NOT a `gen-lang-client-*` auto-project). This is the Matta-precedent gotcha the Step-4 prompt explicitly flags. The current project ID `gen-lang-client-0754692302` will fail Stage 1.4 hard-halt even if every other env var is filled in.
2. **Enroll the new GCP organization in the Vertex AI Zero Data Retention (ZDR) program.** This is a contract-level commitment with Google (per PHASE_1_SPEC §0.5 + `docs/compliance_setup.md`), not an SDK call. Required for `VERTEX_AI_ZDR_ENROLLED=true` in production.
3. **Install the Slack app** in a Kaide test workspace (or the Solvo engagement workspace once contracts permit). This generates the `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` for the Phase 5 webhook.
4. **`terraform apply infra/terraform/`** against the new GCP project to create the Cloud SQL, Memorystore, GCS buckets, and Cloud Run services. The Phase 6 deploy is gated on this — without it there's nothing to smoke-test except the local docker-compose stack.
5. **Resolve the env-var nomenclature mismatch** between the Step-4 prompt and the build's Settings class. The prompt's verification script uses `GCP_REGION`, `DATABASE_URL`, `VERTEX_AI_DATA_LOGGING_DISABLED`, `ADMIN_TOKEN`, `CLOUD_STORAGE_BUCKET`. The build uses `VERTEX_LOCATION`, `POSTGRES_DSN_ASYNC`/`SYNC`, `VERTEX_AI_ZDR_ENROLLED`, `INTERNAL_ADMIN_TOKEN`, `GCS_BUCKET_OUTPUTS`/`GCS_ARCHIVE_BUCKET`. **Either** the prompt updates to call the build's names, **or** Settings + `.env.example` get aliased — but the smoke-test verification script can't run as written.

I cannot auto-resolve any of these without crossing scope: provisioning a new GCP project costs money, agreeing to GCP terms, possibly billing-account binding; installing a Slack app changes workspace state and exposes credentials; running `terraform apply` to production creates real cloud resources; and renaming Settings is a code change that should not happen mid-smoke-test.

---

## What I'd recommend (recommendation, not auto-applied)

**Path A — Local-only smoke (fast, covers Stages 2 + 3 + 4 + 5 against the local docker-compose stack):**

1. Create a real Vertex AI project under the Kaide GCP org. Bind it to the existing billing account. Don't use an AI Studio project.
   ```bash
   # Replace gen-lang-client-* with a hand-named project
   gcloud projects create kaide-solvo-onramp-dev --organization=<KAIDE_ORG_ID>
   gcloud billing projects link kaide-solvo-onramp-dev --billing-account=<BILLING_ACCOUNT>
   gcloud config set project kaide-solvo-onramp-dev
   gcloud auth application-default login
   gcloud auth application-default set-quota-project kaide-solvo-onramp-dev
   gcloud services enable aiplatform.googleapis.com --project=kaide-solvo-onramp-dev
   ```
2. Install a Slack app in a dedicated test workspace (e.g. `kaide-demo.slack.com`). Capture `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` from the app's "Install App" + "Basic Information" pages.
3. Create a one-off europe-west4 GCS bucket for local-staging smoke testing:
   ```bash
   gcloud storage buckets create gs://kaide-solvo-onramp-dev-staging \
     --location=europe-west4 --project=kaide-solvo-onramp-dev
   gcloud storage buckets update gs://kaide-solvo-onramp-dev-staging \
     --lifecycle-file=- <<EOF
   {"rule":[{"action":{"type":"Delete"},"condition":{"age":7,"matchesPrefix":["raw/"]}}]}
   EOF
   ```
4. Write `.env` from the corrected template below (uses **build-side names**, not the prompt's names):
   ```dotenv
   ENVIRONMENT=development
   RELEASE_VERSION=0.1.0-dev
   GCP_PROJECT_ID=kaide-solvo-onramp-dev
   VERTEX_LOCATION=europe-west4
   POSTGRES_USER=onramp
   POSTGRES_PASSWORD=onramp
   POSTGRES_DB=onramp
   POSTGRES_DSN_ASYNC=postgresql+asyncpg://onramp:onramp@postgres:5432/onramp
   POSTGRES_DSN_SYNC=postgresql+psycopg2://onramp:onramp@postgres:5432/onramp
   EXPECTED_ALEMBIC_HEAD=0004_intake_review
   REDIS_URL=redis://redis:6379/0
   VERTEX_AI_ZDR_ENROLLED=false           # dev — leave false; prod requires the contract step
   INTERNAL_ADMIN_PRINCIPAL=ops@kaide.so
   INTERNAL_ADMIN_TOKEN=<openssl rand -hex 32 output>
   SLACK_SIGNING_SECRET=<from Slack app config>
   SLACK_BOT_TOKEN=<xoxb-... from Slack app install>
   GCS_BUCKET_OUTPUTS=kaide-solvo-onramp-dev-staging
   GCS_SIGNER_SERVICE_ACCOUNT=<service-account-with-token-creator-role>@kaide-solvo-onramp-dev.iam.gserviceaccount.com
   ENABLE_WEBHOOK_CALLBACKS=false
   GCS_ARCHIVE_BUCKET=kaide-solvo-onramp-dev-archive
   ARCHIVE_AGE_DAYS=90
   RETENTION_CONFIG_PATH=fixtures/retention_v1.json
   ```
5. Re-run this Step-4 prompt. Stage 0 should pass; Stages 1–5 should then run against the local docker-compose stack with real Vertex calls.

**Path B — Full Cloud Run smoke (slow, requires §3.10 contract steps complete):**

1. Steps A.1–A.3 above.
2. ZDR enrollment with Google (out-of-band; per `docs/compliance_setup.md` it's a 1–2-week process). Until that lands, `VERTEX_AI_ZDR_ENROLLED=true` in production fails honestly.
3. `terraform apply` against `infra/terraform/`.
4. `gcloud builds submit --config=cloudbuild.yaml`.
5. `infra/scripts/smoke_check.sh <cloud-run-url>`.
6. Re-run Step-4 with `SOLVO_DEPLOYED_URL` set.

Path A is the right next step. Path B is mandatory before demo recording on a production-shaped deployment, but Path A unblocks the Vidyard walkthrough using docker-compose + screen recording (the typical FDE-sidecar demo pattern).

---

## Additional recommendation: env-var nomenclature drift

The Step-4 prompt and the codebase Settings disagree on six variable names (full table in `SMOKE_TEST_LOG.md` §Milestone 0.2). The prompt was likely written from generic GCP-conventions memory; the build pins names that map back to Phase 1 spec literals. The right fix is to align the prompt — the build's names are load-bearing (they appear in terraform, in tests, in docs/compliance_setup.md). I haven't auto-edited the prompt; that decision is Hafeedh's.

`.env.example` should also be expanded to cover all Phase 5–6 settings (Slack, GCS buckets, signer SA, admin token). Right now it's frozen at Phase 1.

---

## Resume instructions

After fixing the above:

```bash
cd c:/Users/hp/Solvo_demo
# Verify the new project + .env
gcloud config get-value project
test -f .env && echo "env present"
# Delete the intervention marker
git rm HUMAN_INTERVENTION_REQUEST.md
git commit -m "ops: resolved Step-4 intervention — new Vertex project + .env"
# Re-run Step 4
```
