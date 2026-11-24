; Inno Setup: bygger Skolan-Larare-Setup-<version>.exe av dist\SkolanLarare.  ISCC /DVERSION=0.1.0 larare.iss
; Från 0.8.0 installeras appen per användare (ingen administratör), så att den kan uppdatera sig själv tyst.
; Brandväggsregeln skapas av appen själv första gången den startar (Windows frågar en gång).
; IT kan installera för alla användare med /ALLUSERS (Program Files). Då sköter IT uppdateringarna,
; och /MERGETASKS="brandvagg" skapar brandväggsregeln direkt.
#ifndef VERSION
  #define VERSION "0.0.0"
#endif

[Setup]
AppId={{5E1D2C3B-7A49-4F0E-9C21-8B6D4A3F2E10}
AppName=Lärarrummet
AppVersion={#VERSION}
AppPublisher=Skolan
AppPublisherURL=https://github.com/lolander/Skolan
DefaultDirName={autopf}\Laxspelet Larare
DefaultGroupName=Lärarrummet
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
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
Name: "brandvagg"; Description: "Tillåt kollegor och elever i skolans nätverk (TCP 8770)"; Check: IsAdminInstallMode; Flags: unchecked

[Files]
Source: "..\dist\SkolanLarare\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Gamla genvägar från när appen hette Skolan.
[InstallDelete]
; Appen hette Läxspelet Lärare före 0.13.0
Type: filesandordirs; Name: "{autoprograms}\Läxspelet Lärare"
Type: files; Name: "{autodesktop}\Läxspelet Lärare.lnk"
Type: files; Name: "{group}\Skolan Lärare.lnk"
Type: files; Name: "{group}\Avinstallera Skolan Lärare.lnk"
Type: files; Name: "{autodesktop}\Skolan Lärare.lnk"

[Icons]
Name: "{group}\Lärarrummet"; Filename: "{app}\SkolanLarare.exe"
Name: "{group}\Avinstallera Lärarrummet"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lärarrummet"; Filename: "{app}\SkolanLarare.exe"; Tasks: skrivbord

[Run]
Filename: "{app}\SkolanLarare.exe"; Description: "Starta Lärarrummet nu"; Flags: nowait postinstall skipifsilent; Check: not IsAdminInstallMode
; Automatisk uppdatering (tyst installation): starta appen igen utan att öppna webbläsaren.
Filename: "{app}\SkolanLarare.exe"; Parameters: "--tyst"; Flags: nowait; Check: WizardSilent and not IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Laxspelet Larare"" dir=in action=allow program=""{app}\SkolanLarare.exe"" enable=yes profile=private,domain"; Flags: runhidden; Tasks: brandvagg

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM SkolanLarare.exe"; Flags: runhidden; RunOnceId: "stoppa"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Laxspelet Larare"""; Flags: runhidden; Tasks: brandvagg; RunOnceId: "brandvagg"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  R: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM SkolanLarare.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  Sleep(1000);
  Result := '';
end;
