# §A — Lateral Name

Headless Intake API

# §B — Divergence Declaration

| Axis | Baseline | This Lateral |
|---|---|---|
| Ingress Mechanism | Slack channel file-drop | REST API endpoint with file upload, operator-grade and no UI surface |
| Agent Orchestration Topology | Sequential Celery chord, N=3 Pro ensemble | Single-shot Gemini Pro with structured-output schema, no ensemble and no chain |
| Output Delivery Surface | Slack thread reply with attached JSON | Async API with polling endpoint and signed result URL |

Diverges from baseline along axes 1, 2, 3; diverges from priors along axes 1, 2, 3.

# §C — The Concept

Headless Intake API strips the Pilot Onramp down to an operator-grade HTTP contract. A caller posts a ratesheet file to `/v1/intake/jobs`, receives a `job_id`, polls `/v1/intake/jobs/{job_id}`, and downloads the normalized JSON from a signed URL when complete. There is no Slack app, no inbox, no Drive watcher, and no portal.

The solution target is still only pre-pilot freight ratesheet data normalization. It accepts prospect-side Excel, CSV, EDIFACT PRICAT, and email-export files, converts them into strict `NormalizedRatesheet` payloads, and stops before Solvo's engine does anything with the data. This lateral is designed for technical operators, repeatable benchmark runs, and integration tests around the normalization layer itself.

The structural bet is compression rather than orchestration. After deterministic classification and parser preparation, one long-context `gemini-3.1-pro-preview` call receives the structured parser output, reference candidate excerpts, and the strict response schema. It returns a full candidate `NormalizedRatesheet` in one shot. Python validation then either accepts lanes, flags lanes, or deterministically rejects lanes. This reduces queue complexity, removes ensemble spend, and makes the smallest deployable architecture, but it has a weaker interactive demo and less semantic redundancy than ensemble-based laterals.

# §D — The Strategic Hook (Evidence-Anchored)

Bajaj may prefer this lateral if the priority is speed, auditability, and a clean technical contract over a new work surface. The locked PRD frames the pain as manual rate checks before new pilots can move, and it also records a tension between automated API-delivered workflows for live customers and manual pre-pilot scoping. Headless Intake API answers that tension with a deterministic, explainable intake contract: post the prospect file, receive schema-valid data, inspect every flagged or rejected lane by rules citation. It uses the validated Google Cloud and Gemini stack in `europe-west4`, keeps UN/LOCODE and HS6 checks deterministic, and gives Bajaj a white-box artifact he can hand to a technical buyer at a tier-one carrier. It does not overclaim EBIT, margin uplift, or revenue leakage reduction; it only reduces the manual rate checks needed to get prospect data into the shape Solvo expects before its own engine takes over.

# §E — The Agent Architecture

**Model assignments.**
- `gemini-3.1-pro-preview`: single structured-output normalization call, temperature 0.1, N=1. The model receives deterministic parser output, candidate UN/LOCODE aliases, candidate HS6 records, and the full output schema.
- `gemini-3-flash-preview`: not used in the MVP path except for boot handshake parity or optional future extraction fallback.

**Ensemble pattern.** N=1, temperature 0.1. No ensemble, no verifier pair, no chain. Confidence is derived from deterministic validation outcomes and optional logprob/conformal heuristics where available, not LLM-as-judge.

**Orchestration shape.** Async API job. FastAPI receives upload, writes raw artifact, deterministic classifier/parser prepares a compact `SingleShotNormalizationInput`, one Pro call returns candidate output, Python validation writes final result.

**Data passing.**

```python
class ApiUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prospect_id: str
    prospect_name: str
    source_format_hint: Literal["excel","csv","edifact","email","auto"] = "auto"

class SingleShotNormalizationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    source_format: str
    parser_manifest: dict
    reference_candidates: dict[str, list[str]]
```

Reuses baseline `NormalizedRatesheet`, `LaneRecord`, `FlaggedLane`, `RejectionRecord`, `ExtractionMetadata`.

**Routes.**

```text
POST /v1/intake/jobs
GET  /v1/intake/jobs/{job_id}
GET  /v1/intake/jobs/{job_id}/result-url
GET  /v1/intake/jobs/{job_id}/review
```

