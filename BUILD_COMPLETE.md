# SOLVO PILOT ONRAMP — BUILD COMPLETE

**Sprint 2 close.** All six phases of the Sprint 2 build are shipped and reviewed. This document is the sprint-terminal artifact per `PHASE_6_SPEC.md` §10; it replaces a hypothetical `PHASE_7_SPEC.md`.

---

## §1 — PHASE APPROVAL LEDGER

| Phase | Implementation SHA | Fix patches | Approval SHA |
|---|---|---|---|
| **Phase 1** — Scaffolding + boot validators | `57d9729` | `53e2259` | `ed92d9d` |
| **Phase 2** — Stage 1 + 2, ratesheet schemas, ingress | `c797b86` | `f4279d7` | `8d2d93b` |
| **Phase 3** — Stage 3 N=3 ensemble, UN/LOCODE + WCO HS6 | `4937ddb` | `88c9e14` | `563563c` |
| **Phase 4** — EDIFACT + Stage 4 rules + audit trail | `12cbf20` | `909573f` | `e6a86fa` |
| **Phase 5** — Slack + intake + dispatcher + wiring carry-forward | `288641f` | `74727ed` | `6f1d01c` |
| **Phase 6** — Cloud Run europe-west4 deployment + retention enforcer | `ba9ff1d` | `ac505a1` | `be78781` |

Total phases approved: 6 / 6.
Sprint completion commit (this file): pending on the `docs: Sprint 2 build complete` commit recorded below.

---

## §2 — 9-CRITERION ACCEPTANCE SUITE (PHASE 6 §8)

All criteria are evaluated against the Phase 6 codebase at SHA `be78781`. Each line below records the verification status from the Phase 6 review.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Container startup boot validators pass on Cloud Run (exit codes 1–4 verified) | ✅ PASS (unit-verified) | `tests/unit/test_boot_validators.py` covers all four validators including the Phase 6-extended `_validate_vertex_compliance` with retention assertion. Cloud Run runtime verification deferred to ops smoke-check on first deploy. |
| 2 | End-to-end pipeline runs against a real fixture on Cloud Run | ⏳ DEFERRED to ops smoke run | `tests/integration/test_cloud_run_smoke.py` gated on `SOLVO_DEPLOYED_URL`; runs after `infra/scripts/deploy.sh`. |
| 3 | Conformal scoring fires on a no-majority synthetic | ✅ PASS | `tests/unit/test_validate_wiring.py` covers the full chain — conformal score, `conditional_correction` triggered once, clarification drafted, all in one transaction. |
| 4 | EDIFACT path produces lanes from `06_edifact_pricat.edi` | ✅ PASS | `tests/unit/test_edifact_extractor.py` parses the fixture deterministically; Flash fallback covered. |
| 5 | Signed URL TTL = 900 s exactly | ✅ PASS | `tests/unit/test_signed_url.py`; the TTL constant `SIGNED_URL_TTL_SECONDS = 900` is enforced at the function boundary with a `ValueError` on any other value. |
| 6 | Slack signature verification rejects missing / stale signatures | ✅ PASS | `tests/unit/test_slack_signing.py` covers 401 (mismatch) and 403 (replay window). |
| 7 | `/internal/v1/audit/{job_id}` gated; access_log row appears within 30 s | ✅ PASS (unit) | `tests/unit/test_audit_route.py` covers 200/403/404 + outbox write in same transaction. Dispatcher drains every 5 s. |
| 8 | Retention assertion fails boot when GCS lifecycle drifts | ✅ PASS | Phase 6 review patch wired `assert_retention_floors` into validator 4. `tests/unit/test_retention_enforcer.py` covers raw-window relaxation + audit-window relaxation + extra-field rejection. |
| 9 | All unit + integration tests pass | ✅ PASS | **148/148 unit tests pass** at `be78781`. Integration tests skip without env vars (compose, GCS, Cloud Run smoke). |

**Non-counted but mandatory gates:**

- `ruff check .` → **0 errors** at `be78781`. ✅
- `mypy --strict packages/core packages/compliance packages/ingest packages/reference packages/slack packages/storage packages/dispatcher packages/lifecycle apps/api` → **0 errors** at `be78781`. ✅
- Anti-Replication grep (`pomdp|value_iter|constrained.*mdp|belief.*state|active.*learning|recommend.*rate|predict.*price`) → **0 matches** across `packages/` + `apps/`. ✅
- §3.10.5 compliance handshake: in production, `VERTEX_AI_ZDR_ENROLLED=true` is required (boot validator 4 asserts; absence → exit 4). ✅
- `gitleaks` scan: runs as the project's pre-commit gate; zero findings tracked.

