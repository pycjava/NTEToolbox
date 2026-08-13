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
│   ├── configure.py    #   OCR 模型准备
│   ├── run_rust_tests.sh        #   sandbox 专用 cargo test wrapper（真机/CI 不需要）
│   └── patch_test_manifest.py   #   sandbox 专用：Rust 测试 exe 注入 comctl32 v6 manifest
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
4. `pip install -e ".[hearthstone]" pyinstaller` + `tools/build_agent.py` → `dist/agent.exe`
5. `tools/build_hscoachd.py` → `dist/hscoachd/`（炉石教练 headless 后端，含离线卡库）
6. `cd client && pnpm tauri build`（内含 `pnpm build && pnpm prepare:maafw`，后者把 `dist/hscoachd/` 复制进 `gen/hscoach/`）
7. 复制产物到 `dist-tauri/`

### 构建产物

| 产物 | 路径 |
|------|------|
| 可执行文件 | `dist-tauri\NTEToolbox.exe` |
| WebView2Loader.dll | `dist-tauri\WebView2Loader.dll`（必须和 exe 同目录） |
| NSIS 安装包 | `dist-tauri\NTEToolbox_*_x64-setup.exe` |
| MSI 安装包 | 不生成（默认仅 NSIS） |
| 异环 agent | `dist\agent.exe` |
| 炉石教练后端 | `dist\hscoachd\hscoachd.exe`（客户端内置） |

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
python -m pip install -e ".[hearthstone]" pyinstaller
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
