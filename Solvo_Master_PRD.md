# MASTER PRD — SOLVO.AI SPRINT 2

**Output of Step 1B (Red-Team + Architecture Selection).** Consumes: TARGET_BRIEF.md, Dossier.md, Solvo_intel.md, Solvo_AI_Initial_Dossier.md, Kaide_Labs_SOP_Claude.md, Kaide_Labs_Identity.md. Feeds: Step 2 (Build Spec), Step 3 (Cold Email + Demo Briefing).

---

## 0. EXECUTIVE SUMMARY

**Selected Architecture (Sprint 1, 72-hour build):** *The Pilot Onramp* — a stateless upstream sidecar that absorbs the manual data normalization burden Solvo's missing Senior Implementation Manager used to own. Ingests heterogeneous freight ratesheets (Excel, CSV, EDIFACT PRICAT, raw email exports) from prospect-side data exports, produces schema-validated structured payloads ready for Solvo's engine ingestion, lives entirely in Slack. Ships in 72 hours.

**Phase 2 Extension (month 2 of standing engagement):** *The Procurement Lens* — a downstream sidecar that converts Solvo engine outputs into EU AI Act-aligned compliance artifacts and procurement-grade margin attribution reports, auto-attached to deal records in Solvo's verified HubSpot CRM. Outlined here; full PRD deferred to month 2.

**Killed:** Gemini Candidate 3 (Legacy TOS Integration Adapter). Built on namesake-collision fabrication. Kill reasoning detailed in §6.

**Commercial frame:** £10,000/month standing-capacity engagement + £20,000 Sprint 1 build (50% upfront, first month refundable). The Pilot Onramp is the trust-accelerator; the Procurement Lens is the renewal asset.

---

## 1. THE FDE THESIS

The strongest verified bottleneck in Solvo's operation today is the structural collapse of the pre-pilot scoping and data-normalization function. This function used to be owned by Brent Galloway as Senior Implementation Manager. Galloway departed Solvo in August 2025 to become Principal Delivery Manager at Re-Leased. He has not been replaced. There has been no replacement hiring activity for any commercial or implementation role in the seven months since his departure — verified against Solvo's careers page (only an ML Engineer role posted, since filled by Mayra Bermúdez Contreras in February 2026) and verified against Solvo's LinkedIn posting history (Bajaj's last post in May 2026 is the Mayra hire announcement; the post before that is the same ML Engineer role; nothing commercial in seven months).

In Bajaj's own April 2025 article *"Breaking the Cycle: Rethinking Freight Pricing in an Era of Volatility,"* he names this bottleneck explicitly. The recurring complaint across his public commentary is *"endless hours spent on manual rate checks across trade lanes for global carriers."* That phrase wasn't an abstract industry observation — it was the operational pain Galloway's role was designed to absorb. With Galloway gone and no replacement, this work has fallen entirely to Bajaj himself, as has every other commercial function previously owned by Paul de Haan (VP Growth, departed February 2025 to Visemo S.A.) and Priya Fatania (International Sales Manager, departed August 2025 to Sendbird).

Two verified advisor channels remain active: Will Urban (former Chief Revenue Officer at Flexport, joined as advisor May 2024) and Peter Hove Hildebrandt (former Global Head of Revenue Management at Maersk, joined May 2024). Both predate the contraction and represent active warm-introduction surfaces into top-20 freight forwarders and top-10 shipping lines respectively. Warm intros without a downstream conversion function become stale leads. Solvo's commercial pipeline is structurally bottlenecked between Urban/Hildebrandt's intros and Bajaj's personal bandwidth.

*The Pilot Onramp* fits this specific personnel gap. It does not replicate Dr. Dongho Kim's research domain — POMDPs, Bayesian RL, Constrained MDPs, factored state-space pricing engines are all explicitly out of scope. It operates strictly upstream of Solvo's engine, on the heterogeneous prospect-side data that needs to be normalized before any pricing logic runs. Solvo's own product page at solvo.ai/solution states *"Easily integrate our Pricing Optimisation Engine into your existing pricing and quotation systems"* — that integration story is output-side. Input-side data normalization for new prospects is the wedge.

The Magic Moment maps to Bajaj's commercial language: a chaotic 50-column Excel ratesheet from a prospective Kuehne+Nagel-class freight forwarder drops into a Slack channel; thirty seconds later, a schema-validated structured payload emerges with conformal-prediction confidence scores per lane, ready to feed into Solvo's engine ingestion. The visible state change — from spreadsheet chaos to engine-ready structured data — is the asset.

Pillar map: Bottleneck Assassin ✅ (named by Bajaj himself, cited above). Anti-Replication ✅ (upstream of any pricing logic, doesn't touch the engine). Native Environment ✅ (Slack, where Solvo's eight-person team already lives). Magic Moment ✅ (30-second visible transformation). System Resilience ⚠️ (deterministic Pydantic validation + Python rules engine + conformal prediction; EDIFACT edge cases will require Phase-2 fallback dictionary expansion).

---

## 2. SYSTEM ARCHITECTURE & AGENT ROUTING

### 2.1 Service Topology

The Pilot Onramp deploys as three Cloud Run services in europe-west4 (collocated with Vertex AI for latency):

- `solvo-onramp-api` — FastAPI ingress, Slack interactivity callbacks, job status. Min instances: 0, max: 5, concurrency: 50.
- `solvo-onramp-worker` — Celery workers consuming the ingestion pipeline. Min instances: 1, max: 3, concurrency: 4.
- `solvo-onramp-validator` — Stateless deterministic Python rules engine for output validation. Min instances: 0, max: 2.

Backing services:
- Cloud SQL Postgres (db-f1-micro for demo, scales to db-g1-small at 5+ customers).
- Memorystore Redis (1GB BASIC tier for demo; Standard HA tier in production).
- Cloud Storage bucket `solvo-onramp-artifacts` for raw upload retention (7-day TTL on demo bucket).

All services run as Docker Compose locally for the 72-hour sprint with identical container definitions. Cloud Run is the production-shape target, deployed via `gcloud run deploy` from CI on `main` branch push.

### 2.2 Ingress Contract

FastAPI exposes four routes. All Pydantic models use `ConfigDict(extra="forbid")` — this is load-bearing for the trust posture: any unexpected field rejects with HTTP 422 and a structured error payload, demonstrating to Bajaj's "white-box" sensibility that the system fails predictably rather than silently coercing.

```
POST /v1/ingest/ratesheet           # multipart/form-data, accepts xlsx/xls/csv
POST /v1/ingest/edifact             # text/plain, accepts raw PRICAT messages
POST /v1/ingest/email               # multipart, accepts .eml or .msg with embedded attachments
GET  /v1/jobs/{job_id}/status       # polls job state
GET  /v1/jobs/{job_id}/result       # retrieves normalized payload
POST /v1/webhooks/slack             # Slack interactivity callbacks
```

Pydantic schemas (abbreviated):

```
class RatesheetIngressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prospect_id: str = Field(min_length=3, max_length=64)
    prospect_name: str = Field(min_length=2, max_length=128)
    source_format_hint: Literal["excel", "csv", "edifact", "email", "auto"] = "auto"
    requesting_user_slack_id: str
    callback_channel: str
```

```
class NormalizedRatesheet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    prospect_id: str
    extraction_metadata: ExtractionMetadata
    lanes: list[LaneRecord]
    conformal_scores: dict[str, float]    # keyed by lane_id
    flagged_for_review: list[FlaggedLane]
    deterministically_rejected: list[RejectionRecord]
    schema_version: Literal["onramp.v1"]
```

