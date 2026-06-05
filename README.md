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

## 开发

以下内容为开发者准备，普通用户不需要操作

### 拉取

拉取本仓库和子模块:
`git clone --recursive https://github.com/op200/NTEToolbox.git`

更新子模块（若有需要）:
`git submodule update --init --recursive`

*子模块为 `MaaCommonAssets`，内含 OCR 模型文件*

### 依赖

安装 Python 依赖:
使用任意包管理器安装 `pyproject.toml` 中的依赖

复制 OCR 依赖:
执行 `tools/configure.py` 文件

### MaaToolbox Client（新 UI）开发与构建

基于 [Tauri v2](https://v2.tauri.app/) + React 18 + TypeScript + Vite 的桌面客户端。

#### 环境要求

| 工具 | 版本 | 说明 |
|------|------|------|
| [Node.js](https://nodejs.org/) | ≥ 18 | 前端运行时 |
| [pnpm](https://pnpm.io/) | ≥ 8 | 包管理器 |
| [Rust](https://rustup.rs/) | ≥ 1.77 | Rust 编译器，需安装 `x86_64-pc-windows-gnu` 工具链 |
| [MinGW-w64](https://winlibs.com/) | — | GNU C 工具链（gcc、ld、dlltool），提供链接器 |

#### 环境搭建

```bash
# 1. 安装 Rust GNU 工具链
rustup toolchain install stable-x86_64-pc-windows-gnu
rustup default stable-x86_64-pc-windows-gnu

# 2. 安装 MinGW（提供 gcc/ld/dlltool）
#    方式一：通过 winget
winget install BrechtSanders.WinLibs.POSIX.UCRT
#    方式二：从 https://winlibs.com/ 下载，解压后将 bin 目录加入 PATH

# 3. 安装前端依赖
cd client
pnpm install
```

#### 开发模式

```bash
cd client
pnpm tauri dev
```

启动 Vite 开发服务器（热更新）和 Rust 后端（自动重编译）。

#### 构建发布包

```bash
cd client

# 构建 Debug 版本（快速，用于调试）
pnpm tauri build --debug

# 构建 Release 版本（优化体积和性能）
pnpm tauri build
```

构建产出物：

| 产出 | 路径 |
|------|------|
| 可执行文件 | `client/src-tauri/target/debug/ntetoolbox-client.exe`（debug）或 `target/release/` |
| NSIS 安装包 | `client/src-tauri/target/{debug\|release}/bundle/nsis/MaaToolbox Client_*_x64-setup.exe` |
| MSI 安装包 | `client/src-tauri/target/{debug\|release}/bundle/msi/MaaToolbox Client_*_x64_en-US.msi` |

#### 前端测试

```bash
cd client
pnpm test
```

#### 注意事项

- 确保 MinGW 的 `bin` 目录在系统 PATH 中，否则 Rust 编译链接会失败
- 构建 Release 版本时间较长（首次约 10+ 分钟），后续增量编译只需几十秒
- 静态资源（图片等）请放在 `client/public/` 目录，Vite 会原样复制到构建产物中

### 完整打包流程

本项目打包分为三部分：**Python Agent**、**GUI 前端**、**安装包**。

#### 1. 打包 Python Agent

依赖 [PyInstaller](https://pyinstaller.org/)，将 Python 自动化脚本打包为独立 `agent.exe`：

```bash
# 在项目根目录
pip install -e . pyinstaller
python tools/build_agent.py
```

产出物：`dist/agent.exe`

#### 2. 构建 MaaToolbox Client（新 UI）

参见上方「构建发布包」章节。

#### 3. 构建传统 GUI 安装包（MFAA / MXU）

使用 PowerShell 脚本自动化打包：

```powershell
# 构建 MFAA 版本安装目录
tools\build_install.ps1 -Gui mfaa -Version 1.0.0

# 或构建 MXU 版本安装目录
tools\build_install.ps1 -Gui mxu -Version 1.0.0
```

该脚本会自动：
1. 验证 `deps\bin`（MaaFramework）存在
2. 复制 GUI 前端文件
3. 调用 PyInstaller 打包 `agent.exe`
4. 执行 `tools\install.py` 组装安装目录

#### 4. 生成 NSIS 安装包

```powershell
# 将安装目录打包为 NSIS 安装程序
tools\build_nsis.ps1 -Gui mfaa

# 指定安装目录和输出目录
tools\build_nsis.ps1 -Gui mfaa -InstallDir .\install -OutputDir .\dist-installer
```

产出物：`dist-installer/NTEToolbox-MFAA-Setup.exe`

#### 前置依赖汇总

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| Python ≥ 3.14 | Agent 运行时 | [python.org](https://www.python.org/downloads/) |
| PyInstaller | 打包 agent.exe | `pip install pyinstaller` |
| MaaFramework | 自动化引擎 | 下载到 `deps\bin` |
| Node.js + pnpm | 新 UI 前端构建 | [nodejs.org](https://nodejs.org/) |
| Rust (GNU) + MinGW | 新 UI 后端编译 | [rustup.rs](https://rustup.rs/) + winget |
| NSIS (makensis) | Windows 安装包 | [nsis.sourceforge.io](https://nsis.sourceforge.io/) |
| .NET Desktop Runtime | MFAA GUI 运行时 | 安装时自动下载 |
