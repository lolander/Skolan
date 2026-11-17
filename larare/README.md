# Skolan Lärare (Windows)

Lärarens app för klassen. Den körs på lärarens dator och syns som en webbsida (http://localhost:8770).

- **📬 Veckobrev:** läraren skriver veckans läxor, ord och glosor. När eleven synkar hamnar brevet i föräldrarnas inkorg i Skolan, och föräldern godkänner innan något läggs in.
- **🐲 Klasslag:** klassen bekämpar en gemensam boss. Läraren ser bara klassens summa, aldrig enskilda elevers poäng. Läraren kan lägga till poäng för det klassen gör i klassrummet, så att alla kan vara med.
- **👥 Grupper:** läraren delar klassen i tillfälliga grupper (slumpvis eller själv) och ger en gruppuppgift. Eleverna ser sin grupp och kan bocka av uppgiften.
- **📊 Rapporter:** om föräldern vill får läraren en kort rapport när eleven synkar (dagar övat, förhör, prov), eller via e-post.
- **📈 Statistik:** om föräldern vill ser läraren hur eleven pluggar: dagar per vecka, förhör, prov och ämnen. Aldrig stjärnor, husdjur eller jämförelser.
- **📝 Prov och 📎 studiematerial:** läraren lägger in provresultat per elev och skickar studiematerial som PDF eller foto. Ett veckobrev kan också bifogas som PDF/foto, och familjens Läxspelet läser det med AI. Allt hamnar i förälderns inkorg och föräldern godkänner.
- **📜 Historik:** allt sparas (grupper, uppgifter, rapporter, veckobrev, anteckningar) och kan laddas ner som CSV/Excel.

**Föräldern och läraren bestämmer tillsammans:** en funktion är bara på när både läraren (i lärarappen) och föräldern (i Skolan) har slagit på den.

**Synka på lektionen:** eleverna är på samma wifi som lärarens dator. I Skolan trycker de *🤝 Plugga ihop → 🏫 Anslut till läraren* och skriver adressen som syns i lärarappen. Lärarappen synkar sedan direkt med elevens Skolan hemma (kräver att familjens Skolan nås utifrån, t.ex. via Nabu Casa). Läraren kan också trycka *🔄 Synka alla*.

Data sparas i `%APPDATA%\SkolanLarare\klass.json`.
