export type GameStatus = "ready" | "placeholder";
export type RunState = "idle" | "starting" | "running" | "paused" | "stopping" | "completed" | "failed";
export type OptionValue = boolean | string;

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
};

export type SelectOptionDefinition = {
  key: string;
  type: "select";
  label: string;
  description?: string;
  defaultValue: string;
  cases: string[];
};

export type InputOptionDefinition = {
  key: string;
  type: "input";
  label: string;
  description?: string;
  inputs: OptionInputDefinition[];
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

export type GameDefinition = {
  id: string;
  name: string;
  shortName: string;
  status: GameStatus;
  features: FeatureDefinition[];
};

export type ClientState = {
  selectedGameId: string;
  games: GameDefinition[];
};

const fishingDefaultValues: Record<string, OptionValue> = {
  "钓鱼终止时间开关": true,
  "钓鱼终止时长": "2小时",
  "溜鱼_midpoint_pix_range": "5",
  "溜鱼_midpoint_sleep_time": "5",
  "卖鱼买换饵开关": true,
  "买饵次数": "4"
};

export function buildFeatureConfigSummary(feature: FeatureDefinition): string {
  if (feature.id !== "fish") return feature.configSummary;

  const values = { ...fishingDefaultValues, ...feature.optionValues };
  const endTimeEnabled = values["钓鱼终止时间开关"] === true;
  const autoBaitEnabled = values["卖鱼买换饵开关"] === true;
  const duration = String(values["钓鱼终止时长"] ?? "2小时");
  const baitCount = String(values["买饵次数"] ?? "4");

  return [
    `终止时间 ${endTimeEnabled ? duration : "关闭"}`,
    `自动卖鱼买换饵 ${autoBaitEnabled ? "开启" : "关闭"}`,
    `买饵 ${baitCount}次`
  ].join(" · ");
}

function withDefaultRunState(feature: FeatureDefinition): FeatureDefinition {
  const optionValues =
    feature.id === "fish"
      ? { ...fishingDefaultValues, ...feature.optionValues }
      : feature.optionValues;
  const normalizedFeature = {
    ...feature,
    optionValues,
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

export function buildInitialClientState(games: GameDefinition[]): ClientState {
  const clonedGames = cloneGames(games);

  return {
    selectedGameId: clonedGames[0]?.id ?? "",
    games: clonedGames
  };
}

export function selectGame(state: ClientState, gameId: string): ClientState {
  const exists = state.games.some((game) => game.id === gameId);

  return {
    ...state,
    selectedGameId: exists ? gameId : state.selectedGameId
  };
}

export function addGame(state: ClientState, game: GameDefinition): ClientState {
  const normalizedGame: GameDefinition = {
    ...game,
    features: game.features.map(withDefaultRunState)
  };

  return {
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
