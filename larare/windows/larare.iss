; Inno Setup: bygger Skolan-Larare-Setup-<version>.exe av dist\SkolanLarare.  ISCC /DVERSION=0.1.0 larare.iss
; Från 0.8.0 installeras appen per användare (ingen administratör), så att den kan uppdatera sig själv tyst.
; Brandväggsregeln skapas av appen själv första gången den startar (Windows frågar en gång).
#ifndef VERSION
  #define VERSION "0.0.0"
#endif

[Setup]
AppId={{5E1D2C3B-7A49-4F0E-9C21-8B6D4A3F2E10}
AppName=Läxspelet Lärare
AppVersion={#VERSION}
AppPublisher=Skolan
AppPublisherURL=https://github.com/lolander/Skolan
DefaultDirName={localappdata}\Programs\Laxspelet Larare
DefaultGroupName=Läxspelet Lärare
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
DisableDirPage=yes
UsePreviousAppDir=no
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

; Gamla genvägar från när appen hette Skolan.
[InstallDelete]
Type: files; Name: "{group}\Skolan Lärare.lnk"
Type: files; Name: "{group}\Avinstallera Skolan Lärare.lnk"
Type: files; Name: "{autodesktop}\Skolan Lärare.lnk"

[Icons]
Name: "{group}\Läxspelet Lärare"; Filename: "{app}\SkolanLarare.exe"
Name: "{group}\Avinstallera Läxspelet Lärare"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Läxspelet Lärare"; Filename: "{app}\SkolanLarare.exe"; Tasks: skrivbord

[Run]
Filename: "{app}\SkolanLarare.exe"; Description: "Starta Läxspelet Lärare nu"; Flags: nowait postinstall skipifsilent
; Automatisk uppdatering (tyst installation): starta appen igen utan att öppna webbläsaren.
Filename: "{app}\SkolanLarare.exe"; Parameters: "--tyst"; Flags: nowait; Check: WizardSilent

[UninstallRun]
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
