param(
    [switch] $SkipTauri,

    [ValidateSet('auto', 'none', 'mfaa', 'mxu', 'both')]
    [string] $LegacyGui = "auto",

    [switch] $SkipNsis,

    [string] $Version = "v0.0.0",
    [string] $TauriTargetDir = "",
    [string] $TauriOutputDir = "",
    [string] $InstallDir = "",
    [string] $InstallerOutputDir = "",
    [string] $MfaSourceDir = "",
    [string] $MxuSourceDir = "",
    [string] $Makensis = "makensis",

    [switch] $PlanOnly
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$toolsDir = Join-Path $repoRoot "tools"
$steps = @()

function Resolve-RepoRelativePath {
    param(
        [string] $Path
    )

    if ($Path -eq "") {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

function Get-LegacyGuiExe {
    param(
        [ValidateSet('mfaa', 'mxu')]
        [string] $Gui
    )

    switch ($Gui) {
        "mfaa" { return "MFAAvalonia.exe" }
        "mxu" { return "mxu.exe" }
    }
}

function Get-LegacySourceDir {
    param(
        [ValidateSet('mfaa', 'mxu')]
        [string] $Gui
    )

    if ($Gui -eq "mfaa") {
        if ($MfaSourceDir -ne "") {
            return Resolve-RepoRelativePath $MfaSourceDir
        }
        return Join-Path $repoRoot "MFA"
    }

    if ($MxuSourceDir -ne "") {
        return Resolve-RepoRelativePath $MxuSourceDir
    }
    return Join-Path $repoRoot "MXU"
}

function Test-LegacyGuiSource {
    param(
        [ValidateSet('mfaa', 'mxu')]
        [string] $Gui
    )

    $sourceDir = Get-LegacySourceDir $Gui
    $guiExe = Get-LegacyGuiExe $Gui
    return (Test-Path -LiteralPath (Join-Path $sourceDir $guiExe) -PathType Leaf)
}

function Assert-LegacyGuiSource {
    param(
        [ValidateSet('mfaa', 'mxu')]
        [string] $Gui
    )

    $sourceDir = Get-LegacySourceDir $Gui
    $guiExe = Get-LegacyGuiExe $Gui
    $sourceExe = Join-Path $sourceDir $guiExe

    if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
        throw "Selected legacy GUI source is missing: $sourceExe"
    }
}

function Resolve-LegacyGuis {
    switch ($LegacyGui) {
        "none" {
            return @()
        }
        "mfaa" {
            Assert-LegacyGuiSource "mfaa"
            return @("mfaa")
        }
        "mxu" {
            Assert-LegacyGuiSource "mxu"
            return @("mxu")
        }
        "both" {
            Assert-LegacyGuiSource "mfaa"
            Assert-LegacyGuiSource "mxu"
            return @("mfaa", "mxu")
        }
        "auto" {
            $available = @()
            foreach ($gui in @("mfaa", "mxu")) {
                if (Test-LegacyGuiSource $gui) {
                    $available += $gui
                }
                else {
                    $sourceDir = Get-LegacySourceDir $gui
                    $guiExe = Get-LegacyGuiExe $gui
                    Write-Host "Skipping $($gui.ToUpperInvariant()): missing $(Join-Path $sourceDir $guiExe)" -ForegroundColor DarkYellow
                }
            }
            return $available
        }
    }
}

function Get-LegacyInstallDir {
    param(
        [ValidateSet('mfaa', 'mxu')]
        [string] $Gui,
        [int] $GuiCount
    )

    if ($InstallDir -eq "") {
        if ($GuiCount -gt 1) {
            return Join-Path (Join-Path $repoRoot "install") $Gui
        }
        return Join-Path $repoRoot "install"
    }

    $resolvedInstallDir = Resolve-RepoRelativePath $InstallDir
    if ($GuiCount -gt 1) {
        return Join-Path $resolvedInstallDir $Gui
    }
    return $resolvedInstallDir
}

function Get-InstallerOutputDir {
    if ($InstallerOutputDir -ne "") {
        return Resolve-RepoRelativePath $InstallerOutputDir
    }
    return Join-Path $repoRoot "dist-installer"
}

function Add-BuildStep {
    param(
        [string] $Name,
        [string] $ScriptPath,
        [string[]] $Arguments
    )

    $script:steps += [PSCustomObject] @{
        Name = $Name
        ScriptPath = $ScriptPath
        Arguments = $Arguments
    }
}

function Format-CommandToken {
    param(
        [string] $Token
    )

    if ($Token -eq "") {
        return '""'
    }

    if ($Token -match '[\s"]') {
        return '"' + ($Token -replace '"', '\"') + '"'
    }
    return $Token
}

function Format-BuildCommand {
    param(
        [object] $Step
    )

    $tokens = @(
        $script:powerShellExe,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $Step.ScriptPath
    ) + $Step.Arguments

    return (($tokens | ForEach-Object { Format-CommandToken $_ }) -join " ")
}

function Invoke-BuildStep {
    param(
        [object] $Step,
        [int] $Index,
        [int] $Total
    )

    Write-Host ""
    Write-Host "[$Index/$Total] $($Step.Name)" -ForegroundColor Cyan
    Write-Host "       $(Format-BuildCommand $Step)"

    if ($PlanOnly) {
        return
    }

    Push-Location $repoRoot
    try {
        $processArgs = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $Step.ScriptPath
        ) + $Step.Arguments

        & $script:powerShellExe @processArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Build step failed with exit code ${LASTEXITCODE}: $($Step.Name)"
        }
    }
    finally {
        Pop-Location
    }
}

