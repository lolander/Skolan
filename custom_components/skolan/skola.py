"""Koppling till skolan: läraren och klassen.

Föräldern och läraren bestämmer tillsammans. En funktion är bara på när BÅDA har slagit på den:
föräldern i Skolans inställningar, läraren i lärarappen (Lärarrummet för Windows).
E-postrapporten kräver bara föräldern, men läraren kan säga nej till den i lärarappen.

Lärarappen pratar med barnets Skolan via klasslänken {extern adress}/api/skolan/klass/{nyckel}
(som vänlänken: hemlig nyckel, ingen inloggning). Den skickar veckobrev och klassens läge,
och får tillbaka bara det som föräldern och läraren har slagit på.
Läraren ser aldrig enskilda barns poäng i klasslaget, bara klassens summa.

Flera lärare (från 1.95.0): eleven kan ha en mentor och ämneslärare. Alla synkar med samma klasslänk.
Föräldern väljer per lärare vad den får (annars gäller förälderns standardval). En ämneslärare får bara
sitt eget ämne i rapport, statistik och studieteknik. Föräldern kan koppla bort en lärare (den spärras).

Skolan, rektorn och mentorn (från 1.98.0): Läxspelet litar inte på vad lärarappen säger om sig själv.
- Varje synk är signerad med lärarens nyckel (Ed25519). Första synken knyter nyckeln till läraren; sedan godtas bara den.
- Föräldern godkänner skolan och rektorn en gång (och igen om rektorn byts). Rektorns intyg säger vilka behörigheter
  läraren har och vilka klasser hen är mentor för. En ämneslärare måste dessutom vara godkänd av elevens mentor
  (ämnen, klass, alla eller vissa elever). Utan intyg och roll får läraren bara det som är nivå 0.
- Lärarappen skickar med hela skolans intyg och godkännanden; vi sparar det senaste av varje, så att sänkta
  behörigheter och borttagna godkännanden slår igenom. Intyg och godkännanden gäller i högst 45 dagar.
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

from . import meriter, omsorg, skolkonto, vanner

PA = True  # visar lärare och klass i appen
VAG = "/api/skolan/klass/"
FUNKTIONER = {
    "veckobrev": ("📬", "Veckobrev från läraren", "Lärarens veckobrev hamnar i din inkorg. Du godkänner innan läxorna läggs in."),
    "rapport": ("📊", "Veckorapport till läraren i lärarappen", "När eleven synkar ser läraren en kort rapport: dagar övat, förhör och prov."),
    "klasslag": ("🏫", "Klasslag", "Klassen bekämpar en gemensam boss. Läraren ser bara klassens summa, aldrig ditt barns poäng."),
    "mejl": ("📧", "Rapport via e-post", "Läxspelet mejlar en kort rapport till läraren de dagar du väljer."),
    "grupper": ("👥", "Grupper och extrauppgifter", "Läraren kan sätta ditt barn i tillfälliga grupper med en uppgift, och skicka extrauppgifter till just ditt barn (t.ex. för att komma ikapp). Du godkänner extrauppgifterna innan de läggs in."),
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
NIVA0 = ["veckobrev", "material", "riktlinjer", "klasslag", "insikt"]  # det alla lärare får, även utan skola och rektor
GILTIG = 45 * 24 * 3600  # intyg och godkännanden (samma som i lärarappen)
MAX_SKEV = 900  # en signerad synk får vara högst 15 minuter gammal
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
    for x in s["lararna"].values():  # kopplade före 1.100.0: föräldern hade redan sett dem. Nya lärare får "godkand": False.
        x.setdefault("godkand", True)
    s.setdefault("blockerade", [])  # lärare som föräldern har kopplat bort
    s.setdefault("blockerade_pub", [])  # deras nycklar
    # skolan föräldern har godkänt: {id, namn, rektor_pub, rektor_namn, godkand, intyg: {lid: intyg}, godk: {nyckel: godkännande},
    # forslag: {typ: skola|rektor, ...} som väntar på föräldern, nekade: [rektor_pub]}
    s.setdefault("skolan", {})
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
    lar = [x for x in (s.get("lararna") or {}).values() if x.get("godkand", True)]
    if not lar:
        return {}
    mentorer = [x for x in lar if x.get("roll") == "mentor"]
    return max(mentorer or lar, key=lambda x: x.get("synkad", ""))


def delar(s: dict, lid: str, f: str) -> bool:
    """Förälderns val för just den läraren (annars förälderns standardval)."""
    lar = (s.get("lararna") or {}).get(lid) or {}
    return bool((lar.get("dela") or {}).get(f, s["foralder"].get(f)))


def far(lar: dict, r: str) -> bool:
    """Har läraren rätten r enligt rektorns intyg (och en roll från rektorn eller mentorn)? Nivå 0-saker får alla."""
    return r in NIVA0 or r in (lar.get("ratt") or [])


def aktiv(s: dict, f: str, lid: str | None = None) -> bool:
    """På bara när föräldern OCH läraren har slagit på funktionen, och rektorn har gett läraren rätten. Utan lid: hos någon av lärarna."""
    lararna = s.get("lararna") or {}
    if f == "mejl":  # ingen lärarapp behövs: förälderns val räcker (om ingen lärare har sagt nej)
        return bool(s["foralder"].get("mejl")) and all((x.get("inst") or {}).get("mejl", True) for x in lararna.values())
    if lid is not None:
        lar = lararna.get(lid) or {}
        if not lar.get("godkand", True):  # väntar på föräldern: inget delas och inget tas emot
            return False
        return delar(s, lid, f) and bool((lar.get("inst") or {}).get(f)) and far(lar, f)
    return any(aktiv(s, f, x) for x in lararna)


# ---------- signaturer, skolan och rollerna ----------
def _ub64(x: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))


def _kanon(d: dict) -> bytes:
    return json.dumps({k: v for k, v in d.items() if k != "sig"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sig_ok(pub: str, sig: str, data: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(_ub64(str(pub or ""))).verify(_ub64(str(sig or "")), data)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _signerad(d, pub: str) -> bool:
    return isinstance(d, dict) and _sig_ok(pub, d.get("sig"), _kanon(d))


def _farsk(d: dict) -> bool:
    try:
        return 0 <= dt_util.utcnow().timestamp() - float(d.get("tid") or 0) < GILTIG
    except (TypeError, ValueError):
        return False


def _intyg_for(body: dict, lid: str, pub: str) -> dict | None:
    """Lärarens eget intyg i synken, signerat av den rektor som står i intyget."""
    for c in (body.get("intyg") or [])[:200]:
        if (isinstance(c, dict) and c.get("typ") == "intyg" and c.get("lid") == lid and c.get("pub") == pub
                and _farsk(c) and _signerad(c, str(c.get("rektor_pub") or ""))):
            return c
    return None


def _kedja(sk: dict, kedja) -> str:
    """Följ rektorsbytena från den rektor föräldern har godkänt. Returnerar den senaste rektorns nyckel."""
    nu = sk["rektor_pub"]
    lankar = [x for x in (kedja or [])[:20] if isinstance(x, dict) and x.get("typ") == "rektor" and x.get("skola") == sk["id"]]
    for _ in range(len(lankar)):
        nasta = next((x for x in lankar if x.get("fran") == nu and _signerad(x, nu)), None)
        if not nasta:
            break
        nu = str(nasta.get("till") or "")
    return nu


def _ta_in(sk: dict, intyg, godk) -> None:
    """Spara skolans intyg (signerade av den godkända rektorn) och mentorernas godkännanden. Bara nyare än det vi har."""
    mina = sk.setdefault("intyg", {})
    for c in (intyg or [])[:200]:
        if (isinstance(c, dict) and c.get("typ") == "intyg" and c.get("skola") == sk["id"] and c.get("rektor_pub") == sk["rektor_pub"]
                and _farsk(c) and c.get("tid", 0) > (mina.get(c.get("lid")) or {}).get("tid", 0) and _signerad(c, sk["rektor_pub"])):
            mina[str(c["lid"])[:40]] = c
    alla = sk.setdefault("godk", {})
    for g in (godk or [])[:400]:
        if not isinstance(g, dict) or g.get("typ") != "amneslarare" or g.get("skola") != sk["id"] or not _farsk(g):
            continue
        mi = mina.get(g.get("mentor")) or {}
        k = f"{g.get('mentor')}:{g.get('lid')}|{g.get('klass')}"[:120]
        if g.get("klass") in (mi.get("mentor") or []) and g.get("tid", 0) > (alla.get(k) or {}).get("tid", 0) and _signerad(g, mi.get("pub") or ""):
            alla[k] = g
    for d in (mina, alla):  # utgångna bort
        for k in [k for k, x in d.items() if not _farsk(x)]:
            d.pop(k)


def _skolan_in(s: dict, body: dict, lid: str, pub: str) -> str | None:
    """Läraren har ett intyg från en skola. Returnerar "skola" eller "rektor" om något nytt väntar på föräldern."""
    c = _intyg_for(body, lid, pub)
    if not c:
        return None
    sk = s["skolan"]
    if c["rektor_pub"] in sk.get("nekade", []):
        return None
    paket = {"intyg": [x for x in (body.get("intyg") or [])[:200] if isinstance(x, dict)],
             "godk": [x for x in (body.get("godk") or [])[:400] if isinstance(x, dict)]}
    if not sk.get("godkand") or sk.get("id") != c["skola"]:
        f = sk.get("forslag") or {}
        if f.get("rektor_pub") == c["rektor_pub"] and f.get("id") == c["skola"]:
            f["paket"] = paket  # samma förslag, senaste intygen
            return None
        sk["forslag"] = {"typ": "skola", "id": c["skola"], "namn": _text(c.get("skola_namn"), 60), "rektor_pub": c["rektor_pub"],
                         "rektor_namn": _text(c.get("rektor_namn"), 60), "larare": _text(body.get("larare"), 60),
                         "byte": bool(sk.get("godkand")), "tid": dt_util.now().isoformat(timespec="minutes"), "paket": paket}
        return "skola"
    if c["rektor_pub"] != sk["rektor_pub"]:  # skolan har bytt rektor: giltigt bara om den godkända rektorn har lämnat över
        f = sk.get("forslag") or {}
        if _kedja(sk, body.get("kedja")) == c["rektor_pub"] and f.get("rektor_pub") != c["rektor_pub"]:
            sk["forslag"] = {"typ": "rektor", "id": sk["id"], "namn": sk.get("namn"), "rektor_pub": c["rektor_pub"],
                             "rektor_namn": _text(c.get("rektor_namn"), 60), "larare": _text(body.get("larare"), 60),
                             "tid": dt_util.now().isoformat(timespec="minutes"), "paket": paket}
            return "rektor"
        if f.get("rektor_pub") == c["rektor_pub"]:
            f["paket"] = paket
    _ta_in(sk, body.get("intyg"), body.get("godk"))
    return None


def skolan_beslut(s: dict, ok: bool) -> None:
    """Föräldern godkänner eller nekar skolan/rektorn som väntar."""
    sk = s["skolan"]
    f = sk.get("forslag")
    if not f:
        raise ValueError("Inget väntar på dig.")
    sk["forslag"] = None
    if not ok:
        sk.setdefault("nekade", []).append(f["rektor_pub"])
        sk["nekade"] = sk["nekade"][-20:]
    elif f["typ"] == "skola":
        s["skolan"] = {"id": f["id"], "namn": f["namn"], "rektor_pub": f["rektor_pub"], "rektor_namn": f["rektor_namn"], "godkand": True,
                       "godkand_tid": dt_util.now().isoformat(timespec="minutes"), "intyg": {}, "godk": {}, "nekade": sk.get("nekade", [])}
        _ta_in(s["skolan"], f["paket"]["intyg"], f["paket"]["godk"])
    else:
        sk.update({"rektor_pub": f["rektor_pub"], "rektor_namn": f["rektor_namn"], "intyg": {}, "godkand_tid": dt_util.now().isoformat(timespec="minutes")})
        _ta_in(sk, f["paket"]["intyg"], f["paket"]["godk"])
    roller(s)


def skolan_bort(s: dict) -> None:
    """Föräldern tar bort skolan: alla lärare får bara nivå 0 tills föräldern godkänner en skola igen."""
    s["skolan"] = {"nekade": s["skolan"].get("nekade", [])}
    roller(s)


def _roll(s: dict, lid: str) -> dict:
    """Lärarens roll och rättigheter, som Läxspelet själv har kontrollerat."""
    lar = s["lararna"].get(lid) or {}
    sk = s.get("skolan") or {}
    if not lar.get("pub"):
        return {"roll": "", "ratt": list(NIVA0), "orsak": "gammal"}
    if not sk.get("godkand"):
        return {"roll": "", "ratt": list(NIVA0), "orsak": "skola_vantar" if sk.get("forslag") else "ingen_skola"}
    c = sk.get("intyg", {}).get(lid)
    if not c or c.get("pub") != lar["pub"] or not _farsk(c):
        return {"roll": "", "ratt": list(NIVA0), "orsak": "inget_intyg"}
    ratt = [str(x) for x in c.get("ratt") or []][:30]
    klass = str(lar.get("klass") or "").upper()
    if klass and klass in (c.get("mentor") or []):
        return {"roll": "mentor", "ratt": ratt, "klass": klass, "rektor": sk.get("rektor_namn")}
    amnen, av = [], []
    for g in sk.get("godk", {}).values():
        mi = sk["intyg"].get(g.get("mentor")) or {}
        ml = s["lararna"].get(g.get("mentor")) or {}  # mentorn måste vara elevens mentor och ha synkat här
        if (g.get("lid") == lid and g.get("pub") == lar["pub"] and g.get("amnen") and _farsk(g) and _farsk(mi)
                and g.get("klass") in (mi.get("mentor") or []) and str(ml.get("klass") or "").upper() == g.get("klass") and ml.get("pub") == mi.get("pub")
                and (g.get("elever") is None or elev_id(s) in (g.get("elever") or []))):
            amnen += [_text(a, 40) for a in g["amnen"]]
            av.append(_text(mi.get("namn"), 60))
    if amnen:
        return {"roll": "amne", "ratt": ratt, "amnen": list(dict.fromkeys(amnen))[:8], "mentor": ", ".join(dict.fromkeys(av)), "rektor": sk.get("rektor_namn")}
    return {"roll": "", "ratt": list(NIVA0), "orsak": "ingen_roll"}


def _niva(ratt: list) -> int:
    return max([FUNK_NIVA.get(r, 2 if r in ("prov", "anteckningar", "mentor", "mejl") else 1 if r == "namn" else 0) for r in ratt if r not in NIVA0] or [0])


def roller(s: dict) -> None:
    """Räkna om alla lärares roller (efter en synk eller förälderns beslut). Mentorerna först, ämneslärarna behöver dem."""
    for lid in sorted(s.get("lararna") or {}, key=lambda k: (s["lararna"][k].get("klass") or "") == ""):
        lar = s["lararna"][lid]
        r = _roll(s, lid)
        lar.update({"roll": r["roll"], "ratt": r["ratt"], "amne": ", ".join(r.get("amnen") or []),
                    "verifierad": {k: r.get(k) for k in ("orsak", "rektor", "mentor", "klass") if r.get(k)},
                    "behorighet": {"niva": _niva(r["ratt"]), "rektor": r.get("rektor") or "", "gammal": r.get("orsak") == "gammal"}})


def status(s: dict, bas: str, foralder: bool) -> dict:
    lar = huvudlarare(s)
    lista = sorted((s.get("lararna") or {}).values(), key=lambda x: (x.get("roll") != "mentor", x.get("roll") != "amne", x.get("amne") or "", x.get("namn") or ""))
    if not foralder:  # barnet ser bara lärare som en förälder har godkänt
        lista = [x for x in lista if x.get("godkand", True)]
    ut = {"pa": PA, "aktiv": {f: aktiv(s, f) for f in FUNKTIONER}, "larare": {k: lar.get(k) for k in ("klass", "namn", "url", "synkad", "inst")} if lar else None,
          "lararna": [{**{k: x.get(k) for k in ("id", "klass", "namn", "url", "synkad", "amne", "roll", "skola", "behorighet", "verifierad")},
                       **({"inst": x.get("inst") or {}, "dela": {f: delar(s, x["id"], f) for f in FUNKTIONER},
                           "godkand": bool(x.get("godkand", True)), "vantar_sedan": x.get("vantar_sedan")} if foralder else {})} for x in lista],
          "klass": s.get("klass") if aktiv(s, "klasslag") else None, "lank": lank(bas, s), "kan_nas": bas.startswith("https://"),
          "grupper": s["grupper"] if aktiv(s, "grupper") else []}
    # Skolkontot: Microsoft/Google intygar namn och domän. En lärare vars domän skiljer sig från de andras på samma skola flaggas.
    nu = dt_util.utcnow().timestamp()
    domaner: dict = {}
    for x in lista:
        k = skolkonto.publik(x.get("konto"), nu)
        if k and k["giltig"]:
            domaner.setdefault((x.get("skola") or {}).get("id"), []).append(k["doman"])
    for x, rad in zip(lista, ut["lararna"]):
        k = skolkonto.publik(x.get("konto"), nu)
        andra = domaner.get((x.get("skola") or {}).get("id"), [])
        if k:
            k["avviker"] = bool(k["giltig"] and (x.get("skola") or {}).get("id") and len(andra) > 1 and andra.count(k["doman"]) * 2 < len(andra))
        rad["konto"] = k
        if foralder and x.get("konto_fel"):
            rad["konto_fel"] = x["konto_fel"]
    if foralder:
        sk = s.get("skolan") or {}
        ut["skolan"] = {"namn": sk.get("namn"), "rektor": sk.get("rektor_namn"), "godkand": bool(sk.get("godkand")), "sedan": sk.get("godkand_tid"),
                        "forslag": {k: v for k, v in (sk.get("forslag") or {}).items() if k != "paket"} or None}
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
    if "bara_verifierade" in body:
        f["bara_verifierade"] = bool(body["bara_verifierade"])
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


def godkann_larare(s: dict, lid: str) -> None:
    """Föräldern godkänner en lärare som väntar. Först då delas något och tas något emot."""
    lar = (s.get("lararna") or {}).get(lid)
    if not lar:
        raise ValueError("Läraren finns inte längre.")
    lar["godkand"] = True
    lar["godkand_tid"] = dt_util.now().isoformat(timespec="minutes")
    lar.pop("vantar_notis", None)
    lar.pop("vantar_sedan", None)


def anmal(s: dict, lid: str, text: str, kontakt: str, barn_namn: str) -> dict:
    """🚩 Föräldern anmäler en misstanke om en lärare till rektorn.

    Läraren spärras genast. Anmälan skickas med nästa synk till skolans andra godkända lärare, vars Lärarrummet
    lämnar den vidare till rektorn utan att visa den. Den anmälda läraren får aldrig den. Föräldern får också
    en färdig text att skicka till rektorn eller huvudmannen själv (om ingen annan lärare synkar snart)."""
    lar = (s.get("lararna") or {}).get(lid)
    if not lar:
        raise ValueError("Läraren finns inte längre.")
    text = re.sub(r"[ \t]+", " ", str(text or "")).strip()[:2000]
    if not text:
        raise ValueError("Beskriv kort vad som har hänt.")
    nu = dt_util.now().isoformat(timespec="minutes")
    k = skolkonto.publik(lar.get("konto"), dt_util.utcnow().timestamp()) or {}
    sk = s.get("skolan") or {}
    om = {"id": lid, "namn": lar.get("namn") or "?", "klass": lar.get("klass") or "", "skola": (lar.get("skola") or {}).get("namn") or "",
          "konto": f"{k.get('namn', '')} <{k.get('epost', '')}> ({k.get('lev_namn', '')})" if k else "inte verifierad",
          "synkad": lar.get("synkad") or "", "kopplad": lar.get("godkand_tid") or lar.get("vantar_sedan") or ""}
    rektor_ar_anmald = bool(sk.get("rektor_pub") and lar.get("pub") == sk.get("rektor_pub"))
    till = [x["id"] for x in (s.get("lararna") or {}).values() if x["id"] != lid and x.get("godkand", True) and x.get("pub")
            and (not sk.get("id") or (x.get("skola") or {}).get("id") == sk.get("id"))]
    post = {"id": secrets.token_hex(8), "typ": "anmalan", "tid": nu, "till": till, "om": om, "text": text,
            "kontakt": re.sub(r"\s+", " ", str(kontakt or "")).strip()[:200], "barn": barn_namn[:60], "rektor_anmald": rektor_ar_anmald}
    if till:
        s.setdefault("utgaende", []).append(post)
    s.setdefault("anmalningar", []).append({k2: post[k2] for k2 in ("id", "tid", "om", "text")} | {"till": len(till)})
    koppla_bort(s, lid)
    mottagare = "huvudmannen (kommunen eller friskolan)" if rektor_ar_anmald else f"rektorn{' ' + sk['rektor_namn'] if sk.get('rektor_namn') else ''}"
    brev = (f"Anmälan om misstanke: {om['namn']}{', klass ' + om['klass'] if om['klass'] else ''}{', ' + om['skola'] if om['skola'] else ''}\n\n"
            f"Jag är vårdnadshavare till {barn_namn}. Personen ovan kopplade sig till mitt barns Läxspelet som lärare via appen Lärarrummet.\n"
            f"Skolkonto: {om['konto']}. Senast synkad: {om['synkad'].replace('T', ' ')}.\n\n"
            f"Vad som har hänt:\n{text}\n\n"
            f"Jag har kopplat bort personen i Läxspelet. Kontakt: {post['kontakt'] or '(skriv hur du nås)'}\n")
    return {"till_antal": len(till), "mottagare": mottagare, "brev": brev, "rektor_anmald": rektor_ar_anmald}


def har_godkand_larare(s: dict) -> bool:
    return any(x.get("godkand", True) for x in (s.get("lararna") or {}).values())


def koppla_bort(s: dict, lid: str | None = None) -> None:
    if lid:  # en lärare: spärras (id och nyckel), de andra fortsätter med samma klasslänk
        lar = s.get("lararna", {}).pop(lid, None) or {}
        if lid not in s["blockerade"]:
            s["blockerade"].append(lid)
        if lar.get("pub") and lar["pub"] not in s["blockerade_pub"]:
            s["blockerade_pub"].append(lar["pub"])
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
    if not (a and b):
        return False
    # hela ord: "Moderna språk spanska" = "Spanska", men "NO" är inte "Norska"
    wa, wb = {syn.get(w, w) for w in a.split()}, {syn.get(w, w) for w in b.split()}
    return a == b or wa <= wb or wb <= wa


def _for_amne(lar: dict, amne: str | None) -> bool:
    """Ska den här läraren få något om ämnet? Mentorn får allt, en ämneslärare bara sina godkända ämnen, andra inget."""
    if lar.get("roll") == "mentor":
        return True
    if lar.get("roll") != "amne" or not lar.get("amne"):
        return False
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
def _lan_url(url: str) -> str:
    """Lärarappens adress som barnet öppnar på lektionen: bara en adress i skolans lokala nät (privat IP eller .local),
    aldrig en vanlig webbsida på internet."""
    import ipaddress
    from urllib.parse import urlparse
    if not re.fullmatch(r"https?://[\w.\-]+(:\d+)?", url or ""):
        return ""
    host = urlparse(url).hostname or ""
    try:
        return url if ipaddress.ip_address(host).is_private else ""
    except ValueError:
        return url if host.endswith(".local") else ""


def _till_barnet(text: str, n: int) -> tuple[str, bool]:
    """Fritext från läraren som visas direkt för barnet (gruppuppgifter, klassbossen). Kontaktuppgifter, länkar eller
    olämpligt innehåll visas aldrig; returnerar (text, flaggad)."""
    t = _text(text, n)
    if t and (vanner.har_kontakt(t) or omsorg.bedom(t) in ("akut", "hot", "vald", "farlig")):
        return "(Visas inte: texten innehöll kontaktuppgifter, en länk eller olämpligt innehåll. En förälder har fått veta.)", True
    return t, False


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
    slag = b.get("slag") if b.get("slag") in ("laxa", "prov", "extra") else "veckobrev"

    def iso(v):
        v = _text(v, 10)
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else ""
    # fristående läxor, prov och extrauppgifter från Lärarrummet (samma form som AI:n ger för ett veckobrev)
    uppgifter = [{"typ": "las" if x.get("typ") == "las" else "gora", "vad": _text(x.get("vad"), 200), "amne": _text(x.get("amne"), 40), "datum": iso(x.get("datum")),
                  **({"extra": True, "frivillig": bool(x.get("frivillig")), "post": str(b["id"])} if slag == "extra" else {})}
                 for x in (ai.get("uppgifter") or [])[:10] if isinstance(x, dict) and _text(x.get("vad"), 200)]
    prov = [{"namn": _text(x.get("namn"), 60) or "Prov", "amne": _text(x.get("amne"), 40), "datum": iso(x.get("datum")), "omfattning": _text(x.get("omfattning"), 200)}
            for x in (ai.get("prov") or [])[:6] if isinstance(x, dict) and iso(x.get("datum"))]
    glosor = [[_text(p[0], 80), _text(p[1], 80)] for p in (ai.get("glosor") or []) if isinstance(p, list) and len(p) == 2 and _text(p[0], 80)][:60]
    ord_ = [_text(o, 60) for o in (ai.get("ord") or []) if _text(o, 60)][:40]
    sprak = [_text(x, 20) for x in (ai.get("glosor_sprak") or [])][:2]
    return {"id": str(b["id"]), "titel": _text(b.get("titel"), 80) or "Veckobrev", "vecka": _text(b.get("vecka"), 10), "slag": slag,
            "riktad": bool(b.get("riktad")) and slag == "extra",
            "ai": {"uppgifter": uppgifter, "prov": prov, "forhor_datum": iso(ai.get("forhor_datum")) or None,
                   "ord_namn": _text(ai.get("ord_namn"), 60) or None, "ord_amne": _text(ai.get("ord_amne"), 40) or None,"kapitel": ai.get("kapitel") if isinstance(ai.get("kapitel"), int) else None, "kapitel_namn": _text(ai.get("kapitel_namn"), 60) or None,
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


def ta_emot(s: dict, data: dict, barn_namn: str, body: dict, studieteknik: dict | None = None, raw: bytes = b"", signatur: str = "",
            konto: dict | None = None) -> dict:
    """Lärarappen synkar. Returnerar svaret till läraren (bara det som är påslaget av båda och tillåtet av skolan).
    konto = resultatet av kontrollen av lärarens skolkonto ({"ok": …}, {"fel": …}, {"bort": True} eller None om synken inte säger något)."""
    lid = _text(body.get("larar_id"), 40)
    if not lid:
        raise ValueError("Saknar lärare.")
    pub = str(body.get("pub") or "")
    if lid in s.get("blockerade", []) or (pub and pub in s.get("blockerade_pub", [])):
        raise PermissionError("Föräldern har kopplat bort dig från den här eleven.")
    signerad = False
    if signatur:
        try:
            tid_ok = abs(dt_util.utcnow().timestamp() - float(body.get("tid") or 0)) <= MAX_SKEV
        except (TypeError, ValueError):
            tid_ok = False
        if not re.fullmatch(r"[A-Za-z0-9_\-]{40,50}", pub) or not _sig_ok(pub, signatur, raw):
            raise PermissionError("Synken var inte signerad av läraren.")
        if not tid_ok:
            raise PermissionError("Klockan på lärarens dator går fel (mer än 15 minuter). Ställ klockan och försök igen.")
        signerad = True
    gammal = s["lararna"].get(lid)
    if gammal and gammal.get("pub") and (not signerad or gammal["pub"] != pub):
        raise PermissionError("Det här är inte samma lärarapp som förut. Be föräldern koppla bort den gamla läraren och koppla in igen.")
    if signerad and konto and "ok" in konto:
        har_konto = True
    elif konto and ("bort" in konto or "fel" in konto):
        har_konto = False
    else:
        k = skolkonto.publik((gammal or {}).get("konto"), dt_util.utcnow().timestamp())
        har_konto = bool(k and k["giltig"])
    if s["foralder"].get("bara_verifierade") and not har_konto:
        raise PermissionError("Föräldern tar bara emot lärare som har verifierat sig med sitt skolkonto. Verifiera dig i Lärarrummet under ⚙️ Inställningar."
                              + (f" ({konto['fel']})" if konto and konto.get("fel") else ""))
    inst = body.get("inst") if isinstance(body.get("inst"), dict) else {}
    ny = lid not in s["lararna"]
    if ny and len(s["lararna"]) >= 20:
        raise ValueError("Eleven har redan många lärare kopplade.")
    sk = body.get("skola") if isinstance(body.get("skola"), dict) else {}
    lar = s["lararna"].setdefault(lid, {"dela": {}, "godkand": False})
    lar.update({"id": lid, "klass": _text(body.get("klass"), 40), "namn": _text(body.get("larare"), 60),
                "url": _lan_url(_text(body.get("url"), 80)),
                "inst": {k: bool(inst.get(k)) for k in FUNKTIONER}, "synkad": dt_util.now().isoformat(timespec="minutes"),
                "skola": {"id": _text(sk.get("id"), 40), "namn": _text(sk.get("namn"), 60)} if sk.get("id") else None})
    if signerad:
        lar["pub"] = pub
        if konto and "ok" in konto:
            lar["konto"] = konto["ok"]
            lar.pop("konto_fel", None)
        elif konto and "bort" in konto:
            lar.pop("konto", None)
            lar.pop("konto_fel", None)
        elif konto and "fel" in konto:
            lar["konto_fel"] = _text(konto["fel"], 200)
    forslag = _skolan_in(s, body, lid, pub) if signerad else None
    if ny and not forslag and lar.get("pub"):
        forslag = "larare"
    roller(s)
    if not lar.get("godkand"):
        # Skydd mot att någon som fått tag på klasslänken utger sig för att vara lärare: ingenting når barnet och
        # ingenting om barnet lämnar hemmet förrän en förälder uttryckligen har godkänt just den här läraren.
        nu_ts = dt_util.utcnow().timestamp()
        paminn = ny or nu_ts - float(lar.get("vantar_notis") or 0) > 24 * 3600
        if paminn:
            lar["vantar_notis"] = nu_ts
        lar.setdefault("vantar_sedan", dt_util.now().isoformat(timespec="minutes"))
        return {"_vantar": True, "_forslag": (forslag or "larare") if paminn else None, "_filer": []}
    niva = lar["behorighet"]["niva"]
    nya = 0
    filer: list[tuple[str, bytes]] = []
    budget = [MAX_FILER_PER_SYNK * 4 // 3]
    kanda = set(s.setdefault("mottagna", [])) | {x["id"] for x in s["inkorg"]}
    nu = dt_util.now().isoformat(timespec="minutes")
    flaggor: list[str] = []  # fritext till barnet som stoppades: föräldern får veta

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
            if r and r.get("riktad") and not aktiv(s, "grupper", lid):
                continue  # extrauppgift till just det här barnet: föräldern har inte slagit på grupper och extrauppgifter
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
                rt = _text(m.get("text"), 600)
                if vanner.har_kontakt(rt) or omsorg.bedom(rt) in ("akut", "hot", "vald", "farlig"):  # når aldrig AI:n, föräldern får veta
                    flaggor.append(f"riktlinje till AI:n: {rt[:200]}")
                    kanda.add(m["id"])
                    s["mottagna"].append(m["id"])
                    continue
                in_korg({"id": m["id"], "typ": "riktlinje", "titel": "Riktlinje till AI:n", "amne": _text(m.get("amne"), 40), "text": rt}, None)
    mentor_finns = any(x.get("roll") == "mentor" and x["id"] != lid and aktiv(s, "klasslag", x["id"]) for x in s["lararna"].values())
    if aktiv(s, "klasslag", lid) and isinstance(body.get("klass_status"), dict) and (lar["roll"] == "mentor" or not mentor_finns):
        k = body["klass_status"]
        try:
            boss, fl = _till_barnet(k.get("boss"), 40)
            if fl:
                flaggor.append(f"klassbossens namn: {_text(k.get('boss'), 40)}")
                boss = "Klassbossen"
            s["klass"] = {"namn": _text(k.get("namn"), 40), "vecka": _text(k.get("vecka"), 10), "ikon": _text(k.get("ikon"), 4),
                          "boss": boss, "hp": max(1, min(10**7, int(k.get("hp") or 1))),
                          "skada": max(0, min(10**7, int(k.get("skada") or 0))), "antal": max(0, min(1000, int(k.get("antal") or 0))), "larare": lid}
        except (TypeError, ValueError):
            pass
    if aktiv(s, "grupper", lid):
        gamla = {g["id"]: g for g in s["grupper"]}
        ny = [g for g in s["grupper"] if g.get("larare") and g.get("larare") != lid]  # andra lärares grupper ligger kvar
        for g in (body.get("grupper") or [])[:10]:
            if isinstance(g, dict) and re.fullmatch(r"[A-Za-z0-9_\-]{4,20}", str(g.get("id") or "")):
                gnamn, fl1 = _till_barnet(g.get("namn"), 40)
                uppg, fl2 = _till_barnet(g.get("uppgift"), 1000)
                if fl1 or fl2:
                    flaggor.append(f"gruppuppgift: {_text(g.get('namn'), 40)}: {_text(g.get('uppgift'), 300)}")
                ny.append({"id": g["id"], "namn": "Grupp" if fl1 else gnamn, "uppgift": uppg, "datum": _text(g.get("datum"), 10),
                           "medlemmar": [_text(x, 40) for x in (g.get("medlemmar") or [])][:40], "klar": (gamla.get(g["id"]) or {}).get("klar", ""),
                           "larare": lid, "larare_namn": lar["namn"]})
        s["grupper"] = ny  # avslutade grupper försvinner hos eleven (läraren har dem i sin historik)
    namn = s["foralder"].get("namn") or barn_namn
    vecka = "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])
    return {"v": 3, "namn": namn if far(lar, "namn") and niva >= 1 else "", "_forslag": forslag, "insikt": insikt(s, data, lid, body.get("insikt_fraga")) if aktiv(s, "insikt", lid) else None,
            "foralder": {k: delar(s, lid, k) for k in FUNKTIONER}, "nya_veckobrev": nya,
            "rapport": rapport(data, namn, lar=lar) if aktiv(s, "rapport", lid) else None,
            "klass": {"vecka": vecka, "poang": meriter._vecko_poang(data).get(vecka, 0)} if aktiv(s, "klasslag", lid) else None,
            "grupp_klara": [g["id"] for g in s["grupper"] if g.get("klar") and g.get("larare") in (lid, None)] if aktiv(s, "grupper", lid) else [],
            # extrauppgifter från läraren som barnet är klart med (godkända av föräldern), bara läraren som skickade dem
            "extra_klara": [u["larar_post"] for u in data.get("uppdrag", []) if u.get("larar_post") and u.get("klart") and u.get("larar_id") in (lid, None)][-40:],
            "statistik": statistik(data, lar=lar) if aktiv(s, "statistik", lid) else None,
            "studieteknik": _studieteknik_for(studieteknik, lar) if aktiv(s, "studieteknik", lid) else None,
            "schema": [{k: x.get(k) for k in ("dag", "start", "slut", "namn", "sal", "larare", "info", "ej")} for x in data.get("lektioner", [])][:80] if aktiv(s, "schema", lid) else None,
            "fran_foraldern": [x for x in s.get("utgaende", []) if (lid in (x.get("till") or []) if x["typ"] == "anmalan"
                                                                     else aktiv(s, x["typ"], lid) and (not x.get("till") or lid in x["till"]))][-20:],
            # elevens lärare (namn, ämne, roll) så att lärarna vet vem som är mentor, och samma elev-id för hela skolan
            "lararna": [{"id": x["id"], "namn": x["namn"], "amne": x.get("amne") or "", "roll": x.get("roll") or ""} for x in s["lararna"].values()]
            if far(lar, "mentor") or far(lar, "anteckningar") else [],
            "elev_id": elev_id(s) if far(lar, "namn") and niva >= 1 else "",
            "mottagna": s["mottagna"][-100:], "_filer": filer, "_flaggor": flaggor}


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
    if not t or lar.get("roll") == "mentor":
        return t
    if lar.get("roll") != "amne" or not lar.get("amne"):
        return None
    ut = dict(t)
    for k in ("svaga_punkter", "planer", "riktlinjer"):
        ut[k] = [x for x in (t.get(k) or []) if _for_amne(lar, x.get("amne"))]
    ut["svart"] = [x for x in (t.get("svart") or []) if any(_amne_lika(w, lar["amne"]) for w in re.findall(r"[A-Za-zÅÄÖåäö]+", str(x)))]
    return ut


def amnes_larare(s: dict, data: dict) -> dict:
    """Vilken lärare hör till varje ämne (det barnet ser på ämnet)? {ämnes-id: {namn, kalla}}.
    Först en ämneslärare som skolan har godkänt för ämnet (mentorns godkännande), annars läraren i schemat."""
    ut: dict = {}
    godkanda = [x for x in (s.get("lararna") or {}).values() if x.get("roll") == "amne" and x.get("amne")]
    for a in data.get("amnen", []):
        lar = next((x for x in godkanda if _for_amne(x, a.get("namn"))), None)
        if lar:
            ut[a["id"]] = {"namn": _text(lar.get("namn"), 60), "kalla": "skolan"}
            continue
        namn: dict[str, int] = {}
        for le in data.get("lektioner", []):
            if (le.get("amne") == a["id"] or _amne_lika(le.get("namn") or "", a.get("namn") or "")) and _text(le.get("larare"), 40) and not le.get("ej"):
                namn[_text(le["larare"], 40)] = namn.get(_text(le["larare"], 40), 0) + 1
        if namn:
            ut[a["id"]] = {"namn": max(namn, key=namn.get), "kalla": "schema"}
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
