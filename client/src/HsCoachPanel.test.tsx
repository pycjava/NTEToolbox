import { useEffect, useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GameDefinition } from "./clientModel";
import HsCoachPanel from "./HsCoachPanel";

const { invokeMock } = vi.hoisted(() => ({
  invokeMock: vi.fn()
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock
}));

const HS_GAME: GameDefinition = {
  id: "hs",
  name: "炉石传说",
  description: "AI 教练：实时对局解析与出牌建议",
  shortName: "炉",
  icon: "/hs-icon.png",
  status: "ready",
  kind: "process",
  features: [],
  controller: {
    controllerType: "",
    controllerTypes: [],
    targetWindow: "",
    availableWindows: [],
    connected: false
  }
};

const DEFAULT_CONFIG = {
  api_key: "",
  model: "deepseek-chat",
  base_url: "https://api.deepseek.com/v1",
  friendly_player_id: null,
  coach_mode: "teach"
};

const IDLE_SNAPSHOT = {
  runState: "idle",
  exitCode: null,
  advice: null,
  gameState: null
};

function mockBaseline(overrides: Record<string, (cmd: string, args?: unknown) => unknown>) {
  invokeMock.mockImplementation((cmd: string, args?: unknown) => {
    if (cmd in overrides) return Promise.resolve(overrides[cmd](cmd, args));
    if (cmd === "get_hscoach_config") return Promise.resolve(DEFAULT_CONFIG);
    return Promise.resolve(null);
  });
}

afterEach(() => {
  invokeMock.mockReset();
  cleanup();
});