$powerShellProcess = Get-Process -Id $PID
$script:powerShellExe = $powerShellProcess.Path
if (-not $script:powerShellExe) {
    $script:powerShellExe = (Get-Command powershell).Source
}

if (-not $SkipTauri) {
    $tauriArgs = @()
    if ($TauriTargetDir -ne "") {
        $tauriArgs += @("-TargetDir", (Resolve-RepoRelativePath $TauriTargetDir))
    }
    if ($TauriOutputDir -ne "") {
        $tauriArgs += @("-OutputDir", (Resolve-RepoRelativePath $TauriOutputDir))
    }

    Add-BuildStep `
        -Name "Build MaaToolbox Client (Tauri)" `
        -ScriptPath (Join-Path $toolsDir "build_tauri.ps1") `
        -Arguments $tauriArgs
}

$legacyGuis = @(Resolve-LegacyGuis)
$installerOutput = Get-InstallerOutputDir

foreach ($gui in $legacyGuis) {
    $sourceDir = Get-LegacySourceDir $gui
    $installOutput = Get-LegacyInstallDir -Gui $gui -GuiCount $legacyGuis.Count

    Add-BuildStep `
        -Name "Build $($gui.ToUpperInvariant()) install directory" `
        -ScriptPath (Join-Path $toolsDir "build_install.ps1") `
        -Arguments @(
            "-Gui", $gui,
            "-Version", $Version,
            "-GuiSourceDir", $sourceDir,
            "-InstallDir", $installOutput
        )

    if (-not $SkipNsis) {
        Add-BuildStep `
            -Name "Build $($gui.ToUpperInvariant()) NSIS installer" `
            -ScriptPath (Join-Path $toolsDir "build_nsis.ps1") `
            -Arguments @(
                "-Gui", $gui,
                "-InstallDir", $installOutput,
                "-OutputDir", $installerOutput,
                "-Makensis", $Makensis
            )
    }
}

if ($steps.Count -eq 0) {
    throw "No build steps selected. Enable Tauri or provide an available legacy GUI source."
}

Write-Host "Build plan:" -ForegroundColor Green
for ($index = 0; $index -lt $steps.Count; $index += 1) {
    Write-Host "  $($index + 1). $($steps[$index].Name)"
}

for ($index = 0; $index -lt $steps.Count; $index += 1) {
    Invoke-BuildStep -Step $steps[$index] -Index ($index + 1) -Total $steps.Count
}

if ($PlanOnly) {
    Write-Host ""
    Write-Host "Plan only. No build commands were executed." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " All selected build steps completed." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
