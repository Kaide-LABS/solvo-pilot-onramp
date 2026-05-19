# PHASE 3 SPEC — Solvo Pilot Onramp Sprint 2

**Output of Step 3B (Phase 2 review approved, Phase 3 blueprinted).** Consumes: `ULTIMATE_PRD.md` §3.4 (Stage 3 ensemble), §3.5 (deterministic anchors — UN/LOCODE, WCO HS6), `Solvo_Master_PRD.md` §3.4, `docs/modernization_log.md`, `PHASE_2_SPEC.md` (extraction surface already shipped). Feeds: Step 3A (Codex build of Phase 3) → Step 3B (review + advance to Phase 4 spec).

---

## §0 — PHASE PLAN HEADER

**This is Phase 3 of 6 phases in the Sprint 1 build.** Phase 2 (extraction + ingress) was approved at SHA `8d2d93b`. Subsequent specs flow through Phase 6 (`BUILD_COMPLETE.md`).

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake. |
| ✅ Phase 2 | 8–20 | Ratesheet schemas, deterministic Stage 1 classifier, Stage 2 Gemini-Flash Excel extractor, 5 fixtures, transactional outbox enqueue, `/v1/ingest/ratesheet` + `/v1/jobs/{id}/status\|result`. |
| **Phase 3** | 20–28 | **Stage 3 N=3 Pro ensemble at temps (0.1, 0.5, 0.9), UN/LOCODE ~110k bulk load, WCO HS6 reference load, port-code obfuscation resolution, majority-vote consensus, lane-graph state writes, removal of Phase 1's UN/LOCODE short-circuit.** |
| Phase 4 | 28–36 | EDIFACT via pydifact, Stage 4 Python rules engine, conformal prediction 0.85, conditional Pro correction pass (N=2), clarification phrasing node, alembic 0003 §3.10.4 audit trail. |
| Phase 5 | 36–48 | Slack + Block Kit + slash command + mentions, `/v1/intake/jobs` operator ingress, signed GCS URL delivery, outbox dispatcher. |
| Phase 6 | 48–60 | Cloud Run europe-west4 of 3 services, Cloud SQL + Memorystore, 7-day GCS lifecycle, 90-day archive job, smoke tests, 9-criterion acceptance suite. |

---

## §1 — FILES ADDED OR MODIFIED

**Added:**

```
packages/ingest/
├── normalizer.py                  # Stage 3 N=3 ensemble orchestrator
├── consensus.py                   # majority-vote consensus per lane field
└── port_resolver.py               # UN/LOCODE lookup + carrier-alias resolution

packages/reference/
├── __init__.py
├── un_locode.py                   # async query helpers against un_locode_reference
├── wco_hs6.py                     # async query helpers against wco_hs6_reference
└── loader.py                      # one-shot bulk-load CLI (alembic data ops)

packages/core/models/
└── normalization.py               # EnsembleVote, ConsensusResult, LaneGraphTransition

migrations/versions/
└── 0002_reference_data.py         # un_locode_reference + wco_hs6_reference tables

scripts/
├── load_un_locode.py              # bulk-load CLI: COPY ~110k rows from CSV
└── load_wco_hs6.py                # bulk-load CLI: WCO HS6 chapter+heading rows

data/
├── un_locode_2024_2.csv           # vendored UN/LOCODE snapshot (≥ 100k rows)
└── wco_hs6_2022.csv               # vendored WCO HS6 reference (~5k rows)

tests/unit/
├── test_consensus.py              # majority-vote + tie-breaking semantics
├── test_port_resolver.py          # alias → UN/LOCODE resolution + flagging
├── test_normalizer.py             # N=3 orchestrator with mocked Pro client
├── test_reference_un_locode.py    # async query against in-memory fixture
└── test_reference_wco_hs6.py

tests/integration/
└── test_reference_load.py         # alembic upgrade + bulk-load smoke (gated by env var)
```

**Modified:**

- `packages/ingest/tasks.py` — add `tasks.ingest.normalize_lanes`; chain into Phase 2's link via Celery `chord`.
- `packages/ingest/excel_extractor.py` — emit a `NormalizedRatesheet` with `lanes` containing carrier-internal port codes (e.g. "BSAS"); Phase 3 resolves them downstream.
- `packages/compliance/boot_validators.py` — replace the `un_locode_table_integrity` short-circuit with the real `count(*) >= 100_000` check. The `table_absent_phase1_short_circuit` path is removed entirely.
- `packages/core/settings.py` — bump `expected_alembic_head` default to `0002_reference_data`.
- `packages/core/db/base.py` — add `UnLocodeReference`, `WcoHs6Reference` ORM models.
- `packages/core/models/ratesheet.py` — extend `FlagReason` with `"port_obfuscation_unresolved"`; `LaneRecord.equipment_type` literal stays unchanged.
- `apps/api/main.py` — no surface changes (no new routes in Phase 3).
- `CHANGELOG.md` — Phase 3 entry.

