# Modernization Log — Step 1C

**Pass executed:** 2026-05-13
**Operator:** Claude Code (Opus 4.7 1M) acting as Lead Operations Engineer, Kaide Labs Sprint 2.
**Authoritative output:** the §12 Dependency Validation table and §13 Modernization Provenance block inside [`../Solvo_Master_PRD.md`](../Solvo_Master_PRD.md). This document is the auxiliary log mandated by the Step 1C prompt and captures the raw Nia-query plan; the PRD itself is the source of truth for every verdict.

## Methodology

All research conducted via Nia (`~/.claude/skills/nia/scripts/search.sh web`), per the global Nia-First Workflow directive in `~/.claude/CLAUDE.md`. No native `WebFetch` / `WebSearch` fallback was used. No version number, pricing figure, or release date appears in the PRD that was not retrieved from a Nia query result on 2026-05-13.

## Pass 1 — Frontier model verification

Question for each: is the model ID still live? still in europe-west4? still the appropriate role choice given current pricing? has a non-preview GA variant superseded it?

| Model string | Verdict | Evidence URL |
|---|---|---|
| `gemini-3-flash-preview` | ✅ retained — still "Latest supported model version" for Gemini 3 Flash preview; europe-west4 confirmed in release-notes regional list. No GA Flash variant exists for this role yet. | `cloud.google.com/vertex-ai/generative-ai/docs/learn/locations`, `…/docs/release-notes` |
| `gemini-3.1-pro-preview` | ✅ retained — still "Latest supported model version" for Gemini 3.1 Pro preview; europe-west4 confirmed. No GA Pro variant exists. | `cloud.google.com/vertex-ai/generative-ai/docs/learn/locations`, `docs.cloud.google.com/vertex-ai/generative-ai/docs/provisioned-throughput/supported-models` |

**Adjacent finding (flagged, not implemented):** `gemini-3.1-flash-lite` is now GA (no preview suffix). At roughly an order of magnitude lower price than Pro it is a plausible candidate to take over the Stage 3 normalization role. This is an architecture-level decision and was explicitly carved out of Step 1C scope by the prompt. Recorded as a comment in PRD §2.3.1 for Step 1B red-team reconsideration. The N=3 ensemble on `gemini-3.1-pro-preview` at temperatures (0.1, 0.5, 0.9) is the locked architecture.

**Cost envelope added to PRD §2.3.1:** ≈ $1.53 per 50-lane job, ≈ $15.13 per 500-lane job, upper-bound (pre-cache). Realistic post-cache figures ≈ 40–60% of envelope once implicit/explicit context caching is exercised on the shared normalization system prompt.

## Pass 2 — Library validation

Methodology: query upstream release notes and PyPI for each library named in PRD §2 and §4.1. Verdicts captured in PRD §12 table. Summary:

- ✅ fastapi 0.136.1, pydantic 2.13.4, google-genai 2.0.1, sqlalchemy 2.0.49, celery 5.6.3, openpyxl 3.1.5, alembic 1.18.4 — all current, no PRD syntax updates required (the PRD was already written against modern v2/v5/v2 patterns).
- ⚠️ redis-py: pin to `<7` for Sprint 1. redis-py 8.x flips default protocol RESP2→RESP3 (pre-release as of 2026-04-17). The `SET NX EX` lock pattern itself is unaffected, but ~84 commands change response shape. Sprint 1 stays on RESP2 by pinning; RESP3 migration is a Phase 2 chore.
- ⚠️ pydifact: niche, slow-moving (0.2.3 is current). Pin exactly. Isolate behind adapter interface so replacement remains feasible.
- ⚠️ google-genai 2.0.0 breaking changes: scoped to `interactions` API surface; `GenerateContent` (the only surface the sidecar uses) is explicitly unaffected per upstream 2026-05-07 release notes.

## Pass 3 — PRD rewrite

The PRD was rewritten in place at `Solvo_Master_PRD.md`. Changes:

1. §2.3 Stage 2 and Stage 3 model-string declarations gained inline ⚠️ verification comments dated 2026-05-13.
2. New subsection §2.3.1 "Cost Envelope" added with per-job spend estimates, caching note, and the explicit Flash-Lite role-swap flag carve-out.
3. §12 Dependency Validation table appended with status verdicts and pin recommendations.
4. §13 Modernization Provenance block appended with Nia query log, pinned model strings, pinned library versions, hard-invariant preservation checklist, and the commit SHA.

No hard invariant from the Step 1A/1B architectural lock was touched. Anti-Replication surface remains clean — modernization added no POMDP / Bayesian RL / pricing / explainability / active-learning capability under any pretense.
