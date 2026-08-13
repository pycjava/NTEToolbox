"""T-L1 斩杀/伤害计算器（代码级精确，补 LLM 算术短板）。

竞品差距：HDT/网易盒子都有"本回合场攻/斩杀"提示，本品原缺。LLM
对"7+4 是否斩杀"这类算术不可靠（已知缺陷），教练必须 100% 准确。

设计：纯函数，只用 GameSnapshot 己方合法可见信息，不模拟、不猜测。
- 攻击伤害：己方场上随从/英雄/武器实体的 attack（排除 已尽/冻结/
  无法攻击/休眠/0 攻）
- 手牌直接伤害：只识别文本明确"造成 N 点伤害"的法术（N 用正则提取）
  与冲锋随从；受法力预算约束（0-1 背包 DP 精确最优）
- 嘲讽阻挡模型（T-L4）：对手有嘲讽随从时，攻击伤害必须先清光嘲讽
  ——每次攻击最多打一个嘲讽、过量伤害浪费，用子集和 DP 求"花费最小
  伤害"的清场方案，剩余攻击才打脸；法术永远可以打脸（嘲讽挡不住）。
- lethal = available_damage >= opponent(health + armor)

保守原则：只算"确定的直接打脸伤害"，不计连击/触发/buff 等需要模拟
的效果——这些交给 LLM 在 prompt 里定性分析。宁可漏报（LLM 补），
绝不误报（谎报斩杀比漏报致命得多）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

# 复用 state 的 CardView 类型（lethal 计算器与序列化层共享卡牌视图）
from hscoach.state import CardView, GameSnapshot

# 本回合不能攻击的 flags（与 state._FLAG_TAGS 对应的中文 label）
_NON_ATTACKING_FLAGS = frozenset({"已尽", "冻结", "无法攻击", "休眠"})

# 可作为攻击伤害来源的实体类型。武器实体排除：武器装备后英雄实体
# ATK 已含武器攻击，两者都算会把武器攻击翻倍（误报斩杀）。
# 空串兼容测试构造的无类型卡。
_ATTACK_ENTITY_TYPES = frozenset({"MINION", "HERO", ""})

# 场上随从位上限（冲锋随从打出后占位；7 位满则打不出）
BOARD_SLOTS = 7

# 手牌伤害法术识别：clean_text 后文本形如"造成 6 点伤害。"
# 匹配"造成 N 点伤害"（N 为阿拉伯数字），用于直接伤害法术。
_DAMAGE_SPELL_RE = re.compile(r"造成\s*(\d+)\s*点伤害")
# 只对随从的目标描述（不能打脸）；"角色"/"敌人"/无目标对象都可打脸。
_MINION_ONLY_RE = re.compile(r"对(一个|所有|每个|全部)(敌方)?随从")
_RANDOM_RE = re.compile(r"随机")


def _spell_face_damage(text: str) -> int | None:
    """从法术文本提取"确定可打脸"的伤害值。保守原则：宁可漏报。

    排除（不确定能否打脸）：
    - 含"随机"（目标/分配不确定）
    - 只对随从的目标描述（"对一个随从/对所有(敌方)随从..."）
    保留："对一个角色"、"对所有敌人"、无目标对象（"造成 N 点伤害"）。
    """
    if not text:
        return None
    if _RANDOM_RE.search(text):
        return None
    m = _DAMAGE_SPELL_RE.search(text)
    if not m:
        return None
    dmg = int(m.group(1))
    if dmg <= 0:
        return None
    if _MINION_ONLY_RE.search(text):
        return None
    return dmg


@dataclass
class LethalCheck:
    """一次斩杀检测的结果。

    available_damage: 本回合可对对手英雄造成的确定打脸伤害总和。
    lethal: available_damage 是否 >= 对手(血+甲)。
    detail: 打脸伤害来源列表 [{name, damage, source}]，供注入 prompt / UI。
    deficit: 非 lethal 时，距离斩杀还差多少伤害（>=0）。
    taunt_blocked: 对手嘲讽未被清光，随从/英雄攻击无法打脸。
    taunt_cost: 清嘲讽花费的伤害（未花在打脸上）。
    """

    available_damage: int = 0
    lethal: bool = False
    detail: list[dict] = field(default_factory=list)
    deficit: int = 0
    taunt_blocked: bool = False
    taunt_cost: int = 0
    opponent_fatigue_damage: int | None = None  # 对手牌库空时其下回合疲劳伤害

    def summary(self) -> str:
        """一句可读结论（注入 LLM prompt 与 advice 用）。

        lethal 时强调"本回合可斩杀"并给伤害明细；非 lethal 时告知
        打脸伤害与差额——让 LLM 不必自己算术，聚焦定性决策。
        """
        if self.available_damage == 0:
            if self.taunt_blocked:
                return "本回合无确定打脸伤害（对手嘲讽阻挡，且无可用法术伤害）。"
            return "本回合无确定直接伤害（场攻 0）。"
        if self.lethal:
            sources = "、".join(
                f"{d['name']}({d['damage']})" for d in self.detail
            )
            text = f"⚠ 本回合可斩杀：确定直接伤害共 {self.available_damage}（{sources}）。"
        else:
            sources = "、".join(
                f"{d['name']}({d['damage']})" for d in self.detail
            )
            text = (
                f"本回合确定直接伤害 {self.available_damage}"
                f"（{sources}），距斩杀还差 {self.deficit}。"
            )
        if self.taunt_blocked:
            text += "注意：对手嘲讽未清光，随从/英雄攻击无法打脸（以上仅法术伤害）。"
        elif self.taunt_cost > 0:
            text += f"（其中清除嘲讽花费 {self.taunt_cost} 点伤害）"
        if self.opponent_fatigue_damage:
            text += f"对手牌库已空：其下回合抽牌将受 {self.opponent_fatigue_damage} 点疲劳伤害。"
        return text


def _is_charge_minion(c: CardView) -> bool:
    """手牌中冲锋随从：本回合打出即可攻击英雄（突袭不能打脸，不计）。

    无法攻击的随从（如被 buff 压制）也不能打脸。
    """
    if c.flags and any(f in _NON_ATTACKING_FLAGS for f in c.flags):
        return False
    return bool(c.flags and "冲锋" in c.flags and (c.attack or 0) > 0)


def _collect_hand_damage_candidates(
    hand: list[CardView],
) -> list[HandCandidate]:
    """收集手牌中受法力约束的"可打出直接伤害"候选。

    两类：
    - 直接伤害法术（text 含"造成 N 点伤害"）
    - 冲锋随从（flags 含"冲锋"，attack 即伤害）
    突袭随从不计（本回合只能打随从，不能打脸）。
    """
    candidates: list[HandCandidate] = []
    for c in hand:
        cost = c.cost if c.cost is not None and c.cost > 0 else 0
        # 随从的战吼/亡语文本不算确定打脸（只检查冲锋），非随从（法术等）
        # 才提取伤害文本。无类型信息的卡（测试构造）按文本识别，兼容旧契约。
        if c.card_type != "MINION":
            spell_dmg = _spell_face_damage(c.text)
            if spell_dmg is not None and spell_dmg > 0:
                candidates.append(
                    HandCandidate(cost, spell_dmg, c.name or "法术", "spell", False)
                )
                continue  # 同一张卡不重复计（法术不会同时是冲锋随从）
        # 冲锋随从（风怒冲锋可攻击两次，但仍只占一次费用）
        if _is_charge_minion(c):
            windfury = bool(c.flags and "风怒" in c.flags)
            candidates.append(
                HandCandidate(cost, c.attack or 0, c.name or "冲锋随从", "charge", windfury)
            )
    return candidates


def _candidate_detail(c: HandCandidate) -> dict:
    """把候选转成 detail 字典（compute_lethal 构造攻击/法术条目时消费）。"""
    return {"name": c.name, "damage": c.damage, "source": c.source, "windfury": c.windfury}


def _knapsack_pick(
    candidates: list[HandCandidate], mana_budget: int
) -> tuple[int, list[dict]]:
    """0-1 背包：在法力预算内选伤害总和最大的候选子集（DP 精确最优）。

    修复 Spec 审查 #4：原贪心按 dmg/cost 降序，可被背包反例击穿。
    DP 状态：dp[m] = 花费恰为 m 时能获得的最大伤害及物品列表。
    cost 上界 = mana_budget（炉石法力通常 <=10，DP 规模极小）。
    """
    if not candidates or mana_budget <= 0:
        # mana_budget==0 时仍可选 0 费候选
        if mana_budget == 0:
            zero = [c for c in candidates if c.cost == 0]
            return sum(c.damage for c in zero), [_candidate_detail(c) for c in zero]
        return 0, []

    # 标准 0-1 背包：dp[j] = 考虑前 i 件、费用<=j 的最大伤害；prev 回溯选择
    # 费用超过预算的物品直接跳过；0 费物品特殊处理（必选，不占预算）
    zero_cost = [c for c in candidates if c.cost == 0]
    items = [c for c in candidates if 0 < c.cost <= mana_budget]

    W = mana_budget
    # dp[j] = (max_damage, chosen_list)
    dp: list[tuple[int, list[HandCandidate]]] = [(0, [])] * (W + 1)
    for c in items:
        # 逆序更新（0-1 背包标准）
        new_dp = list(dp)
        for j in range(W, c.cost - 1, -1):
            prev_dmg, prev_chosen = dp[j - c.cost]
            cand_dmg = prev_dmg + c.damage
            if cand_dmg > dp[j][0]:
                new_dp[j] = (cand_dmg, prev_chosen + [c])
        dp = new_dp

    best_dmg, best_chosen = max(dp, key=lambda x: x[0])
    # 加上 0 费候选（必选）
    total = best_dmg + sum(c.damage for c in zero_cost)
    detail = [_candidate_detail(c) for c in best_chosen]
    detail.extend(_candidate_detail(c) for c in zero_cost)
    return total, detail


# 攻击/法术伤害条目：(damage, name, source)，source ∈ board/charge/spell
_Entry = tuple[int, str, str]


def _board_minion_count(board: list[CardView]) -> int:
    """场上随从数（占位统计：英雄/武器/英雄技能等实体不占随从位）。

    无类型信息的卡（测试构造）按"有血量即随从"推断。
    """
    count = 0
    for c in board:
        if c.card_type == "MINION":
            count += 1
        elif not c.card_type and c.health is not None:
            count += 1
    return count


class HandCandidate(NamedTuple):
    """手牌中受法力约束的可打出伤害候选（法术/冲锋随从）。"""

    cost: int
    damage: int
    name: str
    source: str  # spell / charge
    windfury: bool  # 冲锋随从风怒 → 可攻击两次（费用只付一次）


def _min_clear_subset(
    entries: list[_Entry], required_sum: int, required_count: int
) -> tuple[int, tuple[int, ...]] | None:
    """子集和 DP：选一个条目子集，sum >= required_sum 且条目数 >=
    required_count，使 sum 最小（= 清嘲讽花费的最小伤害）。

    条目数约束来自"每次攻击最多打一个嘲讽"（含圣盾时 slice D 会
    再叠加）。返回 (最小花费, 选中条目下标)；不可行返回 None。
    """
    n = len(entries)
    if n == 0 or required_count > n:
        return None
    # 最小可行花费不可能超过 required_sum + 最大条目伤害（去掉任一条目
    # 后就不满足 sum 约束），用它做 DP 上界，规模极小。
    max_need = required_sum + max(d for d, _, _ in entries)
    # dp[k][s] = 花费 s 伤害、用了 k 个条目的一个方案（下标元组），None 不可达
    dp: list[list[tuple[int, ...] | None]] = [
        [None] * (max_need + 1) for _ in range(n + 1)
    ]
    dp[0][0] = ()
    for idx, (dmg, _name, _src) in enumerate(entries):
        for k in range(n - 1, -1, -1):
            row = dp[k]
            for s in range(max_need - dmg, -1, -1):
                prev = row[s]
                if prev is None or idx in prev:
                    continue
                slot = dp[k + 1][s + dmg]
                if slot is None:
                    dp[k + 1][s + dmg] = prev + (idx,)
    # 找满足约束的最小花费
    for s in range(required_sum, max_need + 1):
        for k in range(required_count, n + 1):
            v = dp[k][s]
            if v is not None:
                return s, v
    return None


def _resolve_face(
    attack_entries: list[_Entry],
    spell_entries: list[_Entry],
    taunts: list[CardView],
) -> tuple[int, int, bool, list[dict]]:
    """嘲讽阻挡模型：返回 (打脸伤害, 清嘲讽花费, 攻击是否被阻挡, 打脸明细)。

    - 无嘲讽：攻击 + 法术全部打脸。
    - 有嘲讽：两个策略取优——
      1. 不清嘲讽：法术全部打脸（指定英雄的法术不受嘲讽阻挡），
         攻击全被挡。
      2. 清嘲讽：选"花费最小伤害"的子集（攻击/法术都可用来清，
         每次攻击最多打一个嘲讽），剩余伤害全部打脸。
    """
    all_entries = attack_entries + spell_entries
    total = sum(d for d, _, _ in all_entries)
    if not taunts:
        return total, 0, False, [
            {"name": n, "damage": d, "source": s} for d, n, s in all_entries
        ]
    spell_total = sum(d for d, _, _ in spell_entries)
    spell_detail = [
        {"name": n, "damage": d, "source": s} for d, n, s in spell_entries
    ]
    taunt_hp = sum((t.health or 0) for t in taunts)
    # 免疫嘲讽无法被伤害清除（免疫目标不可被伤害/指定）→ 攻击永远被挡，
    # 打脸法术不受嘲讽阻挡，照常打脸。
    if any(t.flags and "免疫" in t.flags for t in taunts):
        return spell_total, 0, True, spell_detail
    # 圣盾：每层护盾吸收一次攻击 → 清除需 taunt 数 + 圣盾数 次攻击、
    # 总伤害 >= 嘲讽总血量 + 圣盾数（每层盾至少吸收 1 点）。
    ds_count = sum(1 for t in taunts if t.flags and "圣盾" in t.flags)
    cleared = _min_clear_subset(
        all_entries, taunt_hp + ds_count, len(taunts) + ds_count
    )
    if cleared is None:
        return spell_total, 0, True, spell_detail
    clear_sum, used = cleared
    clear_face = total - clear_sum
    # 法术全打脸比清嘲讽更优（或持平）时，不征用法术去清嘲讽
    if spell_total > clear_face:
        return spell_total, 0, True, spell_detail
    used_set = set(used)
    face_detail = [
        {"name": n, "damage": d, "source": s}
        for i, (d, n, s) in enumerate(all_entries)
        if i not in used_set
    ]
    return clear_face, clear_sum, False, face_detail


def compute_lethal(
    snapshot: GameSnapshot,
    friendly_player_id: int = 1,
) -> LethalCheck:
    """计算本回合友方对对手的确定打脸伤害与斩杀判定。

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

    # 攻击伤害（随从 + 英雄实体：英雄攻击也走嘲讽阻挡模型）
    # 风怒可攻击两次 → 两个攻击条目（各自独立打脸或清嘲讽）
    attack_entries: list[_Entry] = []
    for c in friendly.board:
        if c.card_type not in _ATTACK_ENTITY_TYPES:
            continue  # 武器/附魔/英雄技能实体不单独计攻击
        if c.flags and any(f in _NON_ATTACKING_FLAGS for f in c.flags):
            continue
        atk = c.attack or 0
        if atk > 0:
            attack_entries.append((atk, c.name or "随从", "board"))
            if c.flags and "风怒" in c.flags:
                attack_entries.append((atk, c.name or "随从", "board"))

    # 手牌伤害（法术 + 冲锋随从，受法力预算约束，DP 求最优）
    # 随从位约束：冲锋随从打出后占位，空位不足时只能打出一部分（取伤害大的）
    mana_budget = friendly.mana or 0
    hand = friendly.hand if isinstance(friendly.hand, list) else []
    candidates = _collect_hand_damage_candidates(hand)
    slots = BOARD_SLOTS - _board_minion_count(friendly.board)
    if slots <= 0:
        candidates = [c for c in candidates if c[3] != "charge"]
    else:
        charge_cands = sorted(
            (c for c in candidates if c[3] == "charge"), key=lambda c: -c[1]
        )
        candidates = [c for c in candidates if c[3] != "charge"] + charge_cands[:slots]
    _, hand_detail = _knapsack_pick(candidates, mana_budget)
    spell_entries: list[_Entry] = []
    for d in hand_detail:
        entry: _Entry = (d["damage"], d["name"], d["source"])
        if d["source"] == "charge":
            attack_entries.append(entry)  # 冲锋随从是攻击伤害，受嘲讽阻挡
            if d.get("windfury"):
                attack_entries.append(entry)  # 风怒冲锋可攻击两次
        else:
            spell_entries.append(entry)

    # 对手嘲讽阻挡
    taunts = [t for t in opponent.board if t.flags and "嘲讽" in t.flags]
    face, clear_cost, blocked, face_detail = _resolve_face(
        attack_entries, spell_entries, taunts
    )

    opp_hp = (opponent.health or 0) + (opponent.armor or 0)
    lethal = face >= opp_hp and face > 0
    deficit = max(0, opp_hp - face)

    # 疲劳提示：对手牌库空 → 其下回合抽牌受 fatigue+1 点疲劳伤害
    fatigue_damage = None
    if (opponent.deck_count or 0) <= 0:
        fatigue_damage = (opponent.fatigue or 0) + 1

    return LethalCheck(
        available_damage=face,
        lethal=lethal,
        detail=face_detail,
        deficit=deficit,
        taunt_blocked=blocked,
        taunt_cost=clear_cost,
        opponent_fatigue_damage=fatigue_damage,
    )