---

## §2 — PIP DEPENDENCIES

No new top-level dependencies. `google-genai` (already pinned) provides Pro inference via the same client singleton. The bulk-load CLIs use only stdlib `csv` + asyncpg `copy_records_to_table`.

If the executor surfaces a new dependency need, halt and escalate. `docs/modernization_log.md` §12 must update before any new pin lands.

---

## §3 — PYDANTIC SCHEMAS (Phase 3)

Every new BaseModel declares `model_config = ConfigDict(extra="forbid")` on its own line.

### 3.1 `packages/core/models/normalization.py`

```python
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from packages.core.models.ratesheet import LaneRecord, PortCode


class EnsembleVote(BaseModel):
    """One of three (or in Phase 4: five) per-lane votes from the Pro ensemble."""

    model_config = ConfigDict(extra="forbid")

    sample_index: Literal[0, 1, 2, 3, 4]
    temperature: Literal[0.1, 0.5, 0.9]   # Phase 4 widens this to include 0.0 and 1.0
    lane: LaneRecord
    raw_response_hash: str = Field(min_length=8, max_length=64)


class ConsensusResult(BaseModel):
    """Per-lane consensus output produced by majority-vote across votes."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str
    consensus_lane: LaneRecord | None       # None when no field reached majority
    votes: list[EnsembleVote] = Field(min_length=3, max_length=5)
    agreement_per_field: dict[str, int] = Field(default_factory=dict)
    requires_review: bool                    # True when consensus_lane is None or any field tied
    review_reason: Literal[
        "no_majority", "port_obfuscation_unresolved", "agreement_clean"
    ]


class LaneGraphTransition(BaseModel):
    """One write into lane_graph_states. Mirrors §3.6 LangGraph audit log."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    lane_id: str
    status: Literal[
        "parsed", "extracted", "candidate_normalized",
        "needs_reference_lookup", "needs_human_review",
        "validated", "rejected",
    ]
    state_json: dict[str, Any]
    version: int = Field(ge=1)
    updated_at: datetime


class ResolvedPortCode(BaseModel):
    """Output of port_resolver: a canonical PortCode plus the alias that produced it."""

    model_config = ConfigDict(extra="forbid")

    canonical: PortCode
    source_alias: str = Field(min_length=2, max_length=16)
    resolution_method: Literal[
        "direct_unlocode", "carrier_alias_table", "iata_fallback", "unresolved"
    ]
```

`LaneRecord.equipment_type` is **not** widened in Phase 3. `base_rate_usd` remains a `Decimal` and is **never** computed by Phase 3 code — only carried through from Stage 2.

---

## §4 — FASTAPI ROUTE SIGNATURES

**No new routes in Phase 3.** Phase 2's `/v1/ingest/ratesheet`, `/v1/jobs/{id}/status`, `/v1/jobs/{id}/result` are sufficient; Phase 3 changes only the *contents* of `NormalizedRatesheet` written into `onramp_outputs` (now post-normalization, with port codes resolved or flagged).

Routes explicitly deferred — `/v1/intake/*`, `/v1/webhooks/slack`, `/internal/v1/audit/{job_id}` remain Phase 4/5.

---

## §5 — ALEMBIC MIGRATION (`migrations/versions/0002_reference_data.py`)

Reference-data tables loaded **once per environment** by the bulk-load CLIs after `alembic upgrade head`. The migration creates schema; the CLIs populate rows.

