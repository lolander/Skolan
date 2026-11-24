# Tillgänglighetsredogörelse för Lärarrummet

*Gäller Lärarrummet 0.14.0. Senast uppdaterad: 24 november 2026.*

Lärarrummet ska kunna användas av så många lärare som möjligt, även den som använder skärmläsare, tangentbord eller förstoring. Här beskrivs hur appen uppfyller WCAG 2.1 nivå AA, som är kravnivån i lagen om tillgänglighet till digital offentlig service (DOS-lagen).

Lärarrummet tillhandahålls inte av en offentlig aktör, men skolor som använder appen har krav på sig att erbjuda tillgängliga digitala tjänster. Redogörelsen ska göra det lättare för skolan att bedöma appen.

## Hur tillgänglig är appen?

**Delvis förenlig med WCAG 2.1 AA.** Alla automatiska kontroller går igenom, men manuella tester med skärmläsare återstår (se nedan).

## Så har vi granskat

- **Automatisk granskning** med axe-core 4.10 (samma motor som i bland annat Lighthouse och Accessibility Insights) mot WCAG 2.0 och 2.1, nivå A och AA.
- Alla 16 vyer i lärarens app (introduktionen, översikt, statistik, studieteknik, veckobrev, prov, material, grupper, klasslag, rapporter, föräldrar, historik, skolan, behörighet, reglerna och inställningarna) och elevsidan, i både **ljust och mörkt läge**.
- **Resultat: 0 fel.** Granskningen körs på [webbdemon](https://lolander.github.io/Skolan/demo/), som är byggd från samma kod som appen.

Rättat i version 0.14.0:
- Alla formulärfält har nu en kopplad etikett, så att skärmläsare läser upp vad fältet gäller.
- Rullistor, kryssrutor och radioknappar har namn.
- Kontrasten är höjd för grå hjälptext, länkar, knappar och felmeddelanden, i både ljust och mörkt läge (minst 4,5:1).

## Kända brister

- **Inte testat med skärmläsare** (NVDA, JAWS, Skärmläsaren i Windows) eller enbart tangentbord i alla flöden. Automatiska verktyg hittar ungefär hälften av alla tillgänglighetsproblem.
- **Emojier används som ikoner** i rubriker och knappar. De läses upp av skärmläsare, vilket kan bli pratigt men inte hindrar användningen.
- **QR-koden** på översikten har ingen textmotsvarighet i bilden. Adressen står alltid i text bredvid.
- **Material som läraren själv laddar upp** (PDF och foton) omfattas inte. Det är upphovspersonen som ansvarar för att det är tillgängligt.

## Rapportera brister

Upptäcker du något som inte fungerar för dig? Skriv på https://github.com/lolander/Skolan/issues och berätta vilken vy det gäller och vilket hjälpmedel du använder. Svar brukar komma inom några dagar.

Skolor som omfattas av DOS-lagen kan anmäla brister i sina egna digitala tjänster till Myndigheten för digital förvaltning (Digg).
