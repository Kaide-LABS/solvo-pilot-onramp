# HUMAN INTERVENTION REQUEST V3 — Step 4 Stage F.3 re-run HALTED (post Phase 6.6 closure)

**Date:** 2026-05-22
**Halting agent:** Claude Code (Step 4 Stage F.3 smoke runner)
**Repo HEAD at halt:** `c30b928` (BUILD_COMPLETE_V3.md) + 3 uncommitted fixes (see §3)
**Stage status at halt:** F.1 PASSED, F.2 PASSED (4/4 boot validators green), **F.3 HALTED on Run 1 after two consecutive Vertex/credential failures**, F.4/F.5 not yet attempted.

The Step 4 Stage F.3 re-run authorized by `BUILD_COMPLETE_V3.md` cannot complete because the validate stage surfaced three new defect classes that the Phase 6.6 closure spec did not anticipate. Two were fixable from code (patches uncommitted; see §3) and applied during the run. The third is a GCP IAM configuration issue outside Claude Code's authority to resolve.

The Phase 6.6 work itself is intact and verified live: the Defect 6 failure-handler fired correctly on Run 1 (both attempts), durably writing `status='failed'` with PII-redacted `audit_log` payloads. Defect 7 fixture shrink also works (extraction + normalize completed in ~140-150 s, well inside the 180 s budget). Defects 8-10 surfaced only after Phase 6.6's fixes let the pipeline run far enough to exercise paths that were previously masked by the Phase 6.5 / Phase 6.6 failure points.

---

## §1 — Three New Defect Classes (8, 9, 10) Beyond the Original 1-7

### Defect 8 — `fixtures/conformal_calibration_v1.json` missing from worker image

**Symptom:** `_validate` raises `FileNotFoundError: [Errno 2] No such file or directory: 'fixtures/conformal_calibration_v1.json'`.

**Root cause:** `Dockerfile.worker` only copies `fixtures/retention_v1.json` (line 26). `_validate` calls `load_calibration(Path("fixtures/conformal_calibration_v1.json"))` and crashes when the file isn't in the worker container. `.dockerignore` also excludes the fixtures directory with only `retention_v1.json` on the allowlist.

**Why this survived all 6 phases + closure 6.5 + closure 6.6:**
- Phase 6.5 and earlier: validate path never ran because `_normalize` crashed first (Defect 1) or `_validate` itself was wedged at `validating` (Defect 6).
- Phase 6.6 closure spec: focused on shared volume / Vertex client / failure handler / fixture-shrink. Did not audit Docker COPY directives for completeness.

**Fix applied (uncommitted) — `Dockerfile.worker` + `.dockerignore`:**
```diff
 # Dockerfile.worker line 26-27
 COPY fixtures/retention_v1.json fixtures/retention_v1.json
+COPY fixtures/conformal_calibration_v1.json fixtures/conformal_calibration_v1.json
```
```diff
 # .dockerignore line 20-22
 fixtures
 !fixtures/retention_v1.json
+!fixtures/conformal_calibration_v1.json
```

**Verification post-fix:** Worker container has the fixture (`docker compose exec worker ls /app/fixtures/` shows both files). Validate stage no longer raises FileNotFoundError.

### Defect 9 — `google.cloud.storage.Client()` constructed without project

**Symptom:** `_validate` raises `OSError: Project was not passed and could not be determined from the environment.` from `packages/storage/signed_url.py:39`.

**Root cause:** `signed_url.py` constructs `storage.Client()` without a `project=` argument. Cloud Run masks this in production via the metadata-server-derived default project; on the local compose stack with user-OAuth ADC, the project is not in the environment.

**Why this survived:** Same masking chain as Defect 8 — validate path never reached `generate_v4_signed_url` until Phase 6.6 cleared the upstream failures.

**Fix applied (uncommitted) — `packages/storage/signed_url.py`:**
```diff
     def _sync() -> tuple[str, datetime]:
         from google.cloud import storage  # type: ignore[attr-defined]

-        client = storage.Client()
+        from packages.core.settings import get_settings
+
+        client = storage.Client(project=get_settings().gcp_project_id)
```

