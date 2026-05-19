# Changelog

## Phase 4 — Stage 4 Validation + EDIFACT + Audit Trail (2026-05-21)

Files added:

- `packages/core/models/{audit,conformal}.py` — `AuditLogEntry`, `AccessLogEntry`, `ConformalScore`, `ConformalCalibration`, `RuleViolation` (all `extra="forbid"`).
- `packages/ingest/{edifact_extractor,rules_engine,conformal,correction,clarification}.py` — Stage 2 EDIFACT branch (deterministic-first via `pydifact`), pure-Python R1..R7 rules engine, section-granular split conformal at locked 0.85 threshold, conditional N=2 Pro correction at endpoint temps (0.0, 1.0), Pro clarification phrasing with numeric-leak guard.
- `apps/api/routes/audit.py` — `/internal/v1/audit/{job_id}` bearer-gated, write-on-read access-log audit trail.
- `migrations/versions/0003_audit_trail.py` — `onramp_audit_log` + `onramp_access_log` tables (append-only at application layer).
- `fixtures/06_edifact_pricat.edi` — minimal carrier PRICAT for the deterministic-parse path.
- `fixtures/conformal_calibration_v1.json` — vendored calibration record (64 samples, 0.85 threshold).
- `tests/unit/test_{rules_engine,conformal,correction,clarification,edifact_extractor,audit_models,audit_route}.py`.

Files modified:

- `packages/ingest/tasks.py` — added `validate_output_task`; extract widens to {excel, edifact}; normalize transitions to `validating`; validate owns the terminal `completed` transition and emits the `stage=validated` audit_log event.
- `apps/api/routes/ingest.py` — chain extended to `classify → extract → normalize → validate`.
- `packages/core/models/ratesheet.py` — `FlagReason` literal extended with `"hard_rule_violation"`.
- `packages/core/db/base.py` — added `OnrampAuditLog`, `OnrampAccessLog` ORM models.
- `packages/core/settings.py` — `expected_alembic_head` default bumped to `"0003_audit_trail"`; added `internal_admin_principal` + `internal_admin_token`.
- `packages/ingest/outbox.py` — `OutboxEventType` extended with `"access_log"`.
- `apps/api/main.py` — mounted `/internal/v1/audit` router (excluded from `/docs`).

Highlights: Stage 4 hard-rules engine is **pure Python — zero LLM calls**, with rules R1..R7 firing in declared order and the first violation winning per lane. Conformal threshold pinned to **0.85 at the Pydantic Literal level**. Conditional Pro correction is **gated strictly on prior consensus.requires_review** — clean consensus skips the escalation entirely (Wan et al. 2408.17017 §3 alignment). Clarification node **strips any numeric output and falls back to a non-numeric prompt** — the Anti-Replication boundary is enforced at the post-processor regex, not at the prompt level alone. EDIFACT path **prefers determinism**: a fully-tokenizable PRICAT message skips the Flash call.

## Phase 3 — Stage 3 N=3 Pro Ensemble + Reference Data (2026-05-20)

Files added:

- `packages/core/models/normalization.py` — `EnsembleVote`, `ConsensusResult`, `LaneGraphTransition`, `ResolvedPortCode` (all `extra="forbid"`).
- `packages/ingest/{normalizer,consensus,port_resolver}.py` — N=3 Pro ensemble at temps (0.1, 0.5, 0.9), pure-Python majority-vote consensus, deterministic UN/LOCODE → carrier-alias → IATA-fallback resolution chain.
- `packages/reference/{__init__,un_locode,wco_hs6,loader}.py` — async query helpers + bulk-load via asyncpg `copy_records_to_table`.
- `migrations/versions/0002_reference_data.py` — `un_locode_reference`, `wco_hs6_reference`, `carrier_port_aliases` tables.
- `scripts/{__init__,load_un_locode,load_wco_hs6}.py` — idempotent bulk-load CLIs.
- `data/_generate.py` + `data/README.md` — deterministic generator for the ≥100k-row UN/LOCODE snapshot (CSVs gitignored due to size).
- `tests/unit/test_{consensus,port_resolver,normalizer,reference_un_locode,reference_wco_hs6}.py` + `tests/integration/test_reference_load.py`.

Files modified:

