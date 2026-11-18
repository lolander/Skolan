"""Pennuppdrag: skrivuppdrag som barnet skriver för hand på papper och fotar.

Uppdragen börjar mycket små och växer sakta, steg för steg, så att barnet blir bekvämt med att uttrycka sig med pennan.
"""
from __future__ import annotations

import difflib
import random
import uuid

from homeassistant.util import dt as dt_util

from . import meriter

STEG = {
    1: {"namn": "1–2 meningar", "mal": 15, "info": "en eller två hela meningar"},
    2: {"namn": "3 meningar", "mal": 25, "info": "tre meningar"},
    3: {"namn": "5 meningar", "mal": 45, "info": "ungefär fem meningar"},
    4: {"namn": "Ett stycke", "mal": 70, "info": "ett helt stycke, ungefär 6–8 meningar"},
    5: {"namn": "Två stycken", "mal": 120, "info": "två stycken med var sitt innehåll"},
    6: {"namn": "En hel text", "mal": 180, "info": "en hel text med början, mitt och slut, gärna i flera stycken"},
}
TYPER = ["beskriv något du tycker om", "berätta om något som hänt dig", "skriv ett vykort eller brev till någon", "skriv en lista med varför",
         "hitta på en kort saga", "skriv vad du tycker och varför", "förklara hur man gör något", "skriv en dagboksanteckning",
         "beskriv en dröm eller en fantasiplats", "skriv om ditt husdjur i spelet", "skriv en dikt eller ramsa"]
GODKANDA_PER_STEG = 3  # så många godkända uppdrag innan nästa steg
MAX_PER_DAG = 2  # godkända uppdrag per dag som ger ⭐
BYTEN_PER_DAG = 3


def _p(data: dict) -> dict:
    return data.setdefault("penna", {"steg": 1, "klara_pa_steg": 0, "inlamnat": []})


def poang_for(steg: int) -> int:
    return 4 + 2 * steg  # 6, 8, 10, 12, 14, 16 ⭐


def status(data: dict) -> dict:
    p = _p(data)
    idag = dt_util.now().date().isoformat()
    steg = p.get("steg", 1)
    godk_idag = sum(1 for x in p.get("inlamnat", []) if x["tid"][:10] == idag and x.get("godkand"))
    return {"steg": steg, "steg_namn": STEG[steg]["namn"], "mal": STEG[steg]["mal"], "klara_pa_steg": p.get("klara_pa_steg", 0),
            "per_steg": GODKANDA_PER_STEG, "p": poang_for(steg), "bonus": 3, "aktiv": p.get("aktiv"), "idag": godk_idag, "max": MAX_PER_DAG,
            "kvar_idag": max(0, MAX_PER_DAG - godk_idag), "inlamnat": p.get("inlamnat", [])[-20:],
            "byten_kvar": BYTEN_PER_DAG - (p.get("byten", {}).get(idag, 0))}


def ny_typ(data: dict) -> str:
    senaste = [x.get("typ") for x in _p(data).get("inlamnat", [])[-4:]]
    val = [t for t in TYPER if t not in senaste] or TYPER
    return random.choice(val)


def satt_aktiv(data: dict, uppgift: str, tips: list, typ: str, byte: bool) -> dict:
    p = _p(data)
    if byte:
        idag = dt_util.now().date().isoformat()
        b = p.setdefault("byten", {})
        if b.get(idag, 0) >= BYTEN_PER_DAG:
            raise ValueError("Du har bytt uppdrag tre gånger idag. Testa det här!")
        p["byten"] = {idag: b.get(idag, 0) + 1}
    p["aktiv"] = {"id": uuid.uuid4().hex[:10], "uppgift": uppgift, "tips": tips, "typ": typ, "steg": p.get("steg", 1),
                  "skapad": dt_util.now().isoformat(timespec="minutes")}
    return p["aktiv"]


def dubblett(data: dict, hash_: str, text: str) -> str | None:
    """Samma foto eller (nästan) samma text som förut? Returnerar skälet."""
    for x in _p(data).get("inlamnat", []):
        if x.get("hash") == hash_:
            return "Det här fotot har redan lämnats in. Skriv en ny text!"
        if text and x.get("text") and len(text) > 20 and difflib.SequenceMatcher(None, text.lower(), x["text"].lower()).ratio() > 0.8:
            return "Den här texten liknar en som du redan har lämnat in. Skriv en ny text till uppdraget!"
    return None


