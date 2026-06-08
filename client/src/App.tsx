import React, { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import {
  CheckCircle2,
  Fish,
  Gamepad2,
  Monitor,
  Music2,
  Pencil,
  Play,
  HelpCircle,
  RefreshCw,
  Settings,
  Sparkles,
  Square,
  Upload
} from "lucide-react";

import {
  globalSettingsDefaultValues,
  globalSettingsOption,
  initialGames,
  nteOptions
} from "./clientData";
import {
  applyPersistedClientConfig,
  buildPersistedClientConfig,
  type PersistedClientConfig
} from "./clientConfig";
import {
  buildInitialClientState,
  getVisibleOptionKeys,
  refreshWindows,
  selectGame,
  setControllerType,
  setFeatureOptionValues,
  setFeatureRunState,
  setGlobalSettingsValues,
  setTargetWindow,
  type ClientState,
  type ControllerState,
  type FeatureDefinition,
  type GameDefinition,
  type InputOptionDefinition,
  type OptionDefinition,
  type OptionValue,
  type SelectOptionDefinition,
  type SwitchOptionDefinition,
  type RunState,
  type WindowInfo
} from "./clientModel";

type DialogFeature = {
  gameId: string;
  feature: FeatureDefinition;
};

type MaaTaskRunResponse = {
  runState?: RunState;
};

type MaaTaskStatusUpdate = {
  gameId: string;
  featureId: string;
  runState: RunState;
  exitCode?: number | null;
};

const DEFAULT_RESOURCE_NAME = "默认";
const MAA_TASK_STATUS_POLL_INTERVAL_MS = 1_000;
const runningStates = new Set<RunState>(["starting", "running", "stopping"]);

function getFeatureIcon(featureId: string) {
  if (featureId === "fish") return Fish;
  if (featureId === "piano") return Music2;
  if (featureId === "assist") return Sparkles;
  return Gamepad2;
}

function getRunLabel(runState: RunState | undefined) {
  switch (runState) {
    case "starting":
      return "启动中";
    case "running":
      return "运行中";
    case "stopping":
      return "结束中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return "就绪";
  }
}

function getGameSubtitle(game: GameDefinition) {
  if (game.description) return game.description;
  if (game.features.length === 0) return "未导入功能";
  return game.features.map((feature) => feature.name).join(" / ");
}

function App() {
  const [state, setState] = useState<ClientState>(() =>
    buildInitialClientState(initialGames, globalSettingsDefaultValues)
  );
  const [configTarget, setConfigTarget] = useState<DialogFeature | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [activeView, setActiveView] = useState<"features" | "live">("features");
  const stateRef = useRef(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    let cancelled = false;

    invoke<PersistedClientConfig | null>("load_client_config")
      .then((config) => {
        if (cancelled || !config) return;
        setState((current) => applyPersistedClientConfig(current, config));
      })
      .catch((error) => {
        console.error("Failed to load client config", error);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const pollTaskStates = async () => {
      try {
        const updates = (await invoke<MaaTaskStatusUpdate[] | null>("poll_maa_task_states")) ?? [];
        if (cancelled || updates.length === 0) return;

        setState((current) =>
          updates.reduce(
            (nextState, update) =>
              setFeatureRunState(nextState, update.gameId, update.featureId, update.runState),
            current
          )
        );
      } catch (error) {
        console.error("Failed to poll Maa task states", error);
      }
    };

    void pollTaskStates();
    const timer = window.setInterval(() => {
      void pollTaskStates();
    }, MAA_TASK_STATUS_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const selectedGame = useMemo(
    () => state.games.find((game) => game.id === state.selectedGameId) ?? state.games[0],
    [state.games, state.selectedGameId]
  );

  function handleSelectGame(gameId: string) {
    setState((current) => selectGame(current, gameId));
  }

  function handleSaveFeatureConfig(gameId: string, featureId: string, values: Record<string, OptionValue>) {
    let nextState: ClientState | null = null;
    setState((current) => {
      nextState = setFeatureOptionValues(current, gameId, featureId, values);
      return nextState;
    });
    setConfigTarget(null);
    persistClientConfig(nextState ?? stateRef.current);
  }

  function handleRunChange(gameId: string, featureId: string, runState: RunState) {
    const currentState = stateRef.current;
    const game = currentState.games.find((candidate) => candidate.id === gameId);
    const feature = game?.features.find((candidate) => candidate.id === featureId);

    if (!game || !feature) return;

    if (runState === "running") {
      setState((current) => setFeatureRunState(current, gameId, featureId, "running"));
      void invoke<MaaTaskRunResponse>("start_maa_task", {
        request: {
          gameId,
          featureId,
          taskName: feature.name,
          controllerName: game.controller?.controllerType ?? "",
          targetWindow: game.controller?.targetWindow ?? "",
          resourceName: DEFAULT_RESOURCE_NAME,
          optionKeys: feature.optionKeys ?? [],
          optionValues: feature.optionValues ?? {},
          optionDefinitions: nteOptions,
          globalOptionKey: globalSettingsOption.key,
          globalSettingsValues: currentState.settingsValues
        }
      })
        .then((response) => {
          const nextRunState = response?.runState ?? "running";
          setState((current) => setFeatureRunState(current, gameId, featureId, nextRunState));
        })
        .catch((error) => {
          console.error("Failed to start Maa task", error);
          setState((current) => setFeatureRunState(current, gameId, featureId, "failed"));
        });
      return;
    }

    if (runState === "idle") {
      setState((current) => setFeatureRunState(current, gameId, featureId, "stopping"));
      void invoke<MaaTaskRunResponse>("stop_maa_task", { gameId, featureId })
        .then((response) => {
          setState((current) => setFeatureRunState(current, gameId, featureId, response?.runState ?? "idle"));
        })
        .catch((error) => {
          console.error("Failed to stop Maa task", error);
          setState((current) => setFeatureRunState(current, gameId, featureId, "failed"));
        });
      return;
    }

    setState((current) => setFeatureRunState(current, gameId, featureId, runState));
  }

  function handleSaveSettings(values: Record<string, OptionValue>) {
    let nextState: ClientState | null = null;
    setState((current) => {
      nextState = setGlobalSettingsValues(current, values);
      return nextState;
    });
    setIsSettingsOpen(false);
    persistClientConfig(nextState ?? stateRef.current);
  }

  function handleControllerTypeChange(gameId: string, controllerType: string) {
    setState((current) => setControllerType(current, gameId, controllerType));
  }

  function handleTargetWindowChange(gameId: string, targetWindow: string) {
    let nextState: ClientState | null = null;
    setState((current) => {
      nextState = setTargetWindow(current, gameId, targetWindow);
      return nextState;
    });
    persistClientConfig(nextState ?? stateRef.current);
  }

  function handleRefreshWindows(gameId: string) {
    invoke<WindowInfo[]>("enumerate_windows")
      .then((windows) => {
        setState((current) => refreshWindows(current, gameId, windows));
      })
      .catch((error) => {
        console.error("Failed to enumerate windows", error);
        setState((current) => refreshWindows(current, gameId, []));
      });
  }

  function persistClientConfig(nextState: ClientState) {
    stateRef.current = nextState;
    void invoke("save_client_config", {
      config: buildPersistedClientConfig(nextState, nteOptions)
    }).catch((error) => {
      console.error("Failed to save client config", error);
    });
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <img src="/nte-icon.png" alt="" />
          </div>
          <div>
            <h1>MaaToolbox</h1>
            <p>{selectedGame ? getGameSubtitle(selectedGame) : "未选择"}</p>
          </div>
        </div>

        <div className="top-actions">
          <button className="icon-button" type="button" aria-label="设置" title="设置" onClick={() => setIsSettingsOpen(true)}>
            <Settings size={20} />
          </button>
          <button className="icon-button" type="button" aria-label="检查更新" title="检查更新">
            <Upload size={20} />
          </button>
        </div>

        <GameSwitcher
          games={state.games}
          selectedGameId={state.selectedGameId}
          onSelectGame={handleSelectGame}
        />
      </header>

      {selectedGame ? (
        <section className="content-panel" aria-label={`${selectedGame.name} 功能`}>
          <div className="game-heading">
            <div>
              <p className="eyebrow">当前游戏</p>
              <h2>{selectedGame.name}</h2>
            </div>
            <span className={`status-pill status-${selectedGame.status}`}>
              <CheckCircle2 size={16} />
              {selectedGame.status === "ready" ? "已安装" : "预留"}
            </span>
          </div>

          {selectedGame.controller ? (
            <ConnectionBar
              gameId={selectedGame.id}
              controller={selectedGame.controller}
              onControllerTypeChange={handleControllerTypeChange}
              onTargetWindowChange={handleTargetWindowChange}
              onRefreshWindows={handleRefreshWindows}
            />
          ) : null}

          <ViewToggle activeView={activeView} onViewChange={setActiveView} />

          {activeView === "features" ? (
            <FeatureList
              game={selectedGame}
              onConfigure={(feature) => setConfigTarget({ gameId: selectedGame.id, feature })}
              onRunChange={handleRunChange}
            />
          ) : (
            <LiveViewPanel
              targetWindow={selectedGame.controller?.targetWindow ?? ""}
              connected={selectedGame.controller?.connected ?? false}
            />
          )}
        </section>
      ) : (
        <EmptyState title="尚未添加游戏" />
      )}

      {configTarget ? (
        <FeatureConfigDialog
          optionDefinitions={nteOptions}
          target={configTarget}
          onClose={() => setConfigTarget(null)}
          onSave={handleSaveFeatureConfig}
        />
      ) : null}

      {isSettingsOpen ? (
        <SettingsDialog
          settingsValues={state.settingsValues}
          onClose={() => setIsSettingsOpen(false)}
          onSave={handleSaveSettings}
        />
      ) : null}
    </main>
  );
}

type ConnectionBarProps = {
  gameId: string;
  controller: ControllerState;
  onControllerTypeChange: (gameId: string, controllerType: string) => void;
  onTargetWindowChange: (gameId: string, targetWindow: string) => void;
  onRefreshWindows: (gameId: string) => void;
};

function ConnectionBar({ gameId, controller, onControllerTypeChange, onTargetWindowChange, onRefreshWindows }: ConnectionBarProps) {
  const controllerTypes = controller.controllerTypes?.length ? controller.controllerTypes : [controller.controllerType];

  return (
    <div className="connection-bar">
      <div className="connection-row">
        <span className="connection-label">控制器类型</span>
        <select
          value={controller.controllerType}
          onChange={(event) => onControllerTypeChange(gameId, event.target.value)}
        >
          {controllerTypes.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
      </div>
      <div className="connection-row">
        <span className="connection-label">目标窗口</span>
        <div className="connection-control">
          <select
            value={controller.targetWindow}
            onChange={(event) => onTargetWindowChange(gameId, event.target.value)}
          >
            <option value="">请选择窗口</option>
            {controller.availableWindows.map((win) => (
              <option key={win.hwnd} value={win.hwnd}>{win.title} ({win.className})</option>
            ))}
          </select>
          <button className="icon-button" type="button" aria-label="刷新窗口列表" title="刷新窗口列表" onClick={() => onRefreshWindows(gameId)}>
            <RefreshCw size={18} />
          </button>
        </div>
      </div>
      <div className="connection-status">
        <span className={`status-dot ${controller.connected ? "connected" : ""}`} />
        <span className="status-text">{controller.connected ? "已连接" : "未连接"}</span>
      </div>
    </div>
  );
}

type GameSwitcherProps = {
  games: GameDefinition[];
  selectedGameId: string;
  onSelectGame: (gameId: string) => void;
};

function GameSwitcher({ games, selectedGameId, onSelectGame }: GameSwitcherProps) {
  return (
    <nav className="game-switcher" aria-label="游戏选择">
      {games.map((game) => (
        <button
          className={`game-icon ${game.id === selectedGameId ? "selected" : ""}`}
          key={game.id}
          type="button"
          aria-label={game.name}
          title={game.name}
          onClick={() => { onSelectGame(game.id); }}
        >
          <span>{game.icon ? <img src={game.icon} alt={game.name} /> : game.shortName}</span>
        </button>
      ))}
    </nav>
  );
}

type FeatureListProps = {
  game: GameDefinition;
  onConfigure: (feature: FeatureDefinition) => void;
  onRunChange: (gameId: string, featureId: string, runState: RunState) => void;
};

function FeatureList({ game, onConfigure, onRunChange }: FeatureListProps) {
  if (game.features.length === 0) {
    return <EmptyState title="没有可用功能" />;
  }

  return (
    <div className="feature-list">
      {game.features.map((feature) => (
        <FeatureRow
          feature={feature}
          gameId={game.id}
          key={feature.id}
          onConfigure={onConfigure}
          onRunChange={onRunChange}
        />
      ))}
    </div>
  );
}

type FeatureRowProps = {
  feature: FeatureDefinition;
  gameId: string;
  onConfigure: (feature: FeatureDefinition) => void;
  onRunChange: (gameId: string, featureId: string, runState: RunState) => void;
};

function FeatureRow({ feature, gameId, onConfigure, onRunChange }: FeatureRowProps) {
  const Icon = getFeatureIcon(feature.id);
  const currentRunState = feature.runState ?? "idle";
  const isRunning = runningStates.has(currentRunState);

  return (
    <article className={`feature-row ${isRunning ? "running" : ""}`} aria-label={`${feature.name} 功能行`}>
      <div className="drag-handle" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="feature-icon" aria-hidden="true">
        <Icon size={24} />
      </div>
      <div className="feature-copy">
        <div className="feature-title-line">
          <h3>{feature.name}</h3>
          <span className={`run-badge run-${currentRunState}`} aria-live="polite">{getRunLabel(currentRunState)}</span>
        </div>
        <p>{feature.description}</p>
        <p className="feature-summary">{feature.configSummary}</p>
      </div>
      <div className="feature-actions">
        {isRunning ? (
          <button className="secondary-action danger" type="button" onClick={() => onRunChange(gameId, feature.id, "idle")}>
            <Square size={16} />
            结束任务
          </button>
        ) : (
          <button className="primary-action" type="button" onClick={() => onRunChange(gameId, feature.id, "running")}>
            <Play size={17} />
            启动
          </button>
        )}
        <button className="row-icon-button" type="button" aria-label={`编辑${feature.name}`} title="编辑" onClick={() => onConfigure(feature)}>
          <Pencil size={19} />
        </button>
      </div>
    </article>
  );
}

type FeatureConfigDialogProps = {
  optionDefinitions: Record<string, OptionDefinition>;
  target: DialogFeature;
  onClose: () => void;
  onSave: (gameId: string, featureId: string, values: Record<string, OptionValue>) => void;
};

function FeatureConfigDialog({ optionDefinitions, target, onClose, onSave }: FeatureConfigDialogProps) {
  const [values, setValues] = useState<Record<string, OptionValue>>(() => ({ ...(target.feature.optionValues ?? {}) }));
  const visibleOptionKeys = getVisibleOptionKeys(target.feature.optionKeys ?? [], optionDefinitions, values);

  function updateValue(name: string, value: OptionValue) {
    setValues((current) => ({
      ...current,
      [name]: value
    }));
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="feature-config-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">功能配置</p>
            <h2 id="feature-config-title">{target.feature.name}</h2>
          </div>
          <button className="row-icon-button" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>

        {visibleOptionKeys.length > 0 ? (
          <div className="config-grid">
            {visibleOptionKeys.map((optionKey) => {
              const optionDefinition = optionDefinitions[optionKey];
              if (!optionDefinition) return null;

              return (
                <OptionField
                  key={optionKey}
                  option={optionDefinition}
                  values={values}
                  onChange={updateValue}
                />
              );
            })}
          </div>
        ) : (
          <div className="empty-config">这个功能暂时没有可配置项。</div>
        )}

        <div className="modal-actions">
          <button className="secondary-action" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-action" type="button" onClick={() => onSave(target.gameId, target.feature.id, values)}>
            保存
          </button>
        </div>
      </section>
    </div>
  );
}

type OptionFieldProps = {
  option: OptionDefinition;
  values: Record<string, OptionValue>;
  onChange: (name: string, value: OptionValue) => void;
};

function OptionField({ option, values, onChange }: OptionFieldProps) {
  if (option.type === "switch") {
    return <SwitchOption option={option} value={values[option.key] === true} onChange={onChange} />;
  }

  if (option.type === "select") {
    return <SelectOption option={option} value={String(values[option.key] ?? option.defaultValue)} onChange={onChange} />;
  }

  return <InputOption option={option} values={values} onChange={onChange} />;
}

function OptionLabel({ label, description }: { label: string; description?: string }) {
  return (
    <span className="option-label">
      {label}
      {description ? (
        <span className="hint" title={description} aria-label={description}>
          <HelpCircle size={15} />
        </span>
      ) : null}
    </span>
  );
}

function SwitchOption({
  option,
  value,
  onChange
}: {
  option: SwitchOptionDefinition;
  value: boolean;
  onChange: (name: string, value: OptionValue) => void;
}) {
  return (
    <div className="switch-row">
      <OptionLabel label={option.label} description={option.description} />
      <input
        checked={value}
        type="checkbox"
        onChange={(event) => onChange(option.key, event.target.checked)}
      />
    </div>
  );
}

function SelectOption({
  option,
  value,
  onChange
}: {
  option: SelectOptionDefinition;
  value: string;
  onChange: (name: string, value: OptionValue) => void;
}) {
  return (
    <label className="option-row indented-option">
      <OptionLabel label={option.label} description={option.description} />
      <select value={value} onChange={(event) => onChange(option.key, event.target.value)}>
        {option.cases.map((caseName) => (
          <option key={caseName} value={caseName}>
            {caseName}
          </option>
        ))}
      </select>
    </label>
  );
}

function InputOption({
  option,
  values,
  onChange
}: {
  option: InputOptionDefinition;
  values: Record<string, OptionValue>;
  onChange: (name: string, value: OptionValue) => void;
}) {
  return (
    <fieldset className="option-group">
      {option.label ? <legend>{option.label}</legend> : null}
      {option.description ? <p>{option.description}</p> : null}
      {option.inputs.map((input) => (
        <label className="option-row" key={input.name}>
          <OptionLabel label={input.label} description={input.description} />
          <input
            inputMode={input.pipelineType === "int" ? "numeric" : "text"}
            type={input.pipelineType === "int" ? "number" : "text"}
            value={String(values[input.name] ?? input.defaultValue)}
            onChange={(event) => onChange(input.name, event.target.value)}
          />
        </label>
      ))}
    </fieldset>
  );
}

function SettingsDialog({
  settingsValues,
  onClose,
  onSave
}: {
  settingsValues: Record<string, OptionValue>;
  onClose: () => void;
  onSave: (values: Record<string, OptionValue>) => void;
}) {
  const [values, setValues] = useState<Record<string, OptionValue>>(() => ({ ...settingsValues }));

  function updateValue(name: string, value: OptionValue) {
    setValues((current) => ({
      ...current,
      [name]: value
    }));
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">客户端</p>
            <h2 id="settings-title">设置</h2>
          </div>
          <button className="row-icon-button" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="settings-list">
          <OptionField option={globalSettingsOption} values={values} onChange={updateValue} />
          <label className="field-group compact">
            <span>主题</span>
            <select defaultValue="light">
              <option value="light">浅色</option>
              <option value="system">跟随系统</option>
            </select>
          </label>
          <label className="toggle-row">
            <input type="checkbox" defaultChecked />
            <span>启动时打开上次游戏</span>
          </label>
          <label className="toggle-row">
            <input type="checkbox" defaultChecked />
            <span>需要管理员权限时提示</span>
          </label>
        </div>

        <div className="modal-actions">
          <button className="secondary-action" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-action" type="button" onClick={() => onSave(values)}>
            保存
          </button>
        </div>
      </section>
    </div>
  );
}

function EmptyState({ title }: { title: string }) {
  return (
    <div className="empty-state">
      <Gamepad2 size={34} />
      <h3>{title}</h3>
    </div>
  );
}

type ViewToggleProps = {
  activeView: "features" | "live";
  onViewChange: (view: "features" | "live") => void;
};

function ViewToggle({ activeView, onViewChange }: ViewToggleProps) {
  return (
    <div className="view-toggle" role="tablist" aria-label="视图切换">
      <button
        className={`view-toggle-btn ${activeView === "features" ? "active" : ""}`}
        role="tab"
        aria-selected={activeView === "features"}
        type="button"
        onClick={() => onViewChange("features")}
      >
        <Gamepad2 size={18} />
        功能列表
      </button>
      <button
        className={`view-toggle-btn ${activeView === "live" ? "active" : ""}`}
        role="tab"
        aria-selected={activeView === "live"}
        type="button"
        onClick={() => onViewChange("live")}
      >
        <Monitor size={18} />
        实时视图
      </button>
    </div>
  );
}

type LiveViewPanelProps = {
  targetWindow: string;
  connected: boolean;
};

function LiveViewPanel({ targetWindow, connected }: LiveViewPanelProps) {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fps, setFps] = useState(20);
  const [actualFps, setActualFps] = useState(0);
  const frameTimesRef = useRef<number[]>([]);
  const unlistenFrameRef = useRef<UnlistenFn | null>(null);
  const unlistenErrorRef = useRef<UnlistenFn | null>(null);
  const fpsTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 每 500ms 计算一次实际帧率
  useEffect(() => {
    fpsTimerRef.current = setInterval(() => {
      const now = Date.now();
      // 只保留最近 2 秒的帧时间戳
      const recent = frameTimesRef.current.filter((t) => now - t < 2000);
      frameTimesRef.current = recent;
      if (recent.length >= 2) {
        const span = (recent[recent.length - 1] - recent[0]) / 1000;
        setActualFps(Math.round((recent.length - 1) / span));
      } else {
        setActualFps(0);
      }
    }, 500);

    return () => {
      if (fpsTimerRef.current) clearInterval(fpsTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!connected || !targetWindow) {
      setImageSrc(null);
      setError(null);
      frameTimesRef.current = [];
      setActualFps(0);
      return;
    }

    let cancelled = false;
    setImageSrc(null);
    setError(null);
    frameTimesRef.current = [];
    setActualFps(0);

    async function start() {
      const unlistenFrame = await listen<string>("live-view-frame", (event) => {
        if (cancelled) return;
        setImageSrc(`data:image/jpeg;base64,${event.payload}`);
        setError(null);
        frameTimesRef.current.push(Date.now());
      });

      const unlistenError = await listen<string>("live-view-error", (event) => {
        if (cancelled) return;
        setError(event.payload);
      });

      if (cancelled) {
        unlistenFrame();
        unlistenError();
        return;
      }

      unlistenFrameRef.current = unlistenFrame;
      unlistenErrorRef.current = unlistenError;

      await invoke("start_live_view", { targetWindow, fps });
    }

    start();

    return () => {
      cancelled = true;
      if (unlistenFrameRef.current) {
        unlistenFrameRef.current();
        unlistenFrameRef.current = null;
      }
      if (unlistenErrorRef.current) {
        unlistenErrorRef.current();
        unlistenErrorRef.current = null;
      }
      invoke("stop_live_view").catch((err) => {
        console.error("Failed to stop live view", err);
      });
    };
  }, [targetWindow, connected, fps]);

  if (!connected || !targetWindow) {
    return (
      <div className="live-view-placeholder">
        <Monitor size={48} />
        <h3>请先连接目标窗口</h3>
        <p>在上方选择目标窗口后，实时视图将自动开始</p>
      </div>
    );
  }

  const hasFrames = frameTimesRef.current.length > 0;

  return (
    <div className="live-view-panel">
      <div className="live-view-toolbar">
        <span className="live-view-status">
          <span className={`status-dot ${error ? "" : "connected"}`} />
          {error ? "捕获失败" : actualFps > 0 ? `${actualFps} FPS` : "正在连接..."}
        </span>
        <div className="live-view-fps">
          <span className="connection-label">目标帧率</span>
          <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
            <option value={5}>5 FPS</option>
            <option value={10}>10 FPS</option>
            <option value={15}>15 FPS</option>
            <option value={20}>20 FPS</option>
            <option value={30}>30 FPS</option>
          </select>
        </div>
      </div>
      <div className="live-view-viewport">
        {!hasFrames && !error ? (
          <div className="live-view-placeholder">
            <RefreshCw size={32} className="spin" />
            <p>正在捕获第一帧...</p>
          </div>
        ) : error && !imageSrc ? (
          <div className="live-view-error">
            <p className="live-view-error-msg">{error}</p>
            <p>等待重试...</p>
          </div>
        ) : (
          imageSrc && (
            <img
              src={imageSrc}
              alt="实时视图"
              className="live-view-image"
            />
          )
        )}
      </div>
    </div>
  );
}

export default App;