```python
"""reference_data — UN/LOCODE + WCO HS6 reference tables.

Revision ID: 0002_reference_data
Revises: 0001_initial
Create Date: 2026-05-20
"""
revision = "0002_reference_data"
down_revision = "0001_initial"


def upgrade() -> None:
    op.create_table(
        "un_locode_reference",
        sa.Column("code",          sa.Text, primary_key=True),   # e.g. "ARBUE"
        sa.Column("country_code",  sa.Text, nullable=False),     # "AR"
        sa.Column("place_name",    sa.Text, nullable=False),     # "Buenos Aires"
        sa.Column("subdivision",   sa.Text, nullable=True),
        sa.Column("function",      sa.Text, nullable=False),     # UN/LOCODE function digits
        sa.Column("latitude",      sa.Numeric(6, 4), nullable=True),
        sa.Column("longitude",     sa.Numeric(7, 4), nullable=True),
    )
    op.create_index("ix_un_locode_country", "un_locode_reference", ["country_code"])
    op.create_index(
        "ix_un_locode_place_lower",
        "un_locode_reference",
        [sa.text("LOWER(place_name)")],
    )

    op.create_table(
        "wco_hs6_reference",
        sa.Column("hs6",         sa.Text, primary_key=True),     # six-digit
        sa.Column("chapter",     sa.Text, nullable=False),
        sa.Column("heading",     sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
    )

    op.create_table(
        "carrier_port_aliases",
        sa.Column("alias",      sa.Text, primary_key=True),      # "BSAS"
        sa.Column("canonical",  sa.Text, sa.ForeignKey("un_locode_reference.code"), nullable=False),
        sa.Column("source",     sa.Text, nullable=False),        # provenance tag
    )


def downgrade() -> None:
    op.drop_table("carrier_port_aliases")
    op.drop_table("wco_hs6_reference")
    op.drop_index("ix_un_locode_place_lower", table_name="un_locode_reference")
    op.drop_index("ix_un_locode_country", table_name="un_locode_reference")
    op.drop_table("un_locode_reference")
```

**Settings change:** `expected_alembic_head = "0002_reference_data"`. The boot validator immediately fails any container whose DB still reports `0001_initial`.

**Bulk-load CLIs.** `scripts/load_un_locode.py` uses asyncpg `copy_records_to_table` to load `data/un_locode_2024_2.csv` (≥ 100k rows). `scripts/load_wco_hs6.py` does the same for `data/wco_hs6_2022.csv` (~5k rows). Both CLIs are idempotent (`TRUNCATE ... CASCADE` before `COPY`). `carrier_port_aliases` is seeded with the known set used in fixture `03_obfuscated_ports.xlsx` (BSAS→ARBUE, NYC→USNYC, LA→USLAX, HKG→HKHKG, SHA→CNSHA).

---

## §6 — IMPLEMENTATION LOGIC FLOW

### 6.1 Stage 3 — N=3 Pro Ensemble (`packages/ingest/normalizer.py`)

```python
async def normalize_lanes(
    job_id: str,
    extraction: NormalizedRatesheet,
    settings: Settings,
) -> tuple[NormalizedRatesheet, list[ConsensusResult]]:
    """Run the deep ensemble per lane: three independent Pro calls at temps
    (0.1, 0.5, 0.9), then majority-vote consensus across results.

    Model: gemini-3.1-pro-preview (Vertex AI, europe-west4).
    N=3 — exactly three samples. No reduction "for cost" allowed.
    Temperatures: (0.1, 0.5, 0.9) — exactly these three values, in this order.
    """
```

**Hard requirements:**

- N=3, temps (0.1, 0.5, 0.9) — **not** (0.0, 0.5, 1.0), **not** N=1 single-shot, **not** confidence-weighted ensembling.
- The three calls run concurrently via `asyncio.gather`. Total budget 45s; any single-call timeout 20s.
- One retry on Vertex AI 5xx per call (500ms backoff). No retry on 4xx.
- The Pro client is the same `get_vertex_client` singleton — no second `genai.Client(...)`.
- Each call uses `response_mime_type="application/json"`, `response_schema=LaneRecord.model_json_schema()`, and a `system_instruction` that explicitly forbids rate generation.
- Per-lane prompt carries the *extracted* lane (post-Stage-2) plus the relevant reference snippet (matching UN/LOCODE candidates by country, matching HS6 by heading). The Pro is asked to normalize codes, not to generate them.

### 6.2 Majority-Vote Consensus (`packages/ingest/consensus.py`)

```python
def majority_consensus(votes: list[EnsembleVote]) -> ConsensusResult:
    """For each field of LaneRecord, count occurrences across votes and pick
    the strict majority value. If no field reaches majority, return
    consensus_lane=None and review_reason='no_majority'.

    No weighted voting. No confidence weighting. No LLM-judged consensus.
    Strict 2-of-3 (or 3-of-5 in Phase 4) for majority.
    """
```

- Field-level voting on canonical Pydantic-serialized representations (after Decimal→string, date→ISO).
- Ties at 1-1-1 → `no_majority` → lane is flagged, not guessed.
- Surcharge lists: compared as multisets; majority must agree on the *full* set, not subsets.

