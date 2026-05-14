# 1F-red Verdict — Solvo.ai (Pilot Onramp)

*Verdict date: May 14, 2026. Audited: Gemini_1f.md vs ULTIMATE_PRD.md commit at solvo-pilot-onramp.*

## Audit-Hygiene Re-Rating

Gemini's 1F.2 reported a final tally of **10 ✅ verified, 20 ⚠️ unverifiable, 0 ❌ contradicted** across 30 audited claims. Three of those ✅ verdicts fail the hygiene tests defined in this gate and are downgraded.

**Downgraded ✅ → ⚠️:**

1. **Implicit Claim 3 (Slack as current workspace).** Gemini cited `hnhiring.com/july-2023?technologies=python` — a Hacker News hiring aggregator entry from a Bajaj job posting nearly three years before today's audit date. Workforce tooling is time-sensitive; a three-year-old citation cannot anchor a ✅ verified verdict for *current* state. Downgrade to ⚠️ unverifiable; resolve via scoping call.

2. **Implicit Claim 13 (GCP/Azure ingress capability).** LeadIQ-only citation. The original 1F prompt explicitly forbade aggregator profiles as primary sources — they are cross-reference only. No Solvo-controlled source was found to anchor this claim. Downgrade to ⚠️ unverifiable.

3. **Explicit Claim 3 (Tech Stack details).** LeadIQ-only citation. The Master PRD §6.2's HubSpot validation also rested on this source; this contamination has propagated since Step 1B. Downgrade to ⚠️ unverifiable. The HubSpot claim specifically is load-bearing for Phase 2's Procurement Lens; resolve via scoping call before Phase 2 scope is finalized.

**Final tally post-hygiene: 7 ✅ verified, 23 ⚠️ unverifiable, 0 ❌ contradicted.** 77% of audited claims are externally unverifiable.

## Verdict

**REPOSITION-REQUIRED**

## Justification

Gemini's verdict of CLEAR-TO-SHIP is overridden. Three findings drive this override.

First, the audit-hygiene pass downgraded three ✅ verifications, leaving the architecture committing to a 72-hour sprint with 77% of its load-bearing claims unverified externally. The cold-outreach sprint can proceed, but full sprint commitment must be gated on a 15-minute scoping call with Bajaj that resolves three specific verification questions before the 72-hour build begins.

