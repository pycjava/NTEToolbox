param(
    [ValidateSet('mfaa', 'mxu')]
    [string] $Gui = "mfaa",

    [string] $InstallDir = "",
    [string] $OutputDir = "",
    [string] $Makensis = "makensis"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if ($InstallDir -eq "") {
    $InstallDir = Join-Path $repoRoot "install"
}
if ($OutputDir -eq "") {
    $OutputDir = Join-Path $repoRoot "dist-installer"
}

$guiExe = switch ($Gui) {
    "mfaa" { "MFAAvalonia.exe" }
    "mxu" { "mxu.exe" }
}
$guiName = $Gui.ToUpperInvariant()

if (-not (Test-Path -LiteralPath $InstallDir -PathType Container)) {
    throw "Install source directory does not exist: $InstallDir"
}

$guiPath = Join-Path $InstallDir $guiExe
if (-not (Test-Path -LiteralPath $guiPath -PathType Leaf)) {
    throw "Selected GUI executable does not exist: $guiPath"
}

$makensisCommand = Get-Command $Makensis -ErrorAction SilentlyContinue
if ($null -eq $makensisCommand) {
    $defaultMakensisPaths = @(
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )
    $defaultMakensisPath = $defaultMakensisPaths |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if ($null -ne $defaultMakensisPath) {
        $makensisCommand = Get-Command $defaultMakensisPath
    }
}
if ($null -eq $makensisCommand) {
    throw "makensis was not found. Install NSIS or pass -Makensis with the full path."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$installSource = (Resolve-Path $InstallDir).Path.TrimEnd("\")
$outputPath = (Resolve-Path $OutputDir).Path.TrimEnd("\")
$installerScript = Join-Path $repoRoot "installer\NTEToolbox.nsi"

$makensisArgs = @(
    "/DGUI_EXE=$guiExe",
    "/DGUI_NAME=$guiName",
    "/DINSTALL_SOURCE=$installSource",
    "/DOUTPUT_DIR=$outputPath",
    $installerScript
)

& $makensisCommand.Source @makensisArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