### 6.3 Port-Code Obfuscation Resolution (`packages/ingest/port_resolver.py`)

```python
async def resolve_port_code(
    raw: str,
    session: AsyncSession,
) -> ResolvedPortCode:
    """Resolve a raw port string to a canonical UN/LOCODE.

    Order:
      1. If raw matches the canonical regex AND exists in un_locode_reference → direct hit.
      2. If raw exists in carrier_port_aliases → alias hit.
      3. If raw is 3 letters and matches a known IATA code with a co-located UN/LOCODE → iata fallback.
      4. Otherwise → unresolved (flagged for review).
    """
```

- **Pure deterministic logic.** Zero LLM calls. If the resolver can't resolve, the lane is flagged with `port_obfuscation_unresolved`. **The LLM never guesses port codes** — the deterministic anchor invariant from §3.5.
- Postgres `LOWER(place_name)` index supports case-insensitive lookups in Phase 4 if we extend to place-name matching.

### 6.4 Celery Task Chain Extension (`packages/ingest/tasks.py`)

```python
@celery_app.task(name="tasks.ingest.normalize_lanes", bind=True, max_retries=0)
def normalize_lanes_task(self, upstream: dict[str, str]) -> None: ...
```

Wiring updated:

```python
# Phase 2 (deleted):
# classify_format_task.apply_async(link=extract_payload_task.s())

# Phase 3 (new):
classify_format_task.apply_async(
    args=(job_id, staging_path),
    link=extract_payload_task.s() | normalize_lanes_task.s(),
)
```

`normalize_lanes_task` reads the persisted `onramp_outputs.normalized_payload` (written by Phase 2), runs the ensemble + consensus + port resolution, and **overwrites** `normalized_payload` in the same transaction as an outbox `audit_log` event (`{"stage": "normalized", "consensus_clean": N, "flagged": M}`).

### 6.5 Boot Validator — Removing the Phase 1 Short-Circuit

`_validate_un_locode_table_integrity` becomes:

```python
result = await conn.execute(text("SELECT count(*) FROM un_locode_reference"))
count = int(result.scalar() or 0)
if count < 100_000:
    raise AssertionError(f"UN/LOCODE row count {count} < 100000")
return f"un_locode_rows={count}"
```

The `if exists is None: return "table_absent_phase1_short_circuit"` branch is **deleted entirely**. A container booting against a DB without the reference table now fails fast with exit code 3.

---

## §7 — CROSS-PHASE INTEGRATION REQUIREMENTS

- **Boot validators (Phase 1).** Validator 3 changes — the short-circuit is removed and the real row-count check is wired. Validator 1/2/4 untouched. `expected_alembic_head` bumps to `0002_reference_data`.
- **Phase 2 extraction.** The Stage 2 prompt continues to allow carrier-internal port aliases (e.g. "BSAS") to flow through unchanged; Phase 3's `port_resolver` then resolves them. No change to the Stage 2 prompt or extractor code paths.
- **NormalizedRatesheet contract.** Stage 3 may add entries to `flagged_for_review` (with `reason="port_obfuscation_unresolved"` or `"no_majority"`). It MUST NOT remove or rewrite lanes that came out of Stage 2 cleanly. `deterministically_rejected` is untouched in Phase 3 (Stage 4 owns it).
- **Vertex AI client singleton.** Both Pro and Flash run through `get_vertex_client(settings)`. No second client instantiation.
- **Anti-Replication.** Stage 3 normalizes *identifiers* (port codes, HS6, equipment, surcharge taxonomy). It MUST NOT compute, derive, recommend, or otherwise produce monetary values, rates, margins, market-clearing decisions, POMDP/CMDP/value-iteration logic, or active learning on booking outcomes. The Pro system_instruction explicitly forbids rate generation.
- **Transactional outbox.** The `audit_log` row for `stage="normalized"` commits in the same transaction as the `onramp_outputs` update. The dispatcher remains Phase 5.
- **Test coverage.** Phase 2's 70 unit tests continue to pass. Any regression is on Codex to fix in Phase 3.

---

## §8 — PHASE 3 ACCEPTANCE CRITERIA

Step 3B advances to Phase 4 only when ALL of the following pass:

