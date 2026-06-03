export type GameStatus = "ready" | "placeholder";
export type RunState = "idle" | "starting" | "running" | "paused" | "stopping" | "completed" | "failed";

export type FeatureDefinition = {
  id: string;
  name: string;
  description: string;
  configSummary: string;
  runState?: RunState;
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

function withDefaultRunState(feature: FeatureDefinition): FeatureDefinition {
  return {
    ...feature,
    runState: feature.runState ?? "idle"
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
