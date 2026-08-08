"""炉石教练模块入口。

一期 MVP 的形态：读取 Power.log → 解析 → 序列化 → LLM 建议 → 置顶窗显示。
独立于异环 agent 进程运行，依赖隔离。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path

from hscoach.cards import CardDatabase
from hscoach.coach import DeepSeekClient
from hscoach.log_config import ensure_log_config, power_log_path, tail_power_log
from hscoach.log_parser import parse_power_log, parse_power_log_file
from hscoach.overlay import OverlayApp
from hscoach.state import serialize_game
from hscoach.trigger import (
    IncrementalTurnDetector,
    TurnTrigger,
    publish_advice,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="炉石 AI 教练")
    parser.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""),
                        help="LLM API key（默认读 DEEPSEEK_API_KEY 环境变量）")
    parser.add_argument("--model", default="deepseek-chat", help="模型名")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1", help="API 地址")
    parser.add_argument("--publish-dir", default=None, help="advice.json 发布目录")
    parser.add_argument("--friendly-player-id", type=int, default=1,
                        help="友方玩家 id（1=先手，2=后手；默认 1，日志会自动校准）")
    parser.add_argument("--no-overlay", action="store_true", help="不启动 UI，只输出建议到终端")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.api_key:
        print("错误：未提供 API key。用 --api-key 或设置 DEEPSEEK_API_KEY 环境变量。", file=sys.stderr)
        return 2

    # 1. 确保 log.config 已开启
    status = ensure_log_config()
    logger.info("log.config: %s — %s", status.action, status.message)

    # 2. 构建卡牌库
    db = CardDatabase()
    logger.info("构建卡牌库（首次会从 HearthstoneJSON 下载，约 1-2 分钟）...")
    db.build()
    logger.info("卡牌库就绪：%d 张卡", len(db))

    # 3. LLM 客户端
    client = DeepSeekClient(api_key=args.api_key, model=args.model, base_url=args.base_url)

    # 4. 发布目录
    publish_dir = Path(args.publish_dir) if args.publish_dir else Path(tempfile.gettempdir()) / "hs-coach"
    publish_dir.mkdir(parents=True, exist_ok=True)
    logger.info("建议发布到：%s", publish_dir / "advice.json")

    power_log = power_log_path()
    trigger = TurnTrigger(friendly_player_id=args.friendly_player_id)
    detector = IncrementalTurnDetector(friendly_player_id=args.friendly_player_id)

    # 5. 后台线程：增量 tail → 正则检测回合 → 全量解析 → LLM（优化 2+3）
    stop_event = threading.Event()

    def log_worker():
        logger.info("开始监听 %s（打开炉石打一局即开始）...", power_log)
        batch: list[str] = []
        for line in tail_power_log(poll_interval=0.3):
            if stop_event.is_set():
                break
            batch.append(line)
            # CREATE_GAME 边界：重置检测器（新对局）
            if "CREATE_GAME" in line:
                detector.reset()
            # 每攒一批（或遇到回合结束标记）检测一次
            if len(batch) >= 50 or "TAG_CHANGE" in line:
                triggered = detector.feed(batch)
                batch.clear()
                if triggered:
                    # 检测到"轮到友方新回合" → 全量解析 → LLM（回合开始即触发）
                    try:
                        result = parse_power_log(detector.get_all_lines())
                        if result.games:
                            game = result.games[-1]
                            advice = trigger.check_and_trigger(
                                game, db, client, publish_dir
                            )
                            if advice is not None:
                                logger.info(
                                    "回合建议已发布（T%d）：%s",
                                    trigger.last_triggered_turn,
                                    advice.headline,
                                )
                    except Exception as e:  # noqa: BLE001
                        logger.warning("处理日志出错：%s", e)

    worker = threading.Thread(target=log_worker, daemon=True)
    worker.start()

    # 6. 前台：启动 overlay（或终端模式）
    if args.no_overlay:
        print("终端模式：监听中，按 Ctrl+C 退出。建议发布在", publish_dir)
        try:
            while not stop_event.is_set():
                stop_event.wait(1.0)
        except KeyboardInterrupt:
            stop_event.set()
    else:
        advice_path = publish_dir / "advice.json"

        def on_manual():
            if power_log.exists():
                try:
                    result = parse_power_log_file(power_log)
                    if result.games:
                        game = result.games[-1]
                        advice = trigger.manual_trigger(game, db, client, publish_dir)
                        logger.info("手动建议：%s", advice.headline)
                except Exception as e:  # noqa: BLE001
                    logger.warning("手动触发出错：%s", e)

        app = OverlayApp(advice_path, on_manual_trigger=on_manual)
        try:
            app.run()
        finally:
            stop_event.set()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

