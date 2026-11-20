"""Dagens hälsning: något uppmuntrande varje dag och en gåta. Svaret på gåtan kommer dagen efter."""
from __future__ import annotations

import difflib
import re
from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from . import meriter

P_GATA = 5  # ⭐ för rätt svar på gåtan

# (gåta, godkända svar). Svaren jämförs utan versaler, "en/ett" och små stavfel.
GATOR = [
    ("Vad har nycklar men kan inte öppna ett enda lås?", ["piano", "tangentbord", "keyboard"]),
    ("Vad blir blötare ju mer det torkar?", ["handduk"]),
    ("Vad har ett öga men kan inte se?", ["nål", "synål"]),
    ("Vad går upp men aldrig ner?", ["ålder", "åldern"]),
    ("Vad har ben men kan inte gå?", ["bord", "stol"]),
    ("Vad har en hals men inget huvud?", ["flaska"]),
    ("Vad kan man fånga men aldrig kasta?", ["förkylning", "snuva"]),
    ("Ju fler du tar, desto fler lämnar du efter dig. Vad är det?", ["fotsteg", "steg", "fotspår"]),
    ("Vad har tänder men kan inte bita?", ["kam", "såg", "dragkedja"]),
    ("Vad är fullt av hål men kan ändå hålla vatten?", ["svamp", "tvättsvamp"]),
    ("Vad har ett huvud och en svans men ingen kropp?", ["mynt", "slant", "krona"]),
    ("Vad kan resa jorden runt men stannar hela tiden i ett hörn?", ["frimärke"]),
    ("Vilka månader har 28 dagar?", ["alla", "alla månader"]),
    ("Vad blir större ju mer man tar bort från det?", ["hål", "grop"]),
    ("Jag har sidor och en rygg, men jag kan inte stå upp själv. Vad är jag?", ["bok"]),
    ("Vad är ditt, men används mest av andra?", ["namn", "ditt namn"]),
    ("Vad går genom glas utan att det går sönder?", ["ljus", "solljus", "solen"]),
    ("Vad kommer en gång i en minut, två gånger i ett ögonblick men aldrig på tusen år?", ["m", "bokstaven m"]),
    ("Vad har ett ansikte och två visare men inga armar?", ["klocka"]),
    ("Vad flyger fast det inte har några vingar?", ["tid", "tiden"]),
    ("Vad svarar alltid när du ropar, fast ingen är där?", ["eko", "ekot"]),
    ("Vilket ord stavas alltid fel i ordboken?", ["fel"]),
    ("Vad har en bädd men sover aldrig, och en mynning men äter aldrig?", ["flod", "älv", "å"]),
    ("Vad är alltid framför dig men går aldrig att se?", ["framtid", "framtiden"]),
    ("Vad har många ringar men inga fingrar?", ["träd", "trädstam", "stam"]),
    ("Vad går runt hela huset men kommer aldrig in?", ["staket", "stängsel", "häck"]),
    ("Vilket djur kan hoppa högre än ett hus?", ["alla", "alla djur"]),
    ("Vad har en tunga men kan inte smaka?", ["sko", "skor"]),
    ("Vad blir kortare ju längre det brinner?", ["ljus", "stearinljus"]),
    ("Vad har vingar som snurrar men kan inte flyga?", ["väderkvarn", "kvarn", "vindkraftverk"]),
    ("Vad har en mus, ett fönster och en skärm men inget hus?", ["dator"]),
    ("Vad är grönt utanpå, rött inuti och har svarta kärnor?", ["vattenmelon", "melon"]),
    ("Vad är gult, böjt och växer i klasar?", ["banan", "bananer"]),
    ("Vad kan du hålla utan att röra vid det?", ["andan", "andetag", "löfte"]),
    ("Jag har städer men inga hus, skogar men inga träd och sjöar men inga fiskar. Vad är jag?", ["karta"]),
    ("Vad går upp när regnet kommer ner?", ["paraply"]),
    ("Vad finns mitt i Paris?", ["r", "bokstaven r"]),
    ("Hur många ägg kan man äta på fastande mage?", ["ett", "1", "ett ägg"]),
    ("Vad kan man slå, fast det inte gör ont på någon?", ["rekord", "ett rekord"]),
    ("Vad är tyngst: ett kilo fjädrar eller ett kilo sten?", ["lika", "samma", "lika tunga", "båda"]),
    ("Vem bär sitt hus på ryggen och är aldrig hemifrån?", ["snigel", "sköldpadda"]),
    ("Vad växer när det äter, men dör när det dricker?", ["eld", "elden"]),
    ("Vad har många tänder och äter trä?", ["såg"]),
    ("Vad har ögon men ser inte, och kan bli pommes frites?", ["potatis"]),
    ("Vad kommer ner men går aldrig upp igen?", ["regn", "regnet"]),
    ("Vad blir mer av när man delar det med andra?", ["glädje", "kunskap", "kärlek"]),
    ("Vad har en näsa som är lång, men kan inte lukta? (Han ljuger ofta…)", ["pinocchio"]),
    ("Vad kan man se på natten men inte på dagen, fast det finns där hela tiden?", ["stjärnor", "stjärnorna"]),
    ("Vad har fyra ben på morgonen, två mitt på dagen och tre på kvällen?", ["människa", "människan"]),
    ("Vad är svart och vitt och läses överallt?", ["tidning", "bok"]),
    ("Vad kan fyllas med luft men blir ändå inte tyngre?", ["ballong"]),
    ("Vilken sorts bok kan man aldrig läsa?", ["bokträd", "bok"]),
    ("Vad kan man bryta utan att ta i det?", ["löfte", "tystnad", "tystnaden"]),
    ("Vad har ett skal, en vita och en gula?", ["ägg", "ett ägg"]),
    ("Vad är det som snurrar runt solen och har en måne?", ["jorden"]),
    ("Vad står mitt i vatten men blir aldrig blött?", ["skugga", "spegelbild"]),
]

