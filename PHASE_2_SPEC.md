# PHASE 2 SPEC — Solvo Pilot Onramp Sprint 2

**Output of Step 3B (Phase 1 review approved, Phase 2 blueprinted).** Consumes: `ULTIMATE_PRD.md`, `Solvo_Master_PRD.md` §3.3 (ratesheet schemas), §3.4 (Stage 1/2 logic), `docs/modernization_log.md`, `PHASE_1_SPEC.md` (scaffolding already shipped). Feeds: Step 3A (Codex build of Phase 2) → Step 3B (review + advance to Phase 3 spec).

---

## §0 — PHASE PLAN HEADER

**This is Phase 2 of 6 phases in the Sprint 1 build.** Phase 1 (scaffolding + boot validators) was approved at SHA `ed92d9d` (chore: Phase 1 review approved). Subsequent specs are generated cycle-by-cycle through Phase 6 (`BUILD_COMPLETE.md`).

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, four-validator §3.10.5 handshake. |
| **Phase 2** | 8–20 | **Pydantic ratesheet schemas, deterministic Stage 1 classifier, Stage 2 Gemini-Flash Excel extractor, 5 demo fixtures, transactional outbox enqueue, `/v1/ingest/ratesheet` + `/v1/jobs/{id}/status|result` API surface, Celery `tasks.ingest.classify_format` and `tasks.ingest.extract_payload`.** |
| Phase 3 | 20–28 | Stage 3 N=3 Pro ensemble at temps (0.1, 0.5, 0.9), UN/LOCODE ~110k bulk load, WCO HS6, port-code obfuscation resolution, majority-vote consensus. |
| Phase 4 | 28–36 | EDIFACT via pydifact, Stage 4 Python rules engine, conformal prediction 0.85, conditional Pro correction pass (N=2), clarification phrasing node, alembic 0002 §3.10.4 audit trail. |
| Phase 5 | 36–48 | Slack app + Block Kit + slash command + mentions, `/v1/intake/jobs` operator ingress, signed GCS URL delivery. |
| Phase 6 | 48–60 | Cloud Run europe-west4 of 3 services, Cloud SQL + Memorystore, 7-day GCS lifecycle, 90-day archive job, smoke tests, all 9 acceptance criteria. |

---

## §0.5 — CITATION RE-VERIFICATION GATE (PHASE 2 BOUNDARY)

Per `ULTIMATE_PRD.md` §4.7, **Bai et al. — "Schema-Driven Information Extraction from Heterogeneous Tables"** (arXiv:2305.14336) requires re-verification before this spec is finalized. Bai anchors §4.3 (Stage 2 schema-at-extraction-time) and the Phase 2 Stage 2 Excel extractor approach (Pydantic-schema-as-response-schema fed to Gemini Flash).

**Verification status: PROVISIONAL.**

**Nia query trail (2026-05-19):**
- Source: `b533054a-03d7-4330-8e5f-e2f149bd0310` (research_paper, display_name="Schema-Driven Information Extraction from Heterogeneous Tables") — confirmed via `sources.sh list research_paper`.
- ToC retrieval (`TYPE=research_paper sources.sh tree`): **succeeded.** Returned full hierarchical outline including Front Matter (Title, Abstract), Introduction, and subsequent sections — confirming the source-of-truth match on title and arXiv ID.
- Body retrieval (`TYPE=research_paper PAGE=1 sources.sh read` and `TREE_NODE_ID=0001 sources.sh read`): **failed** with HTTP 500 `Error reading documentation file. Please try again or contact support.` Document-agent route (`document.sh`) failed with upstream `overloaded_error` from Anthropic.
- BM25 grep against the indexed source returned zero matches for `schema`, indicating the body chunks were not yet retrievable through the search index despite ingestion completing.

**Resolution per §4.7 gate rules.** Title + ToC confirm the paper's topical alignment with the architectural element it anchors (schema-driven extraction from heterogeneous tables). The Phase 2 Stage 2 extractor does not depend on a specific body-level methodological detail of Bai that is only accessible in the inaccessible chunks — the Phase 2 design uses standard *schema-as-prompt-component* extraction with Gemini Flash's native structured-output mode, which is the broad pattern Bai describes per the title and §4.3's framing. **Step 3A may proceed.** A follow-up re-verification should run after Phase 4 (the next citation gate cycle) to upgrade this PROVISIONAL to PASSED or FAILED.

This gate outcome is recorded for the Phase 6 `BUILD_COMPLETE.md` audit summary.

---

## §1 — FILES ADDED OR MODIFIED

**Added:**