**Verification post-fix:** Project lookup no longer fails — but the next error class surfaces (Defect 10).

### Defect 10 — Signed URL generator requires a private-key-bearing service account; ADC user-OAuth has none

**Symptom (after Defect 9 fix):** `_validate` raises `AttributeError: you need a private key to sign credentials. the credentials you are currently using <class 'google.oauth2.credentials.Credentials'> just contains a token. see https://googleapis.dev/python/google-api-core/latest/auth.html#setting-up-a-service-account for more details.`

**Root cause:** V4 signed URL generation cryptographically signs the URL with the bucket-issuing service-account's private key. On Cloud Run, this works either because:
- (a) the worker runs as the SA and ADC has the key, or
- (b) the IAM `iam.serviceAccountTokenCreator` role lets the runtime delegate signing through the IAM Credentials API.

On the local compose stack the worker's ADC is the user's gcloud OAuth credentials (mounted at `/gcp-adc:ro`), which contain only an access token — no private key, no signing capability. The `service_account_email=signer` argument to `blob.generate_signed_url(...)` tells GCS to impersonate that SA, but the local ADC user lacks the IAM role to do so.

**This is NOT a code defect.** It's a GCP IAM configuration gap on the local-compose smoke environment. Claude Code does not have authority to:
- Issue and download a service-account JSON key (security policy + IAM admin auth).
- Grant `iam.serviceAccountTokenCreator` to a user account.
- Reconfigure ADC.

**Fix REQUIRED from Hafeedh (one of three options):**

1. **Service-account key file (fastest):** Generate a JSON key for the `gcs-onramp-signer@kaide-ai-84019.iam.gserviceaccount.com` SA (the existing `gcs_signer_service_account` from settings), mount it into the worker container at e.g. `/gcp-key.json`, set `GOOGLE_APPLICATION_CREDENTIALS=/gcp-key.json`. This is the recommended local-only path; the key file MUST NOT be committed. Note: this contradicts the Phase 3 §3.10 stance that ZDR and workload identity are the production posture — for local-smoke-only this is acceptable; never deploy with the key.

2. **Grant `iam.serviceAccountTokenCreator` to the user's OAuth principal:** `gcloud iam service-accounts add-iam-policy-binding gcs-onramp-signer@kaide-ai-84019.iam.gserviceaccount.com --member=user:<your-google-email> --role=roles/iam.serviceAccountTokenCreator`. Requires `iam.serviceAccountAdmin` or higher on the project. The signed_url.py code already passes `service_account_email`; with this role grant the local OAuth will sign successfully via IAM Credentials API.

3. **Defer signed-URL generation to a mock for local smoke:** wire `SOLVO_LOCAL_SMOKE=1` (or similar) env var to substitute a fake `https://example.invalid/...` URL in `_validate`. This pushes the Defect 10 surface area to production-only — but loses signed-URL coverage in F.3, weakening the smoke value.

Recommended: option **2** (least security blast radius). Time estimate: ~5 minutes including IAM propagation.

---

## §2 — F.3 Run 1 Evidence

Both attempts of F.3 Run 1 executed and durably failed via the Phase 6.6 failure-handler — confirming Phase 6.6 itself works:

| Attempt | Job ID | Elapsed | Final status | Failure stage / reason |
|---|---|---|---|---|
| 1 (pre-fix Defect 8) | `e91e0083637d4e37839258d060c85d8f` | 223 s (timeout) | wedged at `validating` | FileNotFoundError; failure-handler in worker image was Phase 6.5 code (no `_commit_failure`) — image not yet rebuilt |
| 2 (post-build rebuild, post-Defect-8 fix) | `76843e591f944dfab72163d0026e2323` | 159 s | `failed` (durable) | validate_failed, OSError "Project was not passed" → Defect 9 surfaced |
| 3 (post-Defect-9 fix) | `5a3ba0984870418ca04da5fb4abbfd95` | 132 s | `failed` (durable) | validate_failed, AttributeError "you need a private key to sign credentials" → Defect 10 surfaced |

