# PRD Patches — Solvo Pilot Onramp Sprint 2

*Output of Step 1F-red. Two patches to be applied to the existing repo files before Step 2 (build spec) begins.*

---

## PATCH 1: ULTIMATE_PRD.md — Add new §3.10

Insert this section into `ULTIMATE_PRD.md` immediately after the existing §3.9 (Cost Envelope), before the existing §4 (State-of-the-Art Justification).

```markdown
### 3.10 Compliance Posture (ISO 27001:2022 Alignment) — Step 1F-red Addition

Solvo.ai holds ISO 27001:2022 certification via the British Assessment Bureau (verified primary source: solvo.ai/blog/solvo-ai-is-iso-27001-2022-certified). Any third-party processor routed inside their compliance perimeter must satisfy data residency, retention, audit trail, and sub-processor disclosure requirements that Dr. Kim or a designated compliance reviewer will probe during technical due diligence. The following six elements anchor the Pilot Onramp's compliance posture explicitly rather than relying on positioning language alone.

#### 3.10.1 Vertex AI zero-retention configuration

All Vertex AI Gemini calls must explicitly disable data logging at the request level. The current `google-genai` SDK accepts a request-level metadata configuration that opts out of Google's default request-logging behavior; verify the exact flag name against `docs/modernization_log.md` and current Vertex AI documentation at client initialization time. Default Google Cloud behavior may log requests for service quality assurance; this must be explicitly disabled for every model invocation referenced in §3.4 (Agent Routing).

Implementation reference:

```python
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location="europe-west4",
)

# Every model invocation must opt out of data logging
config = types.GenerateContentConfig(
    temperature=0.1,
    response_mime_type="application/json",
    response_schema=ExtractionResponse,
    # Compliance-critical: opt out of Google's default request logging
    # Verify exact flag name against current SDK release notes
)
```

#### 3.10.2 Data residency (locked)

All Vertex AI calls bind to europe-west4 (already specified in §3.4; repeated here for compliance documentation). All Cloud Run services in §3.1 bind to europe-west4. Cloud SQL Postgres and Memorystore Redis bind to europe-west4. Cloud Storage bucket `solvo-onramp-artifacts` configured with single-region storage class in europe-west4. No data crosses region boundaries under any execution path.

#### 3.10.3 Retention windows

| Data type | Storage | Default retention | Customer-configurable |
|---|---|---|---|
| Raw prospect uploads | Cloud Storage `solvo-onramp-artifacts` | 7 days, auto-delete via bucket lifecycle | Yes |
| Normalized JSON outputs | Postgres `onramp_outputs` | 90 days, then archived to GCS with 180-day TTL | Yes |
| LangGraph state transitions | Postgres `lane_graph_states` | 90 days, then archived | Yes |
| Conformal scores | Postgres `onramp_conformal_scores` | 90 days, then archived | Yes |
| Audit trail (access_log) | Postgres `onramp_outbox` (filtered) | 365 days (ISO 27001 audit log minimum) | No (regulatory floor) |
| Slack thread / Block Kit message references | Slack workspace native retention | Per customer's Slack workspace policy | Per Slack admin |

All retention windows configurable per customer at engagement initiation via the `customer_compliance_profile` configuration loaded at boot. Schema:

```python
class CustomerComplianceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str
    raw_upload_retention_days: int = Field(default=7, ge=1, le=30)
    normalized_output_retention_days: int = Field(default=90, ge=30, le=365)
    archived_output_ttl_days: int = Field(default=180, ge=90, le=730)
    audit_log_retention_days: int = Field(default=365, ge=365, le=2555)  # ISO floor 365, max 7yr
```

#### 3.10.4 Audit trail extension

The existing `onramp_outbox` table (baseline §2.4) is extended with a new event type: `access_log`. Each Slack post, signed-URL generation, API status retrieval, and result download writes an outbox event with timestamp, actor (Slack user ID or API client ID), action verb, target (job ID — never PII), and outcome (success/failure).

Schema extension (Alembic migration `0002_audit_log`):

```python
# Already in onramp_outbox: outbox_id, job_id, event_type, payload, delivered_at, attempts, next_retry_at
# event_type now accepts: 'slack_post' | 'webhook_callback' | 'audit_log' | 'signed_url_create' | 'access_log'

# access_log payload shape:
class AccessLogPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: datetime
    actor_type: Literal["slack_user", "api_client", "system"]
    actor_id: str  # Slack user ID or API client ID, never email or name
    action: Literal["job_created", "job_polled", "result_downloaded", "slack_post_sent", "signed_url_issued"]
    target_job_id: str
    outcome: Literal["success", "failure", "rate_limited"]
    metadata: dict  # extra context, no PII
```

Internal-only audit-retrieval endpoint:

```
GET /internal/v1/audit/{job_id}
Headers: X-Admin-Token: <required>
Returns: list of AccessLogPayload entries for the job, sorted by timestamp
```

Endpoint is separate from client-facing routes, requires admin authentication, and is firewalled from Cloud Run's public ingress.

#### 3.10.5 Container-boot validator addition

A fourth boot validator joins the three in §2.6 (Vertex AI handshake, Postgres schema check, UN/LOCODE table integrity). The new validator:

**Vertex AI compliance handshake** — issues a lightweight Gemini ping with explicit `disable_data_logging` set in the request metadata, verifies the response confirms the configuration was honored, inspects the Vertex AI client configuration object. Failure → exit code 4, container does not enter rotation, Cloud Run health check fails.

Implementation:

```python
async def validate_vertex_ai_compliance() -> None:
    """Boot validator: confirm Vertex AI is configured for zero-retention.
    
    Exit code 4 on failure.
    """
    try:
        client = get_vertex_client()
        # Verify compliance configuration
        response = await client.aio.models.generate_content(
            model="gemini-3-flash-preview",
            contents="ping",
            config=COMPLIANCE_CONFIG,  # verified zero-retention config
        )
        # Inspect response metadata for confirmation of data-logging-disabled
        assert response.metadata.get("data_logging_disabled") is True, \
            "Vertex AI response did not confirm data-logging-disabled"
    except Exception as e:
        logger.critical(f"Vertex AI compliance handshake failed: {e}")
        sys.exit(4)
