import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Fish,
  FolderOpen,
  Gamepad2,
  Music2,
  Pause,
  Pencil,
  Play,
  Plus,
  Settings,
  Sparkles,
  Square,
  Upload
} from "lucide-react";

import { initialGames } from "./clientData";
import {
  addGame,
  buildInitialClientState,
  selectGame,
  setFeatureConfig,
  setFeatureRunState,
  type ClientState,
  type FeatureDefinition,
  type GameDefinition,
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
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const selectedGame = useMemo(
    () => state.games.find((game) => game.id === state.selectedGameId) ?? state.games[0],
    [state.games, state.selectedGameId]
  );

  function handleSelectGame(gameId: string) {
    setState((current) => selectGame(current, gameId));
  }

  function handleSaveFeatureConfig(gameId: string, featureId: string, summary: string) {
    setState((current) => setFeatureConfig(current, gameId, featureId, summary));
    setConfigTarget(null);
  }

  function handleRunChange(gameId: string, featureId: string, runState: RunState) {
    setState((current) => setFeatureRunState(current, gameId, featureId, runState));
  }

  function handleAddGame(game: GameDefinition) {
    setState((current) => addGame(current, game));
    setIsAddOpen(false);
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            NT
          </div>
          <div>
            <h1>NTEToolbox</h1>
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

        <GameSwitcher games={state.games} selectedGameId={state.selectedGameId} onSelect={handleSelectGame} />

        <button className="add-button" type="button" aria-label="添加游戏" title="添加游戏" onClick={() => setIsAddOpen(true)}>
          <Plus size={26} />
        </button>
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

          <FeatureList
            game={selectedGame}
            onConfigure={(feature) => setConfigTarget({ gameId: selectedGame.id, feature })}
            onRunChange={handleRunChange}
          />
        </section>
      ) : (
        <EmptyState title="尚未添加游戏" actionLabel="添加游戏" onAction={() => setIsAddOpen(true)} />
      )}

      {configTarget ? (
        <FeatureConfigDialog
          target={configTarget}
          onClose={() => setConfigTarget(null)}
          onSave={handleSaveFeatureConfig}
        />
      ) : null}

      {isAddOpen ? <AddGameDialog onClose={() => setIsAddOpen(false)} onAdd={handleAddGame} /> : null}
      {isSettingsOpen ? <SettingsDialog onClose={() => setIsSettingsOpen(false)} /> : null}
    </main>
  );
}

type GameSwitcherProps = {
  games: GameDefinition[];
  selectedGameId: string;
  onSelect: (gameId: string) => void;
};

function GameSwitcher({ games, selectedGameId, onSelect }: GameSwitcherProps) {
  return (
    <nav className="game-switcher" aria-label="游戏选择">
      {games.map((game) => (
        <button
          className={`game-icon ${game.id === selectedGameId ? "selected" : ""}`}
          key={game.id}
          type="button"
          aria-label={game.name}
          title={game.name}
          onClick={() => onSelect(game.id)}
        >
          <span>{game.shortName}</span>
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
    return <EmptyState title="没有可用功能" actionLabel="添加游戏" />;
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
  onSave: (gameId: string, featureId: string, summary: string) => void;
};

function FeatureConfigDialog({ target, onClose, onSave }: FeatureConfigDialogProps) {
  const [summary, setSummary] = useState(target.feature.configSummary);

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

        <label className="field-group">
          <span>摘要</span>
          <input value={summary} onChange={(event) => setSummary(event.target.value)} />
        </label>

        <div className="config-grid">
          <label className="toggle-row">
            <input type="checkbox" defaultChecked={target.feature.id === "fish"} />
            <span>主要功能</span>
          </label>
          <label className="toggle-row">
            <input type="checkbox" />
            <span>启动前确认窗口</span>
          </label>
          <label className="field-group compact">
            <span>预设</span>
            <select defaultValue="default">
              <option value="default">默认</option>
              <option value="safe">保守</option>
              <option value="fast">快速</option>
            </select>
          </label>
        </div>

        <div className="modal-actions">
          <button className="secondary-action" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-action" type="button" onClick={() => onSave(target.gameId, target.feature.id, summary)}>
            保存
          </button>
        </div>
      </section>
    </div>
  );
}

type AddGameDialogProps = {
  onClose: () => void;
  onAdd: (game: GameDefinition) => void;
};

function AddGameDialog({ onClose, onAdd }: AddGameDialogProps) {
  const [name, setName] = useState("");
  const trimmedName = name.trim();

  function handleAdd() {
    if (!trimmedName) return;

    onAdd({
      id: `local-${Date.now()}`,
      name: trimmedName,
      shortName: Array.from(trimmedName)[0] ?? "新",
      status: "placeholder",
      features: []
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-labelledby="add-game-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">添加游戏</p>
            <h2 id="add-game-title">本地游戏</h2>
          </div>
          <button className="row-icon-button" type="button" aria-label="关闭" onClick={onClose}>
            ×
          </button>
        </div>

        <label className="field-group">
          <span>名称</span>
          <input value={name} autoFocus onChange={(event) => setName(event.target.value)} placeholder="例如：新游戏" />
        </label>

        <button className="file-target" type="button">
          <FolderOpen size={20} />
          选择 interface.json
        </button>

        <div className="modal-actions">
          <button className="secondary-action" type="button" onClick={onClose}>
            取消
          </button>
          <button className="primary-action" type="button" disabled={!trimmedName} onClick={handleAdd}>
            添加
          </button>
        </div>
      </section>
    </div>
  );
}

function SettingsDialog({ onClose }: { onClose: () => void }) {
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
      </section>
    </div>
  );
}

function EmptyState({ title, actionLabel, onAction }: { title: string; actionLabel: string; onAction?: () => void }) {
  return (
    <div className="empty-state">
      <Gamepad2 size={34} />
      <h3>{title}</h3>
      {onAction ? (
        <button className="primary-action" type="button" onClick={onAction}>
          <Plus size={17} />
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export default App;
