param(
    [string] $TargetDir = "",
    [string] $OutputDir = "",
    [switch] $PreflightOnly
)

$ErrorActionPreference = "Stop"

function Add-PathDirectory {
    param(
        [string] $Directory
    )

    if ([string]::IsNullOrWhiteSpace($Directory)) {
        return
    }
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return
    }

    $resolved = (Resolve-Path -LiteralPath $Directory).Path
    $pathParts = @($env:PATH -split ";" | Where-Object { $_ -ne "" })
    foreach ($pathPart in $pathParts) {
        try {
            $resolvedPathPart = [System.IO.Path]::GetFullPath($pathPart).TrimEnd("\")
            if ($resolvedPathPart -ieq $resolved.TrimEnd("\")) {
                return
            }
        }
        catch {
            if ($pathPart -ieq $resolved) {
                return
            }
        }
    }

    $env:PATH = "$resolved;$env:PATH"
}

function Resolve-RequiredCommand {
    param(
        [string] $DisplayName,
        [string[]] $Names,
        [string[]] $Candidates = @(),
        [string] $InstallHint = ""
    )

    foreach ($candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            Add-PathDirectory (Split-Path -Parent $candidate)
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source) {
            Add-PathDirectory (Split-Path -Parent $command.Source)
            return $command.Source
        }
    }

    $message = "Required command '$DisplayName' was not found."
    if ($InstallHint -ne "") {
        $message += "`n`n$InstallHint"
    }
    throw $message
}

function Test-Python314 {
    param(
        [string] $Command,
        [string[]] $Arguments = @()
    )

    try {
        $version = & $Command @($Arguments + @(
            "-c",
            "import sys; print('{}.{}.{}'.format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro))"
        )) 2>$null | Select-Object -First 1

        if ($version -match "^(\d+)\.(\d+)\.(\d+)") {
            $parsedVersion = [Version] $Matches[0]
            if ($parsedVersion -ge [Version] "3.14.0") {
                return $Matches[0]
            }
        }
    }
    catch {
        return $null
    }

    return $null
}

function Resolve-Python314 {
    $candidatePaths = @()
    $pythonInstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path -LiteralPath $pythonInstallRoot -PathType Container) {
        $candidatePaths += Get-ChildItem -Path $pythonInstallRoot -Directory -Filter "Python*" -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "python.exe" }
    }
    $candidatePaths += @(
        (Join-Path $env:ProgramFiles "Python314\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python314\python.exe")
    )

    foreach ($candidate in ($candidatePaths | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $version = Test-Python314 -Command $candidate
        if ($version) {
            Add-PathDirectory (Split-Path -Parent $candidate)
            Add-PathDirectory (Join-Path (Split-Path -Parent $candidate) "Scripts")
            return [PSCustomObject] @{
                Command = (Resolve-Path -LiteralPath $candidate).Path
                Arguments = [string[]] @()
                Version = $version
            }
        }
    }

    foreach ($name in @("python.exe", "python")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command -or -not $command.Source) { continue }
        if ($command.Source -match "\\Microsoft\\WindowsApps\\python(3)?\.exe$") { continue }

        $version = Test-Python314 -Command $command.Source
        if ($version) {
            Add-PathDirectory (Split-Path -Parent $command.Source)
            Add-PathDirectory (Join-Path (Split-Path -Parent $command.Source) "Scripts")
            return [PSCustomObject] @{
                Command = $command.Source
                Arguments = [string[]] @()
                Version = $version
            }
        }
    }

    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyLauncher -and $pyLauncher.Source) {
        $version = Test-Python314 -Command $pyLauncher.Source -Arguments @("-3.14")
        if ($version) {
            return [PSCustomObject] @{
                Command = $pyLauncher.Source
                Arguments = [string[]] @("-3.14")
                Version = $version
            }
        }
    }

    throw @"
Python 3.14 or newer was not found.

Install Python 3.14+, or make sure one of these works in PowerShell:

    python --version
    py -3.14 --version

"@
}

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

Add-PathDirectory (Join-Path $env:USERPROFILE ".cargo\bin")
Add-PathDirectory (Join-Path $env:APPDATA "npm")
Add-PathDirectory (Join-Path $env:ProgramFiles "nodejs")

# ---------------------------------------------------------------------------
# 1. Locate WinLibs MinGW
# ---------------------------------------------------------------------------
Write-Host "[1/6] Locating WinLibs MinGW ..." -ForegroundColor Cyan

