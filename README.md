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

解码 MIDI 文件依赖 [music21](https://github.com/cuthbertLab/music21)  
（安装并更新命令: `python -m pip install -U music21`）

* #### 键盘输入模式

  完全支持后台运行

  乐谱节拍过快、单位时间内键过多，会导致延迟

  * **使用自定义的 WinAPI**  
    启用该选项能解决延迟问题

<!-- * #### 鼠标输入模式

  完全前台运行

  ***功能未做*** -->

## 下载与使用

> [!IMPORTANT]
> 完整看完下列说明再开始操作

### 下载

在 [Release](https://github.com/op200/NTEToolbox/releases) 中下载最新版本的压缩包

解压后即可使用

### GUI

目前会自动打包 MFAA 和 MXU 两种 GUI，觉得哪个好用就用哪个

* #### MFAA

  启动时会自动判断 [.NET](https://dotnet.microsoft.com) 和 [C++](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) 运行时  
  若电脑中没有对应运行时，需按 GUI 给出的提示在微软官网下载或 GUI 自动下载

* #### MXU

  体积小，执行效率也比 MFAA 高  
  如果觉得 MFAA 钓鱼时溜鱼跟随不及时，最好换用这个 GUI  
  （这个 GUI 没有检查更新功能）

### 启动

打开文件夹内对应的 GUI 的 exe 文件（Windows）即可启动

*因为要支持后台运行，所以必须**以管理员身份运行**，如果嫌每次都要右键exe麻烦，可以在属性里把该exe设为 `以管理员身份运行此程序`*

**仅支持游戏分辨率比例 16:9**，内部缩放到 720p 处理，所以设置 720p 以上并不会提高识别精度

### 依赖

依赖 Python，自行[安装 Python](https://www.python.org/downloads/) 3.14 或更高版本，Windows 用户安装时记得勾选添加到 PATH

需要安装 Python 包 `maafw`  
（安装并更新命令: `python -m pip install -U maafw`）

*如果发现 GUI 中任务执行到一半直接失败，那么大概是调用 Python 失败*

### 配置

* #### 日志

  如果觉得 debug 文件夹体积太大、写入频繁，浪费硬盘，可在 `config/maa_option.json` 中将 `logging` 设为 `false` 以关闭日志

  提交 issue 仍需要提交日志，所以遇到 bug 时需要打开日志，最好将 `draw_quality` 设为 `100` 以提交更清晰的报错自动截图
