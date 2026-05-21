# Human Intervention Required — Step 4 Re-run (Vertex preview-model gate)

Run started: 2026-05-21 (after Stage A–E unblock complete)
Stage: F — boot validators
Failure mode: `gemini-3-flash-preview` returns **404 NOT_FOUND** when invoked from project `kaide-ai-84019` in `europe-west4`. Both Vertex AI boot validators (`vertex_ai_handshake`, `vertex_ai_compliance_handshake`) time out because the SDK's tenacity wrapper retries the 404 until our 5s/8s budgets exhaust.

---

## What now passes (after Stage A–E + iterative compose fixes)

- `postgres`, `redis` healthy
- `dispatcher` healthy (no Vertex dependency)
- Alembic migrations applied through `0004_intake_review`
- UN/LOCODE reference: 100,050 rows (clears the ≥100k floor)
- WCO HS6 reference: 5,000 rows
- `packaging` module resolved (Dockerfile builder→runtime copy gap fixed with explicit `RUN pip install packaging` in runtime stage)
- `Settings` unhashable bug fixed (`packages/compliance/vertex_client.py` switched from `lru_cache(settings)` to a project+location-keyed module-level dict)
- `starlette` pin widened to `>=0.46,<0.50` (was `<0.42`, incompatible with `fastapi 0.136.x`)
- ADC mounted via `docker-compose.yml` (`${USERPROFILE}/AppData/Roaming/gcloud:/gcp-adc:ro`)
- Slack OAuth flow completed; bot token verified via `auth.test`
- GCS staging + archive buckets created, signer SA bound

## What still fails

A direct probe from inside the api container, with `GOOGLE_APPLICATION_CREDENTIALS` mounted correctly:

```python
client.aio.models.generate_content(model="gemini-3-flash-preview", contents="ping")
```

returns:

```
google.genai.errors.ClientError: 404 NOT_FOUND. {'error': {'code': 404,
  'message': 'Publisher Model `projects/kaide-ai-84019/locations/europe-west4/publishers/google/models/gemini-3-flash-preview` was not found or your project does not have access to it. Please ensure you are using a valid model version. For more information, see: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions',
  'status': 'NOT_FOUND'}}
```

The project's identity (ADC) is fine: `aiplatform.googleapis.com` is enabled, billing is linked, the call reaches Vertex AI's regional endpoint — it just returns 404 because the project doesn't have access to the **preview** model.

---

## Why this needs human judgment

Three options, each with a tradeoff Hafeedh should pick:

### Option 1 — Request preview-model allowlist enrollment for `kaide-ai-84019`

Open the Vertex AI Model Garden in GCP Console (https://console.cloud.google.com/vertex-ai/model-garden), find `gemini-3-flash-preview` and `gemini-3.1-pro-preview`, and click the "Enable" / "Get Access" button on each. Google typically grants access within minutes to hours for legitimate projects.

After enrollment, this run resumes from Stage F.2 (validators retry, all 4 should pass).

**Tradeoff:** keeps the modernization-log invariants intact. Requires ~minutes-to-hours of waiting depending on Google's queue.

### Option 2 — Temporarily swap to a GA Gemini model for the smoke test only

Switch the boot validator's handshake target to `gemini-2.5-flash` (GA, accessible from every billing-enabled project). Stage 3's N=3 ensemble would still need `gemini-3.1-pro-preview` so this only unblocks the handshake validator — not the actual pipeline.

**Tradeoff:** breaks the Step 4 invariant ("Never substitute model strings"). Smoke test would be misleading: handshake passes but Magic Moment still 404s in Stage 3.

### Option 3 — Defer Step 4 until Option 1 lands

Park the smoke test, commit the partial unblock state (compose stack builds, infra healthy, 2 of 4 validators pass), and resume after preview enrollment.

**Tradeoff:** clean state but the demo recording is gated on this.

---

## Recommended path

**Option 1** + commit what we have so far. The compose-fix work (starlette pin, packaging install, Dockerfile script copy, ADC mount, Settings hashability) is all real production-grade and worth shipping regardless of the smoke-test outcome. Once preview access lands, Stage F should pass cleanly on the next `docker compose up`.

---

## What I changed since last commit (`ace6f48`)

All in repo working tree, ready to commit:

- `pyproject.toml` — `starlette>=0.46,<0.50` (was `<0.42`); added `packaging>=24.0`
- `Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.dispatcher` — `COPY pyproject.toml README.md ./`, `COPY scripts/ scripts/`, runtime-stage `RUN pip install packaging>=24.0`, builder-stage explicit `"packaging>=24.0"` pin
- `.dockerignore` — `!fixtures/retention_v1.json` exception
- `docker-compose.yml` — removed host port mappings on postgres + redis (collision with host pg); added ADC volume mount + `GOOGLE_APPLICATION_CREDENTIALS` env on api/worker/dispatcher
- `packages/compliance/vertex_client.py` — replaced `@lru_cache(settings)` with project+location-keyed module-level dict (Settings is not hashable)

These changes are independent of the preview-model question and should ship.

---

## Resume instructions

After preview-model access is granted:

```bash
cd c:/Users/hp/Solvo_demo
# Verify access first
gcloud auth print-access-token > /tmp/tok
curl -s -H "Authorization: Bearer $(cat /tmp/tok)" \
  "https://europe-west4-aiplatform.googleapis.com/v1/projects/kaide-ai-84019/locations/europe-west4/publishers/google/models/gemini-3-flash-preview" \
  | python -m json.tool
# Expect: full model JSON, NOT 404

# Then restart the stack
docker compose restart api worker
docker compose ps          # all 5 should be healthy
docker compose logs api | grep "validator" | tail -4
# Expect: all 4 validators passed=true

# Resume smoke at Stage F.3 (Magic Moment x3)
```
