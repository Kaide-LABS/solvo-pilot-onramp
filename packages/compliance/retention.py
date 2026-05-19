"""Project-level Vertex AI retention controls. Implements PHASE_1_SPEC.md §7.2.

See PHASE_1_SPEC §0.5 for the discrepancy between the §3.10 patch's per-request
assumption and the actual Vertex AI surface. Zero-retention is configured at
the project + publisher-model level, not via per-call SDK parameters.
"""

from __future__ import annotations

import asyncio

from packages.core.settings import Settings


async def disable_request_response_logging(settings: Settings, model_id: str) -> None:
    """Disable request/response logging for the given publisher model.

    Idempotent — calling when already disabled is a no-op.

    The google-cloud-aiplatform PublisherModel API is synchronous; wrap in
    asyncio.to_thread so the boot validator coroutine remains async-friendly.
    """

    def _sync() -> None:
        from google.cloud import aiplatform  # type: ignore[attr-defined]

        aiplatform.init(
            project=settings.gcp_project_id,
            location=settings.vertex_location,
        )
        publisher_model = aiplatform.PublisherModel(f"publishers/google/models/{model_id}")
        publisher_model.set_request_response_logging_config(
            enabled=False,
            sampling_rate=1.0,
            bigquery_destination=None,
        )

    await asyncio.to_thread(_sync)


async def assert_request_response_logging_disabled(settings: Settings, model_id: str) -> None:
    """Read back the publisher-model logging config and assert disabled.

    Raises AssertionError if logging is unexpectedly enabled.
    """

    def _sync() -> None:
        from google.cloud import aiplatform  # type: ignore[attr-defined]

        aiplatform.init(
            project=settings.gcp_project_id,
            location=settings.vertex_location,
        )
        publisher_model = aiplatform.PublisherModel(f"publishers/google/models/{model_id}")
        cfg = publisher_model.get_request_response_logging_config()
        if getattr(cfg, "enabled", True):
            raise AssertionError(f"request/response logging unexpectedly enabled for {model_id}")

    await asyncio.to_thread(_sync)
