"""v2.1.3 页脚上下文用量：``usage_from_runner`` 取数 + 定稿页脚渲染。

数据链：gateway 内存 ``_agent_cache`` → ``agent.context_compressor``
（provider 实测 ``last_prompt_tokens`` + ``context_length``）。取不到任何一项
都必须静默返回 None，页脚逐字段跳过 —— 这几条用例就是这条红线。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from hermes_lark_streaming.plugin.adapter import usage_from_runner

KEY = "agent:yosephine:feishu-streaming:dm:oc_abc123"


def _agent(used: int = 0, maximum: int = 0, pin: int = 0):
    comp = SimpleNamespace(last_prompt_tokens=used, context_length=maximum)
    return SimpleNamespace(context_compressor=comp, _config_context_length=pin)


def _runner(cache: dict | None):
    return SimpleNamespace(_agent_cache=cache) if cache is not None else SimpleNamespace()


def test_hit_returns_measured_usage():
    runner = _runner({KEY: (_agent(112520, 1_000_000), "sig", 78, "20261030_111338")})
    assert usage_from_runner(runner, "oc_abc123") == {
        "context_used": 112520, "context_max": 1_000_000,
    }


def test_other_platform_key_ignored():
    other = "agent:yosephine:feishu:dm:oc_abc123"
    runner = _runner({other: (_agent(1000, 2000), "sig", 1, "sid")})
    assert usage_from_runner(runner, "oc_abc123") is None


def test_other_chat_key_ignored():
    runner = _runner({"agent:x:feishu-streaming:dm:oc_other": (_agent(10, 20), "s", 1, "s")})
    assert usage_from_runner(runner, "oc_abc123") is None


def test_group_key_matches_when_chat_id_not_last():
    """群聊 session_key 尾部是 participant id，chat_id 在中间 —— 必须能命中。"""
    group = "agent:yosephine:feishu-streaming:group:oc_abc123:ou_user1"
    runner = _runner({group: (_agent(5000, 100_000), "s", 3, "sid")})
    assert usage_from_runner(runner, "oc_abc123") == {
        "context_used": 5000, "context_max": 100_000,
    }


def test_missing_runner_or_cache_returns_none():
    assert usage_from_runner(None, "oc_abc123") is None
    assert usage_from_runner(_runner(None), "oc_abc123") is None
    assert usage_from_runner(_runner({}), "oc_abc123") is None


def test_zero_or_missing_measurements_return_none():
    assert usage_from_runner(_runner({KEY: (_agent(0, 1_000_000), "s", 1, "s")}), "oc_abc123") is None
    assert usage_from_runner(
        _runner({KEY: (SimpleNamespace(), "s", 1, "s")}), "oc_abc123") is None


def test_window_falls_back_to_config_pin():
    runner = _runner({KEY: (_agent(500, 0, pin=300_000), "s", 1, "s")})
    assert usage_from_runner(runner, "oc_abc123") == {"context_used": 500, "context_max": 300_000}


def test_used_is_clamped_to_window():
    runner = _runner({KEY: (_agent(400_000, 300_000), "s", 1, "s")})
    assert usage_from_runner(runner, "oc_abc123") == {
        "context_used": 300_000, "context_max": 300_000,
    }


def test_bare_agent_entry_supported():
    """缓存值可能是裸 agent（非 tuple）——同样要能取到用量。"""
    runner = _runner({KEY: _agent(1234, 10_000)})
    assert usage_from_runner(runner, "oc_abc123") == {
        "context_used": 1234, "context_max": 10_000,
    }


class _FakeClient:
    """只实现页脚用到的一个 API；记录 batch_update 的 actions 供断言。"""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def cardkit_batch_update(self, card_id, actions, sequence=None):
        self.calls.append(actions)
        return {"ok": True}


def _state(usage: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        chat_id="oc_abc123", card_id="card_1", card_message_id="om_1",
        seq=1, created_at=0.0, usage=usage or {},
    )


def test_seal_footer_renders_context_field():
    from hermes_lark_streaming.composer.finalize import _seal_footer

    client = _FakeClient()
    asyncio.run(_seal_footer(
        client, _state({"context_used": 112_520, "context_max": 1_000_000}),
        footer_fields=[["context"]], show_label=False, model_name="q/deepseek-flash",
    ))
    assert client.calls, "页脚 batch_update 未发出"
    payload = str(client.calls[0])
    assert "112.5K" in payload and "(11%)" in payload


def test_seal_footer_skips_context_without_usage():
    from hermes_lark_streaming.composer.finalize import _seal_footer

    client = _FakeClient()
    asyncio.run(_seal_footer(
        client, _state(), footer_fields=[["context"]], show_label=False, model_name="m",
    ))
    # 没有用量数据 → 渲染层产出空行 → 不应发起 batch_update
    assert client.calls == []
