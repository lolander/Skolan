# Verifiering med skolkonto

*Gäller Lärarrummet 0.13.0 och Läxspelet 1.99.0 och senare.*

En lärare kan logga in med sitt skolkonto hos Microsoft eller Google i Lärarrummet. Föräldern ser då till exempel
**"✔ kommun.se"** vid läraren: Microsoft eller Google intygar lärarens namn och att organisationen har gett personen ett konto.

## Vad det betyder, och inte betyder
- **Det visar** att skolan, kommunen eller huvudmannen har gett personen ett konto i sin organisation.
- **Det visar inte** lärarlegitimation, behörighet att undervisa i ett ämne eller att personen fortfarande är anställd. Ett konto som skolan har stängt kan inte verifieras igen, och verifieringen går ut efter 100 dagar.
- **Läxspelet kontrollerar inte legitimation eller anställning.** Det ansvaret ligger hos skolan, som anställer lärarna, delar ut skolkonton och bestämmer behörigheter i Lärarrummet. Läxspelet visar bara det som skolan och Microsoft eller Google intygar.
- Privata konton (Outlook.com, Hotmail, Gmail) godtas inte.

## Hur det fungerar
1. Läraren trycker på **⚙️ Inställningar → Verifiera med Microsoft/Google** i Lärarrummet. Skolans vanliga inloggning öppnas i webbläsaren.
2. Lärarrummet ber bara om `openid`, `profile` och `email`. Det ger namn och e-postadress, men ingen åtkomst till e-post, filer eller kalender.
3. Microsoft eller Google lämnar ett signerat intyg (ID-token). Intyget är knutet till lärarappens egen nyckel genom att `nonce` är en hash av nyckeln, så det går inte att använda i en annan lärarapp.
4. Intyget följer med när läraren synkar med familjen. Familjens Läxspelet kontrollerar själv signaturen mot Microsofts eller Googles publika nycklar, att intyget är utfärdat till Lärarrummet, nyckeln, åldern och att det inte är ett privat konto.
5. Ingen server hos Läxspelet är inblandad, och inget skickas någon annanstans.

Föräldern kan välja **"Ta bara emot lärare som har verifierat sig med sitt skolkonto"**. En lärare vars domän skiljer sig från de andra lärarna på samma skola flaggas.

## För skolans IT

### Microsoft 365 / Entra ID
Många organisationer låter inte användare godkänna nya appar själva. Då ser läraren ett meddelande om att en administratör måste godkänna appen. Godkänn Lärarrummet en gång för hela organisationen:

- Öppna `https://login.microsoftonline.com/organizations/adminconsent?client_id=<KLIENT-ID>` som global administratör eller administratör för molnprogram. Klient-id står i `custom_components/skolan/skolkonto.py` (`MICROSOFT_KLIENT`).
- Eller använd **Entra-administrationscentret → Företagsprogram → Lärarrummet → Behörigheter → Bevilja administratörsmedgivande**.
- Behörigheter: `openid`, `profile`, `email` (delegerade, bara inloggning).
- Begränsa gärna till lärare: **Företagsprogram → Lärarrummet → Egenskaper → Tilldelning krävs = Ja** och tilldela personalgruppen.

### Google Workspace for Education
- **Administratörskonsolen → Säkerhet → Åtkomst- och datakontroll → API-kontroller → Hantera åtkomst för tredjepartsappar → Konfigurera ny app**. Sök på klient-id (`GOOGLE_KLIENT` i `skolkonto.py`) och välj **Betrodd** för personalens organisationsenhet.
- Behörigheter: `openid`, `email`, `profile`.

## Integritet
Lärarrummet sparar intyget på lärarens dator. Det innehåller namn, e-post, organisationens id eller domän och tidpunkten. Intyget skickas till de familjer som läraren synkar med, och de sparar namn, e-post, domän och datum. Inget annat hämtas från kontot. Läraren kan ta bort verifieringen i ⚙️ Inställningar. Då försvinner den hos familjerna vid nästa synk.

---

## För utvecklaren: registrera apparna (görs en gång)

### Microsoft (Entra, gratis)
1. Gå till **entra.microsoft.com** och logga in med Microsoft-kontot. Om du blir ombedd att skapa en katalog eller ett gratis Azure-konto, gör det.
2. Gå till **Program → Appregistreringar → Ny registrering**.
   - Namn: **Lärarrummet**
   - Kontotyper som stöds: **Konton i valfri organisationskatalog (alla Microsoft Entra ID-klientorganisationer – flera klientorganisationer)**. Välj inte alternativet med personliga konton.
   - Omdirigerings-URI: plattform **Offentlig klient/intern (mobil och skrivbord)**, adress `http://localhost/skolkonto/svar`
3. **Registrera**. Kopiera **Program-ID (klient)**.
4. Under **API-behörigheter**: ta bort `User.Read` och lägg till Microsoft Graph, delegerade: `openid`, `profile`, `email`.
5. Under **Varumärke och egenskaper**: startsida `https://github.com/lolander/Skolan`, sekretesspolicy `https://github.com/lolander/Skolan/blob/main/docs/integritet.md`.

### Google (Google Cloud, gratis)
1. Gå till **console.cloud.google.com** och skapa ett nytt projekt: **Lärarrummet**.
2. Gå till **Google Auth Platform → Kom igång**.
   - Appnamn: **Lärarrummet**
   - Målgrupp: **Extern**
   - Supportadress: din e-post
3. Under **Varumärke**: startsida och sekretesspolicy, samma som för Microsoft.
4. Under **Dataåtkomst**: lägg till `openid`, `.../auth/userinfo.email` och `.../auth/userinfo.profile`. Det är grundläggande behörigheter som inte kräver granskning.
5. Under **Målgrupp**: tryck **Publicera appen** (i produktion).
6. Under **Klienter → Skapa klient**: välj typen **Datorprogram** och namnet Lärarrummet. Kopiera **klient-id** och **klienthemlighet**.

Lägg in värdena i `skolkonto.py`, i båda kopiorna: `MICROSOFT_KLIENT`, `GOOGLE_KLIENT` och `GOOGLE_HEMLIGHET`. Googles hemlighet för skrivbordsappar räknas inte som hemlig.
