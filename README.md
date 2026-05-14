# solvo-pilot-onramp

FDE sidecar for Solvo.ai pre-pilot data normalization. Ingests heterogeneous freight ratesheets (Excel, EDIFACT PRICAT, raw email exports) from prospect-side data exports and produces schema-validated, structured payloads ready for Solvo's pricing engine ingestion.

The sidecar deploys as three Cloud Run services in `europe-west4` (FastAPI ingress, Celery worker pipeline, deterministic Python validator). All user-facing interaction happens in Slack — channel file-drop, `/onramp` slash command, and `@Onramp` mention handlers. Output is delivered as a Slack-attached JSON file plus a Block Kit summary table, with per-lane conformal-prediction confidence scores and pre-isolated lanes that need human review.

Architecture is white-box by construction. Stage 1 (format classification) and Stage 4 (output validation) are deterministic — zero LLM calls. Stage 2 (extraction, `gemini-3-flash-preview`) and Stage 3 (lane normalization, `gemini-3.1-pro-preview` N=3 ensemble) are bracketed on both sides by Pydantic `extra="forbid"` strict-schema enforcement and a Python rules engine that rejects impossible port codes, negative rates, and invalid validity windows against the canonical UN/LOCODE table.

**Client engagement:** Kaide Labs. Commercial terms and engagement details live in Kaide's internal documentation, not in this repository.

**Architectural reference:** [`Solvo_Master_PRD.md`](./Solvo_Master_PRD.md) — the authoritative spec for what gets built, what gets deferred, and what is explicitly out of scope.

**Status:** Pre-engagement. Private repository, will remain private until customer signature.
