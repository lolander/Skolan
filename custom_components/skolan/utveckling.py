"""Min utveckling: hur barnet har blivit bättre (förr jämfört med nu), räknat på det appen redan sparar.

Varje mått jämför barnets första två veckor med data mot de senaste två veckorna. Finns det för lite historik
visas startvärdet och när jämförelsen börjar.
"""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from . import hjarngympa

PERIOD = 14  # dagar i varje jämförelseperiod
MIN_SPANN = 21  # så länge sedan första mätningen måste vara för att jämföra


def _d(t: str) -> date | None:
    try:
        return date.fromisoformat(str(t)[:10])
    except ValueError:
        return None


def _jamfor(punkter: list[tuple[date, float]], idag: date, hur: str = "snitt") -> dict | None:
    """punkter = [(dag, värde)]. Returnerar {da, nu, fran, klar} eller None om inget finns."""
    punkter = sorted(p for p in punkter if p[0])
    if not punkter:
        return None
    start = punkter[0][0]
    if hur == "niva":  # nivåer: första jämfört med nuvarande
        if (idag - start).days < MIN_SPANN:
            return {"da": punkter[-1][1], "nu": None, "fran": (start + timedelta(days=MIN_SPANN)).isoformat(), "klar": False}
        return {"da": punkter[0][1], "nu": punkter[-1][1], "fran": start.isoformat(), "klar": True}
    samla = (lambda v: round(sum(v) / len(v), 1)) if hur == "snitt" else max
    da = [v for t, v in punkter if t < start + timedelta(days=PERIOD)]
    if (idag - start).days < MIN_SPANN:
        return {"da": samla(da), "nu": None, "fran": (start + timedelta(days=MIN_SPANN)).isoformat(), "klar": False}
    nu = [v for t, v in punkter if t > idag - timedelta(days=PERIOD)]
    return {"da": samla(da), "nu": samla(nu) if nu else None, "fran": start.isoformat(), "klar": bool(nu)}


def matt(data: dict) -> dict:
    idag = dt_util.now().date()
    ut = []

    def lagg(id_, ikon, namn, enhet, j, hogre_battre=True, forklaring=""):
        if not j:
            return
        battre = j["klar"] and j["nu"] is not None and (j["nu"] > j["da"] if hogre_battre else j["nu"] < j["da"])
        ut.append({"id": id_, "ikon": ikon, "namn": namn, "enhet": enhet, **j, "battre": battre, "forklaring": forklaring})

    # Glosövning: andel rätt på första försöket
    glos = [(_d(r.get("datum")), 100 * r["ratt"] / r["av"]) for a in data.get("amnen", []) for g in a.get("glosor", [])
            for r in g.get("resultat", []) if r.get("av")]
    lagg("glosor", "✏️", "Rätt direkt när du övar glosor", "%", _jamfor(glos, idag), forklaring="Hur många ord du kan på första försöket.")

    # Förhör: andel rätt
    forhor = [(_d(f.get("klart")), 100 * sum(1 for s in f.get("svar", []) if s.get("ratt")) / len(f["fragor"]))
              for f in data.get("forhor", []) if f.get("klart") and f.get("fragor")]
    lagg("forhor", "📋", "Rätt på förhör", "%", _jamfor(forhor, idag))

    # Hjärngympa: nivån i varje spel
    h = data.get("hjarngympa") or {}
    for spel, info in hjarngympa.SPEL.items():
        p = [(_d(dag), x[spel]["niva"]) for dag, x in (h.get("dagar") or {}).items() if spel in x]
        if p:
            p.append((idag, (h.get("niva") or {}).get(spel, p[-1][1])))
            lagg(f"hj_{spel}", info["ikon"], f"{info['namn']} (nivå)", "", _jamfor(p, idag, "niva"))

    # Mattemonster: rätt på 60 sekunder (det sätt barnet spelar mest)
    mh = (data.get("matte") or {}).get("historik", [])
    if mh:
        vanligast = max({(x["typ"], x["niva"]) for x in mh}, key=lambda k: sum(1 for x in mh if (x["typ"], x["niva"]) == k))
        p = [(_d(x["tid"]), x["poang"]) for x in mh if (x["typ"], x["niva"]) == vanligast]
        lagg("matte", "🔢", "Mattemonster, rätt på 60 s", "rätt", _jamfor(p, idag))

    # Läsflyt: ord per minut
    lf = [(_d(x.get("tid")), x["wpm"]) for x in (data.get("lasflyt") or []) if x.get("ok")]
    lagg("lasflyt", "📖", "Läshastighet", "ord/min", _jamfor(lf, idag))

    # Pluggdagar per vecka
    dagar = sorted(d for d in (_d(x) for x in data.get("meriter", {}).get("ovningsdagar", [])) if d)
    if dagar:
        start = dagar[0]
        if (idag - start).days >= MIN_SPANN:
            da = sum(1 for d in dagar if d < start + timedelta(days=PERIOD)) / (PERIOD / 7)
            nu = sum(1 for d in dagar if d > idag - timedelta(days=PERIOD)) / (PERIOD / 7)
            j = {"da": round(da, 1), "nu": round(nu, 1), "fran": start.isoformat(), "klar": True}
        else:
            j = {"da": round(len(dagar) / max(1, ((idag - start).days + 1) / 7), 1), "nu": None,
                 "fran": (start + timedelta(days=MIN_SPANN)).isoformat(), "klar": False}
        lagg("dagar", "🔥", "Pluggdagar i veckan", "dagar", j)

    r = data.get("meriter", {}).get("raknare", {})
    totalt = [
        ("⭐", "stjärnor intjänade", data.get("meriter", {}).get("intjanat", 0)),
        ("✏️", "glosövningar", r.get("ovningar", 0)),
        ("📋", "förhör klara", sum(1 for f in data.get("forhor", []) if f.get("klart"))),
        ("📖", "läsläxor klara", r.get("las_klara", 0)),
        ("🔥", "dagar i rad som bäst", r.get("basta_streak", 0)),
    ]
    return {"matt": ut, "totalt": [{"ikon": i, "text": t, "antal": n} for i, t, n in totalt if n],
            "battre": [m for m in ut if m["battre"]]}


def notis_text(data: dict) -> str | None:
    """Månadens notis: den största förbättringen, eller None om inget har blivit bättre än."""
    b = matt(data)["battre"]
    if not b:
        return None
    m = max(b, key=lambda x: (x["nu"] - x["da"]) / (abs(x["da"]) or 1))
    enhet = f" {m['enhet']}" if m["enhet"] and m["enhet"] != "%" else m["enhet"]
    return f"{m['ikon']} {m['namn']}: från {m['da']:g}{enhet} till {m['nu']:g}{enhet}! Se allt du har blivit bättre på."
