"""页脚「agent loop」按钮：点击后把整块过程面板追加到卡片底部（v2.1.5）.

用户诉求（2026-10-30）：过程面板不再占正文上方整块空间，改成页脚同一行里
一个收窄的按钮（``agent loop · 4``），点一下才在卡片末尾展开完整过程行。

设计约束与取舍：

- **面板元素只能块级**：飞书 Card 2.0 的 ``collapsible_panel`` 不能内联进
  markdown 行，所以"同一行"用 ``column_set`` 实现 —— 左列页脚 markdown、
  右列小按钮（``size: small`` + ``type: text``）。
- **点击走卡片回调**：按钮 ``behaviors`` 带 ``callback`` + ``panel_key``，
  插件 ``_handle_card_action_event`` 收到后由本模块追加/删除面板。
- **面板数据不常驻内存**：定稿时把状态行快照存进本模块的注册表（TTL 1 小时、
  上限 200 条），键是随机 ``panel_key``；过了保留期或网关重启后点击只会留
  一条日志，不会报错，也不会影响已送达的答案。
- **落点**：``append`` 到卡片末尾（实测 code=0）—— 正是 E 版预览的形态。
"""

from __future__ import annotations

import logging
import time
import uuid
from types import SimpleNamespace
from typing import Any

_logger = logging.getLogger("hermes_lark_streaming.composer")

#: 面板快照保留时长（秒）与条目上限。用户点开面板属于"事后回顾"，
#: 1 小时够用；超出后点击静默失效，不占内存。
_TTL_SEC = 3600
_MAX_ENTRIES = 200

_REGISTRY: dict[str, dict[str, Any]] = {}


def new_key() -> str:
    """生成一个 panel_key（定稿前先生成，页脚按钮里带上）。"""
    return uuid.uuid4().hex[:12]


def register(key: str, payload: dict[str, Any]) -> None:
    """登记一次回合的面板快照（定稿后调用，此时 ``seq`` 已是最终值）。"""
    _gc()
    record = dict(payload)
    record["seq"] = int(record.get("seq") or 0)
    record["created_at"] = time.monotonic()
    record.setdefault("expanded", False)
    _REGISTRY[key] = record
    while len(_REGISTRY) > _MAX_ENTRIES:
        oldest = min(_REGISTRY, key=lambda k: _REGISTRY[k].get("created_at", 0))
        _REGISTRY.pop(oldest, None)


def _gc() -> None:
    cutoff = time.monotonic() - _TTL_SEC
    for key in [k for k, v in _REGISTRY.items() if v.get("created_at", 0) < cutoff]:
        _REGISTRY.pop(key, None)


def lookup(key: str) -> dict[str, Any] | None:
    _gc()
    return _REGISTRY.get(key)


def build_panel(payload: dict[str, Any], *, expanded: bool) -> dict[str, Any]:
    """按快照重建过程面板（与定稿期同款渲染，``turn_state='finalized'`` 全绿）。"""
    from ..cardkit.cards import _apply_panel_title, _render_status_children
    from ..cardkit.elements import UNIFIED_PANEL_ELEMENT_ID, _build_unified_panel_placeholder

    panel = _build_unified_panel_placeholder(expanded=expanded)
    panel["element_id"] = UNIFIED_PANEL_ELEMENT_ID
    _apply_panel_title(panel, str(payload.get("title") or "agent loop"))
    panel["elements"] = _render_status_children(
        payload.get("status_lines") or [],
        durations=payload.get("durations") or {},
        line_times=payload.get("line_times") or [],
        turn_state="finalized",
    )
    return panel


async def handle_action(adapter: Any, data: Any) -> bool:
    """卡片动作入口：展开（``append`` 面板）/ 收起（删面板）。返回是否已消费。"""
    event = getattr(data, "event", None)
    value = getattr(getattr(event, "action", None), "value", {}) or {}
    if not isinstance(value, dict) or not value.get("hermes_agentloop_action"):
        return False

    key = str(value.get("panel_key") or "")
    payload = lookup(key)
    if payload is None:
        _logger.info("agentloop: panel snapshot missing/expired key=%s", key[:12])
        return True

    client = adapter._get_card_client()  # noqa: SLF001 — 适配器内部约定
    if client is None:
        _logger.info("agentloop: card client unavailable key=%s", key[:12])
        return True

    from ..cardkit.elements import UNIFIED_PANEL_ELEMENT_ID
    from ..cardkit.seq import call_with_seq_recovery

    card_id = str(payload.get("card_id") or "")
    seq_holder = SimpleNamespace(seq=int(payload.get("seq") or 0) + 1)
    try:
        if payload.get("expanded"):
            await call_with_seq_recovery(
                seq_holder,
                lambda seq: client.cardkit_batch_update(
                    card_id,
                    [{"action": "delete_elements", "params": {"element_ids": [UNIFIED_PANEL_ELEMENT_ID]}}],
                    sequence=seq,
                ),
                what="agentloop:collapse",
            )
            payload["expanded"] = False
        else:
            panel = build_panel(payload, expanded=True)
            await call_with_seq_recovery(
                seq_holder,
                lambda seq: client.cardkit_batch_update(
                    card_id,
                    [{"action": "add_elements", "params": {"type": "append", "elements": [panel]}}],
                    sequence=seq,
                ),
                what="agentloop:expand",
            )
            payload["expanded"] = True
        payload["seq"] = seq_holder.seq
        _logger.info(
            "agentloop: %s card=%s rows=%d seq=%d",
            "expanded" if payload["expanded"] else "collapsed", card_id,
            len(payload.get("status_lines") or []), seq_holder.seq,
        )
    except Exception:
        _logger.warning(
            "agentloop: toggle failed card=%s key=%s", card_id, key[:12], exc_info=True)
    return True
