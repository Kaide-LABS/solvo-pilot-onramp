#!/usr/bin/env bash
# Implements PHASE_6_SPEC.md §6.1 — one-shot ZDR enrollment flag flip.
#
# Prerequisite: the GCP organization has been enrolled in the Vertex AI
# Zero Data Retention program (manual contract step with Google, NOT
# automatable via gcloud). See docs/compliance_setup.md.
#
# Once enrolled, this script flips VERTEX_AI_ZDR_ENROLLED=true on the
# three Cloud Run services. The §3.10.5 boot validator then permits
# production startup.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?must set PROJECT_ID}"
REGION="europe-west4"

for svc in solvo-onramp-api solvo-onramp-worker solvo-onramp-dispatcher-beat; do
  echo "patching ${svc} VERTEX_AI_ZDR_ENROLLED=true"
  gcloud run services update "${svc}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --update-env-vars="VERTEX_AI_ZDR_ENROLLED=true"
done

echo "ZDR flag flipped. Tail logs to confirm validator 4 passes:"
echo "  gcloud run services logs read solvo-onramp-api --region=${REGION} --project=${PROJECT_ID}"
