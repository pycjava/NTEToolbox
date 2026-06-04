import type { GameDefinition, OptionDefinition } from "./clientModel";

export const globalSettingsOption: OptionDefinition = {
  key: "全局设置",
  type: "input",
  label: "全局设置",
  inputs: [
    {
      name: "debug_mode_switch",
      label: "debug 模式开关 (`1` 为开 `0` 为关)",
      pipelineType: "int",
      defaultValue: "0"
    },
    {
      name: "logging_switch",
      label: "日志开关 (`1` 为开 `0` 为关)",
      description: "关闭后 debug 目录不再写入 maafw 运行时日志。本阶段只保存客户端配置值",
      pipelineType: "int",
      defaultValue: "1"
    }
  ]
};

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
  },
  "弹钢琴_keybord_设置": {
    key: "弹钢琴_keybord_设置",
    type: "input",
    label: "弹钢琴设置",
    inputs: [
      {
        name: "midi_path",
        label: "MIDI 文件路径",
        pipelineType: "string",
        defaultValue: ""
      },
      {
        name: "bpm",
        label: "默认 BPM",
        pipelineType: "string",
        defaultValue: ""
      },
      {
        name: "piano_mode",
        label: "钢琴模式 (只能填 `21` 或 `36`)",
        pipelineType: "string",
        defaultValue: "36"
      },
      {
        name: "timeout_mode",
        label: "超时模式 (只能填 `同步时轴` 或 `速率不变`)",
        pipelineType: "string",
        defaultValue: "速率不变"
      },
      {
        name: "use_custom_winapi",
        label: "使用自定义的 WinAPI (`1` 为开 `0` 为关)",
        description: "使用自定义的 WinAPI 代替 maafw 的键盘输入 API，以解决输入延迟问题。会导致指针光标闪烁但不会抢占鼠标",
        pipelineType: "int",
        defaultValue: "1"
      }
    ]
  },
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
    description: "永远拾取，不判断画面内容。按住 F 时关闭自动拾取。适合粉爪等场景，仅在启用自动拾取时有效",
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
    label: "S级鱼截图设置",
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
