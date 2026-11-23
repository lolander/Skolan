# Integritetspolicy för Läxspelet

*Senast uppdaterad: 23 november 2026*

Läxspelet är en app för familjer där barn pluggar läxor, glosor och prov som ett spel. Den här policyn gäller Windows-appen (från Microsoft Store eller GitHub), integrationen för Home Assistant och lärarappen **Läxspelet Lärare**.

## Var data finns
- **All data sparas lokalt på familjens egen dator** (eller i familjens Home Assistant): barnens namn, läxor, glosor, foton av böcker och texter, resultat, husdjur och inställningar.
- Läxspelet har **ingen egen server** och **samlar inte in** någon data till utvecklaren. Det finns ingen reklam, ingen spårning och ingen analys.

## När data lämnar datorn
Bara i dessa fall, och bara för att funktionen ska fungera:
- **AI-tjänst som familjen själv väljer**, t.ex. Mistral (europeiskt företag, rekommenderas), Anthropic eller en lokal AI (läs tjänstens villkor: flera tjänster, t.ex. Google Gemini, kräver 18 år eller betald nivå för appar som barn använder, se [regelverken](efterlevnad.md#villkor-hos-ai-leverantörerna-avtal-inte-lag)) (t.ex. Google Gemini, OpenAI, Anthropic, Mistral eller en lokal AI). Texter och foton som barnet skickar till AI-funktionerna (t.ex. foto av glosor eller en skrivuppgift, och glosorna när de sparas för en stavningskoll) skickas till den tjänsten med familjens egen nyckel. Tjänstens egna villkor gäller. Vissa gratisnivåer kan använda data för att förbättra tjänsten, och det står i appen när familjen väljer tjänst. Med lokal AI lämnar inget datorn.
- **Fjärråtkomst** (frivillig): en krypterad Cloudflare-tunnel gör appen nåbar för familjens mobiler utanför hemmet. Trafiken passerar då Cloudflare, som tekniskt kan läsa den. Med Nabu Casa (Home Assistant Cloud) är den krypterad hela vägen.
- **Notiser** (frivilliga): skickas via webbläsarens push-tjänst (Apple, Google, Microsoft eller Mozilla) till familjens egna enheter.
- **Lärarkoppling** (frivillig, föräldern slår på varje del): det föräldern godkänner delas med barnets lärare. Se nästa avsnitt.
- **Uppdateringar**: appen frågar GitHub om det finns en ny version (inte i Store-versionen, där sköter Microsoft Store det).

## Lärarkopplingen
- **Allt är av tills föräldern slår på det.** En funktion fungerar bara när både föräldern (i Läxspelet) och läraren (i Läxspelet Lärare) har slagit på den. Föräldern kan välja olika för olika lärare, och när som helst stänga av eller koppla bort en lärare. Den gamla klasslänken slutar då att fungera.
- **Föräldern godkänner skolan och rektorn.** När en lärare från en skola kopplar sig visar Läxspelet skolans och rektorns namn, och föräldern godkänner eller nekar. Byter skolan rektor frågar Läxspelet igen. Innan föräldern har godkänt får lärarna bara det som är nivå 0 (se nedan).
- **Rektorn utser mentorn, och mentorn godkänner ämneslärarna.** Läxspelet kontrollerar själv rektorns digitalt signerade intyg (lärarens behörighet och vilka klasser hen är mentor för) och mentorns signerade godkännande av en ämneslärare (vilka ämnen, och hela klassen eller bara vissa elever). En lärare kan inte ge sig själv en roll. En lärare utan roll får bara det som är nivå 0. Intyg och godkännanden gäller i högst 45 dagar och förnyas automatiskt.
- **Varje synk är signerad av lärarens app.** Klasslänken räcker inte för att utge sig för att vara en lärare som redan är kopplad. Kopplar föräldern bort en lärare spärras också lärarappens nyckel.
- **Föräldern godkänner allt som kommer från läraren** (veckobrev, material, provresultat, riktlinjer) innan det läggs in.
- **Lärarens behörighet styr vad som skickas.** Skolans rektor bestämmer i lärarappen vilken nivå varje lärare har, och föräldern ser lärarens nivå i Läxspelet:
  - **Nivå 0** (standard): läraren får inga uppgifter om barnet. Läxspelet skickar inte barnets namn, elev-id eller lista över lärare. Läraren kan bara få hela klassens summor (se nedan).
  - **Nivå 1**: barnets namn, grupper och, om föräldern delar det, barnets schema.
  - **Nivå 2**: det föräldern väljer att dela om barnet, till exempel veckorapporter, statistik, studieteknik, lappar och underlag till utvecklingssamtal. Allt detta är av tills föräldern slår på det.
- **Klassens insikt** (frivillig): Läxspelet skickar bara summor för lärarens ämne, till exempel vilka glosor barnet har missat och hur många dagar barnet har pluggat inför ett prov. Inget namn, inget elev-id och inga datum skickas, bara en ny slumpad kod varje vecka. Läraren ser inget förrän minst 5 familjer är med, och ett ord visas bara om minst 2 familjer har missat det.
- Det som skickas till läraren går direkt till lärarens dator (HTTPS via klasslänken), inte via någon server hos utvecklaren. Med Cloudflare-tunneln passerar trafiken Cloudflare (se ovan).

## Läxspelet Lärare (för lärare och skolor)
- **Data finns bara på lärarens dator**, krypterad med lärarens Windows-konto (`%APPDATA%\SkolanLarare`). Lärarappen har ingen server, använder ingen AI och skickar ingenting till utvecklaren.
- **Utan beslut från en rektor sparas inga personuppgifter om elever** (nivå 0). Familjerna visas då som "Familj 1, 2, 3 …".
- **Rektorn i appen** bestämmer lärarnas nivå. Besluten signeras digitalt, så en lärare kan inte höja sin egen nivå, och de sparas i en beslutslogg. Sänks en nivå raderar lärarappen genast de kopior av elevuppgifter som inte längre är tillåtna.
- **Skolans IT kan låsa en högsta nivå** på varje dator med grupprinciper eller Intune, oavsett rektorns beslut.
- **Synken mellan lärare på samma skola** är krypterad (AES-256-GCM) och signerad. Elevuppgifter går bara till elevens mentor, och det föräldern har delat med en lärare skickas aldrig vidare till kollegor.
- **Lärarna informeras i appen.** Innan appen kan användas måste läraren läsa och kvittera "📘 Så gör du rätt": appen är ett frivilligt komplement, inga uppgifter om enskilda elever i veckobrev eller meddelanden, det föräldrar delar används inte för betyg, och bara det rektorn har beslutat. Påminnelser visas också där det är lätt att göra fel.
- **Ansvar:** när en skola använder lärarappen är skolans huvudman (kommunen eller friskolan) personuppgiftsansvarig för skolans behandling. Utvecklaren behandlar inga uppgifter och är inte personuppgiftsbiträde.
- Mer för skolor, IT och dataskyddsombud: [Läxspelet och regelverken i Sverige](efterlevnad.md) och [Information till skolor](larare-skolor.md) (nivåer, kryptering, nätverk, gallring, skollagen och mallar).

## Ett komplement, inte en ersättning
Läxspelet ska ses som ett komplement. Det ersätter inte föräldern i läxarbetet och inte skolan. Innan en förälder kan använda föräldrasidorna visar appen **📘 Till dig som förälder**, som föräldern läser och kvitterar:
- Det viktigaste är fortfarande att föräldern finns där: frågar hur det går, sitter med, förhör och pratar om läxan.
- AI:n kan ha fel. Det viktiga, särskilt inför prov, behöver kontrolleras.
- Stjärnor och husdjur är ett medel för att göra pluggandet roligare, inte målet.
- Skolan ansvarar för undervisningen. Appen ersätter inte kontakten med läraren, skolans lärplattform eller utvecklingssamtalet.
- Att må bra går före. Det är okej att hoppa över en dag.

## Barn
Appen används av barn under en förälders uppsikt. Föräldern installerar appen, lägger till barnen och bestämmer vilka funktioner som är på. Föräldern kan när som helst se, ändra eller ta bort barnens data i appen, eller avinstallera appen och radera mappen med data.

## Radera data
- **Familjer:** ta bort en person under ⚙️ Inställningar, eller avinstallera appen och radera mappen `%APPDATA%\Skolan` (Store-versionen raderar sina data vid avinstallation). Koppla bort läraren under Föräldrar → Skolan.
- **Lärare:** 🔐 Behörighet → 🗑️ Radera klassens data, till exempel när läsåret är slut. Avinstallation tar inte bort datan. Radera i så fall också mappen `%APPDATA%\SkolanLarare`.

## Kontakt
Frågor: skapa ett ärende på https://github.com/lolander/Skolan/issues