PEPP = [
    "Varje gång du pluggar blir din hjärna lite starkare. 💪",
    "Det är okej att något är svårt. Det betyder att du lär dig något nytt!",
    "Små steg varje dag blir till stora saker. 🐾",
    "Fel svar är bara ett steg på vägen till rätt svar.",
    "Du behöver inte vara bäst. Du behöver bara vara lite bättre än igår. 🌱",
    "Tio minuter idag är bättre än en timme någon gång.",
    "Hjärnan gillar repetition. Öva lite, vila lite, öva igen!",
    "Vet du vad? Du är bättre på det här än du tror. ⭐",
    "Den som övar blir bra. Så enkelt är det!",
    "Varje glosa du kan är din för alltid. 🧠",
    "Även superhjältar måste träna. 🦸",
    "Kämpa på! Ditt husdjur tror på dig.",
    "Att våga försöka är det modigaste som finns.",
    "Kom ihåg att ta en paus och dricka vatten. 💧",
    "Det du lär dig idag gör morgondagen lättare.",
    "Du har klarat svåra saker förut. Du klarar det här också!",
    "Läs högt, säg orden, skriv dem. Då fastnar de bättre! ✍️",
    "Ingen föds som expert. Alla börjar från början.",
    "Var stolt över det du redan kan! 🏅",
    "Idag är en ny chans. Kör! 🚀",
]


