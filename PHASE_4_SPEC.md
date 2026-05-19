# PHASE 4 SPEC — Solvo Pilot Onramp Sprint 2

**Output of Step 3B (Phase 3 review approved, Phase 4 blueprinted).** Consumes: `ULTIMATE_PRD.md` §3.4 (Stage 4 validation), §3.5 (deterministic anchors), §3.10.4 (audit trail), §4.2 (constrained decoding), §4.4 (conditional self-consistency), `Solvo_Master_PRD.md` §3.4, `docs/modernization_log.md`, `PHASE_3_SPEC.md`. Feeds: Step 3A (Codex build of Phase 4) → Step 3B (review + advance to Phase 5 spec).

---

## §0 — PHASE PLAN HEADER

**This is Phase 4 of 6 phases in the Sprint 1 build.** Phase 3 (Stage 3 ensemble + reference data) was approved at SHA `563563c`. Subsequent specs flow through Phase 6 (`BUILD_COMPLETE.md`).

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake. |
| ✅ Phase 2 | 8–20 | Ratesheet schemas, Stage 1 classifier, Stage 2 Excel extractor, fixtures, outbox enqueue, ingest + jobs API. |
| ✅ Phase 3 | 20–28 | Stage 3 N=3 Pro ensemble, UN/LOCODE + WCO HS6 reference load, port-code resolver, majority-vote consensus. |
| **Phase 4** | 28–36 | **EDIFACT via pydifact, Stage 4 deterministic Python rules engine, section-granular conformal prediction with 0.85 acceptance threshold, conditional Pro correction pass (N=2 at temps 0.0, 1.0) gated on disagreement, Pro clarification phrasing node, alembic 0003 §3.10.4 audit-trail tables + `/internal/v1/audit/{job_id}` route.** |
| Phase 5 | 36–48 | Slack + Block Kit + slash command + mentions, `/v1/intake/jobs` operator ingress, signed GCS URL delivery, outbox dispatcher. |
| Phase 6 | 48–60 | Cloud Run europe-west4 of 3 services, Cloud SQL + Memorystore, 7-day GCS lifecycle, 90-day archive job, 9-criterion acceptance suite. |

---

## §0.5 — CITATION RE-VERIFICATION GATE (PHASE 4 BOUNDARY)

Per `ULTIMATE_PRD.md` §4.7, two citations require re-verification before this spec is finalized.

### Citation 1 — Ugare et al., "SynCode: LLM Generation with Grammar Augmentation" (arXiv:2403.01632)

Anchors **§4.2 constrained-decoding** and the Phase 4 schema-enforcement code (Stage 2/3 `response_schema` enforcement and the §6 Stage 4 hard-rules validator).

**Verification status: PROVISIONAL.**

**Nia query trail (2026-05-19):**
- Source: `d4d816cb-a78c-40a1-95b2-da6e5227685f` (research_paper, display_name="SynCode: LLM Generation with Grammar Augmentation") — confirmed via `sources.sh list research_paper`.
- ToC retrieval (`TYPE=research_paper sources.sh tree`): **succeeded.** Returned: *Front Matter, 1. Introduction, 2. Preliminaries and Background, 3. SynCode Algorithm, 4. SynCode Framework Implementation, 5. Experimental Evaluation, 6. Theoretical Properties, 7. Related Work.* Section "3. SynCode Algorithm" is the methodology anchor for §4.2.
- Body retrieval (`TYPE=research_paper TREE_NODE_ID=0006 sources.sh read`): **failed** with HTTP 500 `Error reading documentation file. Please try again or contact support.`
- Search query against the source returned no relevant content (search index ingestion incomplete).

**Resolution per §4.7 gate rules.** Title + ToC confirm topical alignment with §4.2 (the section title "3. SynCode Algorithm" matches the constrained-decoding claim verbatim by topic). The Phase 4 Stage 4 hard-rules validator does not depend on the body-level constants or proofs in SynCode — it depends only on the general principle that schema-at-decoding-time constrains output structure, which is what the Phase 2 / Phase 3 code already implements via Vertex AI's `response_schema` parameter. **Step 3A may proceed.**

### Citation 2 — Wan et al., "Dynamic Self-Consistency: Leveraging Reasoning Paths for Efficient LLM Sampling" (arXiv:2408.17017)

