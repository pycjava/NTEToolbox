import { describe, expect, it } from "vitest";

import {
  addGame,
  buildInitialClientState,
  getVisibleOptionKeys,
  selectGame,
  setFeatureConfig,
  setFeatureOptionValue,
  setFeatureRunState,
  setGlobalSettingsValues,
  type GameDefinition,
  type OptionDefinition
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
  },
  "实时辅助_S级鱼截图": {
    key: "实时辅助_S级鱼截图",
    type: "switch",
    label: "S级鱼截图",
    description: "识别到金色背景光和 S 图标时，自动保存当前截图",
    defaultValue: true,
    enabledOptionKeys: ["实时辅助_S级鱼截图_设置"]
  },
  "实时辅助_S级鱼截图_设置": {
    key: "实时辅助_S级鱼截图_设置",
    type: "input",
    label: "",
    inputs: [
      {
        name: "S级鱼截图保存目录",
        label: "S级鱼截图保存目录",
        pipelineType: "string",
        defaultValue: "screenshots/s_fish"
      },
      {
        name: "S级鱼截图冷却时间",
        label: "S级鱼截图冷却时间 (秒)",
        pipelineType: "int",
        defaultValue: "5"
      }
    ]
  }
};

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
        configSummary: "",
        optionKeys: ["钓鱼终止时间开关", "溜鱼设置", "卖鱼买换饵开关", "卖鱼买换饵设置"]
      },
      {
        id: "piano",
        name: "弹钢琴",
        description: "MIDI 文件、键盘输入模式",
        configSummary: "",
        optionKeys: ["弹钢琴_keybord_设置"]
      },
      {
        id: "assist",
        name: "实时辅助",
        description: "自动拾取、S 级鱼截图",
        configSummary: "",
        optionKeys: ["实时辅助_自动拾取", "实时辅助_S级鱼截图"]
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
    expect(state.games[0].features).toHaveLength(3);
    expect(state.settingsValues).toMatchObject({
      debug_mode_switch: "0",
      logging_switch: "1"
    });
  });

  it("saves global settings values in client state", () => {
    const state = buildInitialClientState(games);
    const next = setGlobalSettingsValues(state, { debug_mode_switch: "1" });

    expect(next.settingsValues).toMatchObject({
      debug_mode_switch: "1",
      logging_switch: "1"
    });
  });

  it("selects a game from the top icon switcher", () => {
    const state = buildInitialClientState(games);
    const next = selectGame(state, "future");

    expect(next.selectedGameId).toBe("future");
  });

  it("updates the visible feature configuration summary", () => {
    const state = buildInitialClientState(games);
    const next = setFeatureConfig(state, "nte", "fish", "终止时间 4小时 · 自动卖鱼买换饵 开启 · 买饵 4次");

    expect(next.games[0].features[0].configSummary).toBe("终止时间 4小时 · 自动卖鱼买换饵 开启 · 买饵 4次");
  });

  it("marks only the selected feature as running", () => {
    const state = buildInitialClientState(games);
    const next = setFeatureRunState(state, "nte", "fish", "running");

    expect(next.games[0].features[0].runState).toBe("running");
    expect(next.games[0].features[1].runState).toBe("idle");
  });

  it("adds a local game and selects it for the icon switcher", () => {
    const state = setGlobalSettingsValues(buildInitialClientState(games), { debug_mode_switch: "1" });
    const next = addGame(state, {
      id: "new-game",
      name: "新游戏",
      shortName: "新",
      status: "placeholder",
      features: []
    });

    expect(next.games).toHaveLength(3);
    expect(next.selectedGameId).toBe("new-game");
    expect(next.settingsValues.debug_mode_switch).toBe("1");
  });

  it("initializes fishing options with screenshot defaults", () => {
    const state = buildInitialClientState(games);
    const fish = state.games[0].features[0];

    expect(fish.optionValues).toMatchObject({
      "钓鱼终止时间开关": true,
      "钓鱼终止时长": "2小时",
      "溜鱼_midpoint_pix_range": "5",
      "溜鱼_midpoint_sleep_time": "5",
      "卖鱼买换饵开关": true,
      "买饵次数": "4"
    });
    expect(fish.configSummary).toBe("终止时间 2小时 · 自动卖鱼买换饵 开启 · 买饵 4次");
  });

  it("updates fishing duration in option values and summary", () => {
    const state = buildInitialClientState(games);
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼终止时长", "4小时");
    const fish = next.games[0].features[0];

    expect(fish.optionValues?.["钓鱼终止时长"]).toBe("4小时");
    expect(fish.configSummary).toBe("终止时间 4小时 · 自动卖鱼买换饵 开启 · 买饵 4次");
  });

  it("hides fishing duration when end time is disabled", () => {
    const state = buildInitialClientState(games);
    const next = setFeatureOptionValue(state, "nte", "fish", "钓鱼终止时间开关", false);
    const fish = next.games[0].features[0];

    expect(getVisibleOptionKeys(fish.optionKeys ?? [], fishOptionDefinitions, fish.optionValues ?? {})).not.toContain("钓鱼终止时长");
    expect(fish.configSummary).toBe("终止时间 关闭 · 自动卖鱼买换饵 开启 · 买饵 4次");
  });

  it("saves fishing midpoint inputs", () => {
    const state = buildInitialClientState(games);
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
    const state = buildInitialClientState(games);
    const next = setFeatureOptionValue(state, "nte", "fish", "卖鱼买换饵开关", false);

    expect(next.games[0].features[0].configSummary).toBe("终止时间 2小时 · 自动卖鱼买换饵 关闭 · 买饵 4次");
  });

  it("initializes piano keyboard input options", () => {
    const state = buildInitialClientState(games);
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
    const state = buildInitialClientState(games);
    const next = setFeatureOptionValue(state, "nte", "piano", "midi_path", "D:\\songs\\theme.mid");
    const piano = next.games[0].features[1];

    expect(piano.optionValues?.midi_path).toBe("D:\\songs\\theme.mid");
    expect(piano.configSummary).toBe("MIDI theme.mid · 模式 36键 · WinAPI 开启");
  });

  it("initializes realtime assist options", () => {
    const state = buildInitialClientState(games);
    const assist = state.games[0].features[2];

    expect(assist.optionValues).toMatchObject({
      "实时辅助_自动拾取": true,
      "实时辅助_自动拾取_永远拾取": false,
      "实时辅助_S级鱼截图": true,
      "S级鱼截图保存目录": "screenshots/s_fish",
      "S级鱼截图冷却时间": "5"
    });
    expect(assist.configSummary).toBe("自动拾取 开启 · 永远拾取 关闭 · S级鱼截图 开启");
  });

  it("hides realtime assist dependent settings when their switches are disabled", () => {
    const state = buildInitialClientState(games);
    const withoutPickup = setFeatureOptionValue(state, "nte", "assist", "实时辅助_自动拾取", false);
    const withoutScreenshot = setFeatureOptionValue(withoutPickup, "nte", "assist", "实时辅助_S级鱼截图", false);
    const assist = withoutScreenshot.games[0].features[2];
    const visibleOptionKeys = getVisibleOptionKeys(
      assist.optionKeys ?? [],
      assistOptionDefinitions,
      assist.optionValues ?? {}
    );

    expect(visibleOptionKeys).not.toContain("实时辅助_自动拾取_永远拾取");
    expect(visibleOptionKeys).not.toContain("实时辅助_S级鱼截图_设置");
    expect(assist.configSummary).toBe("自动拾取 关闭 · 永远拾取 关闭 · S级鱼截图 关闭");
  });
});
