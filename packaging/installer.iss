; Inno Setup script for ShowMaster Arena Creator (built by build_exe.py)
#define MyAppName "ShowMaster Arena Creator"
#define MyAppExe "ShowMaster Arena Creator.exe"
#ifndef MyAppVersion
  #define MyAppVersion "0.26.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\ShowMaster Arena Creator"
#endif

[Setup]
AppId={{8F2C7A3E-5B1D-4C8E-9A61-3D2F7B9E4C10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=ImmersiveWerks
AppPublisherURL=https://github.com/ImmersiveWerks/showmaster-arena-creator
LicenseFile=..\LICENSE
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=ShowMaster_Arena_Creator_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; files the program made itself (Python caches); your saved grandstands stay in %APPDATA%
Type: filesandordirs; Name: "{app}\_internal"
