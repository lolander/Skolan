"""Meriter, medaljer och nivåer för Skolan.

Meriter delas ut på servern (inte i webbläsaren) när barnet själv:
- lägger in en läxa i tid enligt läxschemat som föräldern har satt upp,
- övar på glosor (extra i god tid före förhöret),
- gör förhör på distans.
Allt sparas i barnets data.json under "meriter". Varje utdelning har en nyckel
så att samma sak aldrig ger meriter två gånger.
"""

from __future__ import annotations

import math
import random
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
    ("provstjarna", "🌟", "Provstjärna", "Toppresultat (minst 90 %) på ett prov", "prov_topp", 1),
    ("provgeni", "🧠", "Provgeni", "Toppresultat på 5 prov", "prov_topp", 5),
    ("utmanare", "🎯", "Utmanare", "Klarat dagens utmaning", "utmaningar", 1),
    ("utmaningskung", "👑", "Utmaningskung", "Klarat dagens utmaning 10 gånger", "utmaningar", 10),
    ("snabbfinger", "⚡", "Snabbfinger", "Fått 20 rätt i Glosrekord", "rekord_max", 20),
    ("raket", "🚀", "Raket", "Fått 35 rätt i Glosrekord", "rekord_max", 35),
    ("passmastare", "🎟️", "Passmästare", "Klarat alla 30 nivåer i läxpasset", "pass_klara", 1),
    ("bossjagare", "⚔️", "Bossjägare", "Besegrat en världsboss på kartan", "bossar", 1),
    ("aventyrare", "🗺️", "Äventyrare", "Klarat 10 nivåer på kartan", "nivaer", 10),
    ("kartans_hjalte", "🏆", "Kartans hjälte", "Klarat 50 nivåer på kartan", "nivaer", 50),
    ("arenamastare", "🏟️", "Arenamästare", "Vunnit 10 strider i arenan", "arena_vinster", 10),
    ("lagspelare", "🏳️", "Lagspelare", "Besegrat 3 lagbossar med ditt lag", "lagbossar", 3),
    ("lagkapten", "🤝", "Lagkapten", "Vunnit 5 lagstrider", "lagstrid_vinster", 5),
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
            _djur_laka(data, int(poang))
            _djur_xp(data, int(poang))
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


# Provresultat som en förälder lägger in. Belöningen beror på andelen rätt (eller betyget).
PROV_BETYG = {"A": 1.0, "B": 0.9, "C": 0.8, "D": 0.7, "E": 0.6, "F": 0.0}
PROV_BELONING = [(0.9, 50, "Toppresultat"), (0.75, 30, "Mycket bra resultat"), (0.6, 15, "Bra resultat")]


def prov_andel(res: dict) -> float | None:
    if res.get("max"):
        return max(0.0, min(1.0, res["poang"] / res["max"]))
    return PROV_BETYG.get(res.get("betyg"))


def prov_beloning(andel: float | None) -> tuple[int, str]:
    for grans, p, text in PROV_BELONING:
        if andel is not None and andel >= grans - 1e-9:
            return p, text
    return 0, ""


def prov_resultat(data: dict, u: dict, res: dict | None) -> int:
    """Sätt (eller ta bort, res=None) provresultatet. Ändras resultatet justeras meriterna. Returnerar nya meriter."""
    gammal = u.get("resultat") or {}
    fore = int(gammal.get("p", 0))
    if res is None:
        u.pop("resultat", None)
        if fore:
            ge(data, -fore, f"Provresultatet för {u['namn']} togs bort", None, "➖")
        return -fore
    andel = prov_andel(res)
    p, text = prov_beloning(andel)
    res["p"] = p
    res["andel"] = round(andel, 3) if andel is not None else None
    res["topp"] = gammal.get("topp", False)
    u["resultat"] = res
    diff = p - fore
    if diff > 0:
        ge(data, diff, f"{text} på provet {u['namn']}!" if not fore else f"Bättre provresultat på {u['namn']}", None, "📝")
    elif diff < 0:
        ge(data, diff, f"Ändrat provresultat på {u['namn']}", None, "➖")
    if andel is not None and andel >= 0.9 - 1e-9 and not res["topp"]:
        res["topp"] = True
        _rakna(data, "prov_topp")
        kolla_medaljer(data)
    return diff


# Barnet fotar en bok (sidorna blir e-bok). Lön efter att en förälder har kollat fotona.
FOTO_SIDOR_PER_STJARNA = 2  # 1 ⭐ per 2 nya sidor
FOTO_MAX_PER_BOK = 50
FOTO_MIN_SIDOR = 10  # så många nya sidor behövs för att be om lön


def foto_obetalda(b: dict) -> list[str]:
    betalda = set(b.get("foto_betalda", []))
    return [f for f in b.get("barn_sidor", []) if f in b.get("sidor", []) and f not in betalda]


