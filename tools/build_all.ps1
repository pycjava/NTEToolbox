param(
    [string] $Version = "v0.0.0",
    [string] $TauriTargetDir = "",
    [string] $TauriOutputDir = "",

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
Write-Host " All build steps completed." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
