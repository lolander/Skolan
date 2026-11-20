# Läxspelet Lärare: information till skolor, IT och dataskyddsombud

*Gäller Läxspelet Lärare 0.10.0 och senare. Senast uppdaterad: 20 november 2026.*

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
| **Familjen bestämmer också** | Varje funktion fungerar bara när både läraren och vårdnadshavaren har slagit på den. Vårdnadshavaren kan när som helst stänga av eller koppla bort läraren. |
| **Mobiler i skolan** | Behövs inte. Vårdnadshavaren skickar en länk till läraren, till exempel med e-post. |
| **Installation** | Per användare, ingen administratörsrätt behövs. Kan installeras tyst och styras med grupprinciper. |
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

### Skolans IT kan låsa en högsta nivå
IT kan sätta en högsta nivå per dator med grupprinciper eller Intune. Den gäller **oavsett vad rektorn beslutar** (se avsnitt 7). Kommunen kan alltså till exempel bestämma att alla datorer har högst nivå 0 tills en konsekvensbedömning är gjord.

---

## 4. Vad vårdnadshavaren styr

Familjens Läxspelet körs hemma hos familjen och ingår inte i skolans system.
- Varje funktion är **av** tills vårdnadshavaren slår på den. Den fungerar bara när både vårdnadshavaren och läraren har den på.
- Vårdnadshavaren kan välja olika för olika lärare och kan koppla bort en lärare eller alla lärare. Klasslänken byts då och den gamla slutar fungera.
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
| Familjens Läxspelet | Nås bara via HTTPS med en hemlig nyckel i länken. Länkar till privata adresser godtas inte. |
| Uppdateringar | Hämtas från projektets GitHub-sida. Appen installerar bara filer vars SHA-256-fingeravtryck stämmer. IT kan stänga av automatiska uppdateringar (se avsnitt 7). |
| Ingen insamling | Ingen telemetri, ingen analys, ingen reklam, inga konton. |

### Begränsningar
- **Programmet är inte kodsignerat ännu.** Windows SmartScreen kan varna. Kontrollera fingeravtrycket (`.sha256`-filen bredvid installationsfilen på GitHub) eller bygg själv från källkoden.
- Mappen `%APPDATA%\SkolanLarare\filer` (PDF och foton som läraren laddar upp) och loggfilen `larare.log` är **inte** krypterade. Lägg inte känsliga dokument där.
- DPAPI skyddar mot att någon läser filen från en stulen dator eller ett annat konto. Det skyddar inte mot den som är inloggad som läraren. Använd skolans vanliga skydd: skärmlås och diskkryptering (BitLocker).
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

**Installation**
- Installationsfil: `Laxspelet-Larare-Setup.exe` från https://github.com/lolander/Skolan/releases/latest
- Installeras per användare i `%LOCALAPPDATA%\Programs\Laxspelet Larare`. Ingen administratör behövs.
- Tyst installation: `Laxspelet-Larare-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` (körs i användarens kontext, t.ex. via Intune som "User"-installation).
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

1. **Börja med nivå 0.** Inga personuppgifter behandlas. Det enda som krävs är att IT godkänner programmet. Sätt gärna `MaxNiva = 0` centralt.
2. **Låt en lärare prova** under en termin, frivilligt för familjerna och parallellt med skolans lärplattform.
3. **Vill skolan använda nivå 1 eller 2:** gör en bedömning med dataskyddsombudet (bilaga B), för in behandlingen i registerförteckningen (bilaga A), informera vårdnadshavarna (bilaga D) och fatta ett rektorsbeslut (bilaga C). Rektorn ger sedan behörigheten i appen och skriver beslutets diarienummer som grund. IT höjer `MaxNiva` på de datorer det gäller.

---

## Bilaga A: underlag till registerförteckningen (artikel 30)

| | Nivå 1 | Nivå 2 |
|---|---|---|
| Ändamål | Planera undervisning och grupparbeten. Kommunicera läxor och material till vårdnadshavare. | Som nivå 1, och följa upp elevens studier hemma i samarbete med vårdnadshavaren. Underlag till utvecklingssamtal. |
| Rättslig grund | Uppgift av allmänt intresse (artikel 6.1 e), skollagen. Skolan avgör. | Som nivå 1. Skolan avgör. |
| Kategorier av registrerade | Elever, lärare | Elever, vårdnadshavare (det de skriver), lärare |
| Kategorier av uppgifter | Namn, grupptillhörighet, schema | Som nivå 1, och studievanor, provresultat, lärarens anteckningar och vårdnadshavarens lappar |
| Mottagare | Elevens vårdnadshavare (via familjens app) | Som nivå 1, och elevens mentor på skolan |
| Överföring till tredje land | Nej. Lärarappen skickar inget till molntjänster. | Nej |
| Lagring | Lärarens dator, krypterad (DPAPI) | Som nivå 1 |
| Gallring | Enligt skolans dokumenthanteringsplan, med funktionen "Radera klassens data" | Som nivå 1 |
| Säkerhetsåtgärder | Se avsnitt 5 | Se avsnitt 5 |

## Bilaga B: frågor till konsekvensbedömningen

- Behövs nivå 1 eller 2 för ändamålet, eller räcker nivå 0 (klassens insikt utan namn)?
- Vilka lärare behöver vilken nivå? (Ämneslärare behöver ofta bara nivå 1.)
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
> Du bestämmer själv i Läxspelet vad som delas med läraren. Allt är avstängt tills du slår på det, och du kan stänga av eller koppla bort läraren när du vill. Det läraren skickar läggs in först när du har godkänt det.
>
> [Om skolan använder nivå 0:] Läraren får inga uppgifter om ditt barn, bara hela klassens summor (till exempel vilka glosor många missar), och först när minst fem familjer är med.
>
> [Om skolan använder nivå 1 eller 2:] Läraren kan få [elevens namn / det du väljer att dela, till exempel veckorapporter]. Uppgifterna sparas krypterat på lärarens dator och gallras enligt skolans regler. [Kommunen/huvudmannen] är personuppgiftsansvarig. Kontakt: dataskyddsombudet, [e-post].

---

Frågor eller förslag: https://github.com/lolander/Skolan/issues