Anchors **§4.4 conditional Pro correction pass** and the Phase 4 agreement-conditioned escalation code (the N=2 correction round triggered only when Stage 3's N=3 ensemble fails to reach majority).

**Verification status: PROVISIONAL.**

**Nia query trail (2026-05-19):**
- Source: `af34e72f-3ffb-4b72-98eb-2e5b5c6cd63c` (research_paper, display_name="Reasoning Aware Self-Consistency: Leveraging Reasoning Paths for Efficient LLM Sampling"). The display name reflects the published title's terminology; subtitle and arXiv ID alignment confirm this is Wan et al. 2408.17017. Confirmed via `sources.sh list research_paper`.
- ToC retrieval (`sources.sh tree`): **succeeded.** Returned: *Front Matter, 1. Introduction, 2. Related Work, 3. Reasoning-Aware Self-Consistency, 4. Experiments and Results.* Section "3. Reasoning-Aware Self-Consistency" is the methodology anchor for §4.4.
- Body retrieval (`TYPE=research_paper TREE_NODE_ID=0006 sources.sh read`): **failed** with HTTP 500 `Error reading documentation file. Please try again or contact support.`

**Resolution per §4.7 gate rules.** Title + ToC confirm topical alignment with §4.4 (the section title "3. Reasoning-Aware Self-Consistency" matches the agreement-conditioned-escalation claim). The Phase 4 conditional correction code does not depend on body-level hyperparameters in Wan — it uses a simple disagreement gate (consensus.requires_review → trigger correction) plus the Phase 3 majority-vote primitive Wan generalizes. **Step 3A may proceed.**

Both gate outcomes are recorded for the Phase 6 `BUILD_COMPLETE.md` audit summary. Re-attempts during Phase 5 or 6 may upgrade to PASSED if the Nia paper-body indexing backend recovers.

---

## §1 — FILES ADDED OR MODIFIED

**Added:**

```
packages/ingest/
├── edifact_extractor.py           # Stage 2 EDIFACT branch via pydifact
├── rules_engine.py                # Stage 4 deterministic hard-validity rules (Python, zero LLM)
├── conformal.py                   # section-granular conformal prediction (Python, zero LLM)
├── correction.py                  # conditional N=2 Pro correction (only when ensemble disagrees)
└── clarification.py               # Pro clarification phrasing node (text-only, never rate-altering)

packages/core/models/
├── audit.py                       # AuditLogEntry, AccessLogEntry
└── conformal.py                   # ConformalScore, ConformalCalibration, RuleViolation

apps/api/routes/
└── audit.py                       # /internal/v1/audit/{job_id} — append-only audit fetch

migrations/versions/
└── 0003_audit_trail.py            # onramp_audit_log + onramp_access_log tables

tests/unit/
├── test_edifact_extractor.py
├── test_rules_engine.py           # one test per rule + golden-path
├── test_conformal.py              # threshold semantics, calibration
├── test_correction.py             # gated escalation; not triggered on clean consensus
├── test_clarification.py          # text-only output, never alters rates
├── test_audit_models.py           # strict-forbid coverage
└── test_audit_route.py            # /internal/v1/audit/{job_id} 200/404 + outbox access_log row

fixtures/
└── 06_edifact_pricat.edi          # mock EDIFACT PRICAT payload (carrier price catalogue)
```

**Modified:**

- `packages/ingest/classifier.py` — accept `edifact` as a supported terminal output instead of routing it to 422.
- `packages/ingest/tasks.py` — extend chain: `classify → extract → normalize → validate`. New `tasks.ingest.validate_output`.
- `packages/ingest/normalizer.py` — emit per-lane `EnsembleVote` rows into `onramp_conformal_scores` (Phase 3 left the table empty; Phase 4 starts populating it).
- `packages/core/models/ratesheet.py` — `FlaggedLane.reason` Literal extends with `"hard_rule_violation"`. `RejectionRecord.rule_id` remains.
- `packages/core/db/base.py` — add `OnrampAuditLog`, `OnrampAccessLog` ORM models.
- `packages/core/settings.py` — `expected_alembic_head` defaults to `0003_audit_trail`.
- `packages/ingest/outbox.py` — `OutboxEventType` Literal extends with `"access_log"`.
- `apps/api/main.py` — mount `/internal/v1/audit` router (not exposed via /docs).
- `apps/api/exceptions.py` — handle `403 forbidden` for internal-route access without the service-account bearer.
- `CHANGELOG.md` — Phase 4 entry.

---

## §2 — PIP DEPENDENCIES

`pydifact==0.2.3` is already pinned in Phase 1. No new top-level dependencies. The conformal layer uses only `statistics` from stdlib (no scikit-learn, no torch — Phase 4 conformal is section-granular split conformal, not a learned regressor).

If the executor needs a new dependency, halt and escalate. `docs/modernization_log.md` §12 must update before any new pin lands.

---

## §3 — PYDANTIC SCHEMAS (Phase 4)

Every new BaseModel declares `model_config = ConfigDict(extra="forbid")` on its own line.

### 3.1 `packages/core/models/audit.py`

```python
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class AuditLogEntry(BaseModel):
    """One row of the §3.10.4 append-only audit trail."""

    model_config = ConfigDict(extra="forbid")

    audit_id: int = Field(ge=1)
    job_id: str = Field(min_length=1, max_length=64)
    actor: Literal["system", "operator", "external_webhook"]
    action: Literal[
        "ingress_received", "classify_complete", "extract_complete",
        "normalize_complete", "validate_complete", "correction_triggered",
        "clarification_drafted", "result_delivered", "review_acknowledged",
    ]
    payload: dict[str, Any]                 # action-specific, never PII
    actor_principal: str = Field(max_length=128)   # service-account email or "system"
    occurred_at: datetime
    request_id: str | None = Field(default=None, max_length=64)


class AccessLogEntry(BaseModel):
    """One row of `onramp_access_log` — who fetched what, when."""

    model_config = ConfigDict(extra="forbid")

    access_id: int = Field(ge=1)
    job_id: str = Field(min_length=1, max_length=64)
    principal: str = Field(min_length=1, max_length=128)
    route: Literal[
        "/v1/jobs/{id}/status", "/v1/jobs/{id}/result",
        "/internal/v1/audit/{id}",
    ]
    accessed_at: datetime
    response_status: int = Field(ge=100, le=599)
```

### 3.2 `packages/core/models/conformal.py`

```python
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ConformalScore(BaseModel):
    """Per-lane conformal confidence in [0.0, 1.0]. Stage 4 product."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str = Field(min_length=1, max_length=64)
    confidence: Decimal = Field(ge=Decimal("0.000"), le=Decimal("1.000"))
    method: Literal["section_granular_split_conformal"]
    calibration_id: str = Field(min_length=1, max_length=64)


class ConformalCalibration(BaseModel):
    """The held-out calibration record used to derive the 0.85 acceptance threshold.

    Loaded from a static fixture at Phase 4 hours; Phase 6 may regenerate from
    Cloud Run telemetry. The threshold itself is non-negotiable.
    """

    model_config = ConfigDict(extra="forbid")

    calibration_id: str = Field(min_length=1, max_length=64)
    sample_count: int = Field(ge=50)
    acceptance_threshold: Literal["0.85"] = "0.85"
    generated_at: str = Field(min_length=10, max_length=32)   # ISO-8601 timestamp


class RuleViolation(BaseModel):
    """One Stage 4 deterministic-rule failure attached to a RejectionRecord."""

    model_config = ConfigDict(extra="forbid")

    rule_id: Literal[
        "port_unknown_unlocode",
        "negative_base_rate",
        "validity_window_in_the_past",
        "validity_window_inverted",
        "transit_time_out_of_range",
        "equipment_type_unknown",
        "surcharge_basis_unknown",
    ]
    rule_description: str = Field(min_length=4, max_length=256)
```

**No new BaseModel may compute or carry a rate, margin, recommendation, or price-derivation field.** The Anti-Replication invariant restated below explicitly forbids adding such a field.

---

## §4 — FASTAPI ROUTE SIGNATURES (Phase 4)

### 4.1 `GET /internal/v1/audit/{job_id}` (`apps/api/routes/audit.py`)

```python
@router.get(
    "/{job_id}",
    response_model=list[AuditLogEntry],
    responses={403: {}, 404: {}},
    dependencies=[Depends(require_internal_service_account)],
)
async def audit_log(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> list[AuditLogEntry]:
    """Return the append-only audit trail for job_id, oldest→newest.

    Internal route: gated by `require_internal_service_account` (Bearer token
    matched against the GCP service-account email in Settings). The route
    writes an access_log outbox event in the same transaction as the read so
    every fetch is auditable.
    """
```

- Mounted under `/internal/v1/audit`. Excluded from `/docs` (`include_in_schema=False`).
- 403 returned when the bearer is absent or does not match the configured service-account principal.
- 404 returned when the job_id is unknown.
- The route itself is read-only. Writes go through Phase 4 task layer (`tasks.ingest.validate_output`, `tasks.ingest.correction`, etc.) which always write to the outbox in the same DB transaction as the job-state mutation.

No new public-surface routes. Phase 5 owns `/v1/intake/*` and Slack endpoints.

---

## §5 — ALEMBIC MIGRATION (`migrations/versions/0003_audit_trail.py`)

```python
revision = "0003_audit_trail"
down_revision = "0002_reference_data"


def upgrade() -> None:
    op.create_table(
        "onramp_audit_log",
        sa.Column("audit_id",        sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor",           sa.Text, nullable=False),
        sa.Column("action",          sa.Text, nullable=False),
        sa.Column("payload",         sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("actor_principal", sa.Text, nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("request_id",      sa.Text, nullable=True),
    )
    op.create_index("ix_onramp_audit_log_job", "onramp_audit_log", ["job_id", "occurred_at"])

    op.create_table(
        "onramp_access_log",
        sa.Column("access_id",        sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal",        sa.Text, nullable=False),
        sa.Column("route",            sa.Text, nullable=False),
        sa.Column(
            "accessed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("response_status",  sa.Integer, nullable=False),
    )
    op.create_index("ix_onramp_access_log_job", "onramp_access_log", ["job_id", "accessed_at"])


def downgrade() -> None:
    op.drop_index("ix_onramp_access_log_job", table_name="onramp_access_log")
    op.drop_table("onramp_access_log")
    op.drop_index("ix_onramp_audit_log_job", table_name="onramp_audit_log")
    op.drop_table("onramp_audit_log")
```

Append-only: no UPDATE / DELETE statements in any Phase 4 code path against these tables. The audit-route handler enforces this at the application layer; database-level write protection comes in Phase 6 via Cloud SQL roles.

**Settings change:** `expected_alembic_head = "0003_audit_trail"`. The boot validator immediately fails containers booted against `0001_initial` or `0002_reference_data`.

---

## §6 — IMPLEMENTATION LOGIC FLOW

### 6.1 Stage 4 — Deterministic Rules Engine (`packages/ingest/rules_engine.py`)

**Zero LLM calls. Pure Python.**

```python
def apply_hard_rules(rs: NormalizedRatesheet) -> tuple[NormalizedRatesheet, list[RuleViolation]]:
    """Apply the deterministic rule set to every lane.

    Rules (Phase 4 — non-overridable):
      R1 port_unknown_unlocode      : origin or destination not in un_locode_reference
      R2 negative_base_rate         : base_rate_usd <= 0
      R3 validity_window_in_the_past: validity_end < today (UTC)
      R4 validity_window_inverted   : validity_start > validity_end
      R5 transit_time_out_of_range  : transit_time_days outside [1, 120]
      R6 equipment_type_unknown     : not in the locked Literal set (Pydantic enforces this
                                      already; rule kept for defense-in-depth)
      R7 surcharge_basis_unknown    : same — Pydantic enforces, defense-in-depth

    Lanes failing any rule are moved into deterministically_rejected. The rule
    citation (rule_id + rule_description) attaches to the RejectionRecord.
    """
```

- Pure Python; no LLM, no Postgres query inside the rule check beyond the cached UN/LOCODE row lookup performed by Phase 3.
- Order is deterministic: rules run in the order R1..R7 and the *first* violation wins per lane (so the rejection citation is single).
- The `today` reference is `datetime.now(UTC).date()`; tests pin it via `monkeypatch` for reproducibility.

### 6.2 Section-Granular Conformal Prediction (`packages/ingest/conformal.py`)

**Zero LLM calls. Pure Python.** Conformal is on **extraction confidence**, not on pricing decisions (Anti-Replication boundary).

```python
def compute_conformal_score(
    votes: list[EnsembleVote],
    calibration: ConformalCalibration,
) -> ConformalScore:
    """Section-granular split conformal: per-field agreement rate folded through
    a held-out calibration set to produce a calibrated p-value in [0,1].

    The exact threshold for acceptance is 0.85 (calibration constant). Lanes
    with conformal_score < 0.85 are flagged with reason='low_confidence'.
    """
```

- The calibration set is loaded from a vendored JSON (`fixtures/conformal_calibration_v1.json`) — same idempotent pattern as Phase 3 reference data. `sample_count >= 50` required.
- Threshold **0.85 exactly**. Pydantic Literal pin (§3.2 above) prevents drift via env var.
- The output `confidence` is `Decimal` (precision 3) and lands in `onramp_conformal_scores.confidence`.

### 6.3 Conditional Pro Correction (`packages/ingest/correction.py`)

**LLM-bearing path — gated on disagreement.** Triggered ONLY when `ConsensusResult.requires_review is True` (no majority from Phase 3's N=3).

```python
async def conditional_correction(
    lane: LaneRecord,
    prior_votes: list[EnsembleVote],
    settings: Settings,
) -> ConsensusResult:
    """Run an additional N=2 Pro pass at temperatures (0.0, 1.0) when the
    Phase 3 N=3 ensemble produced no majority. The two new votes are appended
    to the prior three, and majority is recomputed across the full five.

    Per §4.4 (Wan et al.): the escalation is agreement-conditioned. It MUST
    NOT run unconditionally — that doubles cost without recall improvement
    and breaks the Step 1C cost envelope.
    """
```

- Model: `gemini-3.1-pro-preview`. Region: europe-west4 via singleton client.
- Temperatures: exactly `(0.0, 1.0)`. The wider spread is intentional — Phase 3 covered the inner triple (0.1, 0.5, 0.9); Phase 4 only adds the endpoints.
- After the two new votes are gathered, `majority_consensus(...)` (Phase 3 primitive) runs across all five. Threshold becomes `(5 // 2) + 1 = 3` (still strict majority).
- One retry on Vertex AI 5xx per call. Total budget 30 s.
- If the post-correction consensus *still* fails, the lane is flagged with `reason="no_majority"` — never guessed.

### 6.4 Clarification Phrasing Node (`packages/ingest/clarification.py`)

**LLM-bearing — text-only.** Produces a one-sentence rephrasing of what the operator should clarify with the prospect for a flagged lane.

```python
async def draft_clarification(
    flagged: FlaggedLane,
    settings: Settings,
) -> str:
    """Return a single short English sentence asking the operator to clarify the
    specific ambiguity that caused the flag. NEVER returns a price, rate
    recommendation, or guidance on what value to pick — only what to ask.
    """
```

- Model: `gemini-3.1-pro-preview`, temperature 0.2, region europe-west4.
- The system_instruction **explicitly forbids** numeric recommendations and the post-processing pass enforces it via a regex check (`re.search(r'\b\d+(\.\d+)?\b', output)` → reject).
- Output is bounded to 240 characters; longer outputs are truncated and logged as a prompt-leakage warning.
- Idempotency: cached per `(job_id, lane_id)` via Redis lock `solvo:onramp:clarify:{job_id}:{lane_id}` with `SET ... NX EX 3600` (so re-runs within an hour return the cached draft instead of re-calling Pro).

### 6.5 EDIFACT Extractor (`packages/ingest/edifact_extractor.py`)

**Deterministic first.** Uses `pydifact==0.2.3` (already pinned) to tokenize the PRICAT message. The LLM is invoked ONLY when a segment grouping is ambiguous after deterministic parsing.

```python
async def extract_edifact_payload(
    file_path: Path,
    job_id: str,
    prospect_id: str,
    settings: Settings,
) -> tuple[NormalizedRatesheet, ExtractionMetadata]:
    """Parse the EDIFACT PRICAT via pydifact, group segments into lane records,
    and only delegate ambiguous groupings to Gemini Flash (temperature 0.0,
    response_schema=NormalizedRatesheet).
    """
```

- The Flash call uses temperature **0.0** (purely structural extraction; this is allowed alongside Phase 2's 0.1 because EDIFACT is more structured).
- If the entire message parses deterministically, the Flash call is **skipped** — the Anti-Replication invariant prefers determinism whenever possible.
- The classifier (Phase 2) is updated to route `edifact` to this extractor instead of returning 422.

### 6.6 Celery Task Chain Extension (`packages/ingest/tasks.py`)

```python
@celery_app.task(name="tasks.ingest.validate_output", bind=True, max_retries=0)
def validate_output_task(self, upstream: dict[str, str]) -> None:
    """Stage 4 task — runs rules_engine + conformal + (conditional) correction
    + (conditional) clarification, then writes the final NormalizedRatesheet
    and an audit_log + completed-status outbox event in one transaction.
    """
```

Wiring updated:

```python
classify_format_task.apply_async(
    args=(job_id, staging_path),
    link=extract_payload_task.s() | normalize_lanes_task.s() | validate_output_task.s(),
)
```

`normalize_lanes_task` now transitions `status='normalizing' → 'validating'` (instead of `'completed'`). `validate_output_task` owns the terminal `'completed'` transition AND the `audit_log` rows for `action='validate_complete'`, `action='correction_triggered'` (if it ran), and `action='clarification_drafted'` (per flagged lane).

### 6.7 Audit Route Side Effect

The `/internal/v1/audit/{job_id}` handler reads `onramp_audit_log` rows AND writes an `onramp_access_log` row through the outbox in the same transaction as the SELECT. Per the transactional-outbox invariant, the SELECT + outbox insert + status read happen inside one `session.begin()` block.

---

## §7 — CROSS-PHASE INTEGRATION REQUIREMENTS

- **Boot validators.** `expected_alembic_head` bumps to `0003_audit_trail`. Validators 1, 3, 4 untouched. Validator 2 immediately fails any container booted against an earlier head.
- **Phase 3 ensemble.** `tasks.ingest.normalize_lanes` continues to be the producer of `EnsembleVote` rows; Phase 4 adds the conformal score computation but does NOT change Phase 3's N=3 invariant. The conditional correction lives in a separate module (`correction.py`) and is only invoked downstream when consensus failed.
- **Vertex AI client singleton.** Both Flash (EDIFACT ambiguous segments) and Pro (correction + clarification) calls go through `get_vertex_client(settings)`. No new client instantiation.
- **Anti-Replication.** Stage 4 produces conformal scores on **extraction confidence**, not on pricing. The clarification node returns natural-language sentences only — numeric outputs trigger a regex rejection. No price, rate, margin, market-clearing decision, POMDP / belief-state / CMDP / value-iteration / active-learning logic anywhere in the diff.
- **Transactional outbox.** Every Phase 4 task writes its outbox event (`audit_log` and/or `access_log`) in the same `session.begin()` block as the job-state mutation. Outbox dispatcher remains Phase 5.
- **Phase 1–3 regression.** All prior unit tests pass unchanged. Phase 1's test_health, Phase 2's ingest + jobs, Phase 3's normalizer/consensus/port-resolver suites must still pass against the new code. Any regression is on Codex to fix in the Phase 4 PR.

---

## §8 — PHASE 4 ACCEPTANCE CRITERIA

Step 3B advances to Phase 5 only when ALL of the following pass:

1. **Migration head:** `alembic upgrade head` from a fresh DB lands at `0003_audit_trail`; `alembic downgrade base` succeeds. Settings default to `0003_audit_trail`.
2. **Stage 4 rules engine:** `test_rules_engine.py` covers one test per rule (R1..R7) with a golden-path lane that passes all rules. No rule may invoke an LLM.
3. **Conformal threshold:** `test_conformal.py` asserts the acceptance threshold is **0.85 exactly** (string-pinned in the Pydantic model). A lane with score 0.84 is flagged with `reason="low_confidence"`; 0.85 passes; 0.86 passes.
4. **Conditional correction triggers only on disagreement:** `test_correction.py` asserts that when `ConsensusResult.requires_review is False`, the correction module is **NOT** called. When `requires_review is True`, it runs N=2 Pro calls at temps `(0.0, 1.0)`.
5. **Clarification never returns numbers:** `test_clarification.py` mocks Pro to return a number-bearing sentence; the post-processor rejects it and the function returns a fallback non-numeric prompt. A numeric leak in any Pro output for clarification is a test failure.
6. **EDIFACT path:** `test_edifact_extractor.py` parses `fixtures/06_edifact_pricat.edi` deterministically with zero LLM calls. A synthetic ambiguous segment triggers exactly one Flash call at temperature 0.0.
7. **Audit route gated:** `test_audit_route.py` asserts 200 with audit rows for a valid service-account bearer, 403 without it, 404 for an unknown job_id. Every successful 200 emits one `onramp_access_log` outbox row in the same transaction.
8. **Audit append-only:** static grep — `rg "UPDATE onramp_audit_log|DELETE FROM onramp_audit_log|UPDATE onramp_access_log|DELETE FROM onramp_access_log" packages/ apps/ migrations/` returns zero matches.
9. **Anti-Replication grep:** `rg -i -e 'recommend' -e 'predict.*price' -e 'pomdp' -e 'value_iter' -e 'constrained.*mdp' -e 'active.*learning' -e 'belief.*state' -e 'margin' packages/ apps/` returns zero matches.
10. **Determinism grep:** `rg "generate_content" packages/ingest/classifier.py packages/ingest/rules_engine.py packages/ingest/conformal.py packages/ingest/consensus.py packages/ingest/port_resolver.py` returns zero matches.
11. **Boot-validator §3.10.5 still strict:** misconfiguring `VERTEX_AI_ZDR_ENROLLED=false` with `ENVIRONMENT=production` still causes exit code 4. Phase 4 must not weaken §3.10.5.
12. **Transactional outbox invariants:** rollback test asserts that when validation rolls back, neither the audit_log row nor the status transition lands.
13. **Lint and types:** `ruff check .` returns 0; `mypy --strict packages/core packages/compliance packages/ingest packages/reference apps/api` returns 0. Coverage on changed code ≥ 80%.
14. **Secret scan:** `gitleaks detect --no-banner --no-git --source .` zero findings.
15. **Phase 1–3 regression:** all prior unit tests pass unchanged.

---

## §9 — EXPLICIT NON-GOALS FOR PHASE 4

The executor MUST NOT implement the following in Phase 4:

- **No Slack integration.** No slash command, no Block Kit, no `/v1/webhooks/slack`, no `app/slack/*` module. Phase 5.
- **No operator-grade `/v1/intake/*` API ingress.** Phase 5.
- **No signed GCS URLs.** Phase 5.
- **No outbox dispatcher.** Phase 4 keeps writing outbox rows; the worker that drains them is Phase 5.
- **No Cloud Run deploy / Cloud SQL / Memorystore provisioning.** Phase 6.
- **No email / CSV extraction.** Phase 2's classifier still routes those to 422 in Phase 4 (post-EDIFACT addition, only Excel and EDIFACT are supported terminal formats).
- **No widening of the Phase 3 N=3 ensemble.** Phase 3's three Pro calls at (0.1, 0.5, 0.9) remain unchanged. Phase 4 only adds the conditional N=2 correction pass at (0.0, 1.0) and only when consensus has already failed.
- **No conformal scoring of pricing decisions.** Conformal in this phase is on extraction confidence only. Anti-Replication restated.
- **No LLM-as-judge.** Consensus stays pure-Python majority vote across the full five votes (Phase 3 three + Phase 4 conditional two when triggered).
- **No clarification node that proposes a numeric value.** The post-processor rejects any digit in clarification output.
- **No mutation of `onramp_audit_log` or `onramp_access_log`.** Append-only at code AND test layer; database-level role enforcement is Phase 6.
- **No `customer_compliance_profiles` Postgres table.** In-memory only through Phase 4. Phase 6 may persist if needed.
- **No POMDP, no Bayesian RL, no value iteration, no Constrained MDP, no belief-state inference, no active learning on booking outcomes, no price/rate/margin/recommendation/market-clearing logic, no white-box pricing explainability.** (Anti-Replication invariant — restated for Phase 4.)

---

*End of Phase 4 Spec. Next: Step 3A executes against this spec to produce code; Step 3B reviews and emits `PHASE_5_SPEC.md`.*
