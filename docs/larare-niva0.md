# Kom igång med Läxspelet Lärare på nivå 0

*En sida för rektor, IT och dataskyddsombud. Gäller Läxspelet Lärare 0.12.0 och senare.*

**Nivå 0 betyder att lärarappen inte sparar några uppgifter om elever.** Därför kan en skola börja i liten skala, med ett litet beslut. Nivå 1 och 2 (elevnamn och uppgifter om enskilda elever) kan komma senare, efter en egen bedömning.

🧪 **Prova först, utan att installera:** https://lolander.github.io/Skolan/demo/ (påhittad klass, inget sparas)

## Vad läraren kan göra på nivå 0
- Skicka veckobrev, glosor, studiematerial, scheman och provdatum till familjer som använder Läxspelet hemma.
- Klasslag: klassen samlar poäng tillsammans. Läraren ser bara klassens summa.
- Klassens insikt: vilka glosor många missar och hur många som har börjat plugga inför ett prov. Bara summor, och först när minst 5 familjer är med.
- Samarbeta med kollegor: gemensam provkalender och meddelanden, med krypterad synk.

## Vad som *inte* händer på nivå 0
- Inga elevnamn, inga elev-id och inga uppgifter om enskilda elever sparas eller tas emot. Familjerna visas som "Familj 1, 2, 3 …".
- Familjens Läxspelet skickar inte barnets namn till en lärare på nivå 0.
- Ingen server, inget moln, ingen AI i lärarappen. Utvecklaren får ingen data.
- Lärare kan inte höja sin egen nivå. Bara rektorn i appen kan det, med ett signerat beslut, och IT kan låsa en högsta nivå.
- Lärare kan inte heller ge sig själva en roll. Rektorn utser mentorer och mentorn godkänner ämneslärare. Utan roll får en lärare bara nivå 0 hos familjerna, och vårdnadshavaren godkänner skolan och rektorn i sin app.

## Det som ändå behandlas
- Lärarnas namn, skolans namn och klassens namn, för att lärarna ska kunna samarbeta och familjerna ska veta vem som skickar.
- Lärarappen synkar med familjens Läxspelet via en länk som vårdnadshavaren själv skickar till läraren. Länken innehåller en slumpad nyckel och inget namn.

Dataskyddsombudet avgör om det kräver någon åtgärd. Underlaget i appen (🔐 Behörighet → 🧾 Skapa underlag) visar exakt hur appen är inställd.

## Fyra steg

| | Vem | Vad | Tid |
|---|---|---|---|
| 1 | IT | Godkänn programmet. Installera det, eller låt läraren göra det själv (ingen administratör behövs). Sätt grupprincipen **Högsta behörighetsnivå = Nivå 0**. Mallarna finns i `Laxspelet-Larare-IT.zip` på [release-sidan](https://github.com/lolander/Skolan/releases/latest). | 15 min |
| 2 | Läraren | Starta appen, läs och kvittera **📘 Så gör du rätt**, och skapa skolan under 🏫 Skolan. | 5 min |
| 3 | Rektor | Lämna nivå 0 som standard. Den som skapade skolan kan lämna över rektorsrollen till rektorn. Ett kort beslut räcker (mall: [bilaga C](larare-skolor.md#bilaga-c-mall-för-rektorsbeslut)). | 10 min |
| 4 | Läraren | Informera vårdnadshavarna med [texten i bilaga D](larare-skolor.md#bilaga-d-informationstext-till-vårdnadshavare): det är frivilligt och allt finns också i skolans vanliga kanaler. | 5 min |

## Viktigt
- **Frivilligt komplement.** Allt läraren skickar ska också finnas i skolans lärplattform eller på papper (skollagen: avgiftsfri och likvärdig utbildning).
- **Inga elevuppgifter i utskick.** Det läraren skickar kan läsas av den AI-tjänst familjen själv har valt.
- **Gallra** när läsåret är slut: 🔐 Behörighet → 🗑️ Radera klassens data.

## Mer
- [Information till skolor, IT och dataskyddsombud](larare-skolor.md): nivåerna, tekniska skydd, nätverk, skollagen och mallar.
- [Mallar som Word-filer](mallar/): registerförteckning, exempel på konsekvensbedömning, rektorsbeslut och information till vårdnadshavare.
- [Säkerhet och rapportering av brister](../SECURITY.md) · [Kodsignering](kodsignering.md) · [Integritetspolicy](integritet.md)