def _norm(s: str) -> str:
    s = re.sub(r"[^\wåäöé ]", " ", str(s or "").lower())
    s = re.sub(r"\b(en|ett|den|det|de|bokstaven)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ratt_svar(gissning: str, svar: list[str]) -> bool:
    g = _norm(gissning)
    if not g:
        return False
    for s in svar:
        n = _norm(s) or s.lower()
        if g == n or (len(n) >= 3 and g.startswith(n)) or (len(n) >= 4 and difflib.SequenceMatcher(None, g, n).ratio() >= 0.8):
            return True
    return False


def gata(d: date) -> tuple[str, list[str]]:
    return GATOR[d.toordinal() % len(GATOR)]


def _gator(data: dict) -> dict:
    g = meriter._m(data).setdefault("gator", {})
    for k in sorted(g)[:-30]:  # spara bara en månad
        del g[k]
    return g


def gissa(data: dict, svar: str) -> None:
    idag = dt_util.now().date().isoformat()
    svar = re.sub(r"\s+", " ", str(svar or "")).strip()[:60]
    if not svar:
        raise ValueError("Skriv en gissning först.")
    _gator(data)[idag] = {"gissning": svar}


GATA_AI_PROMPT = (
    "Ett barn har gissat på en gåta. Avgör om barnets svar ska räknas som rätt.\n"
    "Gåta: {fraga}\nFacit (godkända svar): {svar}\nBarnets svar: {gissning}\n\n"
    "Räkna det som rätt om svaret betyder samma sak som facit, är en mer specifik variant av det (t.ex. tvättsvamp när facit är svamp), "
    "en synonym, eller ett annat svar som verkligen passar gåtans alla ledtrådar. Stavfel gör inget. "
    "Räkna det som fel om det bara delvis passar eller är en gissning som inte uppfyller gåtan.\n"
    'Svara ENDAST med JSON: {{"ratt": true/false, "varfor": "en kort mening till barnet"}}'
)


def gata_ai_fraga(data: dict) -> str | None:
    """Prompt till AI:n om gårdagens gissning inte matchar facit (annars None, då behövs ingen AI)."""
    igar = dt_util.now().date() - timedelta(days=1)
    post = _gator(data).get(igar.isoformat(), {})
    if post.get("visad") or not post.get("gissning"):
        return None
    fraga, svar = gata(igar)
    if ratt_svar(post["gissning"], svar):
        return None
    return GATA_AI_PROMPT.format(fraga=fraga, svar=", ".join(svar), gissning=post["gissning"])


def visa_svar(data: dict, ai: dict | None = None) -> dict:
    """Barnet öppnar gårdagens svar. Rätt gissning ger stjärnor (en gång). ai = AI:ns bedömning av ett svar som inte står i facit."""
    igar = dt_util.now().date() - timedelta(days=1)
    post = _gator(data).setdefault(igar.isoformat(), {})
    if post.get("visad"):
        return post
    post["visad"] = True
    fraga, svar = gata(igar)
    if post.get("gissning"):
        post["ratt"] = ratt_svar(post["gissning"], svar) or bool((ai or {}).get("ratt"))
        if (ai or {}).get("varfor"):
            post["varfor"] = str(ai["varfor"])[:200]
        if post["ratt"]:
            meriter.ge(data, P_GATA, "🧩 Du löste gåtan!", f"gata:{igar.isoformat()}", "🧩")
    return post


def _halsning(data: dict, namn: str) -> str:
    """En personlig rad om det finns något att säga, annars dagens pepp."""
    m = meriter._m(data)
    idag = dt_util.now().date()
    dagar = set(m.get("ovningsdagar", []))
    streak = meriter._streak(m.get("ovningsdagar", []))
    d = m.get("djur") or {}
    rader = []
    if streak >= 3:
        rader.append(f"🔥 {streak} dagar i rad, {namn}! Det är riktigt starkt.")
    if (idag - timedelta(days=1)).isoformat() in dagar:
        rader.append(f"Bra jobbat igår, {namn}! Fortsätt så idag. 🌟")
    elif d and dagar and (idag - timedelta(days=1)).isoformat() not in dagar and idag.isoformat() not in dagar:
        rader.append(f"{d.get('art', '')} {d.get('namn', 'Ditt husdjur')} har saknat dig! Lite plugg idag gör hen glad.")
    pepp = PEPP[(idag.toordinal() * 7) % len(PEPP)]
    if rader and idag.toordinal() % 3:
        return rader[idag.toordinal() % len(rader)]
    return pepp


def dagens(data: dict, namn: str) -> dict:
    idag = dt_util.now().date()
    igar = idag - timedelta(days=1)
    g = meriter._m(data).get("gator", {})
    i_post, g_post = g.get(idag.isoformat(), {}), g.get(igar.isoformat(), {})
    fraga_igar, svar_igar = gata(igar)
    return {
        "halsning": _halsning(data, namn),
        "gata": gata(idag)[0],
        "gissning": i_post.get("gissning", ""),
        "igar": {"gata": fraga_igar, "gissning": g_post.get("gissning", ""), "visad": bool(g_post.get("visad")),
                 "svar": svar_igar[0] if g_post.get("visad") else None, "ratt": g_post.get("ratt"), "varfor": g_post.get("varfor", "")},
        "p_gata": P_GATA,
    }


# ---------- egna rekord ----------
def rekord(data: dict) -> list[dict]:
    """Barnets bästa resultat någonsin. "ny" = satt den här veckan."""
    m = meriter._m(data)
    idag = dt_util.now().date()
    mandag = (idag - timedelta(days=idag.weekday())).isoformat()
    ut = []
    basta = None
    for f in data.get("forhor", []):
        n = len(f.get("fragor", []))
        if f.get("status") == "klart" and n >= 5:
            pct = round(100 * sum(1 for x in f.get("svar", []) if x.get("ratt")) / n)
            datum = (f.get("klart") or "")[:10]
            if not basta or pct > basta[0] or (pct == basta[0] and n > basta[2]):
                basta = (pct, f.get("namn", ""), n, datum)
    if basta:
        ut.append({"ikon": "🎯", "namn": "Bästa förhöret", "varde": f"{basta[0]} %", "info": f"{basta[1]} ({basta[2]} frågor)", "ny": basta[3] >= mandag})
    per_dag: dict[str, int] = {}
    for x in m["logg"]:
        if x["p"] > 0 and x.get("ikon") not in meriter.EJ_SKADA:
            per_dag[x["tid"][:10]] = per_dag.get(x["tid"][:10], 0) + x["p"]
    if per_dag:
        dag, p = max(per_dag.items(), key=lambda kv: (kv[1], kv[0]))
        ut.append({"ikon": "⭐", "namn": "Flest ⭐ på en dag", "varde": str(p), "info": dag, "ny": dag >= mandag})
    vp = meriter._vecko_poang(data)
    if vp:
        v, p = max(vp.items(), key=lambda kv: (kv[1], kv[0]))
        nu = "{}-W{:02d}".format(*idag.isocalendar()[:2])
        ut.append({"ikon": "📅", "namn": "Bästa veckan", "varde": f"{p} ⭐", "info": f"vecka {int(v[-2:])}", "ny": v == nu})
    dagar = m.get("ovningsdagar", [])
    if dagar:
        veckor: dict[str, int] = {}
        for d in dagar:
            ar, v, _ = date.fromisoformat(d).isocalendar()
            veckor[f"{ar}-W{v:02d}"] = veckor.get(f"{ar}-W{v:02d}", 0) + 1
        ut.append({"ikon": "📆", "namn": "Flest pluggdagar på en vecka", "varde": f"{max(veckor.values())} av 7", "info": "", "ny": False})
    svit, nu_svit = max(m.get("raknare", {}).get("basta_streak", 0), meriter._streak(dagar)), meriter._streak(dagar)
    if svit:
        ut.append({"ikon": "🔥", "namn": "Längsta svit", "varde": f"{svit} dagar", "info": "pågår nu!" if nu_svit == svit and svit > 1 else "", "ny": nu_svit == svit and svit > 1})
    if m.get("raknare", {}).get("rekord_max"):
        ut.append({"ikon": "⚡", "namn": "Glosrekord", "varde": str(m["raknare"]["rekord_max"]), "info": "", "ny": False})
    k = m.get("karta")
    if k:
        ut.append({"ikon": "🗺️", "namn": "Längst på kartan", "varde": f"nivå {k.get('niva', 1)}", "info": "", "ny": False})
    return ut


# ---------- husdjuret säger något ----------
FAKTA = [
    "Visste du att en snigel kan sova i flera år? 🐌",
    "Visste du att bläckfiskar har tre hjärtan? 🐙",
    "Visste du att hjärnan använder mer energi än nästan allt annat i kroppen? 🧠",
    "Visste du att sköldpaddor har funnits sedan dinosauriernas tid? 🐢",
    "Visste du att man lär sig bättre om man sover ordentligt? 😴",
    "Visste du att en blåval väger lika mycket som 30 elefanter? 🐋",
    "Visste du att det finns fler stjärnor i rymden än sandkorn på alla stränder? ✨",
]


def prat(data: dict) -> str:
    """En pratbubbla från husdjuret om det barnet faktiskt har gjort."""
    import random

    m = meriter._m(data)
    d = m.get("djur")
    if not d:
        return ""
    idag = dt_util.now().date()
    igar = (idag - timedelta(days=1)).isoformat()
    lista: list[str] = []
    for f in reversed(data.get("forhor", [])):
        if f.get("status") == "klart" and (f.get("klart") or "")[:10] >= igar:
            n = len(f.get("fragor", []))
            r = sum(1 for x in f.get("svar", []) if x.get("ratt"))
            if n and r / n >= 0.8:
                lista += [f"Wow, {r} av {n} på {f.get('namn', 'förhöret')}! 🤩", f"Jag visste att du skulle klara {f.get('namn', 'förhöret')}! 🎉"]
            elif n:
                lista.append(f"{f.get('namn', 'Förhöret')} var klurigt. Vi kör igen, vi två! 💪")
            break
    ovat = [g.get("namn", "") for a in data.get("amnen", []) for g in a.get("glosor", []) if idag.isoformat() in g.get("ovat_dagar", [])]
    if ovat:
        lista.append(f"Jag hörde dig öva {ovat[0]}. Du är så smart! 🧠")
    streak = meriter._streak(m.get("ovningsdagar", []))
    if streak >= 2:
        lista.append(f"{streak} dagar i rad! Jag blir starkare för varje dag. 💪")
    dagar = set(m.get("ovningsdagar", []))
    if idag.isoformat() not in dagar and igar not in dagar:
        lista += ["Jag är hungrig… på kunskap! 🍽️📚", "Ska vi plugga lite? Jag har saknat dig!"]
    if meriter._kompis_bastis(d):
        lista.append("Jag och min bästis är redo för äventyr! 💞")
    k = m.get("karta")
    if k and k.get("hp") and k["hp"] - k.get("skada", 0) <= k["hp"] * 0.2:
        lista.append("Monstret är nästan besegrat! Lite till! ⚔️")
    if d.get("art") == "🐍":  # Snake äter mardrömmar
        n = meriter.mardrommar_i_natt(idag.isoformat())
        mardrom = [f"Mums! I natt åt jag {n} mardröm{'mar' if n > 1 else ''}. Du kan sova lugnt! 😋🌙",
                   "Jag håller vakt i natt. Inga mardrömmar kommer förbi mig! 🐍🌙",
                   "Mardrömmar smakar lite som lakrits. Med salt! 😝",
                   "Ju mer du pluggar, desto större mardrömmar orkar jag äta! 💪🌙"]
        if dt_util.now().hour < 12:
            return mardrom[0]
        lista += mardrom[1:]
    if not lista or random.random() < 0.25:
        lista.append(random.choice(FAKTA + PEPP[:5]))
    return random.choice(lista)


# ---------- hejarop från föräldrarna ----------
HEJA_BOOST = (0, 5, 10, 20)  # ⭐ en förälder kan skicka med


def hejarop_ny(data: dict, text: str, boost: int, nar: str, varde: str, av: str) -> None:
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:300]
    if not text:
        raise ValueError("Skriv något till barnet.")
    if nar not in ("nu", "datum", "svit"):
        nar = "nu"
    if nar == "datum" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(varde or "")):
        raise ValueError("Välj ett datum.")
    if nar == "svit":
        try:
            varde = max(2, min(100, int(varde)))
        except (TypeError, ValueError) as err:
            raise ValueError("Skriv hur många dagar i rad.") from err
    lista = data.setdefault("hejarop", [])
    lista.append({"id": __import__("uuid").uuid4().hex[:10], "text": text, "boost": boost if boost in HEJA_BOOST else 0,
                  "nar": nar, "varde": varde if nar != "nu" else None, "av": str(av or "")[:40],
                  "skapad": dt_util.now().isoformat(timespec="minutes"), "last": None})
    del lista[:-50]


