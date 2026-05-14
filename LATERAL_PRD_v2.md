# §A — Lateral Name

Drive Folder Mill

# §B — Divergence Declaration

| Axis | Baseline | This Lateral |
|---|---|---|
| Ingress Mechanism | Slack channel file-drop | Google Drive shared folder watcher with Drive change notifications |
| Agent Orchestration Topology | Sequential Celery chord, N=3 Pro ensemble | Parallel-by-default Cloud Tasks fan-out, no Celery chord |
| Output Delivery Surface | Slack thread reply with attached JSON | Write-back to the same Google Drive folder as `<original_name>_normalized.json` |

Diverges from baseline along axes 1, 2, 3; diverges from priors along axes 1, 2, 3.

# §C — The Concept

Drive Folder Mill treats prospect onboarding as a shared-folder operation. Solvo creates or receives a Google Drive folder for a prospect, shares it with the bot service account, and drops the raw ratesheet files in place. Drive change notifications trigger ingestion; each new file becomes an `onramp_jobs` record; the normalized JSON is written back beside the original file using the deterministic name `<original_name>_normalized.json`.

This still solves only the locked bottleneck: heterogeneous prospect-side data must be normalized before Solvo's engine can ingest it. The lateral is meant for situations where pilot evidence and sample ratesheets already live in folders: multiple spreadsheet versions, carrier PRICAT exports, CSV sidecars, and email-export files from the same prospect. Instead of turning Slack into the system of record, this architecture makes the folder the work surface.

The structural divergence is deep. The baseline uses Celery chords to run a sequential pipeline. Drive Folder Mill uses Cloud-native task fan-out. A Drive notification only schedules a deterministic `classify_file` task. That task writes immutable parse metadata and enqueues per-table or per-lane Cloud Tasks. Extraction, normalization, and validation are independently retryable, and a reducer Cloud Run endpoint assembles completed lane fragments into `NormalizedRatesheet` once all deterministic prerequisites are satisfied. There is no Slack delivery loop, no Celery chord barrier, and no channel-thread state.

# §D — The Strategic Hook (Evidence-Anchored)

The locked PRD identifies a tension Bajaj will recognize: Solvo can describe automated API-delivered workflows for live carrier operations while manual rate checks still persist during pre-pilot scoping. A Drive-folder architecture meets that tension cleanly. It is customer-centric because tier-one carriers and freight forwarders can share the same evidence folder they already use for pilot materials, while Solvo gets an auditable, deterministic transformation of each file into engine-ready data. It speaks Bajaj's white-box language: every file receives a clear status, every rejected lane carries a rules citation, and UN/LOCODE plus HS6 checks stay deterministic. The verified headcount and personnel state raises the value of this shape. With Galloway gone and no commercial replacement activity evidenced in the PRD, reducing manual rate checks has scale value before margin uplift, EBIT, or revenue leakage can even be measured by Solvo's own product. Drive Folder Mill gives Bajaj a folder-level mechanism for cleaning pre-engine data from warm introductions without implying any change to the explainable pricing engine itself.

# §E — The Agent Architecture

**Model assignments.**
- `gemini-3-flash-preview`: deterministic-parser-assisted extraction for spreadsheet blocks, CSV snippets, PRICAT segment groups; temperature 0.1 for spreadsheets/CSV, 0.0 for EDIFACT.
- `gemini-3.1-pro-preview`: lane normalization as a smaller N=2 verifier pair at temperatures 0.1 and 0.5; used only after deterministic candidate retrieval for UN/LOCODE aliases and HS6 candidates.

**Ensemble pattern.** N=2 Pro verifier pair. Consensus requires exact agreement on normalized origin, destination, equipment, validity dates, and surcharge taxonomy. Disagreement moves the lane to `flagged_for_review`.

**Orchestration shape.** Cloud Tasks fan-out. Each stage is an HTTP Cloud Run handler with idempotency keys. No Celery and no chord. A reducer checks `lane_fragments` completion and writes final output.

**Data passing.**

```python
class DriveFileIngress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    drive_file_id: str
    folder_id: str
    file_name: str
    mime_type: str
    md5_checksum: str

class LaneFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    lane_index: int
    raw_extract: dict
    verifier_votes: list[LaneRecord | FlaggedLane]
```

Reuses `NormalizedRatesheet`, `LaneRecord`, `FlaggedLane`, `RejectionRecord`, `ExtractionMetadata`, `PortCode`.

