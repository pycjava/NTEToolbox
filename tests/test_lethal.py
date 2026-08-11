"""T-L1 斩杀/伤害计算器测试。

竞品差距分析结论：HDT/网易盒子都有"本回合伤害"提示，本品缺。
LLM 算术能力不可靠（已知缺陷），教练必须代码级 100% 准确计算
"场攻 + 手牌已知直接伤害"，并把结果注入 prompt + advice。

设计原则（纯函数，可严格 TDD）：
- 只用 GameSnapshot 里己方合法可见信息（己方场面随从 attack、己方
  手牌中可造成直接伤害的法术/随从 charge-rush）
- 不模拟、不猜测（不翻对手手牌/牌库），只做确定的加法
- 输出结构化 LethalCheck：available_damage、lethal(布尔)、detail 列表
- 留法力过滤：超费伤害不计入（cost > 当前法力的牌本回合打不出）
"""

import logging
import unittest

logging.disable(logging.WARNING)

from hscoach.lethal import CardView, LethalCheck, compute_lethal
from hscoach.state import GameSnapshot, PlayerView

logger = logging.getLogger(__name__)


def _card(
    name: str = "",
    attack: int | None = None,
    health: int | None = None,
    cost: int | None = 0,
    flags: list[str] | None = None,
    text: str = "",
    card_id: str | None = None,
) -> CardView:
    """构造测试用 CardView（ lethal 计算器复用 state.CardView）。"""
    return CardView(
        card_id=card_id,
        name=name,
        cost=cost,
        attack=attack,
        health=health,
        flags=flags or [],
        text=text,
    )


def _player(
    health: int = 30,
    armor: int = 0,
    mana: int = 10,
    max_mana: int = 10,
    hand: list | None = None,
    board: list | None = None,
    hand_is_hidden: bool = False,
) -> PlayerView:
    return PlayerView(
        name="测试",
        hero=None,
        health=health,
        armor=armor,
        mana=mana,
        max_mana=max_mana,
        hand=hand or [],
        hand_is_hidden=hand_is_hidden,
        board=board or [],
        deck_count=0,
    )


def _snapshot(friendly: PlayerView, opponent: PlayerView) -> GameSnapshot:
    return GameSnapshot(
        turn=5,
        current_player_id=1,
        players={1: friendly, 2: opponent},
    )


class BoardDamageTest(unittest.TestCase):
    """场攻求和：己方场上可攻击随从的总 attack（排除已尽/冻结）。"""

    def test_empty_board_zero_damage(self):
        opp = _player()
        check = compute_lethal(_snapshot(_player(), opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_single_minion_attack_counts(self):
        friendly = _player(board=[_card(attack=5, health=5)])
        opp = _player()
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 5)

    def test_multiple_minions_sum(self):
        friendly = _player(board=[
            _card(attack=3, health=3),
            _card(attack=4, health=4),
            _card(attack=6, health=6),
        ])
        opp = _player()
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 13)

    def test_exhausted_minion_excluded(self):
        """已尽（本回合行动过）的随从不计入场攻。"""
        friendly = _player(board=[
            _card(attack=5, health=5, flags=["已尽"]),
            _card(attack=3, health=3),
        ])
        opp = _player()
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 3)

    def test_frozen_minion_excluded(self):
        """冻结的随从本回合不能攻击。"""
        friendly = _player(board=[
            _card(attack=5, health=5, flags=["冻结"]),
            _card(attack=3, health=3),
        ])
        opp = _player()
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 3)

    def test_cant_attack_minion_excluded(self):
        """无法攻击（CANT_ATTACK，如减攻到 0 的守卫）不计入。"""
        friendly = _player(board=[
            _card(attack=0, health=5, flags=["无法攻击"]),
            _card(attack=3, health=3),
        ])
        opp = _player()
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 3)

    def test_zero_attack_minion_excluded(self):
        """0 攻随从对场面伤害无贡献。"""
        friendly = _player(board=[_card(attack=0, health=5)])
        opp = _player()
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 0)


class LethalDetectionTest(unittest.TestCase):
    """lethal = available_damage >= opponent(health + armor)。"""

    def test_exact_lethal_detected(self):
        """场攻恰好等于对手血量 → lethal=True（斩杀）。"""
        friendly = _player(board=[_card(attack=7, health=7)])
        opp = _player(health=7)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertTrue(check.lethal)
        self.assertEqual(check.available_damage, 7)

    def test_overkill_lethal(self):
        friendly = _player(board=[_card(attack=10, health=10)])
        opp = _player(health=5)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertTrue(check.lethal)

    def test_armor_counts_against_lethal(self):
        """护甲抵消：场攻 < 血+甲 → 非斩杀。"""
        friendly = _player(board=[_card(attack=7, health=7)])
        opp = _player(health=5, armor=5)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertFalse(check.lethal)

    def test_armor_exact_lethal(self):
        """场攻 = 血 + 甲 → 斩杀（护甲被打穿后致死）。"""
        friendly = _player(board=[_card(attack=10, health=10)])
        opp = _player(health=5, armor=5)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertTrue(check.lethal)

    def test_non_friendly_turn_no_lethal(self):
        """对手回合不计算 lethal（无法攻击）。"""
        friendly = _player(board=[_card(attack=10, health=10)])
        opp = _player(health=5)
        snap = GameSnapshot(turn=5, current_player_id=2, players={1: friendly, 2: opp})
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertFalse(check.lethal)


