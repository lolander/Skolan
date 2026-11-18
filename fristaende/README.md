# Skolan utan Home Assistant

Windowsappen kör **exakt samma kod** som Home Assistant-integrationen (`custom_components/skolan`).
Skillnaden är ett litet "låtsas-Home Assistant" runt den:

| Home Assistant | Windowsappen |
|---|---|
| Användare och inloggning | Personer med PIN-kod (`skolan_app/konto.py`) |
| Sidopanelen | Egen startsida som laddar samma panel (`skolan_app/webb/`) |
| `ai_task` | Familjens val av AI (`skolan_app/ai.py`): Gemini, Claude, OpenAI, Mistral, OpenRouter, Groq, xAI, DeepSeek, Together, lokalt via Ollama/LM Studio eller egen OpenAI-kompatibel adress |
| Notiser via mobilappen | Webbnotiser (`skolan_app/push.py`) |
| Nabu Casa / fjärråtkomst | Gratis Cloudflare-snabbtunnel (`skolan_app/tunnel.py`) |
| Molnröst för uppläsning | Telefonens/webbläsarens egen röst |
| Resten (`hass`, tidsstyrning, vyer) | `skolan_app/varden.py` + `ha_shim/` |

## Uppdateringar

Appen kollar var 6:e timme om det finns en nyare Skolan-Setup på GitHub. Under ⚙️ Inställningar → 🆕 Uppdateringar väljer en förälder:

- **Manuell**: en 🆕-knapp visas för föräldrarna, och de trycker "Uppdatera nu" när det passar.
- **Automatisk**: uppdateringen installeras när ingen har använt Skolan på 15 minuter.

Windows frågar alltid "Vill du tillåta…" på datorn innan installationen körs. Läxor och inställningar (i `%APPDATA%\Skolan`) finns kvar.

## Köra från källkoden

```
cd fristaende
pip install -r requirements.txt
python -m skolan_app            # med ikon vid klockan
python -m skolan_app --utan-ikon  # t.ex. på en server
```

Öppna sedan http://localhost:8765. Data sparas i `%APPDATA%\Skolan` (Windows) eller `~/.skolan`.

## Bygga

GitHub Actions (`.github/workflows/windows.yml`) bygger `Skolan.exe` med PyInstaller, provkör den
(`windows/provkor.py`) och gör ett installationsprogram med Inno Setup. En tagg `v*` publicerar det under Releases.

## Begränsningar

- Datorn måste vara igång (installationen kan starta Skolan automatiskt).
- Fjärradressen (trycloudflare.com) byts när appen startas om. Mobiler som används utanför hemmet behöver då skanna om QR-koden.
- Notiser på iPhone kräver fjärradressen (https) och att Skolan ligger på hemskärmen.
- Vänner mellan familjer kräver fjärråtkomst hos båda.
