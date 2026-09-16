#define MyAppName "InfoScraper"
#define MyAppVersion "1.8.9"
#define MyAppPublisher "InfoScraper Team"
#define MyAppURL "https://github.com/tomjoy248-crypto/SL-crawler-"
#define MyAppExeName "InfoScraper.exe"

[Setup]
AppId={{INFO_SCRAPER_1_0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\InfoScraper
DisableProgramGroupPage=yes
OutputDir=..\setup_output
OutputBaseFilename=InfoScraper-Setup
SetupIconFile=
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "files\InfoScraper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "files\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "files\USER_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\InfoScraper"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\InfoScraper"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,InfoScraper}"; Flags: nowait postinstall skipifsilent