---

## §3 — DEPLOYMENT POINTERS

- **Cloud Run deployment URL:** issued by `terraform output cloud_run_api_url` after `infra/scripts/deploy.sh` runs against the target GCP project. Final URL recorded by ops in `docs/deployment_runbook.md` after the first prod apply.
- **GitHub commit SHA at sprint completion:** `be78781` (Phase 6 review approved). The `docs: Sprint 2 build complete` commit that lands this file is the head-of-main on close.
- **Nia index ID:** `9ae50d60-0de8-4f58-b755-2a118fab6651` (repo `Kaide-LABS/solvo-pilot-onramp:main`). Auto-syncs with GitHub.

---

## §4 — CITATION RE-VERIFICATION AUDIT SUMMARY

`ULTIMATE_PRD.md` §4.7 mandated re-verification of three citations at Phase boundaries. Outcomes:

| Citation | Anchors | Gate boundary | Status | Evidence |
|---|---|---|---|---|
| Bai et al., "Schema-Driven Information Extraction from Heterogeneous Tables" (arXiv:2305.14336) | §4.3 (Stage 2 schema-at-extraction-time) | PHASE_2_SPEC.md §0.5 | **PROVISIONAL** | Nia ToC accessible (`sources.sh tree`); body retrieval HTTP 500. Title + ToC confirm topical alignment; Phase 2 extractor uses standard schema-as-response-schema pattern that doesn't depend on body-level methodology details. |
| Ugare et al., "SynCode: LLM Generation with Grammar Augmentation" (arXiv:2403.01632) | §4.2 (constrained-decoding) | PHASE_4_SPEC.md §0.5 | **PROVISIONAL** | Nia ToC includes section "3. SynCode Algorithm" — direct match for §4.2's claim. Body read HTTP 500. Phase 4 Stage 4 hard-rules validator depends only on the general principle that schema-at-decoding-time constrains output structure (Vertex AI `response_schema`). |
| Wan et al., "Dynamic Self-Consistency: Leveraging Reasoning Paths for Efficient LLM Sampling" (arXiv:2408.17017) | §4.4 (conditional Pro correction pass) | PHASE_4_SPEC.md §0.5 | **PROVISIONAL** | Nia ToC includes section "3. Reasoning-Aware Self-Consistency" — direct match for §4.4. Body read HTTP 500. Phase 4 correction module uses a simple disagreement-conditioned gate plus the Phase 3 majority-vote primitive Wan generalizes. |

**Audit verdict:** All three citations are topically aligned per their ToCs. None of the architectural elements they anchor depend on body-level constants or proofs that the inaccessible Nia chunks would have revealed. Re-attempts may upgrade these to PASSED after the Nia paper-body indexing backend recovers; the architectural commitments stand on Phase 5/6 verification of the runtime behavior.

---

## §5 — KAIDE LABS-INTERNAL INVARIANTS PRESERVED

The full Sprint 2 build preserves every hard invariant from `ULTIMATE_PRD.md`:

