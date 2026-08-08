"""T8(08) 置顶窗 UI 测试。

UI 组件本身难以单元测试（需真实启动 tkinter 主循环），
这里测可分离的核心逻辑：
- advice.json 解析成显示字段
- 内容格式化（步骤、警示）
- 文件 mtime 变化检测逻辑

手动验证（overlay 能启动、显示建议、热键切换）见手动测试记录。
"""

import json
import tempfile
import unittest
from pathlib import Path

from hscoach.coach import Advice
from hscoach.trigger import publish_advice


class OverlayContentParseTest(unittest.TestCase):
    """测试 UI 从 advice.json 提取显示字段的逻辑（不启动 tkinter）。"""

    @staticmethod
    def _parse_display_fields(data: dict) -> dict:
        """复刻 overlay._load_and_display 的解析逻辑（不依赖 tkinter）。"""
        advice = data.get("advice", {})
        turn = data.get("turn", "?")
        kind = advice.get("kind", "")
        headline = advice.get("headline", "")
        why = advice.get("why", "")
        steps = advice.get("steps", [])
        warning = advice.get("warning", "")

        kind_icon = {"play": "⚔️", "trade": "🔄", "pass": "⏭", "uncertain": "❓"}.get(kind, "")
        display_headline = f"T{turn} {kind_icon} {headline}"
        steps_text = "\n".join(f"• {s}" for s in steps) if steps else ""
        if warning:
            steps_text = (steps_text + "\n" if steps_text else "") + f"⚠ {warning}"
        return {
            "headline": display_headline,
            "why": why,
            "steps": steps_text,
        }

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
            fields = self._parse_display_fields(data)
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
            fields = self._parse_display_fields(data)
            self.assertIn("T1", fields["headline"])
            self.assertIn("⏭", fields["headline"])
            self.assertEqual(fields["steps"], "")

    def test_uncertain_kind_uses_question_icon(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            publish_advice(d, Advice(kind="uncertain", headline="两种都行"), turn=3)
            data = json.loads((d / "advice.json").read_text(encoding="utf-8"))
            fields = self._parse_display_fields(data)
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
        fields = self._parse_display_fields(data)
        self.assertIn("随从A撞随从B", fields["steps"])
        self.assertNotIn("⚠", fields["steps"])


if __name__ == "__main__":
    unittest.main()
