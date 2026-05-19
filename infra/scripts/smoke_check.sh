#!/usr/bin/env bash
# Implements PHASE_6_SPEC.md §6.6 — post-deploy smoke check.
set -euo pipefail

URL="${1:?usage: smoke_check.sh <cloud-run-base-url>}"
TOKEN="$(gcloud auth print-identity-token)"

echo "GET ${URL}/v1/health"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${URL}/v1/health" \
  | python -c "import json,sys; d=json.load(sys.stdin); assert d['status']=='healthy'; assert d['region']=='europe-west4'; print('health ok')"

echo "GET ${URL}/v1/health/ready/cloudrun"
curl -fsS -m 3 -H "Authorization: Bearer ${TOKEN}" "${URL}/v1/health/ready/cloudrun" >/dev/null \
  && echo "cloudrun ready"

echo "smoke check passed"