**Deterministic anchors.**
- Classification: no LLM; MIME, magic bytes, xlsx structure, CSV dialect, EDIFACT headers, email headers.
- Reference lookup: deterministic UN/LOCODE and WCO HS6 lookup creates candidates before the Pro call and validates accepted fields after it.
- Validation: strict Pydantic `extra="forbid"` plus Python rules engine controls final acceptance.

**Persistence.**
- Reuse `onramp_jobs`, `onramp_outputs`, `onramp_outbox`.
- Add `api_clients(client_id, name, status, created_at)` only for API key metadata.
- Add `api_job_events(job_id, event_type, payload, created_at)` for pollable status.
- Redis: `solvo:onramp:api:idempotency:{hash}`, `solvo:onramp:job:{job_id}`.

**Cost envelope.**
- 50 lanes: one Pro call ~75K input/18K output = $0.37; total ≈ $0.37/job.
- 500 lanes: one Pro call may exceed 200K context depending on parser compaction. At ~260K input/90K output using >200K pricing, input ~$1.04 and output ~$1.62; total ≈ $2.66/job. If compaction keeps input <=200K, total ≈ $1.48/job.

# §F — The "Native Environment" UI Spec

The user sees no UI. They interact through HTTP, curl, Postman, a notebook, or a thin internal script. They trigger a job with multipart upload and metadata fields. They receive `202 Accepted` with a `job_id`, status URL, and result URL placeholder.

Results are delivered through polling. Completed jobs expose a signed Cloud Storage URL for `normalized_ratesheet.json` plus a JSON review endpoint listing `flagged_for_review` and `deterministically_rejected` lanes. Flagged lanes are handled by posting a corrected payload to a future `/review` endpoint in Phase 2; MVP exposes the flags but does not implement interactive resolution.

The Magic Moment is weak: a terminal upload returns a completed job and signed JSON URL in <=60 seconds. This rates ⚠️ on Pillar 4 because the transformation is technically clear but visually modest.

# §G — Phase 1 Execution Spec (Lateral MVP)

1. Reuse FastAPI, Postgres, Redis, Cloud Storage, Vertex AI `europe-west4`, Pydantic, `google-genai`, `openpyxl`, `pydifact`.
2. Remove Slack runtime requirements from the MVP path.
3. Remove Celery requirement for MVP; use FastAPI background task or Cloud Run Job for async execution.
4. Day 1: API routes, upload persistence, API-key stub, deterministic classifier/parser manifest.
5. Day 2: `SingleShotNormalizationInput`, Pro structured-output call, validation adapter.
6. Day 3: polling status, signed result URL, review endpoint, curl-based demo script.
7. Acceptance: `curl -F file=@rates.xlsx` returns job; polling returns completed; result URL downloads valid `NormalizedRatesheet`.
8. Phase 2 deferral: customer-configured webhooks, OAuth client management, review mutation endpoint, usage metering.

# §H — 5-Pillar Self-Check

| Pillar | Rating | Justification |
|---|---|---|
| 1. Bottleneck Assassin | ✅ | It normalizes the exact pre-pilot files blocking ingestion. |
| 2. Anti-Replication | ✅ | It stops at schema-valid normalized data and never produces prices. |
| 3. Native Environment | ⚠️ | An API is native for technical operators, not for Bajaj's likely day-to-day workflow. |
| 4. Magic Moment | ⚠️ | Terminal polling is less visually compelling than Slack, Drive, or portal state changes. |
| 5. System Resilience | ⚠️ | Single-shot Pro reduces orchestration failure but loses ensemble disagreement signals. |

# §I — Sprint Feasibility & Investment Lateral Flag

Buildable in 72 hours by Hafeedh + Claude Code + Codex CLI. This is the simplest Sprint-feasible lateral technically. The complexity driver is prompt compaction for 500-lane files to avoid >200K context pricing. It fits the £10,000/month standing-capacity model easily because it removes Slack and Celery operational surfaces.

# §J — Anti-Replication Defense

Headless Intake API is a pre-engine normalization contract only. It does not implement Kim's POMDPs, Bayesian RL, Constrained MDPs, factored state spaces, value iteration, active learning over bookings, or price recommendation logic. The DMZ is maintained by route design: upload endpoints accept only prospect files and metadata, and result endpoints return only validated `NormalizedRatesheet`, flags, and deterministic rejection records.

