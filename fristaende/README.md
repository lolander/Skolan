# Skolan utan Home Assistant

Windowsappen kör **exakt samma kod** som Home Assistant-integrationen (`custom_components/skolan`).
Skillnaden är ett litet "låtsas-Home Assistant" runt den:

| Home Assistant | Windowsappen |
|---|---|
| Användare och inloggning | Personer med PIN-kod (`skolan_app/konto.py`) |
| Sidopanelen | Egen startsida som laddar samma panel (`skolan_app/webb/`) |
| `ai_task` | Google Gemini med familjens egen nyckel (`skolan_app/ai.py`) |
| Notiser via mobilappen | Webbnotiser (`skolan_app/push.py`) |
| Nabu Casa / fjärråtkomst | Gratis Cloudflare-snabbtunnel (`skolan_app/tunnel.py`) |
| Molnröst för uppläsning | Telefonens/webbläsarens egen röst |
| Resten (`hass`, tidsstyrning, vyer) | `skolan_app/varden.py` + `ha_shim/` |

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