def lamna_in(data: dict, bedomning: dict, fil: str, hash_: str) -> dict:
    """Spara inlämningen, godkänn eller inte, ge ⭐ och flytta steget."""
    p = _p(data)
    akt = p.get("aktiv") or {}
    steg = akt.get("steg", p.get("steg", 1))
    mal = STEG[steg]["mal"]
    idag = dt_util.now().date().isoformat()
    ord_ = int(bedomning.get("ord") or len(str(bedomning.get("text") or "").split()))
    skal = None
    if not bedomning.get("handskrivet"):
        skal = "Det ser inte ut som en text skriven för hand på papper. Skriv med penna och fota papperet."
    elif int(bedomning.get("passar") or 0) < 50:
        skal = "Texten verkar inte handla om uppdraget. Läs uppdraget igen och försök en gång till."
    elif ord_ < max(6, round(mal * 0.6)):
        skal = f"Lite för kort: {ord_} ord. Försök skriva ungefär {mal} ord."
    godkand = skal is None
    poang = 0
    if godkand:
        godk_idag = sum(1 for x in p.get("inlamnat", []) if x["tid"][:10] == idag and x.get("godkand"))
        if godk_idag < MAX_PER_DAG:
            kvalitet = (int(bedomning.get("handstil") or 0) + int(bedomning.get("tecken") or 0)) / 2
            poang = poang_for(steg) + (3 if kvalitet >= 80 else 0)
            meriter.ge(data, poang, f"🖊️ Pennuppdrag steg {steg}: {akt.get('uppgift', '')[:40]}", f"penna:{akt.get('id') or hash_}", "🖊️")
        meriter.aktiv(data, idag)
        if poang and akt.get("steg", steg) == p.get("steg", 1):  # bara uppdrag som ger ⭐ räknas, så att stegen tar några dagar
            p["klara_pa_steg"] = p.get("klara_pa_steg", 0) + 1
            if p["klara_pa_steg"] >= GODKANDA_PER_STEG and p.get("steg", 1) < max(STEG):
                p["steg"] = p.get("steg", 1) + 1
                p["klara_pa_steg"] = 0
                bedomning["nytt_steg"] = p["steg"]
        p.pop("aktiv", None)
    post = {"id": uuid.uuid4().hex[:10], "tid": dt_util.now().isoformat(timespec="minutes"), "uppgift": akt.get("uppgift", ""), "typ": akt.get("typ"),
            "steg": steg, "fil": fil, "hash": hash_, "text": str(bedomning.get("text") or "")[:3000], "ord": ord_, "godkand": godkand, "skal": skal,
            "p": poang, "handstil": int(bedomning.get("handstil") or 0), "tecken": int(bedomning.get("tecken") or 0),
            "bra": bedomning.get("bra", [])[:2], "tips": bedomning.get("tips", [])[:2], "pepp": str(bedomning.get("pepp") or "")[:200]}
    p["inlamnat"] = (p.get("inlamnat", []) + [post])[-200:]
    return {**post, "nytt_steg": bedomning.get("nytt_steg")}


def foralder_andra(data: dict, pid: str, godkann: bool) -> dict:
    """Föräldern underkänner (⭐ tas tillbaka) eller godkänner en inlämning AI:n sa nej till."""
    p = _p(data)
    x = next((y for y in p.get("inlamnat", []) if y["id"] == pid), None)
    if not x:
        raise ValueError("Inlämningen finns inte.")
    if godkann and not x["godkand"]:
        x["godkand"], x["skal"], x["av_foralder"] = True, None, True
        x["p"] = poang_for(x["steg"])
        meriter.ge(data, x["p"], f"🖊️ Pennuppdrag godkänt av förälder: {x['uppgift'][:40]}", f"penna_f:{x['id']}", "🖊️")
        if x["steg"] == p.get("steg", 1):
            p["klara_pa_steg"] = p.get("klara_pa_steg", 0) + 1
    elif not godkann and x["godkand"]:
        if x.get("p"):
            meriter.ge(data, -x["p"], f"🖊️ Pennuppdrag underkänt av förälder: {x['uppgift'][:40]}", None, "🖊️")
        x["godkand"], x["p"], x["skal"], x["av_foralder"] = False, 0, "Underkänd av förälder.", True
        if x["steg"] == p.get("steg", 1) and p.get("klara_pa_steg", 0) > 0:
            p["klara_pa_steg"] -= 1
    return x
