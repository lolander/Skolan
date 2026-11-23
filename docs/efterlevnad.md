# Läxspelet och regelverken i Sverige

*Senast uppdaterad: 23 november 2026. Gäller Läxspelet 1.98.0 och Läxspelet Lärare 0.12.0.*

Det här är ett underlag för den som frågar om Läxspelet följer svenska och europeiska regler om dataskydd, informationssäkerhet och AI. Det är ingen juridisk rådgivning. En skola som använder lärarappen gör sin egen bedömning tillsammans med sitt dataskyddsombud. Mer om lärarappen finns i [Information till skolor](larare-skolor.md), och vad som händer med familjens data finns i [integritetspolicyn](integritet.md).

## Kort svar

Vi känner inte till något i Läxspelet som bryter mot svensk lag eller EU-regler, med de förbehåll som står nedan. Läxspelet är byggt så att utvecklaren aldrig behandlar några personuppgifter, och så att skolan börjar utan personuppgifter (nivå 0).

Genomgången 23 november 2026 hittade tre saker som nu är åtgärdade (se [Kända brister](#kända-brister-och-åtgärder)):
1. **AI-tjänsternas villkor.** Googles villkor för Gemini kräver 18 år och tillåter inte appar som barn använder. Läxspelet rekommenderade tidigare Geminis gratisnyckel. Nu rekommenderas Mistral (europeiskt företag med gratisplan) eller Anthropic, eller en lokal AI, och varje tjänst visar sina villkor för barn när familjen väljer. Mistral kan kopplas in direkt i Läxspelet, även i Home Assistant.
2. **Tredje land.** Använder en familj Läxspelets gratistunnel (Cloudflare) passerar trafiken mellan lärare och familj ett amerikanskt företag. Underlaget till registerförteckningen sa tidigare "ingen överföring till tredje land". Det är rättat.
3. **AI-märkning för barnet.** Barnet ser nu tydligt att husdjurets, hjälplärarens och skrivverkstadens svar kommer från en AI (AI-förordningen, artikel 50).

## Vem ansvarar för vad

| Vem | Roll enligt dataskyddsförordningen | Varför |
|---|---|---|
| **Familjen** (Läxspelet hemma) | Privat användning: dataskyddsförordningen gäller inte (artikel 2.2 c, hushållsundantaget) | Föräldern installerar appen och använder den för sina egna barn. All data sparas hemma. |
| **Skolans huvudman** (lärarappen) | Personuppgiftsansvarig för skolans behandling | Lärarna använder appen i tjänsten. Huvudmannen beslutar om ändamål och nivå (rektorsbeslut). |
| **Utvecklaren** | Varken personuppgiftsansvarig eller personuppgiftsbiträde | Det finns ingen server och ingen insamling. Utvecklaren får aldrig någon data. Därför behövs inget biträdesavtal. |
| **AI-tjänsten** som familjen väljer | Familjens egen leverantör | Familjen tecknar avtal och skapar nyckel själv. Tjänstens villkor gäller. |
| **Cloudflare / Nabu Casa** (fjärråtkomst) | Familjens egen leverantör | Familjen väljer själv. Lärarappen ansluter till den adress familjen har gett. |

## Regelverk för regelverk

### Dataskyddsförordningen och dataskyddslagen (2018:218)
**Gäller** skolans behandling i lärarappen. Familjens användning omfattas inte (hushållsundantaget).

**Så uppfylls kraven:**
- **Inbyggt dataskydd och dataminimering** (artikel 5 och 25): nivå 0 är standard och innebär att inga elevnamn och inga uppgifter om enskilda elever behandlas. Allt är avstängt tills både vårdnadshavaren och läraren slår på det.
- **Rättslig grund** (artikel 6.1 e): uppgift av allmänt intresse enligt skollagen. Skolan avgör. Mall finns i [registerförteckningen](mallar/).
- **Registerförteckning och konsekvensbedömning** (artikel 30 och 35): mallar och ett ifyllt exempel finns i [mallar](mallar/). Appen tar fram ett underlag med skolans faktiska inställningar (🔐 Behörighet → 🧾 Skapa underlag).
- **Säkerhet** (artikel 32): data på lärarens dator är krypterad med Windows-kontot (DPAPI). Synken mellan lärare är krypterad (AES-256-GCM). Rektorns beslut, mentorns godkännanden och varje synk till familjen är digitalt signerade (Ed25519). Se [Tekniska skydd](larare-skolor.md#5-tekniska-skydd).
- **Behörighetsstyrning:** rektorn bestämmer nivå per lärare och vem som är mentor. Mentorn godkänner ämneslärare per ämne och elev. IT kan låsa en högsta nivå. Familjens app kontrollerar allt detta själv.
- **Lagringsminimering och gallring** (artikel 5.1 e): "Radera klassens data" och fasta tak för historik, anteckningar och meddelanden.
- **Barn** (skäl 38): vårdnadshavaren godkänner skolan och rektorn och bestämmer vad som delas. Läraren får aldrig se jämförelser eller topplistor mellan elever.
- **Känsliga uppgifter** (artikel 9): appen är inte gjord för hälsouppgifter. Lärarna ska enligt reglerna i appen inte skriva om hälsa, diagnoser eller stöd i anteckningar.

**Att tänka på:** skolan behöver själv registerförteckning, eventuell konsekvensbedömning, information till vårdnadshavare (mall finns) och rutiner för begäran om registerutdrag och personuppgiftsincidenter.

### Överföring till tredje land (dataskyddsförordningen kapitel V)
- **Lärarappen** skickar inget till molntjänster och använder ingen AI. Den pratar direkt med kollegorna på skolans nätverk och med familjernas Läxspelet.
- **Familjer med Nabu Casa:** krypterat hela vägen. Nabu Casa kan inte läsa innehållet.
- **Familjer med Läxspelets gratistunnel (Cloudflare):** trafiken är krypterad, men Cloudflare (USA) avslutar krypteringen och kan tekniskt läsa den. Det som går den vägen är det läraren skickar till familjen och det familjen har valt att dela med läraren. Cloudflare är anslutet till EU–US Data Privacy Framework (kontrollera aktuell status i [DPF-listan](https://www.dataprivacyframework.gov/list)). Skolan bör beakta det i sin bedömning, och det är ett skäl att stanna på nivå 0 eller nivå 1.
- **Uppdateringar** hämtas från GitHub (USA). Det enda GitHub ser är datorns IP-adress. IT kan stänga av det.

### Skollagen (2010:800)
- **Avgiftsfri och likvärdig utbildning** (10 kap. 10 §, 1 kap. 9 §): appen är ett frivilligt komplement. Allt läraren skickar ska också finnas i skolans vanliga kanaler. Ingen elev får krävas att använda Läxspelet.
- **Bedömning och betyg:** det familjen delar beskriver plugg hemma och får inte användas för betyg. Regeln står i appen och lärarna måste kvittera den.
- **Rektorns ansvar** (2 kap. 10 §): rektorn bestämmer i appen vad lärarna får göra och vem som är mentor.

### Offentlighets- och sekretesslagen (2009:400) och tryckfrihetsförordningen
Uppgifter i lärarappen kan vara allmänna handlingar, och vissa kan omfattas av sekretess (till exempel 23 kap. OSL). Skolans dokumenthanteringsplan avgör hur de hanteras. Historik och beslutslogg kan laddas ner för diarieföring. Börja med nivå 0 så uppstår få sådana handlingar.

### Arkivlagen (1990:782)
Gallring ska ske enligt huvudmannens gallringsbeslut. Appen har funktionen "Radera klassens data" och export innan gallring. Appen ersätter inte skolans arkiv.

### Cybersäkerhetslagen (2025:1506, NIS2)
**Gäller kommunen som organisation** (i kraft 15 januari 2026), inte Läxspelet som produkt. Kommunen behöver hantera risker i sina system och i leverantörskedjan. Det som hjälper den bedömningen:
- öppen källkod (MIT-licens) som kan granskas,
- komponentlista (SBOM, CycloneDX) för varje version,
- SHA-256-fingeravtryck och kodsignering av installationsfilerna,
- [säkerhetspolicy och privat rapportering av sårbarheter](../SECURITY.md),
- grupprincipmall (ADMX) för att låsa nivå och uppdateringar.

**Att känna till:** Läxspelet är ett hobbyprojekt med en utvecklare. Det finns inget supportavtal och ingen garanterad svarstid.

### EU:s AI-förordning (2024/1689, ändrad genom förordning 2026/1744)
- **Lärarappen** använder ingen AI.
- **Familjens Läxspelet** använder en AI-tjänst som familjen själv väljer, för att läsa glosor från foton, förhöra, rätta övningar och låta husdjuret svara på frågor. Det är övning hemma och ingen bedömning i skolan. Det räknas därför inte som ett AI-system med hög risk inom utbildning (bilaga III punkt 3). Den delen av förordningen gäller dessutom först från 2 december 2027 efter ändringen 2026.
- **Öppenhet** (artikel 50, gäller redan): den som pratar med ett AI-system ska veta att det är en AI. Föräldrarna informeras i introduktionen, och varje vy där en AI svarar har en tydlig märkning ("🤖 … svarar med hjälp av en AI, ett datorprogram och inte en riktig person. Den kan ha fel.").
- **Förbjudna metoder** (artikel 5): appen utnyttjar inte barns sårbarhet. Det finns inga köp, ingen reklam och inga pengar i spelet. Stjärnorna går bara att använda inne i appen.

### Cyberresiliensförordningen (EU 2024/2847)
Gäller produkter som tillhandahålls i kommersiell verksamhet. Läxspelet är gratis, öppen källkod och tjänar inga pengar, och omfattas därför i nuläget inte. Vi följer ändå det förordningen kräver i stort: SBOM, hantering av sårbarheter, säkra uppdateringar med fingeravtryck och automatisk återgång om en ny version inte startar.

### Barnkonventionen (lag 2018:1197)
Barnets bästa: vårdnadshavaren styr, appen visar inga jämförelser för läraren, och introduktionen för föräldrar säger att må bra går före och att appen inte ersätter föräldern.

### Lagen om elektronisk kommunikation (cookies och lagring)
Appen använder ingen spårning, ingen analys och ingen reklam. Det som sparas i webbläsaren behövs för att appen ska fungera.

### Villkor hos AI-leverantörerna (avtal, inte lag)
Familjen ingår avtal direkt med AI-tjänsten. Flera tjänster har åldersgränser:
- **Google Gemini:** användaren måste vara 18 år, och API:et får inte användas i en tjänst som "is likely to be accessed by individuals under the age of 18". Inom EES får sådana tjänster bara använda den betalda nivån ([Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms), gäller från 23 mars 2026).
- **Övriga tjänster** har egna regler. Windowsappen visar för varje tjänst vad den säger om barn, och familjen behöver läsa villkoren för den tjänst de väljer. I Home Assistant väljer familjen AI-integration själv.
- **Anthropic** tillåter appar som barn använder, med skyddsåtgärder och tydlig AI-märkning. **OpenAI** och **Mistral** kräver förälderns samtycke. Läxspelet rekommenderar därför **Mistral**, som är ett europeiskt företag (Frankrike), så att texter och foton stannar inom EU och ingen överföring till tredje land sker. Mistral har en gratisplan, men där får Mistral använda texterna för att träna sina modeller om familjen inte stänger av det (Admin → Privacy). Alternativ: Anthropic eller en lokal AI.
- **DeepSeek** (Kina, saknar beslut om adekvat skyddsnivå) har tagits bort som val. En familj som hade valt DeepSeek får välja en ny tjänst.
- **Lokal AI** (Ollama, LM Studio) skickar inget från datorn.

### Standarder (ISO/IEC 27001, MCF:s metodstöd m.fl.)
Läxspelet är inte certifierat mot någon standard. Kraven för en kommuns ledningssystem för informationssäkerhet ligger på kommunen. Genomgången ovan och [Information till skolor](larare-skolor.md) är underlag för kommunens egen riskbedömning.

## Kända brister och åtgärder

| # | Brist | Åtgärd | Status |
|---|---|---|---|
| 1 | Läxspelet rekommenderade Geminis gratisnyckel, trots att Googles villkor inte tillåter appar som barn använder | Mistral (EU) eller Anthropic rekommenderas, eller lokal AI. Gemini visar en varning. Varje tjänst visar sina villkor för barn. Mistral kan kopplas in direkt i Läxspelet (☰ Meny → 🤖 AI-tjänst). | Klart (1.98.0) |
| 2 | DeepSeek (Kina) gick att välja | Borttaget | Klart (1.98.0) |
| 3 | Barnet såg inte alltid att svaren kom från en AI | AI-märkning i alla vyer där en AI svarar | Klart (1.98.0) |
| 4 | Bilaga A angav "ingen överföring till tredje land" även när Cloudflare-tunneln används | Rättat i [Information till skolor](larare-skolor.md) och i mallen | Klart |
| 5 | Ett godkännande som har dragits in kan gälla i högst 45 dagar om ingen annan lärare synkar med familjen | Beskrivet i dokumentationen. Kortare giltighetstid kan övervägas. | Beskrivet |
| 6 | Lärarappens filer (`filer/`) och logg är inte krypterade | Beskrivet. Diskkryptering (BitLocker) rekommenderas. | Beskrivet |
| 7 | Hobbyprojekt utan supportavtal | Beskrivet. Allt är öppen källkod och kan granskas eller tas över. | Beskrivet |

## Frågor vi kan få

**Bryter ni mot dataskyddsförordningen?**
Vi känner inte till något sådant. Utvecklaren behandlar inga personuppgifter. Skolan börjar på nivå 0 utan personuppgifter om elever, och för nivå 1 och 2 krävs ett rektorsbeslut. Familjens egen användning omfattas av hushållsundantaget.

**Är ni personuppgiftsbiträde? Behöver vi ett biträdesavtal?**
Nej. Det finns ingen server och utvecklaren tar aldrig emot några uppgifter.

**Lämnar elevuppgifter EU?**
Inte från lärarappen till någon molntjänst. Familjer som använder gratistunneln skickar dock trafiken via Cloudflare (USA, Data Privacy Framework). Med Nabu Casa är den krypterad hela vägen. Börja med nivå 0, så skickas inga elevuppgifter alls.

**Används AI för att bedöma eleverna?**
Nej. Lärarappen har ingen AI. Familjens AI används för övning hemma, och det familjen delar får inte användas för betyg.

**Är appen certifierad, till exempel enligt ISO 27001?**
Nej. Det finns öppen källkod, en komponentlista (SBOM), signerade installationsfiler, en säkerhetspolicy och dokumentation för kommunens egen riskbedömning.

**Vem ansvarar om något händer?**
Skolans huvudman för skolans uppgifter, familjen för sina. Sårbarheter rapporteras enligt [SECURITY.md](../SECURITY.md).

**Kan uppgifter i lärarappen begäras ut?**
De kan vara allmänna handlingar. Det avgör skolan enligt sin dokumenthanteringsplan. Historiken och beslutsloggen kan exporteras.

## Källor
- Dataskyddsförordningen (EU) 2016/679 och dataskyddslagen (2018:218)
- Skollagen (2010:800), offentlighets- och sekretesslagen (2009:400), arkivlagen (1990:782)
- Cybersäkerhetslagen (2025:1506): [regeringens pressmeddelande](https://regeringen.se/pressmeddelanden/2025/12/regeringen-utfardar-en-ny-cybersakerhetslag/), [prop. 2025/26:28](https://data.riksdagen.se/dokument/HD0328)
- AI-förordningen (EU) 2024/1689 och [Digital Omnibus om AI, förordning (EU) 2026/1744](https://artificialintelligenceact.eu/ai-act-explorer/digital-omnibus/)
- Cyberresiliensförordningen (EU) 2024/2847
- [IMY: användning av molntjänster inom offentlig sektor](https://www.imy.se/globalassets/dokument/rapporter/rapport---anvandning-av-molntjanster-inom-offentlig-sektor-.pdf)
- [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms)
- [Anthropic: riktlinjer för organisationer som når minderåriga](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors), [Anthropics användarpolicy](https://www.anthropic.com/legal/aup)
- [OpenAI Services Agreement](https://openai.com/policies/services-agreement/), [Mistral Commercial Terms](https://legal.mistral.ai/terms/commercial-terms-of-service)

Frågor eller synpunkter: https://github.com/lolander/Skolan/issues
