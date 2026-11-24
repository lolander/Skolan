# Lärarrummet: svar på vanliga frågor om informationssäkerhet

*Förifyllt underlag för kommunens eller skolans leverantörsbedömning. Gäller Lärarrummet 0.14.0. Senast uppdaterad: 24 november 2026.*

Svaren beskriver appen som den är byggd. Allt går att kontrollera i den öppna källkoden: https://github.com/lolander/Skolan (mappen `larare/`). Fler detaljer finns i [Information till skolor, IT och dataskyddsombud](larare-skolor.md).

## Leverantör och avtal

| Fråga | Svar |
|---|---|
| Vem tillhandahåller programvaran? | David Martell, privatperson. Öppen källkod under MIT-licens. Ingen kommersiell tjänst, inget abonnemang. |
| Behövs ett personuppgiftsbiträdesavtal (PUB-avtal)? | **Nej.** Utvecklaren behandlar inga personuppgifter för skolans räkning: det finns ingen server, inget moln och ingen fjärråtkomst. All data finns på lärarens dator. Huvudmannen är personuppgiftsansvarig för behandlingen i appen. |
| Underbiträden? | Inga hos utvecklaren. Microsoft Store distribuerar appen. Om läraren frivilligt verifierar sig med skolkontot sker inloggningen hos skolans egen Microsoft- eller Google-organisation. |
| Supportåtagande och SLA? | Inget avtalat. Fel och frågor tas emot via GitHub (Issues). Säkerhetsbrister: se [SECURITY.md](../SECURITY.md). |
| Licenskostnad? | Ingen. |

## Data och lagring

| Fråga | Svar |
|---|---|
| Var lagras data? | Bara på lärarens dator, i `%APPDATA%\SkolanLarare\`. |
| Lämnar data EU? | Inte från Lärarrummet. Familjernas Läxspelet nås antingen via Nabu Casa eller via en Cloudflare-tunnel. Trafiken är krypterad men passerar dessa tjänster. Därför rekommenderas att inte skriva personuppgifter i utskick (nivå 0). |
| Vilka personuppgifter? | Som standard **inga** (nivå 0). Nivå 1 (elevnamn) och nivå 2 (uppgifter om enskilda elever) kräver rektorns beslut i appen och kan låsas av IT. |
| Kryptering i vila? | Klassens data krypteras med lärarens Windows-konto (DPAPI). Bifogade filer och loggfilen är inte krypterade: använd BitLocker. |
| Kryptering vid överföring? | Synk mellan lärare: AES-256-GCM och HMAC-SHA256 med skolans nyckel. Synk till familjen: HTTPS (via familjens adress), signerad med Ed25519. |
| Gallring? | Läraren raderar all elevdata med en knapp. Historik och listor har tak (se avsnitt 8 i informationen till skolor). Avinstallation raderar inte data. |
| Säkerhetskopiering? | Ingen hos utvecklaren. Data följer skolans vanliga hantering av lärarens dator. |

## Åtkomst och identitet

| Fråga | Svar |
|---|---|
| Hur loggar man in? | Appen körs i lärarens Windows-konto, och sidan nås bara från datorn själv (`localhost`). Inga egna lösenord. |
| Behörighetsstyrning? | Rektorn i appen tilldelar nivåer och roller, signerat med Ed25519. Mentorn godkänner ämneslärare. IT kan låsa högsta nivå per dator med grupprinciper (`MaxNiva`). |
| Spårbarhet? | Rektorns beslut loggas med namn, tid och grund och kan exporteras. **Tillsynsloggen:** allt lärarna skickar till eleverna sparas hos rektorn i ett år, signerat av lärarens app (Ed25519), och kan exporteras med signaturer, till exempel till huvudmannen eller polisen. Läraren kan inte radera rektorns kopia. Loggen öppnas bara med **fyraögonsprincipen**: rektorn anger grund, en utsedd kontrollant godkänner, och båda bekräftar med en ny inloggning med skol- eller organisationskontot (skolans MFA). Varje öppning sparas i en åtkomstlogg. |
| Inloggning med organisationskonto? | Frivilligt: verifiering med skolkontot via Microsoft Entra ID (multitenant, offentlig klient, PKCE) eller Google, med behörigheterna `openid`, `profile` och `email`. IT godkänner appen en gång, se [Verifiering med skolkonto](skolkonto.md). |

## Barnets trygghet

| Fråga | Svar |
|---|---|
| Kan en obehörig utge sig för att vara lärare? | En ny lärare får ingenting förrän vårdnadshavaren uttryckligen har godkänt just den läraren, och eleven kan inte själv koppla in en lärare. Se [Barnets trygghet](trygghet.md). |
| Kan misstankar anmälas? | Ja. Vårdnadshavaren anmäler i Läxspelet, läraren spärras direkt och anmälan går till rektorn i Lärarrummet. |
| Chatt mellan lärare och elev? | Nej. Utskick går till vårdnadshavarens inkorg för granskning. |

## Drift, sårbarheter och utveckling

| Fråga | Svar |
|---|---|
| Hur distribueras appen? | Microsoft Store (granskning pågår; signerad av Microsoft och kan delas ut med Intune) eller installationsprogram från GitHub med SHA-256-fingeravtryck. |
| Uppdateringar? | Store: sköts av Store. Installationsprogrammet: appen kontrollerar fingeravtrycket innan den installerar. IT kan stänga av automatiska uppdateringar (`Uppdateringar = av`). |
| Komponentförteckning (SBOM)? | Ja, CycloneDX för varje version, bifogad i releasen. |
| Sårbarhetshantering? | Privat rapportering via GitHub (Security → Report a vulnerability), se [SECURITY.md](../SECURITY.md). |
| Telemetri eller analys? | Ingen. Ingen reklam. |
| Nätverk? | Se avsnitt 6 i informationen till skolor: HTTPS ut till GitHub och familjerna, TCP och UDP 8770 i det lokala nätet. |
| AI? | Lärarrummet använder ingen AI. |
| Tillgänglighet? | Granskad mot WCAG 2.1 AA, se [Tillgänglighetsredogörelse](tillganglighet.md). |

## Regelverk
Se [Regelverken i Sverige](efterlevnad.md) (GDPR, skollagen, OSL, arkivlagen, cybersäkerhetslagen, AI-förordningen) och mallarna för konsekvensbedömning, registerförteckning, rektorsbeslut och information till vårdnadshavare i [mallar/](mallar/).