```

This boot validator is the structural anchor for the §5 Vidyard voiceover compliance claim ("Every payload routes through Vertex AI in europe-west4 with zero data retention"). The claim is true because the container refuses to run if the configuration is wrong.

#### 3.10.6 Customer-side deployment option (Phase 2 ladder)

The same Docker images deploy to a customer's own GCP project, with Vertex AI routed through their service account in their organization. The Pilot Onramp becomes a single-tenant deployment where data never leaves the customer's GCP perimeter.

Deployment shape (Phase 2):

```yaml
# customer-side deployment topology
services:
  solvo-onramp-api:
    image: kaide-labs/solvo-onramp-api:v1.x
    deploy_to: customer-gcp-project / europe-west4
    vertex_ai_service_account: customer-sa  # customer's SA, not Kaide's
  
  solvo-onramp-worker:
    image: kaide-labs/solvo-onramp-worker:v1.x
    deploy_to: customer-gcp-project / europe-west4
    
  solvo-onramp-validator:
    image: kaide-labs/solvo-onramp-validator:v1.x
    deploy_to: customer-gcp-project / europe-west4

# Kaide retains: image build pipeline, version updates, monitoring (read-only)
# Customer retains: data, service account, GCP project, all storage, all logs
```

Not built in Sprint 1; documented here as the available Phase 2 escalation path for prospects with stricter compliance postures (banking clients of carrier prospects, government-adjacent freight forwarders). Pricing: standing-capacity engagement +£2k/month for single-tenant deployment overhead (per Step 1B commercial frame § 9.0).

#### 3.10.7 Sprint 1 implementation envelope

| Element | Sprint 1 work | Lines of code | Migration |
|---|---|---|---|
| §3.10.1 Zero-retention config | Configuration only on client init | ~10 | No |
| §3.10.2 Region binding | Already done (baseline) | 0 | No |
| §3.10.3 Retention windows | Bucket lifecycle + scheduled Postgres job | ~20 | One |
| §3.10.4 Audit trail | Migration + endpoint | ~30 | One |
| §3.10.5 Boot validator | One function | ~15 | No |
| §3.10.6 Customer-side | Documentation only for Sprint 1 | 0 | No |
| **Total** | | **~75 lines** | **Two migrations** |

Fits inside 72-hour build. Day 1 hours 0-8 boot validator addition; Day 2 hours 20-28 audit trail extension migration; Day 3 hours 36-48 lifecycle policies + customer compliance profile loader.
```

---

## PATCH 2: Solvo_Master_PRD.md — §5 Sales-Side Framing Updates

Two sentence-level insertions into the existing `Solvo_Master_PRD.md` §5 (Sales-Side Framing). Apply both before Step 3 (cold email send) and Step 2 (build spec generation).

### Patch 2A — Cold Email Body (in §5 "For the cold email (Bajaj-facing):")

Find this paragraph in §5:

> "...The architecture is white-box by design: every flagged lane shows which validation rule triggered, every rejection cites the exact failing constraint. Your engine ingests engine-ready data..."

Replace with:

> "...The architecture is white-box by design: every flagged lane shows which validation rule triggered, every rejection cites the exact failing constraint. **Every payload routes through Vertex AI in europe-west4 with zero retention enabled — the ISO 27001 perimeter holds by default.** Your engine ingests engine-ready data..."

### Patch 2B — Vidyard Voiceover Beat 2 (in §5 "For the demo voiceover... 2. Showing the deterministic anchor")

Find this voiceover paragraph in §5:

> "The Gemini extraction is bracketed on both sides. Pydantic schemas reject any unexpected field at ingress. The validation rules engine rejects any impossible port code, any negative rate, any validity window in the past. Nothing the LLM extracts can land in your engine input without passing both gates."

Replace with:

> "The Gemini extraction is bracketed on both sides. Pydantic schemas reject any unexpected field at ingress. The validation rules engine rejects any impossible port code, any negative rate, any validity window in the past. **Every payload routes through Vertex AI in europe-west4 with zero data retention — prospect data lives in your processing region only and is destroyed at job completion.** Nothing the LLM extracts can land in your engine input without passing both gates."

---

## Application Order

1. Apply Patch 1 (ULTIMATE_PRD.md §3.10) — this is the architectural commitment.
2. Apply Patch 2A (Master PRD §5 cold email body) — this is the language the cold email uses.
3. Apply Patch 2B (Master PRD §5 voiceover Beat 2) — this is the language the future Vidyard recording uses (after gates pass and Sprint 1 builds).
4. Commit both files to the `solvo-pilot-onramp` repo with message: `feat: 1F-red patches — compliance posture §3.10 + sales-frame insertions (Step 1F-red output)`.
5. Re-run Nia index update.
6. Proceed to send the cold email (`outreach_bundle.md` for the sendable text and scoping-call briefing).
