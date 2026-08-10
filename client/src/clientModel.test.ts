// @vitest-environment jsdom
// clientModel 含 resolveTheme，需要 window.matchMedia（浏览器状态模型用 jsdom 更贴合）
import { describe, expect, it } from "vitest";

import {
  addGame,
  buildInitialClientState,
  getVisibleOptionKeys,
  refreshWindows,
  resolveTheme,
  selectGame,
  setFeatureConfig,
  setFeatureOptionValue,
  setFeatureRunState,
  setGlobalSettingsValues,
  setTheme,
  type GameDefinition,
  type OptionDefinition,
  type WindowInfo
} from "./clientModel";

const fishOptionDefinitions: Record<string, OptionDefinition> = {
  "钓鱼终止时间开关": {
    key: "钓鱼终止时间开关",
    type: "switch",
    label: "终止时间",
    description: "启用后可通过下拉列表选择钓鱼持续时长；到达时间后终止该节点",
    defaultValue: true,
    enabledOptionKeys: ["钓鱼终止时长"]
  },
  "钓鱼终止时长": {
    key: "钓鱼终止时长",
    type: "select",
    label: "钓鱼时长",
    defaultValue: "2小时",
    cases: ["30分钟", "1小时", "2小时", "3小时", "4小时", "6小时", "8小时", "12小时"]
  },
  "溜鱼设置": {
    key: "溜鱼设置",
    type: "input",
    label: "溜鱼设置",
    inputs: [
      {
        name: "溜鱼_midpoint_pix_range",
        label: "溜鱼中点停顿范围 (pix)",
        pipelineType: "int",
        defaultValue: "5"
      },
      {
        name: "溜鱼_midpoint_sleep_time",
        label: "溜鱼中点停顿时间 (ms)",
        pipelineType: "int",
        defaultValue: "5"
      }
    ]
  },
  "卖鱼买换饵开关": {
    key: "卖鱼买换饵开关",
    type: "switch",
    label: "自动卖鱼买换饵 (抢占鼠标)",
    description: "无饵或满舱时，按顺序执行卖鱼、买饵、换饵。由于涉及点击操作，会抢占鼠标",
    defaultValue: true
  },
  "卖鱼买换饵设置": {
    key: "卖鱼买换饵设置",
    type: "input",
    label: "卖鱼买换饵设置",
    inputs: [
      {
        name: "买饵次数",
        label: "买饵次数",
        description: "次数 n 代表买 n * 99 个饵",
        pipelineType: "int",
        defaultValue: "4"
      }
    ]
  },
  "钓鱼_S级鱼截图": {
    key: "钓鱼_S级鱼截图",
    type: "switch",
    label: "S级鱼截图",
    description: "识别到 S 图标时，自动保存当前截图",
    defaultValue: true
  },
  "钓鱼_金色鱼截图": {
    key: "钓鱼_金色鱼截图",
    type: "switch",
    label: "金色鱼截图",
    description: "识别到金色背景光时，自动保存当前截图",
    defaultValue: false
  },
  "钓鱼_鱼截图_设置": {
    key: "钓鱼_鱼截图_设置",
    type: "input",
    label: "",
    inputs: [
      {
        name: "鱼截图冷却时间",
        label: "鱼截图冷却时间 (秒)",
        pipelineType: "int",
        defaultValue: "5"
      }
    ]
  }
};

const assistOptionDefinitions: Record<string, OptionDefinition> = {
  "实时辅助_自动拾取": {
    key: "实时辅助_自动拾取",
    type: "switch",
    label: "自动拾取",
    description: "自动按 F 键拾取。自动判断画面内容决定是否拾取",
    defaultValue: true,
    enabledOptionKeys: ["实时辅助_自动拾取_永远拾取"]
  },
  "实时辅助_自动拾取_永远拾取": {
    key: "实时辅助_自动拾取_永远拾取",
    type: "switch",
    label: "自动拾取 - 永远拾取",
    description: "永远拾取，不判断画面内容。仅在启用自动拾取时有效",
    defaultValue: false
  }
};

const globalSettingsDefaultValues = {
  debug_mode_switch: "0",
  logging_switch: "1"
};

