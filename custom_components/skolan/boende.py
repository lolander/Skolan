"""Växelvis boende: vilket hem barnet är i, överlämning och var sakerna finns.

data["boende"] = {"aktiv", "hem": [{"id", "namn", "foraldrar": [användar-id], "annat_system": bool}], "start": ÅÅÅÅ-MM-DD
(första dagen i en period hos hem[0]), "dagar": 7 (periodens längd), "bytestid": "HH:MM", "undantag": [{"fran", "till", "hem"}]}
data["saker"] = [{"id", "namn", "hem"}]
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

from homeassistant.util import dt as dt_util

PERIODER = {7: "Varannan vecka", 14: "Varannan tvåveckorsperiod", 3: "Var tredje dag", 2: "Varannan dag"}
STD_SAKER = ["🎒 Skolväskan", "🩳 Gympapåsen", "📚 Läseboken", "🧮 Matteboken", "💻 Laddaren"]


def _b(data: dict) -> dict:
    return data.get("boende") or {}


def aktiv(data: dict) -> bool:
    b = _b(data)
    return bool(b.get("aktiv")) and len(b.get("hem", [])) == 2 and bool(b.get("start"))


def hem_for(data: dict, dag: date) -> dict | None:
    """Hemmet barnet är i en viss dag (efter bytestiden räknas bytesdagen till det nya hemmet)."""
    if not aktiv(data):
        return None
    b = _b(data)
    hem = b["hem"]
    iso = dag.isoformat()
    for u in b.get("undantag", []):
        if u.get("fran", "") <= iso <= u.get("till", ""):
            return next((h for h in hem if h["id"] == u.get("hem")), None)
    try:
        start = date.fromisoformat(b["start"])
    except ValueError:
        return None
    n = max(1, int(b.get("dagar") or 7))
    return hem[((dag - start).days // n) % 2]


def bytesdag(data: dict, dag: date) -> bool:
    return aktiv(data) and hem_for(data, dag) is not hem_for(data, dag - timedelta(days=1))


def nasta_byte(data: dict, fran: date) -> date | None:
    if not aktiv(data):
        return None
    for i in range(1, 60):
        d = fran + timedelta(days=i)
        if bytesdag(data, d):
            return d
    return None


def foraldrar_for(data: dict, dag: date, alla: list[str]) -> list[str]:
    """Föräldrarna (användar-id) som ska få notiser om barnet en viss dag. Alla om växelvis boende inte är påslaget."""
    h = hem_for(data, dag)
    if not h:
        return list(alla)
    if h.get("annat_system"):
        return []  # den andra föräldern får notiserna från sitt eget Läxspelet
    egna = [x for x in h.get("foraldrar", []) if x in alla]
    return egna or list(alla)


def spara(data: dict, body: dict, alla: list[str]) -> dict:
    gammal = _b(data)
    hem = []
    for i, h in enumerate((body.get("hem") or [])[:2]):
        hem.append({"id": f"h{i + 1}", "namn": re.sub(r"\s+", " ", str(h.get("namn") or f"Hem {i + 1}")).strip()[:30],
                    "foraldrar": [x for x in (h.get("foraldrar") or []) if x in alla], "annat_system": bool(h.get("annat_system"))})
    if len(hem) != 2:
        raise ValueError("Fyll i båda hemmen.")
    dagar = int(body.get("dagar") or 7)
    if dagar not in PERIODER:
        dagar = 7
    # "Den här perioden bor barnet hos …" + bytesdag -> start för en period hos hem[0]
    idag = dt_util.now().date()
    bytesdag_ = int(body.get("bytesdag") if str(body.get("bytesdag", "")).isdigit() else 4)
    senaste = idag - timedelta(days=(idag.weekday() - bytesdag_) % 7) if dagar in (7, 14) else idag
    nu_index = 1 if body.get("nu") == "1" else 0
    start = senaste - timedelta(days=dagar * nu_index)
    tid = str(body.get("bytestid") or "17:00")
    b = {"aktiv": bool(body.get("aktiv")), "hem": hem, "dagar": dagar, "start": start.isoformat(),
         "bytesdag": bytesdag_, "bytestid": tid if re.fullmatch(r"\d{1,2}:\d{2}", tid) else "17:00", "undantag": gammal.get("undantag", [])}
    data["boende"] = b
    if b["aktiv"] and not data.get("saker"):
        data["saker"] = [{"id": uuid.uuid4().hex[:8], "namn": n, "hem": hem[nu_index]["id"]} for n in STD_SAKER]
    return b


def undantag(data: dict, fran: str, till: str, hem_id: str, bort: str | None = None) -> None:
    b = _b(data)
    lista = b.setdefault("undantag", [])
    if bort:
        b["undantag"] = [u for u in lista if u.get("id") != bort]
        return
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", fran or "") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", till or "")) or till < fran:
        raise ValueError("Välj från och till.")
    if hem_id not in {h["id"] for h in b.get("hem", [])}:
        raise ValueError("Välj hem.")
    lista.append({"id": uuid.uuid4().hex[:8], "fran": fran, "till": till, "hem": hem_id})
    b["undantag"] = sorted(lista, key=lambda u: u["fran"])[-30:]


def sak(data: dict, op: str, body: dict) -> None:
    saker = data.setdefault("saker", [])
    hem = {h["id"] for h in _b(data).get("hem", [])}
    if op == "sak_ny":
        namn = re.sub(r"\s+", " ", str(body.get("namn") or "")).strip()[:40]
        if not namn:
            raise ValueError("Skriv vad det är.")
        if len(saker) >= 40:
            raise ValueError("Ta bort något först.")
        saker.append({"id": uuid.uuid4().hex[:8], "namn": namn, "hem": body.get("hem") if body.get("hem") in hem else next(iter(hem), "")})
    elif op == "sak_flytta":
        s = next((x for x in saker if x["id"] == body.get("id")), None)
        if s and body.get("hem") in hem:
            s["hem"] = body["hem"]
    elif op == "sak_bort":
        data["saker"] = [x for x in saker if x["id"] != body.get("id")]


def status(data: dict, namn: dict[str, str]) -> dict | None:
    """Till panelen: hemmen, var barnet är idag, nästa byte, sakerna och undantagen. namn: användar-id -> namn."""
    b = _b(data)
    if not b:
        return None
    idag = dt_util.now().date()
    h = hem_for(data, idag)
    nb = nasta_byte(data, idag)
    return {**b, "aktiv": aktiv(data), "idag": h["id"] if h else None, "idag_namn": h["namn"] if h else None,
            "nasta_byte": nb.isoformat() if nb else None, "nasta_hem": (hem_for(data, nb) or {}).get("namn") if nb else None,
            "saker": data.get("saker", []), "foraldrar_namn": namn}


def overlamning(data: dict, dag: date, uppdrag_text: list[str], skolinfo_text: list[str]) -> dict | None:
    """Text till föräldrarna på bytesdagen: vad som gäller och vad som ska med."""
    if not bytesdag(data, dag):
        return None
    ny, gammal = hem_for(data, dag), hem_for(data, dag - timedelta(days=1))
    saker_gamla = [s["namn"] for s in data.get("saker", []) if s.get("hem") == gammal["id"]]
    rader = []
    if uppdrag_text:
        rader.append("📚 " + "; ".join(uppdrag_text[:6]))
    if skolinfo_text:
        rader.append("📌 " + "; ".join(skolinfo_text[:4]))
    if saker_gamla:
        rader.append(f"🎒 Ligger hos {gammal['namn']}: " + ", ".join(saker_gamla) + ". Ska något med?")
    return {"till": ny, "fran": gammal, "text": "\n".join(rader) or "Inga läxor eller prov just nu. 🎉"}
