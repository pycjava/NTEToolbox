import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import {
  CheckCircle2,
  Download,
  Fish,
  Gamepad2,
  Info,
  Library,
  Loader2,
  type LucideIcon,
  Monitor,
  Music2,
  Pencil,
  Play,
  HelpCircle,
  RefreshCw,
  Settings,
  Sparkles,
  Square,
  X,
  XCircle
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
  resolveTheme,
  selectGame,
  setAdminPromptEnabled,
  setControllerType,
  setFeatureOptionValues,
  setFeatureRunState,
  setGlobalSettingsValues,
  setTargetWindow,
  setTheme,
  type ClientState,
  type ControllerState,
  type FeatureDefinition,
  type GameDefinition,
  type InputOptionDefinition,
  type OptionDefinition,
  type OptionValue,
  type RunState,
  type SelectOptionDefinition,
  type SwitchOptionDefinition,
  type ThemeMode,
  type WindowInfo
} from "./clientModel";
import HsCoachPanel from "./HsCoachPanel";
import {
  addToast,
  createToast,
  dismissToast,
  pruneToasts,
  TOAST_TTL_MS,
  type Toast,
  type ToastKind
} from "./toast";

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

type MutopiaMidiEntry = {
  id: string;
  title: string;
  composer: string;
  instrument: string;
  style: string;
  license: string;
  midiUrl: string;
  sourceUrl: string;
};

