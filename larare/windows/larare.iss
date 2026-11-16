; Inno Setup: bygger Skolan-Larare-Setup-<version>.exe av dist\SkolanLarare.  ISCC /DVERSION=0.1.0 larare.iss
#ifndef VERSION
  #define VERSION "0.0.0"
#endif

[Setup]
AppId={{9B2C7D4E-1F3A-4B6C-8D9E-2A3B4C5D6E7F}
AppName=Skolan Lärare
AppVersion={#VERSION}
AppPublisher=Skolan
AppPublisherURL=https://github.com/lolander/Skolan
DefaultDirName={autopf}\Skolan Larare
DefaultGroupName=Skolan Lärare
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=Skolan-Larare-Setup-{#VERSION}
SetupIconFile=larare.ico
UninstallDisplayIcon={app}\SkolanLarare.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "sv"; MessagesFile: "compiler:Languages\Swedish.isl"

[Tasks]
Name: "skrivbord"; Description: "Skapa en genväg på skrivbordet"; GroupDescription: "Genvägar:"

[Files]
Source: "..\dist\SkolanLarare\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Skolan Lärare"; Filename: "{app}\SkolanLarare.exe"
Name: "{group}\Avinstallera Skolan Lärare"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Skolan Lärare"; Filename: "{app}\SkolanLarare.exe"; Tasks: skrivbord

[Run]
; Eleverna ansluter från sina mobiler på skolans nätverk (privata nätverk och domännätverk, inte publika).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Skolan Larare"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Skolan Larare"" dir=in action=allow program=""{app}\SkolanLarare.exe"" enable=yes profile=private,domain"; Flags: runhidden
Filename: "{app}\SkolanLarare.exe"; Description: "Starta Skolan Lärare nu"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Skolan Larare"""; Flags: runhidden; RunOnceId: "brandvagg"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM SkolanLarare.exe"; Flags: runhidden; RunOnceId: "stoppa"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  R: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM SkolanLarare.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  Sleep(1000);
  Result := '';
end;
