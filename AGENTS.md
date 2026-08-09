# NTEToolbox — 异环工具箱

基于 MaaFramework 的异环游戏自动化工具，包含自动钓鱼、弹钢琴、实时辅助等功能。

## 项目结构

```
NTEToolbox/
├── agent/              # Python 自动化 agent（核心逻辑）
├── assets/             # 游戏资源 + OCR 模型（MaaCommonAssets 子模块）
├── client/             # Tauri v2 + React 前端
│   ├── src/            # React/TypeScript 前端源码
│   ├── src-tauri/      # Rust/Tauri 后端
│   │   ├── src/        #   lib.rs, maa_bridge.rs, client_config.rs
│   │   ├── Cargo.toml  #   crate: ntetoolbox-client, rust-version 1.77.2
│   │   └── tauri.conf.json
│   ├── scripts/        #   prepare-maafw.mjs
│   └── package.json    #   pnpm@11.3.0, tauri 2.x
├── deps/               # MaaFramework SDK（bin/, include/, lib/, share/）— 不入 Git
├── dist/               # PyInstaller 输出（agent.exe）
├── dist-tauri/         # 最终 Tauri 构建产物
├── tests/              # Python pytest 测试
├── tools/              # 构建脚本
│   ├── build_tauri.ps1 #   Tauri 一键构建（6 步）
│   ├── build_all.ps1   #   全量构建编排
│   ├── build_agent.py  #   PyInstaller 打包 Python agent
│   └── configure.py    #   OCR 模型准备
├── pyproject.toml      # Python 包 ntetoolbox，Python >=3.14
└── package.json        # 根 pnpm workspace
```

## 编译环境要求

| 工具 | 版本 | 用途 |
|------|------|------|
| Git | 最新 | 源码 + 子模块 |
| Python | >= 3.14 | agent 运行与打包 |
| Node.js | >= 18 | 前端构建 |
| pnpm | 11.3.0 | 前端包管理（corepack 锁定） |
| Rust | >= 1.77.2 | Tauri 后端（`stable-x86_64-pc-windows-gnu` 工具链） |
| WinLibs MinGW | POSIX UCRT | GNU 链接器（`gcc`/`ld`/`dlltool`） |
| WebView2 | Win10 1803+ 自带 | Tauri 运行时 |
| NSIS / WiX v3 | 可选 | Tauri 安装包生成 |

> **国内环境**：cargo 需配置 rsproxy.cn 镜像，见 `~/.cargo/config.toml`。

## 一键构建（推荐）

在 PowerShell 中执行，从仓库根目录：

```powershell
# 一键构建（推荐）
.\tools\build_tauri.ps1

# 或使用全量构建编排
.\tools\build_all.ps1
```

`build_tauri.ps1` 自动完成 6 步：
1. 查找 WinLibs MinGW（winget 安装路径）
2. 验证 Rust GNU 工具链
3. 设置 `CARGO_TARGET_DIR` 到 `%TEMP%\ntetoolbox-tauri-target`（避免 OneDrive 同步问题）
4. `pip install -e . pyinstaller` + `tools/build_agent.py` → `dist/agent.exe`
5. `cd client && pnpm tauri build`（内含 `pnpm build && pnpm prepare:maafw`）
6. 复制产物到 `dist-tauri/`

### 构建产物

| 产物 | 路径 |
|------|------|
| 可执行文件 | `dist-tauri\MaaToolbox Client.exe` |
| WebView2Loader.dll | `dist-tauri\WebView2Loader.dll`（必须和 exe 同目录） |
| NSIS 安装包 | `dist-tauri\MaaToolbox Client_*_x64-setup.exe` |
| MSI 安装包 | `dist-tauri\MaaToolbox Client_*_x64_en-US.msi`（需启用 VBSCRIPT） |

> **重要**：直接运行 exe 需要 `WebView2Loader.dll` 在同一目录；使用 NSIS 安装包则自动处理。

## 手动构建（调试用）

```powershell
# 1. Python agent
python .\tools\build_agent.py          # → dist/agent.exe

# 2. 前端 + Tauri
cd client
pnpm build                             # TypeScript 编译 + Vite 打包
pnpm prepare:maafw                     # 复制 MaaFramework 到 gen/
pnpm tauri build                       # Rust 编译 + 打包
```

## 开发模式

```powershell
cd client
pnpm tauri dev                         # Vite HMR + Tauri 后端
```

前提：`deps\bin\MaaPiCli.exe`、`assets\resource`、Python 依赖、OCR 模型都已就绪。

## 前置准备（首次）

```powershell
# 子模块
git submodule update --init --recursive

# Python
python -m pip install -e . pyinstaller
python .\tools\configure.py            # OCR 模型 → assets/resource/model/ocr

# 前端
cd client
pnpm install --frozen-lockfile
```

## 测试

```powershell
python -m pytest                       # Python 测试
cd client && pnpm test                 # 前端测试
cd client/src-tauri && cargo check     # Rust 编译检查
```

## Cargo 国内镜像配置

`~/.cargo/config.toml`：

```toml
[source.crates-io]
replace-with = "rsproxy-sparse"

[source.rsproxy-sparse]
registry = "sparse+https://rsproxy.cn/index/"

[net]
git-fetch-with-cli = true
retry = 5
```

## Rust 工具链

本项目使用 `x86_64-pc-windows-gnu`（非 MSVC），依赖 WinLibs MinGW：

