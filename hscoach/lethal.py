"""T-L1 斩杀/伤害计算器（代码级精确，补 LLM 算术短板）。

竞品差距：HDT/网易盒子都有"本回合场攻/斩杀"提示，本品原缺。LLM
对"7+4 是否斩杀"这类算术不可靠（已知缺陷），教练必须 100% 准确。

设计：纯函数，只用 GameSnapshot 己方合法可见信息，不模拟、不猜测。
- 场攻：己方场上随从 attack 求和（排除 已尽/冻结/无法攻击/0 攻）
- 手牌直接伤害：只识别 text 中明确"造成 N 点伤害"的法术，N 用正则
  提取；受法力预算约束（贪心：按单位法力伤害降序填预算，近似最优）
- lethal = available_damage >= opponent(health + armor)

保守原则：只算"确定的直接打脸伤害"，不计连击/触发/buff 等需要模拟
的效果——这些交给 LLM 在 prompt 里定性分析。宁可漏报（LLM 补），
绝不误报（谎报斩杀比漏报致命得多）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 复用 state 的 CardView 类型（lethal 计算器与序列化层共享卡牌视图）
from hscoach.state import CardView, GameSnapshot

# 本回合不能攻击的 flags（与 state._FLAG_TAGS 对应的中文 label）
_NON_ATTACKING_FLAGS = frozenset({"已尽", "冻结", "无法攻击", "休眠"})

# 手牌伤害法术识别：clean_text 后文本形如"造成 6 点伤害。"
# 匹配"造成 N 点伤害"（N 为阿拉伯数字），用于直接伤害法术。
_DAMAGE_SPELL_RE = re.compile(r"造成\s*(\d+)\s*点伤害")


@dataclass
class LethalCheck:
    """一次斩杀检测的结果。

    available_damage: 本回合可对对手英雄造成的确定直接伤害总和。
    lethal: available_damage 是否 >= 对手(血+甲)。
    detail: 伤害来源列表 [{name, damage, source}]，供注入 prompt / UI。
    deficit: 非 lethal 时，距离斩杀还差多少伤害（>=0）。
    """

    available_damage: int = 0
    lethal: bool = False
    detail: list[dict] = field(default_factory=list)
    deficit: int = 0

    def summary(self) -> str:
        """一句可读结论（注入 LLM prompt 与 advice 用）。

        lethal 时强调"本回合可斩杀"并给伤害明细；非 lethal 时告知
        场攻与差额——让 LLM 不必自己算术，聚焦定性决策。
        """
        if self.available_damage == 0:
            return "本回合无确定直接伤害（场攻 0）。"
        if self.lethal:
            sources = "、".join(
                f"{d['name']}({d['damage']})" for d in self.detail
            )
            return f"⚠ 本回合可斩杀：确定直接伤害共 {self.available_damage}（{sources}）。"
        sources = "、".join(
            f"{d['name']}({d['damage']})" for d in self.detail
        )
        return (
            f"本回合确定直接伤害 {self.available_damage}"
            f"（{sources}），距斩杀还差 {self.deficit}。"
        )


def _board_damage(board: list[CardView]) -> int:
    """场攻求和：排除不能攻击的随从。"""
    total = 0
    for c in board:
        if c.flags and any(f in _NON_ATTACKING_FLAGS for f in c.flags):
            continue
        atk = c.attack or 0
        if atk > 0:
            total += atk
    return total


def _board_detail(board: list[CardView]) -> list[dict]:
    """场攻来源明细。"""
    detail = []
    for c in board:
        if c.flags and any(f in _NON_ATTACKING_FLAGS for f in c.flags):
            continue
        atk = c.attack or 0
        if atk > 0:
            detail.append({"name": c.name or "随从", "damage": atk, "source": "board"})
    return detail


def _extract_spell_damage(text: str) -> int | None:
    """从法术文本提取直接伤害值。无匹配返回 None（非直接伤害法术）。"""
    if not text:
        return None
    m = _DAMAGE_SPELL_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _hand_spell_damage(
    hand: list[CardView], mana_budget: int
) -> tuple[int, list[dict]]:
    """手牌中直接伤害法术的贪心选取（受法力预算约束）。

    贪心策略：按"单位法力伤害"降序选，尽可能榨干法力——对纯直接伤害
    法术这是 0-1 背包的近似最优（误差限于单张卡的费用分摊）。
    保守：只认 text 明确"造成 N 点伤害"的牌；带条件（"如果…则造成"）
    的也认，因为提取的 N 是其标称伤害，是否触发由 LLM 定性。
    """
    candidates = []
    for c in hand:
        if c.cost is None:
            continue
        dmg = _extract_spell_damage(c.text)
        if dmg is None or dmg <= 0:
            continue
        if c.cost <= 0:
            # 0 费伤害法术（罕见但存在）—— 效率无穷，优先选
            candidates.append((float("inf"), c.cost, dmg, c.name or "法术"))
        else:
            candidates.append((dmg / c.cost, c.cost, dmg, c.name or "法术"))

    # 按单位法力伤害降序；效率相同时优先绝对伤害大的（接近背包最优）
    candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)

    total_damage = 0
    spent = 0
    detail: list[dict] = []
    for _eff, cost, dmg, name in candidates:
        if spent + cost <= mana_budget:
            spent += cost
            total_damage += dmg
            detail.append({"name": name, "damage": dmg, "source": "spell"})
    return total_damage, detail


def compute_lethal(
    snapshot: GameSnapshot,
    friendly_player_id: int = 1,
) -> LethalCheck:
    """计算本回合友方对对手的确定直接伤害与斩杀判定。

    Args:
        snapshot: GameSnapshot（己方手牌为列表、对手手牌隐藏）
        friendly_player_id: 友方玩家 id

    Returns:
        LethalCheck。对手回合或无场面无伤害牌时 available_damage=0。
    """
    # 只有友方回合才算（对手回合友方不能攻击/出牌）
    if snapshot.current_player_id != friendly_player_id:
        return LethalCheck()

    friendly = snapshot.players.get(friendly_player_id)
    opponent_id = next(
        (pid for pid in snapshot.players if pid != friendly_player_id), None
    )
    if friendly is None or opponent_id is None:
        return LethalCheck()
    opponent = snapshot.players[opponent_id]

    # 场攻（随从可直接打脸）
    board_dmg = _board_damage(friendly.board)
    detail = _board_detail(friendly.board)

    # 手牌伤害法术（受法力预算约束）。法力预算 = 友方当前法力
    mana_budget = friendly.mana or 0
    hand = friendly.hand if isinstance(friendly.hand, list) else []
    spell_dmg, spell_detail = _hand_spell_damage(hand, mana_budget)
    detail.extend(spell_detail)

    available = board_dmg + spell_dmg

    # 斩杀判定：确定直接伤害 >= 对手(血+甲)
    opp_hp = (opponent.health or 0) + (opponent.armor or 0)
    lethal = available >= opp_hp and available > 0
    deficit = max(0, opp_hp - available)

    return LethalCheck(
        available_damage=available,
        lethal=lethal,
        detail=detail,
        deficit=deficit,
    )
