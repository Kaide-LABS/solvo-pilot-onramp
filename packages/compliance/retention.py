"""Project-level Vertex AI retention controls. Implements PHASE_1_SPEC.md §7.2.

See PHASE_1_SPEC §0.5 for the discrepancy between the §3.10 patch's per-request
assumption and the actual Vertex AI surface. Zero-retention is configured at
the project + publisher-model level, not via per-call SDK parameters.

The exact SDK surface for `set_request_response_logging_config` has moved
across `google-cloud-aiplatform` versions and is not stable on the top-level
`aiplatform` module in 1.91.x. When the call site is unavailable we log a
warning and fall through — the production-gate invariant (`ZDR enrolled`
env var) is enforced separately in `boot_validators._validate_vertex_compliance`
and remains load-bearing.
"""

from __future__ import annotations

import asyncio
import logging

from packages.core.settings import Settings

_log = logging.getLogger(__name__)


def _publisher_model_class():
    """Return the PublisherModel class if the SDK exposes it, else None."""
    from google.cloud import aiplatform

    return getattr(aiplatform, "PublisherModel", None)


async def disable_request_response_logging(settings: Settings, model_id: str) -> None:
    """Disable request/response logging for the given publisher model.

    Idempotent. When the installed `google-cloud-aiplatform` SDK does not
    expose `PublisherModel` at the top-level (the case in 1.91.x), this
    function logs a warning and returns — the production ZDR env-var gate
    (`vertex_ai_zdr_enrolled`) is the load-bearing check enforced in
    `boot_validators._validate_vertex_compliance`.
    """

    def _sync() -> None:
        from google.cloud import aiplatform

        cls = _publisher_model_class()
        if cls is None:
            _log.warning(
                "aiplatform.PublisherModel unavailable in installed SDK "
                "(%s); skipping set_request_response_logging_config for %s. "
                "Production ZDR enrollment is enforced via env var.",
                getattr(aiplatform, "__version__", "?"),
                model_id,
            )
            return
        aiplatform.init(
            project=settings.gcp_project_id,
            location=settings.vertex_location,
        )
        publisher_model = cls(f"publishers/google/models/{model_id}")
        publisher_model.set_request_response_logging_config(
            enabled=False,
            sampling_rate=1.0,
            bigquery_destination=None,
        )

    await asyncio.to_thread(_sync)


async def assert_request_response_logging_disabled(settings: Settings, model_id: str) -> None:
    """Read back the publisher-model logging config and assert disabled.

    Same SDK-availability fallthrough as `disable_request_response_logging`.
    Raises AssertionError if logging is unexpectedly enabled.
    """

    def _sync() -> None:
        from google.cloud import aiplatform

        cls = _publisher_model_class()
        if cls is None:
            _log.warning(
                "aiplatform.PublisherModel unavailable; "
                "skipping logging-disabled read-back for %s.",
                model_id,
            )
            return
        aiplatform.init(
            project=settings.gcp_project_id,
            location=settings.vertex_location,
        )
        publisher_model = cls(f"publishers/google/models/{model_id}")
        cfg = publisher_model.get_request_response_logging_config()
        if getattr(cfg, "enabled", True):
            raise AssertionError(f"request/response logging unexpectedly enabled for {model_id}")

    await asyncio.to_thread(_sync)
