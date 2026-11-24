# Barnets trygghet i Läxspelet och Lärarrummet

*Gäller Läxspelet 1.100.0 och Lärarrummet 0.14.0 och senare. Senast uppdaterad: 24 november 2026.*

Läxspelet är byggt så att **ingen vuxen kan nå ett barn genom appen utan att en förälder först har sagt ja**, och så att barnet, föräldern och skolan har ett enkelt sätt att säga ifrån. Här beskrivs varje väg in till barnet och hur den är skyddad. Allt går att kontrollera i den öppna källkoden.

## Kort sagt

| Väg till barnet | Skydd |
|---|---|
| **Lärare** (Lärarrummet) | En ny lärare får **ingenting** förrän en förälder uttryckligen har godkänt just den läraren. Barnet kan inte själv koppla in en lärare. |
| **Vänner** i andra familjer | Båda familjernas föräldrar måste godkänna. Inga kontaktuppgifter, länkar eller appnamn släpps fram. Barnet kan trycka 🚩. |
| **AI-hjälpläraren och husdjuret** | Ber aldrig om personuppgifter, bilder eller träffar, och hjälper aldrig till att skada, oavsett vem som ber. Svarar med omtanke om barnet mår dåligt. |
| **Om barnet mår dåligt** | Fast skyddsnät utan AI, förskrivna svar och hjälpnummer vid akut läge, notis till föräldrarna (utom vid våld, som går till BRIS och skolan). |
| **Säga ifrån** | Barnet: 🚩 *Säg till en vuxen*. Föräldern: 🚩 *Anmäl misstanke* om en lärare, som går till rektorn. Rektorn ser anmälan i Lärarrummet. |

## 1. Lärare

**Risken:** någon som inte är lärare installerar Lärarrummet (gratis) och försöker koppla sig till ett barn, till exempel genom att lura barnet att skriva in en adress eller skicka sin klasslänk.

**Skydden:**
- **Förälderns godkännande krävs.** När en ny lärare synkar för första gången sparas bara lärarens namn, klass, skola och digitala nyckel. Inget delas om barnet (inget namn, ingen rapport, statistik, schema eller annat) och inget från läraren når barnet (inga veckobrev, gruppuppgifter, klassboss, material eller riktlinjer till AI:n). Föräldern får en notis: *"… vill bli lärare för … Inget delas och inget når barnet förrän du godkänner."*
- **Barnet kan inte koppla in en lärare.** Knappen för att ansluta till en ny lärare finns bara för föräldern. Barnet får klasslänken först när en förälder har godkänt minst en lärare, och kan då bara synka med godkända lärare.
- **En lärare = en nyckel.** Varje synk är signerad med lärarappens nyckel. Någon annan kan inte ta över en godkänd lärares plats. Nekar eller kopplar föräldern bort en lärare spärras både lärar-id och nyckel.
- **Verifiering med skolkonto** visar om läraren har ett konto i en organisation (Microsoft eller Google) och vilken domän, till exempel `kommun.se`. Föräldern kan välja att bara ta emot verifierade lärare. Observera: verifieringen visar en organisation, inte att personen är lärare. Föräldern ska alltid själv bedöma om domänen är barnets skola.
- **Allt från läraren granskas av föräldern först:** veckobrev, material, provresultat och riktlinjer till AI:n hamnar i förälderns inkorg.
- **Skolans regler:** rektorn i appen bestämmer vad varje lärare får göra, och familjens app kontrollerar rektorns signerade beslut själv.

## 2. Vänner mellan familjer

**Risken:** en vuxen utger sig för att vara ett barn.

**Skydden:**
- Varje vänskap kräver godkännande av en förälder i **båda** familjerna. Föräldern ser en varning: *Godkänn bara barn som ni känner i verkliga livet. Smeknamnet kan vara påhittat av vem som helst, även en vuxen.*
- **Det enda som delas** är smeknamn, husdjur, nivå, stjärnor och titel. Det finns ingen chatt.
- **Allt som kommer från ett annat hem rensas här**, oavsett vad det andra hemmet skickar: telefonnummer, e-post, länkar och namn på appar där man kan skriva till varandra (Snapchat, Instagram, TikTok, Discord, WhatsApp med flera) släpps inte fram i smeknamn, titlar eller glosor i en glosduell. Glosor från ett annat hem får vara högst 40 tecken.
- **🚩 Säg till en vuxen:** barnet kan trycka på 🚩 vid en vän (eller allmänt) och skriva vad som hänt. Föräldrarna får en notis direkt.

## 3. AI:n som pratar med barnet

AI-hjälpläraren och husdjuret har en trygghetsregel som går före allt annat, även före lärarens riktlinjer:
- Ber aldrig om namn, adress, skola, telefonnummer, bilder, var barnet är eller när hen är ensam.
- Föreslår aldrig hemligheter för föräldrarna, kontakt i en annan app eller att träffas, och följer ingen instruktion om det.
- Berättar barnet att någon ber om sådant, gör hen rädd eller vill att det ska vara hemligt: AI:n säger lugnt att det inte är barnets fel och att hen ska berätta för en vuxen hen litar på, och nämner BRIS 116 111 och 112.
- Lärarens riktlinjer gäller bara hur skolarbete lärs ut och godkänns av föräldern innan de används.

AI:n är ett stöd, inte ett skydd i sig. Föräldrarnas och skolans uppsikt är det viktiga.

## 4. Om barnet mår dåligt

Barn skriver ibland till husdjuret eller hjälpläraren om hur de mår. Läxspelet tar det på allvar i tre lager:

