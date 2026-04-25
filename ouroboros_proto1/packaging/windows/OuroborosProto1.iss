#define MyAppName "Ouroboros proto 1"
#define MyAppVersion GetEnv("APP_VERSION")
#define MyAppPublisher "WintripAI"
#define MyAppURL "https://github.com"
#define MyAppExeName "ouroboros_proto1.exe"

[Setup]
AppId={{8AB9B9B9-9B5B-4E17-84C9-C6D7731AAAF9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\OuroborosProto1
DefaultGroupName=Ouroboros proto 1
DisableProgramGroupPage=yes
OutputBaseFilename=OuroborosProto1Setup
OutputDir=dist
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "target\release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Ouroboros proto 1"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Ouroboros proto 1"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Ouroboros proto 1"; Flags: nowait postinstall skipifsilent
