# Läxspelet i Microsoft Store

I Store signerar Microsoft appen, så Windows visar ingen varning, och Store sköter uppdateringarna.

## 1. Skaffa ett utvecklarkonto (gratis för privatpersoner)
1. Gå till https://storedeveloper.microsoft.com och logga in med ditt Microsoft-konto.
2. Välj **Individual** (privatperson) och fyll i namn, land (Sverige) och kontaktuppgifter.
3. Verifiera dig (e-post, ibland legitimation). Det kan ta från några minuter till ett par dagar.

## 2. Reservera namnet
1. I Partner Center: **Apps and games → New product → MSIX or PWA app**.
2. Reservera namnet **Läxspelet** (eller ett annat om det är upptaget).
3. Öppna **Product management → Product identity**. Där står tre värden:
   - `Package/Identity/Name` (t.ex. `12345David.Laxspelet`)
   - `Package/Identity/Publisher` (t.ex. `CN=ABCD1234-...`)
   - `Package/Properties/PublisherDisplayName` (ditt namn)

## 3. Lägg in värdena i GitHub
I repot: **Settings → Secrets and variables → Actions → Variables → New repository variable**:
- `STORE_NAMN` = Package/Identity/Name
- `STORE_PUBLISHER` = Package/Identity/Publisher
- `STORE_PUBLISHER_NAMN` = PublisherDisplayName

(Eller skicka dem till Claude så läggs de in.)

## 4. Ladda upp paketet
1. Nästa bygge på GitHub (fliken **Actions → Windowsappen**) skapar artefakten **Laxspelet-Store** med en `.msix`-fil.
2. I Partner Center: **Start your submission**. Fyll i pris (gratis), ålder (familjeapp), beskrivning och skärmbilder.
3. Under **Packages**: ladda upp `.msix`-filen.
4. Under **Submission options / Restricted capabilities**: förklara `runFullTrust`:
   *”Läxspelet är en skrivbordsapp (Python) som kör en lokal webbserver för familjens mobiler i hemnätverket och visar en ikon vid klockan.”*
5. Skicka in. Microsoft granskar, oftast inom några dagar.

Nya versioner: ladda upp den nya `.msix`-filen i en ny submission.

---

## Läxspelet Lärare i Store
Samma konto. Store-versionen är signerad av Microsoft, gratis, och skolor kan lägga till den i Intune som *Microsoft Store-app (ny)*.
1. **New product → MSIX or PWA app**, reservera namnet **Läxspelet Lärare**.
2. Lägg in Product identity-namnet som GitHub-variabeln `STORE_LARARE_NAMN` (`STORE_PUBLISHER` och `STORE_PUBLISHER_NAMN` är samma som för Läxspelet).
3. Bygget av lärarappen (**Actions → Lärarappen**) skapar artefakten **Laxspelet-Larare-Store** med en `.msix`-fil. Ladda upp den.
4. Kategori: Utbildning. Ålder: 3+ (appen är för lärare, ingen chatt och inga köp).
5. Förklaring av `runFullTrust`:
   *”Läxspelet Lärare är en skrivbordsapp (Python) som kör en lokal webbserver på lärarens dator. Läraren använder den i webbläsaren (localhost), och kollegor på skolan synkar krypterat via det lokala nätverket.”*
6. Integritetspolicy: https://github.com/lolander/Skolan/blob/main/docs/integritet.md

Store-versionen kollar aldrig GitHub efter uppdateringar. Det sköter Store.
