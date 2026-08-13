"""T-S1 奥秘提示测试（竞品对齐：HDT/盒子的"猜奥秘"基础版）。

数据驱动：从卡牌库筛"标准年卡包内该职业的奥秘"。纯函数测试用合成
Card；集成测试用真实卡牌库校验一致性（不依赖具体数值的脆弱断言）。

标准年卡包（Year of the Scarab 2026）：
CORE + EMERALD_DREAM + THE_LOST_CITY + TIME_TRAVEL + CATACLYSM +
ESCAPEFROM_VIOLET_HOLD。
"""

import unittest

from hscoach.cards import Card
from hscoach.secrets import STANDARD_SETS, possible_secrets
from tests._helpers import card_db


def _card(cid, name, card_class, card_set, text="", cost=0):
    return Card(
        id=cid, name=name, text=text, cost=cost,
        attack=None, health=None, type="SPELL",
        card_class=card_class, card_set=card_set,
    )


class PossibleSecretsPureTest(unittest.TestCase):
    """纯函数：按职业 + 标准卡包 + 奥秘文本过滤。"""

    def test_filters_class_set_and_secret_text(self):
        cards = [
            _card("a", "冰冻陷阱", "HUNTER", "CORE", "<b>奥秘：</b>当你的对手攻击时……"),
            _card("b", "爆炸陷阱", "HUNTER", "CORE", "<b>奥秘：</b>当你的英雄受到攻击时……"),
            _card("c", "照明弹", "HUNTER", "CORE", "使所有随从失去潜行。"),  # 非奥秘
            _card("d", "寒冰护体", "MAGE", "CORE", "<b>奥秘：</b>当你的英雄受到攻击时……"),  # 职业不对
            _card("e", "毒蛇陷阱", "HUNTER", "EXPERT1", "<b>奥秘：</b>……"),  # 非标准年
        ]
        names = [c.name for c in possible_secrets(cards, "HUNTER")]
        self.assertEqual(set(names), {"冰冻陷阱", "爆炸陷阱"})

    def test_sorted_by_cost(self):
        cards = [
            _card("a", "贵的奥秘", "MAGE", "CORE", "奥秘：……", cost=3),
            _card("b", "便宜的奥秘", "MAGE", "CORE", "奥秘：……", cost=2),
        ]
        names = [c.name for c in possible_secrets(cards, "MAGE")]
        self.assertEqual(names, ["便宜的奥秘", "贵的奥秘"])

    def test_unknown_class_returns_empty(self):
        cards = [_card("a", "冰冻陷阱", "HUNTER", "CORE", "奥秘：……")]
        self.assertEqual(possible_secrets(cards, "PRIEST"), [])


class PossibleSecretsIntegrationTest(unittest.TestCase):
    """真实卡牌库：结果一致性校验（不脆弱的断言）。"""

    @classmethod
    def setUpClass(cls):
        cls.cards = card_db().iter_cards()

    def test_all_results_are_standard_class_secrets(self):
        for cls_name in ("HUNTER", "MAGE", "PALADIN", "ROGUE"):
            for c in possible_secrets(self.cards, cls_name):
                self.assertEqual(c.card_class, cls_name)
                self.assertIn("奥秘", c.text)
                self.assertIn(c.card_set, STANDARD_SETS)
                self.assertEqual(c.type, "SPELL")

    def test_hunter_pool_contains_core_secrets(self):
        """猎人标准池至少含核心奥秘（冰冻/爆炸陷阱，历年核心稳定）。"""
        names = {c.name for c in possible_secrets(self.cards, "HUNTER")}
        self.assertIn("冰冻陷阱", names)
        self.assertIn("爆炸陷阱", names)

    def test_mage_pool_non_empty(self):
        """法师是经典奥秘职业，标准池不应为空。"""
        self.assertTrue(possible_secrets(self.cards, "MAGE"))

    def test_paladin_pool_not_from_rotated_sets(self):
        """圣骑近年标准池无奥秘；若有，也必须全部来自标准年卡包。"""
        for c in possible_secrets(self.cards, "PALADIN"):
            self.assertIn(c.card_set, STANDARD_SETS)


if __name__ == "__main__":
    unittest.main()
