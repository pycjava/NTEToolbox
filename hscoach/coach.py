"""T6(06) LLM 教练：局面 → 出牌建议。

把序列化后的合法局面（含注入的卡牌效果）喂给国内云端 LLM，
解析出"单一最优解"建议。护栏代码化（超时熔断、重试、非法建议拒发）。

建议数据契约（advice schema，参考 barnabys coach_publish.py）：
    {
      "kind": "play" | "trade" | "pass" | "uncertain",
      "headline": "一句话主推荐",
      "why": "1-2 句理由",
      "steps": ["步骤1", "步骤2"],  # 可空
      "warning": "注意事项或风险",   # 可空
    }

合规：D9 已在序列化层保证只喂合法信息；此处不再处理隐藏信息。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Protocol

import httpx

from hscoach.state import GameSnapshot

if TYPE_CHECKING:
    from hscoach.lethal import LethalCheck

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_TIMEOUT = 120.0  # 推理模型（如 deepseek-v4-flash）需要较长时间
DEFAULT_MAX_RETRIES = 2

# 建议 kind 的合法取值（唯一词典，overlay 图标等均以此为准）
KINDS = ("play", "trade", "pass", "uncertain")


class AdviceParseError(ValueError):
    """LLM 输出无法解析为合法建议（格式错误，重试/降级处理）。"""


@dataclass
class Advice:
    """一条出牌建议。"""

    kind: str = "uncertain"  # play / trade / pass / uncertain
    headline: str = ""
    why: str = ""
    steps: list[str] = field(default_factory=list)
    warning: str = ""
    # 多候选（LLM 独有）：uncertain 场景给 2-3 个合理打法 + 各自权衡。
    # 竞品都只给 1 个解；本品让玩家自己判断，是"教练"而非"指挥"。
    alternatives: list[dict] = field(default_factory=list)
    # 元数据（不喂 LLM，用于延迟观测）
    latency_ms: int = 0
    degraded: bool = False  # True=降级（超时/失败用了兜底）
    lethal: bool = False  # True=本回合代码判定可斩杀（UI 可高亮）

    def to_dict(self) -> dict:
        """序列化契约（advice.json 与 overlay 消费的字段）。"""
        return asdict(self)


class LLMClient(Protocol):
    """LLM 调用的抽象接口（便于测试 mock）。"""

    def chat(self, system: str, user: str, timeout: float | None = None) -> str: ...


@dataclass
class DeepSeekClient:
    """DeepSeek（兼容 OpenAI 格式）的 LLM 客户端。

    可通过改 base_url/model 复用为 GLM/Qwen 等国内云端。
    """

    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL

    def chat(self, system: str, user: str, timeout: float | None = None) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        to = timeout or DEFAULT_TIMEOUT
        with httpx.Client(timeout=to) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            # 兼容推理模型：content 为空时回退到 reasoning_content
            content = msg.get("content") or ""
            if not content:
                content = msg.get("reasoning_content") or ""
            return content


# 核心规则（所有模式共享，不可模式化覆盖——保证数据契约稳定）
_CORE_RULES = """规则：
1. 你只看到合法可见信息——不知道对手手牌或牌库的具体内容，请勿猜测。
2. 给出"单一最优解"：一个明确的主推荐动作 + 1-2 句理由。
3. 如果没有明显最优解（两种打法都合理），kind 设为 "uncertain"，headline 说明两种都行。
4. 必须严格按 JSON 格式输出，字段：kind, headline, why, steps, warning,
   以及可选的 alternatives（仅 uncertain 时建议提供）。
   kind 取值：play（出牌/施法）、trade（交换/解场）、pass（结束回合）、uncertain（无定论）。
   alternatives 格式：[{\"headline\": \"另一打法\", \"why\": \"为何也可行/为何次优\"}]。
5. 你的建议会显示给玩家参考，由玩家自己操作——你不是在替他打牌。
6. 卡牌效果文本已随局面提供，请以提供的效果为准，不要凭记忆。
7. 只输出最终 JSON，不要在 JSON 前后加任何解释文字。
8. 【斩杀判定】局面里会附一行"伤害评估"，是代码精确计算的本回合确定直接伤害。
   - 标"可斩杀"时：除非有更强赢法，否则推荐执行斩杀，kind 用 "play"。
   - 你不要自行做加法算术（容易算错），直接采信"伤害评估"的数字。
9. 【场面优先】若场面劣势大（对手铺场/有威胁随从），即使有斩杀数字也评估是否需先解场。
"""

# 教练模式（LLM 独有：传统 tracker 无法切换信息密度）
# 每个模式追加在核心规则之后，只改"风格/详细度"，不改数据契约。
COACH_MODES: dict[str, str] = {
    "teach": (
        "【教学模式】面向学习：why 要讲清原理与权衡，steps 写明顺序与"
        "理由。当 kind=uncertain（两种打法都合理）时，务必在 alternatives "
        "里给出每个候选的 headline 与 why，让玩家理解权衡。鼓励新手理解。"
        "alternatives 字段格式：[{\"headline\": \"...\", \"why\": \"...\"}]。"
    ),
    "compete": (
        "【竞赛模式】面向天梯快速决策：headline 一句话给动作，why 控制在"
        "一句，steps 只列必要步骤，warning 只写致命风险。简洁、可执行、少字。"
    ),
    "silent": (
        "【静默模式】克制发声：只在斩杀、致命误判、关键抉择时给建议；"
        "常规回合若无明显问题，kind 用 pass 且 headline 极简。减少对玩家的干扰。"
    ),
}

DEFAULT_COACH_MODE = "teach"


def get_system_prompt(mode: str | None = None) -> str:
    """按教练模式拼接 system prompt。

    未知模式回退 teach（安全默认）。核心规则始终在前（数据契约稳定），
    模式风格追加在后（只改表达密度）。
    """
    m = mode if mode in COACH_MODES else DEFAULT_COACH_MODE
    return (
        "你是一名炉石传说构筑模式的出牌教练。根据给定的对局局面，"
        "给出这一回合最优的出牌建议。\n\n"
        + _CORE_RULES
        + "\n"
        + COACH_MODES[m]
    )


# 向后兼容：SYSTEM_PROMPT 为默认模式（teach）的别名，既有调用/测试不受影响
SYSTEM_PROMPT = get_system_prompt(DEFAULT_COACH_MODE)


def _player_view(players: dict, pid) -> dict:
    """从 players dict 取一个玩家视图，兼容 int/str key。"""
    return players.get(pid) or players.get(str(pid)) or players.get(int(pid)) or {}


def _format_board(cards: list) -> list[str]:
    """格式化一方场面的文本行（攻/血/受伤/关键词）。"""
    if not cards:
        return ["  （空场）"]
    lines = []
    for c in cards:
        atk = f"{c['attack']}/{c['health']}"
        if c.get("damaged"):
            atk += f"(受伤{c['damaged']})"
        flags = f" [{', '.join(c['flags'])}]" if c.get("flags") else ""
        lines.append(f"  - {c['name']} {atk}{flags}".rstrip())
    return lines


def build_user_prompt(
    snapshot: GameSnapshot,
    friendly_player_id: int,
    lethal: "LethalCheck | None" = None,
) -> str:
    """把快照转成给 LLM 的 user prompt（结构化局面文本）。

    Args:
        snapshot: 合法可见快照
        friendly_player_id: 友方玩家 id
        lethal: 可选的斩杀检测结果。若提供，注入一行"伤害评估"到 prompt
            末尾——代码精确计算的本回合确定直接伤害，让 LLM 不必算术。
    """
    d = snapshot.to_dict()
    players = d["players"]
    friendly = _player_view(players, friendly_player_id)
    opponent_id = next((int(pid) for pid in players if int(pid) != friendly_player_id), None)
    opponent = _player_view(players, opponent_id) if opponent_id is not None else {}

    lines = [
        f"=== 当前回合 {snapshot.turn}，轮到玩家 {friendly_player_id} 出牌 ===",
        "",
        "【我方】",
        f"英雄：{friendly.get('health', '?')} 血 {friendly.get('armor', 0)} 护甲 | "
        f"法力 {friendly.get('mana', 0)}/{friendly.get('max_mana', 10)}",
        f"手牌（{len(friendly.get('hand', []))}张）：",
    ]
    for c in friendly.get("hand", []):
        atk = f"{c['attack']}/{c['health']}" if c.get("attack") is not None else ""
        flags = f" [{', '.join(c['flags'])}]" if c.get("flags") else ""
        lines.append(f"  - {c['name']}（{c.get('cost', '?')}费）{atk}{flags} {c.get('text', '')}".rstrip())

    lines.append("场面：")
    lines += _format_board(friendly.get("board", []))

    lines += [
        f"牌库剩余：{friendly.get('deck_count', 0)} 张",
        "",
        "【对手】",
        f"英雄：{opponent.get('health', '?')} 血 {opponent.get('armor', 0)} 护甲",
        f"手牌：{opponent.get('hand', {}).get('count', '?')} 张（隐藏，不知具体）",
        "场面：",
    ]
    lines += _format_board(opponent.get("board", []))

    lines += [
        f"对手牌库剩余：{opponent.get('deck_count', 0)} 张",
        "",
    ]
    # 抽牌概率参考：牌库剩余 N 张时下回合抽到关键牌的概率（补 HDT 核心价值）
    friendly_deck = friendly.get('deck_count', 0) or 0
    if friendly_deck > 0:
        from hscoach.probability import draw_odds_table

        odds = draw_odds_table(friendly_deck)
        lines += [
            f"【抽牌概率】牌库 {friendly_deck} 张——下回合抽到特定单张"
            f"{odds['one_copy_next_draw']*100:.0f}%、两张之一"
            f"{odds['two_copy_next_draw']*100:.0f}%。",
            "",
        ]
    # 伤害评估：代码精确计算的斩杀判定（补 LLM 算术短板）
    if lethal is not None:
        lines += [
            f"【伤害评估】{lethal.summary()}",
            "",
        ]
    lines.append("请给出这一回合的最优出牌建议（JSON 格式）。")
    return "\n".join(lines)


def _parse_advice(raw: str) -> Advice:
    """从 LLM 原始输出解析出 Advice。

    Raises:
        AdviceParseError: 输出里没有 JSON 对象、JSON 非法、或不是对象
            （list/字符串等）。由 get_advice 统一走重试/降级（T6：非法建议
            拒发，不把垃圾当建议发布）。
    """
    # 尝试提取 JSON（LLM 可能在 JSON 前后加解释文字）
    text = raw.strip()
    # 找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise AdviceParseError("输出中未找到 JSON 对象")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise AdviceParseError(f"JSON 解析失败: {e}") from e
    if not isinstance(data, dict):
        # 例如 LLM 返回了 ["play", ...] 或一段纯文本——不是建议对象
        raise AdviceParseError(f"JSON 不是对象，而是 {type(data).__name__}")

    kind = data.get("kind", "uncertain")
    if kind not in KINDS:
        kind = "uncertain"
    # steps 可能是列表或字符串（LLM 有时不按格式返回字符串）
    raw_steps = data.get("steps", [])
    if isinstance(raw_steps, str):
        steps = [raw_steps] if raw_steps.strip() else []
    else:
        steps = [str(s) for s in raw_steps]

    # 多候选（alternatives）：LLM 在 uncertain 场景可给 2-3 个合理打法。
    # 容错：非列表或元素非对象时降级为空，绝不崩解析。
    alternatives: list[dict] = []
    raw_alts = data.get("alternatives", [])
    if isinstance(raw_alts, list):
        for item in raw_alts:
            if isinstance(item, dict):
                alternatives.append({
                    "headline": str(item.get("headline", "")),
                    "why": str(item.get("why", "")),
                })

    return Advice(
        kind=kind,
        headline=str(data.get("headline", "")),
        why=str(data.get("why", "")),
        steps=steps,
        warning=str(data.get("warning", "")),
        alternatives=alternatives,
    )


def get_advice(
    snapshot: GameSnapshot,
    client: LLMClient,
    friendly_player_id: int,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    fallback: Advice | None = None,
    inject_lethal: bool = True,
    coach_mode: str | None = None,
) -> Advice:
    """获取一回合的出牌建议。含超时熔断、重试、降级。

    Args:
        snapshot: 合法可见快照
        client: LLM 客户端（测试时可 mock）
        friendly_player_id: 友方玩家 id
        timeout: 单次调用超时（秒）
        max_retries: 失败重试次数
        fallback: 全部失败时的降级建议（None 则用默认兜底）
        inject_lethal: 是否注入代码精确计算的斩杀判定到 prompt（默认开，
            补 LLM 算术短板）。测试纯 prompt 构造时可关。
        coach_mode: 教练模式（teach/compete/silent），None 用默认 teach。
            LLM 独有：切换信息密度，传统 tracker 做不到。

    Returns:
        Advice（含 latency_ms 和 degraded 标记）
    """
    # 代码级斩杀判定：精确算术，补 LLM 短板
    lethal = None
    if inject_lethal:
        try:
            from hscoach.lethal import compute_lethal

            lethal = compute_lethal(snapshot, friendly_player_id)
        except Exception as e:  # 斩杀计算失败不阻断建议生成
            logger.debug("斩杀计算失败（非致命）：%s", e)
            lethal = None

    user_prompt = build_user_prompt(snapshot, friendly_player_id, lethal=lethal)
    system_prompt = get_system_prompt(coach_mode)
    start = time.monotonic()

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            raw = client.chat(system_prompt, user_prompt, timeout=timeout)
            advice = _parse_advice(raw)
            advice.latency_ms = int((time.monotonic() - start) * 1000)
            # 斩杀局面：在 advice 上标注，UI 可高亮"斩杀"标记
            if lethal is not None and lethal.lethal:
                advice.lethal = True
            return advice
        except Exception as e:  # 网络错误与格式错误都算一次失败，可重试
            last_err = e
            logger.warning("LLM 调用失败（第 %d 次）：%s", attempt + 1, e)
            continue

    # 全部失败 → 降级（优先用上一回合建议，其次诚实占位）
    advice = fallback or Advice(
        kind="uncertain",
        headline="（教练暂时无法响应）",
        why=f"连续 {max_retries + 1} 次调用失败：{last_err}",
        warning="请稍后重试，或手动判断局面",
    )
    advice.latency_ms = int((time.monotonic() - start) * 1000)
    advice.degraded = True
    return advice