def foto_pris(b: dict, n: int | None = None) -> int:
    n = len(foto_obetalda(b)) if n is None else n
    return max(0, min(n // FOTO_SIDOR_PER_STJARNA, FOTO_MAX_PER_BOK - int(b.get("foto_lon", 0))))


def foto_lon(data: dict, b: dict) -> int:
    nya = foto_obetalda(b)
    p = foto_pris(b, len(nya))
    b.setdefault("foto_betalda", []).extend(nya)
    b["foto_lon"] = int(b.get("foto_lon", 0)) + p
    if p:
        ge(data, p, f"Fotade {len(nya)} sidor i {b['namn']}", None, "📸")
        _rakna(data, "foto_sidor", len(nya))
        kolla_medaljer(data)
    return p


P_TIPS = 1  # ett tips i en övning (nästa bokstav) kostar så här många meriter


P_FORSOK = 1  # varje försök efter de 2 gratis på samma ord i en övning
FORSOK_GRATIS = 2


def kop_tips(data: dict, typ: str = "tips") -> None:
    """Köp ett tips (💡) eller ett extra försök (🔁) i en övning."""
    m = _m(data)
    pris, ikon = (P_FORSOK, "🔁") if typ == "forsok" else (P_TIPS, "💡")
    if m.get("saldo", 0) < pris:
        raise ValueError(f"Inte rätt. Du behöver {pris} ⭐ för att kolla fler fel svar. Tryck Visa svaret." if typ == "forsok"
                         else f"Du behöver {pris} ⭐ för ett tips.")
    nu = dt_util.now().isoformat(timespec="minutes")
    sista = m["logg"][-1] if m["logg"] else None
    text = (lambda n: f"🔁 {n} extra försök i övningar") if typ == "forsok" else (lambda n: f"💡 {n} tips i övningar")
    if sista and sista.get("ikon") == ikon and sista["tid"][:13] == nu[:13]:  # samla samma timme på en rad
        sista["p"] -= pris
        sista["n"] = sista.get("n", 1) + 1
        sista["orsak"] = text(sista["n"])
        m["saldo"] = m.get("saldo", 0) - pris
    else:
        ge(data, -pris, "🔁 Extra försök i en övning" if typ == "forsok" else "💡 Tips i en övning", None, ikon)


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
EJ_SKADA = ("🎟️", "👾", "🗺️", "🏳️")  # belöningar gör ingen skada och ger ingen pass-XP
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
    return {**mon, "niva": n, "slag": VARLD_SLAG.get(v["id"], "kraft"),
            "varld": {**{k: v[k] for k in ("id", "namn", "ikon", "farg")}, "nr": vi + 1, "varv": varv}}


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
            "liv": djur_liv(data)[0], "liv_max": djur_liv(data)[1], "p_liv": P_LIV,
            "drycker": [{**x, "antal": k.get("drycker", {}).get(x["id"], 0)} for x in DRYCKER], "dryck_max": DRYCK_MAX,
            "energi": k.get("energi", 0), "energi_max": ENERGI_MAX, "p_energi": P_ENERGI,
            "energi_pris": ENERGI_PRIS, "energi_kop_kvar": ENERGI_KOP_DAG - _energi_kopt(k), "attacker": lista, "typer": TYPER,
            "super_anvand": k.get("super") == vecka, "senaste": k.get("senaste"), "karta": karta,
            "stjarnor_tot": sum(k["stjarnor"].values()), "klara": k.get("klara", [])[-3:], "laxor": laxor, "prov": prov,
            "forsvar": skold_status(data), "def_halv": DEF_HALV, "slag": info.get("slag", "kraft")}


def karta_kort(data: dict) -> dict:
    """Det syskon och vänner får se."""
    k = _karta(data)
    d = _m(data).get("djur") or {}
    return {"niva": k["niva"], "stjarnor": sum(k["stjarnor"].values()), "art": d.get("art"), "djur": d.get("namn"),
            "steg": _djur_steg(data), "repriser": [repris(r) for r in k.get("repriser", [])[-3:]],
            "djur_niva": djur_niva(data)["niva"], "cp": djur_cp(data), "def": djur_def(data), "traning": traning(data),
            "skold": (skold(data) or {}).get("ikon", ""), "arena_poang": k.get("arena_poang", 0),
            "arena_hist": k.get("arena_hist", [])[-3:]}


def repris(r: dict) -> dict | None:
    """Gör om en sparad attack (egen, syskons eller väns) till det stridsscenen behöver.
    Monstret räknas fram från nivån här, så att en vän inte kan skicka in egen text eller kod."""
    try:
        at = next(x for x in ATTACKER if x["id"] == r.get("id"))
        niva = max(1, min(100000, int(r.get("niva") or 1)))
        hp = max(1, min(10**6, int(r.get("hp") or 1)))
        kvar = max(0, min(hp, int(r.get("kvar") or 0)))
        skada = max(0, min(10**6, int(r.get("skada") or 0)))
        liv_max = max(1, min(1000, int(r.get("liv_max") or 0))) if r.get("liv_max") else None
        liv_fore = max(0, min(liv_max, int(r.get("liv_fore") or 0))) if liv_max else None
        mot = max(0, min(1000, int(r.get("mot") or 0)))
        tillbaka = max(0, min(10**6, int(r.get("tillbaka") or 0)))
    except (StopIteration, TypeError, ValueError):
        return None
    mon = niva_info(niva)
    return {"id": at["id"], "ikon": at["ikon"], "namn": at["namn"], "typ": at["typ"], "niva": niva, "hp": hp, "kvar": kvar,
            "skada": skada, "svag": bool(r.get("svag")), "klar": bool(r.get("klar")), "tid": str(r.get("tid") or "")[:25],
            "mot": mot, "miss": bool(r.get("miss")), "liv_fore": liv_fore, "liv_max": liv_max,
            "skydd": r.get("skydd") if r.get("skydd") in SKYDD else "", "tillbaka": tillbaka,
            "skold": r.get("skold") if r.get("skold") in SKOLD else "",
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

# ---------- husdjurets liv ----------
LIV_MAX = [40, 50, 70, 90, 110, 140]  # per steg: Ägg, Bebis, Liten, Stor, Jätte, Legend
P_LIV = 3  # 1 liv tillbaka per 3 intjänade meriter
MISS_CHANS = 0.15  # monstret missar ibland


DJUR_NIVA_MAX = 50
LIV_PER_NIVA = 4  # mer liv för varje nivå husdjuret går upp
KRAFT_PER_NIVA = 0.02  # +2 % skada per nivå


def _xp_for(n: int) -> int:
    """XP som behövs för att nå nivå n (1 → 0, 2 → 40, 10 → 1800, 50 → 49000)."""
    return 20 * n * (n - 1)


def _djur_xp(data: dict, poang: int) -> None:
    """Husdjuret växer av allt barnet pluggar. Första gången räknas allt som redan tjänats in."""
    k = _karta(data)
    if "djur_xp" not in k:
        k["djur_xp"] = _m(data).get("intjanat", 0)
    else:
        k["djur_xp"] += int(poang)


def djur_niva(data: dict) -> dict:
    xp = _karta(data).get("djur_xp", _m(data).get("intjanat", 0))
    n = 1
    while n < DJUR_NIVA_MAX and xp >= _xp_for(n + 1):
        n += 1
    nasta = _xp_for(n + 1) if n < DJUR_NIVA_MAX else None
    return {"niva": n, "xp": xp, "fran": _xp_for(n), "till": nasta}


def djur_kraft(data: dict) -> float:
    """Skadefaktor: +2 % per nivå och lagbonus (+5 % per lagmedlem som pluggat idag)."""
    return (1 + (djur_niva(data)["niva"] - 1) * KRAFT_PER_NIVA) * (1 + lag_bonus(data))


def djur_cp(data: dict) -> int:
    """Stridskraft att jämföra med: liv + bästa attack + försvar, gånger kraften."""
    agda = _m(data).get("attacker", [])
    basta = max([x["skada"] for x in ATTACKER if x["id"] in agda] or [KNUFF["skada"]])
    return round((djur_liv(data)[1] + basta * 6 + djur_def(data) * 3) * djur_kraft(data))


def djur_liv(data: dict) -> tuple[int, int]:
    """(liv kvar, max liv). Nya och gamla husdjur börjar med fullt liv."""
    k = _karta(data)
    mx = LIV_MAX[min(_djur_steg(data), len(LIV_MAX) - 1)] + (djur_niva(data)["niva"] - 1) * LIV_PER_NIVA
    liv = k.get("liv")
    return (mx if liv is None else max(0, min(mx, int(liv)))), mx


def _djur_laka(data: dict, poang: int) -> None:
    """Plugg ger tillbaka liv."""
    k = _karta(data)
    liv, mx = djur_liv(data)
    rest = k.get("liv_rest", 0) + int(poang)
    k["liv"] = min(mx, liv + rest // P_LIV)
    k["liv_rest"] = rest % P_LIV


DRYCKER = [
    {"id": "d_liten", "ikon": "🧃", "namn": "Liten livdryck", "pris": 30, "steg": 0, "liv": 20, "info": "+20 liv."},
    {"id": "d_stor", "ikon": "🧪", "namn": "Stor livdryck", "pris": 70, "steg": 1, "liv": 50, "info": "+50 liv."},
    {"id": "d_full", "ikon": "💖", "namn": "Fulldryck", "pris": 120, "steg": 2, "liv": 9999, "info": "Fyller hela livet."},
    {"id": "d_fenix", "ikon": "🪶", "namn": "Fenixfjäder", "pris": 60, "steg": 0, "liv": 0,
     "info": "Väcker ett utmattat husdjur med halva livet."},
]
DRYCK_MAX = 5  # högst så många av varje sort i ryggsäcken


def dryck_kop(data: dict, dryck_id: str) -> None:
    m = _m(data)
    d = m.get("djur")
    x = next((y for y in DRYCKER if y["id"] == dryck_id), None)
    if not d or not x:
        raise ValueError("Det finns inte.")
    if _djur_steg(data) < x["steg"]:
        raise ValueError(f"{d['namn']} måste bli {DJUR_STEG[x['steg']][1]} först.")
    lager = _karta(data).setdefault("drycker", {})
    if lager.get(dryck_id, 0) >= DRYCK_MAX:
        raise ValueError(f"Ryggsäcken rymmer bara {DRYCK_MAX} {x['namn'].lower()}.")
    if m.get("saldo", 0) < x["pris"]:
        raise ValueError(f"Du behöver {x['pris']} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -x["pris"], f"{x['ikon']} Köpte {x['namn']}", None, "🛍️")
    lager[dryck_id] = lager.get(dryck_id, 0) + 1


ENERGI_PRIS = 20  # ⭐ per köpt ⚡ (pluggar man får man 1 ⚡ per 25 ⭐ och behåller stjärnorna)
ENERGI_KOP_DAG = 5  # högst så många ⚡ köpta per dag, så att plugget är det viktiga


def _energi_kopt(k: dict) -> int:
    idag = dt_util.now().date().isoformat()
    x = k.get("energi_kopt") or {}
    return x.get("n", 0) if x.get("dag") == idag else 0


def energi_kop(data: dict, n: int) -> None:
    m, k = _m(data), _karta(data)
    if not m.get("djur"):
        raise ValueError("Du behöver ett husdjur först.")
    n = max(1, min(ENERGI_KOP_DAG, int(n or 1)))
    if k.get("energi", 0) + n > ENERGI_MAX:
        raise ValueError(f"Du får bara ha {ENERGI_MAX} ⚡ (du har {k.get('energi', 0)}).")
    kopt = _energi_kopt(k)
    if kopt + n > ENERGI_KOP_DAG:
        raise ValueError(f"Du kan köpa högst {ENERGI_KOP_DAG} ⚡ per dag ({ENERGI_KOP_DAG - kopt} kvar idag). Plugga så laddas den!")
    pris = n * ENERGI_PRIS
    if m.get("saldo", 0) < pris:
        raise ValueError(f"Du behöver {pris} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -pris, f"⚡ Köpte {n} energi", None, "🛍️")
    k["energi"] = k.get("energi", 0) + n
    k["energi_kopt"] = {"dag": dt_util.now().date().isoformat(), "n": kopt + n}


def dryck(data: dict, dryck_id: str) -> dict:
    """Husdjuret dricker en dryck ur ryggsäcken."""
    m = _m(data)
    x = next((y for y in DRYCKER if y["id"] == dryck_id), None)
    k = _karta(data)
    lager = k.setdefault("drycker", {})
    if not m.get("djur") or not x or lager.get(dryck_id, 0) <= 0:
        raise ValueError("Du har ingen sådan dryck.")
    liv, mx = djur_liv(data)
    if dryck_id == "d_fenix":
        if liv > 0:
            raise ValueError("Fenixfjädern fungerar bara när husdjuret är utmattat 😵.")
        nytt = mx // 2
    else:
        if liv >= mx:
            raise ValueError(f"{m['djur']['namn']} har redan fullt liv ❤️.")
        nytt = min(mx, liv + x["liv"])
    lager[dryck_id] -= 1
    k["liv"] = nytt
    return {"fore": liv, "liv": nytt, "max": mx}


# ---------- sköldar: försvar 🛡️ ----------
# DEF minskar skadan husdjuret tar: skada × 50 / (50 + DEF). DEF 50 halverar skadan.
# Sköldarna hör till barnet (som attackerna) och följer med när barnet byter djur. En sköld på åt gången.
DEF_HALV = 50
SKOLDAR = [
    {"id": "s_kartong", "ikon": "📦", "namn": "Kartongsköld", "def": 2, "pris": 20, "steg": 0, "info": "Bättre än inget!"},
    {"id": "s_tra", "ikon": "🪵", "namn": "Träsköld", "def": 3, "pris": 40, "steg": 0, "info": "Enkel och stadig."},
    {"id": "s_panna", "ikon": "🍳", "namn": "Stekpanna", "def": 5, "pris": 60, "steg": 0, "block": 0.10, "info": "10 % chans att blockera helt. PLONK!"},
    {"id": "s_lov", "ikon": "🌿", "namn": "Lövsköld", "def": 6, "pris": 90, "steg": 0, "laka": 1, "info": "+1 ❤️ varje gång du attackerar."},
    {"id": "s_sten", "ikon": "🪨", "namn": "Stensköld", "def": 8, "pris": 100, "steg": 0, "info": "Tung och tålig."},
    {"id": "s_eld", "ikon": "🔥", "namn": "Eldsköld", "def": 10, "pris": 150, "steg": 0, "mot": "eld", "info": "Halv skada från 🔥 eld."},
    {"id": "s_vatten", "ikon": "🌊", "namn": "Vattensköld", "def": 10, "pris": 150, "steg": 0, "mot": "vatten", "info": "Halv skada från 🌊 vatten."},
    {"id": "s_is", "ikon": "❄️", "namn": "Issköld", "def": 10, "pris": 150, "steg": 0, "mot": "is", "info": "Halv skada från ❄️ is."},
    {"id": "s_blixt", "ikon": "⚡", "namn": "Blixtsköld", "def": 10, "pris": 150, "steg": 0, "mot": "blixt", "info": "Halv skada från ⚡ blixt."},
    {"id": "s_natur", "ikon": "🍃", "namn": "Natursköld", "def": 10, "pris": 150, "steg": 0, "mot": "natur", "info": "Halv skada från 🍃 natur."},
    {"id": "s_tagg", "ikon": "🦔", "namn": "Taggsköld", "def": 12, "pris": 200, "steg": 1, "tagg": 0.2, "info": "20 % av skadan studsar tillbaka."},
    {"id": "s_magnet", "ikon": "🧲", "namn": "Magnetsköld", "def": 14, "pris": 220, "steg": 1, "magnet": 1, "info": "+1 stridsenergi i arenan när du blir träffad."},
    {"id": "s_bubbla", "ikon": "🫧", "namn": "Bubbelsköld", "def": 15, "pris": 250, "steg": 2, "bubbla": True, "info": "Första träffen blockeras (en gång per nivå och arenastrid)."},
    {"id": "s_padda", "ikon": "🐢", "namn": "Sköldpaddsskal", "def": 18, "pris": 260, "steg": 3, "info": "Hårt skal."},
    {"id": "s_spegel", "ikon": "🪞", "namn": "Spegelsköld", "def": 10, "pris": 300, "steg": 3, "spegel": 0.15, "info": "15 % chans att skicka tillbaka hela attacken."},
    {"id": "s_regnbage", "ikon": "🌈", "namn": "Regnbågssköld", "def": 20, "pris": 500, "steg": 3, "alla": 0.8, "info": "−20 % skada från alla typer."},
    {"id": "s_riddare", "ikon": "🛡️", "namn": "Riddarsköld", "def": 25, "pris": 400, "steg": 3, "info": "En riktig riddarsköld."},
    {"id": "s_stjarna", "ikon": "✨", "namn": "Stjärnsköld", "def": 30, "pris": 650, "steg": 4, "block": 0.25, "info": "25 % chans att blockera helt."},
    {"id": "s_drake", "ikon": "🐉", "namn": "Drakfjällssköld", "def": 35, "pris": 700, "steg": 4, "info": "Gjord av drakfjäll."},
    {"id": "s_legend", "ikon": "👑", "namn": "Legendsköld", "def": 50, "pris": 1200, "steg": 5, "bubbla": True, "block": 0.10, "info": "Bubbla + 10 % blockchans. Halverar all skada."},
]
SKOLD = {x["id"]: x for x in SKOLDAR}
SKYDD = ("bubbla", "block", "spegel", "tagg", "typ", "def")
# Vilken typ monstren slår med i varje värld (så att typsköldarna gör nytta mot bossarna också)
VARLD_SLAG = {"skog": "natur", "hav": "vatten", "berg": "kraft", "trask": "is", "fabrik": "blixt", "vulkan": "eld", "slott": "is", "tid": "vatten"}


def skold(data: dict) -> dict | None:
    s = SKOLD.get(_m(data).get("skold") or "")
    return s if s and s["id"] in _m(data).get("skoldar", []) else None


def djur_def(data: dict) -> int:
    s = skold(data)
    return s["def"] if s else 0


def skada_andel(dfn: int) -> float:
    """Hur stor del av skadan som går igenom (1.0 = all)."""
    return DEF_HALV / (DEF_HALV + max(0, dfn))


def skold_kop(data: dict, sid: str) -> None:
    m = _m(data)
    d = m.get("djur")
    s = SKOLD.get(sid)
    if not d or not s:
        raise ValueError("Det finns inte.")
    agda = m.setdefault("skoldar", [])
    if sid in agda:
        raise ValueError("Den skölden har du redan.")
    if _djur_steg(data) < s["steg"]:
        raise ValueError(f"{d['namn']} måste bli {DJUR_STEG[s['steg']][1]} först.")
    if m.get("saldo", 0) < s["pris"]:
        raise ValueError(f"Du behöver {s['pris']} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -s["pris"], f"🛡️ {d['namn']} fick {s['namn']} {s['ikon']}", None, "🛍️")
    agda.append(sid)
    m["skold"] = sid  # nyköpt sköld tas på direkt


def skold_pa(data: dict, sid: str | None) -> None:
    m = _m(data)
    if not sid:
        m["skold"] = ""
        return
    if sid not in m.get("skoldar", []) or sid not in SKOLD:
        raise ValueError("Den skölden har du inte.")
    m["skold"] = sid


def _skydda(s: dict | None, typ: str, skada: int, bubbla_kvar: bool) -> dict:
    """Vad skölden gör med en träff: {"skada": som går igenom, "skydd": vad som hände, "tillbaka": skada åt anfallaren}."""
    if not s or skada <= 0:
        return {"skada": skada, "skydd": "", "tillbaka": 0}
    if bubbla_kvar and s.get("bubbla"):
        return {"skada": 0, "skydd": "bubbla", "tillbaka": 0}
    if random.random() < s.get("block", 0):
        return {"skada": 0, "skydd": "block", "tillbaka": 0}
    if random.random() < s.get("spegel", 0):
        return {"skada": 0, "skydd": "spegel", "tillbaka": skada}
    ut = skada * skada_andel(s["def"]) * s.get("alla", 1)
    typskydd = s.get("mot") == typ
    if typskydd:
        ut *= 0.5
    ut = max(1, round(ut))
    tillbaka = round(ut * s.get("tagg", 0))
    return {"skada": ut, "skydd": "tagg" if tillbaka else "typ" if typskydd else "def", "tillbaka": tillbaka}


def skold_status(data: dict) -> dict:
    m = _m(data)
    agda, pa = m.get("skoldar", []), skold(data)
    dfn = djur_def(data)
    return {"def": dfn, "minskar": round((1 - skada_andel(dfn)) * 100), "pa": pa["id"] if pa else "",
            "skoldar": [{**x, "har": x["id"] in agda} for x in SKOLDAR]}


def _motattack(n: int, mon: dict) -> int:
    """Hur hårt monstret slår tillbaka. Starkare längre fram och på bossnivåer."""
    bas = (3 + min(15, n // 6)) * (1.8 if mon.get("boss") else 1)
    return max(1, round(bas * random.uniform(0.7, 1.3)))


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
    return round(skada * djur_kraft(data)) * (SVAG_GANGER if svag else 1), svag


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
    liv_fore, liv_max = djur_liv(data)
    if liv_fore <= 0:
        raise ValueError(f"{m['djur']['namn']} är utmattad 😵 Plugga så får hen tillbaka liv!")
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
    klar = k["niva"] > n
    # Monstret slår tillbaka om det överlevde
    miss = not klar and random.random() < MISS_CHANS
    sk = skold(data)
    laka = sk.get("laka", 0) if sk else 0
    if laka:  # lövskölden läker lite när husdjuret attackerar
        liv_fore = min(liv_max, liv_fore + laka)
    skydd = {"skada": 0, "skydd": "", "tillbaka": 0}
    if not klar and not miss:
        skydd = _skydda(sk, mon.get("slag", "kraft"), _motattack(n, mon), k.get("bubbla") != n)
        if skydd["skydd"] == "bubbla":
            k["bubbla"] = n
    mot = skydd["skada"]
    k["liv"] = max(0, liv_fore - mot)
    if skydd["tillbaka"]:  # taggar eller spegel skadar monstret
        _karta_skada(data, skydd["tillbaka"])
    klar2 = k["niva"] > n
    k["senaste"].update({"klar": klar or klar2, "mot": mot, "miss": miss, "liv_fore": liv_fore, "liv": k["liv"], "liv_max": liv_max,
                         "skydd": skydd["skydd"], "tillbaka": skydd["tillbaka"], "skold": sk["id"] if sk else "", "laka": laka})
    k["repriser"] = (k.get("repriser", []) + [{"id": at_id, "niva": n, "hp": hp_fore, "kvar": kvar_fore, "skada": skada,
                                               "svag": svag, "klar": klar or klar2, "tid": k["senaste"]["tid"], "mot": mot,
                                               "miss": miss, "liv_fore": liv_fore, "liv_max": liv_max,
                                               "skydd": skydd["skydd"], "tillbaka": skydd["tillbaka"], "skold": sk["id"] if sk else ""}])[-5:]
    return k["senaste"]


# ---------- arenan: husdjur mot husdjur ----------
KNUFF = {"id": "knuff", "ikon": "🐾", "namn": "Knuff", "typ": "kraft", "energi": 0, "skada": 3}
ARENA_AP_START, ARENA_AP_TUR, ARENA_AP_MAX = 3, 1, 6
ARENA_MISS = 0.1
ARENA_GANGER = 3  # arenan går snabbare än kartan
ARENA_VINST, ARENA_FORLUST = 10, 2  # arenapoäng 🏆
ARENA_XP_VINST, ARENA_XP_FORLUST = 15, 5
# Arenaversion för strider mellan vänner i olika hem. Höj den när regler, drag eller skada ändras
# så att en strid mot en annan version skulle bli fel. Båda hemmen måste ha samma version för att strida.
ARENA_VER = 3  # 2: sköldar och försvar, 3: försvarsträning

# Försvarsträning: när någon annan utmanar ditt husdjur styr datorn det. Tränar du det slåss det
# smartare och tar i mer (bara när det försvarar sig, inte när du själv anfaller).
TRANING = [  # (pris ⭐, namn)
    (0, "Otränad"), (50, "Nybörjare"), (120, "Kämpe"), (250, "Krigare"), (400, "Mästare"), (600, "Stormästare"),
]
TRANING_LIV, TRANING_SKADA = 0.04, 0.03  # per nivå när husdjuret försvarar sig


def traning(data: dict) -> int:
    return max(0, min(len(TRANING) - 1, int(_m(data).get("traning", 0) or 0)))


def traning_kop(data: dict) -> int:
    m = _m(data)
    d = m.get("djur")
    if not d:
        raise ValueError("Du behöver ett husdjur först.")
    t = traning(data)
    if t >= len(TRANING) - 1:
        raise ValueError(f"{d['namn']} är redan fullt tränad 🎓.")
    pris, namn = TRANING[t + 1]
    if m.get("saldo", 0) < pris:
        raise ValueError(f"Du behöver {pris} ⭐ (du har {m.get('saldo', 0)}).")
    ge(data, -pris, f"🎓 {d['namn']} tränade försvar: {namn}", None, "🛍️")
    m["traning"] = t + 1
    return t + 1


def traning_status(data: dict) -> dict:
    t = traning(data)
    return {"niva": t, "namn": TRANING[t][1], "max": len(TRANING) - 1, "liv": round(t * TRANING_LIV * 100), "skada": round(t * TRANING_SKADA * 100),
            "nasta": {"niva": t + 1, "namn": TRANING[t + 1][1], "pris": TRANING[t + 1][0], "liv": round((t + 1) * TRANING_LIV * 100),
                      "skada": round((t + 1) * TRANING_SKADA * 100)} if t + 1 < len(TRANING) else None}


def _forsvarare(k: dict) -> dict:
    """Ett utmanat husdjur som datorn styr får sin träning: mer liv och mer skada."""
    t = max(0, min(len(TRANING) - 1, int(k.get("traning", 0) or 0)))
    if t:
        mx = round(k["max"] * (1 + t * TRANING_LIV))
        k.update({"max": mx, "liv": mx, "drag": {a: max(1, round(v * (1 + t * TRANING_SKADA))) for a, v in k["drag"].items()}})
    return k


def _kampe(data: dict, agare: str) -> dict:
    d = _m(data).get("djur") or {}
    agda = _m(data).get("attacker", [])
    kraft = djur_kraft(data)
    drag = {"knuff": round(KNUFF["skada"] * kraft * ARENA_GANGER)}
    for at in ATTACKER:
        if at["id"] in agda:
            drag[at["id"]] = _attack_varde(data, at, {})[0] * ARENA_GANGER
    mx = djur_liv(data)[1]
    sk = skold(data)
    return {"agare": agare, "namn": d.get("namn", "?"), "art": d.get("art"), "steg": _djur_steg(data),
            "niva": djur_niva(data)["niva"], "cp": djur_cp(data), "liv": mx, "max": mx, "ap": ARENA_AP_START, "drag": drag,
            "skold": sk["id"] if sk else "", "def": sk["def"] if sk else 0, "traning": traning(data)}


def _drag_info(at_id: str) -> dict:
    return KNUFF if at_id == "knuff" else next(x for x in ATTACKER if x["id"] == at_id)


def arena_kampe(data: dict) -> dict | None:
    """Det en vän i ett annat hem får veta om husdjuret för att kunna utmana det."""
    if not _m(data).get("djur"):
        return None
    k = _kampe(data, "")
    return {x: k[x] for x in ("namn", "art", "steg", "niva", "cp", "max", "drag", "skold", "traning")}


def _int(v, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def rensa_kampe(k: dict, agare: str) -> tuple[dict, int]:
    """Kontrollera en väns husdjur från ett annat hem. Drag vi inte känner till tas bort, och inga värden
    får vara större än vad som går att få i Skolan. Returnerar (kämpe, antal borttagna drag)."""
    if not isinstance(k, dict) or not isinstance(k.get("drag"), dict):
        raise ValueError("Vännens husdjur gick inte att läsa.")
    kraft_max = (1 + (DJUR_NIVA_MAX - 1) * 0.02) * (1 + LAG_BONUS_PER * LAG_MAX)
    kanda = {"knuff": KNUFF, **{x["id"]: x for x in ATTACKER}}
    drag, okanda = {}, 0
    for at_id, varde in list(k["drag"].items())[:30]:
        at = kanda.get(at_id)
        if not at:
            okanda += 1
            continue
        tak = math.ceil((at["skada"] * 2 + 3) * kraft_max * ARENA_GANGER * 1.2)
        drag[at_id] = _int(varde, 1, tak)
    drag.setdefault("knuff", KNUFF["skada"] * ARENA_GANGER)
    liv_tak = LIV_MAX[-1] + (DJUR_NIVA_MAX - 1) * 4
    mx = _int(k.get("max"), 1, liv_tak)
    sk = SKOLD.get(k.get("skold") if isinstance(k.get("skold"), str) else "")  # DEF räknas här, vännens siffra används inte
    return {"agare": str(agare)[:16], "namn": str(k.get("namn") or "?")[:20], "art": str(k.get("art") or "")[:8],
            "steg": _int(k.get("steg"), 0, len(DJUR_STEG) - 1), "niva": _int(k.get("niva"), 1, DJUR_NIVA_MAX), "cp": _int(k.get("cp"), 0, 10**6),
            "liv": mx, "max": mx, "ap": ARENA_AP_START, "drag": drag, "skold": sk["id"] if sk else "", "def": sk["def"] if sk else 0,
            "traning": _int(k.get("traning"), 0, len(TRANING) - 1)}, okanda


def arena_start(data: dict, jag: str, mot_id: str, mot_namn: str, mot_data: dict | None = None, de: dict | None = None) -> dict:
    m = _m(data)
    if not m.get("djur"):
        raise ValueError("Du behöver ett husdjur först.")
    if de is None and not _m(mot_data).get("djur"):
        raise ValueError(f"{mot_namn} har inget husdjur än.")
    k = _karta(data)
    if k.get("lagstrid"):
        raise ValueError("Gör klart lagstriden först.")
    if k.get("energi", 0) < 1:
        raise ValueError("Du behöver 1 ⚡ energi för att gå in i arenan. Plugga så laddas den!")
    k["energi"] -= 1
    k["arena"] = {"mot": mot_id, "mot_namn": mot_namn, "jag": _kampe(data, jag), "de": _forsvarare(de or _kampe(mot_data, mot_namn)),
                  "turer": [], "start": dt_util.now().isoformat(timespec="seconds")}
    return k["arena"]


def _slag(kampe: dict, at_id: str, mal: dict) -> dict:
    """Ett anfall i arenan. Målets sköld tar emot träffen."""
    ls = SKOLD.get(kampe.get("skold") or "")
    if ls and ls.get("laka"):
        kampe["liv"] = min(kampe["max"], kampe["liv"] + ls["laka"])
    if random.random() < ARENA_MISS:
        return {"skada": 0, "miss": True, "skydd": "", "tillbaka": 0}
    ra = max(1, round(kampe["drag"][at_id] * random.uniform(0.85, 1.15)))
    s = SKOLD.get(mal.get("skold") or "")
    sk = _skydda(s, _drag_info(at_id)["typ"], ra, not mal.get("bubbla_anv"))
    if sk["skydd"] == "bubbla":
        mal["bubbla_anv"] = True
    mal["liv"] = max(0, mal["liv"] - sk["skada"])
    if sk["tillbaka"]:
        kampe["liv"] = max(0, kampe["liv"] - sk["tillbaka"])
    if s and s.get("magnet") and sk["skada"] > 0:
        mal["ap"] = min(ARENA_AP_MAX, mal["ap"] + s["magnet"])
    return {"skada": sk["skada"], "miss": False, "skydd": sk["skydd"], "tillbaka": sk["tillbaka"]}


def _ai_val(de: dict, mal: dict | None = None) -> str:
    """Datorns val av drag. Tränade husdjur väljer smartare."""
    t = max(0, min(len(TRANING) - 1, int(de.get("traning", 0) or 0)))
    kan = [a for a in de["drag"] if _drag_info(a)["energi"] <= de["ap"]]
    if mal and t >= 2:  # kan den slå ut motståndaren nu tar den det billigaste draget som räcker
        racker = [a for a in kan if de["drag"][a] >= mal["liv"]]
        if racker:
            return min(racker, key=lambda a: _drag_info(a)["energi"])
    if t >= 4:  # sparar energi till sitt starkaste drag om det går nästa tur
        basta = max(de["drag"], key=lambda a: de["drag"][a])
        if basta not in kan and de["ap"] + ARENA_AP_TUR >= _drag_info(basta)["energi"]:
            return "knuff"
    if random.random() < 0.7 + 0.06 * t:
        return max(kan, key=lambda a: de["drag"][a])
    return random.choice(kan)


def arena_drag(data: dict, at_id: str) -> dict:
    k = _karta(data)
    a = k.get("arena")
    if not a:
        raise ValueError("Ingen strid pågår.")
    jag, de = a["jag"], a["de"]
    if at_id not in jag["drag"]:
        raise ValueError("Det draget kan ditt husdjur inte.")
    kostar = _drag_info(at_id)["energi"]
    if kostar > jag["ap"]:
        raise ValueError(f"Du behöver {kostar} ⚡ i striden. Använd Knuff 🐾 och vänta en tur.")
    tur = {"at": at_id, "jag_fore": jag["liv"], "de_fore": de["liv"]}
    jag["ap"] -= kostar
    x = _slag(jag, at_id, de)
    tur.update({"skada": x["skada"], "miss": x["miss"], "skydd": x["skydd"], "tillbaka": x["tillbaka"]})
    if de["liv"] > 0 and jag["liv"] > 0:
        mot = _ai_val(de, jag)
        de["ap"] -= _drag_info(mot)["energi"]
        tur["mot_at"] = mot
        y = _slag(de, mot, jag)
        tur.update({"mot": y["skada"], "mot_miss": y["miss"], "mot_skydd": y["skydd"], "mot_tillbaka": y["tillbaka"]})
    tur["jag_efter"], tur["de_efter"] = jag["liv"], de["liv"]
    jag["ap"] = min(ARENA_AP_MAX, jag["ap"] + ARENA_AP_TUR)
    de["ap"] = min(ARENA_AP_MAX, de["ap"] + ARENA_AP_TUR)
    a["turer"].append(tur)
    if de["liv"] <= 0 or jag["liv"] <= 0 or len(a["turer"]) >= 40:
        vann = de["liv"] <= 0 and jag["liv"] > 0
        tur["slut"] = "vinst" if vann else "forlust"
        _arena_slut(data, vann)
    return tur


def arena_ge_upp(data: dict) -> None:
    if _karta(data).get("arena"):
        _arena_slut(data, False, gav_upp=True)


def _arena_slut(data: dict, vann: bool, gav_upp: bool = False) -> None:
    k = _karta(data)
    a = k.pop("arena")
    k["arena_poang"] = k.get("arena_poang", 0) + (ARENA_VINST if vann else ARENA_FORLUST if not gav_upp else 0)
    _djur_xp(data, 0)
    k["djur_xp"] += ARENA_XP_VINST if vann else ARENA_XP_FORLUST if not gav_upp else 0
    if vann:
        _rakna(data, "arena_vinster")
        kolla_medaljer(data)
    k["arena_hist"] = (k.get("arena_hist", []) + [{
        "mot": a["mot"], "mot_namn": a["mot_namn"], "vann": vann, "gav_upp": gav_upp, "tid": dt_util.now().isoformat(timespec="seconds"),
        "jag": {x: a["jag"].get(x) for x in ("namn", "art", "steg", "niva", "max", "skold", "def")},
        "de": {x: a["de"].get(x) for x in ("namn", "art", "steg", "niva", "max", "skold", "def")},
        "turer": a["turer"][-40:]}])[-10:]


def arena_status(data: dict) -> dict:
    k = _karta(data)
    a = k.get("arena")
    n = djur_niva(data)
    return {"niva": n, "cp": djur_cp(data), "def": djur_def(data), "traning": traning_status(data), "kraft": round(djur_kraft(data), 2), "poang": k.get("arena_poang", 0),
            "vinster": _m(data)["raknare"].get("arena_vinster", 0), "pagar": a, "hist": k.get("arena_hist", [])[-5:],
            "knuff": KNUFF, "ap_max": ARENA_AP_MAX, "ver": ARENA_VER, "drag": {x["id"]: {y: x[y] for y in ("ikon", "namn", "typ", "energi")} for x in [KNUFF, *ATTACKER]}}


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


# ---------- lag: lagboss, lagbonus och lagstrid 2 mot 2 ----------
# Föräldrarna skapar lagen (lag.json). Ett barn är med i högst ett lag.
LAG_MARKEN = ["🏳️", "🦁", "🐺", "🦅", "🐉", "⚡", "🔥", "🌊", "⭐", "🚀", "🛡️", "👑"]
LAG_MAX = 4
LAG_BONUS_PER = 0.05  # +5 % skada för varje lagmedlem som har pluggat idag (även en själv)
LAGBOSSAR = [
    {"ikon": "🐲", "namn": "Läxdraken Maxi"}, {"ikon": "🦖", "namn": "Glos-Rex"}, {"ikon": "🐙", "namn": "Kraken Glömska"},
    {"ikon": "👹", "namn": "Jätten Slarv"}, {"ikon": "🤖", "namn": "Megaroboten"}, {"ikon": "🧊", "namn": "Isjätten"},
    {"ikon": "🌋", "namn": "Lavamonstret"}, {"ikon": "👻", "namn": "Spökkungen"},
]
LAGBOSS_ANDEL = 0.7  # lagbossens liv = 70 % av vad lagmedlemmarna brukar plugga tillsammans en vecka
LAGBOSS_MIN = 150
LAGBOSS_BELONING = 40  # ⭐ till varje lagmedlem när bossen är besegrad
LAGSTRID_VINST, LAGSTRID_FORLUST = 15, 3  # arenapoäng 🏆
LAGSTRID_XP_VINST, LAGSTRID_XP_FORLUST = 20, 6
UTMANARE = ["Skuggan", "Blixten", "Klon-Kalle", "Vilda Vera", "Turbo", "Mörkermyran", "Kapten Kaos", "Gnistan"]


def _dag_poang(data: dict, iso: str) -> int:
    return sum(x["p"] for x in _m(data)["logg"] if x["p"] > 0 and x.get("ikon") not in EJ_SKADA and x["tid"][:10] == iso)


def _vecka_nu() -> str:
    return "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])


def lag_satt(data: dict, lag: dict | None, bonus: int) -> None:
    """Spara barnets lag och dagens lagbonus i barnets data (läses av djur_kraft)."""
    m = _m(data)
    if not lag:
        m.pop("lag", None)
        return
    m["lag"] = {"id": lag["id"], "namn": lag["namn"], "marke": lag["marke"], "dag": dt_util.now().date().isoformat(), "bonus": int(bonus)}


def lag_bonus(data: dict) -> float:
    lag = _m(data).get("lag")
    if not lag or lag.get("dag") != dt_util.now().date().isoformat():
        return 0.0
    return LAG_BONUS_PER * max(0, min(LAG_MAX, int(lag.get("bonus", 0))))


def lag_kort(data: dict) -> dict:
    """Det en vän i ett annat hem behöver för ett vänlag."""
    return {"vecka_id": _vecka_nu(), "vecka": _vecko_poang(data).get(_vecka_nu(), 0), "dag": dt_util.now().date().isoformat(),
            "idag": _dag_poang(data, dt_util.now().date().isoformat()) > 0, "mal": boss_mal_vecka(data),
            "cp": djur_cp(data) if _m(data).get("djur") else 0, "def": djur_def(data)}


def lag_status(lag: dict, medlemmar: list[tuple[str, str, dict]], vanner: list[dict] | None = None) -> dict:
    """Lagets läge. medlemmar = [(barn-id, namn, data)], vanner = vänners senast hämtade kort."""
    idag = dt_util.now().date().isoformat()
    vecka = _vecka_nu()
    ar, v = int(vecka[:4]), int(vecka[-2:])
    boss = LAGBOSSAR[(ar * 53 + v) % len(LAGBOSSAR)]
    hp = max(LAGBOSS_MIN, round(sum(boss_mal_vecka(d) for _i, _n, d in medlemmar) * LAGBOSS_ANDEL))
    folk = []
    for bid, namn, d in medlemmar:
        dj = _m(d).get("djur") or {}
        folk.append({"id": bid, "namn": namn, "art": dj.get("art"), "djur": dj.get("namn"), "steg": _djur_steg(d),
                     "cp": djur_cp(d) if dj else 0, "def": djur_def(d), "idag": _dag_poang(d, idag) > 0,
                     "vecka": _vecko_poang(d).get(vecka, 0)})
    for v in vanner or []:
        lk = v.get("lag") or {}
        denna = lk.get("vecka_id") == vecka
        hp += round((lk.get("mal") or 0) * LAGBOSS_ANDEL)
        folk.append({"id": "van:" + v["kod"], "namn": v.get("smeknamn", "?"), "art": v.get("art"), "djur": "", "steg": v.get("steg", 0),
                     "cp": lk.get("cp", 0), "def": lk.get("def", 0), "idag": bool(lk.get("idag")) and lk.get("dag") == idag,
                     "vecka": lk.get("vecka", 0) if denna else 0, "van": True})
    skada = sum(x["vecka"] for x in folk)
    idag_n = sum(1 for x in folk if x["idag"])
    slut = dt_util.now().date() + timedelta(days=6 - dt_util.now().date().weekday())
    return {"id": lag["id"], "namn": lag["namn"], "marke": lag["marke"], "medlemmar": folk,
            "bonus": idag_n, "bonus_pct": round(idag_n * LAG_BONUS_PER * 100), "bonus_per": round(LAG_BONUS_PER * 100),
            "boss": {**boss, "hp": hp, "skada": min(skada, hp), "klar": skada >= hp, "vecka": vecka,
                     "slut": slut.isoformat(), "beloning": LAGBOSS_BELONING}}


def lagboss_belona(data: dict, st: dict) -> bool:
    """Ge lagbossens belöning till barnet en gång per vecka när laget har besegrat den."""
    b = st["boss"]
    if not b["klar"]:
        return False
    if ge(data, LAGBOSS_BELONING, f"{st['marke']} Laget {st['namn']} besegrade {b['namn']} {b['ikon']}!", f"lagboss:{b['vecka']}", "🏳️"):
        _rakna(data, "lagbossar")
        return True
    return False


def _utmanarlag(lag: list[dict]) -> list[dict]:
    """Ett datorstyrt lag som är ungefär lika starkt som barnens."""
    namn = random.sample(UTMANARE, len(lag))
    arter = random.sample([x for x in DJUR if x not in {k.get("art") for k in lag}] or DJUR, len(lag))
    ut = []
    for i, k in enumerate(lag):
        f = random.uniform(0.92, 1.05)
        sk = random.choice([x for x in SKOLDAR if x["def"] <= max(5, k.get("def", 0) + 5)] + [None])
        mx = max(10, round(k["max"] * f))
        ut.append({"agare": "ai", "namn": namn[i], "art": arter[i], "steg": k["steg"], "niva": k["niva"], "cp": round(k["cp"] * f),
                   "liv": mx, "max": mx, "ap": ARENA_AP_START, "drag": {a: max(1, round(v * f)) for a, v in k["drag"].items()},
                   "skold": sk["id"] if sk else "", "def": sk["def"] if sk else 0})
    return ut


def lagstrid_start(data: dict, jag: str, lag_namn: str, kampar: list[dict], de: list[dict] | None = None, de_namn: str = "") -> dict:
    """kampar[0] är barnets eget husdjur (styrs av barnet), resten styrs av datorn."""
    m = _m(data)
    if not m.get("djur"):
        raise ValueError("Du behöver ett husdjur först.")
    if len(kampar) < 2:
        raise ValueError("Laget behöver minst två husdjur för en lagstrid.")
    k = _karta(data)
    if k.get("arena") or k.get("lagstrid"):
        raise ValueError("Du har redan en strid som pågår.")
    if k.get("energi", 0) < 1:
        raise ValueError("Du behöver 1 ⚡ energi för en lagstrid. Plugga så laddas den!")
    k["energi"] -= 1
    k["lagstrid"] = {"jag": jag, "lag_namn": lag_namn, "lag": kampar, "de": de or _utmanarlag(kampar),
                     "de_namn": de_namn or "Utmanarlaget", "turer": [], "start": dt_util.now().isoformat(timespec="seconds")}
    return k["lagstrid"]


def _levande(lista: list[dict]) -> list[int]:
    return [i for i, x in enumerate(lista) if x["liv"] > 0]


def _ls_slag(sida: str, i: int, kampe: dict, at_id: str, mal_sida: str, mal_lista: list[dict], mal_i: int) -> dict:
    kampe["ap"] -= _drag_info(at_id)["energi"]
    x = _slag(kampe, at_id, mal_lista[mal_i])
    return {"sida": sida, "i": i, "at": at_id, "mal_sida": mal_sida, "mal": mal_i, **x}


def lagstrid_drag(data: dict, at_id: str, mal: int) -> dict:
    k = _karta(data)
    s = k.get("lagstrid")
    if not s:
        raise ValueError("Ingen lagstrid pågår.")
    lag, de = s["lag"], s["de"]
    h = []
    jag = lag[0]
    if jag["liv"] > 0:
        if at_id not in jag["drag"]:
            raise ValueError("Det draget kan ditt husdjur inte.")
        if _drag_info(at_id)["energi"] > jag["ap"]:
            raise ValueError(f"Du behöver {_drag_info(at_id)['energi']} ⚡ i striden. Använd Knuff 🐾 och vänta en tur.")
        lev = _levande(de)
        h.append(_ls_slag("lag", 0, jag, at_id, "de", de, mal if mal in lev else lev[0]))
    for i, x in enumerate(lag[1:], 1):  # lagkamraterna (datorn styr) anfaller den svagaste
        lev = _levande(de)
        if x["liv"] > 0 and lev:
            m_i = min(lev, key=lambda j: de[j]["liv"])
            h.append(_ls_slag("lag", i, x, _ai_val(x, de[m_i]), "de", de, m_i))
    for i, x in enumerate(de):  # motståndarna anfaller någon i laget
        lev = _levande(lag)
        if x["liv"] > 0 and lev:
            m_i = random.choice(lev)
            h.append(_ls_slag("de", i, x, _ai_val(x, lag[m_i]), "lag", lag, m_i))
    for x in lag + de:
        x["ap"] = min(ARENA_AP_MAX, x["ap"] + ARENA_AP_TUR)
    tur = {"h": h, "liv_lag": [x["liv"] for x in lag], "liv_de": [x["liv"] for x in de]}
    s["turer"].append(tur)
    if not _levande(de) or not _levande(lag) or len(s["turer"]) >= 30:
        vann = not _levande(de) and bool(_levande(lag))
        tur["slut"] = "vinst" if vann else "forlust"
        _lagstrid_slut(data, vann)
    return tur


def lagstrid_ge_upp(data: dict) -> None:
    if _karta(data).get("lagstrid"):
        _lagstrid_slut(data, False, gav_upp=True)


def _lagstrid_slut(data: dict, vann: bool, gav_upp: bool = False) -> None:
    k = _karta(data)
    s = k.pop("lagstrid")
    k["arena_poang"] = k.get("arena_poang", 0) + (LAGSTRID_VINST if vann else 0 if gav_upp else LAGSTRID_FORLUST)
    _djur_xp(data, 0)
    k["djur_xp"] += LAGSTRID_XP_VINST if vann else 0 if gav_upp else LAGSTRID_XP_FORLUST
    if vann:
        _rakna(data, "lagstrid_vinster")
        kolla_medaljer(data)
    kort = lambda x: {y: x.get(y) for y in ("namn", "art", "steg", "niva", "max", "skold", "def")}  # noqa: E731
    k["lagstrid_hist"] = (k.get("lagstrid_hist", []) + [{
        "lag_namn": s["lag_namn"], "de_namn": s["de_namn"], "vann": vann, "gav_upp": gav_upp,
        "tid": dt_util.now().isoformat(timespec="seconds"), "lag": [kort(x) for x in s["lag"]], "de": [kort(x) for x in s["de"]],
        "turer": s["turer"][-30:]}])[-5:]


def lagstrid_status(data: dict) -> dict:
    k = _karta(data)
    return {"pagar": k.get("lagstrid"), "hist": k.get("lagstrid_hist", [])[-3:], "vinster": _m(data)["raknare"].get("lagstrid_vinster", 0),
            "vinst": LAGSTRID_VINST, "forlust": LAGSTRID_FORLUST}
