"""Fråga husdjuret: spelguide och barnets läge just nu, som AI:n får när den svarar som husdjuret."""
from __future__ import annotations

from homeassistant.util import dt as dt_util

from . import meriter

# Kort fakta om spelet. Hålls i takt med "Så funkar det" i panel.js.
# Belöningsbutiken, vänner och skolan/klassen nämns inte (dolda för barnen).
SPELGUIDE = """
MERITER ⭐: tjänas på läxor. Lägga in läxan samma dag/dagen efter +20 (senare samma vecka +5). Öva hela glosläxan +5 (max 3 ggr per läxa och dag), alla rätt +5 extra, öva minst 2 dagar före förhöret +10. Förhör: +2 per rätt ord, alla rätt +20, samma dag +5. Högläsning +6/dag, alla dagar +20. Läxboken i tid +25. Läsläxa i tid +30. Prov: registrera 3 dagar innan +10, plugga en dag före +10/dag (max 5), allt klart före provdagen +40, bra provresultat +15/30/50. Tips i övning kostar 1 ⭐, fel efter 2 gratisförsök kostar 1 ⭐.
SVIT 🔥: gör något varje dag. Dag 2 +2, dag 3 +3 … max +10 per dag. Var 7:e dag i rad ger ett svitskydd 🛡️ (max 2) som räddar sviten om man missar 1–2 dagar.
DAGENS UTMANING 🎯: 2–3 mål per dag, alla klara +15. GLOSREKORD ⚡: så många rätt som möjligt på 60 s, nytt rekord +5. DAGENS GÅTA: rätt svar +5, svaret visas dagen efter. FOKUSLÄGE ⏱️: 10/15/20/25 min ger +5/8/10/12, 2 pass per dag. LÄR HUSDJURET 🎓: förklara ett ord med egna ord, bra förklaring +5, jättebra +8. REPETERA 🔁: öva en lista man inte övat på 10 dagar, +10 extra. SYSKONUPPDRAG: gemensamt mål med syskonet, +30 till båda. SAMLARKORT 🃏: kort delas ut när man tjänar 20/60/120 ⭐ samma dag, 50 % chans när man besegrar ett monster på kartan, och av bossar. REVANSCH i Arenan: slå en redan besegrad boss igen (2 ⚡, använder stridsuppsättningen) och vinn kort, högst 3 per dag; dubbletter +3, fullt album +100. KISTOR 🎁: varje läxa/prov man lägger in ger en kista (⭐, ⚡ eller kort), prov inlagt ≥3 dagar innan = silverkista, ≥7 dagar = guldkista, max 4 per dag. PROVBOSSAR 📝: varje prov blir en boss, varje pluggdag före provet ger den 15 % skada (allt klart +20 %, max 80 %), slutstriden öppnar dagen före provet och kostar inget ⚡, vinst +20 och provtrofé 🏆. VECKANS KOLL 📅: alla läxor i läxschemat inlagda i tid en vecka = +15, svitskydd och guldkista. MITT SCHEMA 🗓️: fota lektionsschemat så läser AI:n ämnena; efter skolan frågar husdjuret om det blev läxa (ärligt nej +2); husdjuret frågar också efter studiematerial till ämnen som saknar det, första materialet i ett ämne ger en silverkista. MEDALJER 🏅 +25 var. Var 100:e merit = ny nivå.
HUSDJURET 🐾: växer av alla meriter: Ägg → Bebis (30) → Liten (150) → Stor (400) → Jätte (800) → Legend (1500). Blir hungrigt/ledset om man inte pluggar på ett par dagar. Man kan ha flera husdjur: ett nytt kostar 100 ⭐ och börjar som ägg, byte mellan egna djur är gratis. Bara det aktiva djuret växer, får XP och utvecklas, så varje djur blir unikt. Varje djur har egna attacker (med uppgraderingar), egen försvarsträning och egna kompisar, så ett nytt djur börjar om från början. Allt finns kvar när man byter tillbaka. Varje djur har ett element (🔥 eld, 🍃 natur, ⚡ blixt, 🌊 vatten, ❄️ is eller 💥 kraft): attacker av samma typ gör +25 % (💪), en typ passar dåligt och gör −25 % (😕). Eld-djur är dåliga på is, is- och vattendjur på eld, naturdjur på blixt, blixtdjur på vatten, kraftdjur på natur. Bra strategi: välj attacker som passar djuret OCH som monstren är svaga mot. STRIDSUPPSÄTTNING: i arenan och mot världsbossar får djuret bara använda 4 valda attacker (väljs i butiken, låses när bosstriden börjat). I ARENAN är varje djur svagt mot en attacktyp: eld-djur mot vatten, vatten mot blixt, blixt mot natur, natur mot eld, is mot kraft, kraft mot is – träff på svag punkt gör ×1,5. LADDATTACKER (🌀 Snabbladdning 200, 🌟 Stjärnsmäll 300, och ☀️ Solbrand/🌊 Tsunami/🌩️ Superåska/🌳 Urskogens vrede/🧊 Istiden 380 ⭐): kostar ingen ⚡ men en laddmätare måste fyllas med träffar (svag punkt laddar mest), bara 1–2 gånger per strid, bara i arenan och mot bossar, och tar en plats i uppsättningen. Med smart uppsättning kan ett svagare djur vinna. Sköldar, drycker, energi, hattar och andra saker delas mellan djuren. Från Liten utvecklas det efter vad man gör mest (glosrekord, läsläxor, alla rätt på förhör, många övningar, besegrade bossar) och får ett nytt utseende. Husdjuret har också XP-nivå (1–50): högre nivå ger mer ❤️ liv och +2 % skada per nivå. CP visar hur starkt det är.
HUSDJURSBUTIKEN 🛍️: hattar, bakgrunder, effekter, kompisar, attacker, sköldar, livdrycker och energi. Storleken påverkas inte av att man handlar. Kompisar kan ha en HEMLIG effekt (se reglerna).
ÄVENTYRSKARTAN 🗺️: världar med 10 nivåer var: Glosskogen, Bläckhavet, Trollberget, Sömnträsket, Robotfabriken, Drakvulkanen, Spökslottet, Tidshavet. Varje merit man tjänar gör skada på nivåns monster. Snabbt klarad nivå ger fler stjärnor. Var 10:e nivå är en världsboss: +50 ⭐ och en unik sak. Monstren är lika svåra som man brukar plugga, så alla har chans.
ATTACKER ⚔️: köps i butiken, kostar ⚡ energi. Man får 1 ⚡ per 25 ⭐ man tjänar (max 15 sparade), eller köper ⚡ för 20 ⭐ (max 5 per dag). Varje monster är svagt mot en typ (🔥 eld, 🍃 natur, ⚡ blixt, 🌊 vatten, ❄️ is) och tar då DUBBEL skada. 💥 kraft är aldrig svaghet. Köpta attacker kan uppgraderas till nivå 5 (dyrare för varje nivå). Superattack bara 1 gång per vecka, Regnbågsstråle 1 gång per dag men alla är svaga mot den. Meteorregn: 3–6 meteorer. Blomsterstorm läker husdjuret. Lavaregn +50 % mot bossar. Flera attacker blir starkare av plugg samma dag/vecka (Blixt, Bladvirvel, Istapp, Vattenstråle, Bokstorm, Åskknall, Våg).
STRID ❤️: monstret slår tillbaka (missar ibland). 0 liv = husdjuret kan inte attackera. Liv tillbaka: 1 ❤️ per 3 ⭐ man tjänar, eller livdrycker (🧃 +20, 🧪 +50, 💖 fullt). Från värld 2, när husdjuret är minst Liten, har monstren egna attacker och bossarna slår oftare.
SKÖLDAR 🛡️: DEF minskar skadan (DEF 50 halverar). Monstren slår med sin världs typ (t.ex. 🔥 i Drakvulkanen, 🌊 i Bläckhavet, ❄️ i Sömnträsket), rätt typsköld tar halva skadan. Vissa sköldar blockerar, speglar eller läker.
VECKANS HÄNDELSE: varje vecka en ny twist, t.ex. Eldveckan (🔥 +50 %), Energiveckan (1 ⚡ per 18 ⭐), Bossveckan, Läkeveckan, Turveckan.
ARENAN 🏟️: husdjuret mot syskonets. Vinst 10 🏆, förlust 2. Försvarsträning hjälper när man blir utmanad. GLOSSTRID: svara på glosor för att slå monstret. GLOSDUELL/PLUGGSTUND: tävla eller plugga med syskonet. LAG: lagboss varje vecka, +40 till alla om den besegras.
LÄXPASSET 🎟️: varje merit ger XP, 30 nivåer med belöningar, börjar om varje månad.
VECKANS TÄVLING 🏆: man tävlar mot sig själv: del av sina egna läxor gjorda i tid + hur flitig man är jämfört med sina egna 4 senaste veckor. Perfekt vecka i rad ger bonus. Därför har yngre och äldre lika stor chans.
REGLER: det man gör utanför appen räknas när mamma eller pappa godkänt. Fusk lönar sig inte.
""".strip()


