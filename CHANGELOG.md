# Changelog

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
