# §A — Lateral Name

Inbox Rate Triage

# §B — Divergence Declaration

| Axis | Baseline | This Lateral |
|---|---|---|
| Ingress Mechanism | Slack channel file-drop | Email inbox monitor: `intake@onramp.kaide.so` mailbox watcher |
| Agent Orchestration Topology | Sequential Celery chord, N=3 Pro ensemble | Single-orchestrator pattern: Gemini Pro plans extraction, dispatches bounded Flash subtasks |
| Output Delivery Surface | Slack thread reply with attached JSON | Reply email with normalized JSON plus signed Cloud Storage download URL |

Diverges from baseline along axes 1, 2, 3; diverges from priors along N/A because this is the first lateral.

# §C — The Concept

Inbox Rate Triage moves the Pilot Onramp out of Slack and into the oldest native surface in freight: email. A prospect, advisor, or Solvo operator forwards a messy ratesheet email to `intake@onramp.kaide.so`; the service parses the RFC822 envelope, extracts attached XLSX/XLS/CSV/PRICAT/.eml/.msg payloads, deterministically classifies each payload, and returns an engine-ready `NormalizedRatesheet` as a reply in the same email thread.

The bottleneck remains exactly the one named in the locked PRD: pre-pilot prospect data arrives as heterogeneous freight ratesheets, EDIFACT PRICAT extracts, inconsistent CSV exports, and email bundles that currently require manual rate checks across trade lanes before Solvo can ingest them. This lateral assumes the fastest behavioral adoption path is not asking Bajaj or a small commercial team to move files into a purpose-built Slack channel; it lets them forward whatever the prospect already sent.

Structurally, the difference is not just the surface. The baseline is a worker chain where each pipeline stage owns one transformation. Inbox Rate Triage uses a single Gemini Pro orchestration call to inspect deterministic parser output, generate a bounded work plan, and dispatch independent `gemini-3-flash-preview` extraction subtasks by attachment and detected table region. The Pro orchestrator never routes file types; deterministic classification still does that. Its job is to decide which already-classified content blocks need Flash extraction, which can be normalized directly, and which should be held for human review.

# §D — The Strategic Hook (Evidence-Anchored)

Bajaj's April 2025 line about "endless hours spent on manual rate checks across trade lanes for global carriers" points to a practical intake problem before any model can create value: the material arrives in whatever form the prospect already uses. An email-first path is attractive because it is customer-centric without adding a new tool habit. It also respects the white-box posture in the locked PRD: Gemini extracts; Pydantic validates; the rules engine arbitrates; UN/LOCODE and HS6 checks remain deterministic and auditable. The verified personnel state makes this especially relevant. Brent Galloway's August 2025 departure removed the Senior Implementation Manager function, while Paul de Haan and Priya Fatania also left commercial coverage gaps. With warm advisor channels still active into tier-one carriers and freight forwarders, every inbound sample file that sits in a mailbox becomes a scale constraint. Inbox Rate Triage gives Bajaj a narrow explainable mechanism for turning prospect email chaos into clean pre-engine payloads, reducing revenue leakage from stalled pilot prep without claiming margin uplift or EBIT impact from Solvo's own engine.

# §E — The Agent Architecture

**Model assignments.**
- `gemini-3.1-pro-preview`, Vertex AI `europe-west4`: one orchestration call per job, temperature 0.1, N=1. It receives deterministic parse manifests and returns an `ExtractionWorkPlan`.
- `gemini-3-flash-preview`, Vertex AI `europe-west4`: extraction subtasks per attachment/table block, temperature 0.0 for EDIFACT-derived structures and 0.1 for spreadsheet cells.
- Optional Pro correction pass: N=2 at temperatures 0.1 and 0.5 only for lanes where Flash extraction conflicts with deterministic validation hints.

**Orchestration shape.** Single-orchestrator pattern. The mailbox watcher writes a job, deterministic parsing produces manifests, Pro creates the work plan, Flash subtasks execute in parallel via Celery groups, Python validation closes the job, and the outbox sends the reply email.

**Data passing.**

```python
class EmailIngressEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str
    from_address: str
    subject: str
    received_at: datetime
    attachments: list[AttachmentManifest]

class ExtractionWorkPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    extraction_units: list[ExtractionUnit]
    hold_for_review: list[AttachmentHold]
```

Reuses baseline `NormalizedRatesheet`, `LaneRecord`, `FlaggedLane`, `RejectionRecord`, `PortCode`, and `SurchargeRecord`.

**Deterministic anchors.**
- Classification: MIME, magic bytes, EDIFACT `UNA/UNH` segment detection, CSV dialect sniffing, `.eml/.msg` envelope parsing. Zero LLM calls.
- Reference lookups: UN/LOCODE table and WCO HS6 reference are local deterministic tables loaded at boot.
- Validation: pure Python rules engine rejects extra schema fields, impossible ports, invalid HS6 codes, negative rates, impossible validity windows, and suspect dimensional-weight conventions.

