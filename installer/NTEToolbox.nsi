Unicode true
RequestExecutionLevel admin

!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef GUI_EXE
!define GUI_EXE "MFAAvalonia.exe"
!endif

!ifndef GUI_NAME
!define GUI_NAME "MFAA"
!endif

!ifndef INSTALL_SOURCE
!define INSTALL_SOURCE "..\install"
!endif

!ifndef OUTPUT_DIR
!define OUTPUT_DIR "..\dist-installer"
!endif

!define APP_NAME "NTEToolbox"
!define APP_PUBLISHER "NTEToolbox"
!define DOTNET_MAJOR "10"
!define DOTNET_RUNTIME_NAME "Microsoft.WindowsDesktop.App"
!define DOTNET_RUNTIME_URL "https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe"
!define VC_REDIST_URL "https://aka.ms/vs/17/release/vc_redist.x64.exe"

!macro DownloadHttps URL TARGET DESCRIPTION
    DetailPrint "Downloading ${DESCRIPTION}..."
    Delete "${TARGET}"
    nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri ''${URL}'' -OutFile ''${TARGET}''"'
    Pop $0
    Pop $1
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "Failed to download ${DESCRIPTION}: $1"
        Abort
    ${EndIf}
    ${IfNot} ${FileExists} "${TARGET}"
        MessageBox MB_ICONSTOP "Failed to download ${DESCRIPTION}: output file was not created."
        Abort
    ${EndIf}
!macroend

Name "${APP_NAME} (${GUI_NAME})"
OutFile "${OUTPUT_DIR}\NTEToolbox-${GUI_NAME}-Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
ShowInstDetails show
ShowUninstDetails show

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Section "Install" SecInstall
    SetShellVarContext all
    SetRegView 64

    Call EnsureVCRedist
    Call EnsureDotNetRuntime

    SetOutPath "$INSTDIR"
    File /r /x "debug" /x "logs" /x "temp" "${INSTALL_SOURCE}\*.*"

    WriteUninstaller "$INSTDIR\Uninstall.exe"
    Call CreateDesktopShortcut

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME} (${GUI_NAME})"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    SetShellVarContext all
    SetRegView 64

    Delete "$DESKTOP\${APP_NAME}.lnk"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    RMDir /r "$INSTDIR"
SectionEnd

Function EnsureDotNetRuntime
    DetailPrint "Checking ${DOTNET_RUNTIME_NAME} ${DOTNET_MAJOR}.x..."
    nsExec::ExecToStack '"$SYSDIR\cmd.exe" /C dotnet --list-runtimes | findstr /C:"${DOTNET_RUNTIME_NAME} ${DOTNET_MAJOR}." >nul'
    Pop $0
    Pop $1

    ${If} $0 == 0
        DetailPrint "${DOTNET_RUNTIME_NAME} ${DOTNET_MAJOR}.x is already installed."
        Return
    ${EndIf}

    DetailPrint "Installing ${DOTNET_RUNTIME_NAME} ${DOTNET_MAJOR}.x..."
    !insertmacro DownloadHttps "${DOTNET_RUNTIME_URL}" "$TEMP\windowsdesktop-runtime-${DOTNET_MAJOR}.exe" ".NET Desktop Runtime"

    ExecWait '"$TEMP\windowsdesktop-runtime-${DOTNET_MAJOR}.exe" /install /passive /norestart' $0
    Delete "$TEMP\windowsdesktop-runtime-${DOTNET_MAJOR}.exe"

    ${If} $0 != 0
    ${AndIf} $0 != 3010
        MessageBox MB_ICONSTOP ".NET Desktop Runtime installation failed. Exit code: $0"
        Abort
    ${EndIf}
FunctionEnd

Function EnsureVCRedist
    DetailPrint "Checking Microsoft Visual C++ Redistributable..."
    ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
    ${IfNot} ${Errors}
    ${AndIf} $0 == 1
        DetailPrint "Microsoft Visual C++ Redistributable is already installed."
        Return
    ${EndIf}

    DetailPrint "Installing Microsoft Visual C++ Redistributable..."
    !insertmacro DownloadHttps "${VC_REDIST_URL}" "$TEMP\vc_redist.x64.exe" "Microsoft Visual C++ Redistributable"

    ExecWait '"$TEMP\vc_redist.x64.exe" /install /passive /norestart' $0
    Delete "$TEMP\vc_redist.x64.exe"

    ${If} $0 != 0
    ${AndIf} $0 != 3010
        MessageBox MB_ICONSTOP "Microsoft Visual C++ Redistributable installation failed. Exit code: $0"
        Abort
    ${EndIf}
FunctionEnd

Function CreateDesktopShortcut
    IfFileExists "$INSTDIR\${GUI_EXE}" 0 missingGui
    CreateShortcut "$DESKTOP\NTEToolbox.lnk" "$INSTDIR\${GUI_EXE}" "" "$INSTDIR\${GUI_EXE}" 0
    Return

missingGui:
    MessageBox MB_ICONSTOP "Cannot create desktop shortcut because $INSTDIR\${GUI_EXE} was not found."
    Abort
FunctionEnd