```
packages/ingest/
├── __init__.py                    # re-exports public surface (replaces _placeholder.py)
├── classifier.py                  # Stage 1 deterministic format detection
├── excel_extractor.py             # Stage 2 openpyxl → cell-list → Gemini Flash
├── prompts.py                     # versioned prompt templates + response schemas
├── tasks.py                       # Celery tasks: classify_format, extract_payload
└── outbox.py                      # transactional outbox enqueue helper

packages/core/models/
├── ingress.py                     # RatesheetIngressRequest + helpers
└── ratesheet.py                   # NormalizedRatesheet, LaneRecord, PortCode,
                                   # SurchargeRecord, FlaggedLane, RejectionRecord,
                                   # ExtractionMetadata, SourceRow, JobStatus

apps/api/routes/
├── ingest.py                      # POST /v1/ingest/ratesheet
└── jobs.py                        # GET /v1/jobs/{id}/status, /v1/jobs/{id}/result

packages/core/db/
└── repositories.py                # async CRUD: jobs, outputs, outbox (Phase 2 surface)

fixtures/
├── 01_clean_excel.xlsx            # baseline well-formed ratesheet
├── 02_merged_cells.xlsx           # merged origin/dest cells
├── 03_obfuscated_ports.xlsx       # carrier codes (BSAS, etc.) — kept unresolved (Phase 3)
├── 04_mixed_currencies.xlsx       # USD/EUR/GBP mixed columns
└── 05_mixed_units.xlsx            # metric tonnes vs short tons in surcharge column

tests/unit/
├── test_classifier.py             # one test per supported format + uncertain fallback
├── test_excel_extractor.py        # mocked Gemini Flash, fixture-driven
├── test_ratesheet_models.py       # extra="forbid" on every new BaseModel
├── test_ingress_route.py          # POST /v1/ingest/ratesheet happy + 422
├── test_jobs_routes.py            # status + result lookup
└── test_outbox.py                 # transactional commit semantics
```

**Modified:**

- `pyproject.toml` — add `openpyxl` to runtime imports (already pinned in Phase 1); confirm no new deps.
- `apps/api/main.py` — register `ingest` and `jobs` routers.
- `apps/worker/celery_app.py` — autodiscover `packages.ingest.tasks`.
- `packages/ingest/_placeholder.py` — **deleted** (per §10 of Phase 1, the placeholder is replaced in Phase 2).
- `CHANGELOG.md` — Phase 2 entry.

**No schema migrations in this phase.** The five Phase 1 tables (`onramp_jobs`, `onramp_outputs`, `onramp_outbox`, `onramp_conformal_scores`, `lane_graph_states`) already cover Phase 2 writes. `expected_alembic_head` stays at `0001_initial`.

---

## §2 — PIP DEPENDENCIES

Phase 1 already pinned `openpyxl>=3.1.5,<3.2`. No additions required. The executor MUST NOT add new top-level dependencies in Phase 2.

If a justified addition surfaces during build, halt and escalate — `docs/modernization_log.md` §12 must update before any new pin lands.

---

## §3 — PYDANTIC SCHEMAS (Phase 2)

Every model declares `model_config = ConfigDict(extra="forbid")` on its own line. Inheritance shortcuts are forbidden.

### 3.1 `packages/core/models/ingress.py`

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class RatesheetIngressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prospect_id: str = Field(min_length=3, max_length=64)
    prospect_name: str = Field(min_length=2, max_length=128)
    source_format_hint: Literal["excel", "csv", "edifact", "email", "auto"] = "auto"
    requesting_user_slack_id: str = Field(min_length=2, max_length=64)
    callback_channel: str = Field(min_length=2, max_length=128)
    # File payload arrives via multipart/form-data; the bytes are not part of this model.
