param(
    [ValidateSet('mfaa', 'mxu')]
    [string] $Gui = "mfaa",

    [string] $Version = "v0.0.0",
    [string] $GuiSourceDir = "",
    [string] $InstallDir = ""
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

function Resolve-RepoRelativePath {
    param(
        [string] $Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

function Get-TrimmedPath {
    param(
        [string] $Path
    )

    return ([System.IO.Path]::GetFullPath($Path)).TrimEnd([char[]] @('\', '/'))
}

function Assert-SafeInstallDir {
    param(
        [string] $Path
    )

    $installPath = Get-TrimmedPath $Path
    $repoPath = Get-TrimmedPath $repoRoot
    $driveRoot = ([System.IO.Path]::GetPathRoot($installPath)).TrimEnd([char[]] @('\', '/'))

    if ($installPath -eq $driveRoot) {
        throw "Refusing to delete drive root as install directory: $Path"
    }
    if ($installPath -eq $repoPath) {
        throw "Refusing to delete repository root as install directory: $Path"
    }
    if ($GuiSourceDir -ne "") {
        $guiPath = Get-TrimmedPath $GuiSourceDir
        if ($installPath -eq $guiPath) {
            throw "Refusing to use GUI source directory as install directory: $Path"
        }
    }
}

function Clear-IntermediateArtifacts {
    $pyinstallerBuildDir = Join-Path $repoRoot "build\pyinstaller"
    if (Test-Path -LiteralPath $pyinstallerBuildDir) {
        Remove-Item -Recurse -Force -LiteralPath $pyinstallerBuildDir
    }

    $agentDistExe = Join-Path $repoRoot "dist\agent.exe"
    if (Test-Path -LiteralPath $agentDistExe) {
        Remove-Item -Force -LiteralPath $agentDistExe
    }

    Get-ChildItem -LiteralPath $repoRoot -Filter "*.egg-info" -Directory -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ($InstallDir -eq "") {
    $InstallDir = Join-Path $repoRoot "install"
}
$InstallDir = Resolve-RepoRelativePath $InstallDir
if ($GuiSourceDir -eq "") {
    $GuiSourceDir = switch ($Gui) {
        "mfaa" { Join-Path $repoRoot "MFA" }
        "mxu" { Join-Path $repoRoot "MXU" }
    }
}

$guiExe = switch ($Gui) {
    "mfaa" { "MFAAvalonia.exe" }
    "mxu" { "mxu.exe" }
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "deps\bin") -PathType Container)) {
    throw "MaaFramework files were not found at deps\bin. Download and extract MaaFramework before building install."
}

if (-not (Test-Path -LiteralPath $GuiSourceDir -PathType Container)) {
    throw "GUI source directory does not exist: $GuiSourceDir"
}
$GuiSourceDir = (Resolve-Path -LiteralPath $GuiSourceDir).Path

$sourceGuiExe = Join-Path $GuiSourceDir $guiExe
if (-not (Test-Path -LiteralPath $sourceGuiExe -PathType Leaf)) {
    throw "Selected GUI executable does not exist: $sourceGuiExe"
}

Set-Location $repoRoot

Clear-IntermediateArtifacts
Assert-SafeInstallDir -Path $InstallDir

try {
    if (Test-Path -LiteralPath $InstallDir) {
        Remove-Item -Recurse -Force -LiteralPath $InstallDir
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

    Copy-Item -Recurse -Force -Path (Join-Path $GuiSourceDir "*") -Destination $InstallDir

    Invoke-Step "python" @("-m", "pip", "install", "-e", ".", "pyinstaller")
    Invoke-Step "python" @(".\tools\build_agent.py")

    Invoke-Step "python" @("-m", "pip", "install", "-r", ".\tools\requirements.txt")
    Invoke-Step "python" @(".\tools\install.py", "--version", $Version, "--os", "win", "--arch", "x86_64", "--gui", $Gui, "--install-dir", $InstallDir)

    $installGuiExe = Join-Path $InstallDir $guiExe
    if (-not (Test-Path -LiteralPath $installGuiExe -PathType Leaf)) {
        throw "Install directory was built, but target GUI executable is missing: $installGuiExe"
    }

    $installAgentExe = Join-Path $InstallDir "agent.exe"
    if (-not (Test-Path -LiteralPath $installAgentExe -PathType Leaf)) {
        throw "Install directory was built, but agent.exe is missing: $installAgentExe"
    }

    Write-Host "Install directory built: $InstallDir"
}
finally {
    Clear-IntermediateArtifacts
}