Second, the ISO 27001:2022 compliance finding (Gemini's Latent Bottleneck #1) is not addressable by positioning alone. Gemini's proposed voiceover insertion is a *claim* of compliance, not compliance itself. The current ULTIMATE_PRD §3 routes prospect pricing data through Vertex AI Gemini calls without explicitly documenting the zero-retention configuration, audit-trail components, or customer-side deployment options that Dr. Kim's technical due diligence will require. Architectural additions are needed (specified in §Architectural Additions). These fit inside the 72-hour Sprint 1 envelope because they are configuration flags, a §3 subsection, and one additional container-boot validator. They do not require redesigning orchestration topology, agent routing, or deterministic anchors.

Third, Implicit Claim 6 (Mihai-Costea automation status) is the single most existentially load-bearing verification gate in the audit. The solvo.ai/about page explicitly describes him as "automating any process he can get his hands on" — and the entire Pilot Onramp premise is that prospect data normalization is unautomated. If Mihai has shipped an internal parser, the Pilot Onramp solves a non-problem. Externally unverifiable; must be resolved on the first scoping call.

Gemini's positioning rewrites are partially retained (cold email compliance anchor) and partially rejected — the proposed Vidyard voiceover that names "Dr. Kim's engineering team" violates the Master PRD §7.6 hard no-go framing on named-person references at first contact.

## Positioning Edits

**Demo Script (Master PRD §3.3 Magic Moment scenario):** No change to the existing 0:00–0:30 cold-open. The Magic Moment is tight at 30 seconds and shouldn't be expanded to fit compliance language; that belongs in the post-Magic-Moment architecture walkthrough. Verify in the demo edit that the walkthrough section explicitly shows the boot validator output confirming "Vertex AI zero-retention enabled, europe-west4 region binding confirmed, audit outbox initialized."

**Vidyard Voiceover (Master PRD §5, Beat 2 "Showing the deterministic anchor"):** Insert one sentence immediately before the existing closing of Beat 2. Revised:

> *"The Gemini extraction is bracketed on both sides. Pydantic schemas reject any unexpected field at ingress. The validation rules engine rejects any impossible port code, any negative rate, any validity window in the past. **Every payload routes through Vertex AI in europe-west4 with zero data retention — prospect data lives in your processing region only and is destroyed at job completion.** Nothing the LLM extracts can land in your engine input without passing both gates."*

**Outreach Email Body (Master PRD §5 cold email frame):** No change to the opening line. Insert one sentence in the body between the white-box description and the engine-ready handoff. Revised:

> *"The architecture is white-box by design: every flagged lane shows which validation rule triggered, every rejection cites the exact failing constraint. **Every payload routes through Vertex AI in europe-west4 with zero retention enabled — the ISO 27001 perimeter holds by default.** Your engine ingests engine-ready data..."*

**Magic Moment Frame:** Unchanged.

## Architectural Additions Required

Add a new ULTIMATE_PRD §3.10 titled *"Compliance Posture (ISO 27001:2022 Alignment)"* with six sub-elements:

§3.10.1 Vertex AI zero-retention configuration (explicit disable of data logging on every client invocation; verified at boot).
§3.10.2 Data residency (europe-west4 binding on all services, repeated for compliance documentation).
§3.10.3 Retention windows (7-day raw uploads, 90-day normalized outputs, 365-day audit trail, all customer-configurable).
§3.10.4 Audit trail extension (new `access_log` outbox event type, internal `GET /internal/v1/audit/{job_id}` endpoint).
§3.10.5 Container-boot validator addition (fourth boot check: Vertex AI compliance handshake confirming zero-retention configuration).
§3.10.6 Customer-side deployment option (Phase 2 ladder — same images deploy to customer's GCP project).

**Sprint 1 envelope fit:** ~50 lines of new code, one Alembic migration, two configuration changes. Fits inside 72-hour build. §3.10.6 is documentation only for Sprint 1.

Full §3.10 content provided as a separate drop-in file (`prd_patches.md`).

## First-Scoping-Call Verification Gates

**Gate 1 — Mihai-Costea automation status (Implicit Claim 6).**

*Question:* "On the pre-pilot side — when a forwarder sends you a rate book during scoping, how does that data make it from their spreadsheet into a shape your engine can ingest? Is your team handling that manually right now, or has Mihai's platform work already absorbed it?"

*Confirms:* "Mostly me / Sarah doing it in spreadsheets," "Partial automation but edge cases need manual work," "We've been talking about building a parser." Sprint proceeds.

*Invalidates:* "Mihai shipped a parser last quarter, we don't need that." Sprint commitment pauses. Pivot to Phase 2 Procurement Lens conversation or close engagement gracefully.

**Gate 2 — Pre-pilot vs post-pilot dichotomy (Implicit Claim 1).**

*Question:* "The carrier case study describes an automated API workflow for daily rate generation — when does that workflow kick in during a new engagement? From day one of evaluation, or more after the carrier has signed a pilot contract?"

*Confirms:* "Post-pilot," "Once they're integrated," "API workflow runs in production; pilot evaluation is more bespoke." Sprint proceeds.

*Invalidates:* "From day one — even prospects get the API workflow immediately." Repositioning required; return to Step 1B with constraint that prospect data ingestion is already automated.

**Gate 3 — ISO 27001 compliance + HubSpot CRM verification.**

*Question:* "Quick compliance question for the proposal — for prospect data routing during pilot evaluation, what's the data-residency and retention posture your ISO 27001 perimeter requires? And for the standing-capacity engagement, where would post-pilot artifacts land — HubSpot, or are you on a different stack?"

*Confirms architecture additions sufficient:* "europe-west4 is fine," "Zero retention is what we already require," "HubSpot for CRM." Sprint proceeds with §3.10 as specified; Phase 2 HubSpot assumption confirmed.

*Requires additional architecture:* "Single-tenant in our GCP," "Not HubSpot, we're on [other]." §3.10.6 elevated from Phase 2 to Sprint 1 if single-tenant required; Phase 2 Procurement Lens re-scoped to actual CRM if not HubSpot.

*Decision rule:* This gate informs scope, not whether the sprint proceeds. Sprint always proceeds (assuming Gates 1 and 2 pass); what gets built may shift.

## Acknowledgement

Verdict locked. Sprint paused pending the 15-minute scoping call with Bajaj. The cold email may be sent immediately; sprint commitment depends on Gate 1 and Gate 2 resolution. Gate 3 informs scope but does not block the sprint.

The §3.10 Architectural Additions are baked into the Sprint 1 build spec. Cold email and scoping-call briefing produced separately (`outreach_bundle.md`).