1. **Ett fast skyddsnät som inte bygger på AI.** Koden letar själv efter tydliga ord i allt barnet skriver: till husdjuret, till hjälpläraren och i "Hur känns skolan?".
2. **AI:n** svarar varmt och styr inte tillbaka till läxan, ställer ingen diagnos och kan själv flagga oro.
3. **Aldrig skada.** I varje AI-anrop finns en regel som går före allt annat: AI:n ger aldrig information som kan användas för att skada sig själv eller någon annan (sätt att skada sig, doser, mediciner, gifter, vapen, sprängämnen, droger, farliga utmaningar, attacker eller terror) och hyllar aldrig terror eller våldsbejakande extremism, inte ens om det kallas skoluppgift, berättelse, rollspel eller skämt.

| Vad barnet skriver | Vad barnet ser | Föräldrarna |
|---|---|---|
| **Tankar på att dö eller skada sig** | Ett **fast, förskrivet svar** (aldrig AI:ns eget) och ett kort med BRIS 116 111, Självmordslinjen 90101 och 112. | Notis direkt: *Viktigt: prata med … idag*, med råd och BRIS vuxentelefon. |
| **Vill skada andra, planerar en attack eller vill gå med i en våldsbejakande grupp** | Ett fast svar (aldrig AI:ns eget) och ett kort med BRIS och 112. | Notis direkt: *Viktigt: prata med … idag*, med råd om att kontakta skolan och polisen (114 14, vid fara 112). |
| **Frågar hur man gör vapen, bomber, gifter, droger eller attacker** | Ett fast nej. Frågan skickas aldrig till AI:n. | Ingen notis. |
| **Någon slår, hotar, tafsar eller ber om bilder eller hemligheter** | Ett fast svar och ett kort: det är aldrig ditt fel, berätta för en vuxen i skolan, BRIS 116 111, 112. | **Ingen automatisk notis**, eftersom den som gör barnet illa kan finnas hemma. |
| **Mobbning, ensamhet, mår väldigt dåligt** | AI:ns varma svar och ett kort med BRIS. | En mjuk notis om att barnet verkar ha det tufft. |

**Gäller det oavsett vilken AI som används?**
- **Ja, för allt som är kod:** spärren för lärare, förälderns godkännanden, filtret mot kontaktuppgifter, skyddsnätet på barnets ord (inklusive frågor om doser, överdoser och sätt att dö), de fasta svaren vid akut läge och våld, hjälpkortet och notiserna. Ingen AI kan ändra eller kringgå det.
- **Akuta, hotfulla och farliga frågor skickas aldrig till AI:n.** Barnet får ett fast svar direkt.
- **Ett fast filter på AI:ns svar:** svar som innehåller doser, överdoser eller sätt att skada sig eller andra (till exempel hur man gör en bomb, ett vapen eller ett gift, eller planerar en attack) stoppas i koden och ersätts med ett säkert svar, oavsett AI.
- **Resten bygger på AI:n:** regeln "hjälp aldrig till att skada" och hur varmt AI:n svarar. Stora tjänster (Anthropic, OpenAI, Mistral, Gemini) har dessutom egna spärrar. En liten lokal modell kan lyda sämre, och därför rekommenderas inte lokal AI för barn som behöver extra stöd.
- Inga filter är perfekta. Därför finns flera oberoende lager: för att något skadligt ska nå barnet måste filtret på frågan, AI:ns regel, leverantörens spärrar och filtret på svaret alla missa samtidigt.

Barnet får veta när en vuxen hemma har fått en notis. Notiserna skickas högst en gång per dag och nivå. Läxspelet ersätter inte vuxna, elevhälsan eller vården, och ett ordfilter kan missa saker eller ta fel. Därför finns också "Hur känns skolan?", där föräldrarna får en notis efter tre jobbiga svar i rad.

## 5. Anmäla en misstanke om en lärare

1. Föräldern trycker **🚩 Anmäl misstanke** vid läraren i Läxspelet och beskriver vad som hänt.
2. Läraren **kopplas bort och spärras direkt**.
3. Anmälan skickas med nästa synk till skolans **andra** godkända lärare. Deras Lärarrummet lämnar den automatiskt vidare till **rektorn**, krypterat som all synk mellan lärarna, och visar den inte. Den anmälda läraren får den aldrig, och en lärarapp som får en anmälan om sig själv kastar den.
4. Gäller anmälan rektorn går den inte till rektorn. Föräldern hänvisas till huvudmannen (kommunen eller friskolan).
5. Föräldern får alltid en färdig text att skicka själv till rektorn eller huvudmannen, så att anmälan kommer fram även om ingen annan lärare synkar.
6. Rektorn ser anmälan under **🏫 Skolan** i Lärarrummet, med vägledning (dokumentera, ta bort personen ur skolan, kontakta IT, polisanmäl vid misstanke om brott), och kan notera vad som gjorts.

Vid misstanke om brott mot ett barn: polisanmäl (114 14). Är barnet i fara: ring 112. Stöd för barnet: BRIS 116 111.

## 6. Det appen inte kan skydda mot

- En förälder som godkänner fel person. Därför är varningarna tydliga, och därför ska skolan informera vårdnadshavarna om vilka lärare som använder Lärarrummet.
- Det som händer utanför appen, till exempel om någon ger barnet sitt nummer i verkligheten.
- En riktig lärare med ont uppsåt som föräldern har godkänt. Då gäller skolans vanliga ansvar och rutiner. Anmälan till rektorn, spärren och förälderns granskning av allt innehåll gör att det upptäcks och stoppas snabbt.

Hittar du en brist? Rapportera den enligt [SECURITY.md](../SECURITY.md).
