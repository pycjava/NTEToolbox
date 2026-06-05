# 异环工具箱

基于 MaaFramework 的异环自动化工具

完全以后台运行为目的开发，不用担心抢占窗口焦点和键鼠

*模板自 [MaaPracticeBoilerplate](https://github.com/MaaXYZ/MaaPracticeBoilerplate/tree/e454642639415a2c7068b4121c9f61641ec88569)*

## 功能

### 自动钓鱼 🎣

点击 `开始钓鱼` 后进入钓鱼界面，启动该功能即可自动钓鱼

完全支持后台运行，响应很快，正常情况下100%不追踪丢

*如果觉得卡、追踪会超出绿色范围，大概是电脑性能占用满了，把游戏画质调到最低即可解决*

* #### 自动卖鱼买换饵  

  * **关闭**  
    钓到饵用完或者渔获已满判断为完成
  * **开启**  
    一直钓，直到手动终止，卖鱼买换饵过程会**抢占鼠标**

* #### 其他设置

  详见程序内描述

### 弹钢琴 🎹

游戏内先打开钢琴界面，GUI 选项中输入 MIDI 文件的路径，会读取第一个乐器，自动弹钢琴  
（不输入 MIDI 文件路径，会从工作目录扫描 MIDI 文件）

解码 MIDI 文件依赖 [music21](https://github.com/cuthbertLab/music21)  
（安装并更新命令: `python -m pip install -U music21`）

仅使用键盘输入，完全支持后台运行

* 默认键盘输入 API （maafw API）  
  乐谱节拍过快、单位时间内音符过多，会导致延迟超过拍的时间码  
  即使单位时间内音符不多，拍内的音符与音符间也会有延迟

* **使用自定义的 WinAPI**  
  启用该选项能解决延迟问题

### 实时辅助 ⚡

* #### 自动拾取 🧲

  自动判断可拾取物品并快速拾取，适合粉爪等需要按 `F` 拾取的场景

## 下载与使用

> [!IMPORTANT]
> 完整看完下列说明再开始操作

### 下载

在 [Release](https://github.com/op200/NTEToolbox/releases) 中下载最新版本的压缩包

解压后即可使用

### GUI

提供三种 GUI，按需选择：

* #### MaaToolbox Client（新 UI，推荐）

  基于 Tauri v2 + React 的新一代客户端，界面现代、轻量  
  在 [Release](https://github.com/op200/NTEToolbox/releases) 中下载 NSIS 或 MSI 安装包

* #### MFAA

  启动时会自动判断 [.NET](https://dotnet.microsoft.com) 和 [C++](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) 运行时  
  若电脑中没有对应运行时，需按 GUI 给出的提示在微软官网下载或 GUI 自动下载

* #### MXU

  体积小，执行效率也比 MFAA 高  
  如果觉得 MFAA 钓鱼时溜鱼跟随不及时，最好换用这个 GUI  

### 启动

打开文件夹内对应的 GUI 的 exe 文件（Windows）即可启动

*因为要支持后台运行，所以必须**以管理员身份运行**，如果嫌每次都要右键exe麻烦，可以在属性里把该exe设为 `以管理员身份运行此程序`*

**仅支持游戏分辨率比例 16:9**，内部缩放到 720p 处理，所以设置 720p 以上并不会提高识别精度

### 依赖

依赖 Python，自行[安装 Python](https://www.python.org/downloads/) 3.14 或更高版本，Windows 用户安装时记得勾选添加到 PATH

需要安装 Python 包 `maafw`  
（安装并更新命令: `python -m pip install -U maafw`）

*如果发现 GUI 中任务执行到一半没有报错直接失败，那么大概是调用 Python 失败，检查是否正确安装 Python，Windows 用户需要检查是否将 Python 添加到了 PATH 环境变量*

### 配置

* #### 日志

  如果觉得 debug 文件夹体积太大、写入频繁，浪费硬盘，可在 `config/maa_option.json` 中将 `logging` 设为 `false` 以关闭日志（使用 `全局设置` 功能可以让程序修改这个选项）

  提交 issue 仍需要提交日志，所以遇到 bug 时需要打开日志，最好将 `draw_quality` 设为 `100` 以提交更清晰的报错自动截图

## 开发与编译

以下内容用于从源码构建项目。当前仓库覆盖最完整、最推荐的编译目标是 **Windows x64 的 MaaToolbox Client（新 UI）**。传统 MFAA / MXU 打包仍可用，但需要额外准备对应 GUI 的已发布文件。

> [!IMPORTANT]
> 下方命令默认在 PowerShell 中执行。除非命令里写了 `cd client`，否则都在仓库根目录执行。

### 1. 获取源码

```powershell
git clone --recursive https://github.com/op200/NTEToolbox.git
cd NTEToolbox
git submodule update --init --recursive
```

子模块 `assets/MaaCommonAssets` 内含 OCR 模型。若后续 `tools/configure.py` 报找不到 `assets\MaaCommonAssets\OCR`，先重新执行上面的 `git submodule update --init --recursive`。

### 2. 安装编译工具

| 工具 | 建议版本 | 用途 |
|------|----------|------|
| [Git](https://git-scm.com/download/win) | 最新稳定版 | 拉取源码和子模块 |
| [Python](https://www.python.org/downloads/) | >= 3.14 | 运行和打包 Python agent |
| [Node.js](https://nodejs.org/) | >= 18 | 前端构建运行时 |
| [pnpm](https://pnpm.io/) | 11.3.0 | 前端包管理器，本仓库已在 `packageManager` 中锁定 |
| [Rust](https://rustup.rs/) | >= 1.77.2 | Tauri 后端编译 |
| [WinLibs MinGW-w64](https://winlibs.com/) | POSIX UCRT | 本项目使用 `x86_64-pc-windows-gnu` Rust 工具链链接 |
| [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) | 系统自带或最新版 | Tauri 窗口运行时，Windows 10 1803+ / Windows 11 通常已内置 |
| [NSIS](https://nsis.sourceforge.io/Download) / WiX Toolset v3 | 可选 | 生成 Windows 安装包时使用 |

安装 pnpm、Rust GNU 工具链和 WinLibs：

```powershell
corepack enable
corepack prepare pnpm@11.3.0 --activate

rustup toolchain install stable-x86_64-pc-windows-gnu
rustup default stable-x86_64-pc-windows-gnu

winget install BrechtSanders.WinLibs.POSIX.UCRT
```

`tools\build_tauri.ps1` 会自动查找 winget 安装的 WinLibs 并临时加入 `PATH`。如果你要手动运行 `pnpm tauri build`，需要确认 `gcc`、`ld`、`dlltool` 可用：

```powershell
gcc --version
ld --version
dlltool --version
```

如果命令不存在，将 WinLibs 的 `mingw64\bin` 加入系统 `PATH`，或在当前终端临时加入：

```powershell
$winlibs = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Directory -Filter "BrechtSanders.WinLibs.POSIX.UCRT*" |
  Select-Object -First 1 -ExpandProperty FullName
$env:PATH = "$winlibs\mingw64\bin;$env:PATH"
```

### 3. 准备 MaaFramework

`deps` 目录不会随 Git 仓库提交，需要手动下载 MaaFramework 运行时。

1. 打开 [MaaFramework Releases](https://github.com/MaaXYZ/MaaFramework/releases/latest)。
2. 下载 Windows x64 包，文件名通常类似 `MAA-win-x86_64-*.zip`。
3. 解压到仓库的 `deps` 目录，让目录结构变成 `deps\bin`、`deps\share`、`deps\include` 等。

可用下面命令检查是否放对位置：

```powershell
Test-Path .\deps\bin\MaaPiCli.exe
Test-Path .\deps\share\MaaAgentBinary
```

两个命令都应输出 `True`。如果变成了 `deps\MAA-win-x86_64-xxx\bin`，说明多了一层目录，需要把里面的内容移动到 `deps`。

### 4. 准备 Python 和 OCR 资源

```powershell
python -m pip install -U pip
python -m pip install -e . pyinstaller
python .\tools\configure.py
```

`tools\configure.py` 会把 `assets\MaaCommonAssets\OCR\ppocr_v4\zh_cn` 复制到 `assets\resource\model\ocr`。这是构建和运行 Maa 资源时需要的 OCR 模型目录。

如果你的系统里有多个 Python 版本，可以把命令改成明确版本：

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

### 6. 一键串联构建脚本

推荐使用顶层编排脚本。它会先构建新 UI，并自动检测 `MFA\MFAAvalonia.exe` / `MXU\mxu.exe`，把可用的传统 GUI 安装目录和 NSIS 安装包也串起来构建：

```powershell
.\tools\build_all.ps1
```

常用参数：

```powershell
# 只构建新 UI，不处理传统 GUI
.\tools\build_all.ps1 -LegacyGui none

# 只预览将执行哪些构建命令，不真正构建
.\tools\build_all.ps1 -PlanOnly

# 显式构建 MFAA 安装目录和 NSIS 包
.\tools\build_all.ps1 -SkipTauri -LegacyGui mfaa -Version v1.0.0

# 同时尝试构建 MFAA 和 MXU；缺任何一个 GUI 源都会直接报错
.\tools\build_all.ps1 -LegacyGui both -Version v1.0.0
```

`build_all.ps1` 会按需调用：

- `tools\build_tauri.ps1`
- `tools\build_install.ps1`
- `tools\build_nsis.ps1`

如果 `MFA` / `MXU` 目录不存在，默认 `-LegacyGui auto` 会跳过缺失的传统 GUI。若你传入 `-LegacyGui mfaa`、`-LegacyGui mxu` 或 `-LegacyGui both`，缺少对应 GUI exe 会提前失败，避免半路打包出错。

### 7. 只构建新 UI

如果只需要构建 MaaToolbox Client，可直接使用 Tauri 构建脚本：

```powershell
.\tools\build_tauri.ps1
```

该脚本会按顺序执行：

1. 查找 WinLibs MinGW，并临时加入 `PATH`
2. 安装或切换到 `stable-x86_64-pc-windows-gnu`
3. 设置 `CARGO_TARGET_DIR`，默认使用 `%TEMP%\ntetoolbox-tauri-target`，避免 OneDrive 同步目录影响 Rust 构建
4. 安装 Python 包并用 PyInstaller 生成 `dist\agent.exe`
5. 运行 `pnpm tauri build`
6. 将生成的 exe / NSIS / MSI 产物复制到 `dist-tauri`

默认产物：

| 产物 | 路径 |
|------|------|
| 新 UI 可执行文件 | `dist-tauri\MaaToolbox Client.exe` |
| NSIS 安装包 | `dist-tauri\MaaToolbox Client_*_x64-setup.exe` |
| MSI 安装包 | `dist-tauri\MaaToolbox Client_*_x64_en-US.msi` |

可以自定义 Rust 产物目录和最终输出目录：

```powershell
.\tools\build_tauri.ps1 -TargetDir C:\BuildCache\ntetoolbox-tauri-target -OutputDir .\dist-tauri
```

### 8. 手动构建新 UI

需要排查问题或接入 CI 时，可以拆开执行：

```powershell
# 仓库根目录：先打包 Python agent
python .\tools\build_agent.py

# client 目录：构建前端、准备 MaaFramework 运行时、构建 Tauri
cd client
pnpm build
pnpm prepare:maafw
pnpm tauri build
```

`pnpm tauri build` 会自动执行 `pnpm build && pnpm prepare:maafw`，所以上面显式写出 `pnpm prepare:maafw` 主要用于提前检查资源是否准备正确。

> [!WARNING]
> 若没有先生成 `dist\agent.exe`，`pnpm prepare:maafw` 会退回复制 `agent` 源码目录。这样构建出的安装包仍可能依赖用户机器上的 Python 环境，不是完整独立包。发布给普通用户时请使用 `tools\build_tauri.ps1`，或先手动执行 `python .\tools\build_agent.py`。

Tauri 直接构建时，默认产物在：

| 产物 | 路径 |
|------|------|
| 可执行文件 | `client\src-tauri\target\release\MaaToolbox Client.exe` |
| NSIS 安装包 | `client\src-tauri\target\release\bundle\nsis\` |
| MSI 安装包 | `client\src-tauri\target\release\bundle\msi\` |

### 9. 开发模式

```powershell
cd client
pnpm tauri dev
```

开发模式会启动 Vite 热更新和 Tauri 后端。运行 Maa 任务仍需要提前准备：

- `deps\bin\MaaPiCli.exe`
- `assets\resource`
- Python 依赖：`python -m pip install -e .`
- OCR 模型：`python .\tools\configure.py`

### 10. 测试与检查

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

如果需要运行 Rust 格式化，先确保当前 Rust 工具链安装了 rustfmt：

```powershell
rustup component add rustfmt --toolchain stable-x86_64-pc-windows-gnu
cargo fmt
```

### 11. 可选：构建传统 GUI 安装包

传统 MFAA / MXU 打包依赖外部 GUI 文件，不是仅靠本仓库源码就能生成。构建前需要满足：

- `deps\bin` 和 `deps\share` 已按上文准备好
- MFAA：`MFA\MFAAvalonia.exe` 存在
- MXU：`MXU\mxu.exe` 存在
- 已安装 Python 依赖和 PyInstaller

构建安装目录：

```powershell
# MFAA
.\tools\build_install.ps1 -Gui mfaa -Version v1.0.0

# MXU
.\tools\build_install.ps1 -Gui mxu -Version v1.0.0
```

输出目录默认为 `install`。

生成 NSIS 安装包：

```powershell
.\tools\build_nsis.ps1 -Gui mfaa
```

如果 `makensis` 不在 `PATH` 中，可以指定完整路径：

```powershell
.\tools\build_nsis.ps1 -Gui mfaa -Makensis "C:\Program Files (x86)\NSIS\makensis.exe"
```

默认产物：`dist-installer\NTEToolbox-MFAA-Setup.exe` 或 `dist-installer\NTEToolbox-MXU-Setup.exe`。

### 常见问题

#### `MaaFramework files were not found at deps\bin`

没有下载 MaaFramework，或解压后多了一层目录。确认 `.\deps\bin\MaaPiCli.exe` 存在。

#### `gcc` / `ld` / `dlltool` not found

WinLibs MinGW 没装好，或 `mingw64\bin` 不在 `PATH` 中。优先使用 `.\tools\build_tauri.ps1`，脚本会自动查找 winget 安装路径。

#### `pnpm` not recognized

执行：

```powershell
corepack enable
corepack prepare pnpm@11.3.0 --activate
```

然后重新打开终端。

#### `assets\MaaCommonAssets\OCR` 不存在

子模块没有拉取完整。执行：

```powershell
git submodule update --init --recursive
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

#### MSI 打包报 `failed to run light.exe`

MSI 依赖 WiX Toolset v3。Tauri 官方也提示，Windows 上构建 MSI 时需要系统启用 VBSCRIPT 可选功能；如果本机关闭了该功能，需要在“设置 -> 应用 -> 可选功能 -> 更多 Windows 功能”中启用。

#### 在 OneDrive 目录下 Rust 构建异常或很慢

使用脚本参数把 Rust 产物放到非同步目录：

```powershell
.\tools\build_tauri.ps1 -TargetDir C:\BuildCache\ntetoolbox-tauri-target
```
