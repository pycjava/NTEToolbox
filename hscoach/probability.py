"""T-D1 抽牌概率（超几何分布）。

竞品差距：HDT 标配"下回合抽到 X 的概率"，本品原缺。纯组合数学，
补 LLM 无法精确计算的随机性分析。

超几何分布 H(N, K, n)：
- N = 牌库剩余总数
- K = 目标牌在牌库中的剩余张数
- n = 抽牌次数
- P(恰好 k 张) = C(K,k)·C(N-K, n-k) / C(N, n)
- P(至少 1 张) = 1 - P(恰好 0 张) = 1 - C(N-K, n) / C(N, n)

实现用 math.comb（Python 3.8+），无外部依赖。边界：
- K=0 或 n=0 → 0（无目标牌或不去抽）
- N=0 → 0（空牌库）
- n >= N 且 K>0 → 1（抽穿牌库，目标牌必出）
- k > K 或 k > n → P(exact k) = 0
"""

from __future__ import annotations

import math
from functools import lru_cache


@lru_cache(maxsize=1024)
def _comb(n: int, k: int) -> int:
    """C(n, k)，带缓存。n<k 或 n<0 返回 0。"""
    if n < 0 or k < 0 or k > n:
        return 0
    return math.comb(n, k)


def draw_exact(deck_size: int, copies: int, draws: int, k: int) -> float:
    """P(在 draws 次抽牌中恰好抽到 k 张目标牌)。

    超几何分布 PMF：C(K,k)·C(N-K, n-k) / C(N, n)。
    """
    N, K, n = deck_size, copies, draws
    if N <= 0 or K <= 0 or n <= 0:
        return 0.0 if k > 0 else 1.0
    # 抽牌次数超牌库 → 视为抽穿（n=N）
    n = min(n, N)
    if k < 0 or k > K or k > n:
        return 0.0
    denom = _comb(N, n)
    if denom == 0:
        return 0.0
    num = _comb(K, k) * _comb(N - K, n - k)
    return num / denom


def draw_at_least_one(deck_size: int, copies: int, draws: int) -> float:
    """P(在 draws 次抽牌中至少抽到 1 张目标牌)。

    = 1 - C(N-K, n) / C(N, n)
    """
    N, K, n = deck_size, copies, draws
    if N <= 0 or K <= 0 or n <= 0:
        return 0.0
    n = min(n, N)
    # 目标牌张数 >= 牌库（全是目标）→ 必中
    if K >= N:
        return 1.0
    # 抽牌次数 >= 牌库减目标牌数 + 1 → 必中（抽到只剩目标牌外的牌不够抽）
    # 简化：n > N - K 时必中（非目标牌不够抽，必然抽到目标）
    if n > N - K:
        return 1.0
    denom = _comb(N, n)
    if denom == 0:
        return 0.0
    p_zero = _comb(N - K, n) / denom
    return 1.0 - p_zero


def draw_probability_summary(
    deck_size: int, copies: int, draws: int = 1
) -> str:
    """可读的抽牌概率结论（注入 prompt / overlay 用）。

    形如："下回合抽到概率 6.7%（牌库 30 张含 2 张目标）"。
    """
    if deck_size <= 0 or copies <= 0 or draws <= 0:
        return f"抽到概率 0%（牌库 {deck_size} 张含 {copies} 张目标）"
    p = draw_at_least_one(deck_size, copies, draws)
    pct = p * 100
    turn_word = "下回合" if draws == 1 else f"未来 {draws} 回合"
    return (
        f"{turn_word}抽到概率 {pct:.1f}%"
        f"（牌库 {deck_size} 张含 {copies} 张目标）"
    )
