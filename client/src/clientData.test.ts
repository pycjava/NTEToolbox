import { describe, expect, it } from "vitest";

import { buildClientDataFromInterface, parseJsonc } from "./clientData";

const interfaceConfig = parseJsonc(`{
  "name": "NTEToolbox",
  "description": "异环工具箱",
  "controller": [
    { "name": "Win PostMessage (默认)", "type": "Win32" },
    { "name": "Win PostMessageWithWindowPos", "type": "Win32" },
    { "name": "ADB", "type": "Adb" }
  ],
  "task": [
    { "name": "全局设置", "entry": "全局设置", "option": ["全局设置"] },
    {
      "name": "钓鱼",
      "entry": "钓鱼",
      "option": ["钓鱼终止时间开关", "溜鱼设置", "卖鱼买换饵开关", "卖鱼买换饵设置"]
    },
    {
      "name": "弹钢琴 (键盘输入)",
      "entry": "弹钢琴_keybord",
      "option": ["弹钢琴_keybord_设置"]
    }
  ],
  "option": {
    "全局设置": {
      "type": "input",
      "inputs": [
        { "name": "debug_mode_switch", "label": "debug 模式开关", "pipeline_type": "int", "default": "0" }
      ]
    },
    "钓鱼终止时间开关": {
      "type": "switch",
      "label": "终止时间",
      "description": "启用后可选择钓鱼持续时长",
      "cases": [
        { "name": "Yes", "option": ["钓鱼终止时长"] },
        { "name": "No" }
      ],
      "default_case": "No"
    },
    "钓鱼终止时长": {
      "type": "select",
      "label": "钓鱼时长",
      "cases": [{ "name": "30分钟" }, { "name": "2小时" }],
      "default_case": "2小时"
    },
    "溜鱼设置": {
      "type": "input",
      "inputs": [
        { "name": "溜鱼_midpoint_pix_range", "label": "溜鱼中点停顿范围 (pix)", "pipeline_type": "int", "default": "5" }
      ]
    },
    "卖鱼买换饵开关": {
      "type": "switch",
      "label": "自动卖鱼买换饵",
      "cases": [{ "name": "Yes" }, { "name": "No" }],
      "default_case": "No"
    },
    "卖鱼买换饵设置": {
      "type": "input",
      "inputs": [
        { "name": "买饵次数", "label": "买饵次数", "pipeline_type": "int", "default": "4" }
      ]
    },
    "弹钢琴_keybord_设置": {
      "type": "input",
      "inputs": [
        { "name": "midi_path", "label": "MIDI 文件路径", "pipeline_type": "string" },
        { "name": "piano_mode", "label": "钢琴模式", "pipeline_type": "string", "default": "36" }
      ]
    }
  }
}`);

describe("client data adapter", () => {
  it("builds games, controllers, and options from interface config", () => {
    const data = buildClientDataFromInterface(interfaceConfig);

    expect(data.initialGames).toHaveLength(3);
    expect(data.initialGames[0]).toMatchObject({
      id: "nte",
      name: "异环 NTE",
      shortName: "异",
      status: "ready"
    });
    expect(data.initialGames[0].controller?.controllerTypes).toEqual([
      "Win PostMessage (默认)",
      "Win PostMessageWithWindowPos",
      "ADB"
    ]);
    expect(data.initialGames[0].controller?.controllerType).toBe("Win PostMessage (默认)");
    expect(data.initialGames[0].features.map((feature) => feature.name)).toEqual([
      "钓鱼",
      "弹钢琴 (键盘输入)"
    ]);
  });

  it("derives option definitions and defaults from interface options", () => {
    const data = buildClientDataFromInterface(interfaceConfig);
    const fish = data.initialGames[0].features[0];

    expect(data.globalSettingsOption.inputs[0]).toMatchObject({
      name: "debug_mode_switch",
      label: "debug 模式开关",
      pipelineType: "int",
      defaultValue: "0"
    });
    expect(data.nteOptions["钓鱼终止时间开关"]).toMatchObject({
      type: "switch",
      defaultValue: false,
      enabledOptionKeys: ["钓鱼终止时长"]
    });
    expect(data.nteOptions["钓鱼终止时长"]).toMatchObject({
      type: "select",
      defaultValue: "2小时",
      cases: ["30分钟", "2小时"]
    });
    expect(fish.optionValues).toMatchObject({
      "钓鱼终止时间开关": false,
      "钓鱼终止时长": "2小时",
      "溜鱼_midpoint_pix_range": "5",
      "卖鱼买换饵开关": false,
      "买饵次数": "4"
    });
  });

  it("parses jsonc comments before converting interface data", () => {
    const parsed = parseJsonc(`{
      // client config
      "name": "NTEToolbox",
      "description": "异环工具箱"
    }`);

    expect(parsed).toMatchObject({
      name: "NTEToolbox",
      description: "异环工具箱"
    });
  });
});
