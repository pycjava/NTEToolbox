param(
    [string] $TargetDir = "",
    [string] $OutputDir = ""
)

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
$clientDir = Join-Path $repoRoot "client"
$srcTauriDir = Join-Path $clientDir "src-tauri"

# ---------------------------------------------------------------------------
# 1. Locate WinLibs MinGW (installed via winget)
# ---------------------------------------------------------------------------
Write-Host "[1/6] Locating WinLibs MinGW ..." -ForegroundColor Cyan

$mingwSearchPaths = @(
    # winget install location (POSIX UCRT)
    Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" `
        -Filter "BrechtSanders.WinLibs.POSIX.UCRT*" -Directory -ErrorAction SilentlyContinue `
        | Select-Object -First 1 -ExpandProperty FullName
)

$mingwBin = $null
foreach ($searchBase in $mingwSearchPaths) {
    if (-not $searchBase) { continue }
    $candidate = Join-Path $searchBase "mingw64\bin"
    if (Test-Path (Join-Path $candidate "gcc.exe")) {
        $mingwBin = $candidate
        break
    }
}

if (-not $mingwBin) {
    throw @"

WinLibs MinGW not found. Install it first:

    winget install BrechtSanders.WinLibs.POSIX.UCRT

"@
}

$env:PATH = "$mingwBin;$env:PATH"
Write-Host "       Found MinGW: $mingwBin"
Write-Host "       gcc  : $((& gcc --version 2>$null | Select-Object -First 1) -replace '\n','')"
Write-Host "       ld   : $((& ld --version 2>$null | Select-Object -First 1) -replace '\n','')"

# ---------------------------------------------------------------------------
# 2. Verify Rust GNU toolchain
# ---------------------------------------------------------------------------
Write-Host "[2/6] Verifying Rust GNU toolchain ..." -ForegroundColor Cyan

$rustupHome = if ($env:RUSTUP_HOME) { $env:RUSTUP_HOME } else { Join-Path $env:USERPROFILE ".rustup" }
$gnuToolchain = "stable-x86_64-pc-windows-gnu"
$installed = & rustup toolchain list 2>$null
if ($installed -notmatch [regex]::Escape($gnuToolchain)) {
    Write-Host "       Installing $gnuToolchain ..."
    Invoke-Step rustup @("toolchain", "install", $gnuToolchain)
}

# Ensure it is the default
$defaultLine = $installed | Where-Object { $_ -match "\(default\)" }
if ($defaultLine -notmatch [regex]::Escape($gnuToolchain)) {
    Write-Host "       Setting $gnuToolchain as default ..."
    Invoke-Step rustup @("default", $gnuToolchain)
}

$rustVer = & rustc --version
Write-Host "       $rustVer ($gnuToolchain)"

# ---------------------------------------------------------------------------
# 3. Set writable target directory (avoids OneDrive sync issues)
# ---------------------------------------------------------------------------
Write-Host "[3/6] Configuring build target directory ..." -ForegroundColor Cyan

if ($TargetDir -eq "") {
    $TargetDir = Join-Path $env:TEMP "ntetoolbox-tauri-target"
}
$TargetDir = [System.IO.Path]::GetFullPath($TargetDir)
$env:CARGO_TARGET_DIR = $TargetDir

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
}
Write-Host "       CARGO_TARGET_DIR = $TargetDir"

# ---------------------------------------------------------------------------
# 4. Build Python agent
# ---------------------------------------------------------------------------
Write-Host "[4/6] Building Python agent ..." -ForegroundColor Cyan

Set-Location $repoRoot

Invoke-Step "python" @("-m", "pip", "install", "-e", ".", "pyinstaller")
Invoke-Step "python" @(".\tools\build_agent.py")

# 清理 pip install -e . 生成的 .egg-info 目录
$eggInfoDir = Join-Path $repoRoot "ntetoolbox.egg-info"
if (Test-Path $eggInfoDir) {
    Remove-Item -Recurse -Force $eggInfoDir
    Write-Host "       Cleaned up $eggInfoDir" -ForegroundColor DarkGray
}

$agentDistExe = Join-Path $repoRoot "dist\agent.exe"
if (-not (Test-Path -LiteralPath $agentDistExe -PathType Leaf)) {
    throw "agent.exe was not built: $agentDistExe"
}

# ---------------------------------------------------------------------------
# 5. Build Tauri app (split: pre-copy DLL → compile → inject DLL → bundle NSIS)
# ---------------------------------------------------------------------------
Set-Location $clientDir
$releaseDir = Join-Path $TargetDir "release"
$genDir = Join-Path $srcTauriDir "gen"
$genDllPath = Join-Path $genDir "WebView2Loader.dll"

# Pre-copy WebView2Loader.dll from any existing build so cargo resource validation passes.
# The correct release DLL will overwrite this after the compile step.
if (-not (Test-Path $genDllPath)) {
    $dllCandidates = @(
        (Join-Path $releaseDir "WebView2Loader.dll"),
        (Join-Path $TargetDir "debug\WebView2Loader.dll"),
        (Join-Path $srcTauriDir "target\debug\WebView2Loader.dll"),
        (Join-Path $srcTauriDir "target\release\WebView2Loader.dll")
    )
    foreach ($candidate in $dllCandidates) {
        if (Test-Path $candidate) {
            New-Item -ItemType Directory -Force -Path $genDir | Out-Null
            Copy-Item -Force $candidate $genDllPath
            Write-Host "       Pre-copied WebView2Loader.dll from $candidate" -ForegroundColor DarkGray
            break
        }
    }
}

# 5a. Compile Rust + frontend, skip NSIS/MSI bundling
Write-Host "[5/7] Building Tauri app (compile only) ..." -ForegroundColor Cyan
$buildStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-Step pnpm @("tauri", "build", "--no-bundle")
$buildStopwatch.Stop()
Write-Host "       Compile completed in $($buildStopwatch.Elapsed.ToString('mm\:ss'))" -ForegroundColor Green

# 5b. Overwrite with the correct release DLL
Write-Host "[6/7] Injecting WebView2Loader.dll (release) ..." -ForegroundColor Cyan
$webviewDllPath = Join-Path $releaseDir "WebView2Loader.dll"
if (Test-Path $webviewDllPath) {
    Copy-Item -Force $webviewDllPath $genDllPath
    Write-Host "       WebView2Loader.dll -> gen/ (release)"
} else {
    Write-Host "       WARNING: WebView2Loader.dll not found at $webviewDllPath" -ForegroundColor Yellow
}

# 5c. Create NSIS installer (cargo build is no-op, only packaging runs)
Write-Host "[7/7] Creating NSIS installer ..." -ForegroundColor Cyan
$nsisStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-Step pnpm @("tauri", "build", "--bundles", "nsis")
$nsisStopwatch.Stop()
Write-Host "       NSIS packaging completed in $($nsisStopwatch.Elapsed.ToString('mm\:ss'))" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 6. Collect output artifacts
# ---------------------------------------------------------------------------
Write-Host "[6/6] Collecting output artifacts ..." -ForegroundColor Cyan

if ($OutputDir -eq "") {
    $OutputDir = Join-Path $repoRoot "dist-tauri"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

$releaseDir = Join-Path $TargetDir "release"
$bundleDir  = Join-Path $TargetDir "release\bundle"

if (-not (Test-Path $releaseDir)) {
    throw "Release directory not found: $releaseDir"
}

# Copy exe
$exePath = Join-Path $releaseDir "MaaToolbox Client.exe"
if (Test-Path $exePath) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    Copy-Item -Force $exePath $OutputDir
    Write-Host "       EXE -> $OutputDir\MaaToolbox Client.exe"
}

# Copy WebView2Loader.dll (required next to exe for GNU toolchain builds)
$webviewDllPath = Join-Path $releaseDir "WebView2Loader.dll"
if (Test-Path $webviewDllPath) {
    Copy-Item -Force $webviewDllPath $OutputDir
    Write-Host "       DLL -> $OutputDir\WebView2Loader.dll"
}

# Copy NSIS / MSI installers if they exist
if (Test-Path $bundleDir) {
    $installers = Get-ChildItem -Path $bundleDir -Recurse -Include "*.exe","*.msi" -ErrorAction SilentlyContinue
    foreach ($installer in $installers) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        Copy-Item -Force $installer.FullName $OutputDir
        Write-Host "       $($installer.Name) -> $OutputDir"
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Build complete!" -ForegroundColor Green
Write-Host " Output: $OutputDir" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
