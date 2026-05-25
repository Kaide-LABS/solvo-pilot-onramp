# HUMAN INTERVENTION REQUEST V5 — Step 4 Stage F.3 HALTED (post Defects 11+12 fix)

**Date:** 2026-05-25
**Halting agent:** Claude Code (Step 4 Stage F.3 smoke runner, third attempt)
**Repo HEAD at halt:** `99453a1` (Defects 11+12 fixes — both verified live this run)
**Stage status:** F.1 PASSED, F.2 PASSED, F.3 Run 1 reached `completed` at 214s, **HALTED on Defect 14 (design work) + F.3.1 budget overshoot.**

Defects 11 and 12 are both **genuinely fixed** in commit `99453a1` and verified live in this run:

- **Defect 11 (Slack `unhashable Settings`) — CLOSED.** `slack_post` outbox row no longer fails with `TypeError`. New failure mode is `No module named 'aiohttp'` (Defect 13 below) — different error class, proves the Settings caching fix is in.
- **Defect 12 (result-url 500 transaction) — CLOSED.** The `result_delivered` audit_log row at the bottom of the Run 1 outbox table proves the `get_result_url` route ran to completion and committed the write-side transaction. The route now returns a valid signed URL.

Two NEW defect classes (13, 14) surface, plus an F.3.1 budget concern.

---

## §1 — Defect 13 (MECHANICAL) — `slack_sdk` requires `aiohttp`, not in deps

**Symptom:** `dispatch outbox_id=5 event=slack_post attempt=1 failed: No module named 'aiohttp'`

**Root cause:** `slack_sdk.web.async_client.AsyncWebClient`'s `chat_postMessage` requires `aiohttp` as a transitive runtime dependency. `slack_sdk` lists it as optional and does not pull it via pip dependency resolution. The worker container does not have `aiohttp` installed. This is a missing-dependency defect — `pyproject.toml` (or whatever the deps source is) needs `aiohttp` added.