def _heja_redo(data: dict, h: dict) -> bool:
    if h["nar"] == "datum":
        return dt_util.now().date().isoformat() >= h["varde"]
    if h["nar"] == "svit":
        return meriter._streak(meriter._m(data).get("ovningsdagar", [])) >= int(h["varde"])
    return True


def hejarop_synliga(data: dict) -> list[dict]:
    """Det barnet får se: bara lappar som har "kommit fram" och inte är lästa än."""
    return [{k: h[k] for k in ("id", "text", "boost", "av")} for h in data.get("hejarop", []) if not h.get("last") and _heja_redo(data, h)]


def hejarop_las(data: dict, hid: str) -> None:
    h = next((x for x in data.get("hejarop", []) if x["id"] == hid and not x.get("last") and _heja_redo(data, x)), None)
    if not h:
        raise ValueError("Lappen finns inte.")
    h["last"] = dt_util.now().isoformat(timespec="minutes")
    if h.get("boost"):
        meriter.ge(data, int(h["boost"]), f"💌 Hejarop från {h.get('av') or 'mamma eller pappa'}", f"heja:{h['id']}", "💌")


# ---------- fokusläge: en timer medan husdjuret sover bredvid ----------
FOKUS_MIN = (10, 15, 20, 25)
P_FOKUS = {10: 5, 15: 8, 20: 10, 25: 12}
FOKUS_PER_DAG = 2  # så många fokuspass per dag ger ⭐