type DownloadedMidiEntry = {
  fileName: string;
  displayName: string;
  filePath: string;
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
  const [activeView, setActiveView] = useState<"features" | "live" | "library">("features");
  const [mutopiaCache, setMutopiaCache] = useState<MutopiaMidiEntry[] | null>(null);
  const stateRef = useRef(state);
  const { toasts, pushToast, dismiss } = useToasts();

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // 主题应用：解析 theme → documentElement.dataset.theme。
  // system 模式监听 prefers-color-scheme 变化实时切换。
  useEffect(() => {
    const apply = () => {
      document.documentElement.dataset.theme = resolveTheme(state.theme);
    };
    apply();

    if (state.theme !== "system") return;
    // 防御：jsdom 等无 matchMedia 的环境跳过监听（resolveTheme 已安全降级）
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => apply();
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, [state.theme]);

  useEffect(() => {
    let cancelled = false;

    invoke<PersistedClientConfig | null>("load_client_config")
      .then((config) => {
        if (cancelled || !config) return;
        setState((current) => applyPersistedClientConfig(current, config));
      })
      .catch((error) => {
        console.error("Failed to load client config", error);
        pushToast("error", "加载配置失败");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // 管理员权限提示：开启时若进程未提权，提示一次（异环注入类功能需要管理员）
  useEffect(() => {
    if (!state.adminPromptEnabled) return;
    let cancelled = false;

    invoke<boolean>("is_elevated")
      .then((elevated) => {
        if (cancelled || elevated) return;
        pushToast("info", "当前未以管理员身份运行，部分功能可能不可用");
      })
      .catch((error) => {
        console.error("Failed to query elevation state", error);
      });

    return () => {
      cancelled = true;
    };
  }, [state.adminPromptEnabled]);

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
    pushToast("info", "配置已保存");
  }

  function handleRunChange(gameId: string, featureId: string, runState: RunState) {
    const currentState = stateRef.current;
    const game = currentState.games.find((candidate) => candidate.id === gameId);
    const feature = game?.features.find((candidate) => candidate.id === featureId);

    if (!game || !feature) return;

    if (runState === "running") {
      setState((current) => setFeatureRunState(current, gameId, featureId, "starting"));
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
          pushToast("error", "启动任务失败");
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
          pushToast("error", "结束任务失败");
        });
      return;
    }

    setState((current) => setFeatureRunState(current, gameId, featureId, runState));
  }

  function handleSaveSettings(values: Record<string, OptionValue>, theme?: ThemeMode, adminPromptEnabled?: boolean) {
    let nextState: ClientState | null = null;
    setState((current) => {
      let next = setGlobalSettingsValues(current, values);
      if (theme !== undefined) next = setTheme(next, theme);
      if (adminPromptEnabled !== undefined) next = setAdminPromptEnabled(next, adminPromptEnabled);
      nextState = next;
      return next;
    });
    setIsSettingsOpen(false);
    persistClientConfig(nextState ?? stateRef.current);
    pushToast("info", "设置已保存");
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
        pushToast("error", "刷新窗口列表失败");
      });
  }

  function persistClientConfig(nextState: ClientState) {
    stateRef.current = nextState;
    void invoke("save_client_config", {
      config: buildPersistedClientConfig(nextState, nteOptions)
    }).catch((error) => {
      console.error("Failed to save client config", error);
      pushToast("error", "保存配置失败");
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
            <h1>NTEToolbox</h1>
            <p>{selectedGame ? getGameSubtitle(selectedGame) : "未选择"}</p>
          </div>
        </div>

        <div className="top-actions">
          <button className="icon-button" type="button" aria-label="设置" title="设置" onClick={() => setIsSettingsOpen(true)}>
            <Settings size={20} />
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
              已安装
            </span>
          </div>

          {selectedGame.kind === "process" ? (
            <HsCoachPanel
              game={selectedGame}
              onTargetWindowChange={handleTargetWindowChange}
              onRefreshWindows={handleRefreshWindows}
            />
          ) : (
            <>
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
              ) : activeView === "library" ? (
                <div className="mutopia-panel">
                  <MutopiaMidiBrowser
                    cachedEntries={mutopiaCache}
                    onCacheUpdate={setMutopiaCache}
                  />
                </div>
              ) : (
                <LiveViewPanel
                  targetWindow={selectedGame.controller?.targetWindow ?? ""}
                  connected={selectedGame.controller?.connected ?? false}
                  onError={(message) => pushToast("error", message)}
                />
              )}
            </>
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
          theme={state.theme}
          adminPromptEnabled={state.adminPromptEnabled}
          onClose={() => setIsSettingsOpen(false)}
          onSave={handleSaveSettings}
        />
      ) : null}

      <ToastViewport toasts={toasts} onDismiss={dismiss} />
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
      <div className="connection-header">
        <div className="connection-status">
          <span className={`status-dot ${controller.connected ? "connected" : ""}`} />
          <span className="status-text">{controller.connected ? "已连接" : "未连接"}</span>
        </div>
      </div>
      <div className="connection-grid">
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
          <select
            value={controller.targetWindow}
            onChange={(event) => onTargetWindowChange(gameId, event.target.value)}
          >
            <option value="">请选择窗口</option>
            {controller.availableWindows.map((win) => (
              <option key={win.hwnd} value={win.hwnd}>{win.title} ({win.className})</option>
            ))}
          </select>
        </div>
        <button className="icon-button connection-refresh" type="button" aria-label="刷新窗口列表" title="刷新窗口列表" onClick={() => onRefreshWindows(gameId)}>
          <RefreshCw size={18} />
        </button>
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
      {game.features.map((feature, index) => (
        <FeatureRow
          feature={feature}
          gameId={game.id}
          key={feature.id}
          onConfigure={onConfigure}
          onRunChange={onRunChange}
          rowIndex={index}
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
  rowIndex: number;
};

function FeatureRow({ feature, gameId, onConfigure, onRunChange, rowIndex }: FeatureRowProps) {
  const Icon = getFeatureIcon(feature.id);
  const currentRunState = feature.runState ?? "idle";
  const isRunning = runningStates.has(currentRunState);

  return (
    <article
      className={`feature-row ${isRunning ? "running" : ""}`}
      aria-label={`${feature.name} 功能行`}
      style={{ "--row-index": rowIndex } as React.CSSProperties}
    >
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
          <button className="primary-action" type="button"
            disabled={currentRunState === "starting"}
            onClick={() => onRunChange(gameId, feature.id, "running")}>
            {currentRunState === "starting" ? <Loader2 size={17} className="spin" /> : <Play size={17} />}
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

        {target.feature.id === "piano" ? (
          <PianoTrackSelector value={String(values.midi_path ?? "")} onChange={(path) => updateValue("midi_path", path)} />
        ) : null}

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

function PianoTrackSelector({ value, onChange }: { value: string; onChange: (path: string) => void }) {
  const [files, setFiles] = useState<DownloadedMidiEntry[]>([]);

  function refresh() {
    invoke<DownloadedMidiEntry[]>("list_downloaded_midi")
      .then((result) => setFiles(result ?? []))
      .catch(() => setFiles([]));
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div className="field-group">
      <span>选择曲目</span>
      <div className="midi-select">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          {files.length === 0 ? (
            <option value="">请先在 MIDI 曲库中下载曲目</option>
          ) : (
            <option value="">请选择曲目</option>
          )}
          {files.map((file) => (
            <option key={file.filePath} value={file.filePath}>
              {file.displayName}
            </option>
          ))}
        </select>
        <button className="icon-button" type="button" aria-label="刷新列表" title="刷新列表" onClick={refresh}>
          <RefreshCw size={18} />
        </button>
      </div>
    </div>
  );
}

function MutopiaMidiBrowser({
  cachedEntries,
  onCacheUpdate,
}: {
  cachedEntries: MutopiaMidiEntry[] | null;
  onCacheUpdate: (entries: MutopiaMidiEntry[]) => void;
}) {
  const hasCache = cachedEntries !== null && cachedEntries.length > 0;
  const [entries, setEntries] = useState<MutopiaMidiEntry[]>(() => cachedEntries ?? []);
  const [status, setStatus] = useState<"idle" | "loading" | "failed" | "loaded">(() =>
    hasCache ? "loaded" : "idle"
  );
  const [error, setError] = useState("");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadedIds, setDownloadedIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    invoke<DownloadedMidiEntry[]>("list_downloaded_midi")
      .then((files) => {
        setDownloadedIds(new Set((files ?? []).map((f) => f.fileName)));
      })
      .catch(() => { /* ignore — no downloaded files yet */ });
  }, []);

  // 首次挂载且无缓存时自动加载
  useEffect(() => {
    if (!hasCache) {
      void loadEntries();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadEntries() {
    setStatus("loading");
    setError("");
    try {
      const result = await invoke<MutopiaMidiEntry[]>("list_mutopia_public_domain_midi");
      setEntries(result ?? []);
      onCacheUpdate(result ?? []);
      setStatus("loaded");
    } catch (loadError) {
      setError(String(loadError));
      setStatus("failed");
    }
  }

  async function downloadEntry(entry: MutopiaMidiEntry) {
    setDownloadingId(entry.id);
    setError("");
    try {
      await invoke<string>("download_mutopia_midi", {
        request: {
          title: entry.title,
          composer: entry.composer,
          license: entry.license,
          midiUrl: entry.midiUrl
        }
      });
      setDownloadedIds((prev) => new Set(prev).add(entry.id));
    } catch (downloadError) {
      setError(String(downloadError));
    } finally {
      setDownloadingId(null);
    }
  }

  const filteredEntries = searchQuery.trim()
    ? entries.filter((entry) => {
        const q = searchQuery.toLowerCase();
        return [entry.title, entry.composer, entry.style].some((field) => field.toLowerCase().includes(q));
      })
    : entries;

  return (
    <section className="mutopia-browser" aria-labelledby="mutopia-browser-title">
      <div className="mutopia-header">
        <div>
          <h3 id="mutopia-browser-title">Mutopia 公共领域 MIDI</h3>
          <p>Public Domain only · mutopiaproject.org</p>
        </div>
        <button className="secondary-action" type="button" onClick={loadEntries} disabled={status === "loading"}>
          {status === "loading" ? <Loader2 size={16} className="spin" /> : <Library size={16} />}
          {hasCache ? "刷新曲库" : "加载曲库"}
        </button>
      </div>

      {entries.length > 0 ? (
        <div className="mutopia-search">
          <input
            type="text"
            placeholder="搜索曲名、作曲家、风格..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
        </div>
      ) : null}

      {error ? <p className="mutopia-error">{error}</p> : null}

      {filteredEntries.length > 0 ? (
        <div className="mutopia-list">
          {filteredEntries.map((entry, index) => {
            const isDownloaded = downloadedIds.has(entry.id);
            return (
              <article
                className="mutopia-item"
                key={entry.id}
                style={{ "--row-index": index } as React.CSSProperties}
              >
                <div className="mutopia-copy">
                  <div className="mutopia-title-line">
                    <h4>{entry.title}</h4>
                    <span>{entry.license}</span>
                  </div>
                  <p>{[entry.composer, entry.instrument, entry.style].filter(Boolean).join(" · ")}</p>
                </div>
                <div className="mutopia-actions">
                  {isDownloaded ? (
                    <span className="mutopia-downloaded-badge">已下载 ✓</span>
                  ) : (
                    <button
                      className="primary-action compact-action"
                      type="button"
                      disabled={downloadingId !== null}
                      aria-label={`下载 ${entry.title}`}
                      onClick={() => { void downloadEntry(entry); }}
                    >
                      {downloadingId === entry.id ? <Loader2 size={15} className="spin" /> : <Download size={15} />}
                      下载
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mutopia-empty">
          {status === "loaded" && searchQuery.trim() ? "没有匹配的曲目。" : status === "loaded" ? "没有可用的 Public Domain MIDI。" : " "}
        </div>
      )}
    </section>
  );
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
  theme,
  adminPromptEnabled,
  onClose,
  onSave
}: {
  settingsValues: Record<string, OptionValue>;
  theme: ThemeMode;
  adminPromptEnabled: boolean;
  onClose: () => void;
  onSave: (
    values: Record<string, OptionValue>,
    theme: ThemeMode,
    adminPromptEnabled: boolean
  ) => void;
}) {
  const [values, setValues] = useState<Record<string, OptionValue>>(() => ({ ...settingsValues }));
  const [draftTheme, setDraftTheme] = useState<ThemeMode>(theme);
  const [draftAdminPrompt, setDraftAdminPrompt] = useState<boolean>(adminPromptEnabled);

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
            <select value={draftTheme} onChange={(event) => setDraftTheme(event.target.value as ThemeMode)}>
              <option value="light">浅色</option>
              <option value="dark">暗色</option>
              <option value="system">跟随系统</option>
            </select>
          </label>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={draftAdminPrompt}
              onChange={(event) => setDraftAdminPrompt(event.target.checked)}
            />
            <span>需要管理员权限时提示</span>
          </label>
        </div>

        <div className="modal-actions">
          <button className="secondary-action" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-action" type="button" onClick={() => onSave(values, draftTheme, draftAdminPrompt)}>
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
  activeView: "features" | "live" | "library";
  onViewChange: (view: "features" | "live" | "library") => void;
};

const VIEW_TOGGLE_ORDER: Array<"features" | "live" | "library"> = ["features", "live", "library"];

function ViewToggle({ activeView, onViewChange }: ViewToggleProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [indicator, setIndicator] = useState({ x: 0, w: 0, ready: false });

  function measureIndicator() {
    const container = containerRef.current;
    const activeBtn = btnRefs.current[activeView];
    if (!container || !activeBtn) return;
    const containerRect = container.getBoundingClientRect();
    const btnRect = activeBtn.getBoundingClientRect();
    setIndicator({
      x: btnRect.left - containerRect.left,
      w: btnRect.width,
      ready: true
    });
  }

  // useLayoutEffect 在浏览器 paint 前同步执行，
  // 避免 useEffect（paint 后）导致指示器先以 0 宽度闪现一帧。
  useLayoutEffect(() => {
    measureIndicator();
  }, [activeView]);

  // resize 监听仍用 useEffect（无需阻塞 paint）。
  useEffect(() => {
    const handleResize = () => measureIndicator();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [activeView]);

  return (
    <div className="view-toggle" role="tablist" aria-label="视图切换" ref={containerRef}>
      <span
        className="view-toggle-indicator"
        aria-hidden="true"
        style={{
          transform: `translateX(${indicator.x}px)`,
          width: `${indicator.w}px`,
          opacity: indicator.ready ? 1 : 0
        }}
      />
      {VIEW_TOGGLE_ORDER.map((view) => {
        const Icon = view === "features" ? Gamepad2 : view === "live" ? Monitor : Music2;
        const label = view === "features" ? "功能列表" : view === "live" ? "实时视图" : "MIDI 曲库";
        return (
          <button
            key={view}
            ref={(el) => { btnRefs.current[view] = el; }}
            className={`view-toggle-btn ${activeView === view ? "active" : ""}`}
            role="tab"
            aria-selected={activeView === view}
            type="button"
            onClick={() => onViewChange(view)}
          >
            <Icon size={18} />
            {label}
          </button>
        );
      })}
    </div>
  );
}

type LiveViewPanelProps = {
  targetWindow: string;
  connected: boolean;
  onError: (message: string) => void;
};

function LiveViewPanel({ targetWindow, connected, onError }: LiveViewPanelProps) {
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
        onError("停止实时视图失败");
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

type UseToastsResult = {
  toasts: Toast[];
  pushToast: (kind: ToastKind, message: string) => void;
  dismiss: (id: number) => void;
};

/**
 * Toast 状态管理 hook。
 * push 时按 TTL 自动调度消失；超过可见上限自动裁剪最旧的。
 */
function useToasts(): UseToastsResult {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const clearTimer = useCallback((id: number) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const dismiss = useCallback((id: number) => {
    clearTimer(id);
    setToasts((current) => dismissToast(current, id));
  }, [clearTimer]);

  const pushToast = useCallback((kind: ToastKind, message: string) => {
    const toast = createToast(kind, message);
    setToasts((current) => pruneToasts(addToast(current, toast)));

    const timer = setTimeout(() => {
      timersRef.current.delete(toast.id);
      setToasts((current) => dismissToast(current, toast.id));
    }, TOAST_TTL_MS[kind]);
    timersRef.current.set(toast.id, timer);
  }, []);

  // 卸载时清理所有未触发的定时器
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  return { toasts, pushToast, dismiss };
}

const TOAST_ICON: Record<ToastKind, LucideIcon> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info
};

function ToastViewport({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toast-viewport" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => {
        const Icon = TOAST_ICON[toast.kind];
        return (
          <div
            key={toast.id}
            className={`toast toast-${toast.kind}`}
            role={toast.kind === "error" ? "alert" : "status"}
          >
            <span className="toast-icon" aria-hidden="true">
              <Icon size={18} />
            </span>
            <span className="toast-message">{toast.message}</span>
            <button
              className="toast-close"
              type="button"
              aria-label="关闭通知"
              onClick={() => onDismiss(toast.id)}
            >
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default App;
