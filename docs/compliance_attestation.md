# Compliance Attestation — Solvo Pilot Onramp

Implements PHASE_6_SPEC.md §1. Audit-ready summary of the §3.10 commitments and how they are enforced at runtime.

## ISO 27001:2022 perimeter

Solvo.ai's ISO 27001 certification (British Assessment Bureau, verified primary source) sets the perimeter every third-party processor must satisfy. The Pilot Onramp's posture:

| Control | §3.10 reference | Runtime enforcement |
|---|---|---|
| Data residency | §3.10.2 | `Settings.vertex_location: Literal["europe-west4"]`; terraform `var.region` validation refuses any other value. |
| Vertex AI zero-retention | §3.10.1 + §3.10.5 | Boot validator 4 calls `set_request_response_logging_config(enabled=False)` on every publisher model, asserts the read-back, and requires `VERTEX_AI_ZDR_ENROLLED=true` in production. |
| Retention windows | §3.10.3 | `RetentionAssertion` Literal-pins the four floors (7/90/180/365); the boot validator loads `fixtures/retention_v1.json` and refuses to start on drift. Terraform GCS lifecycle rules match. |
| Audit trail | §3.10.4 | `onramp_audit_log` is append-only at the application layer; the test suite statically asserts no `UPDATE` or `DELETE` statements target the table. Phase 6 ops checklist gates Cloud SQL role privileges. |
| Access logging | §3.10.4 | Every `/v1/jobs/{id}/*` and `/internal/v1/audit/{id}` GET writes an `access_log` outbox row in the request transaction. |
| Sub-processor disclosure | §3.10.6 | Phase 2 (Phase 6 — out of scope) escalation path: customer-side deployment in the customer's own GCP project. Documented as Phase 2 commercial extension. |

## GDPR posture

- All data processing happens inside `europe-west4` (EU). No cross-border data egress.
- Raw uploads are deleted after 7 days via the GCS lifecycle rule (`infra/terraform/gcs.tf`).
- Normalized outputs are archived to Coldline at 90 days; archived blobs are deleted at 180 days.
- Audit logs are retained for 365 days minimum (ISO 27001 floor).
- Customer-configurable overrides land via `CustomerComplianceProfile` (in-memory only in Sprint 1; persistence is Phase 2 commercial extension).

## Boot-validator audit

The four §3.10.5 boot validators are the runtime gate for every production start:

1. `vertex_ai_handshake` — exit 1 if Vertex AI in europe-west4 is unreachable within 5 s.
2. `postgres_alembic_head` — exit 2 if the DB schema head ≠ `0004_intake_review`.
3. `un_locode_table_integrity` — exit 3 if the reference table has < 100,000 rows.
4. `vertex_ai_compliance_handshake` — exit 4 if request/response logging is enabled OR if ZDR is not enrolled in production.

Misconfiguration drives Cloud Run health checks to fail, the container never enters traffic rotation, and ops is alerted via Cloud Run revision health.

## Citation re-verification audit

Per `ULTIMATE_PRD.md` §4.7, the following citations were re-verified at phase boundaries:

- PHASE_2_SPEC §0.5 — Bai et al. (arXiv:2305.14336) — PROVISIONAL (ToC verified; body inaccessible at the Nia paper-search backend during this sprint).
- PHASE_4_SPEC §0.5 — Ugare et al. (arXiv:2403.01632) + Wan et al. (arXiv:2408.17017) — PROVISIONAL (same backend limitation; ToC confirmed both citations match the architectural claims).

These remain PROVISIONAL pending Nia document-agent backend recovery; the `BUILD_COMPLETE.md` summary at sprint termination carries the gate outcomes forward.