def fokus_start(data: dict, minuter: int) -> None:
    if minuter not in FOKUS_MIN:
        raise ValueError("Välj hur länge.")
    meriter._m(data)["fokus"] = {"start": dt_util.now().isoformat(timespec="seconds"), "min": minuter}


def fokus_klar(data: dict) -> int:
    """Timern är slut. Ger ⭐ om tiden verkligen har gått. Returnerar ⭐ (0 om dagens pass är slut)."""
    m = meriter._m(data)
    f = m.get("fokus")
    if not f:
        raise ValueError("Inget fokuspass pågår.")
    gatt = (dt_util.now() - dt_util.parse_datetime(f["start"])).total_seconds()
    if gatt < f["min"] * 60 - 5:
        raise ValueError("Tiden är inte slut än.")
    m.pop("fokus", None)
    idag = dt_util.now().date().isoformat()
    for n in range(1, FOKUS_PER_DAG + 1):
        if meriter.ge(data, P_FOKUS[f["min"]], f"⏱️ Fokuspass {f['min']} minuter", f"fokus:{idag}:{n}", "⏱️"):
            meriter.aktiv(data, idag)
            return P_FOKUS[f["min"]]
    return 0


def fokus_avbryt(data: dict) -> None:
    meriter._m(data).pop("fokus", None)


