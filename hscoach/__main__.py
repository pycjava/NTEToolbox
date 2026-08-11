"""炉石教练模块入口。

一期 MVP 的形态：读取 Power.log → 解析 → 序列化 → LLM 建议 → 置顶窗显示。
独立于异环 agent 进程运行，依赖隔离。
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

from hscoach.advice_worker import AdviceDispatcher, AdviceJob
from hscoach.cards import CardDatabase
from hscoach.coach import DeepSeekClient
from hscoach.config import effective_config, save_config
from hscoach.log_config import ensure_log_config, power_log_path, tail_power_log
from hscoach.log_parser import parse_power_log, parse_power_log_file
from hscoach.overlay import OverlayApp
from hscoach.single_instance import SingleInstanceLock
from hscoach.state import detect_friendly_player_id, serialize_game
from hscoach.trigger import (
    IncrementalTurnDetector,
    TurnTrigger,
    publish_game_state,
)

logger = logging.getLogger(__name__)


def _prompt_api_key(no_overlay: bool) -> str:
    """首次运行引导输入 API key。

    终端模式用 input()；overlay 模式用 tkinter 对话框（打包成品无终端
    也能完成首次配置）。返回空串表示用户取消。
    """
    hint = "请前往 LLM 平台（如 platform.deepseek.com）申请 API key"
    if no_overlay:
        print(f"未配置 LLM API key。{hint}。")
        return input("请输入 API key（直接回车取消）: ").strip()
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        try:
            key = simpledialog.askstring(
                "炉石教练 - 首次运行",
                f"未配置 LLM API key。\n\n{hint}。\n\n"
                "（也可在启动参数里用 --api-key 指定）",
                parent=root,
            )
        finally:
            root.destroy()
        return (key or "").strip()
    except Exception as e:  # 无显示环境等，非致命
        logger.debug("API key 对话框不可用：%s", e)
        return ""


class _ClientHolder:
    """可变 LLM 客户端容器。

    设置里改完 API key/模型/地址后热切换，无需重启；worker 线程每次
    chat 都经由当前持有的客户端，替换是引用赋值，线程安全。
    """

    def __init__(self, client):
        self.client = client

    def chat(self, system: str, user: str, timeout: float | None = None) -> str:
        return self.client.chat(system, user, timeout)


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
    parser.add_argument("--api-key", default=None,
                        help="LLM API key。默认按 环境变量 DEEPSEEK_API_KEY →"
                             " 配置文件 %%APPDATA%%\\NTEToolbox\\hscoach\\config.json"
                             " → 首次运行引导输入 的顺序解析")
    parser.add_argument("--model", default=None, help="模型名（默认读配置文件）")
    parser.add_argument("--base-url", default=None, help="API 地址（默认读配置文件）")
    parser.add_argument("--publish-dir", default=None, help="advice.json 发布目录")
    parser.add_argument("--friendly-player-id", type=int, default=None,
                        help="友方玩家 id（1/2）。默认不传：日志自动校准（推荐）。"
                             "若传错会被自动纠正并警告（D9 合规防线）")
    parser.add_argument("--no-overlay", action="store_true", help="不启动 UI，只输出建议到终端")
    parser.add_argument("--enable-log-config", action="store_true",
                        help="一次性：开启炉石 log.config 后退出（客户端按钮调用）")
    parser.add_argument("--restore-log-config", action="store_true",
                        help="一次性：还原炉石 log.config 后退出（客户端按钮调用）")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 一次性 log.config 操作（客户端按钮）：执行完即退出，不启动监听、不要求 API key
    if args.enable_log_config:
        status = ensure_log_config()
        logger.info("log.config 开启：%s — %s", status.action, status.message)
        print(status.message, flush=True)
        return 0
    if args.restore_log_config:
        from hscoach.log_config import restore_log_config

        status = restore_log_config()
        logger.info("log.config 还原：%s — %s", status.action, status.message)
        print(status.message, flush=True)
        return 0

    # 生效配置：命令行 > 环境变量 > 配置文件 > 默认值
    cfg = effective_config(
        cli_key=args.api_key,
        cli_model=args.model,
        cli_base_url=args.base_url,
        cli_friendly=args.friendly_player_id,
    )
    if not cfg.api_key:
        # 只有完全没给（未传 --api-key、无环境变量、无配置文件）才引导输入；
        # 显式传了空串视为"明确不配置"，直接报错退出（不弹窗，测试/脚本友好）
        if args.api_key is None:
            cfg.api_key = _prompt_api_key(no_overlay=args.no_overlay)
        if not cfg.api_key:
            print(
                "错误：未提供 API key。用 --api-key 或设置 DEEPSEEK_API_KEY "
                "环境变量。",
                file=sys.stderr,
            )
            return 2
    # 记住本次配置（API key / 模型 / 地址），下次启动免输入
    try:
        save_config(cfg)
    except OSError as e:
        logger.warning("配置保存失败（不影响本次运行）：%s", e)

    # 发布目录
    publish_dir = Path(args.publish_dir) if args.publish_dir else Path(tempfile.gettempdir()) / "hs-coach"
    publish_dir.mkdir(parents=True, exist_ok=True)
    logger.info("建议发布到：%s", publish_dir / "advice.json")

    # 单实例锁：已有存活实例则拒绝启动（防双实例抢 Power.log；
    # 残留实例的锁文件会在 PID 已死时被自动接管）
    lock = SingleInstanceLock(publish_dir)
    ok, lock_message = lock.acquire()
    if not ok:
        print(f"错误：{lock_message}", file=sys.stderr)
        return 3
    try:
        return _run(args, cfg, publish_dir)
    finally:
        lock.release()


def _run(args, cfg, publish_dir: Path) -> int:
    """监听主循环（已在单实例锁保护下执行）。"""
    # 1. 确保 log.config 已开启
    status = ensure_log_config()
    logger.info("log.config: %s — %s", status.action, status.message)

    # 2. 构建卡牌库
    db = CardDatabase()
    logger.info("构建卡牌库（首次会从 HearthstoneJSON 下载，约 1-2 分钟）...")
    db.build()
    logger.info("卡牌库就绪：%d 张卡", len(db))

    # 3. LLM 客户端（经 holder 热切换：设置里改模型/地址即时生效）
    client_holder = _ClientHolder(
        DeepSeekClient(api_key=cfg.api_key, model=cfg.model, base_url=cfg.base_url)
    )

    power_log = power_log_path()
    # friendly id 未知时先用占位 1，第一次解析后自动校准（D9 防线：
    # 校准前若映射错误，serialize_game 的 D9 断言会拒绝输出并告警）
    friendly_explicit = (
        args.friendly_player_id is not None or cfg.friendly_player_id is not None
    )
    friendly_player_id = cfg.friendly_player_id or 1
    trigger = TurnTrigger(
        friendly_player_id=friendly_player_id, coach_mode=cfg.coach_mode
    )
    detector = IncrementalTurnDetector(friendly_player_id=friendly_player_id)

    # 4. 后台线程：增量 tail → 正则检测回合 → 全量解析 → 校准 → LLM（优化 2+3）
    stop_event = threading.Event()

    def apply_calibration(result) -> None:
        """日志自动校准友方玩家 id；校准结果与当前值冲突时纠正并告警。"""
        calibrated = calibrate_friendly_player(result)
        if calibrated is None:
            return
        if calibrated != trigger.friendly_player_id:
            if friendly_explicit:
                logger.warning(
                    "自动校准：友方玩家 id 应为 %d（当前 %d，已自动纠正）。"
                    "若你手动指定过请核对。",
                    calibrated, trigger.friendly_player_id,
                )
            else:
                logger.info("自动校准：友方玩家 id = %d", calibrated)
            trigger.friendly_player_id = calibrated
            detector.friendly_player_id = calibrated

    # LLM 建议调度器：把"调 LLM → 发布 advice.json"这条慢路径从 log_worker
    # 剥离到独立线程，避免 LLM 慢（超时 120s）反噬日志读取与记牌器快照。
    # latest-wins：新回合到达时丢弃尚未启动的旧 pending，不堆积过时请求。
    advice_dispatcher = AdviceDispatcher()

    def advice_handler(job: AdviceJob) -> None:
        """worker 线程：调 LLM + 发布 + 更新 last_advice（含异常兜底）。

        job.snapshot 是 submit 时已序列化的不可变快照，无需再碰 hslog game
        对象，跨线程安全。失败由 get_advice 内部降级为兜底建议（degraded）。
        """
        try:
            advice = trigger.generate_and_publish(
                job.snapshot, job.turn, job.fallback, client_holder, publish_dir
            )
            logger.info("回合建议已发布（T%d）：%s", job.turn, advice.headline)
        except Exception as e:  # 发布失败不致命（handler 抛错 dispatcher 会吞）
            logger.warning("回合建议发布失败（T%d）：%s", job.turn, e)

    advice_worker = threading.Thread(
        target=advice_dispatcher.run_loop,
        args=(advice_handler, stop_event),
        daemon=True,
        name="hscoach-advice-worker",
    )
    advice_worker.start()

    def log_worker():
        logger.info("开始监听 %s（打开炉石打一局即开始）...", power_log)
        batch: list[str] = []
        last_state_ts = 0.0  # 盒子快照节流（1s 一次，不阻塞回合触发）
        for line in tail_power_log(poll_interval=0.3):
            if stop_event.is_set():
                break
            batch.append(line)
            # CREATE_GAME 边界：重置检测器（新对局）
            if "CREATE_GAME" in line:
                detector.reset()
                last_state_ts = 0.0  # 新对局立即发一版空快照
            # 每攒一批（或遇到 TAG_CHANGE）检测一次
            if len(batch) >= 50 or "TAG_CHANGE" in line:
                triggered_turns = detector.feed(batch)
                batch.clear()
                for turn in triggered_turns:
                    # 检测到"轮到友方新回合" → 按触发点截取行流全量解析
                    # → 校准 → 序列化快照 → submit 给调度器（不在此阻塞调 LLM）
                    try:
                        result = parse_power_log(detector.get_trigger_window(turn))
                        apply_calibration(result)
                        if result.games:
                            game = result.games[-1]
                            # 序列化 + 检测新回合在 log_worker 完成（轻量），
                            # LLM 调用交给 advice worker，避免慢 LLM 反噬日志读取。
                            snapshot = serialize_game(
                                game, trigger.friendly_player_id, db
                            )
                            new_turn = trigger.detect_new_friendly_turn(snapshot)
                            if new_turn is not None:
                                trigger.last_triggered_turn = new_turn
                                advice_dispatcher.submit(
                                    AdviceJob(
                                        snapshot=snapshot,
                                        turn=new_turn,
                                        fallback=trigger.last_advice,
                                    )
                                )
                    except Exception as e:  # 处理日志出错不致命
                        logger.warning("处理日志出错：%s", e)
                # 盒子：节流发布实时对局快照（血量/手牌/牌库变化即时上屏）
                now = time.monotonic()
                if now - last_state_ts >= 1.0:
                    last_state_ts = now
                    try:
                        result = parse_power_log(detector.get_all_lines())
                        apply_calibration(result)
                        if result.games:
                            snapshot = serialize_game(
                                result.games[-1], trigger.friendly_player_id, db
                            )
                            publish_game_state(
                                publish_dir, snapshot, trigger.friendly_player_id
                            )
                    except Exception as e:  # 快照发布失败不致命（如 D9 断言前）
                        logger.debug("快照发布失败（非致命）：%s", e)

    worker = threading.Thread(target=log_worker, daemon=True)
    worker.start()

    # 5. 前台：启动 overlay（或终端模式）
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
                        snapshot = serialize_game(
                            game, trigger.friendly_player_id, db
                        )
                        # 盒子同步刷新：手动触发也发布一版最新快照
                        publish_game_state(
                            publish_dir, snapshot, trigger.friendly_player_id
                        )
                        # 手动建议走调度器（与自动触发统一，避免和 advice
                        # worker 抢 last_advice；latest-wins 覆盖 pending）。
                        advice_dispatcher.submit(
                            AdviceJob(
                                snapshot=snapshot,
                                turn=snapshot.turn,
                                fallback=trigger.last_advice,
                            )
                        )
                        logger.info("手动建议已排队（T%d）", snapshot.turn)
                except Exception as e:  # 手动触发出错不致命
                    logger.warning("手动触发出错：%s", e)

        def on_restore_log_config() -> str:
            from hscoach.log_config import restore_log_config

            status = restore_log_config()
            logger.info("log.config 还原：%s — %s", status.action, status.message)
            return status.message

        def on_save_settings(new_cfg) -> str:
            """设置对话框保存：写配置文件 + 热切换 LLM 客户端（即时生效）。"""
            try:
                save_config(new_cfg)
            except OSError as e:
                return f"保存失败：{e}"
            client_holder.client = DeepSeekClient(
                api_key=new_cfg.api_key, model=new_cfg.model, base_url=new_cfg.base_url
            )
            logger.info("设置已更新：model=%s base_url=%s", new_cfg.model, new_cfg.base_url)
            return "已保存并即时生效"

        app = OverlayApp(
            advice_path,
            on_manual_trigger=on_manual,
            on_restore_log_config=on_restore_log_config,
            on_save_settings=on_save_settings,
            config=cfg,
        )
        try:
            app.run()
        finally:
            stop_event.set()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