**Deterministic anchors.**
- Classification: Drive MIME, file extension, magic bytes, CSV dialect, EDIFACT regex, xlsx zip header.
- Reference lookup: local UN/LOCODE and WCO HS6 tables produce candidate sets before Pro sees any ambiguous alias.
- Validation: pure Python validates Pydantic strict-forbid schemas, numerical ranges, dates, port codes, HS6 codes, duplicate lane IDs, and dimensional-weight convention fields.

**Persistence.**
- Reuse `onramp_jobs`, `onramp_outputs`, `onramp_conformal_scores`.
- Add `drive_files(job_id, drive_file_id, folder_id, file_name, md5_checksum, output_file_id)`.
- Add `lane_fragments(job_id, lane_index, status, payload, attempts, updated_at)`.
- Redis optional for hot status: `solvo:onramp:drive:{drive_file_id}:{md5}`, `solvo:onramp:task:{task_id}`.
- Transactional outbox event type: `drive_writeback`.

**Cost envelope.**
- 50 lanes: Flash extraction ~25K in/6K out = $0.03; Pro N=2 normalization ~200K in/50K out = $1.00; total ≈ $1.03/job.
- 500 lanes: Flash extraction ~100K in/35K out = $0.16; Pro N=2 normalization ~2M in/500K out = $10.00; total ≈ $10.16/job before caching; shared prompt caching should reduce Pro input materially.

# §F — The "Native Environment" UI Spec

The user sees a Google Drive folder. They trigger a job by sharing a folder with the bot service account or dropping a file into an already-watched folder. During processing, the system writes a small `<original_name>_status.json` marker containing `pending`, `extracting`, `normalizing`, `validating`, or `completed`.

Results arrive as `<original_name>_normalized.json` in the same folder. Flagged lanes arrive as `<original_name>_review.csv`, with lane IDs, source row references, candidate values, validation reason, and blank `operator_resolution` cells. The MVP does not require a custom UI: operators edit the CSV and re-upload as `<original_name>_review_resolved.csv`.

The Magic Moment is the folder changing state in <=60 seconds: a messy `Q2_rates_final.xlsx` appears, then `Q2_rates_final_status.json`, then `Q2_rates_final_normalized.json` with clean/flagged/rejected counts.

# §G — Phase 1 Execution Spec (Lateral MVP)

1. Reuse Cloud Run API/worker container code shape, Postgres, Redis optional, Cloud Storage, Vertex AI `europe-west4`, baseline schemas.
2. Remove Celery from the MVP runtime path; keep dependency in repo only if shared imports assume it.
3. Add Google Drive API dependency and Cloud Tasks client.
4. Day 1: Drive watch registration, service-account sharing flow, deterministic file classifier, `drive_files` migration.
5. Day 2: Cloud Tasks endpoints for extract/normalize/validate/reduce, idempotent task keys.
6. Day 3: Drive write-back, status marker file, review CSV generation, demo folder.
7. Acceptance: adding one XLSX and one PRICAT file to a watched folder creates normalized JSON siblings and review CSVs where needed.
8. Phase 2 deferral: domain-wide delegation, granular Drive ACL inheritance, customer-owned Drive install, full Sheets review loop.

# §H — 5-Pillar Self-Check

| Pillar | Rating | Justification |
|---|---|---|
| 1. Bottleneck Assassin | ✅ | Converts prospect folder dumps into normalized pre-ingestion payloads. |
| 2. Anti-Replication | ✅ | No Solvo engine state, pricing output, or recommendation logic is touched. |
| 3. Native Environment | ✅ | Shared folders are natural for multi-file pilot evidence exchange. |
| 4. Magic Moment | ⚠️ | File write-back is visible, but less dramatic than an interactive Slack or portal demo. |
| 5. System Resilience | ⚠️ | Cloud Tasks retries are strong, but Drive notification setup and ACL edge cases add operational fragility. |

# §I — Sprint Feasibility & Investment Lateral Flag

Buildable in 72 hours by Hafeedh + Claude Code + Codex CLI if scoped to one Google Workspace and one shared demo folder. The complexity drivers are Drive webhook validation and Cloud Tasks idempotency. It remains Sprint-feasible and economically plausible under the £10,000/month model because it swaps Celery workers for managed Cloud Tasks rather than adding enterprise-scale infrastructure.

# §J — Anti-Replication Defense

Drive Folder Mill does not implement or approximate Kim's POMDPs, Bayesian RL, Constrained MDPs, or factored state-space research. It never consumes booking outcomes, does not update a belief state, does not compute a value function, and does not produce a rate or margin recommendation. The DMZ is the folder output boundary: only deterministic validated `NormalizedRatesheet` JSON leaves the pipeline for later engine ingestion.