- `packages/ingest/tasks.py` — added `normalize_lanes_task`; `_extract` now transitions to `"normalizing"` (not `"completed"`); `_normalize` owns the final `completed` transition and emits the `stage="normalized"` audit_log outbox event.
- `apps/api/routes/ingest.py` — Celery chain extended to `classify → extract → normalize` via `link=extract_payload_task.s() | normalize_lanes_task.s()`.
- `packages/compliance/boot_validators.py` — `_validate_un_locode_table_integrity` short-circuit removed; the validator now enforces `count(*) >= 100_000` unconditionally.
- `packages/core/settings.py` — `expected_alembic_head` default bumped to `"0002_reference_data"`.
- `packages/core/db/base.py` — added `UnLocodeReference`, `WcoHs6Reference`, `CarrierPortAlias` ORM models.
- `packages/core/models/ratesheet.py` — `FlagReason` literal extended with `"port_obfuscation_unresolved"`.

Highlights: the **N=3 ensemble at (0.1, 0.5, 0.9) with strict majority-vote** invariant is implemented and locked in `packages/ingest/normalizer.py` (`_TEMPERATURES = (0.1, 0.5, 0.9)`, `_MODEL_ID = "gemini-3.1-pro-preview"`). Port-code resolution is **pure-deterministic** — zero `generate_content` calls in `port_resolver.py`. Phase 1's UN/LOCODE short-circuit is gone — a fresh DB without the reference table now fails boot with exit code 3.

## Phase 2 — Stage 1 Classifier + Stage 2 Excel Extractor (2026-05-19)

Files added:

- `packages/core/models/{ingress,ratesheet}.py` — Pydantic schemas mirroring Solvo_Master_PRD §3.3 (every BaseModel `extra="forbid"`).
- `packages/core/db/repositories.py` — async CRUD on Phase 1 tables (`onramp_jobs`, `onramp_outputs`).
- `packages/ingest/{classifier,excel_extractor,prompts,tasks,outbox}.py` — deterministic Stage 1 + Gemini-Flash Stage 2 + Celery tasks + transactional outbox helper.
- `apps/api/routes/{ingest,jobs}.py` — `/v1/ingest/ratesheet`, `/v1/jobs/{id}/status`, `/v1/jobs/{id}/result`.
- `fixtures/01..05_*.xlsx` and `fixtures/_generate.py` — five demo workbooks (clean, merged cells, obfuscated codes, mixed currencies, mixed surcharge units).
- `tests/unit/test_{ratesheet_models,classifier,excel_extractor,ingress_route,jobs_routes,outbox}.py`.

Files modified:

- `apps/api/main.py` — register `ingest` + `jobs` routers.
- `apps/worker/celery_app.py` — autodiscover `packages.ingest.tasks`.

Files removed:

- `packages/ingest/_placeholder.py` (replaced by real Stage 1/2 modules, per PHASE_1_SPEC §10).

Highlights: deterministic format classifier (zero LLM calls) governs routing; Stage 2 sends a cell-list (capped at 5,000) — not the raw .xlsx blob — to `gemini-3-flash-preview` in `europe-west4` via the singleton Vertex AI client, with `NormalizedRatesheet.model_json_schema()` as the response schema. Idempotency on `onramp_jobs.input_hash` (409 on duplicate). `audit_log` outbox row written in the same transaction as the `onramp_outputs` insert + `status='completed'` update — no commit inside `enqueue_outbox_event`. No new top-level dependencies; alembic head unchanged at `0001_initial`.

## Phase 1 — Scaffolding + Boot Validators (2026-05-14)

Files added:

- `pyproject.toml`, `.python-version`, `.dockerignore`, `.env.example`, `.pre-commit-config.yaml`, `alembic.ini`, `docker-compose.yml`, `Dockerfile.api`, `Dockerfile.worker`
- `apps/api/{__init__,main,exceptions}.py`, `apps/api/routes/{__init__,health}.py`
- `apps/worker/{__init__,celery_app,boot}.py`
- `packages/__init__.py`, `apps/__init__.py`
- `packages/core/{__init__,settings,logging}.py`
- `packages/core/models/{__init__,health,compliance}.py`
- `packages/core/db/{__init__,base,session}.py`
- `packages/ingest/{__init__,_placeholder}.py`
- `packages/compliance/{__init__,vertex_client,retention,boot_validators}.py`
- `migrations/{env.py,script.py.mako}`, `migrations/versions/0001_initial.py`
- `tests/{__init__,conftest}.py`, `tests/unit/{__init__,test_health,test_boot_validators,test_compliance_models}.py`, `tests/integration/{__init__,test_compose_up}.py`
- `docs/compliance_setup.md`
- `fixtures/.gitkeep`

Highlights: four-validator boot sequence wired into FastAPI lifespan and Celery `worker_init`; Alembic `0001_initial` creates the five Phase 1 tables; Vertex AI compliance handshake implements the project-level zero-retention path documented in `PHASE_1_SPEC.md` §0.5.