# ---------- husdjurets veckobrev till föräldrarna ----------
def husdjurets_brev(data: dict, namn: str) -> dict | None:
    """Ett kort brev från husdjuret om veckan som gått (de senaste 7 dagarna)."""
    m = meriter._m(data)
    d = m.get("djur")
    idag = dt_util.now().date()
    fran = (idag - timedelta(days=6)).isoformat()
    djur = f"{d.get('art', '')} {d.get('namn', 'Husdjuret')}" if d else "🐾 Husdjuret"
    dagar = sorted(x for x in m.get("ovningsdagar", []) if x >= fran)
    stj = sum(x["p"] for x in m["logg"] if x["p"] > 0 and x.get("ikon") not in meriter.EJ_SKADA and x["tid"][:10] >= fran)
    rader = []
    if dagar:
        rader.append(f"{namn} har pluggat {len(dagar)} av de senaste 7 dagarna och tjänat {stj} ⭐.")
    else:
        rader.append(f"Jag har saknat {namn} den här veckan. Det har inte blivit något plugg. 🥺")
    fh = [f for f in data.get("forhor", []) if f.get("status") == "klart" and (f.get("klart") or "")[:10] >= fran]
    for f in fh[-3:]:
        n = len(f.get("fragor", []))
        r = sum(1 for x in f.get("svar", []) if x.get("ratt"))
        rader.append(f"📋 Förhöret {f.get('namn', '')}: {r} av {n} rätt." + (" Så bra! 🎉" if n and r / n >= 0.9 else ""))
    ovat = sorted({g["namn"] for a in data.get("amnen", []) for g in a.get("glosor", []) if any(x >= fran for x in g.get("ovat_dagar", []))})
    if ovat:
        rader.append("📝 Vi har övat på " + ", ".join(ovat[:5]) + ("…" if len(ovat) > 5 else "") + ".")
    nya = [x for x in rekord(data) if x["ny"]]
    if nya:
        rader.append("🏅 Nytt rekord: " + ", ".join(f"{x['namn'].lower()} ({x['varde']})" for x in nya[:3]) + "!")
    streak = meriter._streak(m.get("ovningsdagar", []))
    if streak >= 3:
        rader.append(f"🔥 Just nu {streak} dagar i rad!")
    k = m.get("karta")
    if k:
        rader.append(f"🗺️ Tillsammans har vi kommit till nivå {k.get('niva', 1)} på kartan.")
    rader.append("Säg gärna till " + namn + " att jag är stolt! 💛" if dagar else "Kanske kan ni plugga lite tillsammans i helgen? 💛")
    return {"fran": djur, "titel": f"Veckobrev från {djur}", "rader": rader, "period": f"{fran} – {idag.isoformat()}"}


# ---------- födelsedag ----------
P_FODELSEDAG = 50


