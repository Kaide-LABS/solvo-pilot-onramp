"""Boot validator unit tests. PHASE_1_SPEC §9 criterion 8."""

from __future__ import annotations

from typing import Any

import pytest

from packages.compliance import boot_validators as bv
from packages.core.settings import get_settings


@pytest.mark.asyncio
async def test_vertex_handshake_passes_with_responsive_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validator returns passed=True when the client yields at least one candidate."""

    class _FakeResp:
        candidates = [object()]

    class _FakeModels:
        async def generate_content(self, **_kwargs: Any) -> _FakeResp:
            return _FakeResp()

    class _FakeAio:
        models = _FakeModels()

    class _FakeClient:
        aio = _FakeAio()

    monkeypatch.setattr(bv, "get_vertex_client", lambda _settings: _FakeClient())
    result = await bv._validate_vertex_handshake(get_settings())
    assert result.passed is True
    assert result.exit_code_on_failure == 1
    assert "europe-west4" in result.detail


@pytest.mark.asyncio
async def test_vertex_handshake_fails_on_no_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validator returns passed=False when the response has no candidates."""

    class _FakeResp:
        candidates: list[object] = []

    class _FakeModels:
        async def generate_content(self, **_kwargs: Any) -> _FakeResp:
            return _FakeResp()

    class _FakeAio:
        models = _FakeModels()

    class _FakeClient:
        aio = _FakeAio()

    monkeypatch.setattr(bv, "get_vertex_client", lambda _settings: _FakeClient())
    result = await bv._validate_vertex_handshake(get_settings())
    assert result.passed is False


@pytest.mark.asyncio
async def test_compliance_validator_requires_zdr_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In production, missing ZDR enrollment fails validator 4 with exit code 4."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()

    async def _noop_disable(_settings: Any, _model: str) -> None:
        return None

    async def _noop_assert(_settings: Any, _model: str) -> None:
        return None

    monkeypatch.setattr(bv, "disable_request_response_logging", _noop_disable)
    monkeypatch.setattr(bv, "assert_request_response_logging_disabled", _noop_assert)

    result = await bv._validate_vertex_compliance(get_settings())
    assert result.passed is False
    assert result.exit_code_on_failure == 4
    assert "ZDR" in result.detail


@pytest.mark.asyncio
async def test_postgres_alembic_head_passes_on_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validator 2 — alembic_version row matches expected head."""

    class _Row:
        def __init__(self, v: str) -> None:
            self._v = v

        def __getitem__(self, _i: int) -> str:
            return self._v

    class _Result:
        def first(self) -> _Row:
            return _Row("0001_initial")

    class _Conn:
        async def execute(self, *_a: Any, **_kw: Any) -> _Result:
            return _Result()

        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

    class _Engine:
        def connect(self) -> _Conn:
            return _Conn()

        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(bv, "create_async_engine", lambda *_a, **_kw: _Engine())
    result = await bv._validate_postgres_alembic_head(get_settings())
    assert result.passed is True
    assert result.exit_code_on_failure == 2
    assert "0001_initial" in result.detail


@pytest.mark.asyncio
async def test_postgres_alembic_head_fails_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validator 2 fails when DB head does not match expected."""

    class _Row:
        def __getitem__(self, _i: int) -> str:
            return "9999_wrong"

    class _Result:
        def first(self) -> _Row:
            return _Row()

    class _Conn:
        async def execute(self, *_a: Any, **_kw: Any) -> _Result:
            return _Result()

        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

    class _Engine:
        def connect(self) -> _Conn:
            return _Conn()

        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(bv, "create_async_engine", lambda *_a, **_kw: _Engine())
    result = await bv._validate_postgres_alembic_head(get_settings())
    assert result.passed is False
    assert result.exit_code_on_failure == 2


@pytest.mark.asyncio
async def test_un_locode_table_absent_short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validator 3 — Phase 1 short-circuits to passed=True when table is absent."""

    class _NoRow:
        def first(self) -> None:
            return None

    class _Conn:
        async def execute(self, *_a: Any, **_kw: Any) -> _NoRow:
            return _NoRow()

        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

    class _Engine:
        def connect(self) -> _Conn:
            return _Conn()

        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(bv, "create_async_engine", lambda *_a, **_kw: _Engine())
    result = await bv._validate_un_locode_table_integrity(get_settings())
    assert result.passed is True
    assert result.exit_code_on_failure == 3
    assert "short_circuit" in result.detail


@pytest.mark.asyncio
async def test_compliance_validator_passes_in_development_without_zdr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Development environment is allowed to run without ZDR enrollment."""

    async def _noop_disable(_settings: Any, _model: str) -> None:
        return None

    async def _noop_assert(_settings: Any, _model: str) -> None:
        return None

    monkeypatch.setattr(bv, "disable_request_response_logging", _noop_disable)
    monkeypatch.setattr(bv, "assert_request_response_logging_disabled", _noop_assert)

    result = await bv._validate_vertex_compliance(get_settings())
    assert result.passed is True
    assert "rrl_disabled=True" in result.detail
