# Välja AI-tjänst till Läxspelet

*Läget den 24 november 2026. Villkoren ändras ofta, så kontrollera alltid leverantörens egna sidor (länkade under Källor) innan ni bestämmer er. Det här är en sammanställning, inte juridisk rådgivning.*

Läxspelet har ingen egen AI. Hemmet eller skolan kopplar in en AI-tjänst och ingår själv avtal med den. Därför är valet av tjänst ert, och det påverkar hur väl ni uppfyller dataskyddsförordningen (GDPR), AI-förordningen och era egna krav, till exempel enligt ISO/IEC 27001.

## Kort svar

| | Barn får använda appen | Data i EU | Tränar på er data | Avtal om personuppgifter (DPA) | Certifieringar | Kostnad |
|---|---|---|---|---|---|---|
| **Mistral AI** (Frankrike) | Ja, med förälders samtycke | Ja, som standard. Särskild EU-adress ger garanti (+10 %) | Kontrollera inställningen *Anonymous improvement data* och stäng av den | Ja | ISO 27001/27701, SOC 2 Type II (enligt Mistral) | Gratisnivån räcker inte för Läxspelet. Betala per användning med kort, ingående belopp per månad |
| **Anthropic** (Claude, USA) | Ja, om appen har skyddsåtgärder och AI-märkning | Nej, USA via EU:s standardavtalsklausuler (EU-region via Amazon Bedrock) | Nej, inte API-data | Ja, ingår | ISO 27001, ISO 42001, SOC 2 | Förbetalt med kort |
| **OpenAI** (USA) | Ja, med förälders tillstånd och extra skydd | Möjligt för godkända organisationer (+10 %) | Nej, inte API-data som standard | Ja | Inte kontrollerat, se trust.openai.com | Förbetalt med kort |
| **Google Gemini API** | **Nej.** Får inte användas i appar som personer under 18 sannolikt använder | Gratisnivån får inte användas i EES | Ja, på gratisnivån | Bara på betald nivå | Google Cloud har många | Gratis eller betald |
| **Lokal AI** (Ollama, LM Studio) | Ja, inga villkor från en molntjänst | Ja, allt stannar i datorn | Nej | Behövs inte | – | Gratis, men kräver en kraftfull dator och ger svagare svar |

**Vår rekommendation**
- **Skolor:** Mistral via EU-adressen, eller Anthropic. Båda har avtal om personuppgifter och certifieringar som går att granska. Gör en konsekvensbedömning (DPIA) innan ni börjar.
- **Hem som vill ha minst krångel:** Anthropic eller Mistral med betalning per användning och ett utgiftstak (till exempel 10 € per månad).
- **Hem som inte vill att något lämnar huset:** lokal AI, om datorn klarar det.
- **Google Gemini API** rekommenderas inte, eftersom villkoren inte tillåter appar som barn använder.

## Varför valet spelar roll

### Dataskyddsförordningen (GDPR)
Det barnet skriver, fotograferar eller laddar upp skickas till AI-tjänsten. Då är AI-tjänsten **personuppgiftsbiträde** åt hemmet eller skolan. Det kräver:
- **ett biträdesavtal (DPA)** med leverantören (artikel 28);
- **laglig överföring** om datan lämnar EU/EES (kapitel V). Det ordnas med EU:s standardavtalsklausuler eller EU–US Data Privacy Framework;
- att leverantören **inte använder datan för egna syften**, till exempel för att träna modeller, utan att ni vet om det;
- **särskild hänsyn till barn** (skäl 38 och artikel 8).

**Hemma** gäller oftast GDPR:s undantag för rent privat verksamhet (artikel 2.2 c). Leverantörens villkor gäller ändå.
**Skolor** är alltid personuppgiftsansvariga och behöver avtal, en DPIA och information till vårdnadshavare.

### EU:s AI-förordning
- **Transparens (artikel 50):** användaren ska förstå att den pratar med en AI. Läxspelet märker alla AI-svar.
- **Högrisk (bilaga III punkt 3):** AI som bedömer studieresultat eller styr lärandet inom utbildning kan räknas som högrisk från den 2 december 2027. Det gäller främst när en skola använder sådana funktioner. Se [efterlevnad.md](efterlevnad.md).
- Leverantörerna av de stora modellerna har egna skyldigheter som modelleverantörer. Det tar inte bort skolans ansvar som användare.

### ISO/IEC 27001, ISO/IEC 42001 och liknande
Standarderna certifierar en **organisation**, inte ett val av AI. Men de kräver att leverantörer granskas och följs upp (ISO 27001 bilaga A 5.19–5.22). Det blir mycket enklare om AI-tjänsten själv har:
- ISO 27001 (informationssäkerhet);
- ISO 27701 (integritet);
- ISO 42001 (styrning av AI);
- SOC 2-rapporter;
- ett tillgängligt trust center där ni kan begära rapporterna.

## Leverantör för leverantör

