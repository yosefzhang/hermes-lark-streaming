"""v2.1.1: footer provider 解析（V1 补丁回归）."""

from __future__ import annotations

import sys
from types import ModuleType

from hermes_lark_streaming.composer.finalize import _resolve_provider_name


def _install_gateway(monkeypatch, provider: str) -> None:
    gateway = ModuleType("gateway")
    gateway.__path__ = []  # type: ignore[attr-defined]
    run = ModuleType("gateway.run")
    run._load_gateway_config = lambda: {"model": {"provider": provider}}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.run", run)


def test_custom_provider_uses_actual_name(monkeypatch) -> None:
    _install_gateway(monkeypatch, "custom:uni-api")
    assert _resolve_provider_name() == "uni-api"


def test_builtin_provider_passthrough(monkeypatch) -> None:
    _install_gateway(monkeypatch, "openrouter")
    assert _resolve_provider_name() == "openrouter"


def test_missing_provider_returns_empty(monkeypatch) -> None:
    _install_gateway(monkeypatch, "")
    assert _resolve_provider_name() == ""


def test_gateway_unavailable_returns_empty(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "gateway", None)
    monkeypatch.setitem(sys.modules, "gateway.run", None)
    assert _resolve_provider_name() == ""
