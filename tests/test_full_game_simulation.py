"""T-SIM 完整牌局模拟测试——把全部功能串到同一条真实链路里端到端跑一遍。

既有测试把每个功能（斩杀/抽牌概率/教练模式/多候选/调度器/发布）各自孤立
测过；本文件补的是"一场连续演进的对局"：

1. LethalWorkedExamplesTest —— 斩杀计算的独立 worked example（纯 compute_lethal，
   无调度器/LLM）。期望值全部手算，验证我对代码行为的理解与代码一致。
2. ScriptedGameSimulationTest —— 一场法师镜像（开局→铺场→不确定→背包DP→
   冲锋武器斩杀→超时降级），每回合喂进真实 compute_lethal/build_user_prompt/
   get_advice，并经真实 AdviceDispatcher（latest-wins worker 线程）发布。
3. RealFixtureFullGameTest —— 真实 Power.log fixture（15 回合）跑"解析→回合
   检测→调度→发布"的端到端保真。

期望值来自独立来源（手算算术、超几何闭式 1/N、贪心反例），不复现代码。
LLM 用 fake（LLMClient 协议），不触网。
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path

import httpx

logging.disable(logging.WARNING)

from hscoach.advice_worker import AdviceDispatcher, AdviceJob
from hscoach.lethal import compute_lethal
from hscoach.log_parser import parse_power_log
from hscoach.state import CardView, GameSnapshot, PlayerView, serialize_game
from hscoach.trigger import (
    ADVICE_FILENAME,
    GAME_STATE_FILENAME,
    IncrementalTurnDetector,
    TurnTrigger,
    publish_game_state,
)
from tests._helpers import card_db, read_fixture_lines

# 真实火球术 CS2_029 的 clean_text（build 时已去 $ 等标记），_DAMAGE_SPELL_RE 提取 6
FIREBALL_TEXT = "造成 6 点伤害。"

# build_user_prompt 第一行："=== 当前回合 N，轮到玩家 1 出牌 ==="
_TURN_OF_RE = re.compile(r"当前回合 (\d+)")


def _turn_of(user_prompt: str) -> int:
    """从 user prompt 抽取当前回合号（fake LLM 据此选预设响应）。"""
    m = _TURN_OF_RE.search(user_prompt)
    return int(m.group(1)) if m else -1


# ---------- 快照构造辅助（GameSnapshot 是文档化的公开 dataclass） ----------


def _card(name="", attack=None, health=None, cost=0, flags=None, text="", card_id=None):
    return CardView(
        card_id=card_id, name=name, cost=cost, attack=attack, health=health,
        flags=flags or [], text=text,
    )


def _me(health=30, armor=0, mana=10, max_mana=10, hand=None, board=None, deck=26):
    return PlayerView(
        name="我", hero=None, health=health, armor=armor, mana=mana,
        max_mana=max_mana, hand=hand if hand is not None else [],
        hand_is_hidden=False, board=board if board is not None else [],
        deck_count=deck,
    )


def _opp(health=30, armor=0, deck=26, hand=4):
    return PlayerView(
        name="对手", hero=None, health=health, armor=armor, mana=10,
        max_mana=10, hand=hand, hand_is_hidden=True, board=[], deck_count=deck,
    )


def _snap(turn, current, me, opp):
    return GameSnapshot(turn=turn, current_player_id=current, players={1: me, 2: opp})


# ---------- fake LLM（LLMClient 协议，不触网） ----------

_DEFAULT_PLAY = (
    '{"kind":"play","headline":"发展场面","why":"","steps":[],"warning":""}'
)
_UNCERTAIN = (
    '{"kind":"uncertain","headline":"两种打法都行","why":"互有取舍",'
    '"steps":[],"warning":"",'
    '"alternatives":['
    '{"headline":"打法A","why":"理由A"},'
    '{"headline":"打法B","why":"理由B"}'
    ']}'
)
_LETHAL_PLAY = (
    '{"kind":"play","headline":"执行斩杀","why":"伤害足够",'
    '"steps":["火球打脸","冲锋随从打脸"],"warning":""}'
)


class _ScriptedLLM:
    """按回合号返回预设响应；指定回合抛超时。记录每次调用 (turn, system, user)。"""

    def __init__(self, responses, fail_turn=None):
        self.responses = responses
        self.fail_turn = fail_turn
        self.calls = []  # list[tuple[int, str, str]] —— (turn, system, user)

    def chat(self, system, user, timeout=None):
        turn = _turn_of(user)
        self.calls.append((turn, system, user))
        if turn == self.fail_turn:
            raise httpx.TimeoutException("模拟超时")
        return self.responses.get(turn, _DEFAULT_PLAY)


class _DispatcherHarness:
    """启动/停止真实 AdviceDispatcher worker 线程（测 latest-wins 在连续对局里的行为）。"""

    def __init__(self, handler):
        self.d = AdviceDispatcher()
        self.stop = threading.Event()
        self.thread = threading.Thread(
            target=self.d.run_loop, args=(handler, self.stop), daemon=True
        )

    def start(self):
        self.thread.start()

    def wait_idle(self, timeout=5.0):
        """等 worker 处理完当前 job 且 pending 为空。"""
        deadline = time.monotonic() + timeout
        while not self.d.is_idle() and time.monotonic() < deadline:
            time.sleep(0.005)
        return self.d.is_idle()

    def shutdown(self):
        self.stop.set()
        self.thread.join(timeout=3)


# =====================================================================
# 1. 斩杀计算 worked examples（纯 compute_lethal，独立手算期望值）
# =====================================================================


class LethalWorkedExamplesTest(unittest.TestCase):
    """先验证斩杀/背包的行为与独立手算一致——后续完整牌局依赖这些期望值。"""

    def test_opponent_turn_has_zero_lethal(self):
        """对手回合：友方不能攻击/出牌 → 空的 LethalCheck（available_damage=0）。"""
        snap = _snap(
            turn=2, current=2,
            me=_me(board=[_card(name="雪人", attack=5, health=5)]),
            opp=_opp(health=1),
        )
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertFalse(check.lethal)
        self.assertEqual(check.available_damage, 0)

    def test_knapsack_beats_greedy(self):
        """Spec 审查 #4：0-1 背包取最优，胜过按 dmg/cost 贪心。

        手牌三张伤害法术，法力 4：
        - 高费大火球 cost3 dmg5（dmg/cost≈1.67 最高，贪心会先选它 → 花3剩1 → 5）
        - 低费小伤1 cost2 dmg3（1.5）
        - 低费小伤2 cost2 dmg3（1.5）
        DP 选两张小伤（花 4）→ 6 > 5。断言 available_damage==6 且大火球未被选。
        """
        snap = _snap(
            turn=7, current=1,
            me=_me(mana=4, deck=20, board=[], hand=[
                _card(name="高费大火球", cost=3, text="造成 5 点伤害"),
                _card(name="低费小伤1", cost=2, text="造成 3 点伤害"),
                _card(name="低费小伤2", cost=2, text="造成 3 点伤害"),
            ]),
            opp=_opp(health=30),
        )
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertEqual(check.available_damage, 6)
        names = {d["name"] for d in check.detail}
        self.assertIn("低费小伤1", names)
        self.assertIn("低费小伤2", names)
        self.assertNotIn("高费大火球", names)

    def test_lethal_charge_weapon_minion_spell(self):
        """三源斩杀：场攻(随从+武器) + 伤害法术 + 冲锋随从。

        友方场：4/4 随从 + 4 攻武器（在 PLAY zone，无"已尽"）；手牌：火球术
        (4费6伤) + 冲锋随从(5费3攻)；法力 9；对手 14 血。
        场攻=4+4=8；背包同时取火球+冲锋(cost9)=6+3=9；合计 17≥14 → 斩杀。
        """
        snap = _snap(
            turn=9, current=1,
            me=_me(mana=9, deck=18, board=[
                _card(name="雪人", attack=4, health=4),
                _card(name="武器", attack=4, health=None),
            ], hand=[
                _card(name="火球术", cost=4, text=FIREBALL_TEXT),
                _card(name="冲锋怪", cost=5, attack=3, health=3, flags=["冲锋"]),
            ]),
            opp=_opp(health=14, deck=18),
        )
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertTrue(check.lethal)
        self.assertEqual(check.available_damage, 17)
        self.assertEqual(check.deficit, 0)
        # 按来源汇总（不依赖 detail 顺序）
        by_src: dict[str, int] = {}
        for d in check.detail:
            by_src[d["source"]] = by_src.get(d["source"], 0) + d["damage"]
        self.assertEqual(by_src.get("board", 0), 8)   # 随从 4 + 武器 4
        self.assertEqual(by_src.get("spell", 0), 6)   # 火球术
        self.assertEqual(by_src.get("charge", 0), 3)  # 冲锋随从

    def test_real_card_db_feeds_lethal(self):
        """真实卡牌库 → clean_text → lethal 正则：火球术 CS2_029 造成 6 点伤害。"""
        db = card_db()
        raw = db.get("CS2_029")
        self.assertIsNotNone(raw, "卡库缺火球术 CS2_029")
        snap = _snap(
            turn=4, current=1,
            me=_me(mana=10, deck=22,
                   hand=[_card(name=raw.name, cost=raw.cost, text=raw.text)]),
            opp=_opp(health=6),
        )
        check = compute_lethal(snap, friendly_player_id=1)
        self.assertTrue(check.lethal)
        self.assertEqual(check.available_damage, 6)


# =====================================================================
# 2. 完整牌局模拟（脚本化快照 → 真实 AdviceDispatcher）
# =====================================================================


class ScriptedGameSimulationTest(unittest.TestCase):
    """一场法师镜像：开局→铺场→不确定→背包DP→冲锋武器斩杀→超时降级。

    每回合经真实 AdviceDispatcher（latest-wins worker 线程）发布；断言各功能
    在连续对局里的真实行为。期望值独立可算。
    """

    def test_complete_scripted_game(self):
        responses = {5: _UNCERTAIN, 9: _LETHAL_PLAY}
        client = _ScriptedLLM(responses, fail_turn=11)

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)
            recorded: dict[int, object] = {}   # turn -> 产出的 Advice
            processed: list[int] = []          # 已处理回合（经 handler 缝观测）
            drawn: list[tuple[int, int, float]] = []  # (turn, deck, one_copy 概率)
            trigger = TurnTrigger(friendly_player_id=1)

            def handler(job):
                advice = trigger.generate_and_publish(
                    job.snapshot, job.turn, job.fallback, client, publish_dir
                )
                recorded[job.turn] = advice
                processed.append(job.turn)

            harness = _DispatcherHarness(handler)
            harness.start()
            try:
                def play(snap, mode):
                    """提交一回合到调度器、等处理完、发布 game_state 并记录抽牌概率。"""
                    trigger.coach_mode = mode
                    harness.d.submit(AdviceJob(
                        snapshot=snap, turn=snap.turn, fallback=trigger.last_advice))
                    self.assertTrue(
                        harness.wait_idle(),
                        f"worker 未在超时内处理 turn {snap.turn}",
                    )
                    publish_game_state(publish_dir, snap, friendly_player_id=1)
                    st = json.loads(
                        (publish_dir / GAME_STATE_FILENAME).read_text(encoding="utf-8"))
                    odds = (st["players"]["1"].get("draw_odds") or {})
                    drawn.append((snap.turn, snap.players[1].deck_count,
                                  odds.get("one_copy_next_draw")))

                # --- T1 友方开局：空场，牌库 26 ---
                play(_snap(1, 1,
                           _me(deck=26, hand=[_card(name="小鱼人", cost=1,
                                                    attack=1, health=1)]),
                           _opp(deck=26)), "teach")

                # --- T2 对手回合（不经调度器）：友方不能动作 → 斩杀必为 0 ---
                t2 = _snap(2, 2,
                           _me(board=[_card(name="雪人", attack=5, health=5)]),
                           _opp(health=1))
                self.assertEqual(compute_lethal(t2, 1).available_damage, 0)

                # --- T3 友方铺场：场 3/3，对手 30 血（场攻+deficit）---
                t3 = _snap(3, 1,
                           _me(deck=24, board=[_card(name="水人", attack=3, health=3)]),
                           _opp(deck=24))
                play(t3, "teach")
                c3 = compute_lethal(t3, 1)
                self.assertEqual((c3.available_damage, c3.lethal, c3.deficit),
                                 (3, False, 27))

                # --- T5 不确定回合：LLM 返回 alternatives（多候选解析）---
                play(_snap(5, 1,
                           _me(deck=22, board=[_card(name="水人", attack=3, health=3)]),
                           _opp(deck=22)), "teach")
                alts = recorded[5].alternatives
                self.assertEqual(len(alts), 2)
                self.assertTrue(all(set(a) >= {"headline", "why"} for a in alts))

                # --- T7 背包DP回合（竞赛模式）：法力4 → 6（DP 胜贪心）---
                t7 = _snap(7, 1,
                           _me(mana=4, deck=20, hand=[
                               _card(name="高费大火球", cost=3, text="造成 5 点伤害"),
                               _card(name="低费小伤1", cost=2, text="造成 3 点伤害"),
                               _card(name="低费小伤2", cost=2, text="造成 3 点伤害"),
                           ]), _opp(deck=20))
                play(t7, "compete")
                self.assertEqual(compute_lethal(t7, 1).available_damage, 6)

                # --- T9 斩杀回合（竞赛模式）：冲锋武器+随从+法术 = 17 ---
                t9 = _snap(9, 1,
                           _me(mana=9, deck=18, board=[
                               _card(name="雪人", attack=4, health=4),
                               _card(name="武器", attack=4, health=None),
                           ], hand=[
                               _card(name="火球术", cost=4, text=FIREBALL_TEXT),
                               _card(name="冲锋怪", cost=5, attack=3, health=3,
                                     flags=["冲锋"]),
                           ]), _opp(health=14, deck=18))
                play(t9, "compete")
                self.assertTrue(recorded[9].lethal)              # advice 标注斩杀
                self.assertEqual(compute_lethal(t9, 1).available_damage, 17)

                # --- T11 超时降级（静默模式）：LLM 抛错 → 用 T9 建议兜底 ---
                play(_snap(11, 1,
                           _me(deck=16, hand=[_card(name="小鱼人", cost=1,
                                                    attack=1, health=1)]),
                           _opp(deck=16)), "silent")
                self.assertTrue(recorded[11].degraded)
                self.assertEqual(recorded[11].headline, recorded[9].headline)

                # ===== 贯穿断言 =====
                # 调度器：6 个友方回合全部处理，latest-wins 在串行提交下无丢失
                self.assertEqual(sorted(processed), [1, 3, 5, 7, 9, 11])

                # 每回合都发了 advice.json；最终文件 = T11（降级仍发布）
                advice_path = publish_dir / ADVICE_FILENAME
                self.assertTrue(advice_path.exists())
                final = json.loads(advice_path.read_text(encoding="utf-8"))
                self.assertEqual(final["turn"], 11)
                self.assertTrue(final["advice"]["degraded"])

                # 原子写：无残留临时文件
                self.assertEqual(list(publish_dir.glob(".advice_*.tmp")), [])
                self.assertEqual(list(publish_dir.glob(".state_*.tmp")), [])

                # 抽牌概率：友方 draw_odds == 1/N（超几何 K=1,n=1 闭式解），
                # 且随牌库收缩严格递增
                for turn, deck, p in drawn:
                    self.assertIsNotNone(p, f"turn {turn} 缺 draw_odds")
                    self.assertAlmostEqual(p, 1 / deck, places=6,
                                           msg=f"turn {turn} deck {deck} 非 1/N")
                probs = [p for _, _, p in drawn]
                self.assertEqual(probs, sorted(probs), "抽牌概率非随牌库收缩递增")
                self.assertEqual(len(set(probs)), len(probs), "概率应严格递增（无重复）")

                # 教练模式切换：三种模式的特征词出现在对应回合的 system prompt
                self._assert_coach_modes(client, {3: "教学", 7: "竞赛", 11: "静默"})
            finally:
                harness.shutdown()

    @staticmethod
    def _assert_coach_modes(client, expected):
        """每个指定回合的 system prompt 应含对应教练模式特征词。"""
        for turn, marker in expected.items():
            ok = any(t == turn and marker in s for (t, s, _u) in client.calls)
            if not ok:
                raise AssertionError(
                    f"turn {turn} 的 system prompt 未含 {marker!r}（教练模式未切换）"
                )


# =====================================================================
# 3. 真实 Power.log fixture 端到端
# =====================================================================


class RealFixtureFullGameTest(unittest.TestCase):
    """真实 fixture（15 回合，friendly=1，7 个友方回合）跑完整链路。"""

    def test_full_game_through_dispatcher(self):
        client = _ScriptedLLM({})  # 全默认 play 响应
        lines = read_fixture_lines()
        detector = IncrementalTurnDetector(friendly_player_id=1)
        trigger = TurnTrigger(friendly_player_id=1)
        processed: list[int] = []

        with tempfile.TemporaryDirectory() as td:
            publish_dir = Path(td)

            def handler(job):
                trigger.generate_and_publish(
                    job.snapshot, job.turn, job.fallback, client, publish_dir)
                processed.append(job.turn)

            harness = _DispatcherHarness(handler)
            harness.start()
            try:
                # 增量喂入 → 友方回合号（fixture 语义：双数回合玩家1当前）
                turns: list[int] = []
                for i in range(0, len(lines), 200):
                    turns.extend(detector.feed(lines[i:i + 200]))
                self.assertEqual(turns, [2, 4, 6, 8, 10, 12, 14])

                last_snap = None
                for turn in turns:
                    window = detector.get_trigger_window(turn)
                    game = parse_power_log(window).games[-1]
                    snap = serialize_game(game, friendly_player_id=1, db=None)
                    # compute_lethal 在真实快照上不崩，返回合法 int
                    check = compute_lethal(snap, friendly_player_id=1)
                    self.assertIsInstance(check.available_damage, int)
                    self.assertGreaterEqual(check.available_damage, 0)
                    trigger.coach_mode = "teach"
                    harness.d.submit(AdviceJob(
                        snapshot=snap, turn=turn, fallback=trigger.last_advice))
                    self.assertTrue(
                        harness.wait_idle(),
                        f"worker 未在超时内处理真实 fixture turn {turn}",
                    )
                    last_snap = snap

                # 调度器无丢失：每个友方回合都处理了
                self.assertEqual(processed, turns)
                # 最终 advice.json 存在
                self.assertTrue((publish_dir / ADVICE_FILENAME).exists())

                # game_state.json：D9（对手手牌只见数量）+ 友方 draw_odds
                self.assertIsNotNone(last_snap)
                publish_game_state(publish_dir, last_snap, friendly_player_id=1)
                st = json.loads(
                    (publish_dir / GAME_STATE_FILENAME).read_text(encoding="utf-8"))
                for pid, pv in st["players"].items():
                    if int(pid) == 1:
                        self.assertIsInstance(pv["hand"], list)  # 友方手牌是明细
                        if pv.get("deck_count", 0) > 0:
                            odds = pv["draw_odds"]
                            self.assertGreater(odds["one_copy_next_draw"], 0)
                            self.assertGreater(odds["two_copy_next_draw"],
                                               odds["one_copy_next_draw"])
                    else:
                        self.assertIsInstance(pv["hand"], dict)  # 对手只见数量
                        self.assertEqual(set(pv["hand"]), {"count"})
            finally:
                harness.shutdown()


if __name__ == "__main__":
    unittest.main()
