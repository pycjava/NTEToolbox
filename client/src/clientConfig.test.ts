import { describe, expect, it } from "vitest";

import { buildClientDataFromInterface, parseJsonc } from "./clientData";
import {
  buildInitialClientState,
  setFeatureOptionValues,
  setGlobalSettingsValues
} from "./clientModel";
import {
  applyPersistedClientConfig,
  buildPersistedClientConfig
} from "./clientConfig";

const interfaceConfig = parseJsonc(`{
  "name": "NTEToolbox",
  "description": "异环工具箱",
  "controller": [{ "name": "Win PostMessage (默认)", "type": "Win32" }],
  "task": [
    {
      "name": "钓鱼",
      "entry": "钓鱼",
      "option": [
        "钓鱼终止时间开关",
        "溜鱼设置",
        "卖鱼买换饵开关",
        "卖鱼买换饵设置",
        "钓鱼_S级鱼截图",
        "钓鱼_金色鱼截图",
        "钓鱼_鱼截图_设置"
      ]
    }
  ],
  "option": {
    "钓鱼终止时间开关": {
      "type": "switch",
      "cases": [
        {
          "name": "Yes",
          "option": ["钓鱼终止时长"],
          "pipeline_override": { "钓鱼": { "attach": { "终止时间开关": true } } }
        },
        {
          "name": "No",
          "pipeline_override": { "钓鱼": { "attach": { "终止时间开关": false } } }
        }
      ],
      "default_case": "No"
    },
    "钓鱼终止时长": {
      "type": "select",
      "cases": [
        { "name": "2小时", "pipeline_override": { "钓鱼": { "attach": { "终止时长": 120 } } } },
        { "name": "4小时", "pipeline_override": { "钓鱼": { "attach": { "终止时长": 240 } } } }
      ],
      "default_case": "2小时"
    },
    "溜鱼设置": {
      "type": "input",
      "inputs": [
        { "name": "溜鱼_midpoint_pix_range", "pipeline_type": "int", "default": "5" },
        { "name": "溜鱼_midpoint_sleep_time", "pipeline_type": "int", "default": "5" }
      ],
      "pipeline_override": {
        "钓鱼": {
          "attach": {
            "溜鱼_midpoint_pix_range": "{溜鱼_midpoint_pix_range}",
            "溜鱼_midpoint_sleep_time": "{溜鱼_midpoint_sleep_time}"
          }
        }
      }
    },
    "卖鱼买换饵开关": {
      "type": "switch",
      "cases": [
        { "name": "Yes", "pipeline_override": { "钓鱼": { "attach": { "卖鱼买换饵开关": true } } } },
        { "name": "No", "pipeline_override": { "钓鱼": { "attach": { "卖鱼买换饵开关": false } } } }
      ],
      "default_case": "No"
    },
    "卖鱼买换饵设置": {
      "type": "input",
      "inputs": [{ "name": "买饵次数", "pipeline_type": "int", "default": "4" }],
      "pipeline_override": { "钓鱼": { "attach": { "买饵次数": "{买饵次数}" } } }
    },
    "钓鱼_S级鱼截图": {
      "type": "switch",
      "cases": [
        {
          "name": "Yes",
          "pipeline_override": { "钓鱼": { "attach": { "S级鱼截图": true } } }
        },
        {
          "name": "No",
          "pipeline_override": { "钓鱼": { "attach": { "S级鱼截图": false } } }
        }
      ],
      "default_case": "Yes"
    },
    "钓鱼_金色鱼截图": {
      "type": "switch",
      "cases": [
        {
          "name": "Yes",
          "pipeline_override": { "钓鱼": { "attach": { "金色鱼截图": true } } }
        },
        {
          "name": "No",
          "pipeline_override": { "钓鱼": { "attach": { "金色鱼截图": false } } }
        }
      ],
      "default_case": "No"
    },
    "钓鱼_鱼截图_设置": {
      "type": "input",
      "inputs": [
        { "name": "鱼截图冷却时间", "pipeline_type": "int", "default": "5" }
      ],
      "pipeline_override": {
        "钓鱼": {
          "attach": {
            "鱼截图冷却时间": "{鱼截图冷却时间}"
          }
        }
      }
    }
  }
}`);

