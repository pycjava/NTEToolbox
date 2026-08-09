#!/usr/bin/env bash
# sandbox 专用：cargo test --release --lib 的 wrapper。
#
# 背景：本环境是 stripped Windows image，System32 的 comctl32 是 v5；
# cargo 链接的 lib 测试二进制不带 tauri-winres 的 comctl32 v6 manifest，
# 加载 v5 后 TaskDialogIndirect 缺失 → 0xc0000139 启动即崩。
# 方案：--no-run 链接后给测试 exe 注入 v6 manifest，再直接运行（不经
# cargo，避免 cargo 检测 exe 被外部修改而重新链接覆盖 patch）。
#
# 真机 / CI（完整 Windows）不需要此脚本，直接 `cargo test --release --lib`。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/client/src-tauri"

# 本环境 PATH 精简，cargo 在 ~/.cargo/bin，cmd 用全路径
export PATH="$HOME/.cargo/bin:$PATH"
CMD=/c/Windows/System32/cmd.exe

cargo test --release --lib --no-run "$@" > /dev/null 2>&1
# 只匹配 16 位 hash 的测试 exe（排除任何带额外后缀的副本），用绝对路径
EXE=$(ls -t "$(pwd)"/target/release/deps/ntetoolbox_client_lib-????????????????.exe | head -1)
python "$ROOT/tools/patch_test_manifest.py" "$EXE"
# MSYS bash 对 Windows console 程序经管道的输出不可靠，经 PowerShell 调用
# （& 直接调用，输出与退出码都可靠）。
EXE_WIN=$(cygpath -w "$EXE")
PWSH=/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
if [ $# -gt 0 ]; then
  "$PWSH" -NoProfile -Command "& '$EXE_WIN' $*"
else
  "$PWSH" -NoProfile -Command "& '$EXE_WIN'"
fi
