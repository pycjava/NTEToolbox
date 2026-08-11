"""T-A1 多候选建议测试（alternatives）。

竞品差距（LLM 独有）：传统 tracker 只给"一个"推荐，竞品都只给 1 个解。
LLM 能给 2-3 个合理打法 + 各自权衡，让玩家自己判断——这是"教练"而非
"指挥"的核心差异。

设计：Advice 增加 alternatives 字段（list of {headline, why}），可选。
- 主推荐仍在 headline（向后兼容）
- alternatives 只在"两种打法都合理"时提供（uncertain 场景最值钱）
- 解析层：LLM 可选返回 alternatives，没有则空列表
- 向后兼容：既有 advice.json（无 alternatives）仍正常解析
"""

import unittest

from hscoach.coach import Advice, _parse_advice, get_system_prompt


class ParseAlternativesTest(unittest.TestCase):
    """_parse_advice 解析 alternatives 字段。"""

    def test_advice_has_alternatives_field(self):
        """Advice dataclass 有 alternatives 字段，默认空列表。"""
        adv = Advice()
        self.assertEqual(adv.alternatives, [])

    def test_parse_extracts_alternatives(self):
        """LLM 返回 alternatives 时正确解析。"""
        raw = """{
            "kind": "uncertain",
            "headline": "解场或打脸都可",
            "why": "场面均势",
            "steps": [],
            "warning": "",
            "alternatives": [
                {"headline": "解场", "why": "更稳，防反扑"},
                {"headline": "打脸", "why": "抢血，但风险高"}
            ]
        }"""
        adv = _parse_advice(raw)
        self.assertEqual(len(adv.alternatives), 2)
        self.assertEqual(adv.alternatives[0]["headline"], "解场")
        self.assertEqual(adv.alternatives[1]["why"], "抢血，但风险高")

    def test_parse_without_alternatives_is_empty(self):
        """LLM 不返回 alternatives 时为空列表（向后兼容）。"""
        raw = '{"kind":"play","headline":"x","why":"","steps":[],"warning":""}'
        adv = _parse_advice(raw)
        self.assertEqual(adv.alternatives, [])

    def test_malformed_alternatives_graceful(self):
        """alternatives 不是列表或元素非对象时，降级为空列表（不崩）。"""
        raw = '{"kind":"play","headline":"x","why":"","alternatives":"不是列表"}'
        adv = _parse_advice(raw)
        self.assertEqual(adv.alternatives, [])

    def test_alternative_missing_fields_tolerated(self):
        """候选缺 why 字段时不崩，填空串。"""
        raw = '{"kind":"uncertain","headline":"x","alternatives":[{"headline":"只 headline"}]}'
        adv = _parse_advice(raw)
        self.assertEqual(len(adv.alternatives), 1)
        self.assertEqual(adv.alternatives[0]["headline"], "只 headline")
        self.assertEqual(adv.alternatives[0]["why"], "")

    def test_to_dict_includes_alternatives(self):
        """advice.json 序列化包含 alternatives（前端可消费）。"""
        adv = Advice(
            kind="uncertain",
            headline="x",
            alternatives=[{"headline": "plan B", "why": "备选"}],
        )
        d = adv.to_dict()
        self.assertIn("alternatives", d)
        self.assertEqual(len(d["alternatives"]), 1)

    def test_legacy_advice_json_still_parses(self):
        """旧版 advice.json（无 alternatives 字段）仍能解析为 Advice。

        回归防线：overlay/前端消费老文件不能崩。
        """
        legacy = '{"kind":"play","headline":"出火球","why":"斩杀","steps":[],"warning":""}'
        adv = _parse_advice(legacy)
        self.assertEqual(adv.headline, "出火球")
        self.assertEqual(adv.alternatives, [])


class PromptEncouragesAlternativesTest(unittest.TestCase):
    """教学模式 prompt 引导 LLM 在 uncertain 时给 alternatives。"""

    def test_teach_prompt_mentions_alternatives(self):
        """教学模式应在核心规则里鼓励给 alternatives（uncertain 场景）。"""
        p = get_system_prompt("teach")
        self.assertIn("alternatives", p.lower())

    def test_compete_prompt_optional_alternatives(self):
        """竞赛模式不强求 alternatives（要简洁）。"""
        p = get_system_prompt("compete")
        # 竞赛模式可以提或不提，但不强制——这里只验证不崩
        self.assertIsInstance(p, str)


if __name__ == "__main__":
    unittest.main()
