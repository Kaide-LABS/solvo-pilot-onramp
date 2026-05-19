#!/usr/bin/env bash
# Implements PHASE_6_SPEC.md §6.2 — one-shot terraform apply + image build + deploy.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?must set PROJECT_ID}"
SHORT_SHA="$(git rev-parse --short HEAD)"

cd "$(dirname "$0")/../terraform"
terraform init -upgrade
terraform apply -auto-approve -var="project_id=${PROJECT_ID}" -var="release_tag=${SHORT_SHA}"

cd ../..
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions="_REGION=europe-west4,SHORT_SHA=${SHORT_SHA}" \
  --project="${PROJECT_ID}"

echo "deploy complete: ${SHORT_SHA}"
