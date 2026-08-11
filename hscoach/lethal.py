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


def _board_eval(board: list[CardView]) -> tuple[int, list[dict]]:
    """场攻求和 + 来源明细（单次遍历，合并原 _board_damage/_board_detail）。

    排除不能攻击的随从（已尽/冻结/无法攻击/休眠）。武器作为 board 实体
    时其 attack 也计入（英雄可挥砍打脸）——武器有"已尽"flag 会被排除。
    返回 (总场攻, 明细列表)。
    """
    total = 0
    detail: list[dict] = []
    for c in board:
        if c.flags and any(f in _NON_ATTACKING_FLAGS for f in c.flags):
            continue
        atk = c.attack or 0
        if atk > 0:
            total += atk
            detail.append({"name": c.name or "随从", "damage": atk, "source": "board"})
    return total, detail


def _extract_spell_damage(text: str) -> int | None:
    """从法术文本提取直接伤害值。无匹配返回 None（非直接伤害法术）。"""
    if not text:
        return None
    m = _DAMAGE_SPELL_RE.search(text)
    if m:
        return int(m.group(1))
    return None


def _is_charge_minion(c: CardView) -> bool:
    """手牌中冲锋随从：本回合打出即可攻击英雄（突袭不能打脸，不计）。"""
    return bool(c.flags and "冲锋" in c.flags and (c.attack or 0) > 0)


def _collect_hand_damage_candidates(
    hand: list[CardView],
) -> list[tuple[int, int, str, str]]:
    """收集手牌中受法力约束的"可打出直接伤害"候选。

    两类：
    - 直接伤害法术（text 含"造成 N 点伤害"）
    - 冲锋随从（flags 含"冲锋"，attack 即伤害）
    突袭随从不计（本回合只能打随从，不能打脸）。
    返回 [(cost, damage, name, source), ...]，cost<=0 的按 0 处理。
    """
    candidates: list[tuple[int, int, str, str]] = []
    for c in hand:
        cost = c.cost if c.cost is not None and c.cost > 0 else 0
        # 直接伤害法术
        spell_dmg = _extract_spell_damage(c.text)
        if spell_dmg is not None and spell_dmg > 0:
            candidates.append((cost, spell_dmg, c.name or "法术", "spell"))
            continue  # 同一张卡不重复计（法术不会同时是冲锋随从）
        # 冲锋随从
        if _is_charge_minion(c):
            candidates.append((cost, c.attack or 0, c.name or "冲锋随从", "charge"))
    return candidates


def _knapsack_pick(
    candidates: list[tuple[int, int, str, str]], mana_budget: int
) -> tuple[int, list[dict]]:
    """0-1 背包：在法力预算内选伤害总和最大的候选子集（DP 精确最优）。

    修复 Spec 审查 #4：原贪心按 dmg/cost 降序，可被背包反例击穿。
    DP 状态：dp[m] = 花费恰为 m 时能获得的最大伤害及物品列表。
    cost 上界 = mana_budget（炉石法力通常 <=10，DP 规模极小）。
    """
    if not candidates or mana_budget <= 0:
        # mana_budget==0 时仍可选 0 费候选
        if mana_budget == 0:
            total = 0
            detail: list[dict] = []
            for cost, dmg, name, src in candidates:
                if cost == 0:
                    total += dmg
                    detail.append({"name": name, "damage": dmg, "source": src})
            return total, detail
        return 0, []

    # 标准 0-1 背包：dp[j] = 考虑前 i 件、费用<=j 的最大伤害；prev 回溯选择
    # 费用超过预算的物品直接跳过；0 费物品特殊处理（必选，不占预算）
    zero_cost: list[tuple[int, str, str]] = []  # (dmg, name, source)
    items: list[tuple[int, int, str, str]] = []  # (cost, dmg, name, source) cost>0
    for cost, dmg, name, src in candidates:
        if cost == 0:
            zero_cost.append((dmg, name, src))
        elif cost <= mana_budget:
            items.append((cost, dmg, name, src))

    W = mana_budget
    # dp[j] = (max_damage, chosen_list)
    dp: list[tuple[int, list[tuple[int, int, str, str]]]] = [(0, [])] * (W + 1)
    for cost, dmg, name, src in items:
        # 逆序更新（0-1 背包标准）
        new_dp = list(dp)
        for j in range(W, cost - 1, -1):
            prev_dmg, prev_chosen = dp[j - cost]
            cand_dmg = prev_dmg + dmg
            if cand_dmg > dp[j][0]:
                new_dp[j] = (cand_dmg, prev_chosen + [(cost, dmg, name, src)])
        dp = new_dp

    best_dmg, best_chosen = max(dp, key=lambda x: x[0])
    # 加上 0 费候选（必选）
    total = best_dmg + sum(d for d, _, _ in zero_cost)
    detail = [{"name": n, "damage": d, "source": s} for _, d, n, s in best_chosen]
    detail.extend({"name": n, "damage": d, "source": s} for d, n, s in zero_cost)
    return total, detail


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

    # 场攻（随从 + 已装备武器可直接打脸）
    board_dmg, detail = _board_eval(friendly.board)

    # 手牌伤害（法术 + 冲锋随从，受法力预算约束，DP 求最优）
    mana_budget = friendly.mana or 0
    hand = friendly.hand if isinstance(friendly.hand, list) else []
    candidates = _collect_hand_damage_candidates(hand)
    hand_dmg, hand_detail = _knapsack_pick(candidates, mana_budget)
    detail.extend(hand_detail)

    available = board_dmg + hand_dmg

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
