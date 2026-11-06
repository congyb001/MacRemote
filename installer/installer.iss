; Mac 远控 安装包脚本（Inno Setup 6）
; 由 build-installer.ps1 调用：先准备 stage\ 与 stage-vnc\，再编译本文件

#define MyAppName "Mac 远控"
#define MyAppShortName "MacRemote"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "congyb001"
#define MyAppURL "https://github.com/congyb001/MacRemote"
#define MyAppExeName "Mac远控.exe"

[Setup]
AppId={{8F3C1B42-5D7A-4E19-9C6B-2A1D4E8F7B30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 默认装到当前用户目录（%LOCALAPPDATA%\Programs\MacRemote），全程不需要管理员权限
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
OutputDir=dist
OutputBaseFilename={#MyAppShortName}-Setup-{#MyAppVersion}
SetupIconFile=..\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
InfoBeforeFile=BEFORE-INSTALL.txt

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "vncclient"; Description: "安装便携 VNC 客户端（TigerVNC 1.16.2，GPL-2.0，约 23 MB）"; GroupDescription: "组件:"; Flags: checkedonce
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
; 主体（必需）
Source: "stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 便携 VNC 客户端（可取消勾选；GPL-2.0，附带许可证原文）
Source: "stage-vnc\bin\TigerVNC\*"; DestDir: "{app}\bin\TigerVNC"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: WizardIsTaskSelected('vncclient')

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
