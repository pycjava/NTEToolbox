import React, { useMemo, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Fish,
  Gamepad2,
  Maximize2,
  Monitor,
  Music2,
  Pause,
  Pencil,
  Play,
  HelpCircle,
  RefreshCw,
  Settings,
  Sparkles,
  Square,
  Upload
} from "lucide-react";

import { globalSettingsOption, initialGames, nteOptions } from "./clientData";
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
  type RunState
} from "./clientModel";

type DialogFeature = {
  gameId: string;
  feature: FeatureDefinition;
};

const runningStates = new Set<RunState>(["starting", "running", "paused", "stopping"]);

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
    case "paused":
      return "已暂停";
    case "stopping":
      return "停止中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    default:
      return "就绪";
  }
}

function getGameSubtitle(game: GameDefinition) {
  if (game.features.length === 0) return "未导入功能";
  return game.features.map((feature) => feature.name).join(" / ");
}

function App() {
  const [state, setState] = useState<ClientState>(() => buildInitialClientState(initialGames));
  const [configTarget, setConfigTarget] = useState<DialogFeature | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [viewMode, setViewMode] = useState<"features" | "liveview">("features");

  const selectedGame = useMemo(
    () => state.games.find((game) => game.id === state.selectedGameId) ?? state.games[0],
    [state.games, state.selectedGameId]
  );

  function handleSelectGame(gameId: string) {
    setState((current) => selectGame(current, gameId));
  }

  function handleSaveFeatureConfig(gameId: string, featureId: string, values: Record<string, OptionValue>) {
    setState((current) => setFeatureOptionValues(current, gameId, featureId, values));
    setConfigTarget(null);
  }

  function handleRunChange(gameId: string, featureId: string, runState: RunState) {
    setState((current) => setFeatureRunState(current, gameId, featureId, runState));
  }

  function handleSaveSettings(values: Record<string, OptionValue>) {
    setState((current) => setGlobalSettingsValues(current, values));
    setIsSettingsOpen(false);
  }

  function handleControllerTypeChange(gameId: string, controllerType: string) {
    setState((current) => setControllerType(current, gameId, controllerType));
  }

  function handleTargetWindowChange(gameId: string, targetWindow: string) {
    setState((current) => setTargetWindow(current, gameId, targetWindow));
  }

  function handleRefreshWindows(gameId: string) {
    // TODO: replace with Tauri command invocation
    const mockWindows = ["异环 - NTE", "模拟器窗口 1", "模拟器窗口 2"];
    setState((current) => refreshWindows(current, gameId, mockWindows));
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            <img src="./src/assets/nte-icon.png" alt="" />
          </div>
          <div>
            <h1>MaaToolbox</h1>
            <p>{selectedGame?.name ?? "未选择"}</p>
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
          viewMode={viewMode}
          onSelectGame={(gameId) => { handleSelectGame(gameId); setViewMode("features"); }}
          onSelectLiveView={() => setViewMode("liveview")}
        />
      </header>

      {selectedGame ? (
        <section className="content-panel" aria-label={`${selectedGame.name} 功能`}>
          {viewMode === "features" ? (
            <>
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

              <FeatureList
                game={selectedGame}
                onConfigure={(feature) => setConfigTarget({ gameId: selectedGame.id, feature })}
                onRunChange={handleRunChange}
              />
            </>
          ) : (
            <LiveViewPanel />
          )}
        </section>
      ) : (
        <EmptyState title="尚未添加游戏" />
      )}

      {configTarget ? (
        <FeatureConfigDialog
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

const controllerTypes = ["Win PostMessageWithWindowPos", "Win SendMessage", "ADB Input"];

function ConnectionBar({ gameId, controller, onControllerTypeChange, onTargetWindowChange, onRefreshWindows }: ConnectionBarProps) {
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
              <option key={win} value={win}>{win}</option>
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

function LiveViewPanel() {
  return (
    <div className="live-view-panel">
      <div className="live-view-header">
        <h3>实时视图</h3>
        <button className="icon-button" type="button" aria-label="全屏" title="全屏">
          <Maximize2 size={18} />
        </button>
      </div>
      <div className="live-view-content">
        <Monitor size={48} />
        <p>暂无截图</p>
        <p className="live-view-hint">选择目标窗口并启动功能后，此处将显示实时画面</p>
      </div>
    </div>
  );
}

type GameSwitcherProps = {
  games: GameDefinition[];
  selectedGameId: string;
  viewMode: "features" | "liveview";
  onSelectGame: (gameId: string) => void;
  onSelectLiveView: () => void;
};

function GameSwitcher({ games, selectedGameId, viewMode, onSelectGame, onSelectLiveView }: GameSwitcherProps) {
  return (
    <nav className="game-switcher" aria-label="游戏选择">
      {games.map((game) => (
        <button
          className={`game-icon ${game.id === selectedGameId && viewMode === "features" ? "selected" : ""}`}
          key={game.id}
          type="button"
          aria-label={game.name}
          title={game.name}
          onClick={() => { onSelectGame(game.id); }}
        >
          <span>{game.icon ? <img src={game.icon} alt={game.name} /> : game.shortName}</span>
        </button>
      ))}
      <button
        className={`game-icon live-view-btn ${viewMode === "liveview" ? "selected" : ""}`}
        type="button"
        aria-label="实时视图"
        title="实时视图"
        onClick={onSelectLiveView}
      >
        <span><Monitor size={20} /></span>
      </button>
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
    <article className={`feature-row ${isRunning ? "running" : ""}`}>
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
          <span className={`run-badge run-${currentRunState}`}>{getRunLabel(currentRunState)}</span>
        </div>
        <p>{feature.description}</p>
        <p className="feature-summary">{feature.configSummary}</p>
      </div>
      <div className="feature-actions">
        {isRunning ? (
          <>
            <button className="secondary-action" type="button" onClick={() => onRunChange(gameId, feature.id, "paused")}>
              <Pause size={17} />
              暂停
            </button>
            <button className="secondary-action danger" type="button" onClick={() => onRunChange(gameId, feature.id, "idle")}>
              <Square size={16} />
              停止
            </button>
          </>
        ) : (
          <button className="primary-action" type="button" onClick={() => onRunChange(gameId, feature.id, "running")}>
            <Play size={17} />
            启动
          </button>
        )}
        <button className="row-icon-button" type="button" aria-label={`编辑${feature.name}`} title="编辑" onClick={() => onConfigure(feature)}>
          <Pencil size={19} />
        </button>
        <button className="row-icon-button" type="button" aria-label={`复制${feature.name}配置`} title="复制配置">
          <Copy size={19} />
        </button>
      </div>
    </article>
  );
}

type FeatureConfigDialogProps = {
  target: DialogFeature;
  onClose: () => void;
  onSave: (gameId: string, featureId: string, values: Record<string, OptionValue>) => void;
};

function FeatureConfigDialog({ target, onClose, onSave }: FeatureConfigDialogProps) {
  const [values, setValues] = useState<Record<string, OptionValue>>(() => ({ ...(target.feature.optionValues ?? {}) }));
  const optionDefinitions = target.feature.optionKeys?.length ? nteOptions : {};
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

export default App;
