# Deployment Runbook — Solvo Pilot Onramp

Implements PHASE_6_SPEC.md §1. This is the ops-side companion to `infra/README.md`.

## First-time deploy

1. Confirm the target GCP project + organization have been enrolled in the Vertex AI Zero Data Retention program (§3.10.5 / `docs/compliance_setup.md`). Until enrollment lands, the §3.10.5 boot validator will refuse production startup.
2. Authenticate locally: `gcloud auth application-default login`.
3. From `infra/terraform/`, run `terraform init && terraform apply -var="project_id=$PROJECT"`.
4. `gcloud builds submit --config=cloudbuild.yaml` — this builds, pushes, migrates, and deploys.
5. After deploy succeeds, run `infra/scripts/bootstrap_zdr.sh` to flip `VERTEX_AI_ZDR_ENROLLED=true` on the three Cloud Run services.
6. `infra/scripts/smoke_check.sh "$(terraform output -raw cloud_run_api_url)"` — confirms `/v1/health` and `/v1/health/ready/cloudrun` are green.

## Rollback

```bash
gcloud run services update-traffic solvo-onramp-api \
  --to-revisions=PREV=100 --region=europe-west4 --project=$PROJECT
```

The previous revision must still exist (Cloud Run retains the last 100 by default). For migrations: `alembic downgrade -1` against Cloud SQL — only safe when the rolled-back image is compatible with the previous schema head. Phase 6 ships migration `0004_intake_review`; `0003_audit_trail` and `0002_reference_data` are the only safe rollback heads.

## Logs

```bash
gcloud run services logs read solvo-onramp-api --region=europe-west4 --project=$PROJECT --limit=200
```

Boot-validator results land in the first 10 lines of every container's logs. Look for `vertex_ai_handshake passed`, `postgres_alembic_head=0004_intake_review`, `un_locode_rows=…`, and `rrl_disabled=True zdr_enrolled=True`.

## Daily archive

The `tasks.lifecycle.archive_old` Celery beat task runs daily at 00:00 UTC. To trigger manually:

```bash
gcloud run jobs execute solvo-onramp-archive-once --region=europe-west4 --project=$PROJECT
```

(or push a one-off via `infra/scripts/archive_90day.py` from a Cloud Shell that has the worker SA's permissions.)