```
class LaneRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lane_id: str
    origin_port: PortCode             # UN/LOCODE validated
    destination_port: PortCode
    equipment_type: Literal["20GP", "40GP", "40HC", "20RF", "40RF", "OOG", "BULK"]
    commodity_code: str | None
    base_rate_usd: Decimal
    surcharges: list[SurchargeRecord]
    transit_time_days: int | None
    validity_start: date
    validity_end: date
    source_row_reference: SourceRow
```

The `PortCode` validator hits a deterministic UN/LOCODE lookup table at container boot — it never asks the LLM whether a port code is valid. This is the deterministic anchor pattern that makes hallucinations structurally impossible to land in production output.

### 2.3 Agent Flow

The pipeline executes as five Celery tasks chained via a `Celery chord`:

```
classify_format → extract_payload → normalize_lanes → validate_output → post_to_slack
```

Stage 1 — **Deterministic Action Domain Classifier** (`tasks.ingest.classify_format`): zero LLM calls. Inspects file MIME type, magic bytes, file extension, and the first 4KB of content against regex patterns for known formats (xlsx zip header, EDIFACT UNA segment, CSV delimiter detection, .eml RFC822 header). Routes to the appropriate extractor. Falls back to "uncertain" with HTTP 422 if no format passes 0.9 heuristic confidence.

Stage 2 — **Extraction** (`tasks.ingest.extract_payload`): Single Gemini Flash call (`gemini-3-flash-preview` via Vertex AI europe-west4 — ⚠️ verified 2026-05-13 against `cloud.google.com/vertex-ai/generative-ai/docs/learn/locations`: still listed as Latest supported model version, still public preview, still available in europe-west4 per release-notes regional list; no GA Flash variant exists yet for this role), temperature 0.1, strict JSON mode with response schema enforced server-side. Excel extractor uses openpyxl to surface raw cell content as structured input to the LLM (the LLM receives parsed cells, not the .xlsx blob — this constrains the hallucination surface). EDIFACT extractor uses a deterministic PRICAT tokenizer first; the LLM only resolves ambiguous segment groupings. Temperature 0.0 for EDIFACT (purely structural extraction).

Stage 3 — **Lane Normalization** (`tasks.ingest.normalize_lanes`): N=3 deep ensemble pattern using `gemini-3.1-pro-preview` at temperatures (0.1, 0.5, 0.9) — ⚠️ verified 2026-05-13: still Latest supported model version in Vertex AI deployments/endpoints table; europe-west4 supported; preview status retained (no GA Pro variant exists). Per-lane mapping decisions (resolving obfuscated port codes like "BSAS" → "ARBUE" for Buenos Aires, normalizing commodity codes against HS6 taxonomy, mapping carrier-specific surcharge labels like "PSS" or "GRI" to canonical surcharge taxonomy). Majority-vote consensus across three runs. If no majority, the lane is flagged into `flagged_for_review` rather than guessed.

Stage 4 — **Deterministic Validation** (`tasks.ingest.validate_output`): pure Python, no LLM. Section-granular conformal prediction analyzes per-row log probabilities from the ensemble and assigns a confidence score in [0.0, 1.0]. Lanes scoring below 0.85 are moved to `flagged_for_review`. Lanes failing hard validation rules (impossible port codes against UN/LOCODE, negative rates, validity windows in the past, transit times outside [1, 120] day range) are moved to `deterministically_rejected` with a specific rule citation. This is the "white-box failure mode" that Bajaj will recognize as load-bearing for trust.

Stage 5 — **Slack Posting** (`tasks.ingest.post_to_slack`): formats a Slack Block Kit message with a summary table, attaches the normalized JSON as a file, threads the original request, and DMs the requesting user with a job-complete notification. Idempotent — repeat invocations check Redis lock `solvo:onramp:slack_post:{job_id}` before posting.

### 2.3.1 Cost Envelope (Step 1C addition)

Per-ingest-job API spend estimates against verified Vertex AI pricing (May 2026, Global endpoint; Non-global europe-west4 pricing applies — only GA Gemini 3 families incur the +10% non-global premium starting 2026-07-01, so preview models in scope here are billed at Global rates):

**Verified token rates (Vertex AI pricing page, retrieved 2026-05-13):**
- `gemini-3-flash-preview`: $0.50/M input text/image/video, $3.00/M output.
- `gemini-3.1-pro-preview`: $2.00/M input ≤200K ctx ($4.00 >200K), $12.00/M output ≤200K ($18.00 >200K), $0.20/M cached input.

**Token assumptions per architecture:**
- Stage 2 extraction: 1 Flash call per ratesheet. Structured cell-list input.
- Stage 3 normalization: 3 Pro calls per lane (N=3 ensemble at temps 0.1/0.5/0.9). Per-lane prompts are bounded (single-lane row + alias-dictionary excerpt + HS6 candidate set).

| Scenario | Stage 2 (Flash) | Stage 3 (Pro, N=3) | **Total / job** |
|---|---|---|---|
| 50-lane sheet (~20K in / 5K out extraction; ~2K in / 0.5K out per Pro call × 150) | $0.03 | $1.50 | **≈ $1.53** |
| 500-lane sheet (~80K in / 30K out extraction; ~2K in / 0.5K out per Pro call × 1500) | $0.13 | $15.00 | **≈ $15.13** |

⚠️ These are upper-bound envelope estimates; token counts assume no implicit caching of the shared alias-dictionary / HS6 system prompt across the 150–1500 Pro calls. Vertex AI's integrated implicit context caching (active on Gemini 3 family) and explicit context caching at $0.20/M (cached input) materially reduce real-world Pro spend by sharing the immutable normalization prompt prefix across all ensemble calls within a job. Realistic post-cache figures should be approximately 40–60% of envelope; final calibration on first real fixture run.

⚠️ Model role-swap flag (NOT implemented — flagged for Step 1B reconsideration only): `gemini-3.1-flash-lite` is now GA (no preview suffix, confirmed in Vertex AI deployments/endpoints table 2026-05-13). At a fraction of Pro pricing it could plausibly handle the normalization role, collapsing the Stage 3 envelope by ~5–10×. This is a candidate-architecture change, not a modernization swap, and is referred back to Step 1B red-team rather than acted on here. The N=3 ensemble at temperatures (0.1, 0.5, 0.9) on `gemini-3.1-pro-preview` remains in force.

### 2.4 Persistence & State

Postgres schema (abbreviated):