1. **Migration head:** `alembic upgrade head` from a fresh DB lands at `0002_reference_data`; `alembic downgrade base` succeeds. Settings' `expected_alembic_head` defaults to `0002_reference_data`.
2. **Reference-data load:** `python -m scripts.load_un_locode data/un_locode_2024_2.csv` loads ≥ 100,000 rows into `un_locode_reference`. `python -m scripts.load_wco_hs6 data/wco_hs6_2022.csv` loads the WCO snapshot. Both CLIs are idempotent (re-run leaves row counts unchanged).
3. **Boot validator 3 now strict:** `_validate_un_locode_table_integrity` no longer short-circuits. A container booted against a DB without the table or with row count < 100,000 fails with exit code 3.
4. **N=3 ensemble:** `test_normalizer.py` asserts `gemini-3.1-pro-preview` is called exactly three times per lane, at temperatures (0.1, 0.5, 0.9) in that order, via the singleton client. Mocked responses drive the test.
5. **Majority-vote consensus:** `test_consensus.py` covers (a) clean 3-0 agreement, (b) 2-1 majority on each field, (c) 1-1-1 tie → `requires_review=True`, `consensus_lane=None`, `review_reason="no_majority"`. No weighted/confidence-weighted/LLM-judged consensus may exist in the diff.
6. **Port resolution:** `test_port_resolver.py` asserts the four resolution paths (direct, alias, iata fallback, unresolved). Fixture `03_obfuscated_ports.xlsx` resolves BSAS→ARBUE, NYC→USNYC, LA→USLAX after Stage 3.
7. **Deterministic invariant:** `rg -e 'generate_content' packages/ingest/classifier.py packages/ingest/port_resolver.py packages/ingest/consensus.py packages/reference/` returns zero matches. Stage 1, port resolution, and consensus contain zero LLM calls.
8. **Anti-Replication grep:** `rg -i -e 'recommend' -e 'predict.*price' -e 'pomdp' -e 'value_iter' -e 'constrained.*mdp' -e 'active.*learning' -e 'belief.*state' packages/ apps/` returns zero matches.
9. **Transactional outbox:** the `stage="normalized"` audit_log row commits atomically with the `onramp_outputs` update. Rollback test asserts neither lands when the transaction is abandoned.
10. **Lint and types:** `ruff check .` returns 0; `mypy --strict packages/core packages/compliance packages/ingest packages/reference apps/api` returns 0. Coverage on changed code ≥ 80%.
11. **Secret scan:** `gitleaks detect --no-banner --no-git --source .` zero findings.
12. **Phase 1 + Phase 2 regression:** all prior unit tests pass unchanged. Any test that previously passed and now fails is a Phase 3 regression.

---

## §9 — EXPLICIT NON-GOALS FOR PHASE 3

The executor MUST NOT implement the following in Phase 3:

- **No Stage 4 deterministic validation.** No `tasks.ingest.validate_output`, no conformal prediction, no 0.85 threshold, no hard-validity rules engine, no `deterministically_rejected` population. Phase 4.
- **No conformal score writes.** `onramp_conformal_scores` table stays empty. `conformal_scores` field on `NormalizedRatesheet` stays `{}`.
- **No conditional Pro correction pass.** No N=2 escalation, no agreement-conditioned recall. Phase 4.
- **No clarification phrasing node.** Phase 4.
- **No EDIFACT.** The classifier still routes EDIFACT to a 422 ("not supported in Phase 2/3"). Phase 4.
- **No CSV / email extraction.**
- **No `customer_compliance_profiles` table.** In-memory only. Phase 4.
- **No audit-trail endpoint** (`/internal/v1/audit/{job_id}`) and no `access_log` outbox event type. Phase 4.
- **No Slack integration**, **no `/v1/intake/*`**, **no signed URLs**, **no outbox dispatcher**. Phase 5.
- **No Cloud Run deploy.** Phase 6.
- **No widening of the N=3 ensemble.** Exactly three Pro calls, exactly the (0.1, 0.5, 0.9) temperature triple. Phase 4 may widen to N=5 for the conditional correction path — Phase 3 must not pre-implement that.
- **No LLM in port resolution.** `port_resolver` is pure-Python, deterministic, DB-backed. Zero `generate_content` calls.
- **No LLM in consensus.** Majority vote is pure-Python set counting. Zero `generate_content` calls.
- **No active learning, no POMDP, no Bayesian RL, no value iteration, no Constrained MDP, no booking-outcome feedback, no price/rate/margin computation, no market-clearing decision, no white-box pricing explainability.** (Anti-Replication invariant — restated for Phase 3.)

---

*End of Phase 3 Spec. Next: Step 3A executes against this spec to produce code; Step 3B reviews and emits `PHASE_4_SPEC.md` (Phase 4 boundary triggers citation re-verification gate for Ugare et al. and Wan et al.).*
