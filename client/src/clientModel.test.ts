import { describe, expect, it } from "vitest";

import {
  addGame,
  buildInitialClientState,
  selectGame,
  setFeatureConfig,
  setFeatureRunState,
  type GameDefinition
} from "./clientModel";

const games: GameDefinition[] = [
  {
    id: "nte",
    name: "异环 NTE",
    shortName: "异",
    status: "ready",
    features: [
      {
        id: "fish",
        name: "钓鱼",
        description: "自动钓鱼、溜鱼、卖鱼买饵",
        configSummary: "终止时间 2小时 · 自动买饵 关闭"
      },
      {
        id: "piano",
        name: "弹钢琴",
        description: "MIDI 文件、键盘输入模式",
        configSummary: "MIDI 未选择 · WinAPI 输入关闭"
      }
    ]
  },
  {
    id: "future",
    name: "预留游戏",
    shortName: "预",
    status: "placeholder",
    features: []
  }
];

describe("client model", () => {
  it("defaults to the first game when no selection exists", () => {
    const state = buildInitialClientState(games);

    expect(state.selectedGameId).toBe("nte");
    expect(state.games[0].features).toHaveLength(2);
  });

  it("selects a game from the top icon switcher", () => {
    const state = buildInitialClientState(games);
    const next = selectGame(state, "future");

    expect(next.selectedGameId).toBe("future");
  });

  it("updates the visible feature configuration summary", () => {
    const state = buildInitialClientState(games);
    const next = setFeatureConfig(state, "nte", "fish", "终止时间 4小时 · 自动买饵 开启");

    expect(next.games[0].features[0].configSummary).toBe("终止时间 4小时 · 自动买饵 开启");
  });

  it("marks only the selected feature as running", () => {
    const state = buildInitialClientState(games);
    const next = setFeatureRunState(state, "nte", "fish", "running");

    expect(next.games[0].features[0].runState).toBe("running");
    expect(next.games[0].features[1].runState).toBe("idle");
  });

  it("adds a local game and selects it for the icon switcher", () => {
    const state = buildInitialClientState(games);
    const next = addGame(state, {
      id: "new-game",
      name: "新游戏",
      shortName: "新",
      status: "placeholder",
      features: []
    });

    expect(next.games).toHaveLength(3);
    expect(next.selectedGameId).toBe("new-game");
  });
}
);