$mingwBinCandidates = @()
$gccOnPath = Get-Command "gcc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($gccOnPath -and $gccOnPath.Source) {
    $mingwBinCandidates += Split-Path -Parent $gccOnPath.Source
}

$winGetPackageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
if (Test-Path -LiteralPath $winGetPackageRoot -PathType Container) {
    $mingwBinCandidates += Get-ChildItem -Path $winGetPackageRoot `
        -Filter "BrechtSanders.WinLibs.POSIX.UCRT*" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "mingw64\bin" }
}

$mingwBinCandidates += @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_manual\mingw64\bin"),
    "C:\msys64\ucrt64\bin",
    "C:\msys64\mingw64\bin",
    "C:\mingw64\bin"
)

$mingwBin = $null
foreach ($candidate in ($mingwBinCandidates | Where-Object { $_ } | Select-Object -Unique)) {
    if ((Test-Path (Join-Path $candidate "gcc.exe") -PathType Leaf) -and
        (Test-Path (Join-Path $candidate "ld.exe") -PathType Leaf) -and
        (Test-Path (Join-Path $candidate "dlltool.exe") -PathType Leaf)) {
        $mingwBin = $candidate
        break
    }
}

if (-not $mingwBin) {
    throw @"

WinLibs MinGW not found. Install it first:

    winget install BrechtSanders.WinLibs.POSIX.UCRT

Or extract WinLibs POSIX UCRT so mingw64\bin contains gcc.exe, ld.exe, and dlltool.exe.

"@
}

Add-PathDirectory $mingwBin
Write-Host "       Found MinGW: $mingwBin"
Write-Host "       gcc  : $((& gcc --version 2>$null | Select-Object -First 1) -replace '\n','')"
Write-Host "       ld   : $((& ld --version 2>$null | Select-Object -First 1) -replace '\n','')"
Write-Host "       dlltool: $((& dlltool --version 2>$null | Select-Object -First 1) -replace '\n','')"

# ---------------------------------------------------------------------------
# 2. Verify Rust GNU toolchain
# ---------------------------------------------------------------------------
Write-Host "[2/6] Verifying Rust GNU toolchain ..." -ForegroundColor Cyan

$gnuToolchain = "stable-x86_64-pc-windows-gnu"
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
$rustupCommand = Resolve-RequiredCommand `
    -DisplayName "rustup" `
    -Names @("rustup.exe", "rustup") `
    -Candidates @((Join-Path $cargoBin "rustup.exe")) `
    -InstallHint "Install Rust with rustup, or make sure $cargoBin is in PATH."

$installed = & $rustupCommand toolchain list 2>$null
if (-not ($installed -match [regex]::Escape($gnuToolchain))) {
    Write-Host "       Installing $gnuToolchain ..."
    Invoke-Step $rustupCommand @("toolchain", "install", $gnuToolchain)
    $installed = & $rustupCommand toolchain list 2>$null
}

# Ensure it is the default
$defaultLine = $installed | Where-Object { $_ -match "\(default\)" }
if ($defaultLine -notmatch [regex]::Escape($gnuToolchain)) {
    Write-Host "       Setting $gnuToolchain as default ..."
    Invoke-Step $rustupCommand @("default", $gnuToolchain)
}

$rustcCommand = Resolve-RequiredCommand `
    -DisplayName "rustc" `
    -Names @("rustc.exe", "rustc") `
    -Candidates @((Join-Path $cargoBin "rustc.exe")) `
    -InstallHint "Install the $gnuToolchain Rust toolchain with rustup."
$cargoCommand = Resolve-RequiredCommand `
    -DisplayName "cargo" `
    -Names @("cargo.exe", "cargo") `
    -Candidates @((Join-Path $cargoBin "cargo.exe")) `
    -InstallHint "Install the $gnuToolchain Rust toolchain with rustup."

$rustVer = & $rustcCommand --version
$rustHost = & $rustcCommand -vV | Where-Object { $_ -match "^host:" } | Select-Object -First 1
if ($rustHost -notmatch "x86_64-pc-windows-gnu") {
    throw "Active Rust toolchain is not GNU: $rustHost"
}
Write-Host "       $rustVer ($gnuToolchain)"
Write-Host "       cargo: $(& $cargoCommand --version)"

# ---------------------------------------------------------------------------
# 2b. Verify Python and pnpm
# ---------------------------------------------------------------------------
Write-Host "[2b/6] Verifying Python and pnpm ..." -ForegroundColor Cyan

$pythonTool = Resolve-Python314
$pythonCommand = $pythonTool.Command
$pythonArguments = [string[]] @($pythonTool.Arguments)
$pnpmCommand = Resolve-RequiredCommand `
    -DisplayName "pnpm" `
    -Names @("pnpm.cmd", "pnpm") `
    -Candidates @(
        (Join-Path $env:APPDATA "npm\pnpm.cmd"),
        (Join-Path $env:ProgramFiles "nodejs\pnpm.cmd")
    ) `
    -InstallHint "Enable Corepack and activate pnpm: corepack enable; corepack prepare pnpm@11.3.0 --activate"

Write-Host "       python: $($pythonTool.Version) ($pythonCommand $($pythonArguments -join ' '))"
Write-Host "       pnpm  : $(& $pnpmCommand --version) ($pnpmCommand)"

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

if ($PreflightOnly) {
    Write-Host ""
    Write-Host "Preflight checks completed. No build commands were executed." -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# 4. Build Python agent
# ---------------------------------------------------------------------------
Write-Host "[4/6] Building Python agent ..." -ForegroundColor Cyan

Set-Location $repoRoot

Invoke-Step $pythonCommand ($pythonArguments + @("-m", "pip", "install", "-e", ".", "pyinstaller"))
Invoke-Step $pythonCommand ($pythonArguments + @(".\tools\build_agent.py"))

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

# The webview2-com-sys build script copies WebView2Loader.dll into its OUT_DIR/x64/.
# When CARGO_TARGET_DIR is inside %TEMP%, the OS may clean up those files between builds,
# but cargo skips re-running the build script (based on the stale invoked.timestamp).
# Detect this and force a rebuild of webview2-com-sys to regenerate the DLL.
$webview2BuildDirs = Get-ChildItem -Path (Join-Path $TargetDir "release\build") `
    -Directory -Filter "webview2-com-sys-*" -ErrorAction SilentlyContinue
$webview2OutDll = $null
foreach ($dir in $webview2BuildDirs) {
    $candidate = Join-Path $dir.FullName "out\x64\WebView2Loader.dll"
    if (Test-Path $candidate) {
        $webview2OutDll = $candidate
        break
    }
}

if (-not $webview2OutDll) {
    Write-Host "       WebView2Loader.dll missing from build cache, forcing rebuild of webview2-com-sys ..." -ForegroundColor Yellow
    & $cargoCommand @("clean", "-p", "webview2-com-sys", "--release", "--manifest-path", (Join-Path $srcTauriDir "Cargo.toml"))
    if ($LASTEXITCODE -ne 0) {
        Write-Host "       Warning: cargo clean failed, will proceed anyway" -ForegroundColor Yellow
    }
}

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
Invoke-Step $pnpmCommand @("tauri", "build", "--no-bundle")
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
Invoke-Step $pnpmCommand @("tauri", "build", "--bundles", "nsis")
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

# Copy exe (Tauri v2 uses the Cargo package name as the binary name)
$exePath = Join-Path $releaseDir "ntttoolbox-client.exe"
if (Test-Path $exePath) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    Copy-Item -Force $exePath (Join-Path $OutputDir "MaaToolbox Client.exe")
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

# Cleanup PyInstaller's temporary dist output after Tauri has consumed agent.exe.
$agentDistDir = Join-Path $repoRoot "dist"
if (Test-Path -LiteralPath $agentDistDir -PathType Container) {
    $resolvedAgentDistDir = [System.IO.Path]::GetFullPath($agentDistDir).Replace("/", "\").TrimEnd([char[]] "\")
    $resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir).Replace("/", "\").TrimEnd([char[]] "\")
    $outputInsideAgentDist = ($resolvedOutputDir -ieq $resolvedAgentDistDir) -or
        $resolvedOutputDir.StartsWith("$resolvedAgentDistDir\", [System.StringComparison]::OrdinalIgnoreCase)

    if ($outputInsideAgentDist) {
        Write-Host "       Skipped cleanup of $agentDistDir because OutputDir is inside it." -ForegroundColor Yellow
    } else {
        Remove-Item -LiteralPath $agentDistDir -Recurse -Force
        Write-Host "       Cleaned up $agentDistDir" -ForegroundColor DarkGray
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Build complete!" -ForegroundColor Green
Write-Host " Output: $OutputDir" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