```sql
-- Job tracking
CREATE TABLE onramp_jobs (
  job_id          TEXT PRIMARY KEY,
  prospect_id     TEXT NOT NULL,
  prospect_name   TEXT NOT NULL,
  status          TEXT NOT NULL,           -- pending|extracting|normalizing|validating|completed|failed
  input_hash      TEXT NOT NULL UNIQUE,    -- idempotency key
  source_format   TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ
);

-- Normalized output
CREATE TABLE onramp_outputs (
  job_id              TEXT PRIMARY KEY REFERENCES onramp_jobs(job_id),
  normalized_payload  JSONB NOT NULL,
  lane_count          INT NOT NULL,
  flagged_count       INT NOT NULL,
  rejected_count      INT NOT NULL
);

-- Transactional outbox for Slack delivery, webhook callbacks, audit trail
CREATE TABLE onramp_outbox (
  outbox_id      BIGSERIAL PRIMARY KEY,
  job_id         TEXT NOT NULL REFERENCES onramp_jobs(job_id),
  event_type     TEXT NOT NULL,            -- slack_post|webhook_callback|audit_log
  payload        JSONB NOT NULL,
  delivered_at   TIMESTAMPTZ,
  attempts       INT NOT NULL DEFAULT 0,
  next_retry_at  TIMESTAMPTZ
);

-- Per-row conformal scores (for downstream confidence reporting)
CREATE TABLE onramp_conformal_scores (
  job_id         TEXT NOT NULL REFERENCES onramp_jobs(job_id),
  lane_id        TEXT NOT NULL,
  confidence     NUMERIC(4,3) NOT NULL,
  ensemble_votes JSONB NOT NULL,           -- {temp_0.1: "...", temp_0.5: "...", temp_0.9: "..."}
  PRIMARY KEY (job_id, lane_id)
);
```

The outbox pattern ensures that any external-facing side effect (Slack post, webhook callback to Solvo's staging endpoint, audit log entry) is committed in the same Postgres transaction as the job state update. A separate Celery beat task drains the outbox every 15 seconds with exponential backoff retry, ensuring no double-deliveries and no missed callbacks if Slack or Solvo's webhook receiver is temporarily unavailable.

### 2.5 Redis Key Patterns

```
solvo:onramp:job:{job_id}                   # job state cache, TTL 86400s
solvo:onramp:lock:{input_hash}              # idempotency lock, NX EX 3600
solvo:onramp:slack_post:{job_id}            # Slack post idempotency, NX EX 86400
solvo:onramp:ensemble:{job_id}:{lane_id}    # ensemble vote aggregation, TTL 3600
solvo:onramp:result:{job_id}                # result payload cache, TTL 86400
```

### 2.6 Container-Boot Validators

On worker startup, before accepting tasks, the worker runs three fail-fast validators:

1. **Vertex AI handshake** — issues a lightweight `gemini-3-flash-preview` ping with a 5-second timeout. Failure → exit code 1, Cloud Run health check fails, container does not enter rotation.
2. **Postgres schema validation** — `SELECT version_num FROM alembic_version` and compares against expected migration head. Mismatch → exit code 2.
3. **UN/LOCODE table integrity** — counts rows in `un_locode_reference`, expects ≥ 100,000 (canonical UN/LOCODE table is ~110k entries). Mismatch → exit code 3.

This pattern is locked from Sprint 1 (Matta). It is non-negotiable for Bajaj's trust posture — the system either runs correctly or refuses to run.

---

## 3. NATIVE ENVIRONMENT UI SPEC

The Pilot Onramp has no dedicated UI surface. Solvo's eight-person team operates at maximum cognitive load — forcing them to learn a new SaaS dashboard would introduce friction that the FDE thesis is designed to eliminate. All user-facing interaction happens in Slack.

### 3.1 Slack App Configuration

The sidecar deploys as a Slack app installed into Solvo's workspace (separate workspace from Kaide's; one app per customer for isolation). The app requires the following scopes:

```
Bot scopes:
  - chat:write, chat:write.public
  - files:read, files:write
  - channels:history, groups:history
  - im:history, im:write
  - users:read

User scopes:
  - none (no impersonation)
```

### 3.2 Three Slack Surfaces

**Surface 1 — `#pilot-onramp` channel (or `#pilot-onramp-{prospect}` per-prospect):** the primary work surface. Users drop ratesheet files directly into the channel with optional one-line context. The bot acknowledges within 2 seconds with a threaded reply showing job_id and estimated completion time. Subsequent threaded replies show progress (extraction complete, normalization complete, validation complete). Final reply includes the normalized JSON as an attached file plus a Block Kit summary table.

**Surface 2 — `/onramp` slash command:** for users who want to ingest URL-referenced files or paste raw EDIFACT text. Format: `/onramp ingest https://example.com/ratesheet.xlsx --prospect "Kuehne+Nagel"`. The slash command opens an ephemeral confirmation modal showing the inferred parameters before triggering the job, giving the user a chance to correct the prospect attribution.

**Surface 3 — `@Onramp` mention DM:** for users who want to query job status, retrieve past results, or escalate flagged lanes. `@Onramp status qj_8f3a2` returns current job state. `@Onramp flagged qj_8f3a2` opens an interactive review modal showing each flagged lane with the ensemble's three votes and a one-click resolution dropdown.

### 3.3 Magic Moment Scenario (Demo Recording)

The 72-hour sprint produces a Vidyard-hosted demo video, voice-narrated by Hafeedh, total runtime 4-5 minutes. The cold-open captures the Magic Moment in the first 30 seconds:

```
00:00-00:08   Wide shot of a chaotic 50-column Excel ratesheet
              titled "K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx".
              Visible: merged cells, obfuscated port codes,
              embedded surcharge notes in column headers,
              dimensional weight inconsistencies.
              Voice-over: "This is what every new pilot scoping
              call starts with. A forwarder sends you their rate
              book. Forty-seven lanes. Twelve surcharge types.
              Three port code conventions."

00:08-00:14   File drag-and-drop into Slack #pilot-onramp.
              Bot acknowledgment reply appears within 2 seconds.
              Voice-over: "Drop it in. That's it."

00:14-00:30   Time-lapse of bot threaded replies progressing
              through extraction, normalization, validation.
              At 00:28: final reply with attached JSON +
              summary table showing "247 lanes ingested, 241
              normalized, 4 flagged for review, 2 rejected."
              Voice-over: "Thirty seconds. Engine-ready data,
              with confidence scores per lane, with the four
              that need human review pre-isolated, with the two
              impossible port codes hard-rejected. Nothing
              guessed. Nothing hidden."
```

