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
VECKA_MAL = 5  # godkända uppdrag på en vecka = Veckans penna
P_VECKA = 40
SVIT_MAX = 10  # pennsvit: +2 ⭐ per dag i rad, högst +10
BONUS_KVALITET = 5
GODKANDA_PER_STEG = 3  # så många godkända uppdrag innan nästa steg
MAX_PER_DAG = 2  # godkända uppdrag per dag som ger ⭐
BYTEN_PER_DAG = 3


def _p(data: dict) -> dict:
    return data.setdefault("penna", {"steg": 1, "klara_pa_steg": 0, "inlamnat": []})


def poang_for(steg: int) -> int:
    return 10 + 4 * steg  # 14, 18, 22, 26, 30, 34 ⭐


def _godkanda_dagar(p: dict) -> list[str]:
    return sorted({x["tid"][:10] for x in p.get("inlamnat", []) if x.get("godkand")})


def svit(p: dict) -> int:
    """Dagar i rad (till och med idag eller igår) med minst ett godkänt pennuppdrag."""
    from datetime import date, timedelta
    dagar = set(_godkanda_dagar(p))
    d = dt_util.now().date()
    if d.isoformat() not in dagar:
        d -= timedelta(days=1)
    n = 0
    while d.isoformat() in dagar:
        n += 1
        d -= timedelta(days=1)
    return n


def vecka(p: dict) -> int:
    from datetime import timedelta
    idag = dt_util.now().date()
    mandag = (idag - timedelta(days=idag.weekday())).isoformat()
    return sum(1 for x in p.get("inlamnat", []) if x.get("godkand") and x["tid"][:10] >= mandag)


def status(data: dict) -> dict:
    p = _p(data)
    idag = dt_util.now().date().isoformat()
    steg = p.get("steg", 1)
    godk_idag = sum(1 for x in p.get("inlamnat", []) if x["tid"][:10] == idag and x.get("godkand"))
    sv = svit(p)
    nasta_sak = next((x for x in meriter.PENNA_SAKER if x["steg_penna"] > steg), None)
    return {"steg": steg, "steg_namn": STEG[steg]["namn"], "mal": STEG[steg]["mal"], "klara_pa_steg": p.get("klara_pa_steg", 0),
            "per_steg": GODKANDA_PER_STEG, "p": poang_for(steg), "bonus": BONUS_KVALITET, "aktiv": p.get("aktiv"), "val": p.get("val"),
            "svit": sv, "svit_bonus": min(SVIT_MAX, 2 * (sv + (0 if godk_idag else 1))), "vecka": vecka(p), "vecka_mal": VECKA_MAL, "vecka_p": P_VECKA,
            "nasta_sak": nasta_sak, "saker": [x for x in meriter.PENNA_SAKER if x["steg_penna"] <= steg], "idag": godk_idag, "max": MAX_PER_DAG,
            "kvar_idag": max(0, MAX_PER_DAG - godk_idag), "inlamnat": p.get("inlamnat", [])[-20:],
            "byten_kvar": BYTEN_PER_DAG - (p.get("byten", {}).get(idag, 0))}


def ny_typ(data: dict) -> str:
    senaste = [x.get("typ") for x in _p(data).get("inlamnat", [])[-4:]]
    val = [t for t in TYPER if t not in senaste] or TYPER
    return random.choice(val)


def satt_val(data: dict, val: list[dict], byte: bool) -> list[dict]:
    """Tre uppdrag att välja mellan."""
    p = _p(data)
    if byte:
        idag = dt_util.now().date().isoformat()
        b = p.setdefault("byten", {})
        if b.get(idag, 0) >= BYTEN_PER_DAG:
            raise ValueError("Du har fått nya förslag tre gånger idag. Välj ett av dessa, eller hitta på ett eget!")
        p["byten"] = {idag: b.get(idag, 0) + 1}
    p["val"] = val
    p.pop("aktiv", None)
    return val


