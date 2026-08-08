"""T8(08) 置顶窗 UI 测试。

UI 组件本身难以单元测试（需真实启动 tkinter 主循环），
这里测可分离的核心逻辑（overlay.parse_display_fields，与 UI 共用单一来源）：
- advice.json 解析成显示字段
- 内容格式化（步骤、警示）
- kind 图标映射（KIND_ICONS 单一词典，UI 与测试共用）

控制窗（永不穿透的退出按钮）的窗口行为见手动验证记录：
启动 overlay → 默认穿透只作用于建议窗，控制窗始终可点。
"""

import json
import tempfile
import unittest
from pathlib import Path

from hscoach.coach import Advice
from hscoach.overlay import KIND_ICONS, parse_display_fields
from hscoach.trigger import publish_advice


class OverlayContentParseTest(unittest.TestCase):
    """测试 UI 从 advice.json 提取显示字段的逻辑（不启动 tkinter）。"""

    def test_parses_full_advice(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            adv = Advice(
                kind="play",
                headline="出火球术打脸",
                why="能斩杀对手",
                steps=["用火球术", "瞄准敌方英雄"],
                warning="注意对手有反制",
            )
            publish_advice(d, adv, turn=7)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = parse_display_fields(data)
            self.assertIn("T7", fields["headline"])
            self.assertIn("出火球术打脸", fields["headline"])
            self.assertIn("⚔️", fields["headline"])
            self.assertEqual(fields["why"], "能斩杀对手")
            self.assertIn("用火球术", fields["steps"])
            self.assertIn("⚠ 注意对手有反制", fields["steps"])

    def test_handles_minimal_advice(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="pass", headline="结束回合"), turn=1)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = parse_display_fields(data)
            self.assertIn("T1", fields["headline"])
            self.assertIn("⏭", fields["headline"])
            self.assertEqual(fields["steps"], "")

    def test_uncertain_kind_uses_question_icon(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="uncertain", headline="两种都行"), turn=3)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = parse_display_fields(data)
            self.assertIn("❓", fields["headline"])

    def test_steps_without_warning(self):
        data = {
            "turn": 2,
            "advice": {
                "kind": "trade",
                "headline": "交换",
                "why": "解场",
                "steps": ["随从A撞随从B"],
                "warning": "",
            },
        }
        fields = parse_display_fields(data)
        self.assertIn("随从A撞随从B", fields["steps"])
        self.assertNotIn("⚠", fields["steps"])

    def test_icon_map_covers_all_kinds(self):
        """KIND_ICONS 覆盖全部 kind 取值（与 coach.KINDS 对齐）。"""
        self.assertEqual(
            set(KIND_ICONS),
            {"play", "trade", "pass", "uncertain"},
        )
        # 未知 kind 不崩，图标为空
        fields = parse_display_fields({"turn": 1, "advice": {"kind": "hack", "headline": "x"}})
        self.assertEqual(fields["headline"], "T1  x")


if __name__ == "__main__":
    unittest.main()
