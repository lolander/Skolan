; Inno Setup: bygger Skolan-Setup-<version>.exe av dist\Skolan.  ISCC /DVERSION=1.28.0 skolan.iss
; Från 1.95.0 installeras appen per användare (ingen administratör), så att den kan uppdatera sig själv tyst.
; Brandväggsregeln skapas av appen själv första gången den startar (Windows frågar en gång).
#ifndef VERSION
  #define VERSION "0.0.0"
#endif

[Setup]
AppId={{0C7A9E52-3B1D-4F86-A2E4-5D9B7C1F3A60}
AppName=Läxspelet
AppVersion={#VERSION}
AppPublisher=Skolan
AppPublisherURL=https://github.com/lolander/Skolan
DefaultDirName={localappdata}\Programs\Laxspelet
DefaultGroupName=Läxspelet
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
DisableDirPage=yes
UsePreviousAppDir=no
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
Name: "autostart"; Description: "Starta Läxspelet när datorn startar (rekommenderas, så att mobilerna alltid når den)"; GroupDescription: "Start:"

[Files]
Source: "..\dist\Skolan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Gamla genvägar från när appen hette Skolan.
[InstallDelete]
Type: files; Name: "{group}\Skolan.lnk"
Type: files; Name: "{group}\Avinstallera Skolan.lnk"
Type: files; Name: "{autodesktop}\Skolan.lnk"
Type: files; Name: "{userstartup}\Skolan.lnk"

[Icons]
Name: "{group}\Läxspelet"; Filename: "{app}\Skolan.exe"
Name: "{group}\Avinstallera Läxspelet"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Läxspelet"; Filename: "{app}\Skolan.exe"; Tasks: skrivbord
Name: "{userstartup}\Läxspelet"; Filename: "{app}\Skolan.exe"; Parameters: "--tyst"; Tasks: autostart

[Run]
Filename: "{app}\Skolan.exe"; Description: "Starta Läxspelet nu"; Flags: nowait postinstall skipifsilent
; Uppdatering inifrån appen (tyst installation): starta Skolan igen när den är klar.
Filename: "{app}\Skolan.exe"; Parameters: "--tyst"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Skolan.exe"; Flags: runhidden; RunOnceId: "stoppa"

[Code]
// Stäng Skolan (ikonen vid klockan) innan filerna byts.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  R: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Skolan.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  Sleep(1500);
  Result := '';
end;