def satt_aktiv(data: dict, uppgift: str, tips: list, typ: str, byte: bool) -> dict:
    p = _p(data)
    p.pop("val", None)
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
        extra = {}
        if godk_idag < MAX_PER_DAG:
            kvalitet = (int(bedomning.get("handstil") or 0) + int(bedomning.get("tecken") or 0)) / 2
            sv_bonus = min(SVIT_MAX, 2 * (svit(p) + (0 if godk_idag else 1))) if not godk_idag else 0
            poang = poang_for(steg) + (BONUS_KVALITET if kvalitet >= 80 else 0) + sv_bonus
            extra = {"bas": poang_for(steg), "kvalitet": BONUS_KVALITET if kvalitet >= 80 else 0, "svit": sv_bonus}
            meriter.ge(data, poang, f"🖊️ Pennuppdrag steg {steg}: {akt.get('uppgift', '')[:40]}", f"penna:{akt.get('id') or hash_}", "🖊️")
            kista = "guld" if steg >= 4 else "silver"
            if meriter.kista_ge(data, kista, "🖊️ Pennuppdrag", f"pennakista:{akt.get('id') or hash_}"):
                extra["kista"] = kista
        bedomning["extra"] = extra
        meriter.aktiv(data, idag)
        if poang and akt.get("steg", steg) == p.get("steg", 1):  # bara uppdrag som ger ⭐ räknas, så att stegen tar några dagar
            p["klara_pa_steg"] = p.get("klara_pa_steg", 0) + 1
            if p["klara_pa_steg"] >= GODKANDA_PER_STEG and p.get("steg", 1) < max(STEG):
                p["steg"] = p.get("steg", 1) + 1
                p["klara_pa_steg"] = 0
                bedomning["nytt_steg"] = p["steg"]
                sak = next((x for x in meriter.PENNA_SAKER if x["steg_penna"] == p["steg"]), None)
                if sak and meriter.ge_sak(data, sak["id"]):
                    bedomning["ny_sak"] = sak
                meriter.kista_ge(data, "guld", f"🖊️ Nytt pennsteg: {STEG[p['steg']]['namn']}", f"pennasteg:{p['steg']}")
        p.pop("aktiv", None)
    if godkand and poang:
        from datetime import timedelta
        d0 = dt_util.now().date()
        vnyckel = f"pennavecka:{(d0 - timedelta(days=d0.weekday())).isoformat()}"
        if vecka(p) + 1 >= VECKA_MAL and meriter.ge(data, P_VECKA, "🖊️ Veckans penna: 5 pennuppdrag på en vecka!", vnyckel, "🏆"):
            meriter.kista_ge(data, "guld", "🖊️ Veckans penna", vnyckel + ":kista")
            bedomning["vecka"] = P_VECKA
    post = {"id": uuid.uuid4().hex[:10], "tid": dt_util.now().isoformat(timespec="minutes"), "uppgift": akt.get("uppgift", ""), "typ": akt.get("typ"),
            "steg": steg, "fil": fil, "hash": hash_, "text": str(bedomning.get("text") or "")[:3000], "ord": ord_, "godkand": godkand, "skal": skal,
            "p": poang, "handstil": int(bedomning.get("handstil") or 0), "tecken": int(bedomning.get("tecken") or 0),
            "bra": bedomning.get("bra", [])[:2], "tips": bedomning.get("tips", [])[:2], "pepp": str(bedomning.get("pepp") or "")[:200],
            "djur": str(bedomning.get("djur") or "")[:300]}
    p["inlamnat"] = (p.get("inlamnat", []) + [post])[-200:]
    return {**post, "nytt_steg": bedomning.get("nytt_steg"), "ny_sak": bedomning.get("ny_sak"), "extra": bedomning.get("extra") or {},
            "vecka": bedomning.get("vecka")}


def foralder_andra(data: dict, pid: str, godkann: bool) -> dict:
    """Föräldern underkänner (⭐ tas tillbaka) eller godkänner en inlämning AI:n sa nej till."""
    p = _p(data)
    x = next((y for y in p.get("inlamnat", []) if y["id"] == pid), None)
    if not x:
        raise ValueError("Inlämningen finns inte.")
    if godkann and not x["godkand"]:
        x["godkand"], x["skal"], x["av_foralder"] = True, None, True
        x["p"] = poang_for(x["steg"])  # (utan svit- och kvalitetsbonus)
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
