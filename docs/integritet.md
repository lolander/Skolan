# Integritetspolicy för Läxspelet

*Senast uppdaterad: 18 november 2026*

Läxspelet är en app för familjer där barn pluggar läxor, glosor och prov som ett spel. Den här policyn gäller Windows-appen (från Microsoft Store eller GitHub) och integrationen för Home Assistant.

## Var data finns
- **All data sparas lokalt på familjens egen dator** (eller i familjens Home Assistant): barnens namn, läxor, glosor, foton av böcker och texter, resultat, husdjur och inställningar.
- Läxspelet har **ingen egen server** och **samlar inte in** någon data till utvecklaren. Det finns ingen reklam, ingen spårning och ingen analys.

## När data lämnar datorn
Bara i dessa fall, och bara för att funktionen ska fungera:
- **AI-tjänst som familjen själv väljer** (t.ex. Google Gemini, OpenAI, Anthropic, Mistral eller en lokal AI). Texter och foton som barnet skickar till AI-funktionerna (t.ex. foto av glosor eller en skrivuppgift) skickas till den tjänsten med familjens egen nyckel. Tjänstens egna villkor gäller. Vissa gratisnivåer kan använda data för att förbättra tjänsten; det står i appen vid valet. Med lokal AI lämnar inget datorn.
- **Fjärråtkomst** (frivillig): en krypterad Cloudflare-tunnel gör appen nåbar för familjens mobiler utanför hemmet.
- **Notiser** (frivilliga): skickas via webbläsarens push-tjänst (Apple, Google, Microsoft eller Mozilla) till familjens egna enheter.
- **Lärarkoppling** (frivillig, föräldern slår på varje del): det föräldern godkänner delas med barnets lärare.
- **Uppdateringar**: appen frågar GitHub om det finns en ny version (inte i Store-versionen, där sköter Microsoft Store det).

## Barn
Appen används av barn under en förälders uppsikt. Föräldern installerar appen, lägger till barnen och bestämmer vilka funktioner som är på. Föräldern kan när som helst se, ändra eller ta bort barnens data i appen, eller avinstallera appen och radera mappen med data.

## Radera data
Ta bort en person under ⚙️ Inställningar, eller avinstallera appen och radera mappen `%APPDATA%\Skolan` (Store-versionen raderar sina data vid avinstallation).

## Kontakt
Frågor: skapa ett ärende på https://github.com/lolander/Skolan/issues
