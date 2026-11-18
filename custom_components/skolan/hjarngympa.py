"""Hjärngympa: korta hjärnspel. Dagens tre spel ger stjärnor och räknas för sviten; sedan fritt spel utan belöning.

Varje barn har en egen nivå (1-10) per spel som justeras efter dagens spel. Poängen (0-100 per spel) räknas mot
barnets egen nivå, så syskon i olika åldrar kan tävla rättvist.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from . import skrivkrav

SPEL = {
    "rakna": {"namn": "Snabbräkning", "ikon": "🔢", "max": 80},
    "minne": {"namn": "Minnesrutan", "ikon": "🧠", "max": 20},
    "folj": {"namn": "Talföljder", "ikon": "🔮", "max": 60},
    "farg": {"namn": "Färgfällan", "ikon": "🎨", "max": 80},
    "udda": {"namn": "Hitta den udda", "ikon": "🔍", "max": 80},
}
# Så många rätt som ger 100 poäng på varje nivå (1-10). Minnesrutan räknas för sig (se _poang).
MAL = {
    "rakna": [20, 18, 16, 16, 15, 13, 12, 11, 10, 10],
    "folj": [12, 11, 10, 9, 8, 8, 7, 7, 6, 6],
    "farg": [18, 18, 17, 17, 16, 16, 15, 15, 14, 14],
    "udda": [14, 13, 13, 12, 12, 11, 11, 10, 10, 9],
}
DAGLIGA = 3
P_DAGENS = 10  # alla dagens spel klara
SPARA_DAGAR = 60


def _start_niva(data: dict) -> int:
    """Första gången: ungefär efter ålder (9 år = nivå 2, 13 år = nivå 6)."""
    try:
        f = date.fromisoformat(str(data.get("fodelsedag"))[:10])
    except ValueError:
        return 3
    nu = dt_util.now().date()
    alder = nu.year - f.year - ((nu.month, nu.day) < (f.month, f.day))
    return max(1, min(6, alder - 7))


def minne_start(niva: int) -> int:
    """Så lång är första följden i Minnesrutan på den här nivån."""
    return 2 + niva // 3


def _poang(spel: str, niva: int, raw: int) -> int:
    if spel == "minne":
        return max(0, min(100, (raw - minne_start(niva) + 1) * 20))
    return max(0, min(100, round(100 * raw / MAL[spel][niva - 1])))


def dagens_spel(dag: str) -> list[str]:
    """Samma tre spel för alla barn samma dag."""
    return random.Random(f"hjarngympa:{dag}").sample(sorted(SPEL), DAGLIGA)


def _h(data: dict, barn: str) -> dict:
    h = data.setdefault("hjarngympa", {})
    h.setdefault("niva", {})
    for s in SPEL:
        h["niva"].setdefault(s, _start_niva(data))
    h.setdefault("dagar", {})
    h.setdefault("basta", {})
    return h


def status(data: dict, barn: str) -> dict:
    h = data.get("hjarngympa") or {}
    idag = dt_util.now().date().isoformat()
    dagens = dagens_spel(idag)
    gjort = (h.get("dagar") or {}).get(idag, {})
    niva = {s: (h.get("niva") or {}).get(s, _start_niva(data)) for s in SPEL}
    return {
        "spel": SPEL, "mal": MAL, "niva": niva, "basta": h.get("basta", {}),
        "dagens": [{"id": s, "klar": s in gjort, "p": gjort.get(s, {}).get("p")} for s in dagens],
        "klar": all(s in gjort for s in dagens), "summa": sum(x.get("p", 0) for s, x in gjort.items() if s in dagens),
        "belonung": P_DAGENS, "skrivkrav": skrivkrav.status(data),
    }


def resultat(data: dict, barn: str, spel: str, raw: int, daglig: bool) -> dict:
    if spel not in SPEL:
        raise ValueError("Okänt spel.")
    h = _h(data, barn)
    raw = max(0, min(SPEL[spel]["max"], int(raw)))
    idag = dt_util.now().date().isoformat()
    niva = h["niva"][spel]
    p = _poang(spel, niva, raw)
    nytt = raw > h["basta"].get(spel, 0)
    if nytt:
        h["basta"][spel] = raw
    ut = {"p": p, "raw": raw, "nytt": nytt, "niva": niva, "stjarnor": 0, "ny_niva": None}
    gjort = h["dagar"].setdefault(idag, {})
    if daglig and spel in dagens_spel(idag) and spel not in gjort:
        gjort[spel] = {"p": p, "raw": raw, "niva": niva}
        # nivån ändras bara av dagens spel (en gång per spel och dag), så den inte kan fuskas ner i fritt spel
        if p >= 100 and niva < 10:
            h["niva"][spel] = ut["ny_niva"] = niva + 1
        elif p < 50 and niva > 1:
            h["niva"][spel] = ut["ny_niva"] = niva - 1
        if all(s in gjort for s in dagens_spel(idag)):
            summa = sum(gjort[s]["p"] for s in dagens_spel(idag))
            ut["stjarnor"], ut["vantar"] = skrivkrav.belona(data, P_DAGENS, f"🧠 Dagens hjärngympa klar ({summa} poäng)", f"hjarngympa:{idag}", "🧠")
    else:
        h["fri"] = h.get("fri", 0) + 1
    gamla = (dt_util.now().date() - timedelta(days=SPARA_DAGAR)).isoformat()
    for d in [d for d in h["dagar"] if d < gamla]:
        del h["dagar"][d]
    ut["status"] = status(data, barn)
    return ut


def tavling(barnen: list[tuple[dict, dict]]) -> dict:
    """Syskontävlingen: dagens poäng och veckans vinster. barnen = [(conf-barn, data), ...]."""
    nu = dt_util.now().date()
    mandag = nu - timedelta(days=nu.weekday())
    dagar = [(mandag + timedelta(days=i)).isoformat() for i in range(7)]

    def summa(data: dict, dag: str) -> int | None:
        gjort = ((data.get("hjarngympa") or {}).get("dagar") or {}).get(dag, {})
        spel = dagens_spel(dag)
        return sum(gjort[s]["p"] for s in spel) if all(s in gjort for s in spel) else None

    rader = [{"id": b["id"], "namn": b["namn"], "vecka": [summa(d, dag) for dag in dagar], "vinster": 0,
              "idag": sum(x.get("p", 0) for x in (((d.get("hjarngympa") or {}).get("dagar") or {}).get(nu.isoformat(), {})).values())}
             for b, d in barnen]
    for i, dag in enumerate(dagar):
        if dag > nu.isoformat():
            break
        varden = [r["vecka"][i] for r in rader if r["vecka"][i] is not None]
        if len(varden) >= 2:  # en vinst kräver att minst två har spelat klart den dagen
            for r in rader:
                if r["vecka"][i] is not None and r["vecka"][i] == max(varden):
                    r["vinster"] += 1
    return {"dagar": dagar, "idag": nu.isoformat(), "rader": rader, "max": 100 * DAGLIGA}


def _test() -> None:  # pragma: no cover
    assert _poang("minne", 2, 2) == 20 and _poang("minne", 2, 6) == 100
    assert _poang("rakna", 1, 20) == 100 and _poang("rakna", 1, 10) == 50
    assert len(set(dagens_spel(date(2026, 1, 1).isoformat()))) == 3
