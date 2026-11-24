# Kodsignering (Code signing policy)

Installationsfilerna för Läxspelet och Lärarrummet signeras gratis på två sätt:

| Var | Signeras av | Kostnad |
|---|---|---|
| GitHub (`Laxspelet-Setup.exe`, `Laxspelet-Larare-Setup.exe`) | SignPath Foundation | Gratis för öppen källkod |
| Microsoft Store | Microsoft | Gratis |

*Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).*

## Policy
- **Bara det som byggs här signeras.** Filerna byggs av GitHub Actions direkt från koden i det här repot (`.github/workflows/`). Inga filer byggs eller signeras på någons egen dator.
- **Bara versioner signeras.** Signering sker bara när en versionstagg skapas (`v*` för Läxspelet, `larare-v*` för lärarappen), aldrig för vanliga ändringar.
- **Varje signering godkänns av en person** (se roller nedan) i SignPath innan certifikatet används.
- **Roller**
  - Utvecklare och granskare (committers, reviewers): [lolander](https://github.com/lolander)
  - Godkännare (approvers): [lolander](https://github.com/lolander)
- Alla som skriver till repot använder tvåstegsverifiering på GitHub.
- **Integritet:** programmen skickar ingen data till utvecklaren. Se [integritetspolicyn](integritet.md). Programmen installerar eller ändrar inget på datorn utan att användaren (eller skolans IT) har valt det.

## Kontrollera en fil
- Högerklicka på filen → **Egenskaper → Digitala signaturer**. Signeraren ska vara *SignPath Foundation*.
- Eller i PowerShell: `Get-AuthenticodeSignature .\Laxspelet-Larare-Setup.exe`
- Fingeravtrycket finns alltid i `.sha256`-filen bredvid installationsfilen: `Get-FileHash .\Laxspelet-Larare-Setup.exe -Algorithm SHA256`

Ett nytt certifikat behöver bygga upp rykte hos Windows SmartScreen. Under de första veckorna kan Windows därför ändå visa en varning, men utgivaren står då som SignPath Foundation i stället för "Okänd utgivare".

---

## Så kopplas signeringen på (för den som sköter repot)

### 1. Ansök hos SignPath Foundation (gratis)
1. Gå till https://signpath.org/apply och fyll i formuläret:
   - Projekt: **Läxspelet** (Skolan), https://github.com/lolander/Skolan
   - Licens: MIT (OSI-godkänd)
   - Beskrivning: *Open source homework app for families (Windows/Home Assistant) and a companion app for teachers. Built with PyInstaller and Inno Setup on GitHub Actions. No telemetry, no data collection.*
   - Kodsigneringspolicy: länka till den här sidan.
   - Releaser: https://github.com/lolander/Skolan/releases
2. Vänta på svar (brukar ta några dagar till några veckor).

### 2. Ställ in projektet i SignPath
- Skapa ett projekt med slug **Skolan**, kopplat till GitHub-repot (Trusted Build System: GitHub.com).
- Signeringspolicy: **release-signing** (manuellt godkännande).
- Två artefaktkonfigurationer:
  - slug **laxspelet** och slug **larare**, båda med:
    ```xml
    <?xml version="1.0" encoding="utf-8"?>
    <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
      <zip-file>
        <pe-file path="*.exe">
          <authenticode-sign/>
        </pe-file>
      </zip-file>
    </artifact-configuration>
    ```

### 3. Lägg in nycklarna i GitHub
**Settings → Secrets and variables → Actions**:
- Variabel `SIGNPATH_ORGANIZATION_ID` = organisationens id i SignPath
- Hemlighet `SIGNPATH_API_TOKEN` = API-token för en CI-användare med rätt att skicka signeringsbegäranden

Nästa versionstagg skickar installationsfilen till SignPath. När du har godkänt begäran i SignPath fortsätter bygget och publicerar den signerade filen. Utan variabeln byggs allt som förut, osignerat.
