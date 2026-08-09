import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

// 与 HsCoachPanel 相同的契约类型（悬浮窗只渲染已过滤的 advice/game_state）
type HsRunState = "idle" | "starting" | "running" | "stopping" | "completed" | "failed";

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

type HsGameStatePayload = {
  turn: number;
  current_player_id: number | null;
  friendly_player_id: number;
  timestamp: string;
  players: Record<string, { name: string; health: number; armor: number; mana: number; max_mana: number; deck_count: number; board: unknown[] }>;
};

type HsStateSnapshot = {
  runState: HsRunState;
  advice: HsAdvicePayload | null;
  gameState: HsGameStatePayload | null;
};

const POLL_INTERVAL_MS = 1_000;

export default function HsOverlay() {
  const [snapshot, setSnapshot] = useState<HsStateSnapshot | null>(null);

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

  const advice = snapshot?.advice?.advice;
  const gameState = snapshot?.gameState;
  const friendlyId = gameState?.friendly_player_id;
  const friendlyPlayer = friendlyId != null ? gameState?.players[String(friendlyId)] : undefined;
  const opponentPlayer = friendlyId != null
    ? gameState?.players[String(friendlyId === 1 ? 2 : 1)]
    : undefined;

  return (
    <div className="hs-overlay-root">
      {advice ? (
        <article className="hs-overlay-advice">
          <div className="hs-overlay-head">
            <span className="hs-overlay-turn">T{snapshot?.advice?.turn ?? "?"}</span>
            <span className="hs-overlay-kind">{advice.kind}</span>
            {advice.degraded ? <span className="hs-overlay-degraded">降级</span> : null}
          </div>
          <h2 className="hs-overlay-headline">{advice.headline || "（无标题）"}</h2>
          {advice.why ? <p className="hs-overlay-why">{advice.why}</p> : null}
          {advice.steps.length > 0 ? (
            <ol className="hs-overlay-steps">
              {advice.steps.map((step, index) => <li key={index}>{step}</li>)}
            </ol>
          ) : null}
          {advice.warning ? <p className="hs-overlay-warning">⚠ {advice.warning}</p> : null}
        </article>
      ) : (
        <div className="hs-overlay-empty">
          <p>{snapshot?.runState === "running" ? "等待建议…" : "教练未运行"}</p>
        </div>
      )}

      {gameState ? (
        <div className="hs-overlay-state">
          <span className="hs-overlay-hp">
            我 {friendlyPlayer ? `${friendlyPlayer.health}${friendlyPlayer.armor > 0 ? `+${friendlyPlayer.armor}` : ""}HP` : "—"}
          </span>
          <span className="hs-overlay-hp">
            敌 {opponentPlayer ? `${opponentPlayer.health}${opponentPlayer.armor > 0 ? `+${opponentPlayer.armor}` : ""}HP` : "—"}
          </span>
          <span className="hs-overlay-mana">
            {friendlyPlayer ? `法力 ${friendlyPlayer.mana}/${friendlyPlayer.max_mana}` : ""}
          </span>
        </div>
      ) : null}
    </div>
  );
}
