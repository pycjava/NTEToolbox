"""T-H1 对局结果与战绩统计（竞品对齐：HDT/盒子的对局记录/胜率统计）。

游戏结束时 Power.log 在 GameEntity 上写 tag=PLAYSTATE value=4/5/6
（WON/LOST/TIED，本地玩家视角）。检测到终局结果后：
- history.jsonl：追加一行对局记录（结果/双方职业/回合数/时间）
- stats.json：聚合战绩（总场/胜负平/胜率/按职业/最近 N 局），原子写

前端盒子消费 stats.json 显示战绩；history.jsonl 留作后续复盘扩展。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

HISTORY_FILENAME = "history.jsonl"
STATS_FILENAME = "stats.json"
RECENT_LIMIT = 10

# 终局 PLAYSTATE：4=WON、5=LOST、6=TIED（本地玩家视角，写在 GameEntity 上）
RESULT_MAP: dict[int, str] = {4: "win", 5: "loss", 6: "tie"}

_PLAYSTATE_RE = re.compile(r"Entity=GameEntity\s+tag=PLAYSTATE\s+value=(\d+)")


class GameResultDetector:
    """从原始日志行检测对局终局结果（正则，极快，无需 hslog 解析）。

    只认 GameEntity 上的 PLAYSTATE 4/5/6；每局只触发一次（重复写
    PLAYSTATE 不会重复记录）；CREATE_GAME 或手动 reset() 开启下一局。
    """

    def __init__(self) -> None:
        self._fired = False

    def feed(self, lines: list[str]) -> list[str]:
        """喂入原始日志行，返回本次检测到的终局结果列表（win/loss/tie）。"""
        results: list[str] = []
        for line in lines:
            if "CREATE_GAME" in line:
                self._fired = False  # 新对局
                continue
            if self._fired:
                continue
            m = _PLAYSTATE_RE.search(line)
            if m and int(m.group(1)) in RESULT_MAP:
                self._fired = True
                results.append(RESULT_MAP[int(m.group(1))])
        return results

    def reset(self) -> None:
        self._fired = False


def _atomic_write_json(path: Path, payload: dict) -> None:
    """原子写 JSON（tmp + os.replace，读者永不看到半写状态）。"""
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".stats_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _aggregate(history_path: Path) -> dict:
    """从 history.jsonl 聚合战绩。文件缺失/损坏时返回空战绩。"""
    stats: dict = {
        "total": 0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "winrate_pct": 0.0,
        "by_class": {},
        "recent": [],
    }
    if not history_path.exists():
        return stats
    try:
        entries = [
            json.loads(line)
            for line in history_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError):
        return stats  # 损坏的历史不致命，从头开始
    for e in entries:
        stats["total"] += 1
        result = e.get("result")
        if result == "win":
            stats["wins"] += 1
        elif result == "loss":
            stats["losses"] += 1
        else:
            stats["ties"] += 1
        cls = e.get("friendly_class") or "未知"
        bucket = stats["by_class"].setdefault(cls, {"wins": 0, "losses": 0})
        if result == "win":
            bucket["wins"] += 1
        elif result == "loss":
            bucket["losses"] += 1
    stats["recent"] = entries[-RECENT_LIMIT:]
    if stats["total"]:
        stats["winrate_pct"] = round(stats["wins"] / stats["total"] * 100, 1)
    return stats


def record_result(
    publish_dir: Path,
    result: str,
    friendly_class: str,
    opponent_class: str,
    turns: int,
) -> dict:
    """记录一局结果：追加 history.jsonl + 重写 stats.json。

    Returns:
        聚合后的战绩 dict（前端可直接消费）。
    """
    publish_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "result": result,
        "friendly_class": friendly_class or "未知",
        "opponent_class": opponent_class or "未知",
        "turns": turns,
    }
    history_path = publish_dir / HISTORY_FILENAME
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    stats = _aggregate(history_path)
    _atomic_write_json(publish_dir / STATS_FILENAME, stats)
    return stats
