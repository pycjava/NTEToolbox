import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Eye,
  EyeOff,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Square,
  Terminal
} from "lucide-react";

import type { GameDefinition, WindowInfo } from "./clientModel";
import { isHearthstoneWindow } from "./clientModel";

// ── 与 Rust 侧契约对应的类型 ─────────────────────────────────────────

type HsRunState = "idle" | "starting" | "running" | "stopping" | "completed" | "failed";

type HsCoachConfig = {
  api_key: string;
  model: string;
  base_url: string;
  friendly_player_id: number | null;
};

type HsAdvice = {
  kind: string;
  headline: string;
  why: string;
  steps: string[];
  warning: string;
  latency_ms: number;
  degraded: boolean;
};

type HsAdvicePayload = {
  turn: number;
  timestamp: string;
  advice: HsAdvice;
};

type HsPlayerState = {
  name: string;
  health: number;
  armor: number;
  mana: number;
  max_mana: number;
  hand: { count: number } | Array<{ name: string; cost: number; attack?: number; health?: number }>;
  board: Array<{ name: string }>;
  deck_count: number;
};

type HsGameStatePayload = {
  turn: number;
  current_player_id: number | null;
  friendly_player_id: number;
  timestamp: string;
  players: Record<string, HsPlayerState>;
};

type HsStateSnapshot = {
  runState: HsRunState;
  exitCode?: number | null;
  advice: HsAdvicePayload | null;
  gameState: HsGameStatePayload | null;
};

const KIND_LABEL: Record<string, string> = {
  play: "出牌建议",
  trade: "交换建议",
  pass: "过牌建议",
  uncertain: "待定"
};

const POLL_INTERVAL_MS = 1_000;
const runningStates = new Set<HsRunState>(["starting", "running", "stopping"]);

function getRunLabel(runState: HsRunState) {
  switch (runState) {
    case "starting":
      return "启动中";
    case "running":
      return "运行中";
    case "stopping":
      return "结束中";
    case "completed":
      return "已结束";
    case "failed":
      return "失败";
    default:
      return "就绪";
  }
}

type HsCoachPanelProps = {
  game: GameDefinition;
  onTargetWindowChange: (gameId: string, targetWindow: string) => void;
  onRefreshWindows: (gameId: string) => void;
  onError: (message: string) => void;
};