def fodelsedag_idag(data: dict) -> dict | None:
    f = data.get("fodelsedag") or ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f):
        return None
    idag = dt_util.now().date()
    if f[5:] != idag.isoformat()[5:]:
        return None
    nyckel = f"fodelsedag:{idag.year}"
    return {"alder": idag.year - int(f[:4]), "hamtad": nyckel in meriter._m(data)["nycklar"], "p": P_FODELSEDAG}


def fodelsedag_hamta(data: dict) -> None:
    f = fodelsedag_idag(data)
    if not f:
        raise ValueError("Det är inte din födelsedag idag.")
    if meriter.ge(data, P_FODELSEDAG, f"🎂 Grattis på {f['alder']}-årsdagen!", f"fodelsedag:{dt_util.now().year}", "🎂"):
        meriter.ge_sak(data, "g_partyhatt")


# ---------- julkalendern: en lucka om dagen 1–24 december ----------
# Vad som finns bakom luckorna. ("p", ⭐) / ("kort",) / ("sak", id) / ("energi", antal)
LUCKOR = {
    1: [("p", 10)], 2: [("kort",)], 3: [("energi", 3)], 4: [("p", 15)], 5: [("kort",)], 6: [("sak", "g_pepparkaka")],
    7: [("p", 10)], 8: [("energi", 3)], 9: [("kort",)], 10: [("p", 15)], 11: [("kort",)], 12: [("p", 20)],
    13: [("sak", "g_luciakrona"), ("p", 10)], 14: [("kort",)], 15: [("energi", 5)], 16: [("p", 15)], 17: [("kort",)],
    18: [("sak", "g_snogubbe")], 19: [("p", 20)], 20: [("kort",), ("kort",)], 21: [("sak", "g_snofall")], 22: [("p", 25)],
    23: [("sak", "g_julgran")], 24: [("sak", "g_tomteluva"), ("p", 100), ("kort", "legendarisk")],
}


def _jul_aktiv() -> bool:
    d = dt_util.now().date()
    return d.month == 12 and d.day <= 31


def julkalender(data: dict) -> dict | None:
    if not _jul_aktiv():
        return None
    idag = dt_util.now().date()
    oppna = meriter._m(data).get("jul", {}).get(str(idag.year), {})
    return {"dag": idag.day, "ar": idag.year, "luckor": [{"dag": n, "oppnad": str(n) in oppna, "kan": n <= idag.day,
                                                          "innehall": oppna.get(str(n))} for n in range(1, 25)]}


def oppna_lucka(data: dict, dag: int) -> list[str]:
    """Öppna en lucka (även en missad). Returnerar vad som fanns bakom den."""
    import random

    idag = dt_util.now().date()
    if not _jul_aktiv() or not 1 <= dag <= 24 or dag > idag.day:
        raise ValueError("Den luckan går inte att öppna än. 🎄")
    m = meriter._m(data)
    oppna = m.setdefault("jul", {}).setdefault(str(idag.year), {})
    if str(dag) in oppna:
        raise ValueError("Den luckan är redan öppnad.")
    ut = []
    for x in LUCKOR[dag]:
        if x[0] == "p":
            meriter.ge(data, x[1], f"🎄 Lucka {dag}", f"jul:{idag.year}:{dag}", "🎁")
            ut.append(f"+{x[1]} ⭐")
        elif x[0] == "energi":
            k = meriter._karta(data)
            k["energi"] = min(meriter.ENERGI_MAX, k.get("energi", 0) + x[1])
            ut.append(f"+{x[1]} ⚡")
        elif x[0] == "sak":
            meriter.ge_sak(data, x[1])
            s = meriter._sak(x[1]) or {}
            ut.append(f"{s.get('ikon', '🎁')} {s.get('namn', 'En överraskning')}")
        elif x[0] == "kort":
            vid = meriter.VARLDAR[random.randint(0, min(len(meriter.VARLDAR) - 1, (meriter._karta(data).get("niva", 1) - 1) // meriter.NIVA_PER_VARLD + 1))]["id"]
            kid = f"{vid}:9" if len(x) > 1 else f"{vid}:{random.randint(0, 8)}"
            meriter._kort_ge(data, kid)
            ut.append(f"🃏 {meriter._kort_info(kid)['namn']}")
    oppna[str(dag)] = ut
    return ut
