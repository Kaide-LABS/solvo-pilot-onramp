# §A — Lateral Name

Review Room Portal

# §B — Divergence Declaration

| Axis | Baseline | This Lateral |
|---|---|---|
| Ingress Mechanism | Slack channel file-drop | Browser-based file drop portal with shareable result URL |
| Agent Orchestration Topology | Sequential Celery chord, N=3 Pro ensemble | LangGraph stateful agent graph with branching/looping per lane |
| Output Delivery Surface | Slack thread reply with attached JSON | Web portal result page with shareable URL and per-lane interactive review |

Diverges from baseline along axes 1, 2, 3; diverges from priors along axes 1, 2, 3.

# §C — The Concept

Review Room Portal gives the pre-pilot normalization workflow a purpose-built browser surface without expanding the product scope. A Solvo operator opens a lightweight upload page, drags in prospect-side files, enters the prospect name, and watches a result page populate lane-by-lane. Clean lanes are locked, rejected lanes show deterministic rule citations, and flagged lanes can be resolved interactively before downloading `NormalizedRatesheet` JSON.

The bottleneck is unchanged: heterogeneous Excel ratesheets, PRICAT files, inconsistent CSVs, and email exports need to become Solvo's expected schema before engine ingestion. This lateral is for demos and high-touch first pilots where the visible review experience matters more than staying inside Slack or email.

Structurally, Review Room Portal differs from the baseline because it introduces stateful branching rather than a fixed chain. A LangGraph graph owns lane-level state transitions: `parsed`, `extracted`, `candidate_normalized`, `needs_reference_lookup`, `needs_human_review`, `validated`, or `rejected`. Clean lanes can finish while ambiguous lanes loop through reference retrieval, verifier disagreement scoring, and human edits. The model topology is also different: Flash performs fast extraction, Pro verifies only disputed or high-impact fields, and the graph persists every transition for auditability. The portal is not a dashboard for pricing or ROI; it is a bounded pre-engine data-cleaning room.

# §D — The Strategic Hook (Evidence-Anchored)

Review Room Portal is the most demonstrable answer to Bajaj's "endless hours spent on manual rate checks across trade lanes for global carriers" because it makes the before-and-after state visible at lane level. The locked PRD shows Bajaj's allergy to opaque automation and his preference for white-box, deterministic, explainable systems. This lateral leans into that vocabulary: each lane shows the extracted source row, deterministic UN/LOCODE result, HS6 validation status, and the exact reason a lane is clean, flagged, or rejected. The verified commercial context matters here. With Galloway's implementation function gone and warm advisor routes still active into tier-one carriers, Bajaj may prefer a surface he can show in a recorded demo or live scoping call, not just a background processor. It supports scale by reducing manual rate checks before Solvo's engine receives data, while staying careful not to claim margin uplift, EBIT movement, or reduced revenue leakage from the engine's own downstream work.

# §E — The Agent Architecture

**Model assignments.**
- `gemini-3-flash-preview`: extraction node for parsed spreadsheet/table/PRICAT units, temperature 0.1, N=1.
- `gemini-3.1-pro-preview`: verifier node for flagged lanes, temperature schedule N=3 at 0.1, 0.3, 0.7. Lower spread than baseline to reduce UI churn.
- `gemini-3.1-pro-preview`: clarification phrasing node, temperature 0.2, N=1, only generates operator-facing questions; it never writes production fields.

**Orchestration shape.** LangGraph stateful graph. Nodes: `classify_deterministic`, `parse_structural`, `extract_flash`, `retrieve_reference_candidates`, `normalize_pro_verifier`, `validate_python`, `await_human_review`, `finalize_payload`.

**Data passing.**

```python
class PortalUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prospect_id: str
    prospect_name: str
    files: list[UploadedFileManifest]

class LaneGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    lane_id: str
    status: Literal["parsed","extracted","candidate_normalized","needs_reference_lookup","needs_human_review","validated","rejected"]
    source_row_reference: SourceRow
    candidate_lane: LaneRecord | None
    validation_events: list[ValidationEvent]
```

Reuses baseline `NormalizedRatesheet`, `LaneRecord`, `FlaggedLane`, `RejectionRecord`, `SurchargeRecord`, `PortCode`.