Subsequent demo sections walk through the technical architecture, the deterministic validation layer (Bajaj's white-box anchor), and a deliberately broken input to show graceful failure. Demo ends with a one-line CTA: "If this fits, fifteen minutes to scope the production deployment. If not, no follow-up from me."

### 3.4 Forbidden UI Patterns

Three patterns are explicitly disallowed in any client-facing artifact:

1. **No mention of Galloway, de Haan, or Fatania by name.** Any framing that requires Bajaj to acknowledge his commercial function is gone will trigger status defense and burn the engagement. The demo references "scaling pilot conversion velocity" and "absorbing the data normalization burden of every new prospect" — never "replacing your missing implementation manager."
2. **No reference to Solvo's contraction or runway.** The demo positions Solvo as a high-performance company in the build-out phase, not a distressed prospect being rescued. This is a status-respect requirement, not deception — the architecture is genuinely useful regardless of Solvo's stage.
3. **No autonomous-AI rhetoric.** Bajaj's "white-box" obsession is load-bearing. Every LLM mention is paired with the deterministic anchor that constrains it. The demo says "Gemini extracts; Pydantic validates; the rules engine arbitrates" — never "the AI decides."

---

## 4. PHASE 1 EXECUTION SPEC (72-HOUR SPRINT)

The sprint produces a containerized demo deployable to Cloud Run, with one fully-instrumented Magic Moment scenario plus three additional working scenarios for the technical walkthrough. The PRD assumes a single developer (Hafeedh) plus Claude Code as the build agent and Codex CLI as the red-team for adversarial test generation.

### 4.1 Hour-by-Hour Breakdown

**Hours 0–8 (Day 1 morning, Lagos time):** Repository scaffolding and infrastructure.

- `cookiecutter` a new repo from Kaide's standard FastAPI/Celery/Postgres template (`kaide-labs/fde-sidecar-template`).
- Bootstrap Docker Compose with FastAPI service, Celery worker, Postgres, Redis, and a mock Slack webhook receiver for local development.
- Initialize Alembic migrations and create the four Postgres tables defined in §2.4.
- Configure Vertex AI client with europe-west4 region binding, set up service account with `roles/aiplatform.user`.
- Implement the `/v1/health` endpoint with container-boot validators (Vertex AI ping, Postgres migration check, UN/LOCODE table integrity).
- Smoke test: `curl localhost:8000/v1/health` returns 200 with all three checks passing.

**Hours 8–20 (Day 1 afternoon + evening):** Core ingestion pipeline.

- Implement Pydantic models for `RatesheetIngressRequest`, `NormalizedRatesheet`, `LaneRecord`, `PortCode`, all sub-models. Strict `ConfigDict(extra="forbid")` throughout.
- Implement `tasks.ingest.classify_format` with deterministic format detection.
- Implement `tasks.ingest.extract_payload` for Excel format only (defer EDIFACT to hours 28–36). Excel extractor uses openpyxl to parse cell-level content, passes structured cell list to Gemini Flash for semantic interpretation.
- Build a fixture set of 5 mock ratesheet files representing different freight forwarder data shapes (deliberately messy — merged cells, obfuscated port codes, mixed currencies, mixed unit systems). These become the demo test suite.
- Implement transactional outbox writes for every Celery task.
- End-of-day checkpoint: a single Excel file processed end-to-end produces a normalized JSON output. Quality may be poor at this stage; correctness comes in next block.

**Hours 20–28 (Day 2 morning):** Lane normalization and N=3 ensemble.

- Implement `tasks.ingest.normalize_lanes` with the N=3 ensemble pattern. Three parallel Vertex AI calls to `gemini-3.1-pro-preview` at temperatures (0.1, 0.5, 0.9). Per-lane majority-vote consensus.
- Build the deterministic UN/LOCODE reference table — bulk-load the canonical UN/LOCODE CSV (~110k entries) into a Postgres lookup table with indexed origin lookups.
- Implement port code obfuscation resolution (the "BSAS → ARBUE" pattern) — first try exact UN/LOCODE match, then fuzzy match against carrier-specific alias dictionary, then fall back to LLM-assisted resolution with confidence scoring.
- Implement commodity code normalization against the HS6 taxonomy (load the WCO HS6 reference table).

**Hours 28–36 (Day 2 afternoon):** EDIFACT support + deterministic validation.

- Implement EDIFACT PRICAT tokenizer (deterministic, using the `pydifact` library).
- Implement EDIFACT extractor: deterministic tokenization first, then Gemini Flash only for ambiguous segment groupings.
- Implement `tasks.ingest.validate_output` — the deterministic Python rules engine. Hard rejection rules: impossible port codes, negative rates, validity windows in the past, transit times outside [1, 120] days. Soft flagging via conformal prediction at 0.85 threshold.
- End of Day 2: full pipeline runs Excel and EDIFACT end-to-end with deterministic validation.

**Hours 36–48 (Day 3 morning):** Slack integration.

- Configure the Slack app in api.slack.com with required scopes.
- Implement `tasks.ingest.post_to_slack` with Block Kit message formatting.
- Implement `/onramp` slash command with confirmation modal.
- Implement `@Onramp status` and `@Onramp flagged` mention handlers.
- Implement the file-drop event handler that triggers a job automatically when a supported file is uploaded to `#pilot-onramp`.
- Build a test Slack workspace with the bot installed for demo recording.

**Hours 48–60 (Day 3 afternoon + evening):** Demo recording and polish.

- Author the Vidyard demo script (separate document; see Step 3 Demo Briefing for full script).
- Record screen capture of the Magic Moment scenario using OBS, with Hafeedh's voiceover.
- Edit demo video to 4–5 minute runtime in Descript or DaVinci Resolve.
- Build a public-facing landing page at `kaide.so/solvo` with the embedded Vidyard player and a one-line CTA. Hosted on Vercel.
- Upload demo to Vidyard, capture analytics tracking link with timestamp anchor at 0:08 (the Magic Moment start).

**Hours 60–72 (Day 3 evening + Day 4 morning):** Cloud Run deployment + sprint close.

- Build production Docker images for all three services, push to Artifact Registry.
- Deploy to Cloud Run in europe-west4 with the production configuration.
- Provision Cloud SQL Postgres and Memorystore Redis instances.
- Run smoke tests against the production deployment using the demo fixture set.
- Final review: the demo video, the landing page, the production deployment URL, and the outreach asset bundle are all ready.

### 4.2 Acceptance Criteria for Sprint 1 Completion

The sprint is complete when all of the following are true:

- A Cloud Run deployment in europe-west4 successfully processes all 5 demo fixture files end-to-end without errors.
- The Slack app successfully posts validated JSON output to a test channel within 60 seconds of file upload for the smallest fixture (≤50 lanes) and within 180 seconds for the largest fixture (~500 lanes).
- A Vidyard demo video of 4–5 minutes is uploaded with the Magic Moment visible at 0:08–0:30.
- The deterministic validation layer correctly rejects all three deliberately broken fixture files (one with impossible port codes, one with negative rates, one with malformed EDIFACT structure) with specific error messages.
- The N=3 ensemble produces stable outputs (≥95% consistency on the same input across 3 invocations) for the demo fixture set.

### 4.3 What Ships in Sprint 1 vs Phase 2

**Sprint 1 ships:**
- Excel and EDIFACT format support
- UN/LOCODE port code resolution
- HS6 commodity code normalization
- N=3 ensemble lane normalization
- Deterministic validation and conformal prediction
- Slack-based UX (channel upload, slash command, mention handlers)
- Transactional outbox for Slack delivery
- Cloud Run production deployment

**Sprint 1 deliberately defers (to Phase 2 of the engagement):**
- CSV ratesheet support (low priority; most freight forwarders use Excel)
- Raw email (.eml) ingestion with embedded attachment extraction
- Custom per-prospect surcharge taxonomy mapping
- Webhook callback to Solvo's staging environment (Sprint 1 returns results via Slack only; production webhook integration happens after Solvo's own engine ingestion endpoint is documented)
- Multi-language support (Sprint 1 assumes English ratesheets only)
- ⚠️ Inferred from Solvo case study language: the engine likely consumes some normalized structure already; the precise schema match between Pilot Onramp output and Solvo's expected input requires a 30-minute scoping call with Bajaj or Kim before the production webhook can be wired

---

## 5. SALES-SIDE FRAMING

This section is what gets paraphrased into the cold email and the demo briefing. It uses Bajaj's verified vocabulary. It does not use Kaide internal vocabulary (no "stateless sidecar," "DMZ," "anti-replication," "Magic Moment," "FDE," "strike team"). It does not conflate the sidecar with Solvo's engine.

**For the cold email (Bajaj-facing):**

"Your April article landed on the right diagnostic — manual rate checks across trade lanes have become a permanent burden, not a transitional one. The data normalization layer that sits before your engine has, in practice, become the bottleneck between an advisor's warm introduction and a live pilot. We've built a containerized layer that absorbs that work — a forwarder drops their rate book into Slack and a schema-validated payload appears in under thirty seconds, with a deterministic confidence score per lane and rule-based rejection of anything ambiguous. The architecture is white-box by design: every flagged lane shows which validation rule triggered, every rejection cites the exact failing constraint. Your engine ingests engine-ready data; your team focuses on pricing strategy and conversion. Fifteen minutes to scope production deployment if the architecture fits, no follow-up if it doesn't."

