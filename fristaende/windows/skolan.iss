; Inno Setup: bygger Skolan-Setup-<version>.exe av dist\Skolan.  ISCC /DVERSION=1.28.0 skolan.iss
#ifndef VERSION
  #define VERSION "0.0.0"
#endif

[Setup]
AppId={{6E3F2B1A-5C4D-4E8F-9A7B-1C2D3E4F5A6B}
AppName=Skolan
AppVersion={#VERSION}
AppPublisher=Skolan
AppPublisherURL=https://github.com/lolander/Skolan
DefaultDirName={autopf}\Skolan
DefaultGroupName=Skolan
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=Skolan-Setup-{#VERSION}
SetupIconFile=skolan.ico
UninstallDisplayIcon={app}\Skolan.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "sv"; MessagesFile: "compiler:Languages\Swedish.isl"

[Tasks]
Name: "skrivbord"; Description: "Skapa en genväg på skrivbordet"; GroupDescription: "Genvägar:"
Name: "autostart"; Description: "Starta Skolan när datorn startar (rekommenderas, så att mobilerna alltid når den)"; GroupDescription: "Start:"

[Files]
Source: "..\dist\Skolan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Skolan"; Filename: "{app}\Skolan.exe"
Name: "{group}\Avinstallera Skolan"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Skolan"; Filename: "{app}\Skolan.exe"; Tasks: skrivbord
Name: "{userstartup}\Skolan"; Filename: "{app}\Skolan.exe"; Parameters: "--tyst"; Tasks: autostart

[Run]
; Låt mobiler i hemmanätverket nå Skolan (bara privata nätverk, inte publika wifi).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Skolan"" dir=in action=allow program=""{app}\Skolan.exe"" enable=yes profile=private"; Flags: runhidden
Filename: "{app}\Skolan.exe"; Description: "Starta Skolan nu"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Skolan"""; Flags: runhidden; RunOnceId: "brandvagg"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Skolan.exe"; Flags: runhidden; RunOnceId: "stoppa"
