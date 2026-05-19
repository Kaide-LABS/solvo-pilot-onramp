# infra/ — Cloud Run deployment

Implements PHASE_6_SPEC.md §6.

## Layout

- `terraform/` — declarative IaC. `terraform apply` provisions VPC, Cloud SQL Postgres 17, Memorystore Redis 7.4, GCS buckets, three Cloud Run services, IAM, Secret Manager. Region is locked to `europe-west4` per ULTIMATE_PRD §3.2 (variable validation refuses any other value).
- `scripts/deploy.sh` — one-shot: `terraform apply` + `gcloud builds submit` + smoke check.
- `scripts/smoke_check.sh` — post-deploy `/v1/health` curl against the live Cloud Run URL.
- `scripts/bootstrap_zdr.sh` — one-shot ops checklist for the §3.10.5 ZDR enrollment flag.
- `scripts/archive_90day.py` — manual sweep helper (the daily Celery beat task handles the production cadence).

## First-time bootstrap

```bash
cd infra/terraform
terraform init
terraform apply -var="project_id=$YOUR_PROJECT"

# Then push the images.
gcloud builds submit --config=../../cloudbuild.yaml --substitutions=_REGION=europe-west4

# Confirm.
./scripts/smoke_check.sh "$(terraform output -raw cloud_run_api_url)"
```

## Region lock

Every `.tf` file binds resources to `var.region` (default and only-allowed value: `europe-west4`). Mutating the variable in a `tfvars` file fails terraform validation. This mirrors the runtime invariant from §3.10.2.

## Rollback

`gcloud run services update-traffic solvo-onramp-api --to-revisions=PREV=100 --region=europe-west4` flips traffic back to the previous revision; Cloud SQL backup retention is 7 days for point-in-time recovery.
