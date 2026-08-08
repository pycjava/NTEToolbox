"""T5(05) 状态序列化测试。

验证：
- 真实 Game 能序列化成 GameSnapshot
- D9 核心：对手手牌只见数量、不见 CardID；序列化带 CardID 的"对手"
  手牌时直接拒绝（fail loud）
- 己方手牌含卡名/费用/效果/CardID
- 卡牌效果文本被注入（不靠模型记忆）
- 友方玩家 id 自动校准（detect_friendly_player_id）
- 序列化结果可转 dict（喂 LLM 用）
"""

import json
import logging
import unittest
from pathlib import Path

logging.disable(logging.WARNING)

from hearthstone.enums import GameTag, Zone
from hscoach.log_parser import parse_power_log
from hscoach.state import (
    _extract_flags,
    detect_friendly_player_id,
    serialize_game,
)
from tests._helpers import card_db, read_fixture_lines


class StateSerializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 4000 行：已过调度阶段，手牌已揭示（fixture 当前玩家是 1）
        result = parse_power_log(read_fixture_lines(4000))
        cls.game = result.games[0]
        cls.db = card_db()

    def test_serializes_into_snapshot(self):
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        self.assertEqual(len(snap.players), 2)
        self.assertIn(1, snap.players)
        self.assertIn(2, snap.players)

    def test_friendly_hand_has_card_details(self):
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        friendly = snap.players[1]
        self.assertFalse(friendly.hand_is_hidden)
        # 己方手牌是列表（4000 行时应有牌）
        self.assertIsInstance(friendly.hand, list)
        self.assertGreater(len(friendly.hand), 0)
        # 己方手牌卡带 card_id（T4：每张卡 CardID）
        self.assertTrue(all(c.card_id for c in friendly.hand))

    def test_d9_opponent_hand_is_count_only(self):
        """D9 核心：对手手牌只见数量，不是卡牌列表。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        opponent = snap.players[2]
        self.assertTrue(opponent.hand_is_hidden)
        self.assertIsInstance(opponent.hand, int)  # 数量，非列表

    def test_d9_no_opponent_cardid_in_output(self):
        """序列化输出的 dict 里，对手手牌区绝不含 CardID 或卡名。

        （场上/己方侧的 card_id 是合法公开信息；D9 只禁对手手牌。）
        """
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        d = snap.to_dict()
        opponent_hand = d["players"][2]["hand"]
        # 对手手牌应只有 count 字段
        self.assertEqual(set(opponent_hand.keys()), {"count"})

    def test_current_player_id_detected_from_player_entities(self):
        """CURRENT_PLAYER 只写在玩家实体上时（0/1 置位），快照仍能取到
        当前玩家 id（回归：曾恒为 None 导致回合触发永不生效）。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        self.assertEqual(snap.current_player_id, 1)  # 4000 行 = turn 4，玩家1 当前

    def test_d9_swapped_mapping_refuses_serialization(self):
        """把友好 id 传反（真实友方=1，却传 2）：对手侧会出现 CardID，
        D9 断言必须拒绝序列化——防止把对手手牌当己方发给 LLM。"""
        with self.assertRaises(AssertionError):
            serialize_game(self.game, friendly_player_id=2, db=self.db)

    def test_friendly_card_id_in_dict_output(self):
        """T4：己方手牌卡的 CardID 应出现在输出 dict 里（供卡牌库核对）。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        d = snap.to_dict()
        friendly_hand = d["players"][1]["hand"]
        self.assertGreater(len(friendly_hand), 0)
        self.assertIn("card_id", friendly_hand[0])
        self.assertTrue(friendly_hand[0]["card_id"])

    def test_card_text_is_injected(self):
        """己方手牌/场上的卡带效果文本（来自卡牌库）。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        all_cards = list(snap.players[1].hand) + list(snap.players[1].board)
        for c in all_cards:
            self.assertTrue(hasattr(c, "text"))
        with_text = [c for c in all_cards if c.text]
        # 4000 行时应有至少一张带效果文本的牌
        self.assertGreater(len(with_text), 0)

    def test_snapshot_is_json_serializable(self):
        """快照可转 JSON（喂 LLM 用）。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        blob = json.dumps(snap.to_dict(), ensure_ascii=False)
        self.assertIsInstance(blob, str)
        self.assertGreater(len(blob), 0)

    def test_opponent_hand_count_matches(self):
        """对手手牌数量应等于实际该 zone 实体数。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        actual = [
            e for e in self.game.in_zone(Zone.HAND)
            if e.tags.get(GameTag.CONTROLLER) == 2
        ]
        self.assertEqual(snap.players[2].hand, len(actual))

    def test_works_without_card_db(self):
        """无卡牌库时仍可序列化（卡名回退到 CardID）。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=None)
        self.assertEqual(len(snap.players), 2)

    def test_damaged_field_serialized(self):
        """受伤字段（damaged）在输出 dict 中键名一致。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        d = snap.to_dict()
        board = d["players"][1]["board"]
        for c in board:
            self.assertIn("damaged", c)


class FriendlyPlayerDetectionTest(unittest.TestCase):
    """日志自动校准（D9 防线：手牌含 CardID 的玩家即友方）。"""

    def test_detects_friendly_player_1_from_fixture(self):
        result = parse_power_log(read_fixture_lines(4000))
        self.assertEqual(detect_friendly_player_id(result.games[-1]), 1)

    def test_returns_none_when_hands_empty(self):
        """开局调度阶段双方手牌都空 → 无法判断，返回 None（沿用现有值）。"""
        result = parse_power_log(read_fixture_lines(1500))
        self.assertIsNone(detect_friendly_player_id(result.games[-1]))


class FlagExtractionTest(unittest.TestCase):
    def test_exhausted_flag(self):
        """EXHAUSTED（已行动过）应显式提取（spec L61 的 exhausted）。"""
        flags = _extract_flags({GameTag.EXHAUSTED: 1})
        self.assertIn("已尽", flags)

    def test_untargetable_by_spells_flag(self):
        """CANT_BE_TARGETED_BY_SPELLS（不可被法术指定）应显式提取。"""
        flags = _extract_flags({GameTag.CANT_BE_TARGETED_BY_SPELLS: 1})
        self.assertIn("不可被法术指定", flags)

    def test_zero_tags_extract_nothing(self):
        self.assertEqual(_extract_flags({GameTag.TAUNT: 0}), [])


if __name__ == "__main__":
    unittest.main()

