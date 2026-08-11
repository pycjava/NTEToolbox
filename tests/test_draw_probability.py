"""T-D1 抽牌概率测试（超几何分布）。

竞品差距：HDT 核心价值之一是"下回合抽到 X 的概率""起手有 Y 的概率"。
本品原缺。纯组合数学，无需 LLM，补齐致命缺口。

设计：超几何分布 H(N, K, n)：
- N = 牌库剩余总数
- K = 目标牌在牌库中的剩余张数（如 2 张火球术的剩余 copies）
- n = 抽牌次数（下回合抽 1 张，或"未来 n 回合抽 n 张"）
- P(至少抽到 1 张) = 1 - C(N-K, n) / C(N, n)

边界：
- 牌库 0 或目标牌 0 → 概率 0
- n > N → 抽穿牌库，目标牌在则概率 1
- n=0 → 不抽，概率 0
"""

import unittest

from hscoach.probability import (
    draw_at_least_one,
    draw_exact,
    draw_probability_summary,
)


class HypergeometricTest(unittest.TestCase):
    """超几何分布核心：P(至少抽到 1 张目标牌)。"""

    def test_simple_case(self):
        """牌库 30 张含 2 张目标牌，抽 1 张 → P = 2/30。"""
        p = draw_at_least_one(deck_size=30, copies=2, draws=1)
        self.assertAlmostEqual(p, 2 / 30, places=6)

    def test_zero_copies(self):
        """目标牌不在牌库 → 概率 0。"""
        self.assertEqual(draw_at_least_one(30, 0, 1), 0.0)

    def test_zero_deck(self):
        """牌库空 → 概率 0。"""
        self.assertEqual(draw_at_least_one(0, 0, 1), 0.0)

    def test_zero_draws(self):
        """不抽牌 → 概率 0。"""
        self.assertEqual(draw_at_least_one(30, 2, 0), 0.0)

    def test_all_copies_in_small_deck(self):
        """牌库全都是目标牌 → 抽任意一张必中。"""
        self.assertEqual(draw_at_least_one(5, 5, 1), 1.0)

    def test_draws_exceed_deck(self):
        """抽牌次数 >= 牌库数且目标牌在 → 概率 1（抽穿）。"""
        self.assertEqual(draw_at_least_one(10, 2, 10), 1.0)
        self.assertEqual(draw_at_least_one(10, 2, 15), 1.0)

    def test_probability_increases_with_draws(self):
        """抽得越多，至少抽到 1 张的概率越高（单调性）。"""
        p1 = draw_at_least_one(30, 2, 1)
        p2 = draw_at_least_one(30, 2, 2)
        p5 = draw_at_least_one(30, 2, 5)
        self.assertLess(p1, p2)
        self.assertLess(p2, p5)

    def test_probability_increases_with_copies(self):
        """目标牌张数越多，概率越高。"""
        p1 = draw_at_least_one(30, 1, 1)
        p2 = draw_at_least_one(30, 2, 1)
        self.assertLess(p1, p2)

    def test_two_draws_correct_value(self):
        """牌库 30 含 2 张，抽 2 张 → P = 1 - C(28,2)/C(30,2)。

        C(28,2)=378, C(30,2)=435 → P = 1 - 378/435 ≈ 0.1310
        """
        p = draw_at_least_one(30, 2, 2)
        expected = 1 - (378 / 435)
        self.assertAlmostEqual(p, expected, places=6)

    def test_known_combo(self):
        """经典案例：牌库 25 含 2 张斩杀组件，3 回合内抽到概率。

        P = 1 - C(23,3)/C(25,3) = 1 - 1771/2300 ≈ 0.2300
        """
        p = draw_at_least_one(25, 2, 3)
        expected = 1 - (1771 / 2300)
        self.assertAlmostEqual(p, expected, places=6)

    def test_returns_in_unit_interval(self):
        """概率恒在 [0, 1]。"""
        for N in range(1, 30, 5):
            for K in range(0, N + 1, 3):
                for n in range(0, N + 2, 4):
                    p = draw_at_least_one(N, K, n)
                    self.assertGreaterEqual(p, 0.0)
                    self.assertLessEqual(p, 1.0)


class DrawExactTest(unittest.TestCase):
    """P(恰好抽到 k 张) —— 补充指标。"""

    def test_zero_target_zero_draw(self):
        self.assertEqual(draw_exact(30, 2, 1, 0), 1 - 2 / 30)
        # 抽 1 张恰好 0 张目标 = 抽到非目标 = 28/30

    def test_one_draw_one_target(self):
        """抽 1 张恰好抽到 1 张目标 = 2/30。"""
        self.assertAlmostEqual(draw_exact(30, 2, 1, 1), 2 / 30, places=6)

    def test_k_exceeds_possible(self):
        """要求抽到的张数 > 目标牌总数 → 概率 0。"""
        self.assertEqual(draw_exact(30, 2, 5, 3), 0.0)


class SummaryTest(unittest.TestCase):
    """draw_probability_summary 给可读结论（注入 prompt/overlay 用）。"""

    def test_summary_contains_percentage(self):
        s = draw_probability_summary(deck_size=30, copies=2, draws=1)
        self.assertIsInstance(s, str)
        # 含百分号（人读友好）
        self.assertIn("%", s)

    def test_summary_next_turn_draw(self):
        """默认抽 1 张（下回合）。"""
        s = draw_probability_summary(deck_size=30, copies=2, draws=1)
        # 2/30 ≈ 6.67%
        self.assertIn("6", s)

    def test_summary_zero_copies(self):
        s = draw_probability_summary(deck_size=30, copies=0, draws=1)
        self.assertIn("0", s)


if __name__ == "__main__":
    unittest.main()
