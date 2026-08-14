# 炉石教练成品构建脚本：PyInstaller 打包 → 预置离线卡牌库 → 打 zip
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\build_hscoach.ps1
#
# 产物：
#   dist\HsCoach\               可运行目录（双击 HsCoach.exe）
#   dist\HsCoach-<版本>-win64.zip  便携版压缩包
#
# 依赖：python 环境需能 import hslog/httpx（缺则本脚本先装），PyInstaller 自动安装。

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string] $Command,
        [string[]] $Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distDir = Join-Path $repoRoot "dist"
$appDir = Join-Path $distDir "HsCoach"

# 1. 依赖就绪：base + hearthstone extra（本项目运行时依赖）+ PyInstaller。
#    统一走 pyproject.toml 的 extra，与 build_tauri.ps1 一致，显式装齐
#    hslog/httpx/hearthstone（hearthstone 由 hslog 传递，但代码直接
#    import hearthstone.enums，故用 extra 一并兜住，避免漏装）。
#    注意：不要写 "hslog>=1.19.0" 这类带 > 的参数——PowerShell 5.1 会把
#    原生命令参数里的 > 当成重定向，在 CWD 生成一个 "0.27" 垃圾文件。
Set-Location $repoRoot
Invoke-Step "python" @("-m", "pip", "install", "-e", ".[hearthstone]")
Invoke-Step "python" @("-m", "pip", "install", "pyinstaller")

# 清理 pip install -e . 生成的 .egg-info 目录
$eggInfoDir = Join-Path $repoRoot "ntetoolbox.egg-info"
if (Test-Path $eggInfoDir) {
    Remove-Item -Recurse -Force $eggInfoDir
    Write-Host "       Cleaned up $eggInfoDir" -ForegroundColor DarkGray
}

# 2. PyInstaller 构建（onedir）
Set-Location $repoRoot
Invoke-Step "python" @(".\tools\build_hscoach.py")

if (-not (Test-Path -LiteralPath (Join-Path $appDir "HsCoach.exe") -PathType Leaf)) {
    throw "Build succeeded but HsCoach.exe is missing: $appDir"
}

# 3. 预置离线卡牌库（exe 旁 data/，冻结模式下 CardDatabase 从这里读，
#    首次运行无需联网下载）
$cardCacheDir = Join-Path $repoRoot "hscoach\data"
$appDataDir = Join-Path $appDir "data"
if (Test-Path -LiteralPath $cardCacheDir -PathType Container) {
    New-Item -ItemType Directory -Force -Path $appDataDir | Out-Null
    Copy-Item -Force -Path (Join-Path $cardCacheDir "cards.*.json") -Destination $appDataDir
    Write-Host "Card database bundled: $appDataDir"
}

# 4. 打 zip（便携版成品）
$version = python -c "import sys; sys.path.insert(0, r'$repoRoot'); from hscoach._version import __version__; print(__version__)"
$zipPath = Join-Path $distDir "HsCoach-$version-win64.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -Force -LiteralPath $zipPath
}
Compress-Archive -Path $appDir -DestinationPath $zipPath

Write-Host ""
Write-Host "成品构建完成："
Write-Host "  可运行目录：$appDir"
Write-Host "  便携压缩包：$zipPath"
Write-Host ""
Write-Host "使用：解压后双击 HsCoach.exe，首次运行按提示输入 API key"
Write-Host "（模型/API 地址可在悬浮窗的 ⚙设置 里修改，保存即生效）"