```

### 3.2 `packages/core/models/ratesheet.py`

Models mirror `Solvo_Master_PRD.md` §3.3 verbatim:

- `PortCode` — `code: str` validated against `^[A-Z]{2}[A-Z0-9]{3}$` (UN/LOCODE deterministic shape; *runtime* lookup against the reference table is Phase 3).
- `SurchargeRecord` — `code`, `amount_usd: Decimal`, `applies_per: Literal["container", "shipment", "bl", "teu"]`.
- `SourceRow` — `sheet_name: str`, `row_number: int`, `cell_reference: str` (e.g. "A4:M4").
- `ExtractionMetadata` — `extractor_model: Literal["gemini-3-flash-preview"]`, `extracted_at: datetime`, `prompt_version: str`, `cell_count: int`.
- `LaneRecord` — exactly per Master PRD §3.3 (origin/destination `PortCode`, `equipment_type` Literal of 7 values, `base_rate_usd: Decimal`, surcharges list, validity range, `source_row_reference`).
- `FlaggedLane` — `lane: LaneRecord`, `reason: Literal["low_confidence", "no_majority", "ambiguous_field"]`, `confidence: Decimal | None` (Phase 4 populates confidence; Phase 2 default None).
- `RejectionRecord` — `source_row_reference: SourceRow`, `rule_id: str`, `rule_description: str`.
- `NormalizedRatesheet` — `job_id`, `prospect_id`, `extraction_metadata`, `lanes: list[LaneRecord]`, `conformal_scores: dict[str, float]` (empty dict in Phase 2; populated Phase 3+), `flagged_for_review: list[FlaggedLane]`, `deterministically_rejected: list[RejectionRecord]`, `schema_version: Literal["onramp.v1"]`.
- `JobStatus` — `job_id: str`, `status: Literal["pending","extracting","normalizing","validating","completed","failed"]`, `created_at: datetime`, `completed_at: datetime | None`, `lane_count: int | None`.

Phase 2 only populates the **extraction** path: `status` transitions `pending → extracting → completed` (with `lane_count` set). `normalizing` and `validating` remain unused until Phase 3/4.

---

## §4 — FASTAPI ROUTE SIGNATURES

### 4.1 `POST /v1/ingest/ratesheet` (`apps/api/routes/ingest.py`)

```python
@router.post(
    "",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"description": "validation_error"}, 409: {"description": "duplicate_input_hash"}},
)
async def submit_ratesheet(
    request: RatesheetIngressRequest = Depends(parse_form_request),
    upload: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> JobStatus:
    """Compute SHA-256(input bytes); insert onramp_jobs with status=pending and the hash
    as a unique key. On unique-violation return 409 with the existing job_id. Enqueue
    Celery `tasks.ingest.classify_format` with the job_id. Return JobStatus.
    """
```

- Multipart parsing uses `python-multipart` (already pinned). File size cap **25 MiB** enforced before hashing.
- The upload bytes are streamed to a GCS staging URI in Phase 5; in Phase 2 they are written to a temp directory under `/tmp/onramp/{job_id}` and the absolute path is passed to the worker via Celery task arg.
- Idempotency is achieved by `onramp_jobs.input_hash` unique constraint (already in 0001). On conflict, return the existing job_id with HTTP 409 — never enqueue a duplicate.

### 4.2 `GET /v1/jobs/{job_id}/status` (`apps/api/routes/jobs.py`)

```python
@router.get("/{job_id}/status", response_model=JobStatus, responses={404: {}})
async def job_status(job_id: str, session: AsyncSession = Depends(get_async_session)) -> JobStatus:
    """Lookup by job_id; 404 if not found."""
```

### 4.3 `GET /v1/jobs/{job_id}/result` (`apps/api/routes/jobs.py`)

```python
@router.get(
    "/{job_id}/result",
    response_model=NormalizedRatesheet,
    responses={404: {}, 409: {"description": "job_not_completed"}},
)
async def job_result(job_id: str, session: AsyncSession = Depends(get_async_session)) -> NormalizedRatesheet:
    """Returns the row from onramp_outputs.normalized_payload, validated against
    NormalizedRatesheet. 409 if job.status != 'completed'."""
```

Routes intentionally NOT in Phase 2 (deferred):

- `/v1/ingest/edifact`, `/v1/ingest/email` — Phase 4.
- `/v1/webhooks/slack`, `/v1/intake/*` — Phase 5.
- `/internal/v1/audit/{job_id}` — Phase 4.

---

## §5 — ALEMBIC MIGRATION

**None in this phase.** Phase 2 writes only against tables that already exist (`onramp_jobs`, `onramp_outputs`, `onramp_outbox`). `expected_alembic_head="0001_initial"` is unchanged. The boot validator continues to assert `0001_initial`.

---

## §6 — IMPLEMENTATION LOGIC FLOW

### 6.1 Stage 1 — Deterministic Format Classifier (`packages/ingest/classifier.py`)

**Zero LLM calls.** Pure Python.

```python
def classify_format(payload: bytes, filename: str, hint: SourceFormatHint) -> ClassifiedFormat:
    """Return (format, confidence) where format ∈ {excel, csv, edifact, email, uncertain}.

    Order of checks (first match wins):
      1. Magic bytes — xlsx ZIP header (PK\\x03\\x04 + "[Content_Types].xml"); .eml RFC822 header
         in first 4KB; EDIFACT UNA/UNB/UNH segments at offset 0 or after BOM.
      2. Extension fallback (.xlsx, .xls, .csv, .edi, .eml).
      3. Content sniff — CSV via csv.Sniffer on first 8KB.
    Confidence must be >= 0.9 to commit; otherwise returns 'uncertain' and the route returns 422.
    """
```

**Hard requirements:**
- The function is synchronous and pure. No I/O beyond the bytes argument.
- Returns a Pydantic `ClassifiedFormat` (defined in `ratesheet.py` as a small helper model with `extra="forbid"`).
- The `hint` parameter is advisory only — if the hint disagrees with magic bytes, magic bytes win and the discrepancy is logged at WARNING level.

### 6.2 Stage 2 — Excel Extractor (`packages/ingest/excel_extractor.py`)

```python
async def extract_excel_payload(
    file_path: Path,
    job_id: str,
    settings: Settings,
) -> tuple[NormalizedRatesheet, ExtractionMetadata]:
    """Open the xlsx via openpyxl (read_only=True, data_only=True). Build a list of
    structured cell records: {sheet, row, col, value, is_merged_anchor, merge_range}.
    Pass that cell list (NOT the .xlsx blob) to Gemini Flash via
    client.aio.models.generate_content with response_schema set to the NormalizedRatesheet
    JSON schema (pydantic .model_json_schema()) and response_mime_type='application/json'.
    Temperature=0.1. Model: 'gemini-3-flash-preview'. Region: europe-west4 (Settings).

    Parse the JSON response back through NormalizedRatesheet.model_validate to enforce
    the strict schema. Any extra-field rejection bubbles up as an extraction failure;
    the job moves to status='failed' with the validation error stored in
    onramp_outputs.normalized_payload via a thin failure envelope.
    """
```

**Hard requirements:**
- Cell list cap: **5,000 cells.** Larger workbooks raise `ExcelTooLargeError` → 422 at ingress (re-validated by the worker for defense-in-depth).
- The Gemini Flash call MUST use the singleton client from `packages/compliance/vertex_client.py`. No new `genai.Client(...)` instantiations.
- `response_schema` is computed once at import time via `NormalizedRatesheet.model_json_schema()` and cached.
- No retry on Vertex AI 4xx; one retry with 500ms backoff on Vertex AI 5xx. Total Vertex AI budget: 30 seconds per extraction.
- Stage 2 sets `conformal_scores={}`, `flagged_for_review=[]`, `deterministically_rejected=[]` — those populate in Phase 3/4.

### 6.3 Celery Tasks (`packages/ingest/tasks.py`)

```python
@celery_app.task(name="tasks.ingest.classify_format", bind=True, max_retries=0)
def classify_format_task(self, job_id: str, staging_path: str) -> None: ...

@celery_app.task(name="tasks.ingest.extract_payload", bind=True, max_retries=0)
def extract_payload_task(self, job_id: str, staging_path: str, fmt: str) -> None: ...
```

Task names match `Solvo_Master_PRD.md` §3.4 verbatim. Chained via `classify_format_task.apply_async(link=extract_payload_task.s(...))` — Celery `chord` wiring is deferred to Phase 3 where `normalize_lanes` is added.

### 6.4 Transactional Outbox (`packages/ingest/outbox.py`)

```python
async def enqueue_outbox_event(
    session: AsyncSession,
    job_id: str,
    event_type: Literal["slack_post", "webhook_callback", "audit_log", "signed_url_create"],
    payload: dict[str, Any],
) -> None:
    """Insert into onramp_outbox within the caller's transaction.

    The caller is responsible for the surrounding session.begin()/commit(). This
    function MUST NOT call session.commit() — that would split the side-effect insert
    from the job-state update and break the outbox invariant.
    """
```

**Phase 2 outbox use:** on successful extraction, a single `audit_log` event with payload `{"stage": "extracted", "lane_count": N}` is enqueued in the same transaction as the `onramp_outputs` insert and the `onramp_jobs.status = 'completed'` update. The dispatcher that drains the outbox is Phase 5 — Phase 2 only ensures rows land atomically.

---

## §7 — CROSS-PHASE INTEGRATION REQUIREMENTS

- **Boot validators (Phase 1)** must remain untouched. If any Phase 2 change weakens the `vertex_ai_compliance_handshake` validator, Step 3B rejects the PR.
- **Vertex AI client singleton** (`packages/compliance/vertex_client.py`) is the single point of `genai.Client(...)` construction. Phase 2 extractors call `get_vertex_client(settings).aio.models.generate_content(...)` and no other instantiation pattern is permitted.
- **`extra="forbid"` invariant** is enforced repository-wide. The Phase 2 test `test_ratesheet_models.py` adds one round-trip rejection test per new BaseModel.
- **Alembic head pin** stays at `0001_initial`. No migration in Phase 2.
- **Anti-Replication boundary.** Phase 2 produces extraction output — strings, port codes, rates as they appear in the source document. **Zero rate generation, zero price recommendation, zero margin calculation.** If any extractor logic computes a derived monetary value beyond unit conversion (e.g., USD→USD identity), Step 3B rejects.
- **Phase 1 short-circuit on `un_locode_table_integrity`** still holds — Phase 2 does not load UN/LOCODE data. Validator 3 still passes via `table_absent_phase1_short_circuit`.

---

## §8 — PHASE 2 ACCEPTANCE CRITERIA

Step 3B advances to Phase 3 only when ALL of the following pass:

1. **Stage 1 classifier coverage:** `test_classifier.py` passes for all five fixtures + an `uncertain` synthetic. Magic-bytes detection dominates extension and content sniffing.
2. **Stage 2 extractor smoke:** `test_excel_extractor.py` passes against the five fixtures with mocked Gemini Flash returning canned `NormalizedRatesheet` JSON. The test asserts:
   - The mocked client was called exactly once per fixture.
   - The response was parsed through `NormalizedRatesheet.model_validate`.
   - The cell-count cap is enforced.
3. **Ingress route happy path:** `POST /v1/ingest/ratesheet` with fixture `01_clean_excel.xlsx` returns 202 with a `JobStatus` body and inserts an `onramp_jobs` row with `status='pending'`.
4. **Idempotency:** posting the same fixture twice returns 409 on the second call with the same `job_id`.
5. **Job-status lookup:** `GET /v1/jobs/{id}/status` returns 200 with the row; 404 for an unknown id.
6. **Job-result lookup:** after a synthetic transition to `status='completed'` (via direct DB write in the test), `GET /v1/jobs/{id}/result` returns the persisted `NormalizedRatesheet`.
7. **Transactional outbox invariant:** `test_outbox.py` asserts that when `onramp_outputs` insert succeeds, the matching `onramp_outbox` row is present *in the same transaction*. The test triggers a deliberate rollback before commit and confirms neither row lands. Outbox row write and job-state update must commit atomically.
8. **Strict-forbid coverage:** every new BaseModel rejects an unknown field. `test_ratesheet_models.py` includes one parametrized test that iterates all new models.
9. **Lint and types:** `ruff check .` returns 0; `mypy --strict packages/core packages/compliance packages/ingest apps/api` returns 0. Coverage on changed code ≥ 80% (`pytest --cov`).
10. **Secret scan:** `gitleaks detect --no-banner --no-git --source .` zero findings.
11. **Anti-replication grep:** `rg -i -e 'recommend' -e 'predict.*price' -e 'pomdp' -e 'value_iter' -e 'constrained.*mdp' packages/ apps/` returns zero matches.

---

## §9 — EXPLICIT NON-GOALS FOR PHASE 2

The executor MUST NOT implement the following in Phase 2:

- **No Stage 3 ensemble.** No N=3 Pro calls, no temperature-spread (0.1/0.5/0.9) logic, no majority-vote consensus.
- **No Stage 4 validation.** No conformal prediction, no 0.85 threshold, no Python rules engine for hard-validity checks.
- **No UN/LOCODE / WCO HS6 reference data load.** `un_locode_reference` and `wco_hs6_reference` tables are not created and not queried.
- **No EDIFACT.** The classifier may detect EDIFACT magic bytes and route to `uncertain` (returning 422); the extractor for it lands in Phase 4.
- **No email / CSV extraction.** Phase 2 ships Excel only. Other classifications return 422.
- **No Slack integration.** No Block Kit, no `tasks.ingest.post_to_slack`, no slash command. Phase 5.
- **No outbox dispatcher.** Phase 2 writes outbox rows; the worker that drains them is Phase 5.
- **No new Alembic migration.** Schema stays at `0001_initial`.
- **No conformal score writes.** `onramp_conformal_scores` table is untouched; `conformal_scores` field in `NormalizedRatesheet` defaults to empty dict.
- **No `customer_compliance_profiles` persistence.** Phase 1's in-memory shape is unchanged.
- **No Pro-tier model calls.** Phase 2 uses Flash only.
- **No Cloud Run deploy.** Local Docker Compose only.
- **No active learning, no booking-outcome feedback, no value iteration, no POMDP, no Bayesian RL, no price/rate/margin computation, no white-box pricing explainability.** (Anti-Replication invariant — restated for Phase 2 to keep the line explicit.)

---

*End of Phase 2 Spec. Next: Step 3A executes against this spec to produce code; Step 3B reviews and emits `PHASE_3_SPEC.md`.*
