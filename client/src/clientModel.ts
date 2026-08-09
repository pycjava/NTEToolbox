export type GameStatus = "ready";
/** 游戏的驱动方式：maa=走 MaaPiCli 任务（异环）；process=独立后端进程（炉石 hscoachd） */
export type GameKind = "maa" | "process";
export type RunState = "idle" | "starting" | "running" | "stopping" | "completed" | "failed";
export type OptionValue = boolean | string;
export type PipelineOverride = Record<string, unknown>;

/** 用户可选择的主题模式；system 跟随操作系统 prefers-color-scheme */
export type ThemeMode = "light" | "dark" | "system";

/** 解析后的实际主题（不含 system） */
export type ResolvedTheme = "light" | "dark";

export type OptionInputDefinition = {
  name: string;
  label: string;
  description?: string;
  pipelineType: "int" | "string";
  defaultValue: string;
};

export type SwitchOptionDefinition = {
  key: string;
  type: "switch";
  label: string;
  description?: string;
  defaultValue: boolean;
  enabledOptionKeys?: string[];
  pipelineOverridesByValue?: Partial<Record<"true" | "false", PipelineOverride>>;
};

export type SelectOptionDefinition = {
  key: string;
  type: "select";
  label: string;
  description?: string;
  defaultValue: string;
  cases: string[];
  pipelineOverridesByCase?: Record<string, PipelineOverride>;
};

export type InputOptionDefinition = {
  key: string;
  type: "input";
  label: string;
  description?: string;
  inputs: OptionInputDefinition[];
  pipelineOverride?: PipelineOverride;
};

export type OptionDefinition =
  | SwitchOptionDefinition
  | SelectOptionDefinition
  | InputOptionDefinition;

export type FeatureDefinition = {
  id: string;
  name: string;
  description: string;
  configSummary: string;
  runState?: RunState;
  optionKeys?: string[];
  optionValues?: Record<string, OptionValue>;
};

export type WindowInfo = {
  /** 窗口句柄（十进制字符串） */
  hwnd: string;
  /** 窗口标题 */
  title: string;
  /** 窗口类名 */
  className: string;
};

export type ControllerState = {
  /** 控制器类型，如 "Win PostMessageWithWindowPos" */
  controllerType: string;
  /** interface.jsonc 中声明的可选控制器类型 */
  controllerTypes?: string[];
  /** 当前选中的窗口标识（hwnd 十进制字符串） */
  targetWindow: string;
  /** 可选窗口列表 */
  availableWindows: WindowInfo[];
  /** 连接状态 */
  connected: boolean;
};

export type GameDefinition = {
  id: string;
  name: string;
  description?: string;
  shortName: string;
  icon?: string;
  status: GameStatus;
  /** 驱动方式：maa（MaaPiCli 任务）或 process（独立后端进程） */
  kind: GameKind;
  features: FeatureDefinition[];
  controller?: ControllerState;
};

export type ClientState = {
  selectedGameId: string;
  games: GameDefinition[];
  settingsValues: Record<string, OptionValue>;
  /** 主题模式，默认 "system" */
  theme: ThemeMode;
  /** 上次打开的游戏 id，用于启动时恢复选中（connected 仍需重选窗口） */
  lastOpenedGameId?: string;
  /** 管理员权限提示开关：未提权运行时提示一次 */
  adminPromptEnabled: boolean;
};

/**
 * 把 ThemeMode 解析成实际生效的浅/深主题。
 * 显式 light/dark 原样返回；system 查询 prefers-color-scheme。
 * 在无 window 环境（SSR / 纯 Node 测试）安全降级为 light。
 */
