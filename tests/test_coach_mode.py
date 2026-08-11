"""T-M1 教练模式开关测试（教学/竞赛/静默）。

竞品差距（LLM 独有）：传统 tracker 只能给一种固定信息密度。LLM 教练
能按玩家需求切换"详细讲解 vs 一句话决策"——这是 HDT/Firestone 做不到的。

三种模式：
- teach（教学，默认）：多讲原理，why/steps 详细，适合学习
- compete（竞赛）：只给一句主推荐 + 关键风险，极简，适合天梯快速决策
- silent（静默）：只在高价值时刻发声（斩杀/致命误判），减少干扰

实现：SYSTEM_PROMPT 按模式拼接不同的"风格指令"。
"""

import unittest

from hscoach.coach import COACH_MODES, get_system_prompt


class CoachModeTest(unittest.TestCase):
    def test_three_modes_defined(self):
        """三种模式都有定义。"""
        self.assertIn("teach", COACH_MODES)
        self.assertIn("compete", COACH_MODES)
        self.assertIn("silent", COACH_MODES)

    def test_default_mode_is_teach(self):
        """默认教学模式（对新玩家友好）。"""
        prompt = get_system_prompt()
        self.assertEqual(get_system_prompt("teach"), prompt)

    def test_unknown_mode_falls_back_to_teach(self):
        """未知模式回退教学（安全默认）。"""
        self.assertEqual(get_system_prompt("nonsense"), get_system_prompt("teach"))

    def test_teach_mode_emphasizes_explanation(self):
        """教学模式强调讲原理、详细。"""
        p = get_system_prompt("teach")
        # 教学模式应包含"原理/为什么/详细"类引导
        self.assertTrue(
            "原理" in p or "为什么" in p or "详细" in p or "解释" in p,
            f"教学模式应强调讲解，实际：{p[:200]}",
        )

    def test_compete_mode_emphasizes_concise(self):
        """竞赛模式强调简洁、一句话决策。"""
        p = get_system_prompt("compete")
        self.assertTrue(
            "简洁" in p or "一句话" in p or "简短" in p,
            f"竞赛模式应强调简洁，实际：{p[:200]}",
        )

    def test_silent_mode_emphasizes_restraint(self):
        """静默模式强调克制，只在关键时刻发声。"""
        p = get_system_prompt("silent")
        self.assertTrue(
            "静默" in p or "克制" in p or "只在" in p or "关键" in p,
            f"静默模式应强调克制，实际：{p[:200]}",
        )

    def test_all_modes_share_core_rules(self):
        """三种模式共享核心规则：JSON 格式、D9 合规、kind 词典。

        回归防线：模式只改风格，不改数据契约——overlay 解析不能因模式
        不同而崩。
        """
        for mode in COACH_MODES:
            p = get_system_prompt(mode)
            self.assertIn("JSON", p, f"{mode} 缺 JSON 格式要求")
            self.assertIn("kind", p, f"{mode} 缺 kind 词典")
            self.assertIn("合法可见", p, f"{mode} 缺 D9 合规要求")

    def test_all_modes_mention_lethal_guidance(self):
        """三种模式都引导 LLM 重视斩杀判定（lethal 注入全模式生效）。"""
        for mode in COACH_MODES:
            p = get_system_prompt(mode)
            self.assertIn("斩杀", p, f"{mode} 缺斩杀判定引导")


if __name__ == "__main__":
    unittest.main()
