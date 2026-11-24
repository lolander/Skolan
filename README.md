# 🎒 Läxspelet

> ⚠️ **Förhandsversion.** Inställningsguiden är ny och inte färdigtestad. Rapportera gärna fel under Issues.

**En läxapp för barn, inbyggd i Home Assistant.** Barnen övar glosor, gör förhör, läser högt och samlar meriter. Föräldrarna följer allt och godkänner det som görs utanför appen. Allt sparas lokalt hemma hos dig.

> 💛 **Ett komplement, inte en ersättning.** Läxspelet hjälper barnet att plugga, men ersätter inte föräldern i läxarbetet och inte skolan. Föräldrar läser och kvitterar [Till dig som förälder](docs/integritet.md#ett-komplement-inte-en-ersättning) innan de börjar.

*A homework app for kids, built into Home Assistant. The app is in Swedish.*

## Det här kan Skolan

- ✏️ **Glosor och förhör:** öva, Glosrekord (60 sekunder), förhör som föräldrar skickar till barnets telefon, uppläsning av orden.
- 📸 **AI läser läxan:** fota glosor, veckobrev eller en lärobok, så blir det övningar och en e-bok (kräver en AI-tjänst i Home Assistant).
- 🗣️ **Högläsning:** barnet spelar in sig själv, föräldern kan lyssna live och godkänna.
- ⭐ **Meriter och tävling:** svit, dagens utmaning, medaljer, veckotävling mellan syskon där alla tävlar mot sig själva.
- 🐾 **Husdjur:** 50 ritade husdjur med humör, butik med hattar, bakgrunder, effekter, kompisar och rum, högtidspaket och läxpass varje månad.
- 🗺️ **Äventyrskarta:** nivåer med monster och världsbossar. Varje merit gör skada, husdjuret kan lära sig attacker.
- 🔔 **Notiser:** påminnelser, godkänn eller neka direkt i notisen, husdjuret i notiserna.
- 📱 **Widget:** husdjuret på iPhones hemskärm via appen Scriptable.

## Installation i Home Assistant

1. HACS → ⋮ → **Anpassade arkiv** → lägg till `https://github.com/lolander/Skolan` som **Integration**.
2. Installera **Skolan** och starta om Home Assistant.
3. **Inställningar → Enheter och tjänster → Lägg till integration → Skolan.**
4. Följ guiden: välj barnens användare och telefoner, föräldrarna och (valfritt) en AI-tjänst.

Varje barn behöver en egen användare i Home Assistant (inte administratör). **Skolan** dyker upp i sidomenyn.

## Utan Home Assistant: Windowsappen

Har ni inte Home Assistant? Ladda ner **[Laxspelet-Setup.exe](https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Setup.exe)** och installera på familjens dator.

**Lärare:** ladda ner **[Laxspelet-Larare-Setup.exe](https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Larare-Setup.exe)** (Lärarrummet för Windows). Den installeras utan administratör och uppdaterar sig själv. Skolor, IT och dataskyddsombud: läs **[Information till skolor](docs/larare-skolor.md)** (behörighetsnivåer, rektorns beslut, kryptering, grupprinciper och mallar).

🧪 **[Prova lärarappen utan att installera](https://lolander.github.io/Skolan/demo/)** · 📄 [Kom igång på nivå 0](docs/larare-niva0.md) · 📝 [Mallar i Word](docs/mallar/) · 🛠️ [IT-paket](https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Larare-IT.zip) · 🔏 [Kodsignering](docs/kodsignering.md) · 🛡️ [Säkerhet](SECURITY.md)

1. Första gången lägger du till familjen (namn och PIN-kod för varje person) och gärna en gratis AI-nyckel från [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Högerklicka på Skolans ikon vid klockan → **Koppla en mobil** och skanna QR-koden med barnens telefoner. Lägg till Skolan på hemskärmen.
3. Vill ni nå Skolan utanför hemmet och få notiser på iPhone: slå på **Fjärråtkomst** under Inställningar (gratis Cloudflare-tunnel).

Datorn behöver vara igång när barnen pluggar. Data sparas i `%APPDATA%\Skolan`. Mer om hur det fungerar: [fristaende/README.md](fristaende/README.md).

## Integritet

All data (läxor, inspelningar, meriter) sparas i `/config/skolan/` hos dig. Barn ser bara sin egen mapp. Bilder skickas bara till den AI-tjänst du själv väljer.

## Licens

MIT
