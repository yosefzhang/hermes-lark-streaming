"""v2.1.9 fork feature: model "thinking" rows are hidden from cards by default.

Upstream renders 💬 (thinking) lines as panel rounds; the fork decided such
rows are noise for the reader (2026-11-09 user request) and drops them unless
``HLS_SHOW_THINKING`` is truthy. ``tests/conftest.py`` sets that variable for
the rest of the suite, so these tests flip the module-level flag directly.
"""

from __future__ import annotations

from hermes_lark_streaming.cardkit import cards


def _render(lines):
    return cards._render_status_children(list(lines))


def test_thinking_rows_dropped_when_flag_off(monkeypatch):
    monkeypatch.setattr(cards, "_SHOW_THINKING_LINES", False)
    kids = _render(["💬 正在检查内核", "🔧 terminal: ls"])
    flat = str(kids)
    assert "正在检查内核" not in flat
    assert "terminal" in flat.lower() or "Terminal" in flat


def test_thinking_rows_kept_when_flag_on(monkeypatch):
    monkeypatch.setattr(cards, "_SHOW_THINKING_LINES", True)
    kids = _render(["💬 正在检查内核"])
    assert "正在检查内核" in str(kids)


def test_default_flag_reads_env(monkeypatch):
    """The module-level flag is derived from HLS_SHOW_THINKING at import time."""
    import importlib
    import os

    monkeypatch.setenv("HLS_SHOW_THINKING", "0")
    mod = importlib.reload(cards)
    try:
        assert mod._SHOW_THINKING_LINES is False
    finally:
        monkeypatch.setenv("HLS_SHOW_THINKING", "1")
        importlib.reload(mod)
        assert os.environ.get("HLS_SHOW_THINKING") == "1"