### Mistral AI
- **Barn:** minderåriga får ha konto med förälders tillstånd. Det är förbjudet att skicka uppgifter om barn under 13 år, eller under åldern för digitalt samtycke (13 år i Sverige), utan förälders samtycke. När föräldern kopplar in tjänsten är det föräldern som ger samtycket.
- **Data:** lagras i EU som standard. Adressen `api.eu.mistral.ai` garanterar att svaren räknas fram i EU/EFTA och kostar 10 % mer. Konto- och faktureringsuppgifter kan ligga utanför EU.
- **Träning:** uppgifterna går isär. Biträdesavtalet tillåter träning om kunden inte har valt bort det. Gå in under **Privacy** och stäng av *Anonymous improvement data*.
- **Certifieringar:** ISO 27001/27701 och SOC 2 Type II enligt Mistrals hjälpcenter. Rapporterna finns på trust.mistral.ai.
- **Gratisnivån:** räcker inte. Vid vårt test i november 2026 gav den 0 frågor per minut för `mistral-small` och 2 per minut för `ministral-14b`, och läsning av PDF-filer stoppades. Slå på *pay-as-you-go*, som har ett ingående belopp per månad, och sätt ett utgiftstak.
- **Oklart:** en tredjepartskälla påstår att API:t sedan augusti 2026 bara är för företag. Det har vi inte kunnat bekräfta i Mistrals egna villkor.

### Anthropic (Claude)
- **Barn:** Claude.ai, deras egen app, är bara för vuxna. Appar byggda på API:t får användas av barn om de har skyddsåtgärder:
  - åldersanpassning och moderering av innehållet;
  - tydlig information om att det är en AI;
  - att appen följer lagar om barns integritet.
  Anthropic kan granska att det följs. Läxspelet märker AI-svaren, och föräldern styr vad barnet gör.
- **Data:** behandlas i USA. Överföringen sker med standardavtalsklausuler, och Anthropic omfattas av Data Privacy Framework. Behandling i EU finns via Amazon Bedrock (Frankfurt), och då gäller Amazons avtal.
- **Träning:** API-data används inte för träning.
- **Certifieringar:** ISO 27001, ISO 42001, ISO 27017/27018 och SOC 2 Type I och II.

### OpenAI
- **Barn:** inom EES måste användare under 18 ha förälders tillstånd. Den som bygger appar för barn ska ha extra skydd. OpenAI avråder från att behandla barns personuppgifter utan *zero data retention*, alltså att ingenting sparas.
- **Data:** USA som standard. Data i EU erbjuds godkända organisationer, per projekt och mot ett påslag.
- **Träning:** API-data används inte för träning som standard.

### Google Gemini API (AI Studio)
- **Barn:** användaren måste vara 18 år. API:t får inte användas i appar som riktar sig till eller sannolikt används av personer under 18. Det gäller oavsett vems nyckel som används.
- **EES:** appar som görs tillgängliga i EES, Schweiz och Storbritannien får bara använda den betalda nivån.
- **Träning:** gratisnivåns data får användas för att förbättra Googles produkter.
- **Slutsats:** passar inte Läxspelet. Googles produkter för skolor, som Workspace for Education, har egna avtal och omfattas inte av detta.

### Lokal AI (Ollama, LM Studio)
- Ingenting lämnar datorn. Därför finns ingen överföring och inget biträdesavtal.
- Kräver en dator med mycket minne eller ett bra grafikkort. Svaren blir svagare, och bildläsning fungerar bara med vissa modeller.
- Ni ansvarar själva för att välja en modell vars licens tillåter användningen.

### Övriga i listan (OpenRouter, Groq, xAI, Together, egen adress)
Dessa har vi inte gått igenom. **OpenRouter** är en mellanhand som skickar vidare till andra leverantörer, så ni behöver granska båda leden. Läs villkoren om barn, datans placering och träning innan ni väljer någon av dem.

## Checklista innan ni väljer
1. Tillåter tjänsten att barn använder appen, och på vilka villkor?
2. Finns ett biträdesavtal (DPA), och gäller det den nivå ni betalar för?
3. Var behandlas datan? Finns EU-region, och kostar den extra?
4. Används datan för träning? Kan ni stänga av det?
5. Hur länge sparas datan? Finns *zero data retention*?
6. Vilka certifieringar finns, och kan ni få rapporterna?
7. Räcker gränserna för antal frågor per minut? Gratisnivåer gör det sällan.
8. Har ni satt ett utgiftstak?
9. Skolor: är DPIA, registerförteckning och information till vårdnadshavare klara?

## Källor
Kontrollerade 24 november 2026.
- Mistral: [Villkor](https://mistral.ai/en/terms), [Certifieringar (hjälpcenter)](https://help.mistral.ai/en/articles/323772-do-you-have-soc2-or-iso27001-certification), [Regelefterlevnad](https://help.mistral.ai/en/collections/789670-regulatory-compliance-and-certification), [Datalagring och EU-adress (tredje part)](https://www.developersdigest.tech/models/data-retention/mistral), [GDPR-genomgång (tredje part)](https://sovergate.com/blog/mistral-ai-gdpr-compliance)
- Anthropic: [Riktlinjer för organisationer som har minderåriga användare](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors), [AI-policy](https://www.anthropic.com/policy), [Biträdesavtal](https://www.anthropic.com/legal/data-processing-addendum), [Certifieringar](https://privacy.claude.com/en/articles/10015870-what-certifications-has-anthropic-obtained), [Regional efterlevnad](https://claude.com/regional-compliance)
- OpenAI: [Användarvillkor](https://openai.com/policies/usage-policies/), [Råd för användare under 18](https://developers.openai.com/api/docs/guides/safety-checks/under-18-api-guidance), [EU-integritetspolicy](https://openai.com/policies/eu-privacy-policy/), [Villkor](https://openai.com/policies/row-terms-of-use/)
- Google: [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)
- Regelverk: se [efterlevnad.md](efterlevnad.md)
