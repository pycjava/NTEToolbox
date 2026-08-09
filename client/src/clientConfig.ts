import {
  buildFeatureConfigSummary,
  type ClientState,
  type InputOptionDefinition,
  type OptionDefinition,
  type OptionValue,
  type PipelineOverride
} from "./clientModel";

export type PersistedFeatureConfig = {
  optionValues: Record<string, OptionValue>;
  pipelineOverride: PipelineOverride;
};

export type PersistedClientConfig = {
  version: 1;
  settingsValues: Record<string, OptionValue>;
  /** 外观/主题设置（向后兼容：旧配置无此字段） */
  appearance?: {
    theme: "light" | "dark" | "system";
  };
  /** 上次打开的游戏 id */
  lastOpenedGameId?: string;
  /** 管理员权限提示开关：未提权运行时提示一次 */
  adminPromptEnabled?: boolean;
  games: Record<string, {
    controller?: {
      controllerType: string;
      targetWindow: string;
    };
    features: Record<string, PersistedFeatureConfig>;
  }>;
};

export function buildPersistedClientConfig(
  state: ClientState,
  optionDefinitions: Record<string, OptionDefinition>
): PersistedClientConfig {
  return {
    version: 1,
    settingsValues: { ...state.settingsValues },
    appearance: { theme: state.theme ?? "system" },
    lastOpenedGameId: state.lastOpenedGameId,
    adminPromptEnabled: state.adminPromptEnabled ?? true,
    games: Object.fromEntries(
      state.games.map((game) => [
        game.id,
        {
          controller: game.controller
            ? {
                controllerType: game.controller.controllerType,
                targetWindow: game.controller.targetWindow
              }
            : undefined,
          features: Object.fromEntries(
            game.features.map((feature) => {
              const optionValues = { ...(feature.optionValues ?? {}) };

              return [
                feature.id,
                {
                  optionValues,
                  pipelineOverride: buildFeaturePipelineOverride(
                    feature.optionKeys ?? [],
                    optionValues,
                    optionDefinitions
                  )
                }
              ];
            })
          )
        }
      ])
    )
  };
}

export function applyPersistedClientConfig(
  state: ClientState,
  config: PersistedClientConfig | null | undefined
): ClientState {
  if (!config) return state;

  const theme = config.appearance?.theme ?? "system";
  const lastOpenedGameId = config.lastOpenedGameId && state.games.some((g) => g.id === config.lastOpenedGameId)
    ? config.lastOpenedGameId
    : state.lastOpenedGameId;
  // selectedGameId 优先恢复到上次打开的游戏（仍保持 connected:false）
  const restoredSelectedId = lastOpenedGameId && state.games.some((g) => g.id === lastOpenedGameId)
    ? lastOpenedGameId
    : state.selectedGameId;

  return {
    ...state,
    selectedGameId: restoredSelectedId,
    theme,
    lastOpenedGameId,
    adminPromptEnabled: config.adminPromptEnabled ?? true,
    settingsValues: {
      ...state.settingsValues,
      ...(config.settingsValues ?? {})
    },
    games: state.games.map((game) => {
      const savedGame = config.games?.[game.id];
      if (!savedGame) return game;

      return {
        ...game,
        controller: game.controller
          ? {
              ...game.controller,
              controllerType: savedGame.controller?.controllerType ?? game.controller.controllerType,
              targetWindow: savedGame.controller?.targetWindow ?? game.controller.targetWindow,
              // 启动时一律视为未连接：旧的 targetWindow 可能让对应窗口已不存在，
              // 真正的连接需要用户重新选择窗口后建立。
              connected: false
            }
          : game.controller,
        features: game.features.map((feature) => {
          const savedFeature = savedGame.features?.[feature.id];
          if (!savedFeature) return feature;
          const savedOptionValues = omitStaleOptionValues(savedFeature.optionValues ?? {});

          const nextFeature = {
            ...feature,
            optionValues: {
              ...(feature.optionValues ?? {}),
              ...savedOptionValues
            }
          };

          return {
            ...nextFeature,
            configSummary: buildFeatureConfigSummary(nextFeature)
          };
        })
      };
    })
  };
}

