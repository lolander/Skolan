"""Plugga tillsammans: pluggstund och glosduell.

Deltagare är syskon i samma hem ("barn:<id>") eller vänner i andra hem ("van:<vänlänk>").
Varje hem sparar sina egna stunder och dueller i tillsammans.json och räknar sina egna barns framsteg.
Vänners framsteg hämtas direkt från vännens Home Assistant (samma vänlänk som vänkortet).
Bara det som behövs delas: smeknamn, poäng sedan stunden började, och i en duell glosorna och antal rätt.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.util import dt as dt_util

from . import meriter

STUND_MAL = 20  # ⭐ som var och en ska tjäna under pluggstunden (ungefär 15 minuters plugg)
STUND_BONUS = 10  # ⭐ till alla när alla som gått med har klarat målet
DUELL_ORD = 10  # högst så många ord i en duell
DUELL_TID = 10 * 60  # sekunder; sedan räknas duellen som slut
DUELL_DELTA, DUELL_VINST = 5, 5  # ⭐ för att spela klart, extra till vinnaren
MAX_AKTIVA = 20


def _fil(bas: Path) -> Path:
    return bas / "tillsammans.json"


def las(bas: Path) -> dict:
    try:
        t = json.loads(_fil(bas).read_text("utf-8")) if _fil(bas).exists() else {}
    except (OSError, ValueError):
        t = {}
    t.setdefault("stunder", [])
    t.setdefault("dueller", [])
    return t


def spara(bas: Path, t: dict) -> None:
    vecka_sen = (dt_util.now() - timedelta(days=7)).isoformat()
    t["stunder"] = [x for x in t["stunder"] if x["dag"] >= (dt_util.now().date() - timedelta(days=2)).isoformat()][-MAX_AKTIVA:]
    t["dueller"] = [x for x in t["dueller"] if x["start"] >= vecka_sen][-MAX_AKTIVA:]
    tmp = _fil(bas).with_suffix(".tmp")
    tmp.write_text(json.dumps(t, ensure_ascii=False), "utf-8")
    tmp.replace(_fil(bas))


def ny_id() -> str:
    return secrets.token_urlsafe(9)


def _poang_sedan(data: dict, start: str) -> int:
    return sum(x["p"] for x in meriter._m(data)["logg"]
               if x["p"] > 0 and x.get("ikon") not in meriter.EJ_SKADA and x.get("ikon") != "🤝" and x["tid"] >= start[:16])


def _hitta(lista: list[dict], sid: str) -> dict:
    x = next((y for y in lista if y["id"] == sid), None)
    if not x:
        raise ValueError("Den finns inte längre.")
    return x


def _deltagare(x: dict, ref: str) -> dict:
    d = next((y for y in x["deltagare"] if y["ref"] == ref), None)
    if not d:
        raise ValueError("Du är inte inbjuden.")
    return d


# ---------- pluggstund ----------
def stund_ny(t: dict, skapare: tuple[str, str], gaster: list[tuple[str, str]], sid: str | None = None, start: str | None = None) -> dict:
    """skapare/gäster = (ref, namn). Skaparen är med direkt."""
    nu = dt_util.now()
    if not gaster:
        raise ValueError("Bjud in minst en kompis eller ett syskon.")
    s = {"id": sid or ny_id(), "start": start or nu.isoformat(timespec="minutes"), "dag": (start or nu.isoformat())[:10],
         "mal": STUND_MAL, "bonus": STUND_BONUS, "deltagare": [{"ref": skapare[0], "namn": skapare[1], "med": True, "poang": 0}]
         + [{"ref": r, "namn": n, "med": False, "poang": 0} for r, n in gaster], "klar": False}
    t["stunder"].append(s)
    return s


def stund_ga_med(t: dict, sid: str, ref: str) -> dict:
    s = _hitta(t["stunder"], sid)
    if s["dag"] != dt_util.now().date().isoformat():
        raise ValueError("Pluggstunden är slut.")
    _deltagare(s, ref)["med"] = True
    return s


def stund_uppdatera(s: dict, lokala: dict[str, dict], vanner: dict[str, dict]) -> None:
    """lokala = {ref: barnets data}; vanner = {ref: {"med", "poang"}} hämtat från vännernas hem."""
    for d in s["deltagare"]:
        if d["ref"] in lokala:
            d["poang"] = _poang_sedan(lokala[d["ref"]], s["start"])
        elif d["ref"] in vanner:
            v = vanner[d["ref"]]
            d["med"] = d["med"] or bool(v.get("med"))
            d["poang"] = max(0, min(10**5, int(v.get("poang") or 0)))
    med = [d for d in s["deltagare"] if d["med"]]
    s["klar"] = len(med) >= 2 and all(d["poang"] >= s["mal"] for d in med)


def stund_belona(data: dict, s: dict) -> bool:
    if not s["klar"]:
        return False
    return meriter.ge(data, s["bonus"], f"🤝 Pluggstund klar! Alla nådde {s['mal']} ⭐", f"stund:{s['id']}", "🤝")


def stund_publik(s: dict, ref: str) -> dict:
    """Det en vän får veta om sitt barn i vår stund."""
    d = next((y for y in s["deltagare"] if y["ref"] == ref), None)
    return {"med": bool(d and d["med"]), "poang": d["poang"] if d else 0}


# ---------- glosduell ----------
def duell_ny(t: dict, skapare: tuple[str, str], gast: tuple[str, str], namn: str, ord_: list[dict], sid: str | None = None,
             start: str | None = None) -> dict:
    if not ord_:
        raise ValueError("Glosorna är tomma.")
    x = {"id": sid or ny_id(), "start": start or dt_util.now().isoformat(timespec="seconds"), "namn": str(namn)[:60],
         "ord": [{"fraga": str(o["fraga"])[:80], "facit": str(o["facit"])[:80], "fran": str(o.get("fran") or "")[:20],
                  "till": str(o.get("till") or "")[:20]} for o in ord_[:DUELL_ORD]],
         "deltagare": [{"ref": skapare[0], "namn": skapare[1], "med": True, "svar": {}, "forst": "", "klar": ""},
                       {"ref": gast[0], "namn": gast[1], "med": False, "svar": {}, "forst": "", "klar": ""}]}
    t["dueller"].append(x)
    return x


def _slut(x: dict) -> bool:
    try:
        gammal = (dt_util.now() - datetime.fromisoformat(x["start"])).total_seconds() > DUELL_TID
    except ValueError:
        gammal = True
    return gammal or all(d["klar"] for d in x["deltagare"] if d["med"]) and all(d["med"] for d in x["deltagare"])


def duell_ga_med(t: dict, sid: str, ref: str) -> dict:
    x = _hitta(t["dueller"], sid)
    if _slut(x):
        raise ValueError("Duellen är slut.")
    _deltagare(x, ref)["med"] = True
    return x


def duell_svara(t: dict, sid: str, ref: str, i: int, svar: str, ratt_fn) -> bool:
    x = _hitta(t["dueller"], sid)
    d = _deltagare(x, ref)
    if not d["med"] or d["klar"] or _slut(x):
        raise ValueError("Duellen är slut.")
    if not 0 <= i < len(x["ord"]) or str(i) in d["svar"]:
        raise ValueError("Den frågan är redan besvarad.")
    nu = dt_util.now().isoformat(timespec="seconds")
    ratt = bool(ratt_fn(str(svar or ""), x["ord"][i]["facit"]))
    d["svar"][str(i)] = ratt
    d["forst"] = d["forst"] or nu
    if len(d["svar"]) >= len(x["ord"]):
        d["klar"] = nu
    return ratt


def _tid(d: dict) -> float:
    try:
        return (datetime.fromisoformat(d["klar"]) - datetime.fromisoformat(d["forst"])).total_seconds()
    except (ValueError, TypeError):
        return 10**6


def duell_uppdatera(x: dict, vanner: dict[str, dict]) -> None:
    for d in x["deltagare"]:
        v = vanner.get(d["ref"])
        if v:
            d["med"] = d["med"] or bool(v.get("med"))
            n = max(0, min(len(x["ord"]), int(v.get("besvarade") or 0)))
            r = max(0, min(n, int(v.get("ratt") or 0)))
            d["svar"] = {str(i): i < r for i in range(n)}  # vi vet bara antalet, inte vilka
            d["klar"] = str(v.get("klar") or "")[:25] if n >= len(x["ord"]) else ""
            d["forst"] = str(v.get("forst") or "")[:25]


def duell_status(x: dict) -> dict:
    folk = [{"ref": d["ref"], "namn": d["namn"], "med": d["med"], "besvarade": len(d["svar"]), "ratt": sum(d["svar"].values()),
             "klar": bool(d["klar"]), "tid": round(_tid(d)) if d["klar"] else None} for d in x["deltagare"]]
    slut = _slut(x)
    vinnare = []
    if slut and all(f["med"] for f in folk):
        basta = max((f["ratt"], -(f["tid"] or 10**6)) for f in folk)
        vinnare = [f["ref"] for f in folk if (f["ratt"], -(f["tid"] or 10**6)) == basta]
    return {"id": x["id"], "namn": x["namn"], "antal": len(x["ord"]), "start": x["start"], "slut": slut, "folk": folk, "vinnare": vinnare}


def duell_publik(x: dict, ref: str) -> dict:
    d = next((y for y in x["deltagare"] if y["ref"] == ref), None) or {"med": False, "svar": {}, "klar": "", "forst": ""}
    return {"med": d["med"], "besvarade": len(d["svar"]), "ratt": sum(d["svar"].values()), "klar": d["klar"], "forst": d["forst"]}


def duell_belona(data: dict, x: dict, ref: str) -> bool:
    st = duell_status(x)
    jag = next((f for f in st["folk"] if f["ref"] == ref), None)
    if not st["slut"] or not jag or not jag["klar"]:
        return False
    vann = ref in st["vinnare"] and len(st["vinnare"]) == 1
    oavgjort = ref in st["vinnare"] and len(st["vinnare"]) > 1
    p = DUELL_DELTA + (DUELL_VINST if vann else 0)
    text = "🥇 Du vann glosduellen!" if vann else "🤝 Oavgjort i glosduellen!" if oavgjort else "⚔️ Bra kämpat i glosduellen!"
    return meriter.ge(data, p, f"{text} ({jag['ratt']}/{st['antal']})", f"duell:{x['id']}", "⚔️")


def duell_for_barn(x: dict, ref: str) -> dict:
    """Det barnet ser: frågorna utan facit, och vad hen själv svarat."""
    d = next((y for y in x["deltagare"] if y["ref"] == ref), None)
    return {**duell_status(x), "fragor": [{"fraga": o["fraga"], "fran": o["fran"], "till": o["till"]} for o in x["ord"]],
            "mina": d["svar"] if d else {}, "jag": ref, "facit": [o["facit"] for o in x["ord"]] if _slut(x) else None}