def lage(data: dict) -> str:
    """Barnets läge just nu, i korta rader."""
    rader = []
    s = meriter.sammanfattning(data)
    d = s.get("djur")
    rader.append(f"Meriter att handla för: {s['saldo']} ⭐. Tjänat totalt: {s['intjanat']}. Den här veckan: {s['veckan']}.")
    rader.append(f"Svit: {s['streak']} dagar ({'har pluggat idag' if s['streak_idag'] else 'har INTE pluggat idag än'}). Svitskydd: {s['skydd']}.")
    kvar = [x["text"] for x in s.get("utmaning") or [] if not x.get("klar")]
    if s.get("utmaning"):
        rader.append("Dagens utmaning: " + ("allt klart!" if not kvar else "kvar: " + ", ".join(kvar) + "."))
    if not d:
        rader.append("Husdjur: inget valt ännu.")
        return "\n".join(rader)
    dn = meriter.djur_niva(data)
    liv, mx = meriter.djur_liv(data)
    form = (d.get("form") or {}).get("namn")
    el = d.get("element") or {}
    rader.append(f"Element: {el.get('namn')}-djur, {meriter.TYPER.get(el.get('bra'), '')}-attacker +25 %, {meriter.TYPER.get(el.get('dalig'), '')}-attacker −25 %.")
    rader.append(f"Husdjur: {d.get('namn')} {d.get('art')}, {d.get('steg_namn')}{f' ({form})' if form else ''}, nivå {dn['niva']}, "
                 f"liv {liv}/{mx}, CP {meriter.djur_cp(data)}" + (f", {d['nasta'] - d['intjanat']} ⭐ kvar till nästa steg" if d.get("nasta") else "") + ".")
    if d.get("steg", 0) < 1:
        return "\n".join(rader)
    k = meriter.karta_status(data)
    mon = k["monster"]
    typ = lambda t: meriter.TYPER.get(t, t)  # noqa: E731
    rader.append(f"Kartan: nivå {k['niva']} i {mon['varld']['namn']}. Monster: {mon['ikon']} {mon['namn']}{' (VÄRLDSBOSS)' if mon.get('boss') else ''}, "
                 f"svagt mot {typ(mon['svag'])}, slår med {typ(k['slag'])}. Monstrets liv kvar: {k['hp'] - k['skada']} av {k['hp']}.")
    if k.get("mon_attacker"):
        rader.append("Monstrets attacker: " + ", ".join(f"{a['ikon']} {a['namn']}" for a in k["mon_attacker"]) + ".")
    rader.append(f"Energi: {k['energi']}/{k['energi_max']} ⚡ (1 ⚡ per {k['p_energi']} ⭐).")
    if liv <= 0:
        rader.append("Husdjuret är UTMATTAT (0 liv) och kan inte attackera förrän det fått liv tillbaka.")
    agda = [a for a in k["attacker"] if a["har"]]
    if agda:
        rader.append("Egna attacker (skada mot nuvarande monster): " + "; ".join(
            f"{a['ikon']} {a['namn']} nivå {a['lvl']}: {a['nu']} skada, kostar {a['energi']} ⚡{', SVAGHET' if a['svag'] else ''}{', passar djuret +25 %' if a['pass'] > 1 else ', passar inte djuret −25 %' if a['pass'] < 1 else ''}"
            f"{' – redan använd, går inte nu' if a['slut'] else ' – FÖR LITE ⚡ just nu' if a['energi'] > k['energi'] else ''}"
            for a in agda) + ".")
    else:
        rader.append("Egna attacker: inga ännu.")
    namn = {x["id"]: f"{x['ikon']} {x['namn']}" for x in k["attacker"]}
    rader.append("Stridsuppsättning (arena och bossar): " + (", ".join(namn[x] for x in k.get("uppsattning", []) if x in namn) or "tom")
                 + (" (låst under bosstriden)" if k.get("boss_las") else "") + ".")
    if k.get("ladd"):
        rader.append(f"Laddmätare mot bossen: {k['ladd']['p']}/{k['ladd']['max']}.")
    kan = [a for a in k["attacker"] if not a["har"] and a["steg"] <= d.get("steg", 0)]
    if kan:
        rader.append("Kan köpas: " + "; ".join(f"{a['ikon']} {a['namn']} ({typ(a['typ'])}{', passar +25 %' if a['pass'] > 1 else ', passar inte −25 %' if a['pass'] < 1 else ''}) {a['pris']} ⭐" for a in sorted(kan, key=lambda a: a["pris"])[:6]) + ".")
    dr = [f"{x['antal']} {x['ikon']}" for x in k["drycker"] if x["antal"]]
    rader.append("Drycker i ryggsäcken: " + (", ".join(dr) if dr else "inga") + f". DEF: {k['forsvar']['def']}.")
    h = meriter.vecko_handelse()
    rader.append(f"Veckans händelse: {h['ikon']} {h['namn']}: {h['info']}")
    for b in meriter.provboss_lista(data):
        if not b["vunnen"] and b["dagar_kvar"] >= 0:
            rader.append(f"Provboss {b['ikon']} {b['namn']} ({b['prov']}): provet om {b['dagar_kvar']} dagar, {b['pluggdagar']} pluggdagar, "
                         f"{b['skada']} % skadad, svag mot {typ(b['svag'])}" + (", slutstriden är öppen" if b["oppen"] else "") + ".")
    kist = len(meriter._m(data).get("kistor", []))
    if kist:
        rader.append(f"Oöppnade kistor: {kist}.")
    return "\n".join(rader)
