# 异环工具箱

基于 MaaFramework 的《异环》自动化工具。当前主界面是 **MaaToolbox Client**，使用 Tauri v2 + React 构建，后端通过 MaaPiCli 调用 Python agent 和 Maa 资源。

项目主要面向 Windows x64。仓库内仍保留 MaaFramework 支持的多控制器声明，但当前开发、构建和发布说明都以 Windows 客户端为准。

*模板参考 [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate/tree/e454642639415a2c7068b4121c9f61641ec88569)。*

## 功能

### MaaToolbox Client

- 自动读取 `assets/interface.jsonc` 中的任务、选项和控制器配置。
- 支持选择目标游戏窗口，默认匹配窗口标题为 `异环` 或 `NTE` 的 `UnrealWindow`。
- 支持实时画面预览，用于确认窗口选择和截图状态。
- 任务配置会保存到客户端配置文件，重启后恢复。
- 日志默认写入程序目录下的 `debug` 文件夹；如果该目录不可写，会写入 Tauri 本地数据目录的 `maa-runtime\debug`。

### 自动钓鱼

进入游戏钓鱼界面后启动任务，可自动钓鱼和溜鱼。

可配置项：

- 终止时间：30 分钟到 12 小时可选，关闭后按任务自身结束条件停止。
- 溜鱼中点停顿范围和停顿时间。
- 自动卖鱼买换饵：无饵或满舱时按顺序执行卖鱼、买饵、换饵。该流程涉及点击操作，会抢占鼠标。
- 买饵次数：`n` 表示购买 `n * 99` 个饵。

如果追踪经常超出绿色范围，通常是画面识别或机器负载问题，可以先降低游戏画质并确认游戏画面比例为 16:9。

### 弹钢琴

在游戏内打开钢琴界面后启动任务，支持读取 MIDI 文件并使用键盘输入演奏。

可配置项：

- MIDI 文件路径：支持 `.mid` 和 `.midi`。不填写时会从当前工作目录扫描第一个 MIDI 文件。
- 默认 BPM。
- 钢琴模式：`21` 或 `36`。
- 超时模式：`同步时轴` 或 `速率不变`。
- 自定义 WinAPI：默认开启，用于降低键盘输入延迟；会造成指针光标闪烁，但不会抢占鼠标。

MIDI 解析依赖 `music21`，源码运行时由 Python 项目依赖安装；发布版会随 `agent.exe` 一起打包。

### 实时辅助

实时辅助当前包含：

- 自动拾取：识别画面中的可拾取文本后自动按 `F`。
- 永远拾取：不判断画面内容，持续拾取；按住 `F` 时暂停自动拾取。适合粉爪等场景，注意避开盔甲等交互项。
- S 级鱼截图：识别到金色背景光和 S 图标时自动保存截图。
- 截图保存目录和冷却时间可配置，默认目录为 `screenshots/s_fish`。

## 下载与使用

