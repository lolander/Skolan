"""Meriter, medaljer och nivåer för Skolan.

Meriter delas ut på servern (inte i webbläsaren) när barnet själv:
- lägger in en läxa i tid enligt läxschemat som föräldern har satt upp,
- övar på glosor (extra i god tid före förhöret),
- gör förhör på distans.
Allt sparas i barnets data.json under "meriter". Varje utdelning har en nyckel
så att samma sak aldrig ger meriter två gånger.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.util import dt as dt_util

# Poäng
P_I_TID = 20  # läxan inlagd samma dag eller dagen efter den brukar komma
P_SENT = 5  # inlagd senare samma vecka
P_OVNING = 5  # en genomförd övning (max 3 per glosläxa och dag)
P_OVNING_ALLA_RATT = 5
P_TIDIGT = 10  # övat minst 2 dagar före förhöret (en gång per glosläxa och dag)
P_FORHOR_RATT = 2  # per rätt ord på förhör på distans
P_FORHOR_ALLA = 20
P_FORHOR_DIREKT = 5  # gjort förhöret samma dag som det skickades
P_MEDALJ = 25

NIVAER = ["Nybörjare", "Lärling", "Utforskare", "Kunnig", "Skicklig", "Expert", "Mästare", "Stormästare", "Legend"]
NIVA_STEG = 100

# id, ikon, namn, beskrivning, räknare, gräns
MEDALJER = [
    ("forsta", "🐣", "Första steget", "Gjort din första övning", "ovningar", 1),
    ("flitig", "📚", "Flitig", "Gjort 25 övningar", "ovningar", 25),
    ("glosmaskin", "🤖", "Glosmaskin", "Gjort 100 övningar", "ovningar", 100),
    ("rulle", "🔥", "På rulle", "Gjort något i Skolan 3 dagar i rad", "streak", 3),
    ("veckostjarna", "⭐", "Veckostjärna", "Gjort något i Skolan 7 dagar i rad", "streak", 7),
    ("manadsmastare", "🏆", "Månadsmästare", "Gjort något i Skolan 30 dagar i rad", "streak", 30),
    ("punktlig", "⏰", "Punktlig", "Lagt in en läxa i tid", "i_tid", 1),
    ("ordning", "🗂️", "Ordningsmästare", "Lagt in 10 läxor i tid", "i_tid", 10),
    ("tidig", "🐦", "Tidig fågel", "Övat 3 olika dagar före ett förhör", "tidig_max", 3),
    ("fullpott", "🎯", "Full pott", "Alla rätt på ett förhör", "full_pott", 1),
    ("prickskytt", "🏹", "Prickskytt", "Alla rätt på 5 förhör", "full_pott", 5),
    ("blixt", "⚡", "Snabb som blixten", "Gjort ett förhör samma dag som det kom", "forhor_direkt", 1),
    ("lasare", "📖", "Läshäst", "Klarat en läsläxa", "las_klara", 1),
    ("bokmal", "🐛", "Bokmal", "Klarat 5 läsläxor", "las_klara", 5),
    ("provproffs", "📝", "Provproffs", "Pluggat klart inför ett prov i tid", "prov_klara", 1),
    ("utmanare", "🎯", "Utmanare", "Klarat dagens utmaning", "utmaningar", 1),
    ("utmaningskung", "👑", "Utmaningskung", "Klarat dagens utmaning 10 gånger", "utmaningar", 10),
    ("snabbfinger", "⚡", "Snabbfinger", "Fått 20 rätt i Glosrekord", "rekord_max", 20),
    ("raket", "🚀", "Raket", "Fått 35 rätt i Glosrekord", "rekord_max", 35),
    ("passmastare", "🎟️", "Passmästare", "Klarat alla 30 nivåer i läxpasset", "pass_klara", 1),
    ("bossjagare", "⚔️", "Bossjägare", "Besegrat en världsboss på kartan", "bossar", 1),
    ("aventyrare", "🗺️", "Äventyrare", "Klarat 10 nivåer på kartan", "nivaer", 10),
    ("kartans_hjalte", "🏆", "Kartans hjälte", "Klarat 50 nivåer på kartan", "nivaer", 50),
]

P_LAS_I_TID = 30  # läsläxan läst och kontrollfrågorna klarade före slutdatum
P_LAS_SENT = 10
P_PROV_KLART = 40  # allt inför provet läst och kontrollerat före provdagen
P_PROV_DAG = 10  # pluggat inför provet en dag (minst 1 dag före, max 5 dagar)
P_REG_PROV = 10  # barnet registrerade provet minst 3 dagar innan

P_HOGL_DAG = 6  # högläsning en dag, godkänd av förälder
P_HOGL_ALLA = 20  # alla dagar i veckan
P_SKRIV_I_TID = 25  # läxboken klar senast inlämningsdagen
P_SKRIV_SENT = 10

VECKODAGAR = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def _m(data: dict) -> dict:
    m = data.setdefault("meriter", {})
    m.setdefault("logg", [])
    m.setdefault("nycklar", [])
    m.setdefault("medaljer", {})
    m.setdefault("raknare", {})
    m.setdefault("ovningsdagar", [])
    return m


def ge(data: dict, poang: int, orsak: str, nyckel: str | None = None, ikon: str = "⭐") -> bool:
    """Ge meriter. Returnerar False om nyckeln redan har gett meriter."""
    m = _m(data)
    if nyckel:
        if nyckel in m["nycklar"]:
            return False
        m["nycklar"].append(nyckel)
        del m["nycklar"][:-3000]
    m["logg"].append({"tid": dt_util.now().isoformat(timespec="minutes"), "p": int(poang), "orsak": orsak, "ikon": ikon})
    del m["logg"][:-500]
    if poang > 0:
        m["intjanat"] = m.get("intjanat", 0) + int(poang)
        if ikon not in EJ_SKADA:  # belöningar (pass, nivåer, bossar) ger inte pass-XP eller skada
            _pass_xp(m, int(poang))
            _karta_energi(data, int(poang))
            _karta_skada(data, int(poang))
    m["saldo"] = m.get("saldo", 0) + int(poang)
    return True


def _rakna(data: dict, namn: str, n: int = 1) -> None:
    r = _m(data)["raknare"]
    r[namn] = r.get(namn, 0) + n


def _streak(dagar: list[str], slut: date | None = None) -> int:
    """Dagar i rad med läxarbete (alla dagar, även helger)."""
    s = set(dagar)
    d = slut or dt_util.now().date()
    if d.isoformat() not in s:
        d -= timedelta(days=1)  # sviten lever kvar tills dagen är slut
    n = 0
    for _ in range(400):
        if d.isoformat() in s:
            n += 1
        else:
            break
        d -= timedelta(days=1)
    return n


P_STREAK_MAX = 10  # bonus per dag i rad: dag 2 = +2, dag 3 = +3 … max +10
SKYDD_MAX = 2  # svitskydd: ett per 7 dagar i rad, högst 2 sparade
SCHEMA_START = ""  # schemaposter räknas från "fran" (sätts när de sparas); äldre utan "fran" räknas alltid
P_UTMANING = 15  # alla mål i dagens utmaning klara
P_REKORD = 5  # nytt personligt rekord i Glosrekord (en gång per lista och dag)
REKORD_MIN = 5  # så många rätt krävs för att Glosrekord ska räknas för sviten

DJUR = ["🐶", "🐱", "🦊", "🐼", "🐉", "🐢", "🦄", "🐧", "🐰", "🦖",
        "🐻", "🐨", "🐷", "🐸", "🐯", "🦁", "🐭", "🐮", "🐵", "🐹", "🦉", "🦝",
        "🌭", "🍉", "🍞", "🌵", "🍕", "🍦", "🧦", "🪨", "🍌",  # larviga husdjur
        "🐙", "🍩", "🥑", "🍄", "☁️", "🦷", "🥔", "👻", "🤖"]
P_BYT_DJUR = 50  # byta till ett annat djur (första valet är gratis)
# Husdjursbutiken: saker köps för saldot (intjänade meriter och djurets storlek påverkas inte)
DJURBUTIK = [
    {"id": "keps", "typ": "hatt", "ikon": "🧢", "namn": "Keps", "pris": 30, "steg": 0},
    {"id": "rosett", "typ": "hatt", "ikon": "🎀", "namn": "Rosett", "pris": 40, "steg": 0},
    {"id": "solglas", "typ": "hatt", "ikon": "🕶️", "namn": "Solglasögon", "pris": 60, "steg": 0},
    {"id": "horlurar", "typ": "hatt", "ikon": "🎧", "namn": "Hörlurar", "pris": 80, "steg": 1},
    {"id": "hogHatt", "typ": "hatt", "ikon": "🎩", "namn": "Hög hatt", "pris": 100, "steg": 1},
    {"id": "krona", "typ": "hatt", "ikon": "👑", "namn": "Krona", "pris": 250, "steg": 3},
    {"id": "hav", "typ": "bakgrund", "ikon": "🌊", "namn": "Havet", "pris": 60, "steg": 0,
     "bg": "linear-gradient(160deg,#4fc3f7,#0277bd)", "fg": "#fff", "deko": "🐠"},
    {"id": "djungel", "typ": "bakgrund", "ikon": "🌴", "namn": "Djungeln", "pris": 80, "steg": 0,
     "bg": "linear-gradient(160deg,#9ccc65,#2e7d32)", "fg": "#fff", "deko": "🌿"},
    {"id": "vinter", "typ": "bakgrund", "ikon": "❄️", "namn": "Vinter", "pris": 100, "steg": 1,
     "bg": "linear-gradient(160deg,#e3f2fd,#90caf9)", "fg": "#0d47a1", "deko": "⛄"},
    {"id": "rymd", "typ": "bakgrund", "ikon": "🌌", "namn": "Rymden", "pris": 150, "steg": 2,
     "bg": "radial-gradient(circle at 30% 20%,#5c6bc0,#1a1040 70%)", "fg": "#fff", "deko": "🪐"},
    {"id": "slott", "typ": "bakgrund", "ikon": "🏰", "namn": "Slottet", "pris": 200, "steg": 2,
     "bg": "linear-gradient(160deg,#f8bbd0,#8e24aa)", "fg": "#fff", "deko": "🏰"},
    {"id": "glitter", "typ": "effekt", "ikon": "✨", "namn": "Glitter", "pris": 120, "steg": 1, "partikel": "✨"},
    {"id": "regnbage", "typ": "effekt", "ikon": "🌈", "namn": "Regnbågsglöd", "pris": 300, "steg": 3, "glod": "regnbage"},
    # ---- fler hattar ----
    {"id": "blomma", "typ": "hatt", "ikon": "🌻", "namn": "Solros", "pris": 50, "steg": 0},
    {"id": "svamp", "typ": "hatt", "ikon": "🍄", "namn": "Svamphatt", "pris": 70, "steg": 0},
    {"id": "ballong", "typ": "hatt", "ikon": "🎈", "namn": "Ballong", "pris": 70, "steg": 0},
    {"id": "tarta", "typ": "hatt", "ikon": "🧁", "namn": "Muffinhatt", "pris": 90, "steg": 0},
    {"id": "munk", "typ": "hatt", "ikon": "🍩", "namn": "Munk", "pris": 90, "steg": 0},
    {"id": "melon", "typ": "hatt", "ikon": "🍉", "namn": "Melonhatt", "pris": 110, "steg": 1},
    {"id": "hamburgare", "typ": "hatt", "ikon": "🍔", "namn": "Hamburgare", "pris": 120, "steg": 1},
    {"id": "studentmossa", "typ": "hatt", "ikon": "🎓", "namn": "Studentmössa", "pris": 150, "steg": 1},
    {"id": "hjalm", "typ": "hatt", "ikon": "⛑️", "namn": "Räddningshjälm", "pris": 150, "steg": 1},
    {"id": "dykmask", "typ": "hatt", "ikon": "🤿", "namn": "Dykmask", "pris": 180, "steg": 1},
    {"id": "stjarna", "typ": "hatt", "ikon": "⭐", "namn": "Stjärna", "pris": 200, "steg": 1},
    {"id": "blixt", "typ": "hatt", "ikon": "⚡", "namn": "Blixt", "pris": 250, "steg": 2},
    {"id": "eld", "typ": "hatt", "ikon": "🔥", "namn": "Eldfrisyr", "pris": 300, "steg": 2},
    {"id": "planet", "typ": "hatt", "ikon": "🪐", "namn": "Planet", "pris": 350, "steg": 2},
    {"id": "kaktus", "typ": "hatt", "ikon": "🌵", "namn": "Kaktus", "pris": 120, "steg": 1},
    {"id": "blackfisk", "typ": "hatt", "ikon": "🐙", "namn": "Bläckfiskhatt", "pris": 400, "steg": 2},
    {"id": "pokal", "typ": "hatt", "ikon": "🏆", "namn": "Pokal", "pris": 600, "steg": 3},
    {"id": "diamant", "typ": "hatt", "ikon": "💎", "namn": "Diamant", "pris": 900, "steg": 3},
    {"id": "enhorning", "typ": "hatt", "ikon": "🦄", "namn": "Enhörningshorn", "pris": 1200, "steg": 4},
    {"id": "diamantkrona", "typ": "hatt", "ikon": "💠", "namn": "Diamantkrona", "pris": 2500, "steg": 5},
    # ---- fler bakgrunder ----
    {"id": "solnedgang", "typ": "bakgrund", "ikon": "🌅", "namn": "Solnedgång", "pris": 90, "steg": 0, "bg": "linear-gradient(180deg,#ff7043,#ffb74d 50%,#7e57c2)", "fg": "#fff", "deko": "🌅"},
    {"id": "bondgard", "typ": "bakgrund", "ikon": "🐄", "namn": "Bondgården", "pris": 90, "steg": 0, "bg": "linear-gradient(180deg,#b3e5fc,#c5e1a5 60%,#8d6e63)", "fg": "#33691e", "deko": "🚜"},
    {"id": "fotboll", "typ": "bakgrund", "ikon": "⚽", "namn": "Fotbollsplanen", "pris": 110, "steg": 0, "bg": "repeating-linear-gradient(90deg,#43a047 0 30px,#388e3c 30px 60px)", "fg": "#fff", "deko": "⚽"},
    {"id": "godis", "typ": "bakgrund", "ikon": "🍭", "namn": "Godislandet", "pris": 130, "steg": 1, "bg": "linear-gradient(160deg,#f48fb1,#ce93d8,#80deea)", "fg": "#4a148c", "deko": "🍭"},
    {"id": "cirkus", "typ": "bakgrund", "ikon": "🎪", "namn": "Cirkusen", "pris": 150, "steg": 1, "bg": "repeating-linear-gradient(90deg,#e53935 0 24px,#fafafa 24px 48px)", "fg": "#b71c1c", "deko": "🎪"},
    {"id": "tivoli", "typ": "bakgrund", "ikon": "🎡", "namn": "Tivolit", "pris": 160, "steg": 1, "bg": "linear-gradient(160deg,#311b92,#e91e63)", "fg": "#fff", "deko": "🎡"},
    {"id": "oken", "typ": "bakgrund", "ikon": "🌵", "namn": "Öknen", "pris": 160, "steg": 1, "bg": "linear-gradient(180deg,#ffe0b2,#ffb74d 60%,#e65100)", "fg": "#5d4037", "deko": "🐪"},
    {"id": "berg", "typ": "bakgrund", "ikon": "⛰️", "namn": "Fjällen", "pris": 180, "steg": 1, "bg": "linear-gradient(180deg,#90caf9,#e0e0e0 60%,#78909c)", "fg": "#263238", "deko": "🏔️"},
    {"id": "korallrev", "typ": "bakgrund", "ikon": "🪸", "namn": "Korallrevet", "pris": 220, "steg": 2, "bg": "linear-gradient(180deg,#26c6da,#00838f 60%,#ff8a65)", "fg": "#fff", "deko": "🐡"},
    {"id": "regnskog", "typ": "bakgrund", "ikon": "🦜", "namn": "Regnskogen", "pris": 220, "steg": 2, "bg": "linear-gradient(160deg,#1b5e20,#43a047,#c0ca33)", "fg": "#fff", "deko": "🦜"},
    {"id": "stad", "typ": "bakgrund", "ikon": "🌃", "namn": "Stan på natten", "pris": 250, "steg": 2, "bg": "linear-gradient(180deg,#0d1b4c,#1a237e 60%,#ffab00)", "fg": "#fff", "deko": "🌃"},
    {"id": "isgrotta", "typ": "bakgrund", "ikon": "🧊", "namn": "Isgrottan", "pris": 280, "steg": 2, "bg": "linear-gradient(160deg,#e0f7fa,#4dd0e1,#006064)", "fg": "#004d40", "deko": "🧊"},
    {"id": "moln", "typ": "bakgrund", "ikon": "☁️", "namn": "Molnriket", "pris": 300, "steg": 2, "bg": "linear-gradient(180deg,#bbdefb,#fff)", "fg": "#1565c0", "deko": "☁️"},
    {"id": "dino", "typ": "bakgrund", "ikon": "🦕", "namn": "Dinosaurietiden", "pris": 350, "steg": 2, "bg": "linear-gradient(160deg,#8d6e63,#558b2f,#f57f17)", "fg": "#fff", "deko": "🌋"},
    {"id": "pirat", "typ": "bakgrund", "ikon": "🏴‍☠️", "namn": "Piratskeppet", "pris": 400, "steg": 3, "bg": "linear-gradient(180deg,#5d4037,#3e2723 50%,#1565c0)", "fg": "#fff", "deko": "⚓"},
    {"id": "norrsken", "typ": "bakgrund", "ikon": "🌠", "namn": "Norrsken", "pris": 500, "steg": 3, "bg": "linear-gradient(170deg,#0d1b2a,#1b998b,#7b2ff7,#0d1b2a)", "fg": "#fff", "deko": "🌠"},
    {"id": "vulkan", "typ": "bakgrund", "ikon": "🌋", "namn": "Vulkanen", "pris": 600, "steg": 3, "bg": "linear-gradient(180deg,#212121,#bf360c 60%,#ff6f00)", "fg": "#fff", "deko": "🌋"},
    {"id": "rymdstation", "typ": "bakgrund", "ikon": "🛰️", "namn": "Rymdstationen", "pris": 800, "steg": 4, "bg": "radial-gradient(circle at 70% 30%,#90a4ae,#263238 40%,#000 80%)", "fg": "#fff", "deko": "🛰️"},
    {"id": "regnbagsland", "typ": "bakgrund", "ikon": "🌈", "namn": "Regnbågslandet", "pris": 1000, "steg": 4, "bg": "linear-gradient(160deg,#f44336,#ff9800,#ffeb3b,#4caf50,#2196f3,#9c27b0)", "fg": "#fff", "deko": "🌈"},
    {"id": "guldpalats", "typ": "bakgrund", "ikon": "💰", "namn": "Guldpalatset", "pris": 2000, "steg": 5, "bg": "linear-gradient(160deg,#fff8e1,#ffd54f,#ff8f00)", "fg": "#5d4037", "deko": "💰"},
    # ---- fler effekter ----
    {"id": "bubblor", "typ": "effekt", "ikon": "🫧", "namn": "Bubblor", "pris": 80, "steg": 0, "partikel": "🫧"},
    {"id": "lov", "typ": "effekt", "ikon": "🍂", "namn": "Höstlöv", "pris": 90, "steg": 0, "partikel": "🍂"},
    {"id": "noter", "typ": "effekt", "ikon": "🎵", "namn": "Musik", "pris": 110, "steg": 0, "partikel": "🎵"},
    {"id": "stjarnor", "typ": "effekt", "ikon": "⭐", "namn": "Stjärnregn", "pris": 140, "steg": 1, "partikel": "⭐"},
    {"id": "korsbar", "typ": "effekt", "ikon": "🌸", "namn": "Körsbärsblom", "pris": 150, "steg": 1, "partikel": "🌸"},
    {"id": "godisregn", "typ": "effekt", "ikon": "🍬", "namn": "Godisregn", "pris": 160, "steg": 1, "partikel": "🍬"},
    {"id": "pizzaregn", "typ": "effekt", "ikon": "🍕", "namn": "Pizzaregn", "pris": 180, "steg": 1, "partikel": "🍕"},
    {"id": "bin", "typ": "effekt", "ikon": "🐝", "namn": "Bisvärm", "pris": 200, "steg": 1, "partikel": "🐝"},
    {"id": "blixtar", "typ": "effekt", "ikon": "⚡", "namn": "Blixtar", "pris": 250, "steg": 2, "partikel": "⚡"},
    {"id": "eldflammor", "typ": "effekt", "ikon": "🔥", "namn": "Eldflammor", "pris": 300, "steg": 2, "partikel": "🔥"},
    {"id": "mynt", "typ": "effekt", "ikon": "🪙", "namn": "Myntregn", "pris": 400, "steg": 2, "partikel": "🪙"},
    {"id": "diamanter", "typ": "effekt", "ikon": "💎", "namn": "Diamantregn", "pris": 800, "steg": 3, "partikel": "💎"},
    {"id": "supernova", "typ": "effekt", "ikon": "🌟", "namn": "Supernova", "pris": 1500, "steg": 4, "partikel": "🌟"},
    {"id": "puls", "typ": "effekt", "ikon": "💓", "namn": "Pulserande", "pris": 150, "steg": 1, "glod": "puls"},
    {"id": "isglod", "typ": "effekt", "ikon": "🧊", "namn": "Isglöd", "pris": 220, "steg": 2, "glod": "is"},
    {"id": "eldglod", "typ": "effekt", "ikon": "🔥", "namn": "Eldglöd", "pris": 260, "steg": 2, "glod": "eld"},
    {"id": "skugga", "typ": "effekt", "ikon": "🥷", "namn": "Ninjaskugga", "pris": 350, "steg": 2, "glod": "skugga"},
    {"id": "snurr", "typ": "effekt", "ikon": "🌀", "namn": "Snurr", "pris": 400, "steg": 3, "glod": "snurr"},
    {"id": "guldglod", "typ": "effekt", "ikon": "✨", "namn": "Guldglöd", "pris": 700, "steg": 3, "glod": "guld"},
    # ---- kompisar (följer med husdjuret) ----
    {"id": "k_kyckling", "typ": "kompis", "ikon": "🐥", "namn": "Kycklingen", "pris": 80, "steg": 0},
    {"id": "k_mus", "typ": "kompis", "ikon": "🐭", "namn": "Musen", "pris": 90, "steg": 0},
    {"id": "k_groda", "typ": "kompis", "ikon": "🐸", "namn": "Grodan", "pris": 110, "steg": 0},
    {"id": "k_nyckelpiga", "typ": "kompis", "ikon": "🐞", "namn": "Nyckelpigan", "pris": 120, "steg": 0},
    {"id": "k_snigel", "typ": "kompis", "ikon": "🐌", "namn": "Snigeln", "pris": 120, "steg": 0},
    {"id": "k_fjaril", "typ": "kompis", "ikon": "🦋", "namn": "Fjärilen", "pris": 150, "steg": 1},
    {"id": "k_papegoja", "typ": "kompis", "ikon": "🦜", "namn": "Papegojan", "pris": 200, "steg": 1},
    {"id": "k_blackfisk", "typ": "kompis", "ikon": "🐙", "namn": "Bläckfisken", "pris": 250, "steg": 2},
    {"id": "k_robot", "typ": "kompis", "ikon": "🤖", "namn": "Roboten", "pris": 400, "steg": 2},
    {"id": "k_alien", "typ": "kompis", "ikon": "👽", "namn": "Rymdvarelsen", "pris": 500, "steg": 3},
    {"id": "k_spoke", "typ": "kompis", "ikon": "👻", "namn": "Spöket", "pris": 300, "steg": 2},
    {"id": "k_drake", "typ": "kompis", "ikon": "🐲", "namn": "Draken", "pris": 1000, "steg": 4},
    {"id": "k_enhorning", "typ": "kompis", "ikon": "🦄", "namn": "Enhörningen", "pris": 1800, "steg": 5},
    # ---- högtider (går bara att köpa 2 veckor före och under högtiden, men behålls för alltid) ----
    {"id": "hj_hatt", "hogtid": "alla_hjartans", "typ": "hatt", "ikon": "💖", "namn": "Hjärta", "pris": 40, "steg": 0},
    {"id": "hj_bg", "hogtid": "alla_hjartans", "typ": "bakgrund", "ikon": "💌", "namn": "Kärleksbrev", "pris": 70, "steg": 0,
     "bg": "linear-gradient(160deg,#f8bbd0,#ec407a)", "fg": "#fff", "deko": "💌"},
    {"id": "hj_eff", "hogtid": "alla_hjartans", "typ": "effekt", "ikon": "💕", "namn": "Svävande hjärtan", "pris": 100, "steg": 0, "partikel": "💕"},
    {"id": "pask_hatt", "hogtid": "pask", "typ": "hatt", "ikon": "🐣", "namn": "Påskkyckling", "pris": 40, "steg": 0},
    {"id": "pask_bg", "hogtid": "pask", "typ": "bakgrund", "ikon": "🌷", "namn": "Påskäng", "pris": 70, "steg": 0,
     "bg": "linear-gradient(160deg,#fff59d,#aed581)", "fg": "#33691e", "deko": "🌷"},
    {"id": "pask_eff", "hogtid": "pask", "typ": "effekt", "ikon": "🥚", "namn": "Påskägg", "pris": 100, "steg": 0, "partikel": "🥚"},
    {"id": "mid_hatt", "hogtid": "midsommar", "typ": "hatt", "ikon": "🌸", "namn": "Blomsterkrans", "pris": 40, "steg": 0},
    {"id": "mid_bg", "hogtid": "midsommar", "typ": "bakgrund", "ikon": "🌼", "namn": "Midsommaräng", "pris": 70, "steg": 0,
     "bg": "linear-gradient(160deg,#b3e5fc,#c5e1a5 60%,#8bc34a)", "fg": "#1b5e20", "deko": "🌼"},
    {"id": "mid_eff", "hogtid": "midsommar", "typ": "effekt", "ikon": "🦋", "namn": "Fjärilar", "pris": 100, "steg": 0, "partikel": "🦋"},
    {"id": "sol_hatt", "hogtid": "sommarlov", "typ": "hatt", "ikon": "👒", "namn": "Solhatt", "pris": 40, "steg": 0},
    {"id": "sol_hatt2", "hogtid": "sommarlov", "typ": "hatt", "ikon": "😎", "namn": "Sommarbrillor", "pris": 50, "steg": 0},
    {"id": "sol_bg", "hogtid": "sommarlov", "typ": "bakgrund", "ikon": "🏖️", "namn": "Stranden", "pris": 70, "steg": 0,
     "bg": "linear-gradient(180deg,#81d4fa,#4fc3f7 55%,#ffe082 56%,#ffca28)", "fg": "#0d47a1", "deko": "🏖️"},
    {"id": "sol_eff", "hogtid": "sommarlov", "typ": "effekt", "ikon": "🍦", "namn": "Glassregn", "pris": 100, "steg": 0, "partikel": "🍦"},
    {"id": "hal_hatt", "hogtid": "halloween", "typ": "hatt", "ikon": "🎃", "namn": "Pumpahuvud", "pris": 40, "steg": 0},
    {"id": "hal_bg", "hogtid": "halloween", "typ": "bakgrund", "ikon": "🕸️", "namn": "Spökhuset", "pris": 70, "steg": 0,
     "bg": "linear-gradient(160deg,#4a148c,#ff6f00)", "fg": "#fff", "deko": "🦇"},
    {"id": "hal_eff", "hogtid": "halloween", "typ": "effekt", "ikon": "👻", "namn": "Spöken", "pris": 100, "steg": 0, "partikel": "👻"},
    {"id": "luc_hatt", "hogtid": "lucia", "typ": "hatt", "ikon": "🕯️", "namn": "Luciakrona", "pris": 40, "steg": 0},
    {"id": "luc_bg", "hogtid": "lucia", "typ": "bakgrund", "ikon": "🌙", "namn": "Luciamorgon", "pris": 70, "steg": 0,
     "bg": "linear-gradient(160deg,#283593,#ffb74d)", "fg": "#fff", "deko": "⭐"},
    {"id": "luc_eff", "hogtid": "lucia", "typ": "effekt", "ikon": "✨", "namn": "Ljussken", "pris": 100, "steg": 0, "glod": "ljus"},
    {"id": "jul_hatt", "hogtid": "jul", "typ": "hatt", "ikon": "🎅", "namn": "Tomte", "pris": 40, "steg": 0},
    {"id": "jul_hatt2", "hogtid": "jul", "typ": "hatt", "ikon": "🦌", "namn": "Renhorn", "pris": 60, "steg": 0},
    {"id": "jul_bg", "hogtid": "jul", "typ": "bakgrund", "ikon": "🎄", "namn": "Julnatt", "pris": 70, "steg": 0,
     "bg": "linear-gradient(160deg,#1b5e20,#b71c1c)", "fg": "#fff", "deko": "🎄"},
    {"id": "jul_eff", "hogtid": "jul", "typ": "effekt", "ikon": "❄️", "namn": "Snöfall", "pris": 100, "steg": 0, "partikel": "❄️"},
    {"id": "ny_hatt", "hogtid": "nyar", "typ": "hatt", "ikon": "🎉", "namn": "Partyhatt", "pris": 40, "steg": 0},
    {"id": "ny_bg", "hogtid": "nyar", "typ": "bakgrund", "ikon": "🎆", "namn": "Fyrverkeri", "pris": 70, "steg": 0,
     "bg": "radial-gradient(circle at 50% 30%,#3949ab,#0d0d2b 70%)", "fg": "#fff", "deko": "🎆"},
    {"id": "ny_eff", "hogtid": "nyar", "typ": "effekt", "ikon": "🎊", "namn": "Konfetti", "pris": 100, "steg": 0, "partikel": "🎊"},
]
SKOLAVSLUTNING: dict[int, str] = {}  # t.ex. {2027: "2027-06-11"} om skolan slutar en annan dag än fredag v.24
# Saker som BARA finns i paket (säljs inte styckvis)
PAKET_SAKER = [
    {"id": "x_julstjarna", "typ": "hatt", "ikon": "🌟", "namn": "Julstjärna"},
    {"id": "x_juleff", "typ": "effekt", "ikon": "🎁", "namn": "Klappregn", "partikel": "🎁"},
    {"id": "x_hexhatt", "typ": "hatt", "ikon": "🦇", "namn": "Fladdermus"},
    {"id": "x_haleff", "typ": "effekt", "ikon": "🕷️", "namn": "Spindlar", "partikel": "🕷️"},
    {"id": "x_paskhatt", "typ": "hatt", "ikon": "🐰", "namn": "Påskharen"},
    {"id": "x_paskbg", "typ": "bakgrund", "ikon": "🧺", "namn": "Äggjakten", "bg": "linear-gradient(160deg,#e1f5fe,#f8bbd0,#fff59d)", "fg": "#6a1b9a", "deko": "🧺"},
    {"id": "x_midhatt", "typ": "hatt", "ikon": "🍓", "namn": "Jordgubbshatt"},
    {"id": "x_mideff", "typ": "effekt", "ikon": "🐸", "namn": "Små grodorna", "partikel": "🐸"},
    {"id": "x_solhatt", "typ": "hatt", "ikon": "🏄", "namn": "Surfare"},
    {"id": "x_soleff", "typ": "effekt", "ikon": "🌞", "namn": "Solstrålar", "glod": "sol"},
    {"id": "x_luchatt", "typ": "hatt", "ikon": "🌟", "namn": "Stjärngosse"},
    {"id": "x_luceff", "typ": "effekt", "ikon": "🍪", "namn": "Pepparkaksregn", "partikel": "🍪"},
    {"id": "x_nyhatt", "typ": "hatt", "ikon": "🥳", "namn": "Festhatt"},
    {"id": "x_nyeff", "typ": "effekt", "ikon": "🎇", "namn": "Tomtebloss", "partikel": "🎇"},
    {"id": "x_hjhatt", "typ": "hatt", "ikon": "💘", "namn": "Amors pil"},
    {"id": "x_hjeff", "typ": "effekt", "ikon": "😍", "namn": "Kärleksglöd", "glod": "karlek"},
    {"id": "x_rymdeff", "typ": "effekt", "ikon": "🌠", "namn": "Stjärnstoft", "partikel": "🌠"},
    {"id": "x_rymdhatt", "typ": "hatt", "ikon": "👨‍🚀", "namn": "Rymdhjälm"},
    {"id": "x_guldhatt", "typ": "hatt", "ikon": "🔱", "namn": "Solkronan"},
    {"id": "x_guldbg", "typ": "bakgrund", "ikon": "🏛️", "namn": "Legendernas hall", "bg": "radial-gradient(circle at 50% 30%,#fff59d,#ffb300 50%,#6d4c41)", "fg": "#3e2723", "deko": "🏆"},
    {"id": "x_guldeff", "typ": "effekt", "ikon": "💫", "namn": "Legendglöd", "glod": "legend"},
]
# Husdjur som bara finns i paket
PAKET_DJUR = ["⛄", "🎃", "🐣", "🍓", "🍭", "🕯️", "🚀", "❤️", "👽", "🐲"]
# Paketen. hogtid = finns bara runt högtiden, annars alltid (steg = hur stort djuret måste vara)
PAKET = [
    {"id": "p_start", "namn": "Startpaketet", "ikon": "🎒", "pris": 120, "steg": 0, "saker": ["keps", "k_kyckling", "bubblor"]},
    {"id": "p_jul", "namn": "Julpaketet", "ikon": "🎄", "hogtid": "jul", "pris": 600, "steg": 0, "djur": "⛄", "saker": ["x_julstjarna", "x_juleff", "jul_bg"]},
    {"id": "p_halloween", "namn": "Skräckpaketet", "ikon": "🎃", "hogtid": "halloween", "pris": 600, "steg": 0, "djur": "🎃", "saker": ["x_hexhatt", "x_haleff", "hal_bg"]},
    {"id": "p_pask", "namn": "Påskpaketet", "ikon": "🐣", "hogtid": "pask", "pris": 600, "steg": 0, "djur": "🐣", "saker": ["x_paskhatt", "x_paskbg", "pask_eff"]},
    {"id": "p_midsommar", "namn": "Midsommarpaketet", "ikon": "🍓", "hogtid": "midsommar", "pris": 600, "steg": 0, "djur": "🍓", "saker": ["x_midhatt", "x_mideff", "mid_bg"]},
    {"id": "p_sommarlov", "namn": "Sommarlovspaketet", "ikon": "🍭", "hogtid": "sommarlov", "pris": 600, "steg": 0, "djur": "🍭", "saker": ["x_solhatt", "x_soleff", "sol_bg"]},
    {"id": "p_lucia", "namn": "Luciapaketet", "ikon": "🕯️", "hogtid": "lucia", "pris": 500, "steg": 0, "djur": "🕯️", "saker": ["x_luchatt", "x_luceff", "luc_bg"]},
    {"id": "p_nyar", "namn": "Nyårspaketet", "ikon": "🚀", "hogtid": "nyar", "pris": 600, "steg": 0, "djur": "🚀", "saker": ["x_nyhatt", "x_nyeff", "ny_bg"]},
    {"id": "p_hjartan", "namn": "Kärlekspaketet", "ikon": "❤️", "hogtid": "alla_hjartans", "pris": 500, "steg": 0, "djur": "❤️", "saker": ["x_hjhatt", "x_hjeff", "hj_bg"]},
    {"id": "p_rymd", "namn": "Rymdpaketet", "ikon": "👽", "pris": 1500, "steg": 2, "djur": "👽", "saker": ["x_rymdhatt", "x_rymdeff", "rymd", "k_robot"]},
    {"id": "p_legend", "namn": "Legendpaketet", "ikon": "🐲", "pris": 5000, "steg": 4, "djur": "🐲", "saker": ["x_guldhatt", "x_guldbg", "x_guldeff", "k_drake"]},
]
HOGTID_FORE = 14  # säsongssakerna finns att köpa så många dagar före högtiden


def _pask(ar: int) -> date:
    """Påskdagen (gregoriansk beräkning)."""
    a, b, c = ar % 19, ar // 100, ar % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    man = (h + l - 7 * m + 114) // 31
    dag = ((h + l - 7 * m + 114) % 31) + 1
    return date(ar, man, dag)


def hogtider(ar: int) -> list[dict]:
    """Högtiderna ett år: dagen (som räknas bakåt 2 veckor) och sista dagen sakerna går att köpa."""
    pask = _pask(ar)
    midsommar = next(date(ar, 6, d) for d in range(19, 26) if date(ar, 6, d).weekday() == 4)
    # Skolavslutningen: fredagen i vecka 24 om inget annat är angivet (justera i SKOLAVSLUTNING)
    sommarlov = date.fromisoformat(SKOLAVSLUTNING[ar]) if ar in SKOLAVSLUTNING else date.fromisocalendar(ar, 24, 5)
    lista = [
        ("alla_hjartans", "Alla hjärtans dag", "💖", date(ar, 2, 14), date(ar, 2, 14)),
        ("pask", "Påsk", "🐣", pask - timedelta(days=1), pask + timedelta(days=1)),
        ("sommarlov", "Sommarlov", "☀️", sommarlov, sommarlov + timedelta(days=7)),
        ("midsommar", "Midsommar", "🌼", midsommar, midsommar + timedelta(days=1)),
        ("halloween", "Halloween", "🎃", date(ar, 10, 31), date(ar, 10, 31)),
        ("lucia", "Lucia", "🕯️", date(ar, 12, 13), date(ar, 12, 13)),
        ("jul", "Jul", "🎄", date(ar, 12, 24), date(ar, 12, 26)),
        ("nyar", "Nyår", "🎆", date(ar, 12, 31), date(ar + 1, 1, 1)),
    ]
    return [{"id": i, "namn": n, "ikon": ik, "dag": d.isoformat(), "start": (d - timedelta(days=HOGTID_FORE)).isoformat(),
             "slut": s.isoformat()} for i, n, ik, d, s in lista]


def aktiva_hogtider(dag: date | None = None) -> list[dict]:
    dag = dag or dt_util.now().date()
    iso = dag.isoformat()
    return [h for ar in (dag.year - 1, dag.year) for h in hogtider(ar) if h["start"] <= iso <= h["slut"]]


def nasta_hogtid(dag: date | None = None) -> dict | None:
    dag = dag or dt_util.now().date()
    iso = dag.isoformat()
    kommande = sorted((h for ar in (dag.year, dag.year + 1) for h in hogtider(ar) if h["start"] > iso), key=lambda h: h["start"])
    return kommande[0] if kommande else None


def butik_lista() -> list[dict]:
    """Butikens saker med om de går att köpa just nu."""
    aktiva = {h["id"]: h for h in aktiva_hogtider()}
    return [{**x, "kan_kopas": not x.get("hogtid") or x["hogtid"] in aktiva,
             "slutar": aktiva[x["hogtid"]]["slut"] if x.get("hogtid") in aktiva else None} for x in DJURBUTIK] + [
        {**x, "pris": 0, "steg": 0, "bara_paket": True, "kan_kopas": False} for x in PAKET_SAKER] + [
        {**x, "kan_kopas": True} for x in RUM_SAKER] + [
        {**x, "pris": 0, "steg": 0, "bara_paket": True, "kalla": "pass", "kan_kopas": False} for x in PASS_SAKER] + [
        {**b["sak"], "pris": 0, "steg": 0, "bara_paket": True, "kalla": "boss", "kan_kopas": False} for b in BOSSAR]


def _sak(sak_id: str) -> dict | None:
    alla = DJURBUTIK + PAKET_SAKER + RUM_SAKER + PASS_SAKER + [b["sak"] for b in BOSSAR]
    return next((x for x in alla if x["id"] == sak_id), None)


def paket_lista(data: dict) -> list[dict]:
    """Paketen som syns nu: alltid-paket + högtidspaket under sin säsong."""
    aktiva = {h["id"]: h for h in aktiva_hogtider()}
    d = _m(data).get("djur") or {}
    agt, djur_agda = set(d.get("agt", [])), set(d.get("agda_djur", []))
    ut = []
    for p in PAKET:
        if p.get("hogtid") and p["hogtid"] not in aktiva:
            continue
        # vad det hade kostat styckvis (paketsakerna värderas eftersom de inte säljs separat)
        varde = sum((_sak(x) or {}).get("pris") or (900 if p["steg"] >= 4 else 250) for x in p["saker"])
        varde += (3000 if p["steg"] >= 4 else 800) if p.get("djur") else 0
        ut.append({**p, "varde": max(varde, p["pris"] + 100),
                   "slutar": aktiva[p["hogtid"]]["slut"] if p.get("hogtid") else None,
                   "kopt": (not p.get("djur") or p["djur"] in djur_agda) and all(x in agt for x in p["saker"])})
    return ut


def kop_paket(data: dict, paket_id: str) -> None:
    m = _m(data)
    d = m.get("djur")
    p = next((x for x in paket_lista(data) if x["id"] == paket_id), None)
    if not d or not p:
        raise ValueError("Paketet finns inte just nu.")
    if p["kopt"]:
        raise ValueError("Du har redan allt i paketet.")
    if _djur_steg(data) < p["steg"]:
        raise ValueError(f"{d['namn']} måste bli {DJUR_STEG[p['steg']][1]} först.")
    if m.get("saldo", 0) < p["pris"]:
        raise ValueError(f"Du behöver {p['pris']} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -p["pris"], f"📦 Köpte {p['namn']} {p['ikon']}", None, "📦")
    agt = d.setdefault("agt", [])
    pa = d.setdefault("pa", {})
    for x in p["saker"]:
        if x not in agt:
            agt.append(x)
        sak = _sak(x)
        if sak:
            pa[sak["typ"]] = x  # ta på allt direkt
    if p.get("djur"):
        agda = d.setdefault("agda_djur", [])
        if p["djur"] not in agda:
            agda.append(p["djur"])
        d["art"] = p["djur"]
DJUR_STEG = [(0, "Ägg"), (30, "Bebis"), (150, "Liten"), (400, "Stor"), (800, "Jätte"), (1500, "Legend")]


def aktiv(data: dict, dag: str | None = None) -> None:
    """Barnet har gjort läxarbete en dag: räkna sviten och ge svitbonus."""
    m = _m(data)
    idag = dt_util.now().date().isoformat()
    dag = (dag or idag)[:10]
    if dag == idag and dag not in m["ovningsdagar"]:
        _anvand_skydd(data, dag)
    if dag not in m["ovningsdagar"]:
        m["ovningsdagar"].append(dag)
        m["ovningsdagar"].sort()
        del m["ovningsdagar"][:-400]
    n = _streak(m["ovningsdagar"], date.fromisoformat(dag))
    r = m["raknare"]
    r["basta_streak"] = max(r.get("basta_streak", 0), _streak(m["ovningsdagar"]), n)
    if n >= 2:
        ge(data, min(P_STREAK_MAX, n), f"🔥 {n} dagar i rad!", f"streak:{dag}", "🔥")
    if n >= 7 and n % 7 == 0 and m.get("skydd", 0) < SKYDD_MAX:
        if ge(data, 0, f"🛡️ Du fick ett svitskydd för {n} dagar i rad!", f"skydd:{dag}", "🛡️"):
            m["skydd"] = m.get("skydd", 0) + 1
    kolla_utmaning(data)


def _skydd_lucka(m: dict, idag: str) -> tuple[list[str], int]:
    """Missade dagar mellan senaste aktiva dag och idag, och sviten som slutade då."""
    d = date.fromisoformat(idag) - timedelta(days=1)
    lucka = []
    s = set(m["ovningsdagar"])
    while d.isoformat() not in s and len(lucka) <= SKYDD_MAX:
        lucka.append(d.isoformat())
        d -= timedelta(days=1)
    if not lucka or len(lucka) > m.get("skydd", 0):
        return [], 0
    return lucka, _streak(m["ovningsdagar"], d)


def _anvand_skydd(data: dict, idag: str) -> None:
    """Svitskyddet räddar sviten när barnet kommer tillbaka efter en eller två missade dagar."""
    m = _m(data)
    lucka, forra = _skydd_lucka(m, idag)
    if not lucka or forra < 2:
        return
    m["ovningsdagar"].extend(lucka)
    m["ovningsdagar"].sort()
    m.setdefault("skyddade", []).extend(lucka)
    del m["skyddade"][:-60]
    m["skydd"] -= len(lucka)
    ge(data, 0, f"🛡️ Svitskyddet räddade din svit på {forra} dagar!", f"skyddat:{idag}", "🛡️")


# ---------- dagens utmaning ----------


def utmaning(data: dict, dag: str | None = None) -> list[dict]:
    """Dagens utmaning: upp till 3 mål som passar barnets läxor just idag."""
    dag = dag or dt_util.now().date().isoformat()
    glosor = [g for a in data.get("amnen", []) for g in a.get("glosor", [])]
    spelbara = [g for g in glosor if sum(1 for p in g.get("par", []) if len(p) > 1 and str(p[1]).strip()) >= 4]
    mal = []
    for u in data.get("uppdrag", []):
        if u.get("typ") == "hogl":
            d = next((x for x in u.get("dagar", []) if x["datum"] == dag), None)
            if d and not any(x["id"] == "hogl" for x in mal):
                mal.append({"id": "hogl", "ikon": "🗣️", "text": "Läs högt", "klar": d.get("status") in ("ok", "vantar")})
    oppna = [f for f in data.get("forhor", []) if not f.get("klart") or f["klart"][:10] == dag]
    if oppna:
        mal.append({"id": "forhor", "ikon": "📋", "text": "Gör förhöret", "klar": any((f.get("klart") or "")[:10] == dag for f in oppna)})
    prov = [u for u in data.get("uppdrag", []) if u.get("typ") == "prov" and (u.get("datum") or "") > dag and (not u.get("klart") or dag in u.get("studiedagar", []))]
    if prov:
        mal.append({"id": "prov", "ikon": "📝", "text": "Plugga inför provet", "klar": any(dag in u.get("studiedagar", []) for u in prov)})
    if glosor:
        mal.append({"id": "glosor", "ikon": "✏️", "text": "Öva på glosor", "klar": any(dag in g.get("ovat_dagar", []) for g in glosor)})
    if spelbara:
        mal.append({"id": "rekord", "ikon": "⚡", "text": f"Spela Glosrekord ({REKORD_MIN}+ rätt)", "klar": any(dag in g.get("rekord_dagar", []) for g in spelbara)})
    mal = mal[:3]
    return mal if len(mal) >= 2 else []


def kolla_utmaning(data: dict) -> None:
    dag = dt_util.now().date().isoformat()
    mal = utmaning(data, dag)
    if mal and all(x["klar"] for x in mal):
        if ge(data, P_UTMANING, "🎯 Dagens utmaning klar!", f"utmaning:{dag}", "🎯"):
            _rakna(data, "utmaningar")


# ---------- glosrekord ----------


def rekord(data: dict, g: dict, poang: int) -> bool:
    """Ett avslutat Glosrekord-spel. Returnerar True vid nytt personligt rekord."""
    dag = dt_util.now().date().isoformat()
    poang = max(0, min(80, int(poang)))
    gammalt = g.get("rekord", {}).get("poang", 0)
    nytt = poang > gammalt
    if nytt:
        g["rekord"] = {"poang": poang, "dag": dag}
    if poang >= REKORD_MIN:
        rd = g.setdefault("rekord_dagar", [])
        if dag not in rd:
            rd.append(dag)
            del rd[:-60]
        if nytt and gammalt:
            ge(data, P_REKORD, f"⚡ Nytt rekord i {g['namn']}: {poang}!", f"rekord:{g['id']}:{dag}", "⚡")
        aktiv(data, dag)
    r = _m(data)["raknare"]
    r["rekord_max"] = max(r.get("rekord_max", 0), poang)
    kolla_medaljer(data)
    return nytt


# ---------- husdjuret ----------


def djur(data: dict) -> dict | None:
    m = _m(data)
    d = m.get("djur")
    if not d:
        return None
    intj = m.get("intjanat", 0)
    steg = max(i for i, (grans, _n) in enumerate(DJUR_STEG) if intj >= grans)
    nasta = DJUR_STEG[steg + 1][0] if steg + 1 < len(DJUR_STEG) else None
    dagar = sorted(m["ovningsdagar"])
    idag = dt_util.now().date()
    sedan = (idag - date.fromisoformat(dagar[-1])).days if dagar else 99
    humor = "glad" if sedan == 0 else "nojd" if sedan == 1 else "hungrig" if sedan == 2 else "ledsen"
    return {**d, "steg": steg, "steg_namn": DJUR_STEG[steg][1], "nasta": nasta, "intjanat": intj,
            "humor": humor, "sedan": sedan, "form": djur_form(data, steg)}


def kolla_medaljer(data: dict) -> None:
    m = _m(data)
    r = dict(m["raknare"])
    r["streak"] = max(r.get("basta_streak", 0), _streak(m["ovningsdagar"]))
    for mid, ikon, namn, _besk, rak, grans in MEDALJER:
        if mid not in m["medaljer"] and r.get(rak, 0) >= grans:
            m["medaljer"][mid] = dt_util.now().date().isoformat()
            ge(data, P_MEDALJ, f"Ny medalj: {namn}", f"medalj:{mid}", ikon)


def niva(intjanat: int) -> dict:
    i = intjanat // NIVA_STEG
    namn = NIVAER[i] if i < len(NIVAER) else f"Legend {i - len(NIVAER) + 2}"
    return {"niva": i + 1, "namn": namn, "kvar": NIVA_STEG - intjanat % NIVA_STEG, "procent": intjanat % NIVA_STEG}


def sammanfattning(data: dict) -> dict:
    m = _m(data)
    mandag = (dt_util.now().date() - timedelta(days=dt_util.now().weekday())).isoformat()
    veckan = sum(x["p"] for x in m["logg"] if x["p"] > 0 and x["tid"][:10] >= mandag)
    return {
        "intjanat": m.get("intjanat", 0),
        "saldo": m.get("saldo", 0),
        "veckan": veckan,
        "niva": niva(m.get("intjanat", 0)),
        "medaljer": m["medaljer"],
        "streak": _streak(m["ovningsdagar"]),
        "streak_idag": dt_util.now().date().isoformat() in m["ovningsdagar"],
        "streak_max": P_STREAK_MAX,
        "skydd": m.get("skydd", 0),
        "skydd_max": SKYDD_MAX,
        "skydd_raddar": (_skydd_lucka(m, dt_util.now().date().isoformat())[1]
                         if dt_util.now().date().isoformat() not in m["ovningsdagar"] else 0),
        "utmaning": utmaning(data),
        "utmaning_p": P_UTMANING,
        "djur": djur(data),
    }


# ---------- händelser ----------


def _senaste_ankomst(veckodag: int, idag: date) -> date:
    return idag - timedelta(days=(idag.weekday() - veckodag) % 7)


def lagt_in(data: dict, amne_id: str, typ: str, glosor: dict | None = None) -> None:
    """Barnet har lagt in glosor/sidor i ett ämne. Matchar mot läxschemat."""
    idag = dt_util.now().date()
    for s in data.get("schema", []):
        if s.get("amne") != amne_id or s.get("typ") != typ:
            continue
        ankomst = _senaste_ankomst(int(s["kommer"]), idag)
        sen = (idag - ankomst).days
        nyckel = f"lagt_in:{s['id']}:{ankomst.isoformat()}"
        if sen <= 1:
            if ge(data, P_I_TID, f"Lade in {s['namn']} i tid", nyckel, "⏰"):
                _rakna(data, "i_tid")
                _m(data)["nycklar"].append(f"itid:{s['id']}:{ankomst.isoformat()}")
        elif sen <= 3:
            ge(data, P_SENT, f"Lade in {s['namn']}", nyckel, "📥")
        aktiv(data)
        # Förhörsdag från schemat fylls i automatiskt på nya glosor.
        if glosor is not None and not glosor.get("forhor") and s.get("forhor") is not None:
            d = ankomst + timedelta(days=(int(s["forhor"]) - ankomst.weekday()) % 7 or 7)
            if d >= idag:
                glosor["forhor"] = d.isoformat()
    kolla_medaljer(data)


def ovat(data: dict, g: dict, ratt: int, av: int, dag: str | None = None, hela: bool = True) -> None:
    """hela = False när barnet bara övade på några ord (svåra ord). Då räknas sviten men inga övningsmeriter,
    annars lönar det sig att göra fel med flit och sedan öva på ett enda ord."""
    """Övning på glosor. dag = när det gjordes (förälder kan registrera övning på papper i efterhand)."""
    m = _m(data)
    idag = date.fromisoformat(dag) if dag else dt_util.now().date()
    dag = idag.isoformat()
    ovade = g.setdefault("ovat_dagar", [])
    if dag not in ovade:
        ovade.append(dag)
        ovade.sort()
        del ovade[:-60]
    aktiv(data, dag)
    if not hela:
        kolla_medaljer(data)
        return
    _rakna(data, "ovningar")
    r = m["raknare"]
    for n in range(1, 4):  # max 3 övningar per glosläxa och dag ger meriter
        if ge(data, P_OVNING, f"Övade på {g['namn']}", f"ova:{g['id']}:{dag}:{n}", "✏️"):
            if av and ratt == av:
                ge(data, P_OVNING_ALLA_RATT, "Alla rätt på övningen", f"ova_alla:{g['id']}:{dag}:{n}", "✅")
            break
    if g.get("forhor"):
        try:
            dagar = (date.fromisoformat(g["forhor"]) - idag).days
        except ValueError:
            dagar = -1
        if dagar >= 1:
            tidiga = g.setdefault("tidiga_dagar", [])
            if dag not in tidiga:
                tidiga.append(dag)
            r["tidig_max"] = max(r.get("tidig_max", 0), len(tidiga))
        if dagar >= 2:
            ge(data, P_TIDIGT, f"Övade i god tid före förhöret ({g['namn']})", f"tidig:{g['id']}:{dag}", "🐦")
    kolla_medaljer(data)


def _annat_den_dagen(data: dict, dag: str, utom_gid: str) -> bool:
    """Gjorde barnet något annat i Skolan den dagen (så att sviten ska stå kvar)?"""
    for a in data.get("amnen", []):
        for g in a.get("glosor", []):
            if g["id"] != utom_gid and dag in g.get("ovat_dagar", []):
                return True
    if any((f.get("klart") or "")[:10] == dag for f in data.get("forhor", [])):
        return True
    for u in data.get("uppdrag", []):
        if (u.get("klart") or "")[:10] == dag or dag in u.get("studiedagar", []):
            return True
        if any(d.get("datum") == dag and d.get("status") == "ok" for d in u.get("dagar", [])):
            return True
    return False


def angra_ovning(data: dict, g: dict, dag: str) -> int:
    """Förälder bockar ur en övningsdag: ta bort dagen och dra tillbaka meriterna den gav."""
    m = _m(data)
    if dag not in g.get("ovat_dagar", []):
        raise ValueError("Den dagen är inte registrerad.")
    g["ovat_dagar"].remove(dag)
    if dag in g.get("tidiga_dagar", []):
        g["tidiga_dagar"].remove(dag)
    belopp = {f"tidig:{g['id']}:{dag}": P_TIDIGT}
    for n in range(1, 4):
        belopp[f"ova:{g['id']}:{dag}:{n}"] = P_OVNING
        belopp[f"ova_alla:{g['id']}:{dag}:{n}"] = P_OVNING_ALLA_RATT
    if not _annat_den_dagen(data, dag, g["id"]) and dag in m["ovningsdagar"]:
        belopp[f"streak:{dag}"] = min(P_STREAK_MAX, _streak(m["ovningsdagar"], date.fromisoformat(dag)))
        m["ovningsdagar"].remove(dag)
    summa = 0
    for nyckel, p in belopp.items():
        if nyckel in m["nycklar"]:
            m["nycklar"].remove(nyckel)
            summa += p
    r = m["raknare"]
    r["ovningar"] = max(0, r.get("ovningar", 0) - 1)
    if summa:
        m["logg"].append({"tid": dt_util.now().isoformat(timespec="minutes"), "p": -summa,
                          "orsak": f"Borttagen övning på {g['namn']} ({dag})", "ikon": "↩️"})
        m["intjanat"] = max(0, m.get("intjanat", 0) - summa)
        m["saldo"] = m.get("saldo", 0) - summa
    return summa


def forhor_klart(data: dict, f: dict) -> None:
    aktiv(data, f.get("klart"))
    ratt = sum(1 for x in f["svar"] if x["ratt"])
    n = len(f["fragor"])
    if ratt:
        ge(data, ratt * P_FORHOR_RATT, f"Förhör {f['namn']}: {ratt} av {n} rätt", f"forhor:{f['id']}", "📋")
    if n and ratt == n:
        ge(data, P_FORHOR_ALLA, "Alla rätt på förhöret!", f"forhor_alla:{f['id']}", "🎯")
        _rakna(data, "full_pott")
    if not f.get("manuell") and (f.get("klart") or "")[:10] == (f.get("skapad") or "")[:10]:
        if ge(data, P_FORHOR_DIREKT, "Gjorde förhöret direkt", f"forhor_direkt:{f['id']}", "⚡"):
            _rakna(data, "forhor_direkt")
    kolla_medaljer(data)


def vantande(data: dict) -> list[dict]:
    """Läxor enligt schemat som kom idag eller igår och inte är inlagda än (ger full merit)."""
    idag = dt_util.now().date()
    nycklar = set(_m(data)["nycklar"])
    ut = []
    for s in data.get("schema", []):
        ankomst = _senaste_ankomst(int(s["kommer"]), idag)
        if ankomst.isoformat() < s.get("fran", SCHEMA_START):
            continue
        if (idag - ankomst).days <= 1 and f"lagt_in:{s['id']}:{ankomst.isoformat()}" not in nycklar:
            ut.append({**s, "idag": ankomst == idag})
    return ut


def forslag(data: dict) -> list[str]:
    """Saker barnet kan göra nu för att få meriter, viktigast först."""
    idag = dt_util.now().date()
    dag = idag.isoformat()
    m = _m(data)
    ut: list[str] = []
    for s in vantande(data):
        ut.append(f"Lägg in {s['namn']} i Skolan: +{P_I_TID} ⭐")
    for u in data.get("uppdrag", []):
        if u.get("klart"):
            continue
        if u["typ"] == "hogl":
            d = next((x for x in u.get("dagar", []) if x["datum"] == dag), None)
            if d and d.get("status") not in ("ok", "vantar"):
                ut.append(f"Läs högt ur {u['namn']} för mamma eller pappa idag: +{P_HOGL_DAG} ⭐")
        elif u["typ"] == "skriv" and not u.get("vantar") and u["datum"] >= dag:
            ut.append(f"Gör {u['namn']} senast {VECKODAGAR[date.fromisoformat(u['datum']).weekday()]}: +{P_SKRIV_I_TID} ⭐")
    for u in sorted(data.get("uppdrag", []), key=lambda x: x["datum"]):
        if u.get("klart") or u["datum"] < dag or not u.get("sidor") or u["typ"] in ("hogl", "skriv"):
            continue
        p = P_LAS_I_TID if u["typ"] == "las" else P_PROV_KLART
        if u.get("allt_last"):
            ut.append(f"Gör kontrollfrågorna för {u['namn']}: +{p} ⭐")
        else:
            ut.append(f"Läs vidare i {u['namn']} ({u.get('lasta', 0)}/{len(u['sidor'])} sidor), klart senast {u['datum'][5:]}: +{p} ⭐")
    for f in data.get("forhor", []):
        if f.get("status") != "klart":
            ut.append(f"Gör förhöret {f['namn']}: upp till +{len(f['fragor']) * P_FORHOR_RATT + P_FORHOR_ALLA} ⭐")
    kommande = []
    for a in data.get("amnen", []):
        for g in a.get("glosor", []):
            try:
                dagar = (date.fromisoformat(g["forhor"]) - idag).days if g.get("forhor") else None
            except ValueError:
                dagar = None
            if dagar is not None and 0 <= dagar <= 7:
                kommande.append((dagar, g))
    for dagar, g in sorted(kommande, key=lambda x: x[0]):
        ovat_idag = f"ova:{g['id']}:{dag}:1" in m["nycklar"]
        if dagar == 0:
            continue
        if dagar == 1:
            ut.append(f"Förhör imorgon i {g['namn']}! Öva en sista gång: +{P_OVNING} ⭐")
        elif not ovat_idag:
            ut.append(f"Öva på {g['namn']} nu: +{P_OVNING + P_TIDIGT} ⭐ (bonus för att du är i god tid)")
    streak = _streak(m["ovningsdagar"])
    if dag not in m["ovningsdagar"]:
        if streak:
            ut.insert(0, f"Rädda din 🔥 {streak}-dagars svit: gör något i Skolan idag! +{min(P_STREAK_MAX, streak + 1)} ⭐")
        else:
            ut.append("Starta en 🔥 svit: gör något i Skolan varje dag, bonusen växer för varje dag!")
    r = dict(m["raknare"])
    r["streak"] = streak
    for mid, ikon, namn, _b, rak, grans in MEDALJER:
        if mid not in m["medaljer"] and 0 < grans - r.get(rak, 0) <= 3 and rak in ("ovningar", "streak", "i_tid"):
            kvar = grans - r.get(rak, 0)
            vad = {"ovningar": "övning", "streak": "dag i rad", "i_tid": "läxa i tid"}[rak]
            ut.append(f"{kvar} {vad}{'ar' if kvar > 1 and rak != 'streak' else ''} kvar till medaljen {ikon} {namn} (+{P_MEDALJ} ⭐)")
            break
    if not ut:
        ut.append(f"Öva på några glosor: +{P_OVNING} ⭐ per övning")
    return ut



def uppdrag_klart(data: dict, u: dict) -> None:
    idag = (u.get("klart") or dt_util.now().isoformat())[:10]  # dagen det blev klart (kan vara registrerat i efterhand)
    if u["typ"] != "hogl":
        aktiv(data, idag)
    i_tid = idag <= u["datum"] if u["typ"] in ("las", "skriv") else idag < u["datum"]
    if u["typ"] == "las":
        if ge(data, P_LAS_I_TID if i_tid else P_LAS_SENT, f"Läste {u['namn']}{' i tid' if i_tid else ''}", f"las:{u['id']}", "📖"):
            _rakna(data, "las_klara")
    elif u["typ"] == "skriv":
        ge(data, P_SKRIV_I_TID if i_tid else P_SKRIV_SENT, f"Gjorde {u['namn']}{' i tid' if i_tid else ''}", f"skriv:{u['id']}", "✍️")
    elif i_tid:
        if ge(data, P_PROV_KLART, f"Pluggat klart inför provet {u['namn']}", f"prov:{u['id']}", "📝"):
            _rakna(data, "prov_klara")
    kolla_medaljer(data)


def prov_studiedag(data: dict, u: dict, dag: str | None = None) -> None:
    idag = date.fromisoformat(dag) if dag else dt_util.now().date()
    try:
        dagar = (date.fromisoformat(u["datum"]) - idag).days
    except ValueError:
        return
    if dagar >= 1:
        dagar_lista = u.setdefault("studiedagar", [])
        if idag.isoformat() not in dagar_lista:
            dagar_lista.append(idag.isoformat())
            aktiv(data, idag.isoformat())
            if len(dagar_lista) <= 5:
                ge(data, P_PROV_DAG, f"Pluggade inför provet {u['namn']}", f"provdag:{u['id']}:{idag.isoformat()}", "📚")
                kolla_medaljer(data)


def registrerat(data: dict, u: dict) -> None:
    idag = dt_util.now().date()
    try:
        dagar = (date.fromisoformat(u["datum"]) - idag).days
    except ValueError:
        return
    if u["typ"] == "prov" and dagar >= 3:
        ge(data, P_REG_PROV, f"Registrerade provet {u['namn']} i god tid", f"regprov:{u['id']}", "🗓️")



# ---------- rättvis topplista ----------
# Veckopoäng = medel av
#  A) andel av veckans egna läxor som klarats i tid (förhör räknas med sitt resultat)
#  B) insats: meriter hittills i veckan jämfört med snittet av de 4 senaste veckorna vid samma tidpunkt
#     (lika = 50, dubbelt = 100). Snittet gör att det inte lönar sig att slappa en vecka för att "förbättra" nästa.
#     Den som håller 100 % läxor i tid vecka efter vecka får full insats (100), så 100 % är aldrig en nackdel.
# + bonus: 5 poäng per perfekt vecka i rad (100 % i tid), max 20. Därför kan poängen bli över 100.

PERFEKT_BONUS = 5
PERFEKT_MAX = 20


def _andel_vecka(data: dict, mandag: date, tom: date) -> tuple[int | None, int, float]:
    """Andel (0–100) av läxorna som skulle vara klara mellan mandag och tom, antal, antal klarade."""
    nycklar = set(_m(data)["nycklar"])
    m_iso, t_iso = mandag.isoformat(), tom.isoformat()
    sondag = mandag + timedelta(days=6)
    poster: list[float] = []
    for s in data.get("schema", []):
        ankomst = mandag + timedelta(days=int(s["kommer"]))
        if ankomst > tom or ankomst.isoformat() < s.get("fran", SCHEMA_START):
            continue
        klar = f"itid:{s['id']}:{ankomst.isoformat()}" in nycklar
        if klar or (tom - ankomst).days > 1:  # räknas först när tiden har gått ut
            poster.append(1.0 if klar else 0.0)
    for u in data.get("uppdrag", []):
        if u.get("typ") == "hogl":  # högläsning: varje dag räknas för sig
            for d in u.get("dagar", []):
                if m_iso <= d["datum"] <= t_iso:
                    if d.get("status") == "ok":
                        poster.append(1.0)
                    elif d["datum"] < t_iso:
                        poster.append(0.0)
            continue
        klart = (u.get("klart") or "")[:10]
        if klart and m_iso <= klart <= sondag.isoformat() and klart <= t_iso:
            poster.append(1.0 if klart <= u["datum"] else 0.5)
        elif (not klart or klart > t_iso) and m_iso <= u["datum"] < t_iso:
            poster.append(0.0)
    # Förhör som föräldrar skickar är övning, inte egna läxor. De ger meriter men räknas inte här.
    for a in data.get("amnen", []):
        for g in a.get("glosor", []):
            d = g.get("forhor") or ""
            if m_iso <= d <= t_iso:
                poster.append(1.0 if any(x < d for x in g.get("tidiga_dagar", [])) else 0.0)
    if not poster:
        return None, 0, 0.0
    return round(100 * sum(poster) / len(poster)), len(poster), round(sum(poster), 1)


def veckoresultat(data: dict) -> dict:
    nu = dt_util.now()
    idag = nu.date()
    mandag = idag - timedelta(days=idag.weekday())
    m = _m(data)

    andel, antal, klara = _andel_vecka(data, mandag, idag)

    # Perfekta veckor i rad före den här (veckor utan läxor bryter inte svit).
    perfekta = 0
    for k in range(1, 13):
        mv = mandag - timedelta(days=7 * k)
        a, n, _ = _andel_vecka(data, mv, mv + timedelta(days=6))
        if a is None:
            continue
        if a == 100:
            perfekta += 1
        else:
            break

    def _summa(fran, till) -> int:
        f, t = fran.isoformat(timespec="minutes"), till.isoformat(timespec="minutes")
        return sum(x["p"] for x in m["logg"] if x["p"] > 0 and f <= x["tid"] <= t)

    start = nu.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=idag.weekday())
    denna = _summa(start, nu)
    tidigare = [_summa(start - timedelta(days=7 * k), nu - timedelta(days=7 * k)) for k in range(1, 5)]
    snitt = round(sum(tidigare) / 4)
    if denna == 0 and snitt == 0:
        insats = None
    else:
        insats = round(min(100, 50 * denna / max(snitt, 10)))
    if andel == 100 and perfekta >= 1:
        insats = 100  # håller man 100 % är det full insats

    delar = [x for x in (andel, insats) if x is not None]
    bonus = min(PERFEKT_MAX, PERFEKT_BONUS * perfekta) if andel == 100 else 0
    return {
        "poang": (round(sum(delar) / len(delar)) if delar else 0) + bonus,
        "andel": andel,
        "antal": antal,
        "klara": klara,
        "forbattring": insats,
        "denna": denna,
        "forra": snitt,
        "perfekta": perfekta if andel == 100 else 0,
        "bonus": bonus,
    }



def schema_status(data: dict) -> list[dict]:
    """Veckans läxor enligt schemat och om de är gjorda (för föräldrarnas registrering)."""
    idag = dt_util.now().date()
    mandag = idag - timedelta(days=idag.weekday())
    nycklar = set(_m(data)["nycklar"])
    ut = []
    for s in data.get("schema", []):
        ankomst = mandag + timedelta(days=int(s["kommer"]))
        a = ankomst.isoformat()
        if a < s.get("fran", SCHEMA_START):
            continue
        if f"itid:{s['id']}:{a}" in nycklar:
            status = "i_tid"
        elif f"lagt_in:{s['id']}:{a}" in nycklar:
            status = "sent"
        elif ankomst > idag:
            status = "kommande"
        else:
            status = "ej"
        ut.append({"id": s["id"], "namn": s["namn"], "ankomst": a, "status": status})
    return ut


def manuell_schema(data: dict, schema_id: str, ankomst: str, i_tid: bool) -> None:
    s = next((x for x in data.get("schema", []) if x["id"] == schema_id), None)
    if not s:
        raise ValueError("Okänd läxa.")
    nyckel = f"lagt_in:{s['id']}:{ankomst}"
    if i_tid:
        if ge(data, P_I_TID, f"{s['namn']} gjord i tid (registrerad av förälder)", nyckel, "⏰"):
            _rakna(data, "i_tid")
        _m(data)["nycklar"].append(f"itid:{s['id']}:{ankomst}")
    else:
        ge(data, P_SENT, f"{s['namn']} gjord (registrerad av förälder)", nyckel, "📥")
    kolla_medaljer(data)


def hogl_ok(data: dict, u: dict, datum: str) -> None:
    """En dags högläsning är godkänd av en förälder."""
    aktiv(data, datum)
    ge(data, P_HOGL_DAG, f"Läste högt: {u['namn']} ({VECKODAGAR[date.fromisoformat(datum).weekday()]})", f"hogl:{u['id']}:{datum}", "🗣️")
    if u.get("dagar") and all(d.get("status") == "ok" for d in u["dagar"]):
        u["klart"] = max(d["datum"] for d in u["dagar"]) + "T18:00"
        if ge(data, P_HOGL_ALLA, f"Läst högt alla dagar: {u['namn']}!", f"hogl_alla:{u['id']}", "🌟"):
            _rakna(data, "las_klara")
    kolla_medaljer(data)


def _djur_steg(data: dict) -> int:
    intj = _m(data).get("intjanat", 0)
    return max(i for i, (grans, _n) in enumerate(DJUR_STEG) if intj >= grans)


def djur_valj(data: dict, art: str, namn: str) -> None:
    """Välj, döp om eller byt djur. Första djuret är gratis, att byta art kostar."""
    m = _m(data)
    d = m.get("djur")
    if art in PAKET_DJUR:
        if not d or art not in d.get("agda_djur", []):
            raise ValueError("Det djuret finns bara i ett paket.")
        d["art"] = art  # paketdjur man äger byter man till gratis
        if (namn or "").strip():
            d["namn"] = namn.strip()[:20]
        return
    if art not in DJUR:
        raise ValueError("Okänt djur.")
    namn = (namn or "").strip()[:20]
    if not d:
        m["djur"] = {"art": art, "namn": namn or "Kompis", "agt": [], "pa": {}, "gratis_byte": False}
        return
    if art != d["art"] and d.get("gratis_byte", True):
        # djur som fanns innan de 40 husdjuren kom får byta en gång gratis
        d["gratis_byte"] = False
        d["art"] = art
        ge(data, 0, f"🔄 Bytte till {art} (gratis)", None, "🎁")
    elif art != d["art"]:
        if m.get("saldo", 0) < P_BYT_DJUR:
            raise ValueError(f"Du behöver {P_BYT_DJUR} ⭐ för att byta djur.")
        ge(data, -P_BYT_DJUR, f"🔄 Bytte till {art}", None, "🛍️")
        d["art"] = art
    if namn:
        d["namn"] = namn


def djur_kop(data: dict, sak_id: str) -> None:
    m = _m(data)
    d = m.get("djur")
    sak = next((x for x in DJURBUTIK + RUM_SAKER if x["id"] == sak_id), None)
    if not d or not sak:
        raise ValueError("Det finns inte.")
    agt = d.setdefault("agt", [])
    if sak_id in agt:
        raise ValueError("Du har redan den.")
    if sak.get("hogtid") and sak["hogtid"] not in {h["id"] for h in aktiva_hogtider()}:
        raise ValueError("Den finns bara att köpa runt högtiden.")
    if _djur_steg(data) < sak["steg"]:
        raise ValueError(f"{d['namn']} måste bli {DJUR_STEG[sak['steg']][1]} först.")
    if m.get("saldo", 0) < sak["pris"]:
        raise ValueError(f"Du behöver {sak['pris']} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -sak["pris"], f"🛍️ Köpte {sak['namn']} {sak['ikon']} till {d['namn']}", None, "🛍️")
    agt.append(sak_id)
    if sak["typ"] == "rum":
        d.setdefault("rum", {})[sak["plats"]] = sak_id  # ställ in direkt
    else:
        d.setdefault("pa", {})[sak["typ"]] = sak_id  # ta på direkt


def djur_pa(data: dict, typ: str, sak_id: str | None) -> None:
    d = _m(data).get("djur")
    if d and typ == "variant":
        if sak_id and sak_id not in d.get("varianter", []):
            raise ValueError("Den har du inte.")
        d["variant"] = sak_id or None
        return
    if not d or typ not in ("hatt", "bakgrund", "effekt", "kompis"):
        raise ValueError("Det går inte.")
    pa = d.setdefault("pa", {})
    if not sak_id:
        pa.pop(typ, None)
        return
    if sak_id not in d.get("agt", []):
        raise ValueError("Du har inte köpt den.")
    pa[typ] = sak_id


# ---------- läxpasset (en bana med 30 nivåer varje månad) ----------
PASS_NIVAER = 30


def _pass_kostnad(n: int) -> int:
    """XP som krävs från nivå n-1 till nivå n."""
    return 40 + n


def _pass_xp(m: dict, poang: int) -> None:
    manad = dt_util.now().strftime("%Y-%m")
    p = m.setdefault("pass", {})
    if p.get("manad") != manad:
        p.clear()
        p.update({"manad": manad, "xp": 0, "hamtat": []})
    p["xp"] = p.get("xp", 0) + poang


# Saker som bara finns i läxpasset (roterar mellan månaderna)
PASS_SAKER = [
    {"id": "ps_trollstav", "typ": "hatt", "ikon": "🪄", "namn": "Trollstav"},
    {"id": "ps_nalle", "typ": "kompis", "ikon": "🧸", "namn": "Nallen"},
    {"id": "ps_neon", "typ": "bakgrund", "ikon": "🌃", "namn": "Neonstaden", "bg": "linear-gradient(160deg,#12002f,#ff00c8 60%,#00e5ff)", "fg": "#fff", "deko": "🕹️"},
    {"id": "ps_noter", "typ": "effekt", "ikon": "🎶", "namn": "Musikmoln", "partikel": "🎶"},
    {"id": "ps_ufo", "typ": "hatt", "ikon": "🛸", "namn": "UFO"},
    {"id": "ps_klover", "typ": "effekt", "ikon": "🍀", "namn": "Turklöver", "partikel": "🍀"},
    {"id": "ps_drom", "typ": "bakgrund", "ikon": "🌙", "namn": "Drömlandet", "bg": "linear-gradient(170deg,#1a237e,#7b1fa2 50%,#f8bbd0)", "fg": "#fff", "deko": "🌙"},
    {"id": "ps_gitarr", "typ": "hatt", "ikon": "🎸", "namn": "Rockgitarr"},
    {"id": "ps_valp", "typ": "kompis", "ikon": "🐕", "namn": "Valpen"},
    {"id": "ps_mane", "typ": "effekt", "ikon": "💫", "namn": "Stjärnsnurr", "partikel": "💫"},
    {"id": "ps_fjader", "typ": "hatt", "ikon": "🦚", "namn": "Påfågelfjäder"},
    {"id": "ps_hav", "typ": "bakgrund", "ikon": "🐋", "namn": "Djuphavet", "bg": "linear-gradient(180deg,#01579b,#002f6c 60%,#000)", "fg": "#fff", "deko": "🐋"},
    {"id": "ps_katt", "typ": "kompis", "ikon": "🐈", "namn": "Katten"},
    {"id": "ps_regn", "typ": "effekt", "ikon": "🌧️", "namn": "Mysregn", "partikel": "💧"},
    {"id": "ps_mossa", "typ": "hatt", "ikon": "🧢", "namn": "Passkeps"},
]
# Glänsande variant av husdjuret: belöningen på nivå 30 (en ny varje månad)
VARIANTER = [
    {"id": "v_guld", "namn": "Guldskimmer", "filter": "sepia(1) saturate(4) hue-rotate(5deg) brightness(1.1)"},
    {"id": "v_is", "namn": "Isskimmer", "filter": "hue-rotate(170deg) saturate(1.4) brightness(1.1)"},
    {"id": "v_lila", "namn": "Lilaskimmer", "filter": "hue-rotate(250deg) saturate(1.6)"},
    {"id": "v_rosa", "namn": "Rosaskimmer", "filter": "hue-rotate(300deg) saturate(1.5) brightness(1.05)"},
    {"id": "v_skugga", "namn": "Skuggskimmer", "filter": "grayscale(1) brightness(.55) contrast(1.3)"},
    {"id": "v_gron", "namn": "Djungelskimmer", "filter": "hue-rotate(90deg) saturate(1.5)"},
    {"id": "v_eld", "namn": "Eldskimmer", "filter": "hue-rotate(-30deg) saturate(2.2) brightness(1.05)"},
    {"id": "v_silver", "namn": "Silverskimmer", "filter": "grayscale(1) brightness(1.25) contrast(1.1)"},
    {"id": "v_hav", "namn": "Havsskimmer", "filter": "hue-rotate(140deg) saturate(1.8)"},
    {"id": "v_sol", "namn": "Solskimmer", "filter": "hue-rotate(30deg) saturate(2) brightness(1.15)"},
    {"id": "v_natt", "namn": "Nattskimmer", "filter": "invert(.85) hue-rotate(180deg)"},
    {"id": "v_regnbage", "namn": "Regnbågsskimmer", "filter": "hue-rotate(0deg) saturate(2)", "anim": True},
]


def _manad_index() -> int:
    nu = dt_util.now()
    return nu.year * 12 + nu.month


def pass_beloningar() -> list[dict]:
    """Belöningarna i månadens pass. Saker på nivå 5, 10, 15, 20, 25; variant på 30; stjärnor annars."""
    i = _manad_index()
    saker = [PASS_SAKER[(i * 5 + k) % len(PASS_SAKER)] for k in range(5)]
    variant = VARIANTER[i % len(VARIANTER)]
    ut = []
    for n in range(1, PASS_NIVAER + 1):
        if n % 5 == 0 and n < 30:
            x = saker[n // 5 - 1]
            ut.append({"niva": n, "typ": "sak", "sak": x["id"], "ikon": x["ikon"], "namn": x["namn"]})
        elif n == 30:
            ut.append({"niva": n, "typ": "variant", "sak": variant["id"], "ikon": "🌟", "namn": f"{variant['namn']} (glänsande husdjur)"})
        else:
            ut.append({"niva": n, "typ": "stjarnor", "antal": 15 + n * 2, "ikon": "⭐", "namn": f"{15 + n * 2} stjärnor"})
    return ut


def pass_status(data: dict) -> dict:
    m = _m(data)
    p = m.get("pass") or {}
    manad = dt_util.now().strftime("%Y-%m")
    xp = p.get("xp", 0) if p.get("manad") == manad else 0
    hamtat = p.get("hamtat", []) if p.get("manad") == manad else []
    niva, kvar_xp = 0, xp
    while niva < PASS_NIVAER and kvar_xp >= _pass_kostnad(niva + 1):
        kvar_xp -= _pass_kostnad(niva + 1)
        niva += 1
    nasta = _pass_kostnad(niva + 1) if niva < PASS_NIVAER else 0
    idag = dt_util.now().date()
    nasta_man = (idag.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"manad": manad, "xp": xp, "niva": niva, "xp_i_niva": kvar_xp, "xp_till_nasta": nasta,
            "hamtat": hamtat, "beloningar": pass_beloningar(), "dagar_kvar": (nasta_man - idag).days}


def hamta_pass(data: dict, niva: int) -> str:
    """Hämta belöningen på en nivå man har nått."""
    m = _m(data)
    st = pass_status(data)
    if niva < 1 or niva > st["niva"]:
        raise ValueError("Du har inte nått den nivån än.")
    if niva in st["hamtat"]:
        raise ValueError("Redan hämtad.")
    b = st["beloningar"][niva - 1]
    m["pass"].setdefault("hamtat", []).append(niva)
    d = m.get("djur")
    if b["typ"] == "stjarnor":
        ge(data, b["antal"], f"🎟️ Läxpasset nivå {niva}", None, "🎟️")
        return f"+{b['antal']} ⭐"
    if not d:
        ge(data, 100, f"🎟️ Läxpasset nivå {niva}", None, "🎟️")
        return "+100 ⭐ (välj ett husdjur för att få sakerna)"
    if b["typ"] == "variant":
        v = d.setdefault("varianter", [])
        if b["sak"] not in v:
            v.append(b["sak"])
        d["variant"] = b["sak"]
        _rakna(data, "pass_klara")
        kolla_medaljer(data)
        return f"🌟 {b['namn']}!"
    agt = d.setdefault("agt", [])
    if b["sak"] in agt:
        ge(data, 100, f"🎟️ Läxpasset nivå {niva} (hade redan {b['namn']})", None, "🎟️")
        return "+100 ⭐"
    agt.append(b["sak"])
    return f"{b['ikon']} {b['namn']}!"


# ---------- äventyrskartan: nivåer med monster, en världsboss var tionde nivå ----------
VARLDAR = [
    {"id": "skog", "namn": "Glosskogen", "ikon": "🌲", "farg": "#2e7d32", "monster": ["🐛", "🐌", "🦔", "🐝", "🕷️", "🦇", "🐍", "🦂", "🪲"]},
    {"id": "hav", "namn": "Bläckhavet", "ikon": "🌊", "farg": "#0277bd", "monster": ["🦀", "🐡", "🦐", "🪼", "🐚", "🦞", "🐊", "🦭", "🐋"]},
    {"id": "berg", "namn": "Trollberget", "ikon": "⛰️", "farg": "#6d4c41", "monster": ["🐺", "🦅", "🐗", "🦬", "🐐", "🦫", "🦡", "🦨", "🧌"]},
    {"id": "trask", "namn": "Sömnträsket", "ikon": "🌙", "farg": "#4527a0", "monster": ["🦟", "🪰", "🐀", "🦎", "🕸️", "🌫️", "🧛", "🦥", "🐊"]},
    {"id": "fabrik", "namn": "Robotfabriken", "ikon": "🏭", "farg": "#546e7a", "monster": ["⚙️", "🔩", "🔋", "📟", "🖨️", "💾", "🕹️", "📡", "🛸"]},
    {"id": "vulkan", "namn": "Drakvulkanen", "ikon": "🌋", "farg": "#bf360c", "monster": ["☄️", "🌶️", "🦂", "🐍", "🧨", "💣", "🌪️", "🦖", "🔥"]},
    {"id": "slott", "namn": "Spökslottet", "ikon": "🏚️", "farg": "#37474f", "monster": ["🕯️", "💀", "🧙", "🎃", "🪦", "👁️", "🦉", "🕸️", "🧟"]},
    {"id": "tid", "namn": "Tidshavet", "ikon": "⏳", "farg": "#00695c", "monster": ["⏰", "⌛", "🕰️", "⏱️", "📅", "🐠", "🪸", "🌀", "🐙"]},
]
BOSSAR = [  # världsbossar, en per värld (samma ordning som VARLDAR)
    {"id": "glosmonster", "svag": "natur", "svar": 0.85, "namn": "Glosmonstret", "ikon": "👾", "sak": {"id": "b_pixel", "typ": "hatt", "ikon": "👾", "namn": "Pixelmonster"}},
    {"id": "blackfisken", "svag": "blixt", "svar": 0.9, "namn": "Bläckbläckfisken", "ikon": "🦑", "sak": {"id": "b_black", "typ": "effekt", "ikon": "🖋️", "namn": "Bläckstänk", "partikel": "🖋️"}},
    {"id": "troll", "svag": "eld", "svar": 0.95, "namn": "Läxtrollet", "ikon": "👹", "sak": {"id": "b_troll", "typ": "hatt", "ikon": "👹", "namn": "Trollmask"}},
    {"id": "zombie", "svag": "natur", "svar": 1.0, "namn": "Sömnzombien", "ikon": "🧟", "sak": {"id": "b_zombie", "typ": "kompis", "ikon": "🧟", "namn": "Snälla zombien"}},
    {"id": "robot", "svag": "vatten", "svar": 1.0, "namn": "Robotkungen", "ikon": "🤖", "sak": {"id": "b_kugge", "typ": "effekt", "ikon": "⚙️", "namn": "Kugghjul", "partikel": "⚙️"}},
    {"id": "drake", "svag": "is", "svar": 1.05, "namn": "Glömskedraken", "ikon": "🐉", "sak": {"id": "b_drakfjall", "typ": "bakgrund", "ikon": "🏔️", "namn": "Drakberget", "bg": "linear-gradient(170deg,#263238,#b71c1c 70%,#ff6f00)", "fg": "#fff", "deko": "🐉"}},
    {"id": "spoke", "svag": "eld", "svar": 1.1, "namn": "Slarvspöket", "ikon": "👻", "sak": {"id": "b_spoke", "typ": "kompis", "ikon": "👻", "namn": "Lilla spöket"}},
    {"id": "haj", "svag": "blixt", "svar": 1.15, "namn": "Tidshajen", "ikon": "🦈", "sak": {"id": "b_haj", "typ": "hatt", "ikon": "🦈", "namn": "Hajfena"}},
]
NIVA_PER_VARLD = 10
BOSS_MAL_MIN, BOSS_MAL_MAX = 150, 700
BOSS_MAL_BAS = 100  # svit, dagens utmaning m.m. en vanlig vecka
BOSS_LAXA = {"glosor": 90, "bok": 45}  # ungefär vad en läxa i schemat ger en vecka man gör den ordentligt
BOSS_LAXA_ANNAN = 50
BOSS_ATTACK_TILLAGG = 1.15  # attackerna ger extra skada, så monstren har lite mer liv
EJ_SKADA = ("🎟️", "👾", "🗺️")  # belöningar gör ingen skada och ger ingen pass-XP
P_NIVA_STJARNA = 5  # meriter per stjärna när en nivå klaras
P_VARLDSBOSS = 50
ENERGI_MAX = 15


def _vecko_poang(data: dict) -> dict[str, int]:
    """Intjänade meriter (utan belöningar) per vecka, t.ex. {"2026-W46": 320}."""
    ut: dict[str, int] = {}
    for x in _m(data)["logg"]:
        if x["p"] > 0 and x.get("ikon") not in EJ_SKADA:
            ar, v, _ = date.fromisoformat(x["tid"][:10]).isocalendar()
            k = f"{ar}-W{v:02d}"
            ut[k] = ut.get(k, 0) + x["p"]
    return ut


def boss_mal(data: dict, dag: date | None = None) -> int | None:
    """Hur mycket ett barn brukar plugga en hel vecka (snitt av de senaste fyra hela veckorna). None utan historik."""
    dag = dag or dt_util.now().date()
    logg = _m(data)["logg"]
    if not logg:
        return None
    forsta = date.fromisoformat(logg[0]["tid"][:10])
    forsta_mandag = forsta - timedelta(days=forsta.weekday())
    if forsta.weekday() != 0:
        forsta_mandag += timedelta(days=7)  # första veckan var inte hel
    per = _vecko_poang(data)
    veckor = []
    mandag = dag - timedelta(days=dag.weekday())
    for i in range(1, 5):
        m = mandag - timedelta(days=7 * i)
        if m < forsta_mandag:
            break
        ar, v, _ = m.isocalendar()
        veckor.append(per.get(f"{ar}-W{v:02d}", 0))
    if not veckor:
        return None
    return int(sum(veckor) / len(veckor))


def boss_arbete(data: dict, dag: date | None = None) -> tuple[int, int, int]:
    """Veckans väntade läxmängd i meriter: (poäng, antal läxor, antal prov).
    Klara uppdrag räknas också, så att bossen inte blir svagare av att man gör dem."""
    dag = dag or dt_util.now().date()
    mandag = dag - timedelta(days=dag.weekday())
    sondag = mandag + timedelta(days=6)
    p, laxor, prov = BOSS_MAL_BAS, 0, 0
    for x in data.get("schema", []):
        if (mandag + timedelta(days=int(x.get("kommer", 0)))).isoformat() < x.get("fran", SCHEMA_START):
            continue
        p += BOSS_LAXA.get(x.get("typ"), BOSS_LAXA_ANNAN)
        laxor += 1
    for u in data.get("uppdrag", []):
        try:
            datum = date.fromisoformat((u.get("datum") or "")[:10])
        except ValueError:
            continue
        if u.get("typ") == "prov":
            # pluggdagar (upp till 5 dagar före provet) som hamnar i den här veckan
            dagar = sum(1 for i in range(1, 6) if mandag <= datum - timedelta(days=i) <= sondag)
            if dagar or mandag <= datum <= sondag:
                p += P_REG_PROV + P_PROV_DAG * dagar + (P_PROV_KLART if mandag <= datum <= sondag + timedelta(days=1) else 0)
                prov += 1
        elif mandag <= datum <= sondag:
            p += P_LAS_I_TID if u.get("typ") == "las" else P_SKRIV_I_TID
            laxor += 1
    return p, laxor, prov


def boss_mal_vecka(data: dict, dag: date | None = None) -> int:
    """Vad bossen räknar med från ett barn: hälften vana, hälften veckans läxmängd."""
    arbete = boss_arbete(data, dag)[0]
    vana = boss_mal(data, dag)
    mal = (vana + arbete) / 2 if vana is not None else arbete
    return int(min(BOSS_MAL_MAX, max(BOSS_MAL_MIN, mal)))




def niva_dagar(n: int) -> float:
    """Hur många dagars vanligt plugg en nivå motsvarar. Börjar kort och blir längre."""
    d = min(2.5, 0.6 + 0.04 * n)
    return min(5.0, d * 2.5) if n % NIVA_PER_VARLD == 0 else d


def niva_info(n: int) -> dict:
    """Monster, värld och svaghet för nivå n (1, 2, 3 …). Världarna går runt igen efter den sista."""
    vi = (n - 1) // NIVA_PER_VARLD
    v = VARLDAR[vi % len(VARLDAR)]
    varv = vi // len(VARLDAR)
    plats = (n - 1) % NIVA_PER_VARLD
    typer = [t for t in TYPER if t != "kraft"]
    if plats == NIVA_PER_VARLD - 1:
        b = BOSSAR[vi % len(BOSSAR)]
        mon = {"namn": b["namn"], "ikon": b["ikon"], "svag": b["svag"], "boss": True, "svar": b["svar"], "sak": b["sak"]}
    else:
        ik = v["monster"][plats % len(v["monster"])]
        mon = {"namn": f"Nivå {n}", "ikon": ik, "svag": typer[(n * 7 + vi) % len(typer)], "boss": False, "svar": 1.0}
    return {**mon, "niva": n, "varld": {**{k: v[k] for k in ("id", "namn", "ikon", "farg")}, "nr": vi + 1, "varv": varv}}


def niva_liv(data: dict, n: int) -> int:
    dag = boss_mal_vecka(data) / 7
    info = niva_info(n)
    return max(15, int(round(dag * niva_dagar(n) * info["svar"] * BOSS_ATTACK_TILLAGG)))


def _karta(data: dict) -> dict:
    m = _m(data)
    k = m.get("karta")
    if not k:
        k = m["karta"] = {"niva": 1, "skada": 0, "start": dt_util.now().isoformat(timespec="minutes"),
                          "hp": niva_liv(data, 1), "stjarnor": {}, "energi": 3, "energi_rest": 0, "super": ""}
    return k


def _klara_niva(data: dict, k: dict) -> None:
    n = k["niva"]
    info = niva_info(n)
    try:
        tid = (dt_util.now() - datetime.fromisoformat(k["start"])).total_seconds() / 86400
    except (ValueError, TypeError):
        tid = 99
    mal = niva_dagar(n)
    st = 3 if tid <= mal else 2 if tid <= mal * 1.6 else 1
    k["stjarnor"][str(n)] = max(st, k["stjarnor"].get(str(n), 0))
    ge(data, st * P_NIVA_STJARNA, f"🗺️ Nivå {n} klar! {'⭐' * st}", f"niva:{n}", "🗺️")
    if info["boss"]:
        ge(data, P_VARLDSBOSS, f"👾 Du besegrade {info['namn']}!", f"varldsboss:{n}", "👾")
        d = _m(data).get("djur")
        if d and info["sak"]["id"] not in d.setdefault("agt", []):
            d["agt"].append(info["sak"]["id"])
        _rakna(data, "bossar")
    _rakna(data, "nivaer")
    k.setdefault("klara", []).append({"niva": n, "stjarnor": st, "tid": dt_util.now().isoformat(timespec="minutes")})
    del k["klara"][:-20]
    k["niva"] = n + 1
    k["start"] = dt_util.now().isoformat(timespec="minutes")
    k["hp"] = niva_liv(data, n + 1)


def _karta_skada(data: dict, skada: int) -> None:
    """Lägg skada på nivån. Det som blir över går vidare till nästa nivå."""
    k = _karta(data)
    k["skada"] += int(skada)
    for _ in range(5):
        if k["skada"] < k["hp"]:
            break
        over = k["skada"] - k["hp"]
        _klara_niva(data, k)
        k["skada"] = min(over, k["hp"] - 1)
    kolla_medaljer(data)


def _karta_energi(data: dict, poang: int) -> None:
    k = _karta(data)
    rest = k.get("energi_rest", 0) + int(poang)
    k["energi"] = min(ENERGI_MAX, k.get("energi", 0) + rest // P_ENERGI)
    k["energi_rest"] = rest % P_ENERGI


def karta_status(data: dict) -> dict:
    k = _karta(data)
    n = k["niva"]
    info = niva_info(n)
    m = _m(data)
    agda = m.get("attacker", [])
    lista = []
    for at in ATTACKER:
        skada, svag = _attack_varde(data, at, info)
        lista.append({**at, "har": at["id"] in agda, "nu": skada, "svag": svag})
    vecka = "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])
    fran = max(1, n - 12)
    karta = [{**{x: niva_info(i)[x] for x in ("niva", "ikon", "namn", "boss", "varld")}, "stjarnor": k["stjarnor"].get(str(i), 0)}
             for i in range(fran, n + 6)]
    _, laxor, prov = boss_arbete(data)
    return {"niva": n, "hp": k["hp"], "skada": min(k["skada"], k["hp"]), "monster": info, "dagar": niva_dagar(n),
            "energi": k.get("energi", 0), "energi_max": ENERGI_MAX, "p_energi": P_ENERGI, "attacker": lista, "typer": TYPER,
            "super_anvand": k.get("super") == vecka, "senaste": k.get("senaste"), "karta": karta,
            "stjarnor_tot": sum(k["stjarnor"].values()), "klara": k.get("klara", [])[-3:], "laxor": laxor, "prov": prov}


def karta_kort(data: dict) -> dict:
    """Det syskon och vänner får se."""
    k = _karta(data)
    d = _m(data).get("djur") or {}
    return {"niva": k["niva"], "stjarnor": sum(k["stjarnor"].values()), "art": d.get("art"), "djur": d.get("namn"),
            "steg": d.get("steg", 0), "repriser": [repris(r) for r in k.get("repriser", [])[-3:]]}


def repris(r: dict) -> dict | None:
    """Gör om en sparad attack (egen, syskons eller väns) till det stridsscenen behöver.
    Monstret räknas fram från nivån här, så att en vän inte kan skicka in egen text eller kod."""
    try:
        at = next(x for x in ATTACKER if x["id"] == r.get("id"))
        niva = max(1, min(100000, int(r.get("niva") or 1)))
        hp = max(1, min(10**6, int(r.get("hp") or 1)))
        kvar = max(0, min(hp, int(r.get("kvar") or 0)))
        skada = max(0, min(10**6, int(r.get("skada") or 0)))
    except (StopIteration, TypeError, ValueError):
        return None
    mon = niva_info(niva)
    return {"id": at["id"], "ikon": at["ikon"], "namn": at["namn"], "typ": at["typ"], "niva": niva, "hp": hp, "kvar": kvar,
            "skada": skada, "svag": bool(r.get("svag")), "klar": bool(r.get("klar")), "tid": str(r.get("tid") or "")[:25],
            "mon": {"ikon": mon["ikon"], "namn": mon["namn"], "boss": mon["boss"], "varld": {"farg": mon["varld"]["farg"]}}}


# ---------- attacker mot monstren ----------
TYPER = {"eld": "🔥 Eld", "natur": "🍃 Natur", "blixt": "⚡ Blixt", "vatten": "🌊 Vatten", "is": "❄️ Is", "kraft": "💥 Kraft"}
ATTACKER = [
    {"id": "a_eld", "ikon": "🔥", "namn": "Eldspark", "typ": "eld", "pris": 60, "steg": 0, "energi": 1, "skada": 4,
     "info": "Snabb och billig."},
    {"id": "a_blad", "ikon": "🍃", "namn": "Bladvirvel", "typ": "natur", "pris": 90, "steg": 0, "energi": 1, "skada": 3,
     "info": "+3 skada om dagens utmaning är klar."},
    {"id": "a_blixt", "ikon": "⚡", "namn": "Blixt", "typ": "blixt", "pris": 120, "steg": 0, "energi": 1, "skada": 3,
     "info": "Dubbel skada om du har pluggat idag."},
    {"id": "a_vag", "ikon": "🌊", "namn": "Våg", "typ": "vatten", "pris": 150, "steg": 1, "energi": 2, "skada": 5,
     "info": "+1 skada per dag i din svit (högst +9)."},
    {"id": "a_is", "ikon": "❄️", "namn": "Isstorm", "typ": "is", "pris": 250, "steg": 1, "energi": 2, "skada": 10,
     "info": "Stark attack."},
    {"id": "a_super", "ikon": "💥", "namn": "Superattack", "typ": "kraft", "pris": 400, "steg": 2, "energi": 3, "skada": 30,
     "info": "Jättestark, men bara en gång per vecka."},
]
P_ENERGI = 25  # 1 energi per 25 intjänade meriter
SVAG_GANGER = 2  # monstret tar dubbel skada av sin svaghet


def _attack_varde(data: dict, at: dict, mon: dict) -> tuple[int, bool]:
    """Hur mycket skada attacken gör just nu, och om monstret är svagt mot den."""
    m = _m(data)
    idag = dt_util.now().date().isoformat()
    skada = at["skada"]
    if at["id"] == "a_blad" and f"utmaning:{idag}" in m["nycklar"]:
        skada += 3
    elif at["id"] == "a_blixt" and idag in m["ovningsdagar"]:
        skada *= 2
    elif at["id"] == "a_vag":
        skada += min(9, _streak(m["ovningsdagar"]))
    svag = mon.get("svag") == at["typ"]
    return skada * (SVAG_GANGER if svag else 1), svag


def attack_kop(data: dict, at_id: str) -> None:
    m = _m(data)
    d = m.get("djur")
    at = next((x for x in ATTACKER if x["id"] == at_id), None)
    if not d or not at:
        raise ValueError("Det finns inte.")
    agda = m.setdefault("attacker", [])
    if at_id in agda:
        raise ValueError("Den attacken kan du redan.")
    if _djur_steg(data) < at["steg"]:
        raise ValueError(f"{d['namn']} måste bli {DJUR_STEG[at['steg']][1]} först.")
    if m.get("saldo", 0) < at["pris"]:
        raise ValueError(f"Du behöver {at['pris']} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -at["pris"], f"⚔️ {d['namn']} lärde sig {at['namn']} {at['ikon']}", None, "🛍️")
    agda.append(at_id)


def attack(data: dict, at_id: str) -> dict:
    """Husdjuret anfaller nivåns monster. Kostar energi, ger extra skada."""
    m = _m(data)
    if not m.get("djur"):
        raise ValueError("Du behöver ett husdjur först.")
    at = next((x for x in ATTACKER if x["id"] == at_id), None)
    if not at or at_id not in m.get("attacker", []):
        raise ValueError("Den attacken kan ditt husdjur inte än.")
    k = _karta(data)
    vecka = "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])
    if at_id == "a_super" and k.get("super") == vecka:
        raise ValueError("Superattacken går bara att använda en gång per vecka.")
    if k.get("energi", 0) < at["energi"]:
        raise ValueError(f"Du behöver {at['energi']} ⚡ energi. Plugga mer så laddas den!")
    n = k["niva"]
    mon = niva_info(n)
    skada, svag = _attack_varde(data, at, mon)
    hp_fore, kvar_fore = k["hp"], max(0, k["hp"] - k["skada"])
    k["energi"] -= at["energi"]
    if at_id == "a_super":
        k["super"] = vecka
    k["senaste"] = {"id": at_id, "skada": skada, "svag": svag, "niva": n, "tid": dt_util.now().isoformat(timespec="seconds")}
    _rakna(data, "attacker")
    _karta_skada(data, skada)
    k["senaste"]["klar"] = k["niva"] > n
    k["repriser"] = (k.get("repriser", []) + [{"id": at_id, "niva": n, "hp": hp_fore, "kvar": kvar_fore, "skada": skada,
                                               "svag": svag, "klar": k["senaste"]["klar"], "tid": k["senaste"]["tid"]}])[-5:]
    return k["senaste"]


# ---------- husdjurets rum ----------
RUM_PLATSER = ["tapet", "golv", "sang", "lampa", "tavla", "vaxt", "leksak", "fonster"]
RUM_SAKER = [
    {"id": "r_tapet_bla", "typ": "rum", "plats": "tapet", "ikon": "🟦", "namn": "Blå tapet", "pris": 40, "steg": 0, "farg": "#90caf9"},
    {"id": "r_tapet_rosa", "typ": "rum", "plats": "tapet", "ikon": "🟪", "namn": "Rosa tapet", "pris": 40, "steg": 0, "farg": "#f8bbd0"},
    {"id": "r_tapet_gron", "typ": "rum", "plats": "tapet", "ikon": "🟩", "namn": "Grön tapet", "pris": 40, "steg": 0, "farg": "#a5d6a7"},
    {"id": "r_tapet_rymd", "typ": "rum", "plats": "tapet", "ikon": "🌌", "namn": "Rymdtapet", "pris": 200, "steg": 1, "farg": "linear-gradient(#0d1b4c,#311b92)"},
    {"id": "r_tapet_regnbage", "typ": "rum", "plats": "tapet", "ikon": "🌈", "namn": "Regnbågstapet", "pris": 350, "steg": 2, "farg": "linear-gradient(90deg,#ef9a9a,#ffe082,#a5d6a7,#90caf9,#ce93d8)"},
    {"id": "r_golv_tra", "typ": "rum", "plats": "golv", "ikon": "🟫", "namn": "Trägolv", "pris": 40, "steg": 0, "farg": "#a1887f"},
    {"id": "r_golv_matta", "typ": "rum", "plats": "golv", "ikon": "🧶", "namn": "Mjuk matta", "pris": 80, "steg": 0, "farg": "#ef9a9a"},
    {"id": "r_golv_gras", "typ": "rum", "plats": "golv", "ikon": "🌱", "namn": "Gräsmatta", "pris": 120, "steg": 1, "farg": "#7cb342"},
    {"id": "r_golv_guld", "typ": "rum", "plats": "golv", "ikon": "🟨", "namn": "Guldgolv", "pris": 600, "steg": 3, "farg": "#ffd54f"},
    {"id": "r_sang_enkel", "typ": "rum", "plats": "sang", "ikon": "🛏️", "namn": "Säng", "pris": 80, "steg": 0},
    {"id": "r_sang_soffa", "typ": "rum", "plats": "sang", "ikon": "🛋️", "namn": "Soffa", "pris": 150, "steg": 1},
    {"id": "r_sang_talt", "typ": "rum", "plats": "sang", "ikon": "⛺", "namn": "Tält", "pris": 200, "steg": 1},
    {"id": "r_sang_slott", "typ": "rum", "plats": "sang", "ikon": "🏰", "namn": "Slottssäng", "pris": 700, "steg": 3},
    {"id": "r_lampa_lampa", "typ": "rum", "plats": "lampa", "ikon": "💡", "namn": "Lampa", "pris": 50, "steg": 0},
    {"id": "r_lampa_ljus", "typ": "rum", "plats": "lampa", "ikon": "🕯️", "namn": "Ljus", "pris": 60, "steg": 0},
    {"id": "r_lampa_lykta", "typ": "rum", "plats": "lampa", "ikon": "🏮", "namn": "Lykta", "pris": 120, "steg": 1},
    {"id": "r_lampa_diskokula", "typ": "rum", "plats": "lampa", "ikon": "🪩", "namn": "Discokula", "pris": 400, "steg": 2},
    {"id": "r_tavla_bild", "typ": "rum", "plats": "tavla", "ikon": "🖼️", "namn": "Tavla", "pris": 60, "steg": 0},
    {"id": "r_tavla_karta", "typ": "rum", "plats": "tavla", "ikon": "🗺️", "namn": "Skattkarta", "pris": 120, "steg": 1},
    {"id": "r_tavla_klocka", "typ": "rum", "plats": "tavla", "ikon": "🕰️", "namn": "Klocka", "pris": 150, "steg": 1},
    {"id": "r_tavla_pokal", "typ": "rum", "plats": "tavla", "ikon": "🏆", "namn": "Pokalhylla", "pris": 500, "steg": 3},
    {"id": "r_vaxt_kaktus", "typ": "rum", "plats": "vaxt", "ikon": "🌵", "namn": "Kaktus", "pris": 40, "steg": 0},
    {"id": "r_vaxt_blomma", "typ": "rum", "plats": "vaxt", "ikon": "🪴", "namn": "Krukväxt", "pris": 50, "steg": 0},
    {"id": "r_vaxt_solros", "typ": "rum", "plats": "vaxt", "ikon": "🌻", "namn": "Solros", "pris": 80, "steg": 0},
    {"id": "r_vaxt_trad", "typ": "rum", "plats": "vaxt", "ikon": "🌳", "namn": "Inomhusträd", "pris": 300, "steg": 2},
    {"id": "r_leksak_boll", "typ": "rum", "plats": "leksak", "ikon": "⚽", "namn": "Boll", "pris": 40, "steg": 0},
    {"id": "r_leksak_nalle", "typ": "rum", "plats": "leksak", "ikon": "🧸", "namn": "Nalle", "pris": 60, "steg": 0},
    {"id": "r_leksak_spel", "typ": "rum", "plats": "leksak", "ikon": "🎮", "namn": "Spelkonsol", "pris": 250, "steg": 1},
    {"id": "r_leksak_robot", "typ": "rum", "plats": "leksak", "ikon": "🤖", "namn": "Leksaksrobot", "pris": 300, "steg": 2},
    {"id": "r_leksak_raket", "typ": "rum", "plats": "leksak", "ikon": "🚀", "namn": "Leksaksraket", "pris": 450, "steg": 2},
    {"id": "r_fonster_sol", "typ": "rum", "plats": "fonster", "ikon": "🌤️", "namn": "Solfönster", "pris": 60, "steg": 0},
    {"id": "r_fonster_natt", "typ": "rum", "plats": "fonster", "ikon": "🌙", "namn": "Nattfönster", "pris": 80, "steg": 0},
    {"id": "r_fonster_snö", "typ": "rum", "plats": "fonster", "ikon": "🌨️", "namn": "Snöfönster", "pris": 100, "steg": 1},
    {"id": "r_fonster_hav", "typ": "rum", "plats": "fonster", "ikon": "🏝️", "namn": "Havsutsikt", "pris": 250, "steg": 2},
    {"id": "r_fonster_rymd", "typ": "rum", "plats": "fonster", "ikon": "🪐", "namn": "Rymdutsikt", "pris": 500, "steg": 3},
]


def rum_stall(data: dict, plats: str, sak_id: str | None) -> None:
    d = _m(data).get("djur")
    if not d or plats not in RUM_PLATSER:
        raise ValueError("Det går inte.")
    rum = d.setdefault("rum", {})
    if not sak_id:
        rum.pop(plats, None)
        return
    sak = _sak(sak_id)
    if not sak or sak.get("plats") != plats or sak_id not in d.get("agt", []):
        raise ValueError("Du har inte köpt den.")
    rum[plats] = sak_id


# ---------- utvecklingsformer och titlar ----------
FORMER = [  # (id, ikon, namn, titel, räknare, gräns)
    ("blixt", "⚡", "Blixtform", "⚡ Glosblixten", "rekord_max", 20),
    ("visdom", "📚", "Visdomsform", "📚 Bokmalen", "las_klara", 3),
    ("prick", "🎯", "Prickform", "🎯 Prickskytten", "full_pott", 3),
    ("flit", "✨", "Flitform", "✨ Flitmyran", "ovningar", 40),
    ("boss", "⚔️", "Hjälteform", "⚔️ Bossjägaren", "bossar", 2),
]


def _former(data: dict) -> list[tuple]:
    r = _m(data)["raknare"]
    return [f for f in FORMER if r.get(f[4], 0) >= f[5]]


def djur_form(data: dict, steg: int) -> dict | None:
    """Djuret utvecklas efter vanor (från storleken Liten). Den vana där barnet kommit längst vinner."""
    if steg < 2:
        return None
    r = _m(data)["raknare"]
    upplasta = sorted(_former(data), key=lambda f: -(r.get(f[4], 0) / f[5]))
    if not upplasta:
        return None
    f = upplasta[0]
    return {"id": f[0], "ikon": f[1], "namn": f[2]}


def titel(data: dict) -> str | None:
    """Titeln som syns vid namnet på topplistan."""
    m = _m(data)
    st = djur(data) or {}
    if st.get("steg", 0) >= 5:
        return "👑 Legenden"
    if pass_status(data)["niva"] >= PASS_NIVAER:
        return "🎟️ Månadens mästare"
    if _streak(m["ovningsdagar"]) >= 30:
        return "🔥 Eldsjälen"
    r = m["raknare"]
    f = sorted(_former(data), key=lambda f: -(r.get(f[4], 0) / f[5]))
    return f[0][3] if f else None
