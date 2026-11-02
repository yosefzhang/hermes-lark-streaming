"""通知白名单必须双语命中：中文 💾 自我改进回顾 不能变成一张卡。

2026-11-02 实测：只白名单英文 `💾 Self-improvement review:` 时，每条中文通知都会
让 composer 建一张多余的卡片（每轮一张）。这组用例盯住中英两版 + 真工具行回归。
"""

from __future__ import annotations

from hermes_lark_streaming.composer.classify import _is_notice_text


def test_english_review_notice_is_notice():
    assert _is_notice_text("💾 Self-improvement review: patched skill 'feishu-cards'") is True


def test_chinese_review_notice_is_notice():
    assert _is_notice_text("💾 自我改进回顾：技能 'feishu-cards' 已修补") is True


def test_chinese_notice_with_halfwidth_colon():
    assert _is_notice_text("💾 自我改进回顾: 技能已修补") is True


def test_real_tool_line_is_not_a_notice():
    assert _is_notice_text("💻 运行命令 `ls -la`") is False
    assert _is_notice_text("🔍 检索资料") is False


def test_plain_answer_is_not_a_notice():
    assert _is_notice_text("好的，我把结果整理在下面了。") is False