在 [Release](https://github.com/op200/NTEToolbox/releases) 下载最新发布包。

当前仓库默认构建 **NSIS 安装包** 和便携运行需要的 exe/dll 文件，不再默认生成 MSI。普通用户优先使用安装包；如果直接运行便携 exe，确保 `WebView2Loader.dll` 和 `MaaToolbox Client.exe` 在同一目录。

发布版已包含 MaaFramework 运行资源和打包后的 `agent.exe`。普通用户不需要额外安装 Python、`maafw` 或 `music21`。

### 启动

1. 以管理员身份运行 `MaaToolbox Client.exe`。后台窗口控制和部分截图/输入方式需要管理员权限。
2. 在客户端中选择控制器和目标游戏窗口。
3. 确认实时画面预览正常。
4. 根据需要配置全局设置或具体任务。
5. 启动对应任务。

注意事项：

- 游戏画面比例需要为 16:9。内部会按 720p 识别，设置高于 720p 不一定提高识别精度。
- 默认 Windows 控制器使用 PostMessage 后台输入；部分流程仍可能抢占鼠标，文档和界面中会注明。
- WebView2 Runtime 通常已随 Windows 10 1803+ / Windows 11 内置；如果客户端无法启动，可安装最新版 WebView2 Runtime。

## 项目结构

```text
NTEToolbox/
├── agent/                  # Python agent，自定义动作和核心任务逻辑
├── assets/
│   ├── interface.jsonc      # Maa 项目接口，定义任务、选项、控制器
│   ├── resource/            # Maa pipeline、图片和 OCR 运行资源
│   └── MaaCommonAssets/     # OCR 模型子模块
├── client/                  # Tauri v2 + React 客户端
│   ├── src/                 # React/TypeScript 前端
│   ├── src-tauri/           # Rust/Tauri 后端
│   └── scripts/             # Maa 运行资源准备脚本
├── deps/                    # MaaFramework 运行时，手动下载，不入 Git
├── dist/                    # PyInstaller 输出，主要是 agent.exe
├── dist-tauri/              # build_tauri.ps1 汇总后的客户端产物
├── tests/                   # Python 测试
├── tools/                   # 构建和配置脚本
├── pyproject.toml           # Python 包配置，Python >= 3.14
└── package.json             # 根 pnpm 工具依赖
```

## 从源码构建

以下命令默认在 PowerShell 中执行。除非命令里写了 `cd client`，否则都在仓库根目录执行。

### 1. 获取源码

```powershell
git clone --recursive https://github.com/op200/NTEToolbox.git
cd NTEToolbox
git submodule update --init --recursive
```

`assets/MaaCommonAssets` 子模块内含 OCR 模型。若后续 `tools\configure.py` 报找不到 `assets\MaaCommonAssets\OCR`，重新执行：

```powershell
git submodule update --init --recursive
```

### 2. 安装构建工具

| 工具 | 建议版本 | 用途 |
|------|----------|------|
| [Git](https://git-scm.com/download/win) | 最新稳定版 | 拉取源码和子模块 |
| [Python](https://www.python.org/downloads/) | >= 3.14 | 运行和打包 Python agent |
| [Node.js](https://nodejs.org/) | >= 18 | 前端构建运行时 |
| [pnpm](https://pnpm.io/) | 11.3.0 | 前端包管理器 |
| [Rust](https://rustup.rs/) | >= 1.77.2 | Tauri 后端编译 |
| [WinLibs MinGW-w64](https://winlibs.com/) | POSIX UCRT | GNU Rust 工具链链接器 |
| [NSIS](https://nsis.sourceforge.io/Download) | 最新稳定版 | 默认安装包生成 |
| [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) | 系统自带或最新版 | Tauri 窗口运行时 |

启用 pnpm、安装 Rust GNU 工具链和 WinLibs：

```powershell
corepack enable
corepack prepare pnpm@11.3.0 --activate

rustup toolchain install stable-x86_64-pc-windows-gnu
rustup default stable-x86_64-pc-windows-gnu

winget install BrechtSanders.WinLibs.POSIX.UCRT
```

`tools\build_tauri.ps1` 会自动查找 winget 安装的 WinLibs 并临时加入 `PATH`。如果手动运行 `pnpm tauri build`，需要确认这些命令可用：

```powershell
gcc --version
ld --version
dlltool --version
```

如果命令不存在，可以在当前终端临时加入 WinLibs：

```powershell
$winlibs = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Directory -Filter "BrechtSanders.WinLibs.POSIX.UCRT*" |
  Select-Object -First 1 -ExpandProperty FullName
$env:PATH = "$winlibs\mingw64\bin;$env:PATH"
```

### 3. 准备 MaaFramework

`deps` 目录不会随 Git 仓库提交，需要手动下载 MaaFramework Windows x64 运行时。

1. 打开 [MaaFramework Releases](https://github.com/MaaXYZ/MaaFramework/releases/latest)。
2. 下载 Windows x64 包，文件名通常类似 `MAA-win-x86_64-*.zip`。
3. 解压到仓库的 `deps` 目录，让 `deps\bin\MaaPiCli.exe` 存在。

检查：

```powershell
Test-Path .\deps\bin\MaaPiCli.exe
```

命令应输出 `True`。如果路径变成 `deps\MAA-win-x86_64-xxx\bin\MaaPiCli.exe`，说明多了一层目录，需要把里面的内容移动到 `deps`。

### 4. 准备 Python 和 OCR 资源

```powershell
python -m pip install -U pip
python -m pip install -e . pyinstaller
python .\tools\configure.py
```

`tools\configure.py` 会把 `assets\MaaCommonAssets\OCR\ppocr_v4\zh_cn` 复制到 `assets\resource\model\ocr`。

如果系统里有多个 Python 版本，建议明确使用 3.14：

```powershell
py -3.14 -m pip install -e . pyinstaller
py -3.14 .\tools\configure.py
```

### 5. 安装前端依赖

```powershell
cd client
pnpm install --frozen-lockfile
cd ..
```

### 6. 一键构建

推荐直接使用：

```powershell
.\tools\build_tauri.ps1
```

主要流程：

1. 查找 WinLibs MinGW，并临时加入 `PATH`。
2. 安装或切换到 `stable-x86_64-pc-windows-gnu`。
3. 验证 Python 3.14+ 和 pnpm。
4. 设置 `CARGO_TARGET_DIR`，默认使用 `%TEMP%\ntetoolbox-tauri-target`，避免 OneDrive 同步目录影响 Rust 构建。
5. 安装 Python 包并用 PyInstaller 生成 `dist\agent.exe`。
6. 执行 Tauri compile-only 构建，注入 release 版 `WebView2Loader.dll`。
7. 生成 NSIS 安装包，并把产物复制到 `dist-tauri`。

默认产物：

| 产物 | 路径 |
|------|------|
| 客户端 exe | `dist-tauri\MaaToolbox Client.exe` |
| WebView2Loader.dll | `dist-tauri\WebView2Loader.dll` |
| NSIS 安装包 | `dist-tauri\MaaToolbox Client_*_x64-setup.exe` |
| Python agent | `dist\agent.exe` |

可自定义 Rust 产物目录和输出目录：

```powershell
.\tools\build_tauri.ps1 -TargetDir C:\BuildCache\ntetoolbox-tauri-target -OutputDir .\dist-tauri
```

只做环境预检查：

```powershell
.\tools\build_tauri.ps1 -PreflightOnly
```

顶层编排脚本当前主要用于调用 Tauri 构建：

```powershell
.\tools\build_all.ps1
.\tools\build_all.ps1 -PlanOnly
.\tools\build_all.ps1 -TauriTargetDir C:\BuildCache\ntetoolbox-tauri-target -TauriOutputDir .\dist-tauri
```

### 7. 手动构建

调试时可以拆开执行：

```powershell
# 仓库根目录：先打包 Python agent
python .\tools\build_agent.py

# client 目录：构建前端、准备 MaaFramework 运行时、构建 Tauri
cd client
pnpm build
pnpm prepare:maafw
pnpm tauri build
```

`pnpm tauri build` 会通过 `tauri.conf.json` 自动执行 `pnpm build && pnpm prepare:maafw`。显式执行 `pnpm prepare:maafw` 主要用于提前检查 `deps`、`assets\resource` 和 `dist\agent.exe` 是否准备正确。

> [!WARNING]
> 若没有先生成 `dist\agent.exe`，`pnpm prepare:maafw` 会退回复制 `agent` 源码目录。这样适合开发调试，但发布给普通用户前应使用 `tools\build_tauri.ps1` 生成完整独立包。

当前 `tauri.conf.json` 默认只启用 `nsis` bundle，不默认生成 MSI。

## 开发模式

```powershell
cd client
pnpm tauri dev
```

开发模式会启动 Vite 热更新和 Tauri 后端。运行 Maa 任务前仍需要准备：

- `deps\bin\MaaPiCli.exe`
- `assets\resource`
- Python 依赖：`python -m pip install -e .`
- OCR 模型：`python .\tools\configure.py`

如果已经存在 `dist\agent.exe`，开发运行时会优先使用打包后的 agent；否则会使用源码目录和本机 Python 环境。

## 测试与检查

常用检查命令：

```powershell
# Python 测试
python -m pytest

# 前端测试和构建
cd client
pnpm test
pnpm build
pnpm prepare:maafw

# Rust 编译检查
cd src-tauri
cargo check
```

Rust 格式化：

```powershell
rustup component add rustfmt --toolchain stable-x86_64-pc-windows-gnu
cargo fmt
```

## 日志与配置

- 客户端配置保存为 Tauri 应用配置目录下的 `client-config.json`。
- 程序优先在 exe 同目录写入 `debug`。如果不可写，会写入 Tauri 本地数据目录下的 `maa-runtime\debug`。
- Maa 运行时会在内部生成 `config\maa_pi_config.json`。
- 全局设置中的日志开关本质上会修改 Maa 运行时的 `config\maa_option.json`，部分设置需要重启任务或客户端后生效。
- 提交 issue 时建议附带 `debug` 目录内日志。

## 常见问题

#### `MaaFramework files were not found` 或找不到 `MaaPiCli.exe`

没有下载 MaaFramework，或解压后多了一层目录。确认下面命令输出 `True`：

```powershell
Test-Path .\deps\bin\MaaPiCli.exe
```

#### `assets\MaaCommonAssets\OCR` 不存在

子模块没有拉取完整。执行：

```powershell
git submodule update --init --recursive
```

然后重新运行：

```powershell
python .\tools\configure.py
```

#### `gcc` / `ld` / `dlltool` not found

WinLibs MinGW 没装好，或 `mingw64\bin` 不在 `PATH` 中。优先使用 `.\tools\build_tauri.ps1`，脚本会自动查找 winget 安装路径。

#### `pnpm` not recognized

执行：

```powershell
corepack enable
corepack prepare pnpm@11.3.0 --activate
```

然后重新打开终端。

#### Python 版本不对

本项目要求 Python 3.14 或更高版本。多 Python 环境下优先使用：

```powershell
py -3.14 --version
py -3.14 -m pip install -e . pyinstaller
```

#### 直接 `pnpm tauri build` 后，安装包仍要求用户安装 Python

构建前缺少 `dist\agent.exe`。先运行：

```powershell
python .\tools\build_agent.py
```

或改用：

```powershell
.\tools\build_tauri.ps1
```

#### 直接运行 exe 时提示缺少 `WebView2Loader.dll`

GNU 工具链构建出的便携 exe 需要 `WebView2Loader.dll` 位于同一目录。使用 `dist-tauri` 中汇总后的 exe/dll，或使用 NSIS 安装包。

#### PyInstaller 报 `PermissionError: [WinError 5] 拒绝访问`

如果 `.\tools\build_tauri.ps1` 或 `python .\tools\build_agent.py` 在清理 `build\pyinstaller\agent\localpycs` 等目录时报：

```text
PermissionError: [WinError 5] 拒绝访问: '...\build\pyinstaller\agent\localpycs'
Command failed with exit code 1: C:\WINDOWS\py.exe -3.14 .\tools\build_agent.py
```

这通常不是源码逻辑错误，而是 Windows 文件锁或权限问题。常见原因包括 Python/PyInstaller/agent 进程未退出、OneDrive 正在同步构建目录，或安全软件正在扫描 PyInstaller 生成的文件。

先确认没有相关进程占用：

```powershell
Get-Process python,pyinstaller,agent -ErrorAction SilentlyContinue
```

如果确认没有正在运行的构建或程序，删除 PyInstaller 构建缓存后重试：

```powershell
Remove-Item -LiteralPath .\build\pyinstaller -Recurse -Force
.\tools\build_tauri.ps1
```

如果项目位于 OneDrive 目录并且问题反复出现，建议暂停 OneDrive 同步，或把仓库移动到非同步目录，例如 `C:\dev\NTEToolbox` 后再构建。

#### 在 OneDrive 目录下 Rust 构建异常或很慢

`build_tauri.ps1` 默认把 Rust 产物放到 `%TEMP%\ntetoolbox-tauri-target`。也可以手动指定非同步目录：

```powershell
.\tools\build_tauri.ps1 -TargetDir C:\BuildCache\ntetoolbox-tauri-target
```

#### NSIS 安装包生成失败

确认本机已安装 NSIS，并且 `makensis.exe` 可用。也可以先运行：

```powershell
cd client
pnpm tauri build --no-bundle
```

只验证前端和 Rust 程序是否能编译。

## 许可证

本项目使用 `AGPL-3.0-or-later` 许可证，详见 [LICENSE](./LICENSE)。
