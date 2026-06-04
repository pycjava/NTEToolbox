import type { GameDefinition, OptionDefinition } from "./clientModel";

export const nteOptions: Record<string, OptionDefinition> = {
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

export const initialGames: GameDefinition[] = [
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
        configSummary: "MIDI 未选择 · WinAPI 输入关闭"
      },
      {
        id: "assist",
        name: "实时辅助",
        description: "自动拾取、S 级鱼截图",
        configSummary: "自动拾取 关闭 · S级鱼截图 关闭"
      }
    ]
  },
  {
    id: "future-a",
    name: "预留游戏",
    shortName: "预",
    status: "placeholder",
    features: []
  },
  {
    id: "future-b",
    name: "更多游戏",
    shortName: "多",
    status: "placeholder",
    features: []
  }
];