function omitStaleOptionValues(optionValues: Record<string, OptionValue>): Record<string, OptionValue> {
  const nextOptionValues = { ...optionValues };
  if (
    nextOptionValues["鱼截图冷却时间"] === undefined &&
    nextOptionValues["S级鱼截图冷却时间"] !== undefined
  ) {
    nextOptionValues["鱼截图冷却时间"] = nextOptionValues["S级鱼截图冷却时间"];
  }
  delete nextOptionValues["S级鱼截图保存目录"];
  delete nextOptionValues["S级鱼截图冷却时间"];
  return nextOptionValues;
}

export function buildFeaturePipelineOverride(
  optionKeys: string[],
  optionValues: Record<string, OptionValue>,
  optionDefinitions: Record<string, OptionDefinition>
): PipelineOverride {
  let result: PipelineOverride = {};
  const visited = new Set<string>();

  function visit(optionKey: string) {
    if (visited.has(optionKey)) return;
    visited.add(optionKey);

    const optionDefinition = optionDefinitions[optionKey];
    if (!optionDefinition) return;

    if (optionDefinition.type === "switch") {
      const value = optionValues[optionKey] === true;
      result = deepMerge(
        result,
        resolvePipelineOverride(optionDefinition.pipelineOverridesByValue?.[String(value) as "true" | "false"], optionValues, optionDefinitions)
      );

      if (value) {
        for (const childOptionKey of optionDefinition.enabledOptionKeys ?? []) {
          visit(childOptionKey);
        }
      }
      return;
    }

    if (optionDefinition.type === "select") {
      const value = String(optionValues[optionKey] ?? optionDefinition.defaultValue);
      result = deepMerge(
        result,
        resolvePipelineOverride(optionDefinition.pipelineOverridesByCase?.[value], optionValues, optionDefinitions)
      );
      return;
    }

    result = deepMerge(
      result,
      resolvePipelineOverride(optionDefinition.pipelineOverride, optionValues, optionDefinitions, optionDefinition)
    );
  }

  for (const optionKey of optionKeys) {
    visit(optionKey);
  }

  return result;
}

function resolvePipelineOverride(
  pipelineOverride: PipelineOverride | undefined,
  optionValues: Record<string, OptionValue>,
  optionDefinitions: Record<string, OptionDefinition>,
  inputOption?: InputOptionDefinition
): PipelineOverride {
  if (!pipelineOverride) return {};

  return replaceTemplateValues(pipelineOverride, optionValues, optionDefinitions, inputOption) as PipelineOverride;
}

function replaceTemplateValues(
  value: unknown,
  optionValues: Record<string, OptionValue>,
  optionDefinitions: Record<string, OptionDefinition>,
  inputOption?: InputOptionDefinition
): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => replaceTemplateValues(item, optionValues, optionDefinitions, inputOption));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        replaceTemplateValues(child, optionValues, optionDefinitions, inputOption)
      ])
    );
  }

  if (typeof value !== "string") return value;

  const exactMatch = value.match(/^\{(.+)\}$/);
  if (exactMatch) {
    return coerceOptionValue(
      exactMatch[1],
      optionValues[exactMatch[1]] ?? "",
      optionDefinitions,
      inputOption
    );
  }

  return value.replace(/\{([^}]+)\}/g, (_, key: string) =>
    String(optionValues[key] ?? "")
  );
}

function coerceOptionValue(
  key: string,
  value: OptionValue,
  optionDefinitions: Record<string, OptionDefinition>,
  inputOption?: InputOptionDefinition
): OptionValue | number {
  const inputDefinition = inputOption?.inputs.find((input) => input.name === key) ?? findInputDefinition(key, optionDefinitions);
  if (inputDefinition?.pipelineType !== "int") return value;

  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : 0;
}

function findInputDefinition(
  key: string,
  optionDefinitions: Record<string, OptionDefinition>
) {
  for (const optionDefinition of Object.values(optionDefinitions)) {
    if (optionDefinition.type !== "input") continue;
    const inputDefinition = optionDefinition.inputs.find((input) => input.name === key);
    if (inputDefinition) return inputDefinition;
  }

  return undefined;
}

function deepMerge(target: PipelineOverride, source: PipelineOverride): PipelineOverride {
  const result = { ...target };

  for (const [key, value] of Object.entries(source)) {
    const currentValue = result[key];

    if (isPlainObject(currentValue) && isPlainObject(value)) {
      result[key] = deepMerge(currentValue as PipelineOverride, value as PipelineOverride);
    } else {
      result[key] = value;
    }
  }

  return result;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
