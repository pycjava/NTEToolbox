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

$agentDistExe = Join-Path $repoRoot "dist\agent.exe"
if (-not (Test-Path -LiteralPath $agentDistExe -PathType Leaf)) {
    throw "agent.exe was not built: $agentDistExe"
}

# ---------------------------------------------------------------------------
# 5. Build Tauri app
# ---------------------------------------------------------------------------
Write-Host "[5/6] Building Tauri app (pnpm tauri build) ..." -ForegroundColor Cyan

Set-Location $clientDir

$buildStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-Step pnpm @("tauri", "build")
$buildStopwatch.Stop()

Write-Host "       Build completed in $($buildStopwatch.Elapsed.ToString('mm\:ss'))" -ForegroundColor Green

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