export function resolveTheme(theme: ThemeMode): ResolvedTheme {
  if (theme === "light" || theme === "dark") return theme;
  // 测试/SSR 环境无 window，降级浅色
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function buildFeatureConfigSummary(feature: FeatureDefinition): string {
  const values = { ...feature.optionValues };

  if (feature.id === "fish") {
    return buildFishingConfigSummary(values);
  }

  if (feature.id === "piano") {
    return buildPianoConfigSummary(values);
  }

  if (feature.id === "assist") {
    return buildAssistConfigSummary(values);
  }

  return feature.configSummary;
}

function buildFishingConfigSummary(values: Record<string, OptionValue>): string {
  const endTimeEnabled = values["钓鱼终止时间开关"] === true;
  const autoBaitEnabled = values["卖鱼买换饵开关"] === true;
  const sRankScreenshotEnabled = values["钓鱼_S级鱼截图"] === true;
  const goldenScreenshotEnabled = values["钓鱼_金色鱼截图"] === true;
  const duration = String(values["钓鱼终止时长"] ?? "2小时");
  const baitCount = String(values["买饵次数"] ?? "4");

  return [
    `终止时间 ${endTimeEnabled ? duration : "关闭"}`,
    `自动卖鱼买换饵 ${autoBaitEnabled ? "开启" : "关闭"}`,
    `买饵 ${baitCount}次`,
    `S级鱼截图 ${sRankScreenshotEnabled ? "开启" : "关闭"}`,
    `金色鱼截图 ${goldenScreenshotEnabled ? "开启" : "关闭"}`
  ].join(" · ");
}

function buildPianoConfigSummary(values: Record<string, OptionValue>): string {
  const midiPath = String(values.midi_path ?? "").trim();
  const midiName = midiPath ? (midiPath.split(/[\\/]/).filter(Boolean).pop() ?? midiPath) : "未选择";
  const pianoMode = String(values.piano_mode ?? "36");
  const winApiEnabled = values.use_custom_winapi === "1";

  return [
    `MIDI ${midiName}`,
    `模式 ${pianoMode}键`,
    `WinAPI ${winApiEnabled ? "开启" : "关闭"}`
  ].join(" · ");
}

function buildAssistConfigSummary(values: Record<string, OptionValue>): string {
  const autoPickupEnabled = values["实时辅助_自动拾取"] === true;
  const alwaysPickupEnabled = autoPickupEnabled && values["实时辅助_自动拾取_永远拾取"] === true;

  return [
    `自动拾取 ${autoPickupEnabled ? "开启" : "关闭"}`,
    `永远拾取 ${alwaysPickupEnabled ? "开启" : "关闭"}`
  ].join(" · ");
}

function withDefaultRunState(feature: FeatureDefinition): FeatureDefinition {
  const normalizedFeature = {
    ...feature,
    optionValues: { ...(feature.optionValues ?? {}) },
    runState: feature.runState ?? "idle"
  };

  return {
    ...normalizedFeature,
    configSummary: buildFeatureConfigSummary(normalizedFeature)
  };
}

function cloneGames(games: GameDefinition[]): GameDefinition[] {
  return games.map((game) => ({
    ...game,
    features: game.features.map(withDefaultRunState)
  }));
}

export function buildInitialClientState(
  games: GameDefinition[],
  settingsValues: Record<string, OptionValue> = {},
  overrides: { theme?: ThemeMode; lastOpenedGameId?: string; adminPromptEnabled?: boolean } = {}
): ClientState {
  const clonedGames = cloneGames(games);
  const initialSelectedId = overrides.lastOpenedGameId && clonedGames.some((g) => g.id === overrides.lastOpenedGameId)
    ? overrides.lastOpenedGameId
    : clonedGames[0]?.id ?? "";

  return {
    selectedGameId: initialSelectedId,
    games: clonedGames,
    settingsValues: { ...settingsValues },
    theme: overrides.theme ?? "system",
    // 初始即记录当前选中游戏，保证持久化总有 lastOpenedGameId
    lastOpenedGameId: initialSelectedId || undefined,
    adminPromptEnabled: overrides.adminPromptEnabled ?? true
  };
}

export function selectGame(state: ClientState, gameId: string): ClientState {
  const exists = state.games.some((game) => game.id === gameId);

  if (!exists) return state;

  return {
    ...state,
    selectedGameId: gameId,
    lastOpenedGameId: gameId
  };
}

export function setGlobalSettingsValues(
  state: ClientState,
  values: Record<string, OptionValue>
): ClientState {
  return {
    ...state,
    settingsValues: {
      ...state.settingsValues,
      ...values
    }
  };
}

export function setTheme(state: ClientState, theme: ThemeMode): ClientState {
  return { ...state, theme };
}

export function setAdminPromptEnabled(state: ClientState, enabled: boolean): ClientState {
  return { ...state, adminPromptEnabled: enabled };
}

export function setControllerType(
  state: ClientState,
  gameId: string,
  controllerType: string
): ClientState {
  return {
    ...state,
    games: state.games.map((game) =>
      game.id !== gameId || !game.controller
        ? game
        : {
            ...game,
            controller: { ...game.controller, controllerType, connected: false, targetWindow: "" }
          }
    )
  };
}

export function setTargetWindow(
  state: ClientState,
  gameId: string,
  targetWindow: string
): ClientState {
  return {
    ...state,
    games: state.games.map((game) =>
      game.id !== gameId || !game.controller
        ? game
        : {
            ...game,
            controller: {
              ...game.controller,
              targetWindow,
              connected: targetWindow !== ""
            }
          }
    )
  };
}

export function refreshWindows(
  state: ClientState,
  gameId: string,
  windows: WindowInfo[]
): ClientState {
  return {
    ...state,
    games: state.games.map((game) =>
      game.id !== gameId || !game.controller
        ? game
        : {
            ...game,
            controller: {
              ...game.controller,
              availableWindows: windows,
              targetWindow: "",
              connected: false
            }
          }
    )
  };
}

export function addGame(state: ClientState, game: GameDefinition): ClientState {
  const normalizedGame: GameDefinition = {
    ...game,
    features: game.features.map(withDefaultRunState)
  };

  return {
    ...state,
    selectedGameId: normalizedGame.id,
    games: [...state.games.filter((current) => current.id !== normalizedGame.id), normalizedGame]
  };
}

export function setFeatureConfig(
  state: ClientState,
  gameId: string,
  featureId: string,
  configSummary: string
): ClientState {
  return {
    ...state,
    games: state.games.map((game) =>
      game.id !== gameId
        ? game
        : {
            ...game,
            features: game.features.map((feature) =>
              feature.id === featureId ? { ...feature, configSummary } : feature
            )
          }
    )
  };
}

export function setFeatureOptionValue(
  state: ClientState,
  gameId: string,
  featureId: string,
  optionName: string,
  value: OptionValue
): ClientState {
  return setFeatureOptionValues(state, gameId, featureId, { [optionName]: value });
}

export function setFeatureOptionValues(
  state: ClientState,
  gameId: string,
  featureId: string,
  values: Record<string, OptionValue>
): ClientState {
  return {
    ...state,
    games: state.games.map((game) =>
      game.id !== gameId
        ? game
        : {
            ...game,
            features: game.features.map((feature) => {
              if (feature.id !== featureId) return feature;

              const nextFeature = {
                ...feature,
                optionValues: {
                  ...(feature.optionValues ?? {}),
                  ...values
                }
              };

              return {
                ...nextFeature,
                configSummary: buildFeatureConfigSummary(nextFeature)
              };
            })
          }
    )
  };
}

export function setFeatureRunState(
  state: ClientState,
  gameId: string,
  featureId: string,
  runState: RunState
): ClientState {
  return {
    ...state,
    games: state.games.map((game) =>
      game.id !== gameId
        ? game
        : {
            ...game,
            features: game.features.map((feature) => ({
              ...feature,
              runState: feature.id === featureId ? runState : "idle"
            }))
          }
    )
  };
}

export function getVisibleOptionKeys(
  optionKeys: string[],
  optionDefinitions: Record<string, OptionDefinition>,
  optionValues: Record<string, OptionValue>
): string[] {
  const visibleOptionKeys: string[] = [];

  for (const optionKey of optionKeys) {
    const optionDefinition = optionDefinitions[optionKey];
    if (!optionDefinition) continue;

    visibleOptionKeys.push(optionKey);

    if (
      optionDefinition.type === "switch" &&
      optionValues[optionKey] === true &&
      optionDefinition.enabledOptionKeys
    ) {
      visibleOptionKeys.push(...optionDefinition.enabledOptionKeys);
    }
  }

  return visibleOptionKeys;
}