describe("HsCoachPanel run controls", () => {
  it("starts and stops the coach with button states flowing idle → starting → running → stopping → idle", async () => {
    let pollResult = IDLE_SNAPSHOT;
    mockBaseline({
      poll_hscoach_state: () => pollResult,
      start_hscoach: () => undefined,
      stop_hscoach: () => undefined
    });

    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    // 初始：就绪 + 启动教练
    expect(screen.getByText("就绪")).toBeTruthy();
    expect(screen.getByRole("button", { name: /启动教练/ })).toBeTruthy();

    // 启动：按钮立即进入「启动中」，随后轮询进入「运行中」
    fireEvent.click(screen.getByRole("button", { name: /启动教练/ }));
    expect(screen.getByText("启动中")).toBeTruthy();
    expect(invokeMock).toHaveBeenCalledWith("start_hscoach");

    pollResult = { ...IDLE_SNAPSHOT, runState: "running" };
    await waitFor(() => expect(screen.getByText("运行中")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByRole("button", { name: /结束教练/ })).toBeTruthy();

    // 结束：按钮进入「结束中」，stop 被调用，轮询回到 idle
    fireEvent.click(screen.getByRole("button", { name: /结束教练/ }));
    expect(screen.getByText("结束中")).toBeTruthy();
    expect(invokeMock).toHaveBeenCalledWith("stop_hscoach");

    pollResult = IDLE_SNAPSHOT;
    await waitFor(() => expect(screen.getByText("就绪")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByRole("button", { name: /启动教练/ })).toBeTruthy();
  });

  it("recovers to idle via polling even when stop_hscoach rejects", async () => {
    let pollResult = { ...IDLE_SNAPSHOT, runState: "running" };
    mockBaseline({
      poll_hscoach_state: () => pollResult,
      start_hscoach: () => undefined,
      stop_hscoach: () => {
        throw new Error("stop failed");
      }
    });

    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    pollResult = { ...IDLE_SNAPSHOT, runState: "running" };
    await waitFor(() => expect(screen.getByRole("button", { name: /结束教练/ })).toBeTruthy(), { timeout: 3000 });

    // stop 失败：状态短暂停在「结束中」，但轮询会把后端真实状态（idle）带回来
    fireEvent.click(screen.getByRole("button", { name: /结束教练/ }));
    expect(screen.getByText("结束中")).toBeTruthy();

    pollResult = IDLE_SNAPSHOT;
    await waitFor(() => expect(screen.getByText("就绪")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByRole("button", { name: /启动教练/ })).toBeTruthy();
  });

  it("shows exit code when the coach process exited by itself", async () => {
    let pollResult = { ...IDLE_SNAPSHOT, runState: "completed", exitCode: 1 };
    mockBaseline({
      poll_hscoach_state: () => pollResult,
      start_hscoach: () => undefined
    });

    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => expect(screen.getByText("已结束")).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByText("退出码 1")).toBeTruthy();
    // 已结束后按钮回到「启动教练」（可再次启动）
    expect(screen.getByRole("button", { name: /启动教练/ })).toBeTruthy();
  });
});

describe("HsCoachPanel game state tracker display", () => {
  const TRACKER_SNAPSHOT = {
    runState: "running",
    exitCode: null,
    advice: null,
    gameState: {
      turn: 12,
      current_player_id: 1,
      friendly_player_id: 1,
      timestamp: "2026-08-13T12:00:00",
      players: {
        "1": {
          name: "玩家1",
          health: 18,
          armor: 2,
          mana: 4,
          max_mana: 8,
          hand: [{ name: "火球术", cost: 4 }],
          board: [],
          deck_count: 3,
          fatigue: 2,
          played_cards: [{ name: "火球术" }, { name: "寒冰箭" }, { name: "奥术智慧" }],
          secrets: 1,
          possible_secrets: []
        },
        "2": {
          name: "玩家2",
          health: 22,
          armor: 0,
          mana: 8,
          max_mana: 8,
          hand: { count: 4 },
          board: [{ name: "苦痛侍僧" }],
          deck_count: 5,
          fatigue: 0,
          played_cards: [{ name: "奥金斧" }],
          secrets: 2,
          possible_secrets: ["法术反制", "寒冰护体", "爆炸符文", "绿洲盟军", "无穷烈焰", "秘法误导"]
        }
      }
    }
  };

  it("shows fatigue count and played cards for the friendly player", async () => {
    mockBaseline({ poll_hscoach_state: () => TRACKER_SNAPSHOT });
    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => expect(screen.getByText(/疲劳 2/)).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByText(/已出牌：火球术、寒冰箭、奥术智慧/)).toBeTruthy();
  });

  it("shows opponent secret count and possible secret pool (capped)", async () => {
    mockBaseline({ poll_hscoach_state: () => TRACKER_SNAPSHOT });
    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => expect(screen.getByText(/奥秘 ×2/)).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByText(/法术反制/)).toBeTruthy();
    // 候选池最多展示 5 个（第 6 个"秘法误导"被截断）
    expect(screen.queryByText(/秘法误导/)).toBeNull();
  });

  it("does not show fatigue when zero and no secrets when none", async () => {
    const plain = {
      ...TRACKER_SNAPSHOT,
      gameState: {
        ...TRACKER_SNAPSHOT.gameState,
        players: {
          "1": { ...TRACKER_SNAPSHOT.gameState.players["1"], fatigue: 0, played_cards: [], secrets: 0 },
          "2": { ...TRACKER_SNAPSHOT.gameState.players["2"], secrets: 0, possible_secrets: [], played_cards: [] }
        }
      }
    };
    mockBaseline({ poll_hscoach_state: () => plain });
    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => expect(screen.getByText(/血量 18/)).toBeTruthy(), { timeout: 3000 });
    expect(screen.queryByText(/疲劳/)).toBeNull();
    expect(screen.queryByText(/奥秘/)).toBeNull();
    expect(screen.queryByText(/已出牌/)).toBeNull();
  });
});