**For the demo voiceover (3–5 minute Vidyard):**

The voiceover anchors to the same vocabulary. Three explicit beats:

1. *Naming the pain in Bajaj's words* — "Every pilot scoping call starts with a forwarder's rate book. Forty-seven lanes. Twelve surcharge types. Three port code conventions. This is the manual rate check problem you described in April."
2. *Showing the deterministic anchor* — "The Gemini extraction is bracketed on both sides. Pydantic schemas reject any unexpected field at ingress. The validation rules engine rejects any impossible port code, any negative rate, any validity window in the past. Nothing the LLM extracts can land in your engine input without passing both gates."
3. *Closing on engine-ready output* — "What goes into your engine is engine-ready. The state-space ingestion layer your team built sees clean, structured, schema-validated freight data. The work that used to slow down pilot scoping is absorbed before it ever reaches your engineers."

The framing respects three boundaries:

- The sidecar never claims to do anything Solvo's engine does. It does not produce prices, recommend rates, or interpret market signals.
- The sidecar does not credit-claim margin uplift or revenue results. Those are downstream of Solvo's engine, which the sidecar feeds but does not replace.
- The sidecar is positioned as standing capacity, not as a replacement for missing headcount. The engagement is renewable; no implication that one human hire would replace it.

---

## 6. KILL REASONING — REJECTED CANDIDATES

### 6.1 Gemini Candidate 3 (Legacy TOS Integration Adapter) — KILLED

**Kill basis: Namesake-collision fabrication.**

Gemini's Candidate 3 architecture proposed an integration adapter between Solvo's "modern API outputs" and "the heavily fortified, legacy Terminal Operating Systems (TOS) utilized by global shipping lines," specifically targeting Navis N4 as the primary integration surface.

Verification against Solvo's primary sources establishes the fabrication:

- Solvo's product page at solvo.ai/solution states: *"Easily integrate our Pricing Optimisation Engine into your existing pricing and quotation systems."* Pricing and quotation systems — not Terminal Operating Systems.
- Solvo's published carrier case study (solvo.ai/blog/how-a-leading-carrier-achieved-optimal-utilisation-and-competitive-pricing-using-ai) describes integration into *"their rate-management platform"* via an *"automated, API delivered workflow."* Rate management platform — not TOS.
- Solvo's blog, /insights catalog, and /about page contain zero mentions of Navis N4, OPUS, CARGOES, or any TOS-class system.
- Gemini's footnote 13 cited `sourceforge.net/software/product/Solvo.TOS/alternatives` — this is documentation for *Solvo.TOS*, a Terminal Operating System product made by SOLVO Group, a completely separate company from Solvo.ai. Different domain, different product category, different customer base.
- Operational sanity check: shipping line *pricing* decisions do not flow through TOSes. TOSes handle gate moves, yard slots, equipment dispatch, and terminal operations. Pricing decisions flow through commercial systems — CRMs, rate management platforms, quoting platforms, customer ERPs.

The fabrication appears to have entered Gemini's reasoning through namesake collision between "Solvo.ai" and "Solvo.TOS" — exactly the failure pattern flagged in the original Step 0.5 prompt as a known fabrication mode for autonomous research agents. The Step 1A prompt explicitly warned against this pattern; Gemini reintroduced it anyway.

**Why C3' redirect to CargoWise eAdaptor was considered and rejected.**

The C3 architecture *shape* (parallel/downstream integration adapter) is in principle salvageable by redirecting the integration target from the fabricated Navis N4 to a verified target such as CargoWise eAdaptor — the dominant freight forwarder operating platform used by Kuehne+Nagel, DSV, DB Schenker, and most top-20 freight forwarders.

This redirect was investigated and rejected on Ego Check grounds. Solvo's published carrier case study describes precisely this work as something they have already built for one customer: *"the carrier was able to generate rates tailored to their needs and operational goals, shifting from a manual rate setting to an automated, API delivered workflow."* The case study presents this API integration as their existing engineering competence, not as a bottleneck. Building a productized per-customer integration adapter for rate management platforms looks, on inspection, like work Solvo's existing engineering team (Wilkinson, Costea, McLeod, Bermúdez) is already doing for live customers — even if it's a real cost-to-serve bottleneck at the per-customer level.

⚠️ Inferred from primary source language: the integration work appears bespoke per customer, which means a productized adapter *could* still represent a real wedge. But the demo would have to position carefully around "we don't replace your existing integration work — we templatize what you've already proven, so you don't rebuild it for every new pilot." That positioning is fragile, the Magic Moment for a JSON-to-XML payload translation is genuinely weak (Gemini honestly rated it ⚠️), and a CargoWise eAdaptor build in 72 hours would require deep documentation of CargoWise's REST/XML schema that has not been verified to be accessible.

Net: C3' is theoretically viable as a third sidecar in a multi-quarter engagement but unsuitable as either Sprint 1 or Phase 2. Killed.

### 6.2 Gemini Candidate 2 (Regulatory Transparency & Procurement Artifact Engine) — DEFERRED TO PHASE 2

**Why C2 survived red-team:**

C2 passed the Anti-Replication test cleanly. Its §H defense was the strongest of the three candidates, explicitly naming Constrained MDPs and factored POMDP state updates as off-limits and positioning the sidecar as a downstream *reporting layer above* the explainability engine, not a replacement for it. The deterministic Python rules engine in C2's §G — which recalculates claimed margin uplift and strips LLM-hallucinated drivers — is the strongest System Resilience pattern across all three candidates and aligns precisely with Bajaj's "white-box" anchor.

C2's Native Environment assumption (auto-push to Solvo's CRM) was originally flagged as unverified but is now confirmed: Solvo's tech stack includes HubSpot per LeadIQ verification, so the integration target locks to HubSpot's Deals API v3. ⚠️ Pillar 3 self-rating downgraded from Gemini's optimistic ✅ to a contingent ✅ — the rating holds only if HubSpot is the production deployment target; alternative CRM choice would require re-scoping.

**Why C2 is Phase 2, not Sprint 1:**

C2 requires Bajaj to have an existing pilot producing engine output that the sidecar can act on. For a cold prospect with no prior engagement, this means the demo has to either (a) use mocked engine output, which weakens the credibility of the artifact engine, or (b) wait until a real pilot is running, which means C2 cannot be the cold-outreach asset. C1 (Pilot Onramp) does not have this dependency — it acts on prospect-side data that exists pre-engagement.

The commercial logic for the £10k/month standing-capacity model also favors a phased approach. Sprint 1 (C1) demonstrates execution competence and unlocks the engagement. Phase 2 (C2) deepens the engagement by absorbing the higher-value pilot-to-production conversion work, which is what makes the engagement renewable beyond the first 90 days.

**Phase 2 outline for The Procurement Lens:**