const games: GameDefinition[] = [
  {
    id: "nte",
    name: "异环 NTE",
    shortName: "异",
    status: "ready",
    kind: "maa",
    features: [
      {
        id: "fish",
        name: "钓鱼",
        description: "自动钓鱼、溜鱼、卖鱼买饵",
        configSummary: "",
        optionKeys: [
          "钓鱼终止时间开关",
          "溜鱼设置",
          "卖鱼买换饵开关",
          "卖鱼买换饵设置",
          "钓鱼_S级鱼截图",
          "钓鱼_金色鱼截图",
          "钓鱼_鱼截图_设置"
        ],
        optionValues: {
          "钓鱼终止时间开关": true,
          "钓鱼终止时长": "2小时",
          "溜鱼_midpoint_pix_range": "5",
          "溜鱼_midpoint_sleep_time": "5",
          "卖鱼买换饵开关": true,
          "买饵次数": "4",
          "钓鱼_S级鱼截图": true,
          "钓鱼_金色鱼截图": false,
          "鱼截图冷却时间": "5"
        }
      },
      {
        id: "piano",
        name: "弹钢琴",
        description: "MIDI 文件、键盘输入模式",
        configSummary: "",
        optionKeys: ["弹钢琴_keybord_设置"],
        optionValues: {
          midi_path: "",
          bpm: "",
          piano_mode: "36",
          timeout_mode: "速率不变",
          use_custom_winapi: "1"
        }
      },
      {
        id: "assist",
        name: "实时辅助",
        description: "自动拾取",
        configSummary: "",
        optionKeys: ["实时辅助_自动拾取"],
        optionValues: {
          "实时辅助_自动拾取": true,
          "实时辅助_自动拾取_永远拾取": false
        }
      }
    ]
  },
  {
    id: "future",
    name: "预留游戏",
    shortName: "预",
    status: "ready",
    kind: "maa",
    features: []
  }
];

function buildState() {
  return buildInitialClientState(games, globalSettingsDefaultValues);
}