class HandDamageTest(unittest.TestCase):
    """手牌中能本回合造成直接打脸伤害的牌（法术/冲锋），受法力约束。

    本测试集验证"已知直接伤害"的加总——补 LLM 算术短板的核心。
    实现策略保守：只识别 text 中明确写"造成 N 点伤害"的法术，N 用
    正则提取；冲锋随从（charge）attack 计入。超费不计。
    """

    def test_damage_spell_within_mana_counts(self):
        """2 费火球术文本'造成 $ 点伤害'（此处用占位），可支付 → 计入。

        用明确文本'造成 6 点伤害'便于正则提取（HearthstoneJSON 实际
        文本经 clean_text 后是'造成 6 点伤害'）。
        """
        fireball = _card(name="火球术", cost=4, text="对一个角色造成 6 点伤害。")
        friendly = _player(
            mana=10,
            board=[_card(attack=4, health=4)],
            hand=[fireball],
        )
        opp = _player(health=10)
        check = compute_lethal(_snapshot(friendly, opp))
        # 场攻 4 + 火球 6 = 10
        self.assertEqual(check.available_damage, 10)
        self.assertTrue(check.lethal)

    def test_damage_spell_over_mana_excluded(self):
        """超费法术本回合打不出，不计入。"""
        fireball = _card(name="火球术", cost=10, text="造成 6 点伤害。")
        friendly = _player(mana=4, hand=[fireball])
        opp = _player(health=6)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 0)
        self.assertFalse(check.lethal)

    def test_non_damage_spell_not_counted(self):
        """抽牌/增益类法术不计入直接伤害。"""
        draw_spell = _card(name="奥术智慧", cost=3, text="抽两张牌。")
        friendly = _player(mana=10, hand=[draw_spell])
        opp = _player(health=2)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 0)

    def test_multiple_damage_spells_sum(self):
        a = _card(name="a", cost=1, text="造成 3 点伤害。")
        b = _card(name="b", cost=2, text="造成 2 点伤害。")
        friendly = _player(mana=3, hand=[a, b])
        opp = _player(health=5)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertEqual(check.available_damage, 5)

    def test_damage_spell_only_part_of_mana_budget(self):
        """两张伤害法术只能支付一张时，取伤害最大的（贪心近似）。"""
        cheap = _card(name="小", cost=2, text="造成 2 点伤害。")
        big = _card(name="大", cost=8, text="造成 8 点伤害。")
        friendly = _player(mana=8, hand=[cheap, big])
        opp = _player(health=10)
        check = compute_lethal(_snapshot(friendly, opp))
        # 只够打 big（8 费 8 伤），cheap 超预算
        self.assertEqual(check.available_damage, 8)

    def test_knapsack_finds_truly_optimal_not_greedy(self):
        """0-1 背包反例：贪心会选错，DP 必须选最优组合。

        法力 5：
        - A: 2费6伤（效率3.0，贪心先选）
        - B: 3费5伤（效率1.67）
        - C: 2费4伤（效率2.0）
        贪心选 A(剩3费)→选不下 B(3费) 但能选 C(2费)? 剩3费选C(2费)=6+4=10
        但最优是 B+C=3+2=5费 5+4=9伤，或 A+C=2+2=4费 6+4=10伤
        实际最优：A+C=10伤（4费）。贪心按效率选A后剩3费选C也=10。
        换个反例：法力5，A=2费6伤，B=3费5伤 → 贪心选A(剩3)选B(3费5伤)=11
        真正反例：法力4，A=3费5伤(效率1.67)，B=2费3伤(1.5)，C=2费3伤(1.5)
        贪心选A(剩1)选不下BC = 5伤；最优 B+C=4费6伤。
        """
        a = _card(name="A", cost=3, text="造成 5 点伤害。")
        b = _card(name="B", cost=2, text="造成 3 点伤害。")
        c = _card(name="C", cost=2, text="造成 3 点伤害。")
        friendly = _player(mana=4, hand=[a, b, c])
        opp = _player(health=6)
        check = compute_lethal(_snapshot(friendly, opp))
        # DP 应选 B+C=6伤（4费），而非贪心的 A=5伤
        self.assertEqual(check.available_damage, 6)
        self.assertTrue(check.lethal)


class DetailFormatTest(unittest.TestCase):
    """lethal.detail 提供可读的"伤害来源清单"，供注入 prompt。"""

    def test_detail_lists_sources(self):
        minion = _card(name="雪人", attack=5, health=5)
        spell = _card(name="火球术", cost=4, text="造成 6 点伤害。")
        friendly = _player(mana=10, board=[minion], hand=[spell])
        opp = _player(health=11)
        check = compute_lethal(_snapshot(friendly, opp))
        self.assertTrue(check.lethal)
        # detail 是来源列表，每个来源有 name + damage
        self.assertGreater(len(check.detail), 0)
        names = [d["name"] for d in check.detail]
        self.assertIn("雪人", names)
        self.assertIn("火球术", names)
        total = sum(d["damage"] for d in check.detail)
        self.assertEqual(total, 11)

    def test_summary_string(self):
        """check.summary() 给一句可读结论（注入 LLM prompt 用）。"""
        friendly = _player(board=[_card(attack=7, health=7)])
        opp = _player(health=7)
        check = compute_lethal(_snapshot(friendly, opp))
        s = check.summary()
        self.assertIsInstance(s, str)
        self.assertIn("7", s)
        self.assertTrue(check.lethal)


if __name__ == "__main__":
    unittest.main()