describe("client config persistence", () => {
  it("stores edited option values and resolved pipeline overrides", () => {
    const data = buildClientDataFromInterface(interfaceConfig);
    const state = setFeatureOptionValues(
      buildInitialClientState(data.initialGames),
      "nte",
      "fish",
      {
        "钓鱼终止时间开关": true,
        "钓鱼终止时长": "4小时",
        "溜鱼_midpoint_pix_range": "8",
        "溜鱼_midpoint_sleep_time": "12",
        "卖鱼买换饵开关": false,
        "买饵次数": "6",
        "钓鱼_S级鱼截图": true,
        "钓鱼_金色鱼截图": true,
        "鱼截图冷却时间": "7"
      }
    );

    expect(buildPersistedClientConfig(state, data.nteOptions)).toMatchObject({
      version: 1,
      games: {
        nte: {
          features: {
            fish: {
              optionValues: {
                "钓鱼终止时间开关": true,
                "钓鱼终止时长": "4小时",
                "溜鱼_midpoint_pix_range": "8",
                "溜鱼_midpoint_sleep_time": "12",
                "卖鱼买换饵开关": false,
                "买饵次数": "6",
                "钓鱼_S级鱼截图": true,
                "钓鱼_金色鱼截图": true,
                "鱼截图冷却时间": "7"
              },
              pipelineOverride: {
                "钓鱼": {
                  attach: {
                    "终止时间开关": true,
                    "终止时长": 240,
                    "溜鱼_midpoint_pix_range": 8,
                    "溜鱼_midpoint_sleep_time": 12,
                    "卖鱼买换饵开关": false,
                    "买饵次数": 6,
                    "S级鱼截图": true,
                    "金色鱼截图": true,
                    "鱼截图冷却时间": 7
                  }
                }
              }
            }
          }
        }
      }
    });
  });

  it("restores saved settings, controllers, and feature options", () => {
    const data = buildClientDataFromInterface(interfaceConfig);
    const baseState = buildInitialClientState(data.initialGames);
    const savedState = setFeatureOptionValues(
      setGlobalSettingsValues(baseState, { debug_mode_switch: "1" }),
      "nte",
      "fish",
      { "买饵次数": "9" }
    );
    const persisted = buildPersistedClientConfig(savedState, data.nteOptions);

    const restored = applyPersistedClientConfig(buildInitialClientState(data.initialGames), persisted);

    expect(restored.settingsValues.debug_mode_switch).toBe("1");
    expect(restored.games[0].features[0].optionValues?.["买饵次数"]).toBe("9");
    expect(restored.games[0].features[0].configSummary).toContain("买饵 9次");
  });

  it("drops stale screenshot save directory values and migrates cooldown values from saved configs", () => {
    const data = buildClientDataFromInterface(interfaceConfig);
    const persisted = buildPersistedClientConfig(buildInitialClientState(data.initialGames), data.nteOptions);
    persisted.games.nte.features.fish.optionValues["S级鱼截图保存目录"] = "captures";
    persisted.games.nte.features.fish.optionValues["S级鱼截图冷却时间"] = "8";
    delete persisted.games.nte.features.fish.optionValues["鱼截图冷却时间"];

    const restored = applyPersistedClientConfig(buildInitialClientState(data.initialGames), persisted);

    expect(restored.games[0].features[0].optionValues).not.toHaveProperty("S级鱼截图保存目录");
    expect(restored.games[0].features[0].optionValues).not.toHaveProperty("S级鱼截图冷却时间");
    expect(restored.games[0].features[0].optionValues?.["鱼截图冷却时间"]).toBe("8");
    expect(buildPersistedClientConfig(restored, data.nteOptions).games.nte.features.fish.optionValues).not.toHaveProperty(
      "S级鱼截图保存目录"
    );
    expect(buildPersistedClientConfig(restored, data.nteOptions).games.nte.features.fish.optionValues).not.toHaveProperty(
      "S级鱼截图冷却时间"
    );
  });
});