describe("client model", () => {
  it("defaults to the first game when no selection exists", () => {
    const state = buildState();

    expect(state.selectedGameId).toBe("nte");
    expect(state.games[0].features).toHaveLength(3);
    expect(state.settingsValues).toMatchObject({
      debug_mode_switch: "0",
      logging_switch: "1"
    });
  });

  it("saves global settings values in client state", () => {
    const state = buildState();
    const next = setGlobalSettingsValues(state, { debug_mode_switch: "1" });

    expect(next.settingsValues).toMatchObject({
      debug_mode_switch: "1",
      logging_switch: "1"
    });
  });

  it("selects a game from the top icon switcher", () => {
    const state = buildState();
    const next = selectGame(state, "future");

    expect(next.selectedGameId).toBe("future");
  });

  it("updates the visible feature configuration summary", () => {
    const state = buildState();
    const next = setFeatureConfig(state, "nte", "fish", "终止时间 4小时 · 自动卖鱼买换饵 开启 · 买饵 4次");

    expect(next.games[0].features[0].configSummary).toBe("终止时间 4小时 · 自动卖鱼买换饵 开启 · 买饵 4次");
  });

  it("marks only the selected feature as running", () => {
    const state = buildState();
    const next = setFeatureRunState(state, "nte", "fish", "running");

    expect(next.games[0].features[0].runState).toBe("running");
    expect(next.games[0].features[1].runState).toBe("idle");
  });

  it("adds a local game and selects it for the icon switcher", () => {
    const state = setGlobalSettingsValues(buildState(), { debug_mode_switch: "1" });
    const next = addGame(state, {
      id: "new-game",
      name: "新游戏",
      shortName: "新",
      status: "ready",
      kind: "maa",
      features: []
    });

    expect(next.games).toHaveLength(3);
    expect(next.selectedGameId).toBe("new-game");
    expect(next.settingsValues.debug_mode_switch).toBe("1");
  });

  it("initializes fishing options with screenshot defaults", () => {
    const state = buildState();
    const fish = state.games[0].features[0];

    expect(fish.optionValues).toMatchObject({
      "钓鱼终止时间开关": true,
      "钓鱼终止时长": "2小时",
      "溜鱼_midpoint_pix_range": "5",
      "溜鱼_midpoint_sleep_time": "5",
      "卖鱼买换饵开关": true,
      "买饵次数": "4",
      "钓鱼_S级鱼截图": true,
      "钓鱼_金色鱼截图": false,
      "鱼截图冷却时间": "5"
    });
    expect(fish.configSummary).toBe("终止时间 2小时 · 自动卖鱼买换饵 开启 · 买饵 4次 · S级鱼截图 开启 · 金色鱼截图 关闭");
  });

  it("updates fishing duration in option values and summary", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼终止时长", "4小时");
    const fish = next.games[0].features[0];

    expect(fish.optionValues?.["钓鱼终止时长"]).toBe("4小时");
    expect(fish.configSummary).toBe("终止时间 4小时 · 自动卖鱼买换饵 开启 · 买饵 4次 · S级鱼截图 开启 · 金色鱼截图 关闭");
  });

  it("hides fishing duration when end time is disabled", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼终止时间开关", false);
    const fish = next.games[0].features[0];

    expect(getVisibleOptionKeys(fish.optionKeys ?? [], fishOptionDefinitions, fish.optionValues ?? {})).not.toContain("钓鱼终止时长");
    expect(fish.configSummary).toBe("终止时间 关闭 · 自动卖鱼买换饵 开启 · 买饵 4次 · S级鱼截图 开启 · 金色鱼截图 关闭");
  });

  it("saves fishing midpoint inputs", () => {
    const state = buildState();
    const next = setFeatureOptionValue(
      setFeatureOptionValue(state, "nte", "fish", "溜鱼_midpoint_pix_range", "8"),
      "nte",
      "fish",
      "溜鱼_midpoint_sleep_time",
      "12"
    );
    const fish = next.games[0].features[0];

    expect(fish.optionValues?.["溜鱼_midpoint_pix_range"]).toBe("8");
    expect(fish.optionValues?.["溜鱼_midpoint_sleep_time"]).toBe("12");
  });

  it("updates summary when auto bait is disabled", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "fish", "卖鱼买换饵开关", false);

    expect(next.games[0].features[0].configSummary).toBe("终止时间 2小时 · 自动卖鱼买换饵 关闭 · 买饵 4次 · S级鱼截图 开启 · 金色鱼截图 关闭");
  });

  it("updates fishing summary when S-rank screenshot is disabled", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼_S级鱼截图", false);

    expect(next.games[0].features[0].configSummary).toBe("终止时间 2小时 · 自动卖鱼买换饵 开启 · 买饵 4次 · S级鱼截图 关闭 · 金色鱼截图 关闭");
  });

  it("updates fishing summary when golden fish screenshot is enabled", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼_金色鱼截图", true);

    expect(next.games[0].features[0].configSummary).toBe("终止时间 2小时 · 自动卖鱼买换饵 开启 · 买饵 4次 · S级鱼截图 开启 · 金色鱼截图 开启");
  });

  it("keeps fishing screenshot settings visible when its switch is disabled", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼_S级鱼截图", false);
    const fish = next.games[0].features[0];
    const visibleOptionKeys = getVisibleOptionKeys(
      fish.optionKeys ?? [],
      fishOptionDefinitions,
      fish.optionValues ?? {}
    );

    expect(visibleOptionKeys).toContain("钓鱼_鱼截图_设置");
  });

  it("initializes piano keyboard input options", () => {
    const state = buildState();
    const piano = state.games[0].features[1];

    expect(piano.optionValues).toMatchObject({
      midi_path: "",
      bpm: "",
      piano_mode: "36",
      timeout_mode: "速率不变",
      use_custom_winapi: "1"
    });
    expect(piano.configSummary).toBe("MIDI 未选择 · 模式 36键 · WinAPI 开启");
  });

  it("updates piano summary when a MIDI path is selected", () => {
    const state = buildState();
    const next = setFeatureOptionValue(state, "nte", "piano", "midi_path", "D:\\songs\\theme.mid");
    const piano = next.games[0].features[1];

    expect(piano.optionValues?.midi_path).toBe("D:\\songs\\theme.mid");
    expect(piano.configSummary).toBe("MIDI theme.mid · 模式 36键 · WinAPI 开启");
  });

  it("initializes realtime assist options", () => {
    const state = buildState();
    const assist = state.games[0].features[2];

    expect(assist.optionValues).toMatchObject({
      "实时辅助_自动拾取": true,
      "实时辅助_自动拾取_永远拾取": false
    });
    expect(assist.configSummary).toBe("自动拾取 开启 · 永远拾取 关闭");
  });

  it("hides realtime assist dependent settings when their switches are disabled", () => {
    const state = buildState();
    const withoutPickup = setFeatureOptionValue(state, "nte", "assist", "实时辅助_自动拾取", false);
    const assist = withoutPickup.games[0].features[2];
    const visibleOptionKeys = getVisibleOptionKeys(
      assist.optionKeys ?? [],
      assistOptionDefinitions,
      assist.optionValues ?? {}
    );

    expect(visibleOptionKeys).not.toContain("实时辅助_自动拾取_永远拾取");
    expect(visibleOptionKeys).not.toContain("实时辅助_S级鱼截图");
    expect(visibleOptionKeys).not.toContain("实时辅助_S级鱼截图_设置");
    expect(assist.configSummary).toBe("自动拾取 关闭 · 永远拾取 关闭");
  });

  describe("window refresh", () => {
    function controlledState(targetWindow: string, windows: WindowInfo[]) {
      return buildInitialClientState([
        {
          id: "hs",
          name: "炉石传说",
          shortName: "炉",
          status: "ready",
          kind: "process",
          features: [],
          controller: {
            controllerType: "",
            targetWindow,
            availableWindows: windows,
            connected: targetWindow !== ""
          }
        }
      ]);
    }

    it("keeps the selected window when it still exists after refresh", () => {
      const state = controlledState("595722", [
        { hwnd: "595722", title: "炉石传说", className: "UnityWndClass" }
      ]);

      const next = refreshWindows(state, "hs", [
        { hwnd: "595722", title: "炉石传说", className: "UnityWndClass" },
        { hwnd: "1234", title: "微信", className: "WeChatMainWndForPC" }
      ]);

      const controller = next.games[0].controller;
      expect(controller?.availableWindows).toHaveLength(2);
      expect(controller?.targetWindow).toBe("595722");
      expect(controller?.connected).toBe(true);
    });

    it("clears the selection when the selected window disappears", () => {
      const state = controlledState("595722", [
        { hwnd: "595722", title: "炉石传说", className: "UnityWndClass" }
      ]);

      const next = refreshWindows(state, "hs", [
        { hwnd: "1234", title: "微信", className: "WeChatMainWndForPC" }
      ]);

      const controller = next.games[0].controller;
      expect(controller?.availableWindows).toHaveLength(1);
      expect(controller?.targetWindow).toBe("");
      expect(controller?.connected).toBe(false);
    });

    it("populates the list without connecting when nothing was selected", () => {
      const state = controlledState("", []);

      const next = refreshWindows(state, "hs", [
        { hwnd: "595722", title: "炉石传说", className: "UnityWndClass" }
      ]);

      const controller = next.games[0].controller;
      expect(controller?.availableWindows).toHaveLength(1);
      expect(controller?.targetWindow).toBe("");
      expect(controller?.connected).toBe(false);
    });
  });

  describe("theme", () => {
    it("defaults to system theme", () => {
      const state = buildState();

      expect(state.theme).toBe("system");
    });

    it("resolves explicit light and dark themes as-is", () => {
      expect(resolveTheme("light")).toBe("light");
      expect(resolveTheme("dark")).toBe("dark");
    });

    it("resolves system theme by consulting prefers-color-scheme", () => {
      const original = window.matchMedia;
      // 模拟系统深色
      window.matchMedia = (query: string) =>
        ({
          matches: query.includes("dark"),
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false
        }) as unknown as MediaQueryList;

      try {
        expect(resolveTheme("system")).toBe("dark");
      } finally {
        window.matchMedia = original;
      }
    });

    it("falls back to light when system prefers light", () => {
      const original = window.matchMedia;
      window.matchMedia = (query: string) =>
        ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false
        }) as unknown as MediaQueryList;

      try {
        expect(resolveTheme("system")).toBe("light");
      } finally {
        window.matchMedia = original;
      }
    });

    it("updates theme via setTheme reducer", () => {
      const state = buildState();
      const next = setTheme(state, "dark");

      expect(next.theme).toBe("dark");
      // 不应污染其余状态
      expect(next.selectedGameId).toBe(state.selectedGameId);
      expect(next.games).toBe(state.games);
    });
  });
});