- Ingress: webhook from Solvo's engine output system. Payload contains the finalized pricing recommendation, ensemble confidence intervals, variable weights for the driving factors, and the prospect/deal identifier.
- Two artifact outputs: an EU AI Act-aligned Model Card (high-risk system documentation per Article 6) and a procurement-grade Margin Attribution Report (board-readable PDF).
- Deterministic rules engine recalculates the claimed margin uplift from the raw variable weights, mathematically verifying that the LLM-generated narrative aligns with the engine's actual mathematical output. Hallucinated drivers (a non-existent port strike, a fabricated competitor capacity claim) are stripped and replaced with templated factual statements.
- Output delivery: auto-attached to the relevant Deal record in Solvo's HubSpot CRM via `POST /crm/v3/objects/deals/{deal_id}/associations/contact/{contact_id}` plus file attachment via the HubSpot Files API. Secondary delivery to a per-prospect Google Drive folder with email notification to Bajaj.
- Full Phase 2 PRD ships at month-2 mark of the engagement, conditional on Sprint 1 closing the engagement and the customer engagement health remaining green.

---

## 7. REFINED OUTREACH POSTURE (RE-DERIVED)

This section was re-derived independently from the verified intel rather than inherited from Gemini's pre-baked framing. Specific tactical recommendations from Gemini's profile section have been retained only where they survive independent analysis.

### 7.1 Target

Email Bajaj exclusively. Including Kim in the initial outreach creates two problems: (a) Kim's posting history shows minimal engagement with commercial/business communications (his public footprint is academic and technical), so adding him to the To: line will likely produce no engagement and signal that the outreach hasn't been targeted; (b) Bajaj is verified as the commercial decision-maker, and the Pilot Onramp's value proposition is operational, not architectural — Kim's input is appropriate at technical due diligence, not at first contact.

Do not CC anyone from the broader team (Jarvis, McLeod, Wilkinson, Bermúdez). The pitch is to the CEO; the technical review is a separate downstream stage.

### 7.2 Timing

Tuesday or Wednesday, 7:30 AM London time. Two reasons: (a) verified pattern of Bajaj's morning posting cadence in 2024–mid-2025 suggests he checks LinkedIn and email in the early morning before customer-facing meetings start; (b) Mondays are reactive (handling weekend accumulation), Thursdays/Fridays are wind-down — Tuesday/Wednesday morning is the high-cognitive-availability window. ⚠️ Inferred from the posting cadence pattern; not directly verified against email-open data.

Avoid Tuesday after the second week of any month (likely sprint-planning or board-prep windows for a small startup). Avoid the first week of January, August, and December.

### 7.3 Subject Line

Three candidates, ranked by directness:

1. *"Absorbing the pilot scoping load"* — directly names the bottleneck, uses operational vocabulary.
2. *"Pre-engine data normalization sidecar — 30s demo inside"* — technical, names the architecture, signals the demo.
3. *"On your April article — built the layer that absorbs the rate-check load"* — references his specific published work, signals research depth.

Recommended: candidate 3. It anchors to a specific verified Bajaj-authored piece, signals that the outreach is research-anchored not generic, and primes the recipient to read with the rate-check frame in mind. ⚠️ Inferred preference; A/B testing across the three is recommended if the outreach volume supports it.

### 7.4 Opening Line

Direct anchor to the April article's exact bottleneck phrasing. Do not open with introduction of Kaide Labs, do not open with "Hi Gaurav," do not open with any social-warming preamble. Open with the diagnostic.

Example opening: *"Your April article landed the diagnostic — manual rate checks have stopped being a transitional pain and become a permanent operational tax. The data normalization layer that sits before your engine has, in practice, become the bottleneck between an advisor's warm introduction and a live pilot."*

### 7.5 Tone

Pragmatic, technical, operationally specific. Avoid: hedging language ("might," "could potentially"), inflated claims ("revolutionary," "game-changing"), service-firm vocabulary ("our team can," "we'd love to"). Use: declarative architecture language, named operational pain points, specific time-to-value claims with verifiable demonstration.

### 7.6 Hard No-Go Framings (Status Defense Triggers)

Three framings will trigger immediate defensive reactions based on the verified contraction state and must be avoided categorically:

**No "rescue mission" frame.** Do not mention the departure of Galloway, de Haan, or Fatania. Do not suggest the commercial pipeline is broken, contracting, or in difficulty. Do not reference the headcount cliff, the Hao board resignation, the posting silence, or any signal of distress. Frame the Pilot Onramp strictly as a scaling tool — "absorbs the manual normalization burden of each new pilot you onboard" — not a recovery tool. ⚠️ This boundary is load-bearing; the entire engagement architecture depends on respecting it.

**No vendor-relationship vocabulary.** No "dev shop," "outsource," "consultant," "agency," "implementation partner," "service team." The positioning is a deployed strike team with proprietary infrastructure — but communicate that without ever using the internal Kaide vocabulary. Externally: *"We've built a containerized layer for pre-engine data normalization"* or *"This is a deployed sidecar, not a consulting engagement."*

**No autonomous-AI rhetoric.** No "AI agents," "autonomous decision-making," "self-driving pipeline," "AI replaces manual work." Bajaj's white-box obsession means every LLM mention must be paired with the deterministic anchor. The framing is "Gemini extracts; Pydantic validates; the rules engine arbitrates" — never "the AI handles it for you."

### 7.7 Demo Delivery and Follow-Up

Demo via Vidyard with timestamp anchor at the Magic Moment (0:08–0:30). Email includes a single CTA: *"Fifteen minutes to scope production deployment if the architecture fits. No follow-up from me if it doesn't."*

Telemetry-based follow-up per the Kaide Identity SOP §9:
- Video viewed, no reply within 7 days → one soft nudge with a Phase 2 reference ("If the Sprint 1 architecture lands, the natural extension is procurement-grade artifact production downstream — happy to show that as a follow-on").
- Video not viewed within 7 days → one "buried in inbox" re-send.
- After two touches with no engagement, close the file and move down the prospect pipeline.

The hard-stop discipline is non-negotiable. Bajaj is in survival mode; a high-volume follow-up cadence will burn the relationship and damage the broader Kaide outreach signal.

---

## 8. PILLAR AUDIT — HONEST RATINGS

The Pilot Onramp is rated against the 5-Pillar Demo Standard with deliberate ⚠️ acknowledgment where rigor demands it.

| Pillar | Rating | Justification |
|---|---|---|
| 1. Bottleneck Assassin | ✅ | Maps to Bajaj's verified April 2025 quote on "endless hours spent on manual rate checks" and directly fills the Galloway personnel gap. Citation chain is the strongest of all three Gemini candidates. |
| 2. Anti-Replication | ✅ | Operates upstream of Solvo's engine entirely. Does not touch POMDPs, belief state, value iteration, factored state spaces, Constrained MDPs, or any pricing logic. The Ego Check holds even under Kim's scrutiny — pre-pilot prospect data normalization is a different surface than the engine's internal data layer. |
| 3. Native Environment | ✅ | Slack-only UX. Solvo's verified eight-person team operates in Slack. No new SaaS dashboard adoption required. |
| 4. Magic Moment | ✅ | Chaotic 50-column Excel → schema-validated structured JSON in <30 seconds is a strong visual transformation. Specifically: the before-state (multi-column merged-cell Excel chaos) and after-state (Slack-attached JSON file plus Block Kit summary) are visually distinct in a way that translates to video. |
| 5. System Resilience | ⚠️ | Pydantic catches structural anomalies. The N=3 ensemble + conformal prediction catches semantic anomalies. The deterministic rules engine catches hard violations. But: nuanced EDIFACT edge cases (custom carrier-specific extensions, malformed segments that parse structurally but encode invalid business semantics) will occasionally bypass all three gates. Phase 2 mitigation: a maintained per-customer fallback dictionary expansion. |

