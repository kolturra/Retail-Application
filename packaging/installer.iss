; Inno Setup script. AppVersion must equal retail.__version__ (tests/test_packaging_files.py checks this).
; The shop's data lives in %LOCALAPPDATA%\RetailApp. This installer never writes, overwrites or deletes
; anything there, so upgrading or uninstalling keeps the database, licence key, settings and backups.
#define AppName "Retail App"
#define AppVersion "0.1.0"

[Setup]
AppId={{8F2C1A64-5B7D-4E39-A0C2-6D41B9E37F58}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\RetailApp
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=RetailApp-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\RetailApp\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\RetailApp.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\RetailApp.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RetailApp.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
