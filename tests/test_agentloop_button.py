"""v2.1.5 页脚 agent loop 按钮：左对齐排队布局 + 点击展开/收起。

用户指定（2026-10-30）：按钮用 H 版样式（type=text / size=small，无边框），
放在页脚行里「已完成」之后左对齐排队，点击后把过程面板 append 到卡片末尾。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from hermes_lark_streaming.cardkit.elements import _build_footer_elements
from hermes_lark_streaming.composer import agentloop

DATA = {
    "duration": 5.9, "model": "q/deepseek-flash", "provider": "uni-api",
    "reasoning_effort": "中", "context_used": 177_900, "context_max": 1_000_000,
}
FIELDS = [["status", "elapsed", "model", "provider", "reasoning", "context"]]
BUTTON = {"key": "abc123def456", "label": "agent loop · 4"}


def _footer(**kwargs):
    return _build_footer_elements(DATA, fields=FIELDS, style="icon", **kwargs)


def test_button_row_is_left_aligned_queue():
    hr, row = _footer(agentloop=BUTTON)
    assert hr["tag"] == "hr"
    assert row["tag"] == "column_set"
    cols = row["columns"]
    assert len(cols) == 3
    # 左列 = 只有「已完成」，中间 = 按钮，右侧 = 其余字段（weighted 吃剩余宽度）
    assert cols[0]["width"] == "auto"
    assert "已完成" in cols[0]["elements"][0]["i18n_content"]["zh_cn"]
    assert "5.9s" not in cols[0]["elements"][0]["i18n_content"]["zh_cn"]
    assert cols[1]["width"] == "auto"
    button = cols[1]["elements"][0]
    assert button["tag"] == "button"
    assert button["type"] == "text" and button["size"] == "small"
    assert button["text"]["content"] == "agent loop · 4"
    value = button["behaviors"][0]["value"]
    assert value == {"hermes_agentloop_action": "toggle", "panel_key": "abc123def456"}
    assert cols[2]["width"] == "weighted"
    rest = cols[2]["elements"][0]["i18n_content"]["zh_cn"]
    assert rest.startswith("⏳ 5.9s") and "177.9K/1.0M (17%)" in rest


def test_without_button_footer_stays_single_markdown():
    elements = _footer()
    assert [el["tag"] for el in elements] == ["hr", "markdown"]


def test_button_dropped_when_no_status_field():
    """fields 里没有 status 时不能凭空造按钮 —— 退回整行 markdown。"""
    elements = _build_footer_elements(DATA, fields=[["elapsed", "model"]], style="icon", agentloop=BUTTON)
    assert [el["tag"] for el in elements] == ["hr", "column_set"]
    assert elements[1]["columns"][1]["elements"][0]["text"]["content"] == "agent loop · 4"


def test_registry_register_and_lookup():
    agentloop._REGISTRY.clear()
    key = agentloop.new_key()
    agentloop.register(key, {"card_id": "c1", "status_lines": ["a", "b"], "seq": 7})
    rec = agentloop.lookup(key)
    assert rec and rec["seq"] == 7 and rec["expanded"] is False
    agentloop._REGISTRY.clear()


def test_registry_ttl_expiry(monkeypatch):
    agentloop._REGISTRY.clear()
    key = agentloop.new_key()
    agentloop.register(key, {"card_id": "c1"})
    agentloop._REGISTRY[key]["created_at"] -= agentloop._TTL_SEC + 1
    assert agentloop.lookup(key) is None


class _FakeClient:
    def __init__(self):
        self.calls = []

    async def cardkit_batch_update(self, card_id, actions, sequence=None):
        self.calls.append((card_id, actions, sequence))
        return {"ok": True}


def _adapter():
    client = _FakeClient()
    return SimpleNamespace(_get_card_client=lambda: client), client


def _action(key):
    return SimpleNamespace(event=SimpleNamespace(action=SimpleNamespace(
        value={"hermes_agentloop_action": "toggle", "panel_key": key})))


def test_handle_action_expands_then_collapses():
    agentloop._REGISTRY.clear()
    key = agentloop.new_key()
    agentloop.register(key, {
        "card_id": "card_1", "status_lines": ["💻 运行命令 `ls`"], "seq": 5,
        "title": "agent loop · 1 个工具",
    })
    adapter, client = _adapter()

    assert asyncio.run(agentloop.handle_action(adapter, _action(key))) is True
    card_id, actions, seq = client.calls[-1]
    assert card_id == "card_1" and seq == 6
    assert actions[0]["action"] == "add_elements"
    assert actions[0]["params"]["type"] == "append"
    assert actions[0]["params"]["elements"][0]["element_id"] == "agent_process_panel"
    assert agentloop.lookup(key)["expanded"] is True

    assert asyncio.run(agentloop.handle_action(adapter, _action(key))) is True
    card_id, actions, seq = client.calls[-1]
    assert actions[0]["action"] == "delete_elements"
    assert seq == 7
    assert agentloop.lookup(key)["expanded"] is False


def test_handle_action_ignores_unknown_key():
    agentloop._REGISTRY.clear()
    adapter, client = _adapter()
    assert asyncio.run(agentloop.handle_action(adapter, _action("missing"))) is True
    assert client.calls == []


def test_handle_action_returns_false_for_other_actions():
    adapter, _ = _adapter()
    other = SimpleNamespace(event=SimpleNamespace(action=SimpleNamespace(value={"foo": 1})))
    assert asyncio.run(agentloop.handle_action(adapter, other)) is False
