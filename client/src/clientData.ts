import type { GameDefinition } from "./clientModel";

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
        configSummary: "终止时间 2小时 · 自动买饵 关闭"
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