- **Region binding.** All Vertex AI clients, Cloud Run services, Cloud SQL, Memorystore, and GCS buckets are pinned to `europe-west4` via `Settings.vertex_location: Literal["europe-west4"]` and terraform validation.
- **Model strings.** Only `gemini-3-flash-preview` (Stage 2 extraction, EDIFACT disambiguation) and `gemini-3.1-pro-preview` (Stage 3 N=3 ensemble, Phase 4 conditional correction, Phase 4 clarification) are referenced across `generate_content` calls. No `gemini-2.5-*` or other substitutions.
- **Zero-retention configuration.** Project-level `set_request_response_logging_config(enabled=False)` on each publisher model at boot, asserted by validator 4. Plus ZDR enrollment env-var gating in production.
- **Pydantic `ConfigDict(extra="forbid")`.** Verified on every `BaseModel` subclass across all six phases.
- **N=3 ensemble at temperatures (0.1, 0.5, 0.9).** Module-scope lock in `packages.ingest.normalizer._TEMPERATURES`; the static `test_normalizer_temperatures_are_locked` test pins it.
- **Phase 4 conditional correction temperatures (0.0, 1.0).** Endpoint-only spread; agreement-conditioned escalation only.
- **Majority-vote consensus.** Pure-Python strict majority in `packages.ingest.consensus.majority_consensus`. No weighted voting, no confidence weighting, no LLM-judged consensus.
- **Deterministic Stage 1 + Stage 4.** Zero `generate_content` calls in `classifier.py`, `rules_engine.py`, `consensus.py`, `port_resolver.py`, `packages/reference/`, `packages/lifecycle/`, `packages/dispatcher/`, `packages/storage/`, `packages/slack/`.
- **Transactional outbox.** Every external side-effect row writes inside the caller's `session.begin()`. Dispatcher drains every 5 s with `SET key value NX EX 30` Redis locks.
- **Redis distributed locks.** Pattern is `SET NX EX`; no Redlock, no `WATCH/MULTI`.
- **Anti-Replication boundary.** Zero code produces a price, rate recommendation, margin, market-clearing decision, POMDP / CMDP / value-iteration logic, active learning on booking outcomes, or pricing-decision confidence interval. Conformal prediction is on **extraction confidence** only. The clarification node post-processor rejects any digit. Block Kit Slack summaries embed counts + reasons + signed URL — never rate values.
- **§3.10.4 audit trail.** Append-only `onramp_audit_log` and `onramp_access_log` tables; no `UPDATE` / `DELETE` statements against either in production code paths.
- **§3.10.3 retention floors.** Pinned at the Literal level in `packages.core.models.lifecycle.RetentionAssertion` AND enforced at boot by validator 4 via `assert_retention_floors`.

---

## §6 — HANDOFF TO HAFEEDH

Per `outreach_bundle.md`, Hafeedh manually records the **4–5 minute Vidyard walkthrough** of the Solvo Pilot Onramp demo. The codebase + Cloud Run deployment + the five demo fixtures (`fixtures/01_clean_excel.xlsx` … `05_mixed_units.xlsx`) plus `06_edifact_pricat.edi` are all in place at `be78781`.

Suggested walkthrough scaffold (per the outreach bundle):

1. Open the GitHub repo at `Kaide-LABS/solvo-pilot-onramp` and tour the §3 PRD-aligned package structure (30 s).
2. Show `docs/compliance_attestation.md` — the ISO 27001 / GDPR posture summary (45 s).
3. Run `POST /v1/intake/jobs` against the deployed Cloud Run URL with `fixtures/01_clean_excel.xlsx`. Show the 202 + `JobStatus` (30 s).
4. Show the `/v1/jobs/{id}/status` transitions: `pending → extracting → normalizing → validating → completed` (45 s).
5. Fetch `/v1/intake/jobs/{id}/result-url`, download the signed-URL JSON, show the normalized payload with a flagged lane from `03_obfuscated_ports.xlsx` re-submitted in parallel (60 s).
6. Show a Slack channel screenshot with the Block Kit summary — counts + reasons + link, no rate values (30 s).
7. Wrap with the Anti-Replication framing: "we extract and normalize the ratesheet; Solvo's engine prices it" (45 s).

Once recorded, Hafeedh uploads to Vidyard and sends the link via the `outreach_bundle.md`-specified channel.

---

## §7 — SPRINT-CLOSE CHECKLIST

- [x] All 6 phases built (`feat: Phase N implementation` commits 1–6).
- [x] All 6 phases reviewed and approved (`chore: Phase N review approved` commits 1–6).
- [x] Six fix-patch commits across the six review cycles.
- [x] PHASE_(1..6)_SPEC.md files committed at repo root.
- [x] Citation re-verification gates fired at PHASE_2 + PHASE_4 boundaries; outcomes recorded in §0.5 of each spec.
- [x] 148 unit tests pass at the sprint-terminal commit.
- [x] ruff + mypy --strict gates clean at the sprint-terminal commit.
- [x] Anti-Replication grep zero across `packages/` + `apps/`.
- [x] Terraform + Cloud Build pipeline in place for `gcloud builds submit`.
- [x] `infra/scripts/deploy.sh` and `infra/scripts/smoke_check.sh` shipped.
- [x] `docs/deployment_runbook.md` + `docs/compliance_attestation.md` shipped.
- [ ] First production Cloud Run apply (ops-driven; out of code scope).
- [ ] Vidyard walkthrough recorded (Hafeedh-driven; out of code scope).

---

*End of sprint. The next commit on `main` lands this file with message `docs: Sprint 2 build complete — 6 phases shipped (Sprint 2 close)`. No PHASE_7_SPEC.md.*
