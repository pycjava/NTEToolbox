"""T7(07) 回合触发器 + 建议发布。

从日志流检测"轮到友方玩家回合"事件，触发 LLM 教练生成建议，
以原子写 JSON 文件（advice.json）方式发布供 UI 消费。

触发检测：监听 TAG_CHANGE ... tag=TURN value=N（回合数递增）+
          CURRENT_PLAYER 指向友方玩家。简化实现：每当 TURN tag 递增
          且当前是友方回合，触发一次。

发布契约（advice.json，语言无关，三期 C# WPF 可零成本复用）：
    {
      "turn": 5,
      "timestamp": "2026-08-08T12:34:56",
      "advice": { ... Advice.to_dict() ... }
    }
原子写：先写临时文件再 os.replace，读者永不看到半写状态。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hearthstone.enums import GameTag
from hscoach.coach import Advice, LLMClient, get_advice
from hscoach.log_parser import parse_power_log
from hscoach.state import GameSnapshot, serialize_game
from hscoach.cards import CardDatabase

logger = logging.getLogger(__name__)

ADVICE_FILENAME = "advice.json"


@dataclass
class TurnTrigger:
    """检测回合变化并触发建议生成。

    用法：每次解析完一批新日志行后，调 check_and_trigger(result, ...)，
    若检测到"轮到友方的新回合"，则生成建议并发布。
    """

    friendly_player_id: int
    last_triggered_turn: int = 0

    def detect_new_friendly_turn(self, snapshot: GameSnapshot) -> int | None:
        """若 snapshot 是轮到友方的新回合（turn > 上次触发的），返回 turn 号；否则 None。"""
        if snapshot.current_player_id != self.friendly_player_id:
            return None
        if snapshot.turn <= self.last_triggered_turn:
            return None
        return snapshot.turn

    def check_and_trigger(
        self,
        game,
        db: CardDatabase | None,
        client: LLMClient,
        publish_dir: Path,
    ) -> Advice | None:
        """检查并可能触发：序列化 → 检测新回合 → 生成建议 → 发布。

        Returns: 若触发了建议返回 Advice，否则 None。
        """
        snapshot = serialize_game(game, self.friendly_player_id, db)
        new_turn = self.detect_new_friendly_turn(snapshot)
        if new_turn is None:
            return None

        self.last_triggered_turn = new_turn
        advice = get_advice(snapshot, client, self.friendly_player_id)
        publish_advice(publish_dir, advice, new_turn)
        return advice

    def manual_trigger(
        self,
        game,
        db: CardDatabase | None,
        client: LLMClient,
        publish_dir: Path,
    ) -> Advice:
        """手动触发"再想想"：不强求 turn 递增，基于当前局面生成。"""
        snapshot = serialize_game(game, self.friendly_player_id, db)
        advice = get_advice(snapshot, client, self.friendly_player_id)
        publish_advice(publish_dir, advice, snapshot.turn)
        return advice


def publish_advice(publish_dir: Path, advice: Advice, turn: int) -> Path:
    """原子写 advice.json 到 publish_dir。

    返回写入的文件路径。读者通过监听该文件刷新 UI。
    """
    publish_dir.mkdir(parents=True, exist_ok=True)
    target = publish_dir / ADVICE_FILENAME
    payload = {
        "turn": turn,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "advice": advice.to_dict(),
    }
    # 原子写：临时文件 + os.replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(publish_dir), prefix=".advice_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target)
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target


def read_advice(publish_dir: Path) -> dict | None:
    """读取已发布的 advice.json（UI 侧用）。不存在返回 None。"""
    target = publish_dir / ADVICE_FILENAME
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def process_log_lines_for_trigger(
    lines: list[str],
    trigger: TurnTrigger,
    db: CardDatabase | None,
    client: LLMClient,
    publish_dir: Path,
) -> list[Advice]:
    """处理一批日志行，检测并触发所有新回合建议。

    简化策略：用完整行流解析出最后的 game 状态，check_and_trigger 一次。
    （更精细的实现可按 BLOCK 边界增量检测，但一期按最终态即可。）
    """
    result = parse_power_log(lines)
    advices = []
    for game in result.games:
        advice = trigger.check_and_trigger(game, db, client, publish_dir)
        if advice is not None:
            advices.append(advice)
    return advices