**Deterministic anchors.**
- Classification is Python-only by MIME, magic bytes, PRICAT headers, CSV dialect, and xlsx structure.
- Reference retrieval is deterministic SQL/vector-free lookup over UN/LOCODE aliases and WCO HS6 candidates; Pro sees candidates but cannot create accepted codes.
- Final validation is Python-only and uses Pydantic `ConfigDict(extra="forbid")`.

**Persistence.**
- Reuse `onramp_jobs`, `onramp_outputs`, `onramp_conformal_scores`.
- Add `portal_sessions(session_id, job_id, signed_result_slug, expires_at)`.
- Add `lane_graph_states(job_id, lane_id, status, state_json, version, updated_at)`.
- Add `human_review_events(job_id, lane_id, field_name, old_value, new_value, reviewer, created_at)`.
- Redis: `solvo:onramp:portal:{slug}`, `solvo:onramp:lane_state:{job_id}:{lane_id}`.

**Cost envelope.**
- 50 lanes: Flash extraction ~20K in/5K out = $0.03; Pro verifier on 20 ambiguous lanes, N=3 ~120K in/30K out = $0.60; clarification text ~5K in/1K out = $0.02. Total ≈ $0.65/job.
- 500 lanes: Flash extraction ~80K in/30K out = $0.13; Pro verifier on 150 ambiguous lanes, N=3 ~900K in/225K out = $4.50; clarification text ~30K in/6K out = $0.13. Total ≈ $4.76/job.

# §F — The "Native Environment" UI Spec

The user sees a browser portal with an upload area, prospect name field, job status strip, lane table, and JSON download button. They trigger a job by dragging files into the page or selecting files from disk. The result page is available through a signed shareable URL with expiry.

Results appear in the portal table: green clean lanes, yellow flagged lanes, red rejected lanes. Flagged lanes open an inline review drawer showing source row, model candidates, deterministic lookup status, and editable fields constrained by dropdowns for equipment type, UN/LOCODE validated ports, and HS6 candidates. Saving a correction reruns Python validation only.

The Magic Moment is a split-screen demo: upload a chaotic spreadsheet and watch the result page populate within <=60 seconds with green/yellow/red lane rows and a ready JSON download.

# §G — Phase 1 Execution Spec (Lateral MVP)

1. Reuse FastAPI, Postgres, Redis, Cloud Storage, Vertex AI `europe-west4`, baseline schemas and validators.
2. Add `langgraph` dependency and minimal server-rendered or static portal UI.
3. Keep Celery optional; MVP can run graph nodes in FastAPI background tasks for demo scale.
4. Day 1: upload page, signed slug routes, file persistence, deterministic classifier.
5. Day 2: LangGraph lane state model, Flash extraction, Pro verifier node, Python validation node.
6. Day 3: lane review UI, correction events, JSON download, demo fixtures.
7. Acceptance: upload XLSX, see lane table, edit one flagged lane, download Pydantic-valid `NormalizedRatesheet`.
8. Phase 2 deferral: auth provider integration, multi-user collaboration, full audit export, production-grade frontend polish.

# §H — 5-Pillar Self-Check

| Pillar | Rating | Justification |
|---|---|---|
| 1. Bottleneck Assassin | ✅ | It attacks the exact lane normalization burden and makes review faster. |
| 2. Anti-Replication | ✅ | The portal never produces prices or touches Solvo engine state. |
| 3. Native Environment | ⚠️ | A browser portal is less native than Slack, email, or Drive for an eight-person team. |
| 4. Magic Moment | ✅ | The visible lane table transformation is the strongest demo surface of the laterals. |
| 5. System Resilience | ⚠️ | Stateful graph plus UI review adds moving parts beyond a 72-hour backend-only processor. |

# §I — Sprint Feasibility & Investment Lateral Flag

Buildable in 72 hours if the portal is deliberately thin: upload, status, lane table, inline correction, JSON download. Complexity drivers are LangGraph state persistence and frontend review ergonomics. This is Sprint-feasible for a demo but closer to an investment lateral if polished multi-user access, branded UI, or enterprise auth is required.

# §J — Anti-Replication Defense

Review Room Portal stays outside Kim's POMDP, Bayesian RL, Constrained MDP, and factored state-space pricing domain. The graph state is workflow state for extraction and validation, not a pricing belief state. Human edits resolve schema fields only. The DMZ is maintained by blocking any route that accepts Solvo engine outputs, booking outcomes, price targets, revenue objectives, or market data; the only final artifact is validated pre-engine `NormalizedRatesheet` JSON.

