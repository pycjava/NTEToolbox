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
  friendly_player_id: null
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