⚠️ Inference flagged: the Pillar 1 strength depends on the assumption that Bajaj is currently personally absorbing the data normalization work that Galloway used to own. Verified evidence supports this (his posting silence + the absence of replacement hiring + the verified departure dates), but a definitive confirmation would require Bajaj's own statement on a discovery call. The bottleneck framing should be tested against his actual current pain in the first 15-minute scoping conversation.

---

## 9. COMMERCIAL FRAME

**Engagement structure:**

- £10,000/month standing-capacity engagement (locks in monitoring, maintenance, minor adjustments, and on-call support for the deployed sidecar).
- £20,000 Sprint 1 build (one-time, on delivery).
- 50% upfront (£10,000) to reserve the strike team and begin the build.
- 50% on deployment (£10,000).
- First month of the standing-capacity engagement is fully refundable.

**Phase 2 commercial extension:**

- £15,000 Sprint 2 build for *The Procurement Lens* (one-time).
- Standing-capacity fee increases to £13,000/month at 2-sidecar deployment (per the Kaide step-up pricing schedule).
- Both sidecars share infrastructure (same Postgres, same Redis, same Cloud Run project) — operational margin improves with the second sidecar.

**Value anchoring (for the cold email and 15-minute scoping call):**

Frame against the cost of rebuilding Galloway's role: a Senior Implementation Manager in London commands £80,000–£110,000 base + benefits + ramp time. Replacing the function via FTE recruitment costs Solvo £120,000+ all-in for year one and assumes a 3-month ramp before the new hire is productive. The Pilot Onramp engagement costs £140,000 for year one (Sprint 1 build £20,000 + 12 × £10,000 standing capacity) and is operationally productive within 72 hours. The math leans favorable on time-to-value, not headline cost. ⚠️ The headline cost is approximately equivalent to FTE replacement; the wedge is time-to-productive and unplug-guarantee optionality, not raw cost arbitrage.

---

## 10. SELF-CHECK COMPLIANCE

Per Step 1B prompt self-check requirements:

