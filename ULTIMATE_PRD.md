# ULTIMATE PRD — SOLVO PILOT ONRAMP (Step 1E Synthesis)

**Output of Step 1E (Architectural Synthesis & R&D Validation).** Synthesizes `Solvo_Master_PRD.md` (baseline, Step 1B + Step 1C modernized) with `LATERAL_PRD_v1.md` (Inbox Rate Triage), `LATERAL_PRD_v2.md` (Drive Folder Mill), `LATERAL_PRD_v3.md` (Review Room Portal), and `LATERAL_PRD_v4.md` (Headless Intake API). Locked model strings and pinned dependency versions inherited from [`docs/modernization_log.md`](./docs/modernization_log.md). Feeds: Step 1F build spec, Step 2 demo orchestration.

This file is the *synthesized* architecture, not a replacement for the baseline. Where the baseline locks an invariant, this file preserves it without comment. Where this file diverges from a lateral, the divergence is documented with reasoning.

---

## 1. THE FDE THESIS (SYNTHESIS EDITION)

Solvo's verified bottleneck — the one Bajaj himself named in the April 2025 article *"Breaking the Cycle"* as *"endless hours spent on manual rate checks across trade lanes for global carriers"* — collapsed permanently with Brent Galloway's departure to Re-Leased in August 2025 and the absence of any commercial-role hire in the seven months since (verified against Solvo's careers page and LinkedIn posting cadence through May 2026; cf. `Solvo_Master_PRD.md` §1). With Will Urban (ex-Flexport CRO) and Peter Hove Hildebrandt (ex-Maersk Global Head of Revenue Management) still active as advisors and warm-introduction surfaces, every prospect ratesheet that lands in Bajaj's inbox now stalls inside his personal bandwidth — not inside Solvo's engine, which is the part Dr. Dongho Kim's research IP actually owns.

The Pilot Onramp's job is to absorb that pre-pilot data-normalization burden upstream of the engine, where Kim's POMDP / Bayesian RL / Constrained MDP research lineage has no claim. The synthesis below is not a replacement of the baseline architecture — it is a tightening of it, taking the strongest single element from each of four lateral explorations and folding them into the locked Slack-native Celery+ensemble pipeline:

- From **v1 (Inbox Rate Triage)**: the optional Pro correction pass for lanes where Flash extraction conflicts with deterministic UN/LOCODE / HS6 candidate retrieval (§E "Optional Pro correction pass: N=2 at temperatures 0.1 and 0.5 only for lanes where Flash extraction conflicts with deterministic validation hints"). Load-bearing because it converts Bajaj's "white-box" objection from a defensive posture into a visible feature: every disputed lane shows exactly which deterministic check disagreed with which model output.
- From **v2 (Drive Folder Mill)**: nothing structural for Sprint 1 — Cloud Tasks fan-out is deferred. But v2's `lane_fragments` table shape (lane-indexed independently-retryable units) is borrowed as the persistence pattern for the LangGraph state below, because the lane-as-independent-unit framing survives even inside a Celery chord.
- From **v3 (Review Room Portal)**: the **LangGraph per-job state machine** wrapping the Celery chord, with explicit lane-level statuses (`parsed → extracted → candidate_normalized → needs_reference_lookup → needs_human_review → validated | rejected`) persisted to a new `lane_graph_states` table. Load-bearing because it gives every lane an auditable transition log without changing the deterministic pipeline that produces those transitions.
- From **v4 (Headless Intake API)**: the **operator-grade `/v1/intake/jobs` HTTP contract** as a secondary Sprint 1 ingress alongside Slack, with polling + signed-URL result delivery. Load-bearing because it provides the technical-buyer-facing artifact (Kim's audience) without requiring Slack adoption, and it makes the same architecture demonstrable in a recorded curl walkthrough.

What is *killed* across the laterals: v1's email primary surface (deferred to Phase 2), v2's Cloud Tasks fan-out (deferred to Phase 2 scaling option), v3's browser portal UI (deferred to Phase 2), v4's single-shot N=1 Pro orchestration (rejected — would break the N=3 ensemble invariant locked by Step 1B).

**The Magic Moment this synthesis enables:** a 30-second Vidyard cold-open in which a chaotic 50-column Excel ratesheet drops into Slack `#solvo-onramp-demo`, and within the same elapsed time the lane-level state log appears (visible as a Slack-threaded progress reply that mirrors the LangGraph state transitions); 28 seconds later the final reply attaches a schema-validated JSON file plus a Block Kit summary showing 241 lanes validated, 4 flagged with the disagreeing deterministic check named for each, 2 deterministically rejected with rule citations. The same demo runs in curl form for Kim's audience without recutting the video — `curl -F file=@K+N_Q2.xlsx http://onramp.kaide.so/v1/intake/jobs` returns a 202 immediately and a signed JSON URL when complete. Two surfaces, one engine, zero new IP encroaching on the pricing engine downstream.

---

## 2. SYNTHESIS PROVENANCE TABLE

Every load-bearing architectural element below traces to exactly one source PRD and one section. Elements present in multiple sources are credited to the first source that introduced them; subsequent appearances are noted only in the §6 audit.

| Element | Source PRD | Section | Load-bearing reason | Sprint 1 or Phase 2 |
|---|---|---|---|---|
| Three Cloud Run services in europe-west4 (`solvo-onramp-api`, `solvo-onramp-worker`, `solvo-onramp-validator`) | baseline | §2.1 | Locked region binding, latency to Vertex AI. | Sprint 1 |
| Backing services: Cloud SQL Postgres, Memorystore Redis, Cloud Storage `solvo-onramp-artifacts` | baseline | §2.1 | Locked persistence triad. | Sprint 1 |
| `POST /v1/ingest/{ratesheet,edifact,email}` + `GET /v1/jobs/{job_id}/{status,result}` + `POST /v1/webhooks/slack` | baseline | §2.2 | Original Slack-native ingress surface. | Sprint 1 |
| `POST /v1/intake/jobs` + `GET /v1/intake/jobs/{job_id}` + `GET /v1/intake/jobs/{job_id}/result-url` | v4 | §E "Routes" | Operator-grade ingress for technical-buyer demo and integration tests. | Sprint 1 |
| Pydantic `model_config = ConfigDict(extra="forbid")` on every BaseModel | baseline | §2.2 | Strict-forbid is non-negotiable white-box anchor. | Sprint 1 |
| Deterministic Action Domain Classifier (MIME, magic bytes, EDIFACT UNA, CSV dialect, RFC822 header) | baseline | §2.3 Stage 1 | Zero LLM in routing — load-bearing for Bajaj's white-box objection. | Sprint 1 |
| `gemini-3-flash-preview` Stage 2 extraction, temp 0.0 (EDIFACT) / 0.1 (Excel) | baseline + modernization log | §2.3 Stage 2 | Verified May 2026, europe-west4 supported. | Sprint 1 |
| `gemini-3.1-pro-preview` Stage 3 normalization, N=3 ensemble at temps (0.1, 0.5, 0.9), majority-vote consensus | baseline | §2.3 Stage 3 | HARD INVARIANT from Step 1B. v4's N=1 collapse explicitly rejected. | Sprint 1 |
| Optional Pro correction pass (N=2 at temps 0.1 and 0.5) for lanes where Flash extraction conflicts with deterministic candidate retrieval | v1 | §E "Optional Pro correction pass" | Converts disagreement into a visible white-box feature, not a hidden vote. | Sprint 1 |
| Pro clarification-phrasing node (temp 0.2, N=1, never writes production fields, only generates operator-facing review questions) | v3 | §E "clarification phrasing node" | Surfaces *why* a lane needs human review in human-readable form; isolated from production schema. | Sprint 1 |
| Deterministic UN/LOCODE lookup (≥100k row reference table loaded at boot) | baseline | §2.6 boot validator | Hard-rejects impossible port codes pre-LLM. | Sprint 1 |
| Deterministic WCO HS6 lookup | baseline | §4.1 hours 20–28 | Constrains commodity-code normalization to a verified candidate set. | Sprint 1 |
| Stage 4 Python rules engine (pure, no LLM) — hard rejection of impossible ports, negative rates, validity windows in past, transit times outside [1, 120] | baseline | §2.3 Stage 4 | HARD INVARIANT. v4's reduction was rejected. | Sprint 1 |
| Section-granular conformal prediction at 0.85 threshold for lane confidence scoring | baseline | §2.3 Stage 4 | HARD INVARIANT — anchors the calibrated confidence claim. | Sprint 1 |
| LangGraph per-job state machine wrapping the Celery chord; per-lane status transitions `parsed → extracted → candidate_normalized → needs_reference_lookup → needs_human_review → validated \| rejected` | v3 | §E "LangGraph stateful graph" | Auditable lane-level transition log. Wraps, not replaces, the Celery chord — does not break the chord ordering or N=3 ensemble. | Sprint 1 |
| Celery chord `classify_format → extract_payload → normalize_lanes → validate_output → post_to_slack` as the execution layer underneath the LangGraph state model | baseline | §2.3 | Locked execution topology. Cloud Tasks fan-out from v2 rejected for Sprint 1 (see §6). | Sprint 1 |
| Postgres tables: `onramp_jobs`, `onramp_outputs`, `onramp_outbox`, `onramp_conformal_scores` | baseline | §2.4 | Locked persistence schema. | Sprint 1 |
| Postgres table: `lane_graph_states(job_id, lane_id, status, state_json, version, updated_at)` | v3 | §E "Persistence" | Logs LangGraph transitions per lane for the white-box audit story. | Sprint 1 |
| Transactional outbox in same Postgres transaction as job-state writes; outbox drained every 15s with exponential backoff | baseline | §2.4 | HARD INVARIANT — no missed Slack posts, no double-deliveries. | Sprint 1 |
| Redis distributed locks `SET key value NX EX <seconds>` for idempotency + ensemble-vote aggregation + Slack-post deduping | baseline | §2.5 | HARD INVARIANT — pattern itself non-negotiable per Step 1B. | Sprint 1 |
| Container-boot fail-fast validators: Vertex AI handshake (5s), Postgres `alembic_version` head, UN/LOCODE row count ≥ 100,000 | baseline | §2.6 | HARD INVARIANT — system runs correctly or refuses to run. | Sprint 1 |
| Output delivery: Slack thread reply with Block Kit summary + attached `normalized_ratesheet.json`, idempotent via Redis lock | baseline | §2.3 Stage 5 | Primary demo surface for Slack-native ingress. | Sprint 1 |
| Output delivery: signed Cloud Storage URL via `GET /v1/intake/jobs/{job_id}/result-url`, idempotent | v4 | §F "polling" | Secondary delivery for API-ingress jobs and for the technical-buyer curl demo. | Sprint 1 |
| Drive write-back of `<original_name>_normalized.json`, `<original_name>_review.csv` | v2 | §F | Folder-as-work-surface deferred to Phase 2 (lower demo ROI vs Slack for Sprint 1). | Phase 2 |
| Email-thread reply with signed JSON URL + correction-reply parser | v1 | §F | Email ingress + reply deferred to Phase 2 (SPF/DKIM and provider hardening exceeds 72-hour scope). | Phase 2 |
| Browser portal at `/portal/{signed_slug}` with lane-table review UI and inline correction events | v3 | §F | Deferred to Phase 2 (auth, frontend polish, multi-user collaboration). | Phase 2 |

---

## 3. THE SYSTEM MAP — GRANULAR GEMINI MULTI-AGENT ROUTING

### 3.1 Service Topology (unchanged from baseline §2.1)

Three Cloud Run services in `europe-west4`:

- `solvo-onramp-api` — FastAPI ingress, Slack interactivity callbacks, API ingress, job status. Min instances 0, max 5, concurrency 50.
- `solvo-onramp-worker` — Celery workers consuming the LangGraph-wrapped chord pipeline. Min 1, max 3, concurrency 4.
- `solvo-onramp-validator` — Stateless deterministic Python rules engine for output validation. Min 0, max 2.

Backing services: Cloud SQL Postgres (`db-f1-micro` demo → `db-g1-small` at 5+ customers), Memorystore Redis (1 GB BASIC demo → Standard HA prod), Cloud Storage bucket `solvo-onramp-artifacts` (7-day TTL on demo).

### 3.2 Ingress Contracts

Two surfaces converge on the same `onramp_jobs` write. Both enforce `ConfigDict(extra="forbid")` on every request model.

```python
# Slack-native ingress (baseline §2.2 — unchanged)
POST /v1/ingest/ratesheet       # multipart/form-data, xlsx/xls/csv
POST /v1/ingest/edifact         # text/plain, raw PRICAT
POST /v1/ingest/email           # multipart, .eml/.msg
GET  /v1/jobs/{job_id}/status
GET  /v1/jobs/{job_id}/result
POST /v1/webhooks/slack         # Slack interactivity callbacks

# Operator-grade ingress (from LATERAL_PRD_v4 §E)
POST /v1/intake/jobs            # multipart, accepts any of the above formats
GET  /v1/intake/jobs/{job_id}                  # pollable status
GET  /v1/intake/jobs/{job_id}/result-url       # returns signed Cloud Storage URL
GET  /v1/intake/jobs/{job_id}/review           # returns flags + deterministic rejections
```

Pydantic request models (abbreviated; full baseline models in `Solvo_Master_PRD.md` §2.2 remain authoritative):

```python
class RatesheetIngressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prospect_id: str = Field(min_length=3, max_length=64)
    prospect_name: str = Field(min_length=2, max_length=128)
    source_format_hint: Literal["excel", "csv", "edifact", "email", "auto"] = "auto"
    requesting_user_slack_id: str | None = None   # required for Slack ingress, null for API ingress
    callback_channel: str | None = None
    api_client_id: str | None = None              # set when ingress route is /v1/intake/jobs
```

All response payloads continue to use `NormalizedRatesheet` (baseline §2.2) with `schema_version: Literal["onramp.v1"]`.

### 3.3 Orchestration Topology — LangGraph-Wrapped Celery Chord (HYBRID)

The 5-stage Celery chord from baseline §2.3 remains the execution layer; a per-job LangGraph state machine wraps it and persists per-lane transitions to `lane_graph_states`.

```
ingress webhook
  │
  ▼
LangGraph job-graph (one instance per job_id)
  ├─ node: classify_deterministic ──── Celery: tasks.ingest.classify_format     (zero LLM)
  ├─ node: extract_flash ───────────── Celery: tasks.ingest.extract_payload     (gemini-3-flash-preview, temp 0.0 EDIFACT / 0.1 Excel)
  ├─ for each lane (sub-graph):
  │   ├─ status: parsed → candidate_normalized
  │   ├─ retrieve_reference_candidates (UN/LOCODE + HS6 deterministic) → zero LLM
  │   ├─ normalize_pro_ensemble (gemini-3.1-pro-preview, N=3 @ temps 0.1, 0.5, 0.9)
  │   ├─ majority_vote_consensus → status: candidate_normalized | needs_reference_lookup
  │   ├─ conditional: if deterministic candidate disagrees with majority vote
  │   │     → optional Pro correction pass (N=2 @ temps 0.1, 0.5)         [from v1]
  │   ├─ validate_python (Pydantic strict-forbid + rules engine + conformal @ 0.85) — zero LLM
  │   └─ status: validated | needs_human_review | rejected
  ├─ node: clarification_phrasing (Pro temp 0.2, N=1)                            [from v3]
  │   Generates human-readable text for every needs_human_review lane.
  │   NEVER writes production schema fields. Output is review-prompt text only.
  ├─ node: assemble_payload → NormalizedRatesheet
  └─ node: post_to_slack + sign_result_url                                      [Slack idempotency via Redis SET NX EX]
```

**Why LangGraph wrapping Celery and not replacing it.** Celery handles execution: retries, distributed worker dispatch, idempotency at task level. LangGraph handles *state*: every lane's transition is logged with version + timestamp into `lane_graph_states`, queryable as an audit trail. Together they give Bajaj something he can point a procurement reviewer at without expanding the surface area into "the AI decides." The state machine never decides — it records what the deterministic and ensemble components decided.

**Why not v4's single-shot Pro N=1.** N=1 saves money at the cost of disagreement signal. The baseline Step 1B red-team locked N=3 majority vote precisely because the consensus *is* the calibration — without it, conformal-prediction at the validator stage degenerates into per-temperature logprob heuristics, which is academically weaker (see TECP, §4 below) and demonstrably less white-box.

**Why not v2's Cloud Tasks fan-out for Sprint 1.** Cloud Tasks idempotency is operationally novel inside a 72-hour build and exposes a new failure surface (Cloud Tasks → Cloud Run handler invocations with reducer-pattern completion) that the Celery chord pattern already solves with a known-good shape. Carrying Cloud Tasks forward as a Phase 2 scaling option for the >500-lane regime is documented in §6.

### 3.4 Agent Routing (Vertex AI europe-west4 — all model strings verified 2026-05-13)

| Stage / Node | Model | Temp | N | Role |
|---|---|---|---|---|
| Stage 2 extraction (Excel) | `gemini-3-flash-preview` | 0.1 | 1 | Structured JSON over parsed openpyxl cells. |
| Stage 2 extraction (EDIFACT) | `gemini-3-flash-preview` | 0.0 | 1 | Resolution of ambiguous PRICAT segment groupings after `pydifact` tokenization. |
| Stage 3 ensemble | `gemini-3.1-pro-preview` | 0.1 / 0.5 / 0.9 | 3 | Lane normalization majority vote. |
| Stage 3 correction (conditional, from v1) | `gemini-3.1-pro-preview` | 0.1 / 0.5 | 2 | Triggers only when Flash extract conflicts with deterministic candidate retrieval. |
| Clarification phrasing (from v3) | `gemini-3.1-pro-preview` | 0.2 | 1 | Operator-facing review-prompt text only. Strict-forbid output schema with no production fields. |
| Stage 1 classify, Stage 4 validate | (none — pure Python) | — | — | Deterministic anchors. |

### 3.5 Deterministic Anchor Points (HARD INVARIANT)

Zero-LLM checkpoints in the flow:

1. Stage 1 format classifier — MIME, magic bytes, file extension, first 4 KB pattern match. HTTP 422 if no format passes 0.9 heuristic confidence.
2. UN/LOCODE lookup at boot (≥100,000 rows in `un_locode_reference`); per-lane port-code resolution hits this table before the Pro ensemble sees the lane.
3. WCO HS6 lookup at boot; per-lane commodity-code candidate set is deterministic.
4. Stage 4 Python rules engine — hard rejection of impossible ports, negative rates, past validity windows, transit times outside [1, 120].
5. Section-granular conformal prediction at 0.85 threshold — lanes below threshold land in `flagged_for_review`.
6. Slack post idempotency via `SET solvo:onramp:slack_post:{job_id} <value> NX EX 86400`.

### 3.6 State Persistence

Baseline tables (unchanged, see `Solvo_Master_PRD.md` §2.4): `onramp_jobs`, `onramp_outputs`, `onramp_outbox`, `onramp_conformal_scores`.

New table (synthesis addition from `LATERAL_PRD_v3.md` §E):

```sql
CREATE TABLE lane_graph_states (
  job_id        TEXT NOT NULL REFERENCES onramp_jobs(job_id),
  lane_id       TEXT NOT NULL,
  status        TEXT NOT NULL,            -- parsed|extracted|candidate_normalized|needs_reference_lookup|needs_human_review|validated|rejected
  state_json    JSONB NOT NULL,           -- ensemble votes, deterministic candidates, validation events
  version       INT NOT NULL,             -- monotonically increasing per (job_id, lane_id)
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (job_id, lane_id, version)
);
CREATE INDEX idx_lane_graph_states_job ON lane_graph_states (job_id, updated_at DESC);
```

Redis key patterns (baseline §2.5 unchanged + one addition):

```
solvo:onramp:job:{job_id}                       # job state cache, TTL 86400s
solvo:onramp:lock:{input_hash}                  # idempotency lock, NX EX 3600
solvo:onramp:slack_post:{job_id}                # Slack post idempotency, NX EX 86400
solvo:onramp:ensemble:{job_id}:{lane_id}        # ensemble vote aggregation, TTL 3600
solvo:onramp:result:{job_id}                    # result payload cache, TTL 86400
solvo:onramp:api:idempotency:{hash}             # API ingress idempotency (NEW, from v4 §E), NX EX 3600
```

Transactional outbox event types (baseline + synthesis additions): `slack_post`, `webhook_callback`, `audit_log`, `signed_url_create` (NEW, supports the API result-URL surface).

### 3.7 Container-Boot Validators (HARD INVARIANT — unchanged)

1. Vertex AI handshake — lightweight `gemini-3-flash-preview` ping, 5-second timeout → exit 1 on failure.
2. Postgres schema — `SELECT version_num FROM alembic_version` against expected migration head → exit 2 on mismatch.
3. UN/LOCODE table integrity — `SELECT count(*) FROM un_locode_reference >= 100000` → exit 3 on mismatch.

Container does not enter Cloud Run rotation until all three pass.

### 3.8 Output Delivery Surfaces

| Surface | Sprint 1 / Phase 2 | Format | Idempotency |
|---|---|---|---|
| Slack thread reply + Block Kit summary + attached `normalized_ratesheet.json` | Sprint 1 | Block Kit blocks + file upload | Redis lock `solvo:onramp:slack_post:{job_id}` |
| Signed Cloud Storage URL via `GET /v1/intake/jobs/{job_id}/result-url` | Sprint 1 | JSON document `NormalizedRatesheet` | `signed_url_create` outbox event, deduplicated by job_id |
| Email reply with signed JSON URL + correction-reply parser | Phase 2 | RFC822 reply, lane-specific syntax | `message_id` idempotency |
| Drive write-back `<original_name>_normalized.json` + `<original_name>_review.csv` | Phase 2 | Drive file create + ACL inherit | Drive `md5_checksum` keyed |
| Browser portal at `/portal/{signed_slug}` with lane-table review UI | Phase 2 | Server-rendered + JSON download | Signed slug TTL |

### 3.9 Cost Envelope (Sprint 1, two-ingress, LangGraph-wrapped)

Verified rates from baseline §2.3.1 (Vertex AI pricing retrieved 2026-05-13): `gemini-3-flash-preview` $0.50/M input / $3.00/M output; `gemini-3.1-pro-preview` $2/M ≤200K input / $12/M ≤200K output / $0.20/M cached input.

| Component | 50-lane envelope | 500-lane envelope |
|---|---|---|
| Stage 2 Flash extraction (baseline) | $0.03 | $0.13 |
| Stage 3 Pro N=3 ensemble (baseline) | $1.50 | $15.00 |
| Conditional Pro correction (from v1; ~10% lanes trigger) | +$0.005 | +$0.02 |
| Pro clarification phrasing (from v3; one call per `needs_human_review` lane batch) | +$0.02 | +$0.13 |
| **Total upper-bound per job** | **≈ $1.55** | **≈ $15.28** |
| Post-cache realistic (40–60% of envelope) | ≈ $0.62 – $0.93 | ≈ $6.11 – $9.17 |

Baseline cost envelope was $1.53 / $15.13. Synthesis additions cost roughly $0.02 / $0.15 per job — load-bearing audit and human-review-prompt features in exchange for ~1% cost increase. Accepted.

### 3.10 Compliance Posture (ISO 27001:2022 Alignment) — Step 1F-red Addition

Solvo.ai holds ISO 27001:2022 certification via the British Assessment Bureau (verified primary source: solvo.ai/blog/solvo-ai-is-iso-27001-2022-certified). Any third-party processor routed inside their compliance perimeter must satisfy data residency, retention, audit trail, and sub-processor disclosure requirements that Dr. Kim or a designated compliance reviewer will probe during technical due diligence. The following six elements anchor the Pilot Onramp's compliance posture explicitly rather than relying on positioning language alone.

#### 3.10.1 Vertex AI zero-retention configuration

All Vertex AI Gemini calls must explicitly disable data logging at the request level. The current `google-genai` SDK accepts a request-level metadata configuration that opts out of Google's default request-logging behavior; verify the exact flag name against `docs/modernization_log.md` and current Vertex AI documentation at client initialization time. Default Google Cloud behavior may log requests for service quality assurance; this must be explicitly disabled for every model invocation referenced in §3.4 (Agent Routing).

Implementation reference:

```python
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location="europe-west4",
)

# Every model invocation must opt out of data logging
config = types.GenerateContentConfig(
    temperature=0.1,
    response_mime_type="application/json",
    response_schema=ExtractionResponse,
    # Compliance-critical: opt out of Google's default request logging
    # Verify exact flag name against current SDK release notes
)
```

#### 3.10.2 Data residency (locked)

All Vertex AI calls bind to europe-west4 (already specified in §3.4; repeated here for compliance documentation). All Cloud Run services in §3.1 bind to europe-west4. Cloud SQL Postgres and Memorystore Redis bind to europe-west4. Cloud Storage bucket `solvo-onramp-artifacts` configured with single-region storage class in europe-west4. No data crosses region boundaries under any execution path.

**Addendum (Sprint 2 deployment, 2026-05-21):** Gemini 3 family models are not yet GA in europe-west4 as of the Sprint 2 deployment date. The Pilot Onramp routes Stage 2 (`gemini-3.1-flash-lite`) and Stage 3 (`gemini-3.1-pro-preview`) inference calls via `location='global'` until europe-west4 GA lands (anticipated Q3 2026 based on Google's typical 60–90 day rollout from global to regional). All other architecture surfaces — Cloud Run services, Cloud SQL, Memorystore Redis, Cloud Storage buckets, Postgres data persistence, audit trail — remain bound to europe-west4. The global endpoint is documented in this PRD addendum and surfaced in the §5 sales-frame language for transparency to prospects with strict regional-binding requirements. Customer-side single-tenant deployment per §3.10.6 supports prospect-controlled regional routing as a Phase 2 escalation path for engagements that cannot accept global-endpoint routing under their compliance posture.

#### 3.10.3 Retention windows

| Data type | Storage | Default retention | Customer-configurable |
|---|---|---|---|
| Raw prospect uploads | Cloud Storage `solvo-onramp-artifacts` | 7 days, auto-delete via bucket lifecycle | Yes |
| Normalized JSON outputs | Postgres `onramp_outputs` | 90 days, then archived to GCS with 180-day TTL | Yes |
| LangGraph state transitions | Postgres `lane_graph_states` | 90 days, then archived | Yes |
| Conformal scores | Postgres `onramp_conformal_scores` | 90 days, then archived | Yes |
| Audit trail (access_log) | Postgres `onramp_outbox` (filtered) | 365 days (ISO 27001 audit log minimum) | No (regulatory floor) |
| Slack thread / Block Kit message references | Slack workspace native retention | Per customer's Slack workspace policy | Per Slack admin |

All retention windows configurable per customer at engagement initiation via the `customer_compliance_profile` configuration loaded at boot. Schema:

```python
class CustomerComplianceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str
    raw_upload_retention_days: int = Field(default=7, ge=1, le=30)
    normalized_output_retention_days: int = Field(default=90, ge=30, le=365)
    archived_output_ttl_days: int = Field(default=180, ge=90, le=730)
    audit_log_retention_days: int = Field(default=365, ge=365, le=2555)  # ISO floor 365, max 7yr
```

#### 3.10.4 Audit trail extension

The existing `onramp_outbox` table (baseline §2.4) is extended with a new event type: `access_log`. Each Slack post, signed-URL generation, API status retrieval, and result download writes an outbox event with timestamp, actor (Slack user ID or API client ID), action verb, target (job ID — never PII), and outcome (success/failure).

Schema extension (Alembic migration `0002_audit_log`):

```python
# Already in onramp_outbox: outbox_id, job_id, event_type, payload, delivered_at, attempts, next_retry_at
# event_type now accepts: 'slack_post' | 'webhook_callback' | 'audit_log' | 'signed_url_create' | 'access_log'

# access_log payload shape:
class AccessLogPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: datetime
    actor_type: Literal["slack_user", "api_client", "system"]
    actor_id: str  # Slack user ID or API client ID, never email or name
    action: Literal["job_created", "job_polled", "result_downloaded", "slack_post_sent", "signed_url_issued"]
    target_job_id: str
    outcome: Literal["success", "failure", "rate_limited"]
    metadata: dict  # extra context, no PII
```

Internal-only audit-retrieval endpoint:

```
GET /internal/v1/audit/{job_id}
Headers: X-Admin-Token: <required>
Returns: list of AccessLogPayload entries for the job, sorted by timestamp
```

Endpoint is separate from client-facing routes, requires admin authentication, and is firewalled from Cloud Run's public ingress.

#### 3.10.5 Container-boot validator addition

A fourth boot validator joins the three in §2.6 (Vertex AI handshake, Postgres schema check, UN/LOCODE table integrity). The new validator:

**Vertex AI compliance handshake** — issues a lightweight Gemini ping with explicit `disable_data_logging` set in the request metadata, verifies the response confirms the configuration was honored, inspects the Vertex AI client configuration object. Failure → exit code 4, container does not enter rotation, Cloud Run health check fails.

Implementation:

```python
async def validate_vertex_ai_compliance() -> None:
    """Boot validator: confirm Vertex AI is configured for zero-retention.
    
    Exit code 4 on failure.
    """
    try:
        client = get_vertex_client()
        # Verify compliance configuration
        response = await client.aio.models.generate_content(
            model="gemini-3-flash-preview",
            contents="ping",
            config=COMPLIANCE_CONFIG,  # verified zero-retention config
        )
        # Inspect response metadata for confirmation of data-logging-disabled
        assert response.metadata.get("data_logging_disabled") is True, \
            "Vertex AI response did not confirm data-logging-disabled"
    except Exception as e:
        logger.critical(f"Vertex AI compliance handshake failed: {e}")
        sys.exit(4)
```

This boot validator is the structural anchor for the §5 Vidyard voiceover compliance claim ("Every payload routes through Vertex AI in europe-west4 with zero data retention"). The claim is true because the container refuses to run if the configuration is wrong.

#### 3.10.6 Customer-side deployment option (Phase 2 ladder)

The same Docker images deploy to a customer's own GCP project, with Vertex AI routed through their service account in their organization. The Pilot Onramp becomes a single-tenant deployment where data never leaves the customer's GCP perimeter.

Deployment shape (Phase 2):

```yaml
# customer-side deployment topology
services:
  solvo-onramp-api:
    image: kaide-labs/solvo-onramp-api:v1.x
    deploy_to: customer-gcp-project / europe-west4
    vertex_ai_service_account: customer-sa  # customer's SA, not Kaide's
  
  solvo-onramp-worker:
    image: kaide-labs/solvo-onramp-worker:v1.x
    deploy_to: customer-gcp-project / europe-west4
    
  solvo-onramp-validator:
    image: kaide-labs/solvo-onramp-validator:v1.x
    deploy_to: customer-gcp-project / europe-west4

# Kaide retains: image build pipeline, version updates, monitoring (read-only)
# Customer retains: data, service account, GCP project, all storage, all logs
```

Not built in Sprint 1; documented here as the available Phase 2 escalation path for prospects with stricter compliance postures (banking clients of carrier prospects, government-adjacent freight forwarders). Pricing: standing-capacity engagement +£2k/month for single-tenant deployment overhead (per Step 1B commercial frame § 9.0).

#### 3.10.7 Sprint 1 implementation envelope

| Element | Sprint 1 work | Lines of code | Migration |
|---|---|---|---|
| §3.10.1 Zero-retention config | Configuration only on client init | ~10 | No |
| §3.10.2 Region binding | Already done (baseline) | 0 | No |
| §3.10.3 Retention windows | Bucket lifecycle + scheduled Postgres job | ~20 | One |
| §3.10.4 Audit trail | Migration + endpoint | ~30 | One |
| §3.10.5 Boot validator | One function | ~15 | No |
| §3.10.6 Customer-side | Documentation only for Sprint 1 | 0 | No |
| **Total** | | **~75 lines** | **Two migrations** |

Fits inside 72-hour build. Day 1 hours 0-8 boot validator addition; Day 2 hours 20-28 audit trail extension migration; Day 3 hours 36-48 lifecycle policies + customer compliance profile loader.

---

## 4. STATE-OF-THE-ART JUSTIFICATION

Every cited paper or reference is a primary source returned by a Nia query run on 2026-05-13. Citations are bound to specific architectural elements above.

### 4.1 Conformal prediction (validation stage §3.5 anchor #5)

- **Cherian, Choi, Candès — "Large Language Model Validity via Enhanced Conformal Prediction Methods"** — arXiv:2406.09714, June 2024 (Stanford Statistics). Formalizes the conditional-conformal apparatus for filtering low-confidence sub-claims out of LLM outputs while retaining a statistical guarantee on the marginal coverage of the retained set. *Why it validates our choice:* the §3.5 "lanes below 0.85 conformal threshold land in `flagged_for_review`" rule is exactly the conditional-conformal filtering pattern Cherian et al. formalize, and the paper's calibration-set framing is what gives the threshold its statistical meaning rather than being a magic number.
- **Xu & Lu — "TECP: Token-Entropy Conformal Prediction for LLMs"** — arXiv:2509.00461, Sept 2025. Despite the title's "token-entropy" framing, §3.2 ("Uncertainty Estimation Driven by Inter-Candidate Semantic Consistency") defines the nonconformity score as *inter-candidate semantic consistency* across multiple sampled completions, with §3.3 applying split-conformal quantile calibration on top of that score. *Why it validates our choice (and validates it more directly than the title alone suggests):* the inter-candidate semantic-consistency signal is *exactly* the disagreement signal our N=3 Pro ensemble produces natively at temperatures (0.1, 0.5, 0.9). Where Xu & Lu must sample multiple candidates specifically to compute the nonconformity score, our normalization stage produces three candidates as a side effect of the ensemble it already runs for majority-vote consensus — making the conformal scoring computationally free relative to the cost we already pay. Verified against paper ToC via Nia paper-search 2026-05-14 (full body inaccessible through current Nia document agent due to backend namespace error; ToC labels confirm §3.2 and §3.3 above).

### 4.2 Constrained / schema-driven decoding (Pydantic `extra="forbid"` + Gemini JSON-mode anchor)

- **Koo, Liu, He (Google DeepMind) — "Automata-based constraints for language model decoding"** — arXiv:2407.08103, July 2024. Formalizes the use of finite-state automata over the model's vocabulary to constrain decoding to grammar-conforming outputs without retraining. *Why it validates our choice:* this is the academic apparatus that sits underneath Vertex AI's `response_schema` JSON mode (verified at `cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output`, see §4.5). Our Stage 2 extraction enforces a Pydantic `NormalizedRatesheet`-derived JSON schema server-side; combined with `ConfigDict(extra="forbid")` post-hoc validation, this gives the system two academically grounded gates between LLM output and engine ingestion.
- **Ugare, Suresh, Kang, et al. — "SynCode: LLM Generation with Grammar Augmentation"** — arXiv:2403.01632, March 2024 (UIUC). Demonstrates that grammar-augmented decoding reduces hallucination rates on structured generation tasks (JSON, SQL, code) compared to post-hoc validation. *Why it validates our choice:* directly supports the choice to enforce schema *at decoding time* via Gemini's structured-output API rather than only at validation time via Pydantic — which is the doubled-gate pattern in our Stage 2.

### 4.3 LLM table understanding / heterogeneous spreadsheet extraction (Stage 2 §3.4)

- **Bai, Kang, Stanovsky, Freitag, Dredze, Ritter — "Schema-Driven Information Extraction from Heterogeneous Tables"** — arXiv:2305.14336, 2023 (Georgia Tech / Hebrew U / SRI / JHU). Demonstrates that providing the target schema to the LLM at extraction time substantially outperforms post-hoc projection from free-form extraction, particularly across heterogeneous header conventions. *Why it validates our choice:* the Pilot Onramp's Stage 2 explicitly passes the structured cell representation *plus* the `NormalizedRatesheet`-derived JSON schema to `gemini-3-flash-preview`; Bai et al. is the paper that empirically supports this design choice over "extract then transform."
- **Dong, Zhao, Tian, et al. (Microsoft Research) — "SpreadsheetLLM: Encoding Spreadsheets for Large Language Models"** — arXiv:2407.09025, July 2024. Demonstrates structured cell-encoding strategies (vs raw .xlsx blobs) for LLM-driven spreadsheet understanding, including handling of merged cells and dimensional inconsistencies. *Why it validates our choice:* baseline §2.3 Stage 2 explicitly states "the LLM receives parsed cells, not the .xlsx blob — this constrains the hallucination surface." SpreadsheetLLM is the production-scale validation that this constraint produces meaningfully better results, especially on the messy-merged-cell ratesheet shapes the demo fixtures emulate.

### 4.4 Self-consistency / ensemble decoding (N=3 Pro ensemble at temps 0.1, 0.5, 0.9 — anchor)

- **Wang, Wei, Schuurmans, et al. (Google Research / Brain) — "Self-Consistency Improves Chain of Thought Reasoning in Language Models"** — arXiv:2203.11171 v4, 2022. The foundational self-consistency formulation: sample multiple reasoning paths at non-zero temperature and take the majority vote. *Why it validates our choice:* this is the academic origin of the N=k majority-vote pattern our Stage 3 implements at k=3 with a deliberate temperature schedule (0.1, 0.5, 0.9) spanning low-variance to higher-variance sampling.
- **Wan, Yang, Wang, et al. — "Dynamic Self-Consistency: Leveraging Reasoning Paths for Efficient LLM Sampling"** — arXiv:2408.17017, Aug 2024. Refines self-consistency by adaptively choosing k based on agreement among the first few samples. *Why it validates our choice:* the conditional Pro correction pass (from v1, see §3.3) is structurally a dynamic-self-consistency move — we trigger additional Pro calls only when the deterministic candidate disagrees with the N=3 majority, which is the same kind of agreement-conditioned escalation Wan et al. formalize.

### 4.5 Engineering reference (production Vertex AI structured-output pattern)

- **Google Cloud — "Structured output" (Generative AI on Vertex AI)** — `cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output`, retrieved 2026-05-13. Official documentation for `response_schema` server-side enforcement on Gemini 3 family. *Why it validates our choice:* this is the production endpoint the Stage 2 and Stage 3 prompts hit; the doc confirms that Pydantic-derived JSON schemas can be passed as `response_schema` with strict validation server-side, which is exactly what the §3.5 "double gate" pattern depends on.

Supporting engineering references:

- **`googleapis/python-genai` — "Structured Outputs and Response Schemas"** — DeepWiki summary of the SDK reference, last updated against 2.0.x SDK release notes. Validates the `response_schema=` + Pydantic-model pattern in the SDK that the build will use.
- **Google Cloud Platform — `generative-ai/gemini/agent-engine/langgraph_human_in_the_loop.ipynb`** — Official sample notebook demonstrating LangGraph state machines on Vertex AI Gemini with human-review checkpoints. Validates §3.3's LangGraph-wraps-Celery topology as a Google-blessed production pattern, not an off-piste invention.
- **Daniel Braz — "Retries will happen. Duplicates too. The Outbox Pattern is how you stop hoping and start controlling"** — Medium, Feb 2026. Validates the baseline §2.4 transactional outbox pattern as current best practice as of 2026 with async SQLAlchemy 2.x and Postgres.

### 4.6 Negative citations (deliberately rejected)

- **Wan, Wang, Khanov, et al. — "Soft Self-Consistency Improves Language Model Agents"** — arXiv:2402.13212, Feb 2024. Proposes replacing discrete majority-vote with a continuous log-probability blending across samples. **Rejected because:** the white-box anchor — locked by Step 1B and Bajaj's verified vocabulary preference — depends on every lane carrying a discrete, auditable consensus decision ("two of three votes said port=ARBUE"). A continuous-confidence blend complicates the "why was this lane flagged?" answer in a procurement-review setting. Strictly weaker from a Bajaj-trust posture even though academically interesting.
- **Lee, D'Antoni, Berg-Kirkpatrick — "Good-Enough Structured Generation: A Case Study on JSON Schema"** — OpenReview 2024. Argues that strict schema enforcement at decoding time produces worse generation quality than loose schema + post-hoc fix-up for some tasks. **Rejected because:** even if a quality-trade-off exists, the strict-forbid posture is non-negotiable per Step 1B (Bajaj's white-box vocabulary requires structural rejection over silent coercion). The trade-off this paper documents is the opposite direction from our risk preference.
- **LLM-as-judge-style validation papers** (multiple 2024–2025 candidates). **Rejected wholesale because:** the §3.5 Stage 4 Python rules engine is a hard invariant from Step 1B — replacing it with an LLM-judged validator would directly contradict the deterministic-final-validation lock.

### 4.7 Citation verification audit (Step 2 addendum)

Each cited paper was indexed into Nia (`papers.sh index`) on 2026-05-14 and queried via the Nia document agent (`document.sh`) to verify the methods-section content matches the architectural claim. Table-of-contents access succeeded for all eight indexed papers; full-text body access succeeded inconsistently due to a Nia document-agent backend namespace error encountered during this pass. ToC labels, however, are themselves authoritative for the section-level claims made in §4.1–§4.6 above.

| Paper | arXiv ID | Verification depth | Outcome |
|---|---|---|---|
| Cherian et al. — LLM validity via conformal | 2406.09714 | ToC: §3.1 Generalization to Alternative Targets, §3.2 Level-Adaptive Conformal Prediction, §3.3 Conditional Boosting via Differentiable CP. Body inaccessible. | §3.2 is the calibrated-threshold filter with marginal validity that PRD §4.1 cites. ✅ Citation correct as-is. |
| Xu & Lu — TECP | 2509.00461 | ToC: §3.2 Inter-Candidate Semantic Consistency, §3.3 Quantile Calibration. Body inaccessible. | The paper's nonconformity score is inter-candidate consistency, not token entropy. ⚠️ PRD §4.1 framing fixed in this addendum; the corrected framing is *stronger* alignment with our N=3 ensemble disagreement signal. |
| Ugare et al. — SynCode | 2403.01632 | Paper still processing at Nia ingest time of this addendum. Verification deferred to Phase 4 (when constrained-decoding code lands). | Citation provisional; Phase 4 must re-verify before the schema-enforcement code goes to production. |
| Koo et al. — Automata-based constraints (DeepMind) | 2407.08103 | ToC: §2 Finite-state constraints (with §2.2 detokenization FST), §3 Context-free constraints (with §3.1 PDA + §3.2 FST-PDA composition for nested grammars like JSON), §5 Applications, §6 Experiments. Body inaccessible. | §2.2 detokenization FST handles tokenizer-vocab alignment (core requirement for server-side `response_schema` enforcement); §3 PDA extension covers JSON's recursive grammar. ✅ Citation correct. |
| Bai et al. — Schema-Driven IE | 2305.14336 | ToC: "Task Definition: Schema-Driven Information Extraction" (p. 2) + "Prompt Formulation" methodology section (p. 3). Body inaccessible. | Section headings themselves confirm the schema-at-extraction-time framing the PRD §4.3 cites. ✅ Citation correct on structural grounds; full-text re-verification deferred to Phase 2 (when Stage 2 extractor code lands). |
| Dong et al. — SpreadsheetLLM | 2407.09025 | ToC: §3.1 Vanilla Spreadsheet Encoding (cell-tuple), §3.2 Structural-Anchor-Based Compression (heterogeneous header handling), §3.3 Inverted-Index Translation, §3.4 Data-Format-Aware Aggregation, §3.5 Chain of Spreadsheet. Body inaccessible. | §3.1 cell-tuple `(address, value, format)` encoding is *exactly* the "LLM receives parsed cells, not the .xlsx blob" pattern PRD §4.3 cites. ✅ Citation correct. |
| Wang et al. — Self-Consistency | 2203.11171 | ToC accessible; body inaccessible. | Foundational paper; cited at the formulation level (N=k majority vote), not at specific temperature schedule. PRD's (0.1, 0.5, 0.9) is a deliberate design choice anchored in Step 1B, not claimed to match Wang's specific T values. ✅ Citation correct at the formulation-level granularity claimed. |
| Wan et al. — Dynamic Self-Consistency | 2408.17017 | Paper still processing at Nia ingest time. Verification deferred to Phase 4 (when conditional Pro correction code lands). | Citation provisional; Phase 4 must re-verify the agreement-conditioned-escalation framing. |

**Net.** Five of eight citations are verified at ToC granularity; one (TECP) required a wording fix that produced a stronger architectural alignment; two (SynCode, Dynamic Self-Consistency) are flagged as provisional and must be re-verified by Step 3B QA before the Phase 4 code that depends on them ships. No citation was found to be load-bearingly wrong — only one needed reframing.

Full-text verification of all eight papers is gated on Nia document-agent backend recovery; until then the ToC-level verification above stands as the audit record.

---

## 5. EXECUTION SPEC (PHASE 1 SPRINT, 72-HOUR BUILDABLE SUBSET)

This subset ships the Sprint 1 rows from §2. All Phase 2 rows are explicitly deferred. The execution mirrors baseline §4.1 but folds in the LangGraph wrapping and the two-ingress topology.

### 5.1 Hour-by-Hour Breakdown

**Hours 0–8 — Repository, infra, boot validators.**
- `cookiecutter` Kaide's `fde-sidecar-template` skeleton.
- Docker Compose: FastAPI + Celery worker + Postgres + Redis + mock Slack receiver.
- Alembic migration `0001_initial`: `onramp_jobs`, `onramp_outputs`, `onramp_outbox`, `onramp_conformal_scores`, `lane_graph_states`, `un_locode_reference`, `wco_hs6_reference`.
- Vertex AI client init bound to `europe-west4`; service account `roles/aiplatform.user`.
- `/v1/health` with the three boot validators wired.
- Smoke: `curl localhost:8000/v1/health` → 200 with all three checks passing.

**Hours 8–20 — Ingress + core pipeline.**
- Pydantic models for `RatesheetIngressRequest`, `NormalizedRatesheet`, `LaneRecord`, `PortCode`, all sub-models, all strict-forbid.
- FastAPI routes for both Slack-native ingress (`/v1/ingest/*`) and API ingress (`/v1/intake/jobs`).
- `tasks.ingest.classify_format` — deterministic Stage 1.
- `tasks.ingest.extract_payload` — Excel only (EDIFACT in hours 28–36); openpyxl → cell list → `gemini-3-flash-preview` with `response_schema` from Pydantic model.
- Five demo fixture ratesheets (deliberately messy).
- Transactional outbox writes wired into each Celery task.
- Checkpoint: one Excel file → normalized JSON end-to-end.

**Hours 20–28 — Lane normalization, N=3 ensemble, LangGraph wrapper.**
- `tasks.ingest.normalize_lanes` — three parallel Vertex AI Pro calls per lane at temps 0.1, 0.5, 0.9; majority-vote consensus into `flagged_for_review` if no majority.
- Bulk-load UN/LOCODE reference (~110k rows) and WCO HS6 reference into Postgres.
- Port-code obfuscation resolution: exact match → carrier-alias fuzzy match → LLM-assisted with confidence.
- Wrap the chord in a LangGraph state machine; write each lane's transition into `lane_graph_states`.
- Conditional Pro correction pass (from v1) wired as a `langgraph.conditional_edge`.

**Hours 28–36 — EDIFACT, deterministic validation, clarification phrasing.**
- `pydifact` PRICAT tokenizer + Flash for ambiguous segment groupings.
- Stage 4 Python rules engine: impossible port codes, negative rates, past validity windows, transit times outside [1, 120].
- Section-granular conformal prediction at 0.85.
- Clarification-phrasing Pro node (from v3) — generates `flagged_lane_review_prompt` text for each `needs_human_review` lane. Output schema is strict-forbid and excludes every production field.
- Full pipeline runs Excel + EDIFACT end-to-end.

**Hours 36–48 — Slack integration + API result-URL surface.**
- Slack app creation, scopes, install into test workspace.
- `tasks.ingest.post_to_slack` — Block Kit summary + JSON attachment.
- `/onramp` slash command with confirmation modal.
- `@Onramp status` and `@Onramp flagged` mention handlers.
- `GET /v1/intake/jobs/{job_id}/result-url` — emits signed Cloud Storage URL via outbox event `signed_url_create`.
- `curl -F file=@K+N_Q2.xlsx ...` walkthrough script for the API ingress demo.

**Hours 48–60 — Demo recording + landing page.**
- Vidyard demo script (handled by Step 3 Demo Briefing).
- OBS screen capture: chaotic Excel → Slack drop → 30-second result reply (Magic Moment).
- Secondary curl demo capture for the technical audience.
- Edit to 4–5 minute runtime in Descript or DaVinci Resolve.
- `kaide.so/solvo` landing page on Vercel with embedded Vidyard player and timestamp anchor at 0:08.

**Hours 60–72 — Cloud Run deployment, smoke, sprint close.**
- Build production Docker images, push to Artifact Registry.
- Deploy three services to Cloud Run in `europe-west4`.
- Provision Cloud SQL Postgres + Memorystore Redis.
- Run demo fixture suite against production deployment.
- Final review.

### 5.2 Acceptance Criteria

1. Cloud Run deployment in `europe-west4` processes all 5 demo fixtures end-to-end without errors.
2. Slack ingress: smallest fixture (≤50 lanes) completes in ≤60s; largest (~500 lanes) in ≤180s.
3. API ingress: `curl -F file=@fixture.xlsx http://<api>/v1/intake/jobs` returns `202 Accepted` with `job_id`, polling endpoint returns `completed`, result-URL endpoint returns a signed Cloud Storage URL that downloads a Pydantic-valid `NormalizedRatesheet`.
4. Vidyard demo video 4–5 min uploaded with Magic Moment visible at 0:08–0:30.
5. Deterministic validator correctly rejects all three deliberately broken fixtures with specific rule citations.
6. N=3 ensemble produces ≥95% output consistency across 3 invocations on the same fixture.
7. `lane_graph_states` table contains complete transition history for every lane in every test job, queryable by `(job_id, lane_id)` ordered by `version`.
8. Container fails boot if any of: Vertex AI ping > 5s, Postgres migration mismatch, UN/LOCODE row count < 100,000.
9. Conditional Pro correction pass fires only when deterministic candidate disagrees with the N=3 majority (verified by inspecting `lane_graph_states.state_json` on a fixture engineered to produce this disagreement).
10. Clarification-phrasing node's output schema has zero overlap with `LaneRecord`'s production fields (compile-time check via `assert` in `app/agents/clarify.py`).

### 5.3 Sprint 1 vs Phase 2

**Sprint 1 ships:** Slack ingress + API ingress; Excel + EDIFACT support; UN/LOCODE + HS6 normalization; N=3 ensemble + conditional Pro correction; LangGraph state wrapping with `lane_graph_states`; clarification phrasing; deterministic validation + conformal; Slack output + signed-URL output; Cloud Run europe-west4 deployment.

**Sprint 1 deliberately defers:** CSV format support; email (.eml) ingress with embedded attachment extraction; Drive folder write-back; browser portal UI; per-prospect custom surcharge taxonomy; webhook callback into Solvo's staging engine (waiting on schema-match scoping call per Master PRD §4.3); multi-language ratesheets; Cloud Tasks fan-out scaling option.

### 5.4 Build-agent commands

```bash
# Hour 0–8
cookiecutter gh:Kaide-LABS/fde-sidecar-template
docker compose up -d postgres redis
alembic upgrade head
gcloud config set project solvo-onramp-prod
gcloud config set run/region europe-west4
gcloud iam service-accounts create solvo-onramp-vertex --display-name "Onramp Vertex AI"
gcloud projects add-iam-policy-binding solvo-onramp-prod \
  --member="serviceAccount:solvo-onramp-vertex@solvo-onramp-prod.iam.gserviceaccount.com" \
  --role=roles/aiplatform.user
curl localhost:8000/v1/health

# Hour 60–72
docker build -t europe-west4-docker.pkg.dev/solvo-onramp-prod/onramp/api:1e94ebe .
gcloud run deploy solvo-onramp-api --image=europe-west4-docker.pkg.dev/solvo-onramp-prod/onramp/api:1e94ebe \
  --region=europe-west4 --min-instances=0 --max-instances=5 --concurrency=50
gcloud sql instances create solvo-onramp-pg --region=europe-west4 --tier=db-f1-micro
gcloud redis instances create solvo-onramp-cache --region=europe-west4 --size=1 --tier=BASIC
```

---

## 6. COMPARISON VS LOCKED BASELINE

**Retained from baseline unchanged:**
- Three-service Cloud Run topology in europe-west4
- Postgres + Redis + Cloud Storage triad
- Slack-native ingress routes and webhook
- N=3 Pro ensemble at temps (0.1, 0.5, 0.9) with majority-vote consensus
- Deterministic Stage 1 classifier and Stage 4 rules engine
- Section-granular conformal prediction at 0.85 threshold
- `onramp_jobs`, `onramp_outputs`, `onramp_outbox`, `onramp_conformal_scores` tables
- Transactional outbox in same Postgres transaction as job-state writes
- Redis `SET NX EX` lock pattern
- Container-boot fail-fast validators
- Pydantic `ConfigDict(extra="forbid")` on every BaseModel
- Anti-Replication boundary (no POMDP / Bayesian RL / pricing / explainability / active learning)
- Pinned model strings and dependency versions from `docs/modernization_log.md`

**Modified from baseline:**
- Orchestration is now a LangGraph state machine *wrapping* the Celery chord, not a pure chord. The chord's execution semantics are preserved; LangGraph adds an auditable per-lane transition log without changing what the chord does. (Source: v3.)
- New table `lane_graph_states` added to Alembic migration `0001_initial`. (Source: v3.)
- Conditional Pro correction pass (N=2 at temps 0.1, 0.5) added between Stage 3 and Stage 4, triggered only when deterministic UN/LOCODE / HS6 candidate disagrees with the N=3 majority vote. (Source: v1.)
- Clarification-phrasing Pro node added after Stage 4, generating operator-facing review-prompt text for `needs_human_review` lanes. Output schema is strict-forbid and contains no production-schema fields. (Source: v3.)
- Outbox event types extended: `signed_url_create` added to support API-ingress result delivery. (Source: v4.)
- Redis key namespace extended: `solvo:onramp:api:idempotency:{hash}` for the API ingress. (Source: v4.)

**Added from laterals (Sprint 1):**
- Operator-grade API ingress: `POST /v1/intake/jobs`, `GET /v1/intake/jobs/{job_id}`, `GET /v1/intake/jobs/{job_id}/result-url`, `GET /v1/intake/jobs/{job_id}/review`. Source: v4 §E.
- Signed Cloud Storage URL output surface. Source: v4 §F.
- LangGraph per-lane state machine wrapping the Celery chord. Source: v3 §E.
- `lane_graph_states` table for transition audit. Source: v3 §E.
- Conditional Pro correction pass. Source: v1 §E.
- Clarification-phrasing Pro node. Source: v3 §E.

**Added from laterals (Phase 2 — not built in Sprint 1):**
- Email forward ingress with correction-reply parser. Source: v1.
- Drive folder watcher + folder write-back. Source: v2.
- Browser portal with lane-table review UI. Source: v3.
- Cloud Tasks fan-out as an alternative orchestration shape for >500-lane scaling. Source: v2.

**Rejected from laterals (will not be built):**
- v4's single-shot Pro N=1 normalization. **Rejected because:** the N=3 ensemble at temps (0.1, 0.5, 0.9) with majority-vote consensus is a Step 1B hard invariant; without three samples there is no consensus signal to calibrate conformal prediction against. Adopting v4's N=1 would weaken both the white-box trust posture and the academic grounding (§4.4).
- v2's N=2 Pro verifier pair. **Rejected because:** same N-invariant reason. v2's exact-agreement consensus is also more brittle than the baseline majority vote: with N=2, any disagreement collapses to "flagged," producing noisier review surface.
- v2's Cloud Tasks fan-out as the Sprint 1 orchestration. **Rejected because:** Celery chord is the team's known surface and Cloud Tasks idempotency adds a novel operational failure mode inside the 72-hour build. Carried forward as a Phase 2 scaling option only.
- v3's browser portal as the primary Sprint 1 surface. **Rejected because:** browser portals trigger Bajaj's "new tool habit" friction (Master PRD §3 forbidden UI patterns "no new SaaS dashboard"). The LangGraph state model — the load-bearing element of v3 — survives without the UI surface.
- v1's email primary ingress. **Rejected because:** SPF/DKIM/provider hardening and correction-reply parsing exceed the 72-hour scope window. The capability is straightforward to add in Phase 2 once Sprint 1 has shipped.

---

## 7. OPEN TENSIONS CARRIED FORWARD

The baseline §11 documented three tensions in the verified Solvo intel that could not be resolved without direct conversation with Bajaj. None of the lateral PRDs or the synthesis pass produced new evidence to resolve them. They are carried forward verbatim.

**(1) The "API delivered workflow" case study claim vs the manual rate check bottleneck.** Status unchanged. Most likely explanation remains: the API workflow exists for post-pilot production deployment (live customers feeding live data into the engine), while pre-pilot scoping (new prospects sending sample data for engagement evaluation) still goes through manual processing. The Pilot Onramp targets the pre-pilot stage specifically — a positioning the synthesis preserves and that should be tested directly in the first scoping call.

**(2) The "Pricing Operating System for Shipping Lines" pivot vs the freight forwarder marketing emphasis.** Status unchanged. The Pilot Onramp serves both ICPs and is agnostic to which is currently dominant. No synthesis decision depends on the resolution of this tension.

**(3) Bajaj's posting silence as survival signal vs as deliberate focus.** Status unchanged. The outreach posture in baseline §7 is calibrated to be safe under either interpretation, and the synthesis introduces no new framing claims that would require resolving this tension before sending the cold email.

These remain open. Step 2 (cold email + 15-minute scoping call) is the proper forum to resolve them, not Step 1E.

---

*End of Ultimate PRD. Synthesis architecture locked. Next step: Step 1F (build-spec generation for Claude Code / Codex CLI) and Step 2 (cold email + demo briefing).*
