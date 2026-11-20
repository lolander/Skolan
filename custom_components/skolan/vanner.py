"""Vänner mellan familjer, direkt mellan hemmens Home Assistant (som Direct Connect, ingen server).

Varje barn har en vänlänk: {familjens externa adress}/api/skolan/van/{nyckel}. Den visar bara barnets
kort (smeknamn, husdjur, nivå, stjärnor, titel). Den som har länken kan se kortet, så den delas bara
med kompisar. När en förälder godkänt en ny vän hämtar vår Home Assistant vännens kort direkt från
vännens Home Assistant och skickar samtidigt en förfrågan dit, så att den familjen kan lägga till oss.

Kräver att båda familjerna kan nås utifrån: Nabu Casa, eller Läxspelets egen gratis tunnel (grind.py) som bara
släpper fram vänlänkarna. Tunnelns adress byts vid varje omstart, så varje vänskap har en gemensam hemlighet och
hemmet meddelar sina vänner sin nya adress (signerat). Når vi inte en vän frågar vi gemensamma vänner om vännens
senaste adress. Vänner identifieras av nyckeln i länken (svansen), inte av adressen.
Ingen chatt, inget annat delas.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import time
import re
import secrets
from pathlib import Path
from urllib.parse import urlparse

from homeassistant.util import dt as dt_util

from . import meriter

PA = True  # Vänner är påslaget
TIMEOUT = 10
MAX_VANNER = 50
MAX_INKOMMANDE = 20
VAG = "/api/skolan/van/"
KOD_RE = re.compile(r"https://[A-Za-z0-9.\-]+(?::\d+)?/api/skolan/van/[A-Za-z0-9_\-]{20,64}")


def pa() -> bool:
    return PA


def svans(kod: str) -> str:
    """Nyckeln i en vänlänk (samma även när adressen byts)."""
    return str(kod or "").split(VAG, 1)[-1].split("/", 1)[0]


def samma(a: str, b: str) -> bool:
    return bool(a and b) and svans(a) == svans(b)


def _sig(hemlighet: str, *delar: str) -> str:
    return hmac.new(hemlighet.encode(), "|".join(delar).encode(), hashlib.sha256).hexdigest()


def egen_kod(bas: str, v: dict) -> str:
    return f"{bas.rstrip('/')}{VAG}{v['nyckel']}" if bas.startswith("https://") else ""


def normal_kod(text: str) -> str:
    """Plocka ut en vänlänk ur det barnet klistrat in. Bara https och inga lokala adresser."""
    m = KOD_RE.search(str(text or ""))
    if not m:
        raise ValueError("Klistra in hela vänlänken (den börjar med https:// och innehåller /api/skolan/van/).")
    kod = m.group(0)
    host = urlparse(kod).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Vänlänken måste gå att nå utifrån.")
    except ValueError as err:
        if "utifrån" in str(err):
            raise
    if "." not in host or host.endswith((".local", ".lan", ".home", ".internal", ".localdomain")):
        raise ValueError("Vänlänken måste gå att nå utifrån.")
    return kod


def smeknamn_ok(text: str) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not 2 <= len(s) <= 16:
        raise ValueError("Smeknamnet ska vara 2–16 tecken.")
    if re.search(r"\d{4,}|@|https?:|www\.", s):
        raise ValueError("Skriv inte telefonnummer, mejl eller länkar i smeknamnet.")
    return s


def _fil(mapp: Path) -> Path:
    return mapp / "vanner.json"


def las(mapp: Path) -> dict:
    f = _fil(mapp)
    try:
        v = json.loads(f.read_text("utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        v = {}
    v.setdefault("nyckel", "")
    v.setdefault("smeknamn", "")
    v.setdefault("smeknamn_ok", False)  # en förälder har godkänt smeknamnet
    v.setdefault("vanner", [])  # [{kod, smeknamn, art, niva, stjarnor, titel, hamtad, fel}]
    v.setdefault("utgaende", [])  # [{kod, tid}] barnet vill lägga till, väntar på förälder
    v.setdefault("inkommande", [])  # [{kod, smeknamn, tid}] någon vill bli vän, väntar på förälder
    v.setdefault("synkad", "")
    return v


def spara(mapp: Path, v: dict) -> None:
    tmp = _fil(mapp).with_suffix(".tmp")
    tmp.write_text(json.dumps(v, ensure_ascii=False), "utf-8")
    tmp.replace(_fil(mapp))


def se_till_nyckel(v: dict) -> bool:
    if v["nyckel"]:
        return False
    v["nyckel"] = secrets.token_urlsafe(24)
    return True


def kort(v: dict, karta: dict, titel: str | None) -> dict | None:
    """Det enda som delas med vännerna. None tills smeknamnet är godkänt."""
    if not (v["smeknamn"] and v["smeknamn_ok"]):
        return None
    return {"v": 1, "smeknamn": v["smeknamn"], "art": karta.get("art"), "niva": karta.get("niva", 1),
            "stjarnor": karta.get("stjarnor", 0), "titel": titel or "", "steg": karta.get("steg", 0),
            "attack": (karta.get("repriser") or [None])[-1], "arena_ver": meriter.ARENA_VER,
            "lag": karta.get("lag")}  # för vänlag: veckans poäng, pluggat idag, vanlig vecka


def publik(v: dict, foralder: bool, bas: str) -> dict:
    """Det appen får se."""
    return {"pa": pa(), "kod": egen_kod(bas, v) if v["smeknamn_ok"] else "", "kan_nas": bas.startswith("https://"),
            "smeknamn": v["smeknamn"], "smeknamn_ok": v["smeknamn_ok"],
            "vanner": sorted(v["vanner"], key=lambda x: (-x.get("niva", 0), -x.get("stjarnor", 0))),
            "utgaende": v["utgaende"], "inkommande": v["inkommande"], "synkad": v["synkad"], "foralder": foralder}


def _rensa_kort(k: dict) -> dict:
    return {"smeknamn": str(k.get("smeknamn") or "?")[:16], "art": str(k.get("art") or "")[:8],
            "niva": max(1, min(100000, int(k.get("niva") or 1))), "stjarnor": max(0, min(10**6, int(k.get("stjarnor") or 0))),
            "titel": str(k.get("titel") or "")[:40], "steg": max(0, min(5, int(k.get("steg") or 0))),
            "attack": meriter.repris(k["attack"]) if isinstance(k.get("attack"), dict) else None,
            "arena_ver": max(0, min(10**6, int(k.get("arena_ver") or 0))),  # 0 = vännens Skolan kan inte vänstrider
            "lag": _rensa_lag(k.get("lag"))}


def _rensa_lag(x) -> dict | None:
    if not isinstance(x, dict):
        return None
    try:
        return {"vecka_id": str(x.get("vecka_id") or "")[:10], "vecka": max(0, min(10**5, int(x.get("vecka") or 0))),
                "idag": bool(x.get("idag")), "dag": str(x.get("dag") or "")[:10], "mal": max(0, min(10**5, int(x.get("mal") or 0))),
                "cp": max(0, min(10**6, int(x.get("cp") or 0))), "def": max(0, min(100, int(x.get("def") or 0)))}
    except (TypeError, ValueError):
        return None


# ---------- ändringar ----------
def satt_smeknamn(v: dict, namn: str, foralder: bool) -> None:
    v["smeknamn"] = smeknamn_ok(namn)
    v["smeknamn_ok"] = foralder  # barnets eget smeknamn måste godkännas av en förälder


def godkann_smeknamn(v: dict) -> None:
    if not v["smeknamn"]:
        raise ValueError("Inget smeknamn att godkänna.")
    v["smeknamn_ok"] = True


def _kolla_ny(v: dict, kod: str, egen: str) -> None:
    if kod == egen or svans(kod) == v["nyckel"]:
        raise ValueError("Det är din egen vänlänk.")
    if any(samma(x["kod"], kod) for x in v["vanner"]):
        raise ValueError("Ni är redan vänner.")
    if len(v["vanner"]) >= MAX_VANNER:
        raise ValueError(f"Du kan ha högst {MAX_VANNER} vänner.")


def onska(v: dict, text: str, egen: str) -> dict:
    """Barnet klistrar in en kompis vänlänk. En förälder godkänner sedan."""
    kod = normal_kod(text)
    _kolla_ny(v, kod, egen)
    if any(samma(x["kod"], kod) for x in v["utgaende"]):
        raise ValueError("Den vännen väntar redan på godkännande.")
    rad = {"kod": kod, "tid": dt_util.now().isoformat(timespec="minutes")}
    v["utgaende"].append(rad)
    return rad


def lagg_in_van(v: dict, kod: str, k: dict, hemlighet: str | None = None) -> None:
    gammal = next((x for x in v["vanner"] if samma(x["kod"], kod)), {})
    v["vanner"] = [x for x in v["vanner"] if not samma(x["kod"], kod)]
    v["vanner"].append({"kod": kod, **_rensa_kort(k), "hamtad": dt_util.now().isoformat(timespec="minutes"), "fel": 0,
                        "hemlighet": hemlighet or gammal.get("hemlighet") or ""})
    v["utgaende"] = [x for x in v["utgaende"] if not samma(x["kod"], kod)]
    v["inkommande"] = [x for x in v["inkommande"] if not samma(x["kod"], kod)]


def ny_hemlighet() -> str:
    return secrets.token_urlsafe(24)


def inkommande_hemlighet(v: dict, kod: str) -> str:
    return next((x.get("hemlighet") or "" for x in v["inkommande"] if samma(x["kod"], kod)), "")


def ta_bort(v: dict, kod: str) -> None:
    for lista in ("vanner", "utgaende", "inkommande"):
        v[lista] = [x for x in v[lista] if not samma(x["kod"], kod)]


def ta_emot_forfragan(v: dict, text: str, smeknamn: str, hemlighet: str = "") -> dict | None:
    """En annan familjs Home Assistant säger att deras barn har lagt till vårt barn. None om den redan finns."""
    kod = normal_kod(text)
    if any(samma(x["kod"], kod) for x in v["vanner"] + v["inkommande"]):
        return None
    if len(v["inkommande"]) >= MAX_INKOMMANDE:
        raise ValueError("För många förfrågningar.")
    h = str(hemlighet or "")[:64] if re.fullmatch(r"[A-Za-z0-9_\-]{20,64}", str(hemlighet or "")) else ""
    rad = {"kod": kod, "smeknamn": str(smeknamn or "")[:16], "tid": dt_util.now().isoformat(timespec="minutes"), "hemlighet": h}
    v["inkommande"].append(rad)
    return rad


def uppdatera_van(v: dict, kod: str, k: dict | None) -> None:
    """Efter en hämtning: nytt kort, eller räkna ett misslyckat försök."""
    for x in v["vanner"]:
        if samma(x["kod"], kod):
            if k:
                x.update(_rensa_kort(k), hamtad=dt_util.now().isoformat(timespec="minutes"), fel=0)
            else:
                x["fel"] = x.get("fel", 0) + 1


# ---------- nätverk ----------
async def hamta_kort(session, kod: str) -> dict:
    """Hämta en väns kort direkt från vännens Home Assistant."""
    try:
        async with session.get(f"{kod}?json=1", timeout=TIMEOUT, allow_redirects=False) as r:
            if r.status != 200:
                raise ValueError("Vännens kort gick inte att hämta (har kompisen godkänt sitt smeknamn?).")
            text = await r.content.read(4096)
        k = json.loads(text)
        if not isinstance(k, dict) or k.get("v") != 1:
            raise ValueError("Det där verkar inte vara en vänlänk från Läxspelet.")
        return k
    except ValueError:
        raise
    except Exception as err:  # noqa: BLE001
        raise ValueError("Kunde inte nå kompisens Home Assistant just nu.") from err


def arena_koll(svar: dict, namn: str) -> None:
    """Versionskoll innan en vänstrid: båda hemmen måste ha samma arenaversion."""
    deras = svar.get("arena_ver") if isinstance(svar, dict) else None
    if not isinstance(deras, int) or "kampe" not in svar:
        raise ValueError(f"{namn} har en äldre Läxspelet som inte kan vänstrider än. Be en förälder där uppdatera Läxspelet.")
    if deras < meriter.ARENA_VER:
        raise ValueError(f"{namn} har en äldre version av Läxspelet ({str(svar.get('skolan') or '?')[:12]}). Be en förälder där uppdatera, så kan ni strida.")
    if deras > meriter.ARENA_VER:
        raise ValueError(f"{namn} har en nyare version av Läxspelet ({str(svar.get('skolan') or '?')[:12]}). Be mamma eller pappa uppdatera Läxspelet, så kan ni strida.")
    if not svar.get("kampe"):
        raise ValueError(f"{namn} har inget husdjur än.")


async def hamta_kampe(session, kod: str, namn: str) -> dict:
    """Hämta vännens husdjur för arenan direkt från vännens server, med versionskoll."""
    try:
        async with session.get(f"{kod}?json=1&arena=1", timeout=TIMEOUT, allow_redirects=False) as r:
            if r.status != 200:
                raise ValueError(f"{namn} går inte att nå just nu.")
            svar = json.loads(await r.content.read(8192))
    except ValueError:
        raise
    except Exception as err:  # noqa: BLE001
        raise ValueError(f"Kunde inte nå {namn} just nu.") from err
    arena_koll(svar, namn)
    return svar["kampe"]


async def skicka_forfragan(session, kod: str, egen: str, smeknamn: str, hemlighet: str = "") -> None:
    """Säg till vännens Home Assistant att vi har lagt till dem (så att de kan lägga till oss). Hemligheten är vänskapens."""
    try:
        async with session.post(f"{kod}/forfragan", json={"kod": egen, "smeknamn": smeknamn, "hemlighet": hemlighet}, timeout=TIMEOUT,
                                allow_redirects=False) as r:
            await r.read()
    except Exception:  # noqa: BLE001
        pass  # inte så farligt; kompisen kan lägga till oss med vår länk ändå


# ---------- ny adress (gratistunneln byter adress vid omstart) ----------
MAX_SKEV = 3600


def adress_paket(v: dict, x: dict, egen: str) -> dict:
    """Säg till en vän: vår nya vänlänk. Signerat med vänskapens hemlighet."""
    tid = str(int(time.time()))
    return {"fran": v["nyckel"], "kod": egen, "tid": tid, "sig": _sig(x["hemlighet"], "adress", v["nyckel"], egen, tid)}


def ta_emot_adress(v: dict, body: dict) -> bool:
    """En vän har fått ny adress. True om vi uppdaterade."""
    fran, kod, tid, sig = (str(body.get(k) or "") for k in ("fran", "kod", "tid", "sig"))
    x = next((y for y in v["vanner"] if svans(y["kod"]) == fran and y.get("hemlighet")), None)
    if not x or not tid.isdigit() or abs(time.time() - int(tid)) > MAX_SKEV:
        return False
    if not hmac.compare_digest(_sig(x["hemlighet"], "adress", fran, kod, tid), sig):
        return False
    ny = normal_kod(kod)
    if svans(ny) != fran:
        return False
    x["kod"], x["fel"] = ny, 0
    return True


def adressbok_fraga(v: dict, via: dict, vem: str) -> dict:
    """Fråga en gemensam vän (via) om den senaste adressen till vem (en vän vi inte når)."""
    tid = str(int(time.time()))
    return {"fran": v["nyckel"], "vem": svans(vem), "tid": tid, "sig": _sig(via["hemlighet"], "adressbok", v["nyckel"], svans(vem), tid)}


def adressbok_svar(v: dict, body: dict) -> str | None:
    """En vän frågar om en annan väns adress. Svarar bara vänner, och bara om båda är våra vänner."""
    fran, vem, tid, sig = (str(body.get(k) or "") for k in ("fran", "vem", "tid", "sig"))
    x = next((y for y in v["vanner"] if svans(y["kod"]) == fran and y.get("hemlighet")), None)
    if not x or not tid.isdigit() or abs(time.time() - int(tid)) > MAX_SKEV:
        return None
    if not hmac.compare_digest(_sig(x["hemlighet"], "adressbok", fran, vem, tid), sig):
        return None
    y = next((z for z in v["vanner"] if svans(z["kod"]) == vem), None)
    return y["kod"] if y and not y.get("fel") else None
