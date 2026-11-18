"""Pluggplaner inför prov, övningsprov, svaga punkter, dagens läxlista och veckorapporten.

Ren logik utan AI-anrop. AI:n anropas från __init__.py och resultatet valideras här.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from . import meriter

PROVTYPER = {"skriftligt": "Skriftligt prov", "glosor": "Glosförhör", "muntligt": "Muntligt prov", "praktiskt": "Praktiskt prov", "inlamning": "Inlämning"}
SATT = {"forhor": "bli förhörd", "lasa": "läsa och sammanfatta", "skriva": "skriva egna anteckningar", "forklara": "förklara för någon",
        "rita": "rita bilder och tankekartor", "lyssna": "lyssna och prata", "uppgifter": "räkna/göra uppgifter", "ovningsprov": "göra övningsprov"}
MAL = {"godkant": "klara provet", "bra": "få ett bra resultat", "toppen": "få toppresultat"}
DELTYPER = {"las": "📖", "forhor": "📝", "ovningsprov": "🧪", "repetera": "🔁", "uppgifter": "✏️", "glosor": "🗣️", "sammanfatta": "🗒️", "forklara": "🙋"}
KAN = {0: "kan inte än", 1: "osäker", 2: "kan"}
SVAG_INTERVALL = [1, 3, 7]  # dagar till nästa repetition efter 1, 2, 3 rätt i rad
SVAG_MAX = 300
P_OVNINGSPROV = 10
P_PLANDEL = 3  # per del i planen (högst 3 per dag); pluggdagen ger sina egna ⭐


def _id() -> str:
    return uuid.uuid4().hex[:10]


def _idag() -> date:
    return dt_util.now().date()


def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


# ---------- studieprofil (hur barnet pluggar bäst) ----------

def profil(data: dict, alder: int | None = None) -> dict:
    p = dict(data.get("studieprofil") or {})
    p.setdefault("min_dag", 15 if (alder or 12) < 11 else 25)
    p.setdefault("dagar", [0, 1, 2, 3, 6])
    p.setdefault("satt", ["forhor", "lasa"])
    p.setdefault("svart", "")
    return p


def profil_spara(data: dict, body: dict) -> dict:
    p = profil(data)
    if "min_dag" in body:
        p["min_dag"] = max(5, min(90, int(body.get("min_dag") or 20)))
    if isinstance(body.get("dagar"), list):
        p["dagar"] = sorted({int(x) for x in body["dagar"] if str(x).isdigit() and 0 <= int(x) <= 6}) or [0, 1, 2, 3]
    if isinstance(body.get("satt"), list):
        p["satt"] = [x for x in body["satt"] if x in SATT][:8]
    if "svart" in body:
        p["svart"] = _txt(body.get("svart"), 300)
    data["studieprofil"] = p
    return p


def profil_text(p: dict) -> str:
    dn = ["mån", "tis", "ons", "tor", "fre", "lör", "sön"]
    return (f"Vill plugga ungefär {p['min_dag']} min per dag, helst på {', '.join(dn[d] for d in p['dagar'])}. "
            f"Lär sig bäst genom att {', '.join(SATT[s] for s in p['satt']) or 'blanda'}."
            + (f" Tycker detta är svårt: {p['svart']}." if p.get("svart") else ""))


# ---------- föräldrarnas önskemål (påverkar, styr inte) ----------
STRIKTHET = {"mild": "mild: flexibelt, korta pass, mycket pepp, det gör inget om en dag missas",
             "lagom": "lagom: en tydlig plan men med lite luft",
             "strang": "sträng: tydliga krav, regelbunden repetition och att planen följs, men fortfarande snällt och i rimlig mängd"}


def onskemal(data: dict) -> dict:
    o = dict(data.get("foralder_onskemal") or {})
    o.setdefault("strikthet", "lagom")
    o.setdefault("text", "")
    return o


def onskemal_spara(data: dict, body: dict, av: str) -> dict:
    o = onskemal(data)
    if body.get("strikthet") in STRIKTHET:
        o["strikthet"] = body["strikthet"]
    if "text" in body:
        o["text"] = _txt(body.get("text"), 800)
    o["av"] = _txt(av, 40)
    o["uppdaterad"] = dt_util.now().isoformat(timespec="minutes")
    data["foralder_onskemal"] = o
    return o


def onskemal_text(data: dict) -> str:
    o = onskemal(data)
    return f"Strikthet: {STRIKTHET[o['strikthet']]}." + (f" Föräldrarna skriver: {o['text']}" if o.get("text") else "")


# ---------- pluggplan ----------

def plan_dagar(u: dict, dagar: list[int], uteslut: list[str] | None = None) -> list[str]:
    """Dagar att plugga på: från idag till dagen före provet, bara valda veckodagar (högst 21)."""
    try:
        prov = date.fromisoformat(u["datum"])
    except (KeyError, ValueError, TypeError):
        return []
    idag = _idag()
    ut = []
    d = idag
    while d < prov and len(ut) < 21:
        if d.weekday() in dagar and d.isoformat() not in (uteslut or []):
            ut.append(d.isoformat())
        d += timedelta(days=1)
    if not ut and idag < prov:
        ut = [idag.isoformat()]
    return ut


def omraden_spara(u: dict, lista: list) -> list[dict]:
    """Provets områden med barnets egen bedömning (0 kan inte, 1 osäker, 2 kan)."""
    gamla = {o["namn"].lower(): o for o in (u.get("plan") or {}).get("omraden", [])}
    ut = []
    for x in lista[:12]:
        namn = _txt(x.get("namn") if isinstance(x, dict) else x, 80)
        if not namn or namn.lower() in {o["namn"].lower() for o in ut}:
            continue
        g = gamla.get(namn.lower(), {})
        kan = x.get("kan") if isinstance(x, dict) else None
        kan = int(kan) if str(kan) in ("0", "1", "2") else g.get("kan", 1)
        ut.append({"id": g.get("id") or _id(), "namn": namn, "kan": kan, "info": _txt(x.get("info") if isinstance(x, dict) else "", 200)})
    return ut


def plan_spara(u: dict, inst: dict, omraden: list[dict], delar_ai: list, dagar: list[str]) -> dict:
    """Validera AI:ns plan: rätt dagar, rimliga minuter, känd typ. Saknade dagar fylls inte på, det är AI:ns jobb."""
    tillatna = set(dagar)
    namn = {o["namn"].lower(): o["id"] for o in omraden}
    delar = []
    for x in delar_ai[:60]:
        if not isinstance(x, dict):
            continue
        dag = str(x.get("dag") or "")[:10]
        if dag not in tillatna:
            dag = min(dagar, key=lambda d: abs((date.fromisoformat(d) - date.fromisoformat(dag)).days)) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dag) and dagar else None
        titel = _txt(x.get("titel"), 80)
        if not dag or not titel:
            continue
        typ = x.get("typ") if x.get("typ") in DELTYPER else "las"
        delar.append({"id": _id(), "dag": dag, "titel": titel, "vad": _txt(x.get("vad"), 400), "typ": typ,
                      "min": max(5, min(90, int(x.get("min") or 15))) if str(x.get("min") or "").isdigit() else 15,
                      "omrade": namn.get(str(x.get("omrade") or "").lower()), "klar": None})
    delar.sort(key=lambda d: d["dag"])
    gammal = u.get("plan") or {}
    if gammal.get("delar"):  # planen görs om: spara hur det gick med den gamla
        u["plan_historik"] = (u.get("plan_historik", []) + [plan_summering(u, gammal)])[-5:]
    plan = {"skapad": dt_util.now().isoformat(timespec="minutes"), "inst": inst, "omraden": omraden, "delar": delar,
            "ovningsprov": gammal.get("ovningsprov", []), "version": gammal.get("version", 0) + 1}
    u["plan"] = plan
    return plan


def plan_summering(u: dict, plan: dict) -> str:
    """En rad om hur en plan gick: vad som gjordes, vad som hoppades över och resultaten."""
    delar = plan.get("delar", [])
    gjorda = [d for d in delar if d.get("klar")]
    i_tid = [d for d in gjorda if d["klar"][:10] <= d["dag"]]
    typer = {}
    for d in delar:
        t = typer.setdefault(d["typ"], [0, 0])
        t[1] += 1
        t[0] += bool(d.get("klar"))
    inst = plan.get("inst") or {}
    r = (f"Plan gjord {str(plan.get('skapad'))[:10]} ({PROVTYPER.get(inst.get('provtyp'), 'prov')}, mål: {MAL.get(inst.get('mal'), '?')}): "
         f"{len(gjorda)} av {len(delar)} delar gjorda ({len(i_tid)} i tid). Per typ gjorda/planerade: "
         + ", ".join(f"{t} {a}/{b}" for t, (a, b) in typer.items()) + ".")
    ops = [o for o in plan.get("ovningsprov", []) if o.get("resultat")]
    if ops:
        r += " Övningsprov: " + ", ".join(f"{o['ratt']}/{len(o['fragor'])}" for o in ops) + "."
    if plan.get("omraden"):
        r += " Områden (barnets bedömning): " + ", ".join(f"{o['namn']} {KAN[o['kan']]}" for o in plan["omraden"]) + "."
    return r


def plan_historik(data: dict, utom: str | None = None) -> str:
    """Tidigare pluggplaner och hur det gick på proven, så att AI:n kan förbättra nästa plan."""
    rader = []
    for u in sorted(data.get("uppdrag", []), key=lambda x: x.get("datum") or ""):
        if u.get("typ") != "prov" or (not u.get("plan") and not u.get("plan_historik")):
            continue
        rad = [f"{u['namn']} ({u.get('amne_namn')}, prov {u.get('datum')})" + (" [nuvarande prov]" if u["id"] == utom else "") + ":"]
        rad += [f"  tidigare version: {h}" for h in u.get("plan_historik", [])]
        if u.get("plan") and u["id"] != utom:
            rad.append("  " + plan_summering(u, u["plan"]))
        res = u.get("resultat")
        if isinstance(res, dict):
            andel = meriter.prov_andel(res)
            rad.append(f"  Provresultat: {res.get('betyg') or (f'{res.get('poang')}/{res.get('max')}')}" + (f" ({round(andel * 100)} %)" if andel is not None else ""))
        if len(rad) > 1:
            rader.append("\n".join(rad))
    return "\n".join(rader[-8:]) or "Inga tidigare planer."


def del_klar(data: dict, u: dict, del_id: str, klar: bool) -> dict:
    plan = u.get("plan") or {}
    d = next((x for x in plan.get("delar", []) if x["id"] == del_id), None)
    if not d:
        raise ValueError("Delen finns inte.")
    idag = _idag().isoformat()
    p = 0
    if klar and not d.get("klar"):
        d["klar"] = dt_util.now().isoformat(timespec="minutes")
        meriter.prov_studiedag(data, u)  # pluggdag: ⭐ och skada på provbossen
        meriter.aktiv(data, idag)
        for n in range(1, 4):
            if meriter.ge(data, P_PLANDEL, f"📅 Pluggplan: {d['titel'][:40]}", f"plandel:{idag}:{n}", "📅"):
                p = P_PLANDEL
                break
    elif not klar:
        d["klar"] = None
    return {"p": p, "alla": all(x.get("klar") for x in plan.get("delar", []))}


def plan_lage(u: dict) -> dict | None:
    """Plan med status för panelen: dagens delar, missade och hur långt man kommit."""
    plan = u.get("plan")
    if not plan:
        return None
    idag = _idag().isoformat()
    delar = plan.get("delar", [])
    return {**plan, "idag": idag, "klara": sum(1 for d in delar if d.get("klar")), "antal": len(delar),
            "missade": sum(1 for d in delar if not d.get("klar") and d["dag"] < idag)}


# ---------- övningsprov ----------

def ovningsprov_spara(u: dict, fragor_ai: list, omraden: list[dict]) -> dict:
    namn = {o["namn"].lower(): o["id"] for o in omraden}
    fragor = []
    for x in fragor_ai[:12]:
        if not isinstance(x, dict) or not _txt(x.get("fraga"), 10):
            continue
        alt = [_txt(a, 120) for a in (x.get("alternativ") or []) if _txt(a, 120)][:5]
        facit = _txt(x.get("facit"), 300)
        if alt and facit not in alt:
            alt = []  # flerval utan rätt svar bland alternativen blir en vanlig fråga
        fragor.append({"fraga": _txt(x.get("fraga"), 300), "facit": facit, "alternativ": alt,
                       "omrade": namn.get(str(x.get("omrade") or "").lower())})
    if len(fragor) < 3:
        raise ValueError("AI:n kunde inte göra något övningsprov. Lägg in mer material i ämnet och försök igen.")
    op = {"id": _id(), "skapad": dt_util.now().isoformat(timespec="minutes"), "fragor": fragor, "svar": None, "resultat": None}
    plan = u.setdefault("plan", {"omraden": omraden, "delar": [], "inst": {}})
    plan["ovningsprov"] = (plan.get("ovningsprov", []) + [op])[-5:]
    return op


def ovningsprov_ut(op: dict, med_facit: bool) -> dict:
    return {**op, "fragor": [{k: v for k, v in q.items() if med_facit or k != "facit"} for q in op["fragor"]]}


def ovningsprov_ratta(data: dict, u: dict, op: dict, svar: list, bedomning: list, amne: str) -> dict:
    """Spara rättningen. Flerval rättas här, resten av AI:n. Fel blir svaga punkter, områdena uppdateras."""
    res = []
    for i, q in enumerate(op["fragor"]):
        s = _txt(svar[i] if i < len(svar) else "", 300)
        b = bedomning[i] if i < len(bedomning) and isinstance(bedomning[i], dict) else {}
        if q["alternativ"]:
            ratt = s == q["facit"]
        else:
            ratt = bool(b.get("ratt")) if s else False
        res.append({"svar": s, "ratt": ratt, "kommentar": _txt(b.get("kommentar"), 300)})
    op["svar"] = [r["svar"] for r in res]
    op["resultat"] = res
    op["ratt"] = sum(r["ratt"] for r in res)
    op["klar"] = dt_util.now().isoformat(timespec="minutes")
    omr = {o["id"]: o for o in (u.get("plan") or {}).get("omraden", [])}
    per = {}
    for q, r in zip(op["fragor"], res):
        if q.get("omrade") in omr:
            per.setdefault(q["omrade"], []).append(r["ratt"])
        if not r["ratt"]:
            svag_ny(data, amne, u["id"], q["fraga"], q["facit"], "ovningsprov")
    for oid, lista in per.items():
        andel = sum(lista) / len(lista)
        omr[oid]["kan"] = 2 if andel >= 0.8 else 1 if andel >= 0.4 else 0
    idag = _idag().isoformat()
    p = P_OVNINGSPROV if meriter.ge(data, P_OVNINGSPROV, f"🧪 Övningsprov: {u['namn'][:40]}", f"ovningsprov:{u['id']}:{idag}", "🧪") else 0
    meriter.prov_studiedag(data, u)
    meriter.aktiv(data, idag)
    return {"resultat": res, "ratt": op["ratt"], "av": len(res), "p": p}


# ---------- svaga punkter (repetition med ökande mellanrum) ----------

def svag_ny(data: dict, amne: str, uppdrag: str | None, fraga: str, facit: str, kalla: str) -> None:
    fraga, facit = _txt(fraga, 300), _txt(facit, 300)
    if not fraga or not facit:
        return
    lista = data.setdefault("svaga", [])
    gammal = next((x for x in lista if x["fraga"].lower() == fraga.lower() and not x.get("klar")), None)
    nasta = (_idag() + timedelta(days=1)).isoformat()
    if gammal:
        gammal.update({"steg": 0, "nasta": nasta})
        return
    lista.append({"id": _id(), "amne": amne, "uppdrag": uppdrag, "fraga": fraga, "facit": facit, "kalla": kalla,
                  "steg": 0, "nasta": nasta, "skapad": _idag().isoformat(), "klar": None})
    aktiva = [x for x in lista if not x.get("klar")]
    if len(lista) > SVAG_MAX:
        data["svaga"] = aktiva[-SVAG_MAX:]


def svaga_idag(data: dict) -> list[dict]:
    idag = _idag().isoformat()
    return [x for x in data.get("svaga", []) if not x.get("klar") and x["nasta"] <= idag]


def svag_svar(data: dict, sid: str, kunde: bool) -> dict:
    x = next((y for y in data.get("svaga", []) if y["id"] == sid), None)
    if not x:
        raise ValueError("Frågan finns inte.")
    idag = _idag()
    if kunde:
        x["steg"] += 1
        if x["steg"] >= len(SVAG_INTERVALL):
            x["klar"] = idag.isoformat()
        else:
            x["nasta"] = (idag + timedelta(days=SVAG_INTERVALL[x["steg"]])).isoformat()
    else:
        x["steg"] = 0
        x["nasta"] = (idag + timedelta(days=1)).isoformat()
    m = meriter._m(data)
    r = m.get("svag_dag") or {}
    if r.get("dag") != idag.isoformat():
        r = {"dag": idag.isoformat(), "n": 0}
    r["n"] += 1
    m["svag_dag"] = r
    if r["n"] == 3:  # tre repetitioner = en pluggdag i sviten
        meriter.aktiv(data, idag.isoformat())
    return {"befast": bool(x.get("klar")), "kvar": len(svaga_idag(data))}


def svaga_status(data: dict) -> dict:
    lista = [x for x in data.get("svaga", []) if not x.get("klar")]
    return {"idag": len(svaga_idag(data)), "totalt": len(lista),
            "befasta": sum(1 for x in data.get("svaga", []) if x.get("klar"))}


# ---------- dagens läxlista ----------

def _min_for(u: dict) -> int:
    if u.get("typ") in ("las", "hogl") and u.get("sidor"):
        return max(5, min(45, 2 * (len(u["sidor"]) - u.get("lasta", 0))))
    return {"glosor": 10, "skriv": 20}.get(u.get("typ"), 15)


def dagens_lista(data: dict) -> dict:
    """Vad barnet ska göra idag, i en bra ordning, med ungefärlig tid. Ingen AI, bara regler."""
    idag = _idag()
    iso = idag.isoformat()
    rader = []
    for f in data.get("forhor", []):
        if f.get("status") in ("skickat", "pagar"):
            rader.append({"ikon": "📋", "text": f"Förhör: {f.get('namn')}", "min": 5, "prio": 0, "mal": {"forhor": f["id"]}})
    for u in data.get("uppdrag", []):
        if u.get("klart") or not u.get("datum"):
            continue
        try:
            dagar = (date.fromisoformat(u["datum"]) - idag).days
        except ValueError:
            continue
        if u.get("typ") == "prov":
            for d in (u.get("plan") or {}).get("delar", []):
                if not d.get("klar") and d["dag"] <= iso:
                    rader.append({"ikon": DELTYPER.get(d["typ"], "📅"), "text": f"{d['titel']} ({u['amne_namn']}, provet {('i morgon' if dagar == 1 else f'om {dagar} dagar')})",
                                  "min": d["min"], "prio": 2 if d["dag"] == iso else 1, "mal": {"plan": u["id"]}, "missad": d["dag"] < iso})
            if not u.get("plan") and 0 < dagar <= 7:
                rader.append({"ikon": "📅", "text": f"Gör en pluggplan för {u['namn']} (provet om {dagar} dagar)", "min": 3, "prio": 1, "mal": {"plan": u["id"]}})
        elif 0 <= dagar <= 2:
            rader.append({"ikon": "📖" if u.get("typ") in ("las", "hogl") else "✏️", "text": f"{u['namn']} ({u.get('amne_namn')}, klar {('idag' if dagar == 0 else 'i morgon' if dagar == 1 else 'i övermorgon')})",
                          "min": _min_for(u), "prio": dagar, "mal": {"uppdrag": u["id"]}})
    sv = len(svaga_idag(data))
    if sv:
        rader.append({"ikon": "🔁", "text": f"Repetera {sv} svag{'a punkter' if sv > 1 else ' punkt'}", "min": max(3, min(15, sv)), "prio": 3, "mal": {"svaga": True}})
    rader.sort(key=lambda r: r["prio"])
    for r in rader:
        r.pop("prio", None)
    return {"rader": rader[:10], "min": sum(r["min"] for r in rader[:10])}


# ---------- veckorapport ----------

def vecko_underlag(data: dict, namn: str) -> str:
    """Det AI:n får för att skriva veckorapporten till föräldrarna."""
    idag = _idag()
    fran = (idag - timedelta(days=7)).isoformat()
    m = meriter._m(data)
    logg = [x for x in m.get("logg", []) if str(x.get("tid") or "")[:10] >= fran]
    rader = [f"Barn: {namn}. Period: {fran} – {idag.isoformat()}."]
    if logg:
        rader.append(f"Meriter i veckan ({sum(int(x.get('p') or x.get('poang') or 0) for x in logg)} ⭐): " + "; ".join(
            f"{str(x.get('tid'))[5:10]} {x.get('orsak') or x.get('text')}" for x in logg[-60:]))
    else:
        rader.append("Inga meriter i appen den här veckan.")
    rader.append(f"Svit: {meriter.sammanfattning(data).get('streak')} dagar.")
    for u in data.get("uppdrag", []):
        plan = u.get("plan") or {}
        for op in plan.get("ovningsprov", []):
            if op.get("klar", "")[:10] >= fran:
                fel = [q["fraga"] for q, r in zip(op["fragor"], op.get("resultat") or []) if not r["ratt"]]
                rader.append(f"Övningsprov {u['namn']}: {op.get('ratt')} av {len(op['fragor'])} rätt." + (f" Fel på: {' | '.join(fel[:5])}" if fel else ""))
        if plan.get("delar") and u.get("datum", "") >= fran:
            klara = sum(1 for d in plan["delar"] if d.get("klar"))
            rader.append(f"Pluggplan {u['namn']} (prov {u['datum']}): {klara} av {len(plan['delar'])} delar klara. "
                         + "Områden: " + ", ".join(f"{o['namn']} ({KAN[o['kan']]})" for o in plan.get("omraden", [])))
        if u.get("resultat") and str(u["resultat"].get("datum") or u.get("datum") or "") >= fran:
            rader.append(f"Provresultat {u['namn']}: {u['resultat']}")
    for f in data.get("forhor", []):
        if str(f.get("klart") or "")[:10] >= fran:
            rader.append(f"Förhör {f.get('namn')}: {sum(1 for s in f.get('svar', []) if s.get('ratt'))} av {len(f.get('fragor', []))} rätt.")
    sv = [x for x in data.get("svaga", []) if x["skapad"] >= fran or (x.get("klar") or "") >= fran]
    if sv:
        rader.append("Svaga punkter i veckan: " + " | ".join(f"{x['fraga']}{' (befäst)' if x.get('klar') else ''}" for x in sv[:12]))
    kommande = sorted((u for u in data.get("uppdrag", []) if not u.get("klart") and u.get("datum") and idag.isoformat() <= u["datum"] <= (idag + timedelta(days=10)).isoformat()), key=lambda u: u["datum"])
    if kommande:
        rader.append("Kommande: " + "; ".join(f"{u['datum']} {u['namn']} ({u.get('amne_namn')})" for u in kommande))
    si = meriter.skolinfo(data)
    if si:
        rader.append("Från skolan: " + "; ".join(f"{x.get('datum') or ''} {x['text']}" for x in si[:8]))
    return "\n".join(rader)


# ---------- lärarens riktlinjer (AI:n samarbetar med läraren) ----------
RIKTLINJE_REGEL = ("LÄRARENS RIKTLINJER (viktigt, gäller allt ovan): följ dem. De går före föräldrarnas önskemål när det gäller hur något lärs ut "
                   "(metod, begrepp, hur mycket hjälp). Säg aldrig emot läraren eller lärarens metod och lär inte ut ett annat sätt än läraren. "
                   "Är du osäker på hur läraren vill ha det: säg det och föreslå att barnet frågar läraren.")


def riktlinjer(data: dict) -> list[dict]:
    return data.get("larar_riktlinjer", [])


def riktlinje_ny(data: dict, amne_id: str, amne_namn: str, text: str, kalla: str, av: str) -> dict:
    text = _txt(text, 600)
    if len(text) < 3:
        raise ValueError("Skriv vad läraren vill.")
    lista = data.setdefault("larar_riktlinjer", [])
    if len(lista) >= 60:
        raise ValueError("Ta bort några gamla riktlinjer först.")
    r = {"id": _id(), "amne": amne_id or "", "amne_namn": _txt(amne_namn, 40) or "Alla ämnen", "text": text,
         "kalla": "larare" if kalla == "larare" else "foralder", "av": _txt(av, 60), "tid": dt_util.now().isoformat(timespec="minutes")}
    lista.append(r)
    return r


def riktlinje_bort(data: dict, rid: str) -> None:
    data["larar_riktlinjer"] = [x for x in riktlinjer(data) if x["id"] != rid]


def larare_block(data: dict, amne_id: str | None = None) -> str:
    """Text att lägga sist i en AI-prompt. Tom om det inte finns några riktlinjer för ämnet."""
    rader = [x for x in riktlinjer(data) if not x["amne"] or amne_id is None or x["amne"] == amne_id]
    if not rader:
        return ""
    return "\n\n" + RIKTLINJE_REGEL + "\n" + "\n".join(
        f"- {x['amne_namn']}: {x['text']}" + (" (direkt från läraren)" if x["kalla"] == "larare" else " (enligt föräldern)") for x in rader[-20:])


def amne_svenska(data: dict) -> str:
    """Ämnet för skrivande (svenska), annars ett id som bara matchar riktlinjer för alla ämnen."""
    a = next((x for x in data.get("amnen", []) if "svensk" in x["namn"].lower()), None)
    return a["id"] if a else "-"


def studieteknik(data: dict, alder: int | None) -> dict:
    """Det läraren får se om studietekniken (om föräldern slagit på det). Inga stjärnor, husdjur eller jämförelser."""
    planer = []
    tankar = ""
    for u in sorted(data.get("uppdrag", []), key=lambda x: x.get("datum") or ""):
        if u.get("typ") == "prov" and u.get("plan"):
            planer.append({"prov": u["namn"], "amne": u.get("amne_namn"), "datum": u.get("datum"), "sammanfattning": plan_summering(u, u["plan"])})
            tankar = (u["plan"].get("inst") or {}).get("tankar") or tankar
    svaga = {}
    for x in data.get("svaga", []):
        if not x.get("klar"):
            svaga[x["amne"]] = svaga.get(x["amne"], 0) + 1
    namn = {a["id"]: a["namn"] for a in data.get("amnen", [])}
    rap = (data.get("veckorapport") or {}).get("rapport") or {}
    skriv_omr = {}
    for x in (data.get("skriv") or {}).get("historik", [])[-40:]:
        for k, v in (x.get("omraden") or {}).items():
            skriv_omr.setdefault(k, []).append(v)
    return {"profil": profil_text(profil(data, alder)), "planer": planer[-6:], "ai_tankar": tankar or rap.get("studietaktik", ""),
            "svart": rap.get("svart", []), "svaga_punkter": [{"amne": namn.get(k, "?"), "antal": v} for k, v in sorted(svaga.items(), key=lambda kv: -kv[1])][:6],
            "skrivande": {k: round(sum(v) / len(v)) for k, v in skriv_omr.items()},
            "riktlinjer": [{"amne": x["amne_namn"], "text": x["text"], "kalla": x["kalla"]} for x in riktlinjer(data)]}
