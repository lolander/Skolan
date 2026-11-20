"""Koppling till skolan: läraren och klassen.

Föräldern och läraren bestämmer tillsammans. En funktion är bara på när BÅDA har slagit på den:
föräldern i Skolans inställningar, läraren i lärarappen (Läxspelet Lärare för Windows).
E-postrapporten kräver bara föräldern, men läraren kan säga nej till den i lärarappen.

Lärarappen pratar med barnets Skolan via klasslänken {extern adress}/api/skolan/klass/{nyckel}
(som vänlänken: hemlig nyckel, ingen inloggning). Den skickar veckobrev och klassens läge,
och får tillbaka bara det som föräldern och läraren har slagit på.
Läraren ser aldrig enskilda barns poäng i klasslaget, bara klassens summa.

Flera lärare (från 1.95.0): eleven kan ha en mentor och ämneslärare. Alla synkar med samma klasslänk.
Föräldern väljer per lärare vad den får (annars gäller förälderns standardval). En ämneslärare får bara
sitt eget ämne i rapport, statistik och studieteknik. Föräldern kan koppla bort en lärare (den spärras).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path

from homeassistant.util import dt as dt_util

from . import meriter

PA = True  # visar lärare och klass i appen
VAG = "/api/skolan/klass/"
FUNKTIONER = {
    "veckobrev": ("📬", "Veckobrev från läraren", "Lärarens veckobrev hamnar i din inkorg. Du godkänner innan läxorna läggs in."),
    "rapport": ("📊", "Veckorapport till läraren i lärarappen", "När eleven synkar ser läraren en kort rapport: dagar övat, förhör och prov."),
    "klasslag": ("🏫", "Klasslag", "Klassen bekämpar en gemensam boss. Läraren ser bara klassens summa, aldrig ditt barns poäng."),
    "mejl": ("📧", "Rapport via e-post", "Läxspelet mejlar en kort rapport till läraren de dagar du väljer."),
    "grupper": ("👥", "Grupper och gruppuppgifter", "Läraren kan sätta ditt barn i tillfälliga grupper med en uppgift. Barnet ser gruppen och kan bocka av uppgiften."),
    "statistik": ("📈", "Statistik till läraren", "Läraren ser hur ditt barn pluggar: dagar per vecka, förhör, prov och ämnen. Inga stjärnor, husdjur eller jämförelser."),
    "schema": ("🗓️", "Schemat till läraren", "Läraren ser den digitala kopian av schemat som Läxspelet har läst av (lektioner, salar och lärare)."),
    "studieteknik": ("🧠", "Studieteknik till läraren", "Läraren ser hur ditt barn pluggar: pluggplaner och hur de följs, vad som är svårt, svaga punkter, skrivandet och AI:ns tankar om studietekniken. Inga stjärnor, husdjur eller jämförelser."),
    "riktlinjer": ("📝", "Riktlinjer från läraren till AI:n", "Läraren kan skicka riktlinjer per ämne (t.ex. metod, begrepp eller hur mycket hjälp) som AI:n följer, så att den hjälper på samma sätt som läraren. De hamnar i din inkorg och du godkänner först."),
    "lapp": ("✉️", "Lappar till läraren", "Du kan skicka en kort lapp om vad ditt barn har tyckt varit svårt, så att läraren kan ta upp det igen. Du läser och godkänner varje lapp innan den skickas."),
    "samtal": ("🗣️", "Underlag till utvecklingssamtalet", "Du kan skicka underlaget till utvecklingssamtalet till läraren. Du väljer själv när, och ser exakt vad som skickas."),
    "insikt": ("🔎", "Klassens insikt (utan namn)", "Läraren ser bara hela klassens summa, t.ex. vilka glosor många missar och hur många som har pluggat inför ett prov. Inget går att koppla till ditt barn, och inget visas förrän minst 5 familjer är med."),
    "material": ("📎", "Prov och studiematerial från läraren", "Läraren kan skicka provresultat, studiematerial och klassens schema (PDF eller foto). Det hamnar i din inkorg och du godkänner innan något läggs in."),
}
# Lägsta behörighetsnivå (beslutad av rektorn i lärarappen) som krävs för att funktionen ska skicka något till läraren.
# Lärarappar före 0.10.0 skickar ingen nivå och räknas som nivå 0, så de får inga uppgifter om barnet.
FUNK_NIVA = {"veckobrev": 0, "klasslag": 0, "riktlinjer": 0, "material": 0, "insikt": 0,
             "grupper": 1, "schema": 1, "rapport": 2, "statistik": 2, "studieteknik": 2, "lapp": 2, "samtal": 2}
KLASSBOSS_BELONING = 30
MAX_INKORG = 30
MAX_FIL = 8 * 1024 * 1024  # en fil från läraren
MAX_FILER_PER_SYNK = 15 * 1024 * 1024
FIL_TYPER = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _fil(mapp: Path) -> Path:
    return mapp / "skola.json"


def las(mapp: Path) -> dict:
    try:
        s = json.loads(_fil(mapp).read_text("utf-8")) if _fil(mapp).exists() else {}
    except (OSError, ValueError):
        s = {}
    s.setdefault("nyckel", "")
    f = s.setdefault("foralder", {})
    for k in FUNKTIONER:
        f.setdefault(k, False)
    f.setdefault("namn", "")  # namnet läraren ser
    f.setdefault("mejl_till", "")
    f.setdefault("mejl_dagar", [4])  # 0 = måndag; fredag som standard
    s.setdefault("larare", {})  # (gammalt, en lärare) flyttas till "lararna"
    s.setdefault("lararna", {})  # {larar_id: {id, klass, namn, url, inst, synkad, amne, roll, skola, dela: {f: bool}}}
    if s["larare"].get("id") and s["larare"]["id"] not in s["lararna"]:
        s["lararna"][s["larare"]["id"]] = {**s["larare"], "roll": s["larare"].get("roll") or "mentor", "dela": {}}
    s["larare"] = {}
    s.setdefault("blockerade", [])  # lärare som föräldern har kopplat bort
    s.setdefault("inkorg", [])  # från läraren: veckobrev, studiematerial och provresultat ("typ")
    s.setdefault("mottagna", [])  # id:n från läraren som redan har kommit fram, så att filer inte skickas igen
    s.setdefault("klass", None)  # klassens läge från lärarappen
    s.setdefault("mejl_skickat", "")
    s.setdefault("grupper", [])  # från läraren: [{id, namn, uppgift, datum, medlemmar: [namn], klar}]
    s.setdefault("utgaende", [])  # till läraren, godkänt av föräldern: [{id, typ: lapp|samtal, tid, ...}]
    s.setdefault("lapp", {})  # veckans lapp: {vecka, text, status: utkast|skickad}
    return s


def spara(mapp: Path, s: dict) -> None:
    s["inkorg"] = s["inkorg"][-MAX_INKORG:]
    s["mottagna"] = s.get("mottagna", [])[-300:]
    s["utgaende"] = s.get("utgaende", [])[-30:]
    tmp = _fil(mapp).with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False), "utf-8")
    tmp.replace(_fil(mapp))


def se_till_nyckel(s: dict) -> bool:
    if s["nyckel"]:
        return False
    s["nyckel"] = secrets.token_urlsafe(24)
    return True


def lank(bas: str, s: dict) -> str:
    return f"{bas.rstrip('/')}{VAG}{s['nyckel']}" if bas.startswith("https://") and s["nyckel"] else ""


def huvudlarare(s: dict) -> dict:
    """Mentorn (eller den lärare som synkade senast). Tom om ingen lärare är kopplad."""
    lar = list((s.get("lararna") or {}).values())
    if not lar:
        return {}
    mentorer = [x for x in lar if x.get("roll") == "mentor"]
    return max(mentorer or lar, key=lambda x: x.get("synkad", ""))


def delar(s: dict, lid: str, f: str) -> bool:
    """Förälderns val för just den läraren (annars förälderns standardval)."""
    lar = (s.get("lararna") or {}).get(lid) or {}
    return bool((lar.get("dela") or {}).get(f, s["foralder"].get(f)))


def aktiv(s: dict, f: str, lid: str | None = None) -> bool:
    """På bara när föräldern OCH läraren har slagit på funktionen. Utan lid: hos någon av lärarna."""
    lararna = s.get("lararna") or {}
    if f == "mejl":  # ingen lärarapp behövs: förälderns val räcker (om ingen lärare har sagt nej)
        return bool(s["foralder"].get("mejl")) and all((x.get("inst") or {}).get("mejl", True) for x in lararna.values())
    if lid is not None:
        lar = lararna.get(lid) or {}
        niva = int((lar.get("behorighet") or {}).get("niva") or 0)
        return delar(s, lid, f) and bool((lar.get("inst") or {}).get(f)) and niva >= FUNK_NIVA.get(f, 2)
    return any(aktiv(s, f, x) for x in lararna)


def status(s: dict, bas: str, foralder: bool) -> dict:
    lar = huvudlarare(s)
    lista = sorted((s.get("lararna") or {}).values(), key=lambda x: (x.get("roll") != "mentor", x.get("amne") or "", x.get("namn") or ""))
    ut = {"pa": PA, "aktiv": {f: aktiv(s, f) for f in FUNKTIONER}, "larare": {k: lar.get(k) for k in ("klass", "namn", "url", "synkad", "inst")} if lar else None,
          "lararna": [{**{k: x.get(k) for k in ("id", "klass", "namn", "url", "synkad", "amne", "roll", "skola", "behorighet")},
                       **({"inst": x.get("inst") or {}, "dela": {f: delar(s, x["id"], f) for f in FUNKTIONER}} if foralder else {})} for x in lista],
          "klass": s.get("klass") if aktiv(s, "klasslag") else None, "lank": lank(bas, s), "kan_nas": bas.startswith("https://"),
          "grupper": s["grupper"] if aktiv(s, "grupper") else []}
    if foralder:
        ut.update({"foralder": s["foralder"], "funktioner": [{"id": k, "ikon": v[0], "namn": v[1], "info": v[2]} for k, v in FUNKTIONER.items()],
                   "inkorg": [x for x in s["inkorg"] if x["status"] == "ny"], "mejl_skickat": s["mejl_skickat"]})
    return ut


def satt_installningar(s: dict, body: dict) -> None:
    lid = body.get("larare")
    if lid:  # förälderns val för en viss lärare
        lar = (s.get("lararna") or {}).get(lid)
        if not lar:
            raise ValueError("Läraren finns inte.")
        d = lar.setdefault("dela", {})
        for k in FUNKTIONER:
            if k in body:
                d[k] = bool(body[k])
        return
    f = s["foralder"]
    for k in FUNKTIONER:
        if k in body:
            f[k] = bool(body[k])
    if "namn" in body:
        f["namn"] = re.sub(r"\s+", " ", str(body.get("namn") or "")).strip()[:40]
    if "mejl_till" in body:
        m = str(body.get("mejl_till") or "").strip()[:120]
        if m and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", m):
            raise ValueError("Skriv en riktig e-postadress till läraren.")
        f["mejl_till"] = m
    if "mejl_dagar" in body:
        f["mejl_dagar"] = sorted({int(d) for d in body.get("mejl_dagar") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
    if f.get("mejl") and not f.get("mejl_till"):
        raise ValueError("Skriv lärarens e-postadress först.")


def koppla_bort(s: dict, lid: str | None = None) -> None:
    if lid:  # en lärare: spärras, de andra fortsätter med samma klasslänk
        s.get("lararna", {}).pop(lid, None)
        if lid not in s["blockerade"]:
            s["blockerade"].append(lid)
        s["grupper"] = [g for g in s["grupper"] if g.get("larare") != lid]
        s["utgaende"] = [x for x in s.get("utgaende", []) if lid not in (x.get("till") or [])]
        if (s.get("klass") or {}).get("larare") == lid:
            s["klass"] = None
        return
    s["lararna"] = {}
    s["larare"] = {}
    s["klass"] = None
    s["grupper"] = []
    s["nyckel"] = secrets.token_urlsafe(24)  # den gamla klasslänken slutar fungera


def elev_id(s: dict) -> str:
    """Samma för alla elevens lärare (så att lärarna på en skola vet att det är samma elev)."""
    return hashlib.sha256(("elev:" + s["nyckel"]).encode()).hexdigest()[:20]


def _amne_lika(a: str, b: str) -> bool:
    """Ämnesnamn som betyder samma sak (Matte/Matematik, Spanska/Moderna språk spanska …)."""
    syn = {"matematik": "matte", "ma": "matte", "svenska som andraspråk": "svenska", "sv": "svenska", "en": "engelska",
           "samhällskunskap": "so", "historia": "so", "geografi": "so", "religion": "so",
           "biologi": "no", "fysik": "no", "kemi": "no", "naturorienterande ämnen": "no", "samhällsorienterande ämnen": "so"}
    n = lambda x: syn.get(re.sub(r"[^a-zåäö ]", "", (x or "").lower()).strip(), re.sub(r"[^a-zåäö ]", "", (x or "").lower()).strip())  # noqa: E731
    a, b = n(a), n(b)
    sprak = {"spanska", "tyska", "franska", "italienska", "kinesiska", "arabiska", "ryska", "japanska"}
    if {a, b} & {"moderna språk", "moderna sprak", "språkval"} and ({a, b} & sprak):
        return True
    return bool(a and b) and (a == b or a in b or b in a)


def _for_amne(lar: dict, amne: str | None) -> bool:
    """Ska den här läraren få något om ämnet? Mentorn får allt, en ämneslärare bara sitt ämne."""
    if lar.get("roll") != "amne" or not lar.get("amne"):
        return True
    return any(_amne_lika(x, amne) for x in re.split(r"[,/]", lar["amne"]))


# ---------- rapport ----------
def rapport(data: dict, namn: str, dagar: int = 7, lar: dict | None = None) -> dict:
    """Kort rapport om de senaste dagarna. Inga husdjur, inga poäng, ingen jämförelse. lar = ämneslärare: bara sitt ämne."""
    lar = lar or {}
    idag = dt_util.now().date()
    fran = (idag - timedelta(days=dagar - 1)).isoformat()
    m = meriter._m(data)
    ovat = sorted(d for d in m.get("ovningsdagar", []) if d >= fran)
    rader = [f"Har pluggat {len(ovat)} av de senaste {dagar} dagarna."]
    for f in data.get("forhor", []):
        if (f.get("klart") or "")[:10] >= fran and f.get("status") == "klart" and _for_amne(lar, f.get("amne_namn")):
            n = len(f.get("fragor", []))
            ratt = sum(1 for x in f.get("svar", []) if x.get("ratt"))
            bed = {"godkant": " (godkänt)", "ej_godkant": " (inte godkänt än)"}.get(f.get("bedomning") or "", "")
            rader.append(f"Förhör {f.get('namn', '')}: {ratt} av {n} rätt{bed}.")
    for a in data.get("amnen", []):
        if not _for_amne(lar, a.get("namn")):
            continue
        for g in a.get("glosor", []):
            d = [x for x in g.get("ovat_dagar", []) if x >= fran]
            if d:
                rader.append(f"{a['namn']}, {g['namn']}: övat {len(d)} dagar.")
    for u in data.get("uppdrag", []):
        if u.get("typ") == "prov" and u.get("resultat") and (u["resultat"].get("tid") or "")[:10] >= fran and _for_amne(lar, u.get("amne_namn")):
            r = u["resultat"]
            visa = f"{r['poang']:g} av {r['max']:g} poäng" if "max" in r else f"betyg {r.get('betyg', '')}"
            rader.append(f"Prov {u.get('namn', '')}: {visa}.")
    return {"namn": namn, "fran": fran, "till": idag.isoformat(), "rader": rader[:20]}


def statistik(data: dict, veckor: int = 8, lar: dict | None = None) -> dict:
    """Det läraren ser när statistiken är på: hur barnet pluggar, inga stjärnor eller husdjur. lar = ämneslärare: bara sitt ämne."""
    lar = lar or {}
    idag = dt_util.now().date()
    start = idag - timedelta(days=idag.weekday() + 7 * (veckor - 1))
    fran = start.isoformat()
    dagar = set(meriter._m(data).get("ovningsdagar", []))
    per_vecka = []
    for i in range(veckor):
        m = start + timedelta(days=7 * i)
        v = "{}-W{:02d}".format(*m.isocalendar()[:2])
        per_vecka.append({"vecka": v, "dagar": sum(1 for d in range(7) if (m + timedelta(days=d)).isoformat() in dagar)})
    forhor = []
    for f in data.get("forhor", []):
        if (f.get("klart") or "")[:10] >= fran and f.get("status") == "klart" and _for_amne(lar, f.get("amne_namn")):
            forhor.append({"namn": _text(f.get("namn"), 60), "datum": (f.get("klart") or "")[:10], "n": len(f.get("fragor", [])),
                           "ratt": sum(1 for x in f.get("svar", []) if x.get("ratt"))})
    prov = []
    for u in data.get("uppdrag", []):
        r = u.get("resultat")
        if u.get("typ") == "prov" and r and (r.get("tid") or "")[:10] >= fran and _for_amne(lar, u.get("amne_namn")):
            prov.append({"namn": _text(u.get("namn"), 60), "amne": _text(u.get("amne_namn"), 40), "datum": (r.get("tid") or "")[:10],
                         **({"poang": r["poang"], "max": r["max"]} if "max" in r else {"betyg": r.get("betyg", "")})})
    amnen = []
    for a in data.get("amnen", []):
        if not _for_amne(lar, a.get("namn")):
            continue
        d = {x for g in a.get("glosor", []) for x in g.get("ovat_dagar", []) if x >= fran}
        if d:
            amnen.append({"namn": _text(a.get("namn"), 40), "dagar": len(d)})
    return {"fran": fran, "till": idag.isoformat(), "per_vecka": per_vecka, "forhor": forhor[-15:], "prov": prov[-10:],
            "amnen": sorted(amnen, key=lambda x: -x["dagar"])[:10]}


def rapport_text(r: dict) -> str:
    return "\n".join([f"Hej! Här är en kort rapport om {r['namn']} ({r['fran']} – {r['till']}).", ""]
                     + [f"• {x}" for x in r["rader"]]
                     + ["", "Rapporten skickas automatiskt från familjens Läxspelet. Svara gärna på mejlet om något är oklart."])


# ---------- e-post ----------
def smtp_las(bas: Path) -> dict:
    try:
        return json.loads((bas / "smtp.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def smtp_spara(bas: Path, body: dict) -> dict:
    gammal = smtp_las(bas)
    ny = {"server": str(body.get("server") or "").strip()[:100], "port": int(body.get("port") or 587),
          "anvandare": str(body.get("anvandare") or "").strip()[:120], "fran": str(body.get("fran") or body.get("anvandare") or "").strip()[:120],
          "losen": str(body.get("losen") or "") or gammal.get("losen", "")}
    if not ny["server"] or not ny["anvandare"] or not ny["losen"]:
        raise ValueError("Fyll i server, användare och lösenord (för Gmail: ett applösenord).")
    f = bas / "smtp.json"
    f.write_text(json.dumps(ny), "utf-8")
    f.chmod(0o600)
    return ny


def smtp_publik(bas: Path) -> dict:
    c = smtp_las(bas)
    return {k: c.get(k, "") for k in ("server", "port", "anvandare", "fran")} | {"har_losen": bool(c.get("losen"))}


def skicka_mejl(bas: Path, till: str, amne: str, text: str) -> None:
    c = smtp_las(bas)
    if not c.get("server"):
        raise ValueError("Ställ in e-post (SMTP) under Skolan och läraren först.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = c["fran"] or c["anvandare"], till, amne
    msg.set_content(text)
    ctx = ssl.create_default_context()
    if int(c.get("port", 587)) == 465:
        with smtplib.SMTP_SSL(c["server"], 465, context=ctx, timeout=20) as srv:
            srv.login(c["anvandare"], c["losen"])
            srv.send_message(msg)
    else:
        with smtplib.SMTP(c["server"], int(c.get("port", 587)), timeout=20) as srv:
            srv.starttls(context=ctx)
            srv.login(c["anvandare"], c["losen"])
            srv.send_message(msg)


# ---------- från lärarappen ----------
def _text(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _rensa_brev(b: dict) -> dict | None:
    """Ett veckobrev från läraren, i samma form som AI:n ger när föräldern fotar ett veckobrev."""
    if not isinstance(b, dict) or not re.fullmatch(r"[A-Za-z0-9_\-]{4,30}", str(b.get("id") or "")):
        return None

    def dag(v):
        try:
            return int(v) if v is not None and 0 <= int(v) <= 6 else None
        except (TypeError, ValueError):
            return None

    ai = b.get("ai") if isinstance(b.get("ai"), dict) else {}
    glosor = [[_text(p[0], 80), _text(p[1], 80)] for p in (ai.get("glosor") or []) if isinstance(p, list) and len(p) == 2 and _text(p[0], 80)][:60]
    ord_ = [_text(o, 60) for o in (ai.get("ord") or []) if _text(o, 60)][:40]
    sprak = [_text(x, 20) for x in (ai.get("glosor_sprak") or [])][:2]
    return {"id": str(b["id"]), "titel": _text(b.get("titel"), 80) or "Veckobrev", "vecka": _text(b.get("vecka"), 10),
            "ai": {"kapitel": ai.get("kapitel") if isinstance(ai.get("kapitel"), int) else None, "kapitel_namn": _text(ai.get("kapitel_namn"), 60) or None,
                   "las_dagar": [d for d in (dag(x) for x in (ai.get("las_dagar") or [])) if d is not None][:7],
                   "hoglasning": bool(ai.get("hoglasning")), "skriv_dag": dag(ai.get("skriv_dag")),
                   # en lista per veckobrev: glosor med översättning går före, stavningsorden nämns då i instruktionerna
                   "ord": [f"{a} = {b2}" for a, b2 in glosor] or ord_, "glosor_sprak": sprak if glosor and len(sprak) == 2 else None,
                   "diktamen_dag": dag(ai.get("diktamen_dag")),
                   "regler": [_text(r, 160) for r in (ai.get("regler") or []) if _text(r, 160)][:10]
                   + ([_text("Stavningsord: " + ", ".join(ord_), 300)] if glosor and ord_ else []), "note": _text(ai.get("note"), 300)}}


def _larar_fil(f, budget: list) -> tuple[dict, bytes] | None:
    """En fil från läraren (base64). Returnerar (info, innehåll) eller None om den inte går att ta emot."""
    import base64
    import binascii

    if not isinstance(f, dict) or f.get("mime") not in FIL_TYPER or not isinstance(f.get("data"), str):
        return None
    if len(f["data"]) > MAX_FIL * 4 // 3 + 8 or len(f["data"]) > budget[0]:
        return None
    try:
        b = base64.b64decode(f["data"], validate=True)
    except (binascii.Error, ValueError):
        return None
    ok = b.startswith(b"%PDF") if f["mime"] == "application/pdf" else b[:3] == b"\xff\xd8\xff" or b[:8] == b"\x89PNG\r\n\x1a\n" or b[8:12] == b"WEBP"
    if not ok or len(b) > MAX_FIL:
        return None
    budget[0] -= len(f["data"])
    namn = f"larare_{dt_util.now().strftime('%Y%m%d-%H%M%S')}_{secrets.token_hex(4)}{FIL_TYPER[f['mime']]}"
    return {"namn": namn, "mime": f["mime"], "orig": _text(f.get("namn"), 80)}, b


def _resultat(r) -> dict | None:
    if not isinstance(r, dict):
        return None
    ut = {"kommentar": _text(r.get("kommentar"), 200)}
    try:
        if r.get("max") not in (None, ""):
            mx, po = float(r["max"]), float(r.get("poang") or 0)
            if 0 < mx <= 10000 and 0 <= po <= mx:
                return {**ut, "poang": po, "max": mx}
    except (TypeError, ValueError):
        return None
    betyg = _text(r.get("betyg"), 2).upper()
    return {**ut, "betyg": betyg} if betyg in meriter.PROV_BETYG else None


def ta_emot(s: dict, data: dict, barn_namn: str, body: dict, studieteknik: dict | None = None) -> dict:
    """Lärarappen synkar. Returnerar svaret till läraren (bara det som är påslaget av båda)."""
    lid = _text(body.get("larar_id"), 40)
    if not lid:
        raise ValueError("Saknar lärare.")
    if lid in s.get("blockerade", []):
        raise PermissionError("Föräldern har kopplat bort dig från den här eleven.")
    inst = body.get("inst") if isinstance(body.get("inst"), dict) else {}
    ny = lid not in s["lararna"]
    if ny and len(s["lararna"]) >= 20:
        raise ValueError("Eleven har redan många lärare kopplade.")
    sk = body.get("skola") if isinstance(body.get("skola"), dict) else {}
    lar = s["lararna"].setdefault(lid, {"dela": {}})
    lar.update({"id": lid, "klass": _text(body.get("klass"), 40), "namn": _text(body.get("larare"), 60),
                "url": _text(body.get("url"), 80) if re.fullmatch(r"https?://[\w.\-]+(:\d+)?", _text(body.get("url"), 80)) else "",
                "inst": {k: bool(inst.get(k)) for k in FUNKTIONER}, "synkad": dt_util.now().isoformat(timespec="minutes"),
                "amne": _text(body.get("amne"), 60), "roll": "amne" if body.get("roll") == "amne" else "mentor",
                "skola": {"id": _text(sk.get("id"), 40), "namn": _text(sk.get("namn"), 60)} if sk.get("id") else None})
    beh = body.get("behorighet") if isinstance(body.get("behorighet"), dict) else None
    niva = max(0, min(2, int(beh.get("niva") or 0))) if beh else 0  # lärarappar före 0.10.0: nivå 0, ingen data om barnet
    lar["behorighet"] = {"niva": niva, "rektor": _text((beh or {}).get("rektor"), 60), "gammal": not beh}
    nya = 0
    filer: list[tuple[str, bytes]] = []
    budget = [MAX_FILER_PER_SYNK * 4 // 3]
    kanda = set(s.setdefault("mottagna", [])) | {x["id"] for x in s["inkorg"]}
    nu = dt_util.now().isoformat(timespec="minutes")

    def in_korg(post: dict, fil) -> bool:
        """Lägg posten i inkorgen. En bifogad fil som inte kom fram (för stor eller fel sort) gör att posten väntar till nästa synk."""
        nonlocal nya
        if fil is not None:
            f = _larar_fil(fil, budget)
            if not f:
                return False
            post["fil"] = f[0]
            filer.append((f[0]["namn"], f[1]))
        s["inkorg"].append({**post, "tid": nu, "status": "ny", "larar_id": lid, "larare": lar["namn"]})
        s["mottagna"].append(post["id"])
        kanda.add(post["id"])
        nya += 1
        return True

    if aktiv(s, "veckobrev", lid):
        for b in (body.get("veckobrev") or [])[:10]:
            r = _rensa_brev(b)
            if r and r["id"] not in kanda:
                in_korg({**r, "typ": "veckobrev"}, b.get("fil"))
    if aktiv(s, "material", lid):
        for m in (body.get("material") or [])[:10]:
            if not isinstance(m, dict) or not re.fullmatch(r"[A-Za-z0-9_\-]{4,40}", str(m.get("id") or "")) or m["id"] in kanda:
                continue
            post = {"id": m["id"], "titel": _text(m.get("titel"), 80) or "Från läraren", "amne": _text(m.get("amne"), 40), "text": _text(m.get("text"), 1000)}
            if m.get("typ") == "prov":
                res = _resultat(m.get("resultat"))
                if res is None and m.get("fil") is None:
                    continue
                pid = _text(m.get("prov_id"), 40)
                if in_korg({**post, "typ": "prov", "prov_id": pid, "datum": _text(m.get("datum"), 10), "resultat": res}, m.get("fil")) and pid:
                    for x in s["inkorg"][:-1]:  # ett ändrat resultat ersätter det som inte är godkänt än
                        if x.get("prov_id") == pid and x["status"] == "ny":
                            x["status"] = "ersatt"
            elif m.get("typ") == "schema" and m.get("fil") is not None:
                in_korg({**post, "typ": "schema"}, m["fil"])
            elif m.get("fil") is not None:
                in_korg({**post, "typ": "material"}, m["fil"])
    if aktiv(s, "riktlinjer", lid):
        for m in (body.get("riktlinjer") or [])[:20]:
            if isinstance(m, dict) and re.fullmatch(r"[A-Za-z0-9_\-]{4,40}", str(m.get("id") or "")) and m["id"] not in kanda and _text(m.get("text"), 600):
                in_korg({"id": m["id"], "typ": "riktlinje", "titel": "Riktlinje till AI:n", "amne": _text(m.get("amne"), 40), "text": _text(m.get("text"), 600)}, None)
    mentor_finns = any(x.get("roll") == "mentor" and x["id"] != lid and aktiv(s, "klasslag", x["id"]) for x in s["lararna"].values())
    if aktiv(s, "klasslag", lid) and isinstance(body.get("klass_status"), dict) and (lar["roll"] == "mentor" or not mentor_finns):
        k = body["klass_status"]
        try:
            s["klass"] = {"namn": _text(k.get("namn"), 40), "vecka": _text(k.get("vecka"), 10), "ikon": _text(k.get("ikon"), 4),
                          "boss": _text(k.get("boss"), 40), "hp": max(1, min(10**7, int(k.get("hp") or 1))),
                          "skada": max(0, min(10**7, int(k.get("skada") or 0))), "antal": max(0, min(1000, int(k.get("antal") or 0))), "larare": lid}
        except (TypeError, ValueError):
            pass
    if aktiv(s, "grupper", lid):
        gamla = {g["id"]: g for g in s["grupper"]}
        ny = [g for g in s["grupper"] if g.get("larare") and g.get("larare") != lid]  # andra lärares grupper ligger kvar
        for g in (body.get("grupper") or [])[:10]:
            if isinstance(g, dict) and re.fullmatch(r"[A-Za-z0-9_\-]{4,20}", str(g.get("id") or "")):
                ny.append({"id": g["id"], "namn": _text(g.get("namn"), 40), "uppgift": _text(g.get("uppgift"), 1000), "datum": _text(g.get("datum"), 10),
                           "medlemmar": [_text(x, 40) for x in (g.get("medlemmar") or [])][:40], "klar": (gamla.get(g["id"]) or {}).get("klar", ""),
                           "larare": lid, "larare_namn": lar["namn"]})
        s["grupper"] = ny  # avslutade grupper försvinner hos eleven (läraren har dem i sin historik)
    namn = s["foralder"].get("namn") or barn_namn
    vecka = "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])
    return {"v": 2, "namn": namn if niva >= 1 else "", "insikt": insikt(s, data, lid, body.get("insikt_fraga")) if aktiv(s, "insikt", lid) else None,
            "foralder": {k: delar(s, lid, k) for k in FUNKTIONER}, "nya_veckobrev": nya,
            "rapport": rapport(data, namn, lar=lar) if aktiv(s, "rapport", lid) else None,
            "klass": {"vecka": vecka, "poang": meriter._vecko_poang(data).get(vecka, 0)} if aktiv(s, "klasslag", lid) else None,
            "grupp_klara": [g["id"] for g in s["grupper"] if g.get("klar") and g.get("larare") in (lid, None)] if aktiv(s, "grupper", lid) else [],
            "statistik": statistik(data, lar=lar) if aktiv(s, "statistik", lid) else None,
            "studieteknik": _studieteknik_for(studieteknik, lar) if aktiv(s, "studieteknik", lid) else None,
            "schema": [{k: x.get(k) for k in ("dag", "start", "slut", "namn", "sal", "larare", "info", "ej")} for x in data.get("lektioner", [])][:80] if aktiv(s, "schema", lid) else None,
            "fran_foraldern": [x for x in s.get("utgaende", []) if aktiv(s, x["typ"], lid) and (not x.get("till") or lid in x["till"])][-20:],
            # elevens lärare (namn, ämne, roll) så att lärarna vet vem som är mentor, och samma elev-id för hela skolan
            "lararna": [{"id": x["id"], "namn": x["namn"], "amne": x.get("amne") or "", "roll": x.get("roll") or "mentor"} for x in s["lararna"].values()] if niva >= 2 else [],
            "elev_id": elev_id(s) if niva >= 2 else "",
            "mottagna": s["mottagna"][-100:], "_filer": filer}


def insikt(s: dict, data: dict, lid: str, fraga) -> dict | None:
    """Klassens insikt: bara sådant läraren kan summera för hela klassen. Ingen koppling till barnet:
    en ny slumpad kod varje vecka (inte elevens id), inga namn och inga datum."""
    if not isinstance(fraga, dict):
        return None
    idag = dt_util.now().date()
    vecka = "{}-W{:02d}".format(*idag.isocalendar()[:2])
    t = s.setdefault("insikt_token", {}).get(lid) or {}
    if t.get("vecka") != vecka:
        t = s["insikt_token"][lid] = {"vecka": vecka, "t": secrets.token_urlsafe(12)}
    amne = _text(fraga.get("amne"), 60)
    amnen = [a for a in data.get("amnen", []) if not amne or any(_amne_lika(a.get("namn", ""), x) for x in re.split(r"[,/]", amne))]
    fran = (idag - timedelta(days=21)).isoformat()
    mandag = (idag - timedelta(days=idag.weekday())).isoformat()
    fel: dict[str, int] = {}
    ovat = False
    for a in amnen:
        for g in a.get("glosor", []):
            if not any(d >= fran for d in g.get("ovat_dagar", [])) and (g.get("skapad") or "") < fran:
                continue
            ovat = ovat or any(d >= mandag for d in g.get("ovat_dagar", []))
            for o, n in (g.get("svara") or {}).items():
                if isinstance(n, int) and n > 0:
                    fel[str(o)[:60]] = fel.get(str(o)[:60], 0) + n
    prov = {}
    for p in (fraga.get("prov") or [])[:20]:
        if not isinstance(p, dict):
            continue
        u = next((u for u in data.get("uppdrag", []) if u.get("typ") == "prov" and u.get("datum") == p.get("datum")
                  and (not p.get("amne") or _amne_lika(u.get("amne_namn") or "", str(p.get("amne"))))), None)
        if u:
            prov[_text(p.get("id"), 20)] = {"dagar": len(u.get("studiedagar") or []), "plan": bool(u.get("plan"))}
    return {"token": t["t"], "ord": sorted(fel.items(), key=lambda x: -x[1])[:15], "ovat": ovat, "prov": prov}


def _studieteknik_for(t: dict | None, lar: dict) -> dict | None:
    """En ämneslärare får de allmänna studievanorna och det som gäller sitt ämne."""
    if not t or lar.get("roll") != "amne" or not lar.get("amne"):
        return t
    ut = dict(t)
    for k in ("svaga_punkter", "planer", "riktlinjer"):
        ut[k] = [x for x in (t.get(k) or []) if _for_amne(lar, x.get("amne"))]
    ut["svart"] = [x for x in (t.get("svart") or []) if any(_amne_lika(w, lar["amne"]) for w in re.findall(r"[A-Za-zÅÄÖåäö]+", str(x)))]
    return ut


def klassboss_belona(data: dict, s: dict) -> bool:
    k = s.get("klass")
    vecka = "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])
    if not aktiv(s, "klasslag") or not k or k.get("vecka") != vecka or k["skada"] < k["hp"]:
        return False
    return meriter.ge(data, KLASSBOSS_BELONING, f"🏫 Klassen besegrade {k['boss']} {k['ikon']}!", f"klassboss:{vecka}", "🏳️")


def grupp_klar(s: dict, gid: str) -> None:
    g = next((x for x in s["grupper"] if x["id"] == gid), None)
    if not g:
        raise ValueError("Gruppen finns inte längre.")
    g["klar"] = g.get("klar") or dt_util.now().isoformat(timespec="minutes")
