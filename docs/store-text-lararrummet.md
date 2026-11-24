# Texter till Microsoft Store: Lärarrummet (klistra in i Partner Center)

**Namn:** Lärarrummet

**Kort beskrivning:**
Lärarens följeslagare till Läxspelet. Skicka veckobrev, glosor, provdatum och studiematerial till klassens familjer, samordna prov med kollegorna och följ klassens plugg. Allt sparas på din dator.

**Beskrivning:**
Lärarrummet kopplar ihop läraren med familjer som använder Läxspelet. Appen körs på lärarens dator och familjerna synkar över skolans nätverk. Det finns ingen molntjänst och inget konto att skapa.

📬 Veckobrev: läsläxa, stavningsord och glosor hamnar direkt i elevernas Läxspel. Föräldern godkänner innan något läggs in.
📎 Studiematerial och prov: skicka sammanfattningar, provdatum och resultat som PDF eller foto.
🏫 Skolan: lärarna på skolan delar en gemensam provkalender och skickar meddelanden till varandra, krypterat på skolans nätverk.
🐙 Klasslag: klassen besegrar en gemensam veckoboss genom att plugga. Du ser bara klassens summa.
🔎 Klassens insikt: vilka ord som är svåra och hur klassen pluggar inför prov, bara som summor från minst 5 familjer.
🔐 Behörigheter: rektor bestämmer vad varje lärare får se, i tre nivåer. Alla beslut loggas, och skolans IT kan låsa inställningar med grupprinciper.
✔ Verifiering med skolkonto: läraren kan visa familjerna att kontot tillhör skolan, via Microsoft eller Google.

Föräldern bestämmer alltid själv vad familjen delar med läraren. Ingen reklam, ingen spårning och ingen AI i Lärarrummet.

**Funktioner (Product features, en per rad):**
- Veckobrev med läsläxa, stavningsord och glosor
- Studiematerial, provdatum och provresultat till familjerna
- Gemensam provkalender och meddelanden mellan lärare
- Klasslag med veckoboss
- Klassens insikt som anonyma summor
- Behörigheter som rektor bestämmer, med beslutslogg
- Grupprinciper (ADMX) för skolans IT
- Allt lagras lokalt, inget moln

**Nyckelord:** lärare, skola, veckobrev, glosor, läxor, prov, klass, mentor, Läxspelet

**Kategori:** Utbildning (Education)

**Integritetspolicy (URL):** https://github.com/lolander/Skolan/blob/main/docs/integritet.md

**Webbplats:** https://github.com/lolander/Skolan

**Supportkontakt:** https://github.com/lolander/Skolan/issues

**Pris:** Gratis · **Marknader:** Sverige (eller alla)

**Åldersklassning (IARC):** inget våld, inga köp, ingen kontakt med främlingar (meddelanden bara mellan lärare på samma skola), ingen platsdelning. Det brukar ge 3+ / PEGI 3.

**Förklaring till runFullTrust (Submission options → Restricted capabilities):**
Lärarrummet är en skrivbordsapp (Python) som kör en lokal webbserver på lärarens dator. Läraren använder appen i webbläsaren (localhost), familjernas Läxspel synkar mot den över skolans lokala nätverk och kollegor synkar krypterat med varandra. Appen visar också en ikon vid klockan. Därför behöver den köras som ett fullt betrott skrivbordsprogram.

**Skärmbilder:** `docs/store-bilder-lararrummet/` (1366×768, från demon med påhittad klass).