**Fix surface (NOT applied — see Defect 14 reason to halt):**
- Add `aiohttp` to project dependencies in `pyproject.toml`.
- Rebuild worker + dispatcher (api doesn't need it).
- Re-run F.3.

This is mechanical and unambiguous, but it is gated behind Defect 14 — without GCS upload there is no point delivering the Slack post (the link in the post would 404).

---

## §2 — Defect 14 (DESIGN WORK — HALT TRIGGER) — `_validate` never uploads JSON to GCS

**Symptom:** `result-url` endpoint returns a valid signed URL. `curl` against that URL returns `404`. The `gs://<bucket>/jobs/<job_id>/normalized_ratesheet.json` blob does not exist.

**Root cause:** `_validate` writes the normalized payload to `OnrampOutput.normalized_payload` (a JSONB column in Postgres) and enqueues the `audit_log/validated` + `slack_post` outbox rows. Nowhere does it upload the JSON to GCS. The signed URL is generated for a blob name that no code ever writes.

This is **not** a 1-line fix:
- Requires deciding which task writes the blob (_validate? a separate GCS-upload outbox handler?).
- Requires the worker to have GCS write credentials (the current setup gives it ADC for signing only).
- Requires a Pydantic schema for the JSON envelope (or just `.model_dump_json()` of `validated`).
- Requires deciding the GCS object metadata (Content-Type, retention class, KMS key per §3.10.3).
- Touches the §3.10 retention story (the blob's lifecycle policy).
- The Slack message body includes the signed URL — broken until this is fixed.

This is design judgment. Per Step 4 V2 prompt's halt-trigger list: "A defect surfaces that involves design judgment (e.g., requires changing a Pydantic schema, a route signature, or a phase invariant)". Halting.

**Why this survived all prior smoke runs:** Same masking chain as Defects 8-12. No prior run completed validate AND reached the result-url fetch.

---

## §3 — F.3.1 Budget Overshoot

Run 1 (job `c0a66106e65c44978f967fe94618be44`) completed at `total_s=214`, exceeding the 180s budget by 19%. F.3.1 is FAILED on this run.

This is borderline and *may* be cold-cache variance — fresh stack, first Pro call of the session. Two diagnostic options:
- Run F.3 again on a warm stack (after Defect 13 + 14 fixed) and see if it lands ≤180s.
- Re-baseline the budget to 240s in a Phase 6.8 spec if the warm-stack run also exceeds 180s.

Per Phase 6.6 §6.4.3 the latency math assumes "~150s normalize (15 lanes × ~10s parallel-per-lane ensemble)". Observed normalize in Run 1 was ~160s (status went `extracting`→`normalizing` at T+9s, completed at T+214s, validate is fast). That's at the upper end of the planned envelope. No regression — just no headroom.

Decision deferred to Hafeedh: tighten the per-lane ensemble timeout or relax the F.3.1 budget. **Not** in Claude Code's scope to relax a phase-spec acceptance criterion.

---

## §4 — F.3 Run 1 Evidence Despite Halt

Outbox for Run 1:

```
 event_type |      stage       | delivered | attempts
------------+------------------+-----------+----------
 audit_log  | ingress_received | t         |        0
 audit_log  | extracted        | t         |        0
 audit_log  | normalized       | t         |        0
 audit_log  | validated        | t         |        0
 slack_post |                  | f         |        1  ← Defect 13
 audit_log  | result_delivered | t         |        0  ← Defect 12 fix verified
```

Six expected outbox rows, five delivered. Only `slack_post` blocked, by Defect 13. The `result_delivered` row proves the `/result-url` endpoint is now functional (Defect 12 fix).

Other verifications during Run 1:
- F.3.1 budget: ❌ 214s > 180s (see §3)
- F.3.2 count bands: ⏸ result JSON download returned 404 (Defect 14), so counts not externally validated. They *are* present in `onramp_outputs.normalized_payload`, accessible via psql for the recording.
- F.3.3 outbox `audit_log`+`slack_post`: rows present, `audit_log/validated` delivered, `slack_post` blocked by Defect 13.
- F.3.4 cross-run consistency: not measurable (only Run 1 attempted).

---

## §5 — Cumulative Sprint-2 Smoke Spend

This run: ~$0.20 (1 Run 1, ~50 Pro + 1 Flash).
Cumulative across all halts: **~$0.90** of Vertex AI.

Inside the $5 budget by a wide margin.

---

## §6 — Recommended Path Forward

Defects 13 + 14 + the F.3.1 budget question together justify a small Phase 6.8 closure spec rather than another direct ops commit, because:

1. **Defect 14 requires architectural decisions** (where in the pipeline does the GCS upload happen? what's the failure semantics if upload fails after status='completed' is written?). Cleanest answer is probably: `_validate` writes the JSON to GCS as the LAST step inside the success-path transaction's "outbox" — actually, since GCS is external, it can't be in the DB transaction; the cleanest pattern is an `upload_result` event_type the dispatcher handles, mirroring `slack_post`. That deserves an explicit spec.

2. **Defect 13** is mechanical but pairs naturally with Defect 14 (the Slack message needs the GCS URL to make sense).

3. **The F.3.1 overshoot** may reveal that the budget is too tight; Phase 6.6 set it to 180s with no warm-vs-cold distinction. A re-baseline (e.g., 240s for cold, 180s for warm) or a tightening of `_PER_CALL_TIMEOUT_SECONDS` deserves spec-level review, not a smoke-run patch.

Phase 6.8 spec scope (proposed):
- §6.1 Defect 13 — add `aiohttp>=3.9` to `pyproject.toml`.
- §6.2 Defect 14 — introduce an `upload_result` outbox event handled by the dispatcher (or wire the upload into `_validate`'s success path as a fire-and-forget — but then status=`completed` may precede upload, which is its own design question).
- §6.3 F.3.1 budget re-baseline — pick one: tighten ensemble timeout, relax F.3.1, or split warm/cold budgets.
- §6.4 Test update — `tests/integration/test_pipeline_e2e.py` happy-path must now also `curl` the signed URL and parse the result (proving the GCS upload landed and is fetchable). The Defect 14 closure is fundamentally about end-to-end smoke coverage; without an integration test that fetches the signed URL, this whole class of defects survives any future F.3 halt.

Estimated Phase 6.8 effort: 1-2 hours including review.

If Hafeedh prefers Path A (direct ops commit) for Defect 13 and a separate Phase 6.8 for Defect 14 alone, that's also reasonable — Defect 13 is a one-liner.

---

## §7 — What is NOT a Regression

Phase 6.5 / Phase 6.6 invariants all preserved:
- Per-task `make_async_engine` (Phase 6.5)
- Per-call `get_vertex_client` (Phase 6.6)
- `_failure_payload` / `_commit_failure` shape (Phase 6.6)
- 15-lane K+N fixture, broken lanes at 7/11/14
- N=3 ensemble at (0.1, 0.5, 0.9), majority-vote consensus, per-lane parallelism
- `location='global'` Vertex routing, europe-west4 Cloud Run + storage
- Transactional outbox invariants
- Deterministic Stage 1 + Stage 4
- Anti-Replication boundary

Defects 8-14 are all in adjacent code (Docker COPY, storage client init, IAM, SDK call shape, route-handler transaction discipline, missing deps, missing GCS upload step) that the original Phase 1-6 specs and the two closure patches did not scope.

---

## §8 — Final Status

```
Stage F.1: PASS
Stage F.2: PASS (4/4 validators)
Stage F.3 Run 1: status='completed' at 214s; F.3.1 FAIL by 34s
Stage F.3 Runs 2, 3: not attempted
Stage F.4: not attempted
Stage F.5: not attempted

Defect 11 fix: verified live (no more unhashable errors)
Defect 12 fix: verified live (result-url returned URL + result_delivered audit row written)
Defect 13 (NEW, mechanical): aiohttp missing in deps; blocks slack_post delivery
Defect 14 (NEW, design): _validate never uploads JSON to GCS; signed URL is 404
F.3.1 budget concern: 214s vs 180s on cold stack
```

Demo recording remains NOT AUTHORIZED.

— End of HUMAN_INTERVENTION_REQUEST_V5.md.
