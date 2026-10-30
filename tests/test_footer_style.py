"""v2.1.4 页脚风格：``plain``（· 分隔）与 ``icon``（emoji + 全角空格）。

用户 2026-10-30 在真飞书卡片里对比 A/B/C/D 四版后选定 B（icon）。
这组用例守住两件事：默认行为逐字不变；icon 版每个字段都有图标且用全角空格分隔。
"""

from __future__ import annotations

from hermes_lark_streaming.cardkit.elements import _build_footer_elements
from hermes_lark_streaming.config import Config

DATA = {
    "duration": 5.9, "model": "q/deepseek-flash", "provider": "uni-api",
    "reasoning_effort": "中", "context_used": 177_900, "context_max": 1_000_000,
}
FIELDS = [["status", "elapsed", "model", "provider", "reasoning", "context"]]


def _content(**kwargs) -> str:
    """返回中文一行的渲染结果（页脚 markdown 的 en 行 + i18n_content.zh_cn 双语）。"""
    elements = _build_footer_elements(DATA, fields=FIELDS, **kwargs)
    assert elements, "页脚元素为空"
    el = elements[-1]
    return (el.get("i18n_content") or {}).get("zh_cn") or el["content"]


def test_plain_style_keeps_middle_dot():
    content = _content()
    assert content.startswith("已完成 · 5.9s · q/deepseek-flash")
    assert "　" not in content


def test_icon_style_prefixes_every_field():
    content = _content(style="icon")
    for icon in ("✅", "⏱", "🤖", "☁️", "🧠", "📊"):
        assert icon in content, f"{icon} 缺失：{content}"
    assert "　" in content and " · " not in content
    assert "177.9K/1.0M (17%)" in content


def test_unknown_style_falls_back_to_plain():
    assert _content(style="fancy") == _content(style="plain")


def test_error_style_icons():
    el = _build_footer_elements(DATA, is_error=True, fields=[["status"]], style="icon")[-1]
    assert "❌" in (el.get("i18n_content") or {}).get("zh_cn", "")


def test_config_footer_style_defaults_and_parsing():
    cfg = Config()
    cfg._raw = {}
    assert cfg.footer_style == "plain"
    cfg._raw = {"feishu_streaming": {"footer": {"style": "icon"}}}
    assert cfg.footer_style == "icon"
    cfg._raw = {"feishu_streaming": {"footer": {"style": "ICON"}}}
    assert cfg.footer_style == "icon"
    cfg._raw = {"feishu_streaming": {"footer": {"style": "grid"}}}
    assert cfg.footer_style == "plain"
    cfg._raw = {"feishu_streaming": {"footer": "broken"}}
    assert cfg.footer_style == "plain"
