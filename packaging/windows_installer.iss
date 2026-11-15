; Instalador de Windows (Inno Setup 6). Lo usa .github/workflows/instaladores.yml
#define AppName "LBD Flightcase Maker"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6C1E7A52-6B0E-4F2B-9A57-3F1C2B7D9E41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=eldoctormail
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=LBDFlightcaseMaker-{#AppVersion}-Windows-Instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
SetupIconFile=icono\icono.ico
UninstallDisplayIcon={app}\{#AppName}.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Registry]
; "Abrir con" para los proyectos .scad del taller, sin quitarle la asociación a OpenSCAD
Root: HKA; Subkey: "Software\Classes\.scad\OpenWithProgids"; ValueType: string; ValueName: "FlightcaseCalculator.Scad"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\FlightcaseCalculator.Scad"; ValueType: string; ValueName: ""; ValueData: "Proyecto del taller (OpenSCAD)"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\FlightcaseCalculator.Scad\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppName}.exe,0"
Root: HKA; Subkey: "Software\Classes\FlightcaseCalculator.Scad\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppName}.exe"" ""%1"""

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
