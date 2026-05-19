# Changelog

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