**Persistence.**
- Reuse `onramp_jobs`, `onramp_outputs`, `onramp_conformal_scores`, and `onramp_outbox`.
- Add `email_messages(job_id, message_id, thread_references, from_address, reply_to, subject, attachment_count)`.
- Redis: `solvo:onramp:email:{message_id}` idempotency, `solvo:onramp:job:{job_id}`, `solvo:onramp:result:{job_id}`.
- Transactional outbox event types: `email_reply`, `signed_url_create`, `audit_log`.

**Cost envelope.** Verified rates from PRD §2.3.1: Flash $0.50/M input and $3/M output; Pro $2/M input and $12/M output at <=200K context.
- 50 lanes: Pro orchestration ~25K in/2K out = $0.07; Flash extraction ~25K in/7K out = $0.03; correction pass on 10 flagged lanes, N=2 ~40K in/10K out = $0.20. Total ≈ $0.30/job.
- 500 lanes: Pro orchestration ~90K in/8K out = $0.28; Flash extraction ~140K in/45K out = $0.21; correction pass on 80 flagged lanes, N=2 ~320K in/80K out = $1.60. Total ≈ $2.09/job.

# §F — The "Native Environment" UI Spec

Users forward prospect emails or attachments to `intake@onramp.kaide.so`. The system replies within 10 seconds with a short acknowledgement containing `job_id`, detected files, and expected completion. The final reply includes `normalized_ratesheet.json`, a signed download URL, lane counts, flagged-lane counts, and deterministic rejection counts.

Flagged lanes are handled by email reply. The reply template lists lane IDs and exact questions, for example: `L17 origin "BSAS" failed deterministic UN/LOCODE lookup; reply "L17 origin=ARBUE" to resolve.` The parser accepts only lane-specific correction syntax; free-form notes are stored as review comments but never alter output automatically.

The Magic Moment is a recorded demo where a messy forwarded prospect email with three attachments receives a reply in <=60 seconds showing one normalized JSON, a signed result URL, and a concise table: clean lanes, flagged lanes, rejected lanes.

# §G — Phase 1 Execution Spec (Lateral MVP)

1. Reuse FastAPI, Celery, Postgres, Redis, Cloud Storage, Vertex AI `europe-west4`, Pydantic v2, `google-genai`, `openpyxl`, `pydifact`.
2. Add inbound email webhook adapter: SendGrid Inbound Parse or Mailgun Routes for the demo mailbox.
3. Add dependencies: `python-multipart` if absent, `mail-parser` or stdlib `email` wrapper, provider SDK only if webhook signing requires it.
4. Remove no baseline dependencies; Celery remains useful for parallel Flash subtasks.
5. Day 1: mailbox webhook, attachment persistence, deterministic classifier, idempotency by `message_id`.
6. Day 2: Pro `ExtractionWorkPlan`, Flash extraction units, baseline normalization schema reuse.
7. Day 3: reply-email delivery, signed URL, correction-reply parser for flagged lanes, demo fixture.
8. Acceptance: forwarding one `.eml` with XLSX and CSV attachments yields a valid `NormalizedRatesheet` reply and signed JSON URL.
9. Phase 2 deferral: full Microsoft Graph mailbox support, SPF/DKIM hardening, enterprise archive retention, rich HTML review forms.

# §H — 5-Pillar Self-Check

| Pillar | Rating | Justification |
|---|---|---|
| 1. Bottleneck Assassin | ✅ | Directly absorbs the prospect-file normalization burden before pilot ingestion. |
| 2. Anti-Replication | ✅ | No price, recommendation, margin, booking outcome, or engine-state logic is introduced. |
| 3. Native Environment | ✅ | Email is already the native exchange surface for prospect data and attachments. |
| 4. Magic Moment | ✅ | Forwarded email to signed normalized JSON reply is visually simple and demo-friendly. |
| 5. System Resilience | ⚠️ | Email attachment variance and malformed forwarded chains add parsing risk beyond the Slack baseline. |

# §I — Sprint Feasibility & Investment Lateral Flag

Buildable in 72 hours by Hafeedh + Claude Code + Codex CLI. The main complexity drivers are inbound email provider setup, attachment idempotency, and correction-reply parsing. It stays within the £10,000/month standing-capacity model because it reuses the baseline Cloud Run, Postgres, Redis, Cloud Storage, and Vertex AI footprint.

# §J — Anti-Replication Defense

This lateral does not touch Dr. Dongho Kim's POMDP, Bayesian reinforcement learning, Constrained MDP, or factored state-space pricing research. It performs pre-engine extraction, normalization, deterministic UN/LOCODE validation, deterministic HS6 validation, and schema enforcement. The DMZ is maintained by ending at `NormalizedRatesheet` handoff: no value iteration, belief-state update, booking-outcome learning, market-clearing decision, rate recommendation, margin estimate, or Solvo engine output is read or produced.

