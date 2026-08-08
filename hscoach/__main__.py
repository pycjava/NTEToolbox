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
from hscoach.state import detect_friendly_player_id
from hscoach.trigger import (
    IncrementalTurnDetector,
    TurnTrigger,
)

logger = logging.getLogger(__name__)


def calibrate_friendly_player(result) -> int | None:
    """从一次解析结果推断友方玩家 id（日志自动校准，D9 防线）。

    依次尝试：
    1. hslog 官方的 FriendlyPlayerExporter：首个手牌 SHOW_ENTITY 必属
       友方（客户端只揭示本地玩家的手牌）。
    2. 手牌 CardID 启发式（detect_friendly_player_id）：手牌含 CardID
       的玩家即友方。
    推断不出来（开局调度阶段双方手牌都空）返回 None，沿用现有值。
    """
    if result.packet_trees:
        try:
            from hslog.export import FriendlyPlayerExporter

            pid = FriendlyPlayerExporter(result.packet_trees[-1]).export()
            if pid is not None:
                return int(pid)
        except Exception as e:  # 推断失败不致命，回退启发式
            logger.debug("FriendlyPlayerExporter 推断失败：%s", e)
    if result.games:
        return detect_friendly_player_id(result.games[-1])
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="炉石 AI 教练")
    parser.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""),
                        help="LLM API key（默认读 DEEPSEEK_API_KEY 环境变量）")
    parser.add_argument("--model", default="deepseek-chat", help="模型名")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1", help="API 地址")
    parser.add_argument("--publish-dir", default=None, help="advice.json 发布目录")
    parser.add_argument("--friendly-player-id", type=int, default=None,
                        help="友方玩家 id（1/2）。默认不传：日志自动校准（推荐）。"
                             "若传错会被自动纠正并警告（D9 合规防线）")
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
    # friendly id 未知时先用占位 1，第一次解析后自动校准（D9 防线：
    # 校准前若映射错误，serialize_game 的 D9 断言会拒绝输出并告警）
    friendly_player_id = args.friendly_player_id or 1
    trigger = TurnTrigger(friendly_player_id=friendly_player_id)
    detector = IncrementalTurnDetector(friendly_player_id=friendly_player_id)

    # 5. 后台线程：增量 tail → 正则检测回合 → 全量解析 → 校准 → LLM（优化 2+3）
    stop_event = threading.Event()

    def apply_calibration(result) -> None:
        """日志自动校准友方玩家 id；校准结果与当前值冲突时纠正并告警。"""
        calibrated = calibrate_friendly_player(result)
        if calibrated is None:
            return
        if calibrated != trigger.friendly_player_id:
            if args.friendly_player_id is not None:
                logger.warning(
                    "自动校准：友方玩家 id 应为 %d（当前 %d，已自动纠正）。"
                    "若你手动传过 --friendly-player-id 请核对。",
                    calibrated, trigger.friendly_player_id,
                )
            else:
                logger.info("自动校准：友方玩家 id = %d", calibrated)
            trigger.friendly_player_id = calibrated
            detector.friendly_player_id = calibrated

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
            # 每攒一批（或遇到 TAG_CHANGE）检测一次
            if len(batch) >= 50 or "TAG_CHANGE" in line:
                triggered_turns = detector.feed(batch)
                batch.clear()
                for turn in triggered_turns:
                    # 检测到"轮到友方新回合" → 按触发点截取行流全量解析
                    # → 校准 → LLM（回合开始即触发，快照正好在回合起点）
                    try:
                        result = parse_power_log(detector.get_trigger_window(turn))
                        apply_calibration(result)
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
                    except Exception as e:  # 处理日志出错不致命
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
            # 每次重新解析路径（国服重启后路径会变）
            current_log = power_log_path()
            if current_log.exists():
                try:
                    result = parse_power_log_file(current_log)
                    apply_calibration(result)
                    if result.games:
                        game = result.games[-1]
                        advice = trigger.manual_trigger(game, db, client, publish_dir)
                        logger.info("手动建议：%s", advice.headline)
                except Exception as e:  # 手动触发出错不致命
                    logger.warning("手动触发出错：%s", e)

        def on_restore_log_config() -> str:
            from hscoach.log_config import restore_log_config

            status = restore_log_config()
            logger.info("log.config 还原：%s — %s", status.action, status.message)
            return status.message

        app = OverlayApp(
            advice_path,
            on_manual_trigger=on_manual,
            on_restore_log_config=on_restore_log_config,
        )
        try:
            app.run()
        finally:
            stop_event.set()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