describe("HsCoachPanel stats display", () => {
  const STATS_SNAPSHOT = {
    runState: "running",
    exitCode: null,
    advice: null,
    gameState: null,
    stats: { total: 12, wins: 8, losses: 4, ties: 0, winrate_pct: 66.7 }
  };

  it("shows win/loss record and winrate when stats are present", async () => {
    mockBaseline({ poll_hscoach_state: () => STATS_SNAPSHOT });
    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => expect(screen.getByText(/对局 12/)).toBeTruthy(), { timeout: 3000 });
    expect(screen.getByText(/胜 8/)).toBeTruthy();
    expect(screen.getByText(/胜率 66.7%/)).toBeTruthy();
  });

  it("does not show stats when absent", async () => {
    mockBaseline({ poll_hscoach_state: () => IDLE_SNAPSHOT });
    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => expect(screen.getByText("就绪")).toBeTruthy(), { timeout: 3000 });
    expect(screen.queryByText(/胜率/)).toBeNull();
    expect(screen.queryByText(/对局 \d/)).toBeNull();
  });
});

describe("HsCoachPanel mount enumeration", () => {
  it("enumerates windows exactly once even when the parent re-renders with new inline callbacks", async () => {
    // 回归：面板挂载时的窗口枚举曾依赖 onRefreshWindows 引用——父组件
    // （App）每次重渲染都会创建新内联回调，形成
    // "枚举 → 父 setState → 重渲染 → 再枚举"的无限循环（CPU 打满、
    // vitest 挂死）。修复后：无论父组件重渲染多少次，枚举只发生一次。
    let enumerateCalls = 0;
    mockBaseline({
      poll_hscoach_state: () => IDLE_SNAPSHOT,
      enumerate_windows: () => {
        enumerateCalls += 1;
        return [];
      }
    });

    function Wrapper() {
      const [, setTick] = useState(0);
      useEffect(() => {
        const id = window.setInterval(() => setTick((tick) => tick + 1), 10);
        return () => window.clearInterval(id);
      }, []);
      return (
        <HsCoachPanel
          game={HS_GAME}
          onTargetWindowChange={() => {}}
          onRefreshWindows={() => {}}
          onError={() => {}}
        />
      );
    }

    const { unmount } = render(<Wrapper />);
    await waitFor(() => expect(enumerateCalls).toBeGreaterThan(0), { timeout: 3000 });
    // 让父组件重渲染循环暴露一段时间（10ms 一次 tick）：有 bug 时这里
    // 会反复枚举，计数持续增长；修复后保持 1。
    await new Promise((resolve) => setTimeout(resolve, 150));
    unmount();
    expect(enumerateCalls).toBe(1);
  });
});

describe("HsCoachPanel follow-window dropdown", () => {
  it("auto-enumerates windows on mount and populates the dropdown", async () => {
    mockBaseline({
      poll_hscoach_state: () => IDLE_SNAPSHOT,
      enumerate_windows: () => [
        { hwnd: "595722", title: "炉石传说", className: "UnityWndClass" },
        { hwnd: "1234", title: "微信", className: "WeChatMainWndForPC" }
      ]
    });

    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "炉石传说 (UnityWndClass)" })).toBeTruthy();
    }, { timeout: 3000 });
    expect(invokeMock).toHaveBeenCalledWith("enumerate_windows");
  });

  it("shows a hint when no Hearthstone-like window is enumerated", async () => {
    mockBaseline({
      poll_hscoach_state: () => IDLE_SNAPSHOT,
      enumerate_windows: () => [
        { hwnd: "1234", title: "微信", className: "WeChatMainWndForPC" }
      ]
    });

    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/未检测到炉石窗口/)).toBeTruthy();
    }, { timeout: 3000 });
  });

  it("does not show the hint when a Hearthstone window is listed", async () => {
    mockBaseline({
      poll_hscoach_state: () => IDLE_SNAPSHOT,
      enumerate_windows: () => [
        { hwnd: "595722", title: "炉石传说", className: "UnityWndClass" }
      ]
    });

    render(<HsCoachPanel game={HS_GAME} onTargetWindowChange={() => {}} onRefreshWindows={() => {}} onError={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "炉石传说 (UnityWndClass)" })).toBeTruthy();
    }, { timeout: 3000 });
    expect(screen.queryByText(/未检测到炉石窗口/)).toBeNull();
  });
});