```powershell
rustup toolchain install stable-x86_64-pc-windows-gnu
rustup default stable-x86_64-pc-windows-gnu
```

## 常见问题

| 问题 | 解决 |
|------|------|
| `gcc`/`ld`/`dlltool` not found | 用 `build_tauri.ps1`（自动查找）或将 WinLibs `mingw64\bin` 加入 PATH |
| `crates.io` 超时 | 配置 rsproxy.cn 镜像（见上方） |
| `WebView2Loader.dll` 缺失 | 确保 dll 和 exe 在同一目录，或用 NSIS 安装包 |
| MSI `light.exe` 失败 | 需启用 Windows VBSCRIPT 可选功能 |
| OneDrive 下 Rust 构建慢 | `build_tauri.ps1` 自动用 temp 目录，或 `-TargetDir C:\BuildCache\...` |
| `pnpm` not recognized | `corepack enable && corepack prepare pnpm@11.3.0 --activate` |
| `assets\MaaCommonAssets\OCR` 不存在 | `git submodule update --init --recursive` |
| `MaaFramework files not found at deps\bin` | 下载 MaaFramework 到 `deps/`，确保 `deps\bin\MaaPiCli.exe` 存在 |

## 代码风格

- Python：`ruff.toml` 定义了完整规则集
- Rust：`cargo fmt`（需 `rustup component add rustfmt --toolchain stable-x86_64-pc-windows-gnu`）
- 前端：TypeScript + Prettier（`.prettierrc`）

---

## AI 协作约定（针对 ZCode）

> 通用 agent 执行协议。所有非简单任务（调试、改代码、改测试、改仓库配置、可能引向代码改动的调查）都适用。

### Superpowers 协议（强制，非建议）

在响应或行动之前，助手**必须**：

- 检查是否有已发现的技能（skill）适用。
- 把 `using-superpowers` 视为入口工作流。
- 即使任务看起来简单，也要调用任何可能适用的技能。
- 实现类工作优先走 superpowers 工作流，而非临时性的 ad-hoc 执行。

如果跳过了相关技能，必须**显式说明**跳过原因，并在继续前请求许可。

### 硬性关卡（Hard Gates）

每个非简单任务，助手**必须**：

1. 显式声明当前激活的 superpowers 技能及其适用理由。
2. 在开展实质性工作前，显式声明当前所处阶段（phase）。
3. 调试任务：在尝试任何修复前，先完成根因调查（`systematic-debugging` 思路）。
4. 代码改动：优先 TDD（先写失败测试，再实现）——本项目已有 `tests/`（Python pytest）与 `client/src/*.test.tsx`（前端 vitest）。
5. 声称成功之前，必须完成 `verification-before-completion`：跑对应验证命令并出示结果。
6. 任何必要步骤被跳过时，必须明确声明偏差并先请求批准。

### 可见报告要求

每个非简单任务，助手必须在工作过程中（不仅最终总结）可见地报告：

- 激活的技能
- 当前阶段
- 已收集的证据
- TDD 场景下失败的测试命令
- 通过的验证命令
- 如有测试改动了文件，事后恢复的文件列表

### 禁止的捷径

助手**不得**：

- 不经根因调查就从症状跳到修复。
- 在 TDD 场景下，先改代码再补失败测试。
- 没有新的验证证据就声称 bug 已修复。
- 对非简单任务跳过可见的阶段报告。
- 任务结束时留下被测试改动过的配置或状态文件未恢复。
- 偏离规定协议后悄悄继续。

### 测试安全

如果测试会改动项目配置或状态文件，助手必须先备份、事后恢复。本项目至少适用于：

- `pyproject.toml`（Python 依赖/构建配置）
- `client/package.json` 与 `client/pnpm-lock.yaml`（前端依赖锁）
- `client/src-tauri/tauri.conf.json`（Tauri 打包配置）

> 注：原版规则引用的 `tools/manifest.json` / `data/tool-state.json` / `data/workflows.json` 在本项目中不存在，已替换为上述真实文件。

若测试被中断、中止或意外失败，助手必须检查是否有被测试改动过的文件残留，并在继续无关工作或声称完成前恢复它们。

### 诚实规则

如果助手没有完全遵循规定的 superpowers 工作流，必须**直说**。
不得在只遵循了部分协议时，暗示已完全合规。

### 本项目的验证命令速查

| 范围 | 命令 |
|------|------|
| Python 测试 | `python -m pytest` |
| 前端测试 | `cd client && pnpm test` |
| 前端构建 | `cd client && pnpm build` |
| Rust 编译检查 | `cd client/src-tauri && cargo check` |
| 一键构建 | `.\tools\build_tauri.ps1` |

### 技能使用约定

- **UI / CSS / 前端样式 / 交互动效 / 配色** 任务 → 先调用 `ui-ux-pro-max` 技能做设计预研，再落地代码。
- **PDF / DOCX 文档生成** → 先调用 `pdf` / `docx` 技能。
- **不确定用什么技能** → 调用 `find-skills` 查询。
- 用户显式输入 `/<skill-name>` 时，立即用 Skill 工具调用（BLOCKING REQUIREMENT）。

### 任务纪律（本项目补充）

- UI 改动前先 `EnterPlanMode`，方案对齐后再动手。
- 改完必须跑对应验证命令，如实报告结果（不谎报）。
- 按用户指定范围改，不顺手重构；超范围先问。
- 诚实区分"本次引入的问题"与"既有的问题"。