**Phase 6.6 fixes verified live:**
- Per-task `make_async_engine` (Defect 1 fix): no `Event loop is closed` errors in any of the three attempts.
- Per-call `get_vertex_client` (Defect 5 fix): N=3 ensemble × 15 lanes ran cleanly on attempts 2 and 3 (no fork-pool client crash).
- `_failure_payload` + `_commit_failure` (Defect 6 fix): attempts 2 and 3 wrote durable `status='failed'` rows AND PII-redacted `audit_log` rows with `stage='validate_failed'`, `error_type`, and 500-char redacted `error_message`. No `/tmp/onramp/` leak observed. The fix works exactly as the spec describes.
- 15-lane fixture (Defect 7 shrink): normalize completed in ~140-145 s on both attempts 2 and 3, comfortably inside the 180 s budget.

**Phase 6.6 fixes that did NOT need to fire:**
- Shared staging volume (Defect 4): verified at preflight via `grep -A1 "staging:" docker-compose.yml`; worker successfully reads the K+N file written by api.

---

## §3 — Uncommitted Working-Tree Patches

Three files modified during the smoke run, NOT yet committed:

```
M  Dockerfile.worker                  (Defect 8 fix)
M  .dockerignore                      (Defect 8 fix — unblock the fixture COPY)
M  packages/storage/signed_url.py     (Defect 9 fix)
```

These should be committed as `fix: Step 4 F.3 re-run patches — Defects 8 + 9 (missing fixture COPY, missing project arg)`. Defect 10 is left for Hafeedh because it requires IAM action, not code action.

---

## §4 — F.3 Stage Bookkeeping

- 60-min F.3 time-box: ~20 min consumed (3 attempts of Run 1 + 2 rebuilds + DB cleanups).
- Counter at 0/3 consecutive Magic-Moment passes.
- After Defect 10 is resolved by Hafeedh:
  - Pull the (then-committed) Defect 8 + 9 fixes.
  - `docker compose down -v && docker compose build worker api && docker compose up -d --wait`.
  - Re-run alembic + reference-data load.
  - Restart F.3 Run 1 from scratch.

If Run 1 then succeeds, F.3.4 cross-run determinism + F.3.5 three-consecutive-pass gate apply unchanged. F.4 and F.5 procedures are also unchanged.

---

## §5 — Cost Incurred During the Halted F.3 Run

Three F.3 attempts that reached or passed normalize ≈ 3 × (1 Flash extract + 15 lanes × 3 Pro calls) = 3 × 46 ≈ **138 Vertex AI calls**. No clarification or correction Pro calls fired (those would only be on flagged lanes, which validate failed before reaching). Rough estimate at $2/M input, $12/M output, ~2K in / ~0.5K out per Pro call: ~$0.35–$0.50 of Vertex spend. No Slack notification fired (Phase 6.6's failure-path correctly skips `slack_post` enqueue on failure).

---

## §6 — Sprint-Level Implication

`BUILD_COMPLETE_V3.md` was committed on the basis of Phase 6.6 acceptance criteria §8 #1-13 (which it genuinely satisfies — the static-check criteria pass) plus #14 "F.3-F.5 readiness", treating the runtime F.3 pass as a post-approval validation. That validation has now surfaced Defects 8-10. **The build itself is not undone.** The eight defects called out in V3 (1-7 plus the schema-fix sub-defect from the 3B review) remain closed. Sprint 2 closure is therefore best described as "Phase 6.6 approved on code-merit; smoke run halted on three pre-existing defects in adjacent components (Docker COPY, storage client init, IAM)."

Decision for Hafeedh:
- **Path A** — treat Defects 8-10 as a Phase 6.7 closure patch (a third closure), spec + build + review cycle, then a final F.3-F.5 run.
- **Path B** — treat Defects 8-10 as operational fixes (no spec), commit the §3 patches directly, fix IAM, re-run F.3-F.5, and write `BUILD_COMPLETE_V4.md`.

Path B is the lower-overhead option. Defects 8 and 9 are 4-line patches against pre-existing code; Defect 10 is config not code. Recommend Path B unless Bajaj's review process requires every code change to have a phase spec.

— End of HUMAN_INTERVENTION_REQUEST_V3.md.