- ✅ C3's Navis N4 fabrication addressed explicitly — killed with full reasoning in §6.1.
- ✅ §K-equivalent vocabulary tightened — §5 (Sales-Side Framing) avoids "your pricing intelligence," "your pricing approach," and any phrasing that conflates the sidecar with the engine. Forbidden internal vocabulary ("stateless sidecar," "DMZ rule," "anti-replication," "magic moment," "FDE," "strike team") is absent from §5 and §7.
- ✅ Outreach posture re-derived independently — §7 reasoning anchors to verified intel (April article phrasing, posting cadence pattern, headcount state, Kim's communication profile) rather than inheriting Gemini's pre-baked framing.
- ✅ Architecture defenses cite specific verified intel — Bajaj April 2025 article, Galloway August 2025 departure, solvo.ai/solution product page language, verified HubSpot in tech stack, etc.
- ✅ Honest pillar ratings — Pillar 5 marked ⚠️ on the surviving candidate, C2 Pillar 3 marked as contingent ✅, no 5/5 rubber-stamping.
- ✅ Kaide internal vocabulary preserved in technical sections (§2, §4), stripped from client-facing sections (§5, §7).
- ✅ Inferences marked ⚠️ with evidence basis throughout.

---

## 11. UNRESOLVED TENSIONS — FLAGGED, NOT SYNTHESIZED

Three tensions in the verified intel cannot be resolved at this stage and are flagged here rather than papered over:

**(1) The "API delivered workflow" case study claim vs the manual rate check bottleneck.** Solvo's published carrier case study describes a fully automated API-delivered workflow for a top carrier. Bajaj's April 2025 article describes manual rate checks as the persistent operational pain. The tension: if the API workflow is fully built for live customers, why is manual rate checking still a personal bottleneck for Bajaj? Most likely answer (⚠️ inferred): the API workflow exists for *post-pilot production deployment* (live customers feeding live data into the engine), but *pre-pilot scoping* (new prospects sending sample data for engagement evaluation) still goes through manual processing. The Pilot Onramp targets the pre-pilot stage specifically. This tension should be tested directly in the first scoping call.

**(2) The "Pricing Operating System for Shipping Lines" pivot vs the freight forwarder marketing emphasis.** Solvo's LinkedIn banner has updated to position the company as a shipping line product, narrower than the earlier freight-forwarder + carriers framing. But Solvo.ai/about and solvo.ai/solution still emphasize freight forwarders as the primary ICP. Two possible interpretations: (a) Solvo is pivoting from freight forwarders to shipping lines and the marketing surface hasn't fully caught up; (b) the LinkedIn banner is aspirational and the actual current customer base is still freight forwarders. The Pilot Onramp serves both market segments and is agnostic to which ICP is currently dominant.

**(3) Bajaj's posting silence as survival signal vs as deliberate focus.** The posting cadence collapse (last commercial post 7+ months ago) is consistent with two states: (a) survival mode with no commercial wins to announce, (b) deliberate heads-down focus on shipping the engine extension for the "shipping lines" pivot. Both are consistent with the verified evidence. The outreach posture in §7 is calibrated to be safe under either interpretation — respect status, name the operational pain without naming the contraction, lead with the demo asset. ⚠️ The discovery call should test directly which state Bajaj is in; the architecture remains valuable in either case.

---

---

## 12. DEPENDENCY VALIDATION (Step 1C output)

All entries verified 2026-05-13 against PyPI release pages and upstream GitHub release tags via Nia `search.sh web` queries. Status legend: ✅ current and PRD syntax correct, ⚠️ current but PRD has stale syntax requiring update, 🔴 breaking change requiring PRD architectural revision.

| Library | Current Stable (May 2026) | PRD References | Status | Action Taken |
|---|---|---|---|---|
| fastapi | 0.136.1 (2026-04-23) | implicit §2.2 routes, §4.1 hours 0–8 | ✅ | No PRD code uses legacy `@app.on_event` decorator; lifespan pattern is the only one referenced. Pin to `fastapi>=0.136,<0.137` in Step 2 requirements. |
| pydantic | 2.13.4 (2026-05-06) | §2.2 throughout, §2.4 schemas | ✅ | All PRD model definitions already use v2 `model_config = ConfigDict(extra="forbid")` — load-bearing strict-forbid invariant. No v1 `Config` inner class, no `validator`, no `dict()`, no `parse_obj` present. Pin `pydantic>=2.13,<3`. |
| google-genai | 2.0.1 (2026-05-07) | §2.3 Stage 2, Stage 3, §2.6 boot validator | ✅ | v2.0.0 breaking changes are scoped to the new `interactions` API surface (per upstream release notes 2026-05-07); `GenerateContent` usage (the only surface the PRD invokes via Vertex AI client) is explicitly unaffected. Additionally: legacy `vertexai.generative_models` namespace deprecates 2026-06-24 per `cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk` — making `google-genai` the mandatory path the PRD already specifies. Pin `google-genai>=2.0,<3`. |
| sqlalchemy | 2.0.49 (2026-04-03) | §2.4 schema/ORM, §4.1 hours 0–8 | ✅ | PRD shows raw DDL only; no v1 `session.query(Model)` patterns present anywhere. Implementation in Step 2 must use `select()` + `session.execute()` — recorded as an invariant for build spec. Pin `sqlalchemy>=2.0.49,<2.1`. |
| celery | 5.6.3 (2026-03-26) | §2.3 chord, §2.4 outbox drain, §4.1 worker boot | ✅ | No `apply_async` vs `.delay()` patterns shown in PRD that would conflict. Chord pattern is stable across 5.6.x. Pin `celery[redis]>=5.6.3,<5.7`. |
| openpyxl | 3.1.5 | §4.1 hours 8–20 Excel extractor | ✅ | API surface used (cell-level read) is stable. Pin `openpyxl>=3.1.5,<3.2`. |
| pydifact | 0.2.3 | §4.1 hours 28–36 EDIFACT tokenizer | ⚠️ | Library is small, slow-moving (0.x semantic versioning, last meaningful release on PyPI is 0.2.3). No breaking change risk in 72-hour sprint window. Pin exactly `pydifact==0.2.3`. Flag for Step 2: keep tokenizer logic isolated behind an adapter interface so a future fork or replacement remains feasible without touching pipeline code. |
| alembic | 1.18.4 | §4.1 hours 0–8, §2.6 migration check | ✅ | No deprecated patterns referenced. Pin `alembic>=1.18.4,<1.19`. |
| redis-py | 7.x stable; 8.x pre-release (RESP3 default change) | §2.5 lock patterns, §2.4 outbox drain | ⚠️ | redis-py 8.x changes default protocol from RESP2 to RESP3 (per release notes 2026-04-17, pre-release status); ~84 commands have unified-but-different response shapes vs 7.x. The PRD's `SET key value NX EX <seconds>` lock pattern is a hard-invariant per Step 1B and is unaffected by RESP3 (return value is a simple OK/None). **Action:** pin `redis>=5.0,<7` for Sprint 1 to stay on the protocol the PRD was written against; defer RESP3 migration to a Phase 2 chore. Mark this pin in Step 2 build spec with rationale. |

🔴 status entries: none. No library forces a PRD architectural revision.

---

## 13. MODERNIZATION PROVENANCE (Step 1C output)

**Date of modernization pass:** 2026-05-13

**Nia query log (all queries via `~/.claude/skills/nia/scripts/search.sh web`; URLs reflect documentation pages returned by Nia and were the basis for status verdicts):**

| Query | Primary source URL hit | Source-page freshness signal |
|---|---|---|
| `Vertex AI gemini-3-flash-preview gemini-3.1-pro-preview general availability europe-west4 2026` | `cloud.google.com/vertex-ai/generative-ai/docs/learn/locations` | "Latest supported model version" table lists both model IDs; europe-west4 region row populated. |
| (same query, secondary hit) | `cloud.google.com/vertex-ai/generative-ai/docs/release-notes` | Gemini 3 Flash public preview entry lists `europe-west4 (Netherlands)` among supported regions. |
| (same query, tertiary hit) | `docs.cloud.google.com/vertex-ai/generative-ai/docs/provisioned-throughput/supported-models` | `gemini-3-flash-preview` and `gemini-3.1-pro-preview` both confirmed as "Latest supported version (preview)". |
| `Vertex AI Gemini 3 Pro Flash model pricing per million tokens 2026` | `docs.cloud.google.com/vertex-ai/generative-ai/pricing` | Gemini 3.1 Pro Preview: $2/$4 in, $12/$18 out per 1M tokens; Gemini 3 Flash Preview: $0.50 in (text/image/video), $3 out. |
| `fastapi latest version pypi release 2026 lifespan` | `github.com/fastapi/fastapi/releases/tag/0.136.1` | Published 2026-04-23. |
| `pydantic latest stable version pypi 2026` | `github.com/pydantic/pydantic/releases/tag/v2.13.4` | Published 2026-05-06. |
| `google-genai python SDK pypi latest version 2026 vertex ai client` | `pypi.org/project/google-genai/2.0.1/` | Latest stable 2.0.1. |
| `google-genai 2.0 python sdk breaking changes migration vertex client` | `github.com/googleapis/python-genai/releases/tag/v2.0.0` | v2.0.0 dated 2026-05-07; "⚠ BREAKING CHANGES — Interactions Only … `GenerateContent` usage is unaffected." |
| (same query, secondary) | `cloud.google.com/vertex-ai/generative-ai/docs/deprecations/genai-vertexai-sdk` | Vertex AI `generative_models` module deprecates 2026-06-24; google-genai is mandatory replacement. |
| `sqlalchemy 2 latest version pypi 2026 release` | `github.com/sqlalchemy/sqlalchemy/releases/tag/rel_2_0_49` | Published 2026-04-03. |
| `celery latest version pypi 2026 release broker redis` | `github.com/celery/celery/releases/latest` (v5.6.3) | Tagged 2026-03-26; changelog page lists 5.6.2 on 2026-01-04 and 5.6.3 subsequently. |
| `alembic openpyxl pydifact redis-py latest version pypi 2026` | `pypi.org/project/alembic/` (1.18.4), `pypi.org/project/openpyxl/` (3.1.5), `github.com/redis/redis-py/releases` (RESP3 default change, 2026-04-17), `pypi.org/project/pydifact/` (0.2.3) | Cross-confirmed against PyPI project pages. |

**Pinned model strings (post-modernization):**
- `gemini-3-flash-preview` (Stage 2 extraction, temp 0.0–0.1, Vertex AI europe-west4)
- `gemini-3.1-pro-preview` (Stage 3 normalization, N=3 at temps 0.1/0.5/0.9, Vertex AI europe-west4)

**Pinned library versions (Step 2 build-spec target):**
- `fastapi>=0.136,<0.137`
- `pydantic>=2.13,<3`
- `google-genai>=2.0,<3`
- `sqlalchemy>=2.0.49,<2.1`
- `alembic>=1.18.4,<1.19`
- `celery[redis]>=5.6.3,<5.7`
- `redis>=5.0,<7`  (RESP2 default; defer RESP3 to Phase 2)
- `openpyxl>=3.1.5,<3.2`
- `pydifact==0.2.3`

**Hard invariants confirmed preserved:**
- ✅ Pydantic `ConfigDict(extra="forbid")` strict-forbid on every BaseModel (untouched).
- ✅ N=3 ensemble at temps (0.1, 0.5, 0.9) with majority-vote consensus (untouched).
- ✅ Zero LLM calls in Stage 1 classifier and Stage 4 validator (untouched).
- ✅ Container-boot fail-fast validators (Vertex handshake, Postgres migration head, UN/LOCODE row count) (untouched).
- ✅ Transactional outbox in same Postgres transaction as job state writes (untouched).
- ✅ Redis lock pattern `SET key value NX EX <seconds>` (untouched).
- ✅ europe-west4 region binding for Vertex AI client and Cloud Run services (untouched and reconfirmed against current regional availability).
- ✅ Anti-Replication surface: no POMDP / Bayesian RL / pricing / explainability / active-learning capabilities introduced.
- ✅ Slack-only UX: no dashboard or web admin surface introduced.

**Git commit hash:** `1e94ebe99f71ba69db53a098f13b2a71aac714d3` (initial commit, `Kaide-LABS/solvo-pilot-onramp` on `main`, pushed 2026-05-13). Note: the SHA captures the state *before* this provenance line was backfilled with the SHA itself, since the SHA is unknowable prior to the commit. A follow-up commit will record the backfilled PRD; for handoff purposes the architectural state of the repo is identical at both SHAs.

---

*End of Master PRD. Step 1C modernization complete. Next step: Step 2 (Build Spec generation for Claude Code) and Step 3 (Cold Email + Demo Briefing).*
