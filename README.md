# 🎒 Skolan

> ⚠️ **Förhandsversion.** Inställningsguiden är ny och inte färdigtestad. Rapportera gärna fel under Issues.

**En läxapp för barn, inbyggd i Home Assistant.** Barnen övar glosor, gör förhör, läser högt och samlar meriter. Föräldrarna följer allt och godkänner det som görs utanför appen. Allt sparas lokalt hemma hos dig.

*A homework app for kids, built into Home Assistant. The app is in Swedish.*

## Det här kan Skolan

- ✏️ **Glosor och förhör:** öva, Glosrekord (60 sekunder), förhör som föräldrar skickar till barnets telefon, uppläsning av orden.
- 📸 **AI läser läxan:** fota glosor, veckobrev eller en lärobok, så blir det övningar och en e-bok (kräver en AI-tjänst i Home Assistant).
- 🗣️ **Högläsning:** barnet spelar in sig själv, föräldern kan lyssna live och godkänna.
- ⭐ **Meriter och tävling:** svit, dagens utmaning, medaljer, veckotävling mellan syskon där alla tävlar mot sig själva.
- 🐾 **Husdjur:** 50 ritade husdjur med humör, butik med hattar, bakgrunder, effekter, kompisar och rum, högtidspaket, läxpass varje månad och veckans boss.
- 🔔 **Notiser:** påminnelser, godkänn eller neka direkt i notisen, husdjuret i notiserna.
- 📱 **Widget:** husdjuret på iPhones hemskärm via appen Scriptable.

## Installation

1. HACS → ⋮ → **Anpassade arkiv** → lägg till `https://github.com/lolander/Skolan` som **Integration**.
2. Installera **Skolan** och starta om Home Assistant.
3. **Inställningar → Enheter och tjänster → Lägg till integration → Skolan.**
4. Följ guiden: välj barnens användare och telefoner, föräldrarna och (valfritt) en AI-tjänst.

Varje barn behöver en egen användare i Home Assistant (inte administratör). **Skolan** dyker upp i sidomenyn.

## Integritet

All data (läxor, inspelningar, meriter) sparas i `/config/skolan/` hos dig. Barn ser bara sin egen mapp. Bilder skickas bara till den AI-tjänst du själv väljer.

## Licens

MIT
