# Compliance Setup — Ops Checklist

This document is the ops-side companion to `ULTIMATE_PRD.md` §3.10 and `PHASE_1_SPEC.md` §0.5.

## Vertex AI Zero Data Retention (ZDR)

Vertex AI's zero-retention posture has **two independent controls** that must both be in place. The boot validator §3.10.5 enforces the first programmatically; the second is a Google Cloud contract step that Kaide ops handles out-of-band.

### Control 1 — Request/response logging disabled (programmatic)

Set at runtime by `packages/compliance/retention.py:disable_request_response_logging()`. The Vertex AI compliance boot validator (validator 4) invokes this on every container start for each Gemini publisher model in scope (`gemini-3-flash-preview`, `gemini-3.1-pro-preview`). It is idempotent — calling when already disabled is a no-op.

If this control is ever observed in the enabled state at boot, validator 4 fails with exit code 4 and the container refuses to enter Cloud Run rotation.

### Control 2 — Abuse-monitoring prompt logging opt-out (contract)

Google may log prompts for abuse monitoring as part of the standard Generative AI safety program (GCP Terms of Service §4.3). Opting out requires enrollment in the **Vertex AI Zero Data Retention** program at the Google Cloud organization level. Reference: `https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention`.

Once Kaide is enrolled for the Solvo engagement organization, set the environment variable:

```
VERTEX_AI_ZDR_ENROLLED=true
```

on every Cloud Run deployment in production. Boot validator 4 asserts this is `true` whenever `ENVIRONMENT=production`. In `development` and `staging` the validator permits `false` for local iteration.

### Audit trail

Both controls are part of the Sprint 1 §3.10 compliance commitment. Every change to either control should be recorded in the engagement's compliance log (Notion: Kaide Labs → Solvo Engagement → Compliance, restricted access). The boot validator's emitted `detail` string (e.g., `rrl_disabled=True zdr_enrolled=True models=3-flash-preview,3.1-pro-preview`) is the runtime evidence that both controls were in place at the time the container entered rotation.

## Region binding

All Cloud Run services, Cloud SQL Postgres, Memorystore Redis, Cloud Storage buckets, and the Vertex AI publisher models used by this project must remain in `europe-west4`. This is enforced at the Pydantic level: `Settings.vertex_location` is `Literal["europe-west4"]` and any deployment env that attempts to substitute a different region will fail Pydantic validation before the FastAPI lifespan ever runs.
