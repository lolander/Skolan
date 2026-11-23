# Läxspelet Lärare: information till skolor, IT och dataskyddsombud

*Gäller Läxspelet Lärare 0.12.0 och Läxspelet 1.98.0 och senare. Senast uppdaterad: 23 november 2026.*

**Snabbt:** [Kom igång på nivå 0 (en sida)](larare-niva0.md) · [Regelverken i Sverige](efterlevnad.md) · [Prova appen utan att installera](https://lolander.github.io/Skolan/demo/) · [Mallar i Word](mallar/) · [IT-paket](https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Larare-IT.zip) · [Säkerhet](../SECURITY.md)

Det här dokumentet är till för rektorer, IT-avdelningar och dataskyddsombud. Läs det **innan** appen installeras på skolans datorer. Det beskriver vad appen gör, vilka uppgifter den hanterar, hur spärrarna fungerar och hur skolan själv bestämmer nivån. Dokumentet är ett underlag för skolans egen bedömning och ersätter inte den. Huvudmannen (kommunen eller friskolan) är alltid personuppgiftsansvarig för skolans behandling av elevuppgifter.

Källkoden är öppen (MIT-licens): https://github.com/lolander/Skolan (mappen `larare/`). Allt som står här går att kontrollera i koden.

---

## 1. Kort sammanfattning

| | |
|---|---|
| **Vad** | Ett Windows-program för lärare som kompletterar familjernas Läxspelet (en läxapp hemma). Läraren skickar veckobrev, glosor, studiematerial och provdatum till familjerna. |
| **Var finns data** | Bara på lärarens dator. Ingen server, inget moln, inget konto hos utvecklaren. Utvecklaren får aldrig någon data. |
| **AI** | Lärarappen använder ingen AI och skickar inget till någon AI-tjänst. |
| **Personuppgifter** | Som standard **inga** (nivå 0). Nivå 1 och 2 måste beslutas av skolans rektor i appen, och skolans IT kan låsa en högsta nivå per dator. |
| **Roller** | Rektorn utser mentorer per klass. Mentorn godkänner ämneslärarna (ämnen, och hela klassen eller vissa elever). Familjens app kontrollerar själv de signerade besluten. En lärare utan roll får bara nivå 0 hos familjerna. |
| **Familjen bestämmer också** | Varje funktion fungerar bara när både läraren och vårdnadshavaren har slagit på den. Vårdnadshavaren kan när som helst stänga av eller koppla bort läraren. |
| **Mobiler i skolan** | Behövs inte. Vårdnadshavaren skickar en länk till läraren, till exempel med e-post. |
| **Installation** | Per användare utan administratör, eller för alla användare av IT. Grupprincipmall (ADMX) och Intune-instruktioner finns. |
| **Frivilligt** | Appen ersätter inte skolans lärplattform. Elever utan Läxspelet får allt via skolans ordinarie kanaler. |

---

## 2. De tre nivåerna

Varje lärare har en nivå. Utan beslut från en rektor gäller **nivå 0**.

### Nivå 0: inga personuppgifter
- Veckobrev, studiematerial och scheman till hela klassen.
- Riktlinjer till elevernas AI-hjälplärare (hur läraren vill att ett ämne förklaras). AI:n finns hos familjen, inte i lärarappen.
- Klasslag: klassen bekämpar en gemensam "boss". Läraren ser bara klassens summa.
- **Klassens insikt**: till exempel vilka glosor många i klassen missar och hur många som har börjat plugga inför ett prov. Bara summor. Inget visas förrän minst **5 familjer** är med, och ett ord visas bara om minst **2 familjer** har missat det. Familjerna skickar en ny slumpad kod varje vecka i stället för elevens id, utan namn och utan datum.
- Meddelanden mellan lärare på skolan. Lärarna ska inte skriva uppgifter om elever i meddelandena.
- **Inga elevnamn sparas.** Familjerna visas som "Familj 1, 2, 3 …". Klasslänken innehåller en slumpad nyckel och inget namn.

### Nivå 1: elevnamn
Som nivå 0, och dessutom:
- Elevernas namn (det namn vårdnadshavaren har valt att visa).
- Grupper och gruppuppgifter (eleverna ser vilka som är i samma grupp).
- Elevens schema, om vårdnadshavaren delar det.

### Nivå 2: uppgifter om enskilda elever
Som nivå 1, och dessutom det vårdnadshavaren väljer att dela:
- Veckorapporter, statistik och studieteknik (hur eleven pluggar hemma).
- Lappar från vårdnadshavaren (vad eleven tycker är svårt) och underlag till utvecklingssamtal.
- Provresultat per elev, som läraren skickar till familjen.
- Lärarens anteckningar om en elev.
- Delning med elevens mentor: ämneslärarens provresultat och anteckningar går bara till elevens mentor, och en ämneslärare får bara anteckningar i sitt eget ämne. Det vårdnadshavaren delat med en lärare skickas aldrig vidare till kollegor.

Rektorn kan också välja enskilda funktioner i stället för en hel nivå. Ett exempel: nivå 1 och provresultat, men inga anteckningar.

---

## 3. Rektorn i appen

- En lärare skapar skolan i appen och blir då **rektor i appen**. Rollen kan lämnas över till en kollega, till exempel till skolans rektor eller den rektorn utser.
- Rektorn bestämmer en **standard** för alla lärare och kan ge enskilda lärare andra behörigheter.
- Ett beslut om nivå 1 eller 2 kräver att rektorn skriver **vad beslutet grundar sig på**, till exempel dataskyddsombudets bedömning eller ett diarienummer.
- Besluten **signeras digitalt** av rektorn (Ed25519). Lärarnas appar godtar bara beslut som är signerade av den rektor de redan litar på, så en lärare kan inte höja sin egen nivå.
- Alla beslut sparas i en **beslutslogg** (tid, vem, vad och grund) som kan laddas ner som Excel/CSV, till exempel till dataskyddsombudet eller för diarieföring.
- **När en nivå sänks** tar lärarens app genast bort kopior av elevuppgifter som inte längre är tillåtna, och namnen ersätts med "Familj N". Lärarens egna anteckningar och provresultat döljs och skickas inte längre. Läraren ser hur många de är och kan radera dem.

### Mentorer och ämneslärare
Från lärarappen 0.12.0 bestämmer lärarna inte själva vilken roll de har hos familjerna.
- **Rektorn utser mentorn** för varje klass (🔐 Behörighet → Varje lärare → Mentor för klass). Beslutet signeras och hamnar i beslutsloggen.
- **Mentorn godkänner ämneslärarna** för sin klass (🔐 Behörighet → Ämneslärare för klassen): vilka ämnen, och hela klassen eller bara vissa elever (till exempel språkval). Godkännandet signeras med mentorns nyckel. Mentorn tar bort det när läraren slutar undervisa klassen.
- **Familjens Läxspelet kontrollerar själv** rektorns intyg och mentorns godkännande. En ämneslärare får uppgifter bara i de godkända ämnena och bara om de godkända eleverna. Den som inte har någon roll får bara det som är nivå 0, oavsett vilken nivå rektorn har gett.
- **Vårdnadshavaren godkänner skolan och rektorn** första gången, och igen om rektorn byts. Rektorsbytet är signerat av den förra rektorn.
- Intyg och godkännanden gäller i högst **45 dagar** och förnyas automatiskt när rektorns och mentorns appar är igång.

### Skolans IT kan låsa en högsta nivå
IT kan sätta en högsta nivå per dator med grupprinciper eller Intune. Den gäller **oavsett vad rektorn beslutar** (se avsnitt 7). Kommunen kan alltså till exempel bestämma att alla datorer har högst nivå 0 tills en konsekvensbedömning är gjord.

---

## 4. Vad vårdnadshavaren styr

Familjens Läxspelet körs hemma hos familjen och ingår inte i skolans system.
- Varje funktion är **av** tills vårdnadshavaren slår på den. Den fungerar bara när både vårdnadshavaren och läraren har den på.
- Vårdnadshavaren kan välja olika för olika lärare och kan koppla bort en lärare eller alla lärare. Klasslänken byts då och den gamla slutar fungera.
- Vårdnadshavaren godkänner skolan och rektorn innan någon lärare får mer än nivå 0, och igen om skolan byter rektor.
- Läxspelet visar för varje lärare vilken roll skolan har gett: mentor (rektorns beslut), ämneslärare i vissa ämnen (mentorns godkännande) eller ingen roll.
- Allt läraren skickar (veckobrev, material, provresultat, riktlinjer) hamnar i vårdnadshavarens inkorg och läggs in först när vårdnadshavaren har godkänt det.
- Lappar och underlag till utvecklingssamtal skickas bara när vårdnadshavaren själv väljer det. Vårdnadshavaren ser exakt vad som skickas.
- Om läraren har nivå 0 skickar familjens Läxspelet inte barnets namn, elev-id eller lista över lärare alls.

**Bra att veta:** det läraren skickar till familjen (till exempel ett veckobrev) kan läsas av den AI-tjänst familjen har valt i sin egen app. Läraren bör därför inte skriva personuppgifter i veckobrev eller studiematerial.

---

## 5. Tekniska skydd

| Område | Skydd |
|---|---|
| Lärarens sida | Visas bara på datorn själv (`http://localhost:8770`). Andra datorer och mobiler på nätverket kan inte se eller ändra något. |
| Data på datorn | `%APPDATA%\SkolanLarare\klass.dat` krypteras med lärarens Windows-konto (DPAPI). Appen kontrollerar att krypteringen går att läsa tillbaka innan den används. Om krypteringen inte fungerar sparas datan okrypterat och appen visar en varning. |
| Synk med kollegor | Krypterad med AES-256-GCM och signerad med HMAC-SHA256, med en nyckel som bara skolans lärare har. Meddelanden äldre än 15 minuter godtas inte. |
| Gå med i skolan | Kräver en kod som gäller i 7 dagar. Högst 10 felaktiga försök per timme och adress. Skolans nyckel skickas krypterad med koden och aldrig i klartext. |
| Rektorsbeslut | Signerade med Ed25519 (se avsnitt 3). |
| Synk till familjen | Signerad med lärarappens egen nyckel (Ed25519) och högst 15 minuter gammal. Familjens app knyter nyckeln till läraren vid första synken och godtar sedan bara den. |
| Roller | Rektorns intyg (behörighet, mentor för klasser) och mentorns godkännande av ämneslärare är signerade (Ed25519) och gäller högst 45 dagar. Familjens app sparar det senaste, så att sänkta behörigheter och borttagna godkännanden slår igenom. |
| Familjens Läxspelet | Nås bara via HTTPS med en hemlig nyckel i länken. Länkar till privata adresser godtas inte. |
| Uppdateringar | Hämtas från projektets GitHub-sida. Appen installerar bara filer vars SHA-256-fingeravtryck stämmer. IT kan stänga av automatiska uppdateringar (se avsnitt 7). |
| Ingen insamling | Ingen telemetri, ingen analys, ingen reklam, inga konton. |

### Begränsningar
- **Kodsignering:** installationsfilerna signeras via SignPath Foundation, och Store-versionen av Microsoft (se [kodsignering](kodsignering.md)). Tills signeringen är på plats kan Windows SmartScreen varna. Kontrollera då fingeravtrycket (`.sha256`-filen bredvid installationsfilen) eller bygg själv från källkoden.
- **Komponentlista:** varje version har en SBOM (CycloneDX) med alla bibliotek som följer med. Säkerhetsbrister rapporteras enligt [SECURITY.md](../SECURITY.md).
- Mappen `%APPDATA%\SkolanLarare\filer` (PDF och foton som läraren laddar upp) och loggfilen `larare.log` är **inte** krypterade. Lägg inte känsliga dokument där.
- DPAPI skyddar mot att någon läser filen från en stulen dator eller ett annat konto. Det skyddar inte mot den som är inloggad som läraren. Använd skolans vanliga skydd: skärmlås och diskkryptering (BitLocker).
- **Fördröjning när något dras in:** sänker rektorn en behörighet eller tar mentorn bort ett godkännande, slår det igenom hos en familj nästa gång någon av skolans lärare synkar med familjen. Synkar ingen annan lärare kan ett gammalt intyg gälla i högst 45 dagar.
- **Rektorns app behöver startas** minst var femte vecka (till exempel efter sommarlovet). Annars går intygen ut och lärarna får nivå 0 hos familjerna tills rektorns app har varit igång.
- **Familjer utan Nabu Casa** når lärarappen via en Cloudflare-tunnel. Trafiken är krypterad men passerar Cloudflare, som tekniskt kan läsa den. Det är ytterligare ett skäl att inte skriva personuppgifter i veckobrev och material.
- Appen sänder en kort signal på det lokala nätverket (UDP 8770) med skolans id, lärarens id och port, så att kollegornas appar hittar varandra. Signalen innehåller inga elevuppgifter.

---

## 6. Nätverk

| Riktning | Vart | Varför |
|---|---|---|
| Ut, HTTPS 443 | `api.github.com`, `github.com`, `release-assets.githubusercontent.com` | Kolla och hämta uppdateringar (var 6:e timme, kan stängas av). |
| Ut, HTTPS 443 | Familjernas Läxspelet, t.ex. `*.ui.nabu.casa` eller `*.trycloudflare.com` | Synka med familjer som har kopplat läraren. |
| Lokalt nät, TCP 8770 | Kollegornas datorer | Synk mellan lärare i samma skola (krypterad). |
| Lokalt nät, UDP 8770 | Broadcast | Hitta kollegor (se avsnitt 5). Om broadcast är spärrat kan läraren skriva in kollegans adress. |
| In, TCP 8770 (valfritt) | Elevernas mobiler | Bara om läraren vill att elever ansluter på lektionen. Kräver en brandväggsregel (administratör). **Behövs inte** om vårdnadshavaren skickar klasslänken. |

---

## 7. För IT: installation och styrning

**IT-paket:** [Laxspelet-Larare-IT.zip](https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Larare-IT.zip) innehåller grupprincipmallen (ADMX/ADML på svenska och engelska), färdiga `.reg`-filer och instruktioner för Intune.

**Installation**
- Installationsfil: `Laxspelet-Larare-Setup.exe` från https://github.com/lolander/Skolan/releases/latest
- **Per användare** (standard): `%LOCALAPPDATA%\Programs\Laxspelet Larare`, ingen administratör. Tyst: `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` (Intune: *Användare*). Appen uppdaterar sig själv om IT inte stänger av det.
- **För alla användare**: lägg till `/ALLUSERS` (Intune: *System*). Appen hamnar i `%ProgramFiles%\Laxspelet Larare` och **uppdaterar aldrig sig själv**, så IT styr versionen. `/MERGETASKS="brandvagg"` skapar brandväggsregeln (TCP 8770, privat och domän).
- **Microsoft Store**: när appen finns där kan den läggas till i Intune som *Microsoft Store-app (ny)*. Signerad av Microsoft, och Store sköter uppdateringarna.
- Data: `%APPDATA%\SkolanLarare\`. **Avinstallation raderar inte datan.** Läraren raderar den i appen (🔐 Behörighet → 🗑️ Radera klassens data), eller så tar IT bort mappen.

**Grupprinciper / Intune** (registret, `HKLM` eller `HKCU`):

```
HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Laxspelet Larare
  MaxNiva        REG_DWORD  0, 1 eller 2   Högsta nivå på datorn, oavsett rektorns beslut
  Uppdateringar  REG_SZ     automatisk | manuell | av
```

- Om värdet finns både i `HKLM` och `HKCU` gäller det strängaste.
- Med `Uppdateringar = av` kontaktar appen inte GitHub, och IT distribuerar nya versioner själv.
- Läraren ser i appen att inställningarna är låsta av IT.

Exempel (PowerShell som administratör):

```powershell
New-Item -Path "HKLM:\SOFTWARE\Policies\Laxspelet Larare" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Laxspelet Larare" -Name MaxNiva -Type DWord -Value 0
Set-ItemProperty -Path "HKLM:\SOFTWARE\Policies\Laxspelet Larare" -Name Uppdateringar -Value manuell
```

---

## 8. Gallring och allmänna handlingar

- I appen kan läraren radera alla elevuppgifter på en gång, till exempel när läsåret är slut (**🔐 Behörighet → 🗑️ Radera klassens data**). Inställningar, veckobrev och skolan finns kvar.
- Historiken kan laddas ner som Excel/CSV, och rektorns beslutslogg likaså. Det underlättar om skolan behöver diarieföra eller arkivera något innan gallring.
- Hur länge uppgifter sparas i appen: historik högst 5 000 rader, anteckningar högst 1 000, meddelanden mellan lärare högst 300. Klassens insikt används bara för innevarande vecka, och äldre veckor tas bort vid nästa synk.
- I kommunala skolor kan uppgifter i appen vara allmänna handlingar, och vissa kan omfattas av sekretess. Skolans dokumenthanteringsplan avgör hur de ska hanteras. Det är ett skäl att börja med nivå 0.

---

## 9. Skollagen och likvärdighet

Appen är byggd för att vara ett **frivilligt komplement**. Då stämmer den med skollagens krav. Skolan ansvarar för att den används så.

- **Avgiftsfri utbildning (10 kap. 10 § skollagen):** familjerna får inte behöva skaffa något för att få del av undervisningen. Allt läraren skickar via appen ska därför också finnas i skolans ordinarie kanaler (lärplattform, papper). Ingen elev får krävas att använda Läxspelet.
- **Likvärdig utbildning (1 kap. 9 §):** elever utan Läxspelet får inte gå miste om något. Klasslaget räknar in det hela klassen gör i klassrummet (lärarens "Klassens plugg"), och läraren ser aldrig enskilda elevers poäng. Klassens insikt beskriver bara de familjer som är med och ska inte användas som en bild av hela klassen.
- **Bedömning och betyg:** det familjen delar (statistik, studieteknik, hur mycket eleven pluggar hemma) beskriver arbete hemma och ska **inte** användas som underlag för betyg eller bedömning. Det är ett stöd för samtal med eleven och vårdnadshavaren.
- **Information om elevens utveckling (10 kap. 12–13 §§, utvecklingssamtal):** appen ersätter inte skolans dokumentation, till exempel den individuella utvecklingsplanen eller skriftliga omdömen. Familjens underlag till utvecklingssamtalet är vårdnadshavarens eget.
- **Kränkande behandling (6 kap.):** appen visar inga jämförelser eller topplistor mellan elever för läraren. Gruppernas sammansättning syns för eleverna i gruppen (nivå 1). Läraren bör tänka på det som vid all gruppindelning.
- **Rektorns ansvar (2 kap. 10 §):** rektorn beslutar om enhetens inre organisation. Därför är det rektorn som i appen bestämmer vad lärarna får göra.
- **Mobiltelefoner i skolan:** inget i appen kräver att elever använder mobilen i skolan. Vårdnadshavaren skickar klasslänken hemifrån.

### Lärarna får reglerna i appen
Första gången appen startas, och när reglerna ändras, måste läraren läsa och kvittera **📘 Så gör du rätt** (frivilligt komplement, inga elevuppgifter i utskick, inte för betyg, insikten gäller bara de som är med, saklighet i anteckningar, bara det rektorn beslutat, gallring). Kvitteringen sparas i lärarens historik. Dessutom visas korta påminnelser där det är lätt att göra fel: när läraren skriver veckobrev, material, provresultat, anteckningar och meddelanden, delar in grupper, och tittar på statistik, studieteknik, rapporter och lappar.

## 10. Rekommenderad väg för en skola

1. **Börja med nivå 0.** Inga personuppgifter om elever behandlas. Se [Kom igång på nivå 0](larare-niva0.md). Sätt gärna `MaxNiva = 0` centralt med grupprincipmallen.
2. **Låt en lärare prova** under en termin, frivilligt för familjerna och parallellt med skolans lärplattform.
3. **Vill skolan använda nivå 1 eller 2:** gör en bedömning med dataskyddsombudet (bilaga B och [exemplet i Word](mallar/Konsekvensbedomning-exempel.docx)), för in behandlingen i registerförteckningen (bilaga A), informera vårdnadshavarna (bilaga D) och fatta ett rektorsbeslut (bilaga C). Alla finns som [Word-mallar](mallar/). Rektorn ger sedan behörigheten i appen och skriver beslutets diarienummer som grund. IT höjer `MaxNiva` på de datorer det gäller.
4. **Utse mentorer:** rektorn anger vilka klasser varje mentor har. Mentorerna godkänner sedan ämneslärarna för sina klasser.
5. **Underlag från appen:** 🔐 Behörighet → 🧾 Skapa underlag ger en utskrivbar sida med skolans faktiska inställningar, lärarnas nivåer, registerförteckningen och beslutsloggen, utan elevuppgifter. Bifoga den till beslutet.

---

## Bilaga A: underlag till registerförteckningen (artikel 30)

| | Nivå 1 | Nivå 2 |
|---|---|---|
| Ändamål | Planera undervisning och grupparbeten. Kommunicera läxor och material till vårdnadshavare. | Som nivå 1, och följa upp elevens studier hemma i samarbete med vårdnadshavaren. Underlag till utvecklingssamtal. |
| Rättslig grund | Uppgift av allmänt intresse (artikel 6.1 e), skollagen. Skolan avgör. | Som nivå 1. Skolan avgör. |
| Kategorier av registrerade | Elever, lärare | Elever, vårdnadshavare (det de skriver), lärare |
| Kategorier av uppgifter | Namn, grupptillhörighet, schema | Som nivå 1, och studievanor, provresultat, lärarens anteckningar och vårdnadshavarens lappar |
| Mottagare | Elevens vårdnadshavare (via familjens app) | Som nivå 1, och elevens mentor på skolan |
| Överföring till tredje land | Lärarappen skickar inget till molntjänster. Familjer som använder Läxspelets gratistunnel tar emot synken via Cloudflare (USA, EU–US Data Privacy Framework), som tekniskt kan läsa trafiken. Med Nabu Casa är den krypterad hela vägen. Se [regelverken](efterlevnad.md#överföring-till-tredje-land-dataskyddsförordningen-kapitel-v). | Som nivå 1 |
| Lagring | Lärarens dator, krypterad (DPAPI) | Som nivå 1 |
| Gallring | Enligt skolans dokumenthanteringsplan, med funktionen "Radera klassens data" | Som nivå 1 |
| Säkerhetsåtgärder | Se avsnitt 5 | Se avsnitt 5 |

## Bilaga B: frågor till konsekvensbedömningen

- Behövs nivå 1 eller 2 för ändamålet, eller räcker nivå 0 (klassens insikt utan namn)?
- Vilka lärare behöver vilken nivå? (Ämneslärare behöver ofta bara nivå 1.)
- Vem är mentor för vilka klasser, och hur ser mentorerna till att bara rätt ämneslärare godkänns, för rätt elever (till exempel språkval)? Hur tas godkännanden bort när en lärare slutar?
- Elever är barn och därför särskilt skyddsvärda. Det är vårdnadshavaren som väljer vad som delas, och delningen är frivillig. Hur informeras vårdnadshavarna (bilaga D)?
- Finns risk att uppgifter omfattas av sekretess, till exempel anteckningar om hälsa eller stöd? Ge i så fall inte rätten "Anteckningar om elever", eller ge tydliga instruktioner.
- Är lärarnas datorer krypterade (BitLocker) och har de skärmlås?
- Hur sker gallring och eventuell arkivering (avsnitt 8)?
- Likvärdighet: elever utan Läxspelet får samma information via skolans ordinarie kanaler.

## Bilaga C: mall för rektorsbeslut

> **Beslut om användning av Läxspelet Lärare**
> Skola: … Datum: … Diarienummer: …
> Rektor beslutar att lärarna på skolan får använda Läxspelet Lärare med följande behörigheter:
> - Standard för alla lärare: nivå 0 (inga personuppgifter).
> - [Namn]: nivå … , funktioner: …
>
> Beslutet grundar sig på: dataskyddsombudets bedömning [datum/dnr], registerförteckning [dnr].
> Användningen är frivillig för vårdnadshavarna och ersätter inte skolans lärplattform. Uppgifter gallras enligt dokumenthanteringsplanen.
> Beslutet förs in i appens beslutslogg med diarienumret som grund.
>
> Underskrift: …

## Bilaga D: informationstext till vårdnadshavare

> **Läxspelet och skolan**
> Vissa lärare på skolan använder Läxspelet Lärare för att skicka veckobrev, glosor och studiematerial direkt till familjer som använder Läxspelet hemma. Det är frivilligt och ersätter inte [skolans lärplattform], där all information också finns.
>
> Första gången en lärare från skolan kopplar sig frågar Läxspelet om du godkänner [skolans namn] och rektor [namn]. Rektorn utser ditt barns mentor, och mentorn godkänner ämneslärarna. Läxspelet visar vilken roll varje lärare har.
>
> Du bestämmer själv i Läxspelet vad som delas med läraren. Allt är avstängt tills du slår på det, och du kan stänga av eller koppla bort läraren när du vill. Det läraren skickar läggs in först när du har godkänt det.
>
> Läxspelet är ett komplement. Det ersätter varken ditt stöd i läxarbetet eller skolans undervisning och kontakten med läraren.
>
> [Om skolan använder nivå 0:] Läraren får inga uppgifter om ditt barn, bara hela klassens summor (till exempel vilka glosor många missar), och först när minst fem familjer är med.
>
> [Om skolan använder nivå 1 eller 2:] Läraren kan få [elevens namn / det du väljer att dela, till exempel veckorapporter]. Uppgifterna sparas krypterat på lärarens dator och gallras enligt skolans regler. [Kommunen/huvudmannen] är personuppgiftsansvarig. Kontakt: dataskyddsombudet, [e-post].

---

Frågor eller förslag: https://github.com/lolander/Skolan/issues
