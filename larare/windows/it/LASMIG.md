# Läxspelet Lärare: för skolans IT

Allt i den här mappen är till för att installera och styra Läxspelet Lärare centralt.
Mer om nivåer, dataskydd och skollagen: https://github.com/lolander/Skolan/blob/main/docs/larare-skolor.md
Prova appen utan att installera (påhittad klass): https://lolander.github.io/Skolan/demo/

## Innehåll
| Fil | Vad |
|---|---|
| `LaxspeletLarare.admx`, `sv-SE\`, `en-US\` | Grupprincipmall: högsta behörighetsnivå och uppdateringar |
| `Niva0-IT-uppdaterar.reg` | Nivå 0, appen kontaktar inte GitHub (IT distribuerar) |
| `Niva0-automatiska-uppdateringar.reg` | Nivå 0, appen uppdaterar sig själv |

## 1. Grupprinciper
- **Active Directory:** kopiera `LaxspeletLarare.admx` till `\\<domän>\SYSVOL\<domän>\Policies\PolicyDefinitions\` och `.adml`-filerna till `sv-SE\` och `en-US\` där. Inställningarna finns sedan under *Datorkonfiguration (eller Användarkonfiguration) → Administrativa mallar → Läxspelet Lärare*.
- **Intune:** *Enheter → Konfiguration → Importera ADMX*. Ladda upp `LaxspeletLarare.admx` och `en-US\LaxspeletLarare.adml`. Skapa sedan en profil (*Mallar → Importerade administrativa mallar*).
- Utan mallen: använd `.reg`-filerna, eller sätt värdena under `HKLM\SOFTWARE\Policies\Laxspelet Larare` (`MaxNiva` DWORD 0–2, `Uppdateringar` REG_SZ `automatisk`/`manuell`/`av`).

Finns ett värde både för datorn och användaren gäller det strängaste. Läraren ser i appen att inställningen är låst.

## 2. Installation
Installationsfil: https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Larare-Setup.exe
Kontrollera fingeravtrycket mot `.sha256`-filen på samma sida (`Get-FileHash <fil> -Algorithm SHA256`).

| | Per användare | För alla användare |
|---|---|---|
| Kommando | `Laxspelet-Larare-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` | `Laxspelet-Larare-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS` |
| Behörighet | Ingen administratör | Administratör (Intune: *System*) |
| Mapp | `%LOCALAPPDATA%\Programs\Laxspelet Larare` | `%ProgramFiles%\Laxspelet Larare` |
| Uppdateringar | Appen uppdaterar sig själv (om inte `Uppdateringar = av`) | **Aldrig själv.** IT distribuerar nya versioner. |
| Avinstallation | `"%LOCALAPPDATA%\Programs\Laxspelet Larare\unins000.exe" /VERYSILENT` | `"%ProgramFiles%\Laxspelet Larare\unins000.exe" /VERYSILENT` |

**Brandvägg (valfritt):** lägg till `/MERGETASKS="brandvagg"` vid installation för alla användare. Då skapas regeln *Laxspelet Larare* (in, TCP 8770, profil privat och domän, bara för `SkolanLarare.exe`) och tas bort vid avinstallation. Regeln behövs bara för synk mellan kollegor och om elever ska ansluta på lektionen. Utan den fungerar allt som går via familjens klasslänk.

### Intune (Win32-app)
1. Paketera installationsfilen med *Microsoft Win32 Content Prep Tool* (`IntuneWinAppUtil.exe`).
2. Installationskommando: se tabellen ovan. Installationsbeteende: *System* för `/ALLUSERS`, annars *Användare*.
3. Identifiering (alla användare): registret `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{5E1D2C3B-7A49-4F0E-9C21-8B6D4A3F2E10}_is1`, värdet `DisplayVersion`, version större än eller lika med den du distribuerar. Per användare: samma nyckel under `HKCU`.
4. Returkoder: 0 = klart.

### Microsoft Store
När Läxspelet Lärare finns i Microsoft Store kan den läggas till i Intune som *Microsoft Store-app (ny)*. Store-versionen är signerad av Microsoft och Store sköter uppdateringarna.

## 3. Data och gallring
- Data: `%APPDATA%\SkolanLarare\` (krypterad med lärarens Windows-konto, DPAPI). Avinstallation raderar **inte** datan.
- Läraren raderar elevuppgifter i appen: *🔐 Behörighet → 🗑️ Radera klassens data*. IT kan ta bort mappen.

## 4. Nätverk
Ut HTTPS 443 till `github.com`, `api.github.com`, `release-assets.githubusercontent.com` (bara om uppdateringar är på) och till familjernas Läxspelet. Lokalt TCP/UDP 8770 för kollegor. Se avsnitt 6 i dokumentet för skolor.

## 5. Komponentlista och säkerhet
- Komponentlista (SBOM, CycloneDX): `Laxspelet-Larare-SBOM-<version>.cdx.json` på release-sidan.
- Rapportera säkerhetsbrister: https://github.com/lolander/Skolan/security/policy
