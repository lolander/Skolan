# Säkerhet

## Rapportera en säkerhetsbrist
Skriv **inte** om säkerhetsbrister i ett vanligt ärende. Använd i stället
**[Security → Report a vulnerability](https://github.com/lolander/Skolan/security/advisories/new)** här på GitHub.
Rapporten syns då bara för dig och den som sköter projektet.

Beskriv gärna vad som är fel, hur det kan återskapas och vilken version det gäller. Du får ett svar inom 7 dagar.
Allvarliga brister rättas så snabbt som möjligt, och appen uppdaterar sig själv. Den som rapporterar nämns i
säkerhetsmeddelandet om hen vill.

## Versioner som får säkerhetsrättningar
| | |
|---|---|
| Läxspelet (Home Assistant och Windows) | senaste versionen |
| Lärarrummet | senaste versionen. Versioner före 0.10.0 finns inte längre att ladda ner och får inga uppgifter om barn från familjernas Läxspelet. |

## Så skyddas användarna
- Ingen server och ingen insamling: data finns bara hos familjen och på lärarens dator. Se [integritetspolicyn](docs/integritet.md).
- Installationsfilerna byggs av GitHub Actions från den här koden, har ett SHA-256-fingeravtryck och signeras (se [kodsignering](docs/kodsignering.md)).
- Komponentlista (SBOM, CycloneDX) för lärarappen finns bland filerna på varje release.
- Lärarappen: krypterad synk (AES-256-GCM), signerade rektorsbeslut (Ed25519), data krypterad med Windows-kontot (DPAPI).
- Lärare ↔ familj: varje synk signeras av lärarappen (Ed25519). Familjens app kontrollerar själv rektorns intyg och mentorns godkännande och kräver att vårdnadshavaren har godkänt skolan och rektorn. Mer i [information till skolor](docs/larare-skolor.md) och [regelverken i Sverige](docs/efterlevnad.md).
