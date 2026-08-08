"""T6(06) LLM 教练测试。

验证（不依赖真实 LLM API，全用 mock 客户端）：
- prompt 构造：含局面信息、卡牌效果、对手手牌只见数量
- 输出解析：合法 JSON → Advice
- 解析容错：非 JSON / 缺字段 / 非对象 JSON → AdviceParseError，
  get_advice 走重试 + 降级（T6：非法建议拒发）
- 超时熔断：连续失败 → 降级建议（可用上一回合建议兜底）
- 延迟记录
"""

import logging
import unittest
from pathlib import Path

import httpx

logging.disable(logging.WARNING)

from hearthstone.enums import GameTag, Zone
from hscoach.coach import (
    KINDS,
    Advice,
    AdviceParseError,
    DeepSeekClient,
    _parse_advice,
    build_user_prompt,
    get_advice,
)
from hscoach.log_parser import parse_power_log
from hscoach.state import serialize_game
from tests._helpers import card_db, read_fixture_lines

FIXTURE = Path(__file__).resolve().parent / "data" / "friendly_player_id_is_1.power.log"


class MockLLMClient:
    """可控的 mock LLM 客户端。"""

    def __init__(self, response: str = "", raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_system = ""
        self.last_user = ""

    def chat(self, system: str, user: str, timeout: float | None = None) -> str:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        if self.raise_exc:
            raise self.raise_exc
        return self.response


class ParseAdviceTest(unittest.TestCase):
    def test_parses_valid_json(self):
        raw = '{"kind":"play","headline":"出火球术","why":"能斩杀","steps":["火球打脸"],"warning":""}'
        adv = _parse_advice(raw)
        self.assertEqual(adv.kind, "play")
        self.assertEqual(adv.headline, "出火球术")
        self.assertEqual(adv.steps, ["火球打脸"])

    def test_string_steps_not_split_into_chars(self):
        """LLM 返回字符串而非列表时，steps 不应被拆成单字。"""
        raw = '{"kind":"pass","headline":"结束回合","why":"无法出牌","steps":"直接点击结束回合。","warning":""}'
        adv = _parse_advice(raw)
        self.assertEqual(adv.steps, ["直接点击结束回合。"])
        self.assertNotEqual(adv.steps, list("直接点击结束回合。"))

    def test_empty_string_steps(self):
        raw = '{"kind":"play","headline":"x","why":"","steps":"","warning":""}'
        adv = _parse_advice(raw)
        self.assertEqual(adv.steps, [])

    def test_handles_json_wrapped_in_text(self):
        raw = '好的，分析如下：\n{"kind":"trade","headline":"交换","why":"解场","steps":[],"warning":""}\n以上。'
        adv = _parse_advice(raw)
        self.assertEqual(adv.kind, "trade")

    def test_unknown_kind_becomes_uncertain(self):
        raw = '{"kind":"hack","headline":"","why":""}'
        adv = _parse_advice(raw)
        self.assertEqual(adv.kind, "uncertain")

    def test_kinds_vocabulary_is_single_source(self):
        """kind 合法取值集中在 KINDS。"""
        self.assertEqual(KINDS, ("play", "trade", "pass", "uncertain"))

    def test_garbage_raises_advice_parse_error(self):
        with self.assertRaises(AdviceParseError):
            _parse_advice("这不是JSON")

    def test_malformed_json_raises_advice_parse_error(self):
        with self.assertRaises(AdviceParseError):
            _parse_advice('{"kind":"play","headline":broken}')

    def test_non_object_json_raises_advice_parse_error(self):
        """修复回归：json.loads 成功但不是对象（list/字符串/数字）时，
        旧实现 data.get 抛 AttributeError 被误当网络失败；现在明确抛
        AdviceParseError 走格式错误路径。"""
        for raw in ('["play", "trade"]', '"一段纯文本"', "42"):
            with self.assertRaises(AdviceParseError):
                _parse_advice(raw)


class BuildPromptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = parse_power_log(read_fixture_lines(4000))
        cls.game = result.games[0]
        cls.db = card_db()

    def test_prompt_contains_turn_and_mana(self):
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        prompt = build_user_prompt(snap, friendly_player_id=1)
        self.assertIn("回合", prompt)
        self.assertIn("法力", prompt)

    def test_prompt_marks_opponent_hand_hidden(self):
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        prompt = build_user_prompt(snap, friendly_player_id=1)
        self.assertIn("隐藏", prompt)
        self.assertIn("不知具体", prompt)

    def test_prompt_does_not_leak_opponent_cards(self):
        """D9：prompt 里对手手牌行只应有数量（隐藏，不知具体）。"""
        snap = serialize_game(self.game, friendly_player_id=1, db=self.db)
        prompt = build_user_prompt(snap, friendly_player_id=1)
        opponent_hand_lines = [
            ln for ln in prompt.splitlines()
            if ln.startswith("手牌：") and "隐藏" in ln
        ]
        # 对手手牌行形如 "手牌：N 张（隐藏，不知具体）"，只有数量
        self.assertEqual(len(opponent_hand_lines), 1)
        self.assertRegex(
            opponent_hand_lines[0],
            r"^手牌：\d+ 张（隐藏，不知具体）$",
        )


class GetAdviceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = parse_power_log(read_fixture_lines(4000))
        cls.game = result.games[0]
        cls.db = card_db()
        cls.snap = serialize_game(cls.game, friendly_player_id=1, db=cls.db)

    def test_successful_call_returns_advice(self):
        client = MockLLMClient(
            response='{"kind":"play","headline":"测试建议","why":"理由","steps":[],"warning":""}'
        )
        adv = get_advice(self.snap, client, friendly_player_id=1)
        self.assertEqual(adv.kind, "play")
        self.assertEqual(adv.headline, "测试建议")
        self.assertFalse(adv.degraded)
        self.assertGreaterEqual(adv.latency_ms, 0)
        self.assertEqual(client.calls, 1)

    def test_timeout_triggers_degraded_fallback(self):
        client = MockLLMClient(raise_exc=httpx.TimeoutException("超时"))
        adv = get_advice(self.snap, client, friendly_player_id=1, max_retries=1)
        self.assertTrue(adv.degraded)
        self.assertIn("无法响应", adv.headline)
        # 应重试 max_retries+1 次
        self.assertEqual(client.calls, 2)

    def test_custom_fallback_used_on_failure(self):
        client = MockLLMClient(raise_exc=httpx.HTTPError("网络错误"))
        custom = Advice(kind="pass", headline="保守打法", why="自定义降级")
        adv = get_advice(self.snap, client, friendly_player_id=1, fallback=custom, max_retries=0)
        self.assertTrue(adv.degraded)
        self.assertEqual(adv.headline, "保守打法")

    def test_retry_succeeds_on_second_attempt(self):
        responses = iter([
            httpx.TimeoutException("第一次超时"),
            '{"kind":"play","headline":"第二次成功","why":"","steps":[],"warning":""}',
        ])

        class RetryClient:
            def __init__(self):
                self.calls = 0

            def chat(self, system, user, timeout=None):
                self.calls += 1
                item = next(responses)
                if isinstance(item, Exception):
                    raise item
                return item

        client = RetryClient()
        adv = get_advice(self.snap, client, friendly_player_id=1, max_retries=2)
        self.assertEqual(adv.kind, "play")
        self.assertEqual(adv.headline, "第二次成功")
        self.assertFalse(adv.degraded)
        self.assertEqual(client.calls, 2)

    def test_non_object_json_degrades_with_retry(self):
        """LLM 返回非对象 JSON：应视为格式错误重试（T6），最终降级。"""
        client = MockLLMClient(response='["play", "trade"]')
        adv = get_advice(self.snap, client, friendly_player_id=1, max_retries=1)
        self.assertTrue(adv.degraded)
        self.assertEqual(client.calls, 2)  # 重试 max_retries+1 次
        self.assertIn("无法响应", adv.headline)

    def test_non_object_json_uses_custom_fallback(self):
        client = MockLLMClient(response='"纯文本"')
        custom = Advice(kind="pass", headline="上回合建议", why="兜底")
        adv = get_advice(self.snap, client, friendly_player_id=1, fallback=custom, max_retries=0)
        self.assertTrue(adv.degraded)
        self.assertEqual(adv.headline, "上回合建议")


class DeepSeekClientConfigTest(unittest.TestCase):
    def test_default_config(self):
        c = DeepSeekClient(api_key="sk-test")
        self.assertEqual(c.model, "deepseek-chat")
        self.assertIn("deepseek.com", c.base_url)

    def test_custom_model_for_glm(self):
        c = DeepSeekClient(api_key="x", model="glm-4", base_url="https://open.bigmodel.cn/api/paas/v4")
        self.assertEqual(c.model, "glm-4")


if __name__ == "__main__":
    unittest.main()