export default function HsCoachPanel({ game, onTargetWindowChange, onRefreshWindows, onError }: HsCoachPanelProps) {
  const [snapshot, setSnapshot] = useState<HsStateSnapshot | null>(null);
  const [config, setConfig] = useState<HsCoachConfig | null>(null);
  const [configDraft, setConfigDraft] = useState<HsCoachConfig | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [logBusy, setLogBusy] = useState(false);
  const [logMessage, setLogMessage] = useState<string | null>(null);
  const [overlayVisible, setOverlayVisible] = useState(false);
  const [overlayBusy, setOverlayBusy] = useState(false);
  const [windows, setWindows] = useState<WindowInfo[]>(game.controller?.availableWindows ?? []);
  // 首次枚举完成前不显示「未检测到炉石窗口」提示（避免打开面板时闪一下）
  const [windowsLoaded, setWindowsLoaded] = useState(false);

  // 读取共享配置（与独立版 HsCoach 同一份 config.json）
  useEffect(() => {
    invoke<HsCoachConfig>("get_hscoach_config")
      .then((cfg) => {
        setConfig(cfg);
        setConfigDraft(cfg);
      })
      .catch((error) => console.error("Failed to load hscoach config", error));
  }, []);

  // 轮询后端状态（进程状态 + advice.json + game_state.json）
  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const state = await invoke<HsStateSnapshot>("poll_hscoach_state");
        if (!cancelled) setSnapshot(state);
      } catch (error) {
        console.error("Failed to poll hscoach state", error);
      }
    };

    void poll();
    const timer = window.setInterval(() => { void poll(); }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const runState = snapshot?.runState ?? "idle";
  const isRunning = runningStates.has(runState);

  async function handleRunChange(runState: HsRunState) {
    if (runState === "running") {
      setSnapshot((current) => ({
        runState: "starting",
        advice: current?.advice ?? null,
        gameState: current?.gameState ?? null
      }));
      try {
        await invoke("start_hscoach");
      } catch (error) {
        console.error("Failed to start hscoach", error);
        setSnapshot((current) => ({ ...(current ?? { runState: "idle", advice: null, gameState: null }), runState: "failed" }));
      }
      return;
    }

    if (runState === "idle") {
      setSnapshot((current) => ({
        runState: "stopping",
        advice: current?.advice ?? null,
        gameState: current?.gameState ?? null
      }));
      try {
        await invoke("stop_hscoach");
      } catch (error) {
        console.error("Failed to stop hscoach", error);
        onError("结束教练失败：请检查任务管理器中的 hscoachd 进程后重试");
      }
    }
  }

  async function handleSaveConfig() {
    if (!configDraft) return;
    setSavingConfig(true);
    try {
      await invoke("save_hscoach_config", { config: configDraft });
      setConfig(configDraft);
    } catch (error) {
      console.error("Failed to save hscoach config", error);
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSetLogging(enabled: boolean) {
    setLogBusy(true);
    setLogMessage(null);
    try {
      const message = await invoke<string>("set_hs_logging", { enabled });
      setLogMessage(message);
    } catch (error) {
      console.error("Failed to toggle hs logging", error);
      setLogMessage(String(error));
    } finally {
      setLogBusy(false);
    }
  }

  async function handleShowOverlay() {
    setOverlayBusy(true);
    try {
      await invoke("show_hs_overlay", { targetWindow: game.controller?.targetWindow ?? "" });
      setOverlayVisible(true);
    } catch (error) {
      console.error("Failed to show hs overlay", error);
    } finally {
      setOverlayBusy(false);
    }
  }

  async function handleHideOverlay() {
    setOverlayBusy(true);
    try {
      await invoke("hide_hs_overlay");
      setOverlayVisible(false);
    } catch (error) {
      console.error("Failed to hide hs overlay", error);
    } finally {
      setOverlayBusy(false);
    }
  }

  const handleRefreshWindows = useCallback(() => {
    invoke<WindowInfo[]>("enumerate_windows")
      .then((result) => {
        setWindows(result ?? []);
        setWindowsLoaded(true);
      })
      .catch((error) => {
        console.error("Failed to enumerate windows", error);
        setWindowsLoaded(true);
      });
    onRefreshWindows(game.id);
  }, [game.id, onRefreshWindows]);

  // 挂载即枚举一次窗口列表：跟随窗口下拉不依赖用户手动点刷新
  useEffect(() => {
    handleRefreshWindows();
  }, [handleRefreshWindows]);

  const advice = snapshot?.advice?.advice;
  const gameState = snapshot?.gameState;
  const friendlyId = gameState?.friendly_player_id;
  const players = gameState?.players ?? {};
  const friendlyPlayer = friendlyId != null ? players[String(friendlyId)] : undefined;
  const opponentPlayer = friendlyId != null
    ? players[String(friendlyId === 1 ? 2 : 1)]
    : undefined;

  // 枚举完成且列表里没有炉石类窗口时给出指引（判定规则见 isHearthstoneWindow）
  const hasHearthstoneWindow = windows.some(isHearthstoneWindow);
  const showWindowHint = windowsLoaded && !hasHearthstoneWindow;

  return (
    <div className="hs-panel">
      {/* 运行控制 */}
      <section className="hs-card">
        <div className="hs-card-header">
          <h3>教练运行</h3>
          <span className={`run-badge run-${runState}`} aria-live="polite">{getRunLabel(runState)}</span>
        </div>
        <p className="hs-card-hint">
          启动后监听炉石 Power.log：回合开始时生成出牌建议，实时发布对局快照（仅本地可见信息，不读取对手手牌）。
        </p>
        <div className="hs-actions">
          {isRunning ? (
            <button className="secondary-action danger" type="button" onClick={() => { void handleRunChange("idle"); }}>
              <Square size={16} />
              结束教练
            </button>
          ) : (
            <button className="primary-action" type="button" disabled={runState === "starting"} onClick={() => { void handleRunChange("running"); }}>
              {runState === "starting" ? <Loader2 size={17} className="spin" /> : <Play size={17} />}
              启动教练
            </button>
          )}
          {snapshot?.exitCode != null ? <span className="hs-exit-code">退出码 {snapshot.exitCode}</span> : null}
        </div>
      </section>

      {/* LLM 配置（与独立版共享） */}
      {configDraft ? (
        <section className="hs-card">
          <div className="hs-card-header">
            <h3>LLM 配置</h3>
            <button className="row-icon-button" type="button" title="保存配置" aria-label="保存配置" onClick={() => { void handleSaveConfig(); }} disabled={savingConfig}>
              {savingConfig ? <Loader2 size={18} className="spin" /> : <Save size={18} />}
            </button>
          </div>
          <p className="hs-card-hint">与独立版 HsCoach 共享 %APPDATA%\NTEToolbox\hscoach\config.json，改完即时生效（运行中需重启教练）。</p>
          <div className="hs-config-grid">
            <label className="option-row">
              <span className="option-label">API Key</span>
              <input
                type="password"
                value={configDraft.api_key}
                placeholder="sk-..."
                onChange={(event) => setConfigDraft({ ...configDraft, api_key: event.target.value })}
              />
            </label>
            <label className="option-row">
              <span className="option-label">模型</span>
              <input
                type="text"
                value={configDraft.model}
                onChange={(event) => setConfigDraft({ ...configDraft, model: event.target.value })}
              />
            </label>
            <label className="option-row">
              <span className="option-label">API 地址</span>
              <input
                type="text"
                value={configDraft.base_url}
                onChange={(event) => setConfigDraft({ ...configDraft, base_url: event.target.value })}
              />
            </label>
            <label className="option-row">
              <span className="option-label">友方玩家 id（留空自动校准）</span>
              <input
                type="number"
                value={configDraft.friendly_player_id ?? ""}
                placeholder="自动"
                onChange={(event) => setConfigDraft({
                  ...configDraft,
                  friendly_player_id: event.target.value === "" ? null : Number(event.target.value)
                })}
              />
            </label>
          </div>
        </section>
      ) : null}

      {/* 炉石日志 */}
      <section className="hs-card">
        <div className="hs-card-header">
          <h3>炉石日志</h3>
        </div>
        <p className="hs-card-hint">炉石需要开启 Power 日志才能解析对局。启动教练会自动开启；还原会把 log.config 恢复原状。</p>
        <div className="hs-actions">
          <button className="secondary-action" type="button" disabled={logBusy} onClick={() => { void handleSetLogging(true); }}>
            <Terminal size={16} />
            开启日志
          </button>
          <button className="secondary-action" type="button" disabled={logBusy} onClick={() => { void handleSetLogging(false); }}>
            <RotateCcw size={16} />
            还原日志
          </button>
          {logBusy ? <Loader2 size={16} className="spin" /> : null}
        </div>
        {logMessage ? <p className="hs-log-message">{logMessage}</p> : null}
      </section>

      {/* 悬浮窗 */}
      <section className="hs-card">
        <div className="hs-card-header">
          <h3>游戏内悬浮窗</h3>
        </div>
        <p className="hs-card-hint">置顶、透明、点击穿透，跟随炉石窗口显示最新建议与血量/费用。</p>
        <div className="connection-row">
          <span className="connection-label">跟随窗口</span>
          <select
            value={game.controller?.targetWindow ?? ""}
            onChange={(event) => onTargetWindowChange(game.id, event.target.value)}
          >
            <option value="">请选择炉石窗口</option>
            {windows.map((win) => (
              <option key={win.hwnd} value={win.hwnd}>{win.title} ({win.className})</option>
            ))}
          </select>
          <button className="icon-button connection-refresh" type="button" aria-label="刷新窗口列表" title="刷新窗口列表" onClick={handleRefreshWindows}>
            <RefreshCw size={18} />
          </button>
        </div>
        {showWindowHint ? (
          <p className="hs-log-message">
            未检测到炉石窗口：请确认炉石已启动并处于窗口化/无边框模式后点刷新；若仍不出现，请以管理员身份运行本工具箱后重试。
          </p>
        ) : null}
        <div className="hs-actions">
          {overlayVisible ? (
            <button className="secondary-action danger" type="button" disabled={overlayBusy} onClick={() => { void handleHideOverlay(); }}>
              <EyeOff size={16} />
              隐藏悬浮窗
            </button>
          ) : (
            <button className="secondary-action" type="button" disabled={overlayBusy} onClick={() => { void handleShowOverlay(); }}>
              {overlayBusy ? <Loader2 size={16} className="spin" /> : <Eye size={16} />}
              显示悬浮窗
            </button>
          )}
        </div>
      </section>

      {/* 最新建议 */}
      <section className="hs-card">
        <div className="hs-card-header">
          <h3>最新建议</h3>
          {snapshot?.advice ? <span className="hs-turn-badge">第 {snapshot.advice.turn} 回合</span> : null}
        </div>
        {advice ? (
          <article className={`hs-advice hs-advice-${advice.kind}`}>
            <div className="hs-advice-head">
              <span className="hs-advice-kind">{KIND_LABEL[advice.kind] ?? advice.kind}</span>
              {advice.degraded ? <span className="hs-advice-degraded">降级</span> : null}
              {advice.latency_ms > 0 ? <span className="hs-advice-latency">{Math.round(advice.latency_ms / 100) / 10}s</span> : null}
            </div>
            <h4 className="hs-advice-headline">{advice.headline || "（无标题）"}</h4>
            {advice.why ? <p className="hs-advice-why">{advice.why}</p> : null}
            {advice.steps.length > 0 ? (
              <ol className="hs-advice-steps">
                {advice.steps.map((step, index) => <li key={index}>{step}</li>)}
              </ol>
            ) : null}
            {advice.warning ? <p className="hs-advice-warning">⚠ {advice.warning}</p> : null}
          </article>
        ) : (
          <p className="hs-empty">暂无建议。启动教练并打一局炉石，回合开始时这里会出现建议。</p>
        )}
      </section>

      {/* 对局快照 */}
      <section className="hs-card">
        <div className="hs-card-header">
          <h3>对局状态</h3>
          {gameState ? <span className="hs-turn-badge">第 {gameState.turn} 回合</span> : null}
        </div>
        {gameState ? (
          <div className="hs-state-grid">
            <HsPlayerSummary title="我方" player={friendlyPlayer} current={gameState.current_player_id === friendlyId} />
            <HsPlayerSummary title="对方" player={opponentPlayer} current={gameState.current_player_id === friendlyId ? false : true} />
          </div>
        ) : (
          <p className="hs-empty">暂无对局数据。检测到炉石对局后这里会显示实时快照。</p>
        )}
      </section>
    </div>
  );
}

function HsPlayerSummary({ title, player, current }: { title: string; player?: HsPlayerState; current: boolean }) {
  if (!player) {
    return (
      <div className="hs-player">
        <span className="hs-player-title">{title}</span>
        <p className="hs-empty">—</p>
      </div>
    );
  }

  const handLabel = Array.isArray(player.hand) ? `${player.hand.length} 张` : `${player.hand.count} 张`;

  return (
    <div className={`hs-player ${current ? "current" : ""}`}>
      <span className="hs-player-title">{title} {current ? "· 行动中" : ""}</span>
      <span className="hs-player-meta">
        {player.health > 0 ? `血量 ${player.health}` : "已阵亡"}
        {player.armor > 0 ? ` +${player.armor} 甲` : ""}
        {" · "}
        法力 {player.mana}/{player.max_mana}
      </span>
      <span className="hs-player-meta">
        手牌 {handLabel} · 牌库 {player.deck_count} · 场面 {player.board.length}
      </span>
    </div>
  );
}
