"""Läxspelet Lärare: en liten server på lärarens dator.

- Läraren använder sidan på datorn (http://localhost:8770). Bara datorn själv får ändra något.
- Eleverna ansluter på lektionen från sin mobil: http://<datorns adress>:8770/elev. Elevens Skolan-app skickar
  sin klasslänk hit, och lärarappen synkar sedan direkt med elevens Skolan hemma (veckobrev, klassens boss,
  och det föräldern och läraren båda har slagit på).
- Klasslaget: läraren ser bara klassens summa, aldrig vad en enskild elev har pluggat.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import sys
import time
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import ClientSession, ClientTimeout, web

from . import VERSION, schemavy
from . import behorighet as beh
from . import windows
from .skola import Skola
from .uppdatera import Uppdaterare

_LOGGER = logging.getLogger("skolan_larare")
STD_PORT = 8770
WEBB = Path(__file__).parent / "webb"
FUNKTIONER = {
    "veckobrev": "📬 Skicka veckobrev till eleverna",
    "rapport": "📊 Ta emot veckorapporter när eleverna synkar",
    "klasslag": "🏫 Klasslag med en gemensam boss",
    "mejl": "📧 Ta emot rapporter via e-post från föräldrarna",
    "grupper": "👥 Grupper och gruppuppgifter",
    "statistik": "📈 Se statistik om hur eleverna pluggar",
    "material": "📎 Skicka provresultat, studiematerial och schema (PDF/foto)",
    "schema": "🗓️ Se elevernas digitala scheman",
    "studieteknik": "🧠 Se elevernas studieteknik (pluggplaner, vad som är svårt, AI:ns tankar)",
    "riktlinjer": "📝 Skicka riktlinjer till elevernas AI-hjälplärare",
    "lapp": "✉️ Ta emot lappar från föräldrarna (det eleven tycker är svårt)",
    "samtal": "🗣️ Ta emot underlag till utvecklingssamtalet från föräldrarna",
    "insikt": "🔎 Klassens insikt: svåra ord och plugg inför prov (bara summor, minst 5 familjer)",
}
FIL_TYPER = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_FIL = 8 * 1024 * 1024  # samma gräns som i elevens Läxspelet
MAX_FILER_PER_SYNK = 14 * 1024 * 1024  # base64, under elevens gräns
KLASSBOSSAR = [("🐲", "Läxdraken"), ("🦖", "Glos-Rex"), ("🐙", "Kraken Glömska"), ("👹", "Jätten Slarv"),
               ("🤖", "Megaroboten"), ("🧊", "Isjätten"), ("🌋", "Lavamonstret"), ("👻", "Spökkungen")]
KLASSBOSS_PER_ELEV = 120  # ⭐ per elev som är med (ungefär en vanlig veckas plugg)
REGLER_VER = "1"  # höj när reglerna i "Så gör du rätt" ändras, så att lärarna läser dem igen
LANK_RE = re.compile(r"https://[A-Za-z0-9.\-]+(?::\d+)?/api/skolan/klass/[A-Za-z0-9_\-]{20,64}")


def datamapp() -> Path:
    if os.environ.get("SKOLAN_LARARE_DATA"):
        m = Path(os.environ["SKOLAN_LARARE_DATA"])
    elif os.name == "nt":
        m = Path(os.environ.get("APPDATA", Path.home())) / "SkolanLarare"
    else:
        m = Path.home() / ".skolan_larare"
    m.mkdir(parents=True, exist_ok=True)
    return m


def logga(mapp: Path) -> None:
    h = RotatingFileHandler(mapp / "larare.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h] + ([logging.StreamHandler()] if sys.stderr else []))


def port_upptagen(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def lan_ip() -> str:
    """Datorns adress i skolans nätverk."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def vecka_nu() -> str:
    return "{}-W{:02d}".format(*date.today().isocalendar()[:2])


def normal_lank(text: str) -> str:
    m = LANK_RE.search(str(text or ""))
    if not m:
        raise ValueError("Det där är ingen klasslänk från Läxspelet.")
    host = urlparse(m.group(0)).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError("Klasslänken måste gå till elevens Läxspelet på internet.")
    except ValueError as err:
        if "internet" in str(err):
            raise
    if "." not in host or host.endswith((".local", ".lan", ".home", ".internal")):
        raise ValueError("Klasslänken måste gå till elevens Läxspelet på internet.")
    return m.group(0)


class Klass:
    """Allt läraren har: inställningar, elever, veckobrev. Sparas i klass.json."""

    def __init__(self, mapp: Path, port: int) -> None:
        self.fil = mapp / "klass.json"
        self.skyddad_fil = mapp / "klass.dat"  # krypterad med lärarens Windows-konto
        self.port = port
        self.d = {}
        self.skyddad = False
        try:
            if self.skyddad_fil.exists():
                self.d = json.loads(beh.las_skyddad(self.skyddad_fil.read_bytes()).decode("utf-8"))
                self.skyddad = True
            else:
                self.d = json.loads(self.fil.read_text("utf-8"))
        except (OSError, ValueError) as err:
            if self.fil.exists() or self.skyddad_fil.exists():
                _LOGGER.error("Kunde inte läsa klassens data: %s", err)
            if self.skyddad_fil.exists():  # läs aldrig över krypterad data med en tom klass
                raise
        self.d.setdefault("nyckel", beh.ny_nyckel())  # lärarens egen signeringsnyckel (för rektorsbeslut)
        self.d.setdefault("larar_id", secrets.token_urlsafe(12))
        self.d.setdefault("klass", "")
        self.d.setdefault("larare", "")
        self.d.setdefault("inst", {k: False for k in FUNKTIONER})
        self.d.setdefault("elever", [])
        self.d.setdefault("veckobrev", [])
        self.d.setdefault("extra", {})  # {vecka: poäng} klassens plugg i klassrummet
        self.d.setdefault("grupper", [])  # [{id, namn, medlemmar: [elev-id], uppgift, datum, skapad, aktiv, klara: {elev-id: tid}}]
        self.d.setdefault("historik", [])  # [{tid, typ, text}] allt som hänt, för lärarens rapport
        # [{id, typ: material|prov, titel, amne, text, datum, max, fil, till: [elev-id] (tom = alla), resultat: {elev-id: {...}}, skapad}]
        self.d.setdefault("material", [])
        self.d.setdefault("amne", "")  # lärarens ämne(n), t.ex. "Spanska" eller "Matte, NO"
        self.d.setdefault("roll", "mentor")  # "mentor" (får allt föräldern delar) eller "amne" (bara sitt ämne)
        self.filer = mapp / "filer"
        self.filer.mkdir(exist_ok=True)
        for k in FUNKTIONER:
            self.d["inst"].setdefault(k, False)
        self.skola = Skola(self)
        self.rensa_otillatet()
        self.spara()

    def logga(self, typ: str, text: str) -> None:
        self.d["historik"].append({"tid": time.strftime("%Y-%m-%d %H:%M"), "typ": typ, "text": text[:500]})
        self.d["historik"] = self.d["historik"][-5000:]

    def elev_namn(self, eid: str) -> str:
        return next((e.get("namn") or "?" for e in self.d["elever"] if e["id"] == eid), "?")

    def grupp_publik(self, g: dict) -> dict:
        return {**g, "namn_lista": [self.elev_namn(x) for x in g["medlemmar"]],
                "klara_namn": [self.elev_namn(x) for x in g.get("klara", {})]}

    def spara(self) -> None:
        data = json.dumps(self.d, ensure_ascii=False, indent=1).encode("utf-8")
        if beh.kan_skydda():
            try:
                tmp = self.skyddad_fil.with_suffix(".tmp")
                tmp.write_bytes(beh.skydda(data))
                tmp.replace(self.skyddad_fil)
                self.skyddad = True
                if self.fil.exists():
                    self.fil.unlink()  # den okrypterade gamla filen
                return
            except OSError as err:
                _LOGGER.warning("Kunde inte kryptera klassens data, sparar okrypterat: %s", err)
                self.skyddad = False
        tmp = self.fil.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(self.fil)

    # ---------- behörigheter (beslutas av skolans rektor) ----------
    def ratt(self) -> set[str]:
        p = (self.d.get("skola") or {}).get("policy")
        r = set(beh.niva_ratt(0)) if not p else set(beh.rensa_ratt(p.get("larare", {}).get(self.d["larar_id"], p.get("standard"))))
        mx = windows.it_policy().get("max_niva")
        if mx is not None:  # skolans IT har låst en högsta nivå på datorn
            r = {k for k in r if beh.RATTIGHETER[k][0] <= mx}
        return r

    def har(self, r: str) -> bool:
        return r in self.ratt()

    def far(self, k: str) -> bool:
        """Funktionen är påslagen av läraren OCH tillåten av rektorn."""
        return bool(self.d["inst"].get(k)) and self.har(k)

    def pseudonym(self, e: dict) -> str:
        if not e.get("nr"):
            e["nr"] = max([x.get("nr") or 0 for x in self.d["elever"]] + [0]) + 1
        return f"Familj {e['nr']}"

    def rensa_otillatet(self) -> None:
        """Ta bort kopior av elevuppgifter som läraren inte längre får ha (efter ett nytt rektorsbeslut).

        Lärarens egna anteckningar och provresultat döljs men finns kvar tills läraren raderar dem."""
        r = self.ratt()
        for e in self.d["elever"]:
            for falt, ratt in (("rapport", "rapport"), ("statistik", "statistik"), ("studieteknik", "studieteknik"),
                               ("lappar", "lapp"), ("samtal", "samtal"), ("schema", "schema")):
                if ratt not in r and e.get(falt):
                    e.pop(falt, None)
            if "namn" not in r:
                e["namn"] = self.pseudonym(e)
            if "mentor" not in r and "anteckningar" not in r:
                e.pop("lararna", None)
                e.pop("elev_id", None)
        s = self.d.get("skola")
        if s and "mentor" not in r:
            s["resultat"], s["anteckningar_in"] = {}, {}

    def dolda(self) -> dict:
        r = self.ratt()
        ant = len(self.d.get("anteckningar", [])) if "anteckningar" not in r else 0
        prov = sum(len(m.get("resultat") or {}) for m in self.d["material"] if m["typ"] == "prov") if "prov" not in r else 0
        hist = sum(1 for h in self.d["historik"] if not self.historik_ok(h))
        return {"anteckningar": ant, "prov": prov, "historik": hist, "summa": ant + prov + hist}

    HIST_RATT = {"rapport": "rapport", "lapp": "lapp", "samtal": "samtal", "prov": "prov"}

    def historik_ok(self, h: dict) -> bool:
        r = self.HIST_RATT.get(h.get("typ"))
        return not r or self.har(r)

    def radera_dolda(self) -> None:
        r = self.ratt()
        if "anteckningar" not in r:
            self.d["anteckningar"] = []
        if "prov" not in r:
            for m in self.d["material"]:
                if m["typ"] == "prov":
                    m["resultat"] = {}
        self.d["historik"] = [h for h in self.d["historik"] if self.historik_ok(h)]
        self.logga("behorighet", "Uppgifter som inte längre är tillåtna raderades.")

    def insikt(self) -> dict:
        """Klassens insikt: bara summor, och bara när minst INSIKT_MIN familjer är med."""
        v = vecka_nu()
        bidrag = list((self.d.get("insikt") or {}).get(v, {}).values())
        ut = {"vecka": v, "antal": len(bidrag), "min": beh.INSIKT_MIN, "visas": len(bidrag) >= beh.INSIKT_MIN}
        if not ut["visas"]:
            return ut
        ord_: dict[str, dict] = {}
        for b in bidrag:
            for o, fel in b.get("ord", []):
                x = ord_.setdefault(o.lower(), {"ord": o, "fel": 0, "familjer": 0})
                x["fel"] += fel
                x["familjer"] += 1
        ut["ord"] = sorted([x for x in ord_.values() if x["familjer"] >= 2], key=lambda x: (-x["familjer"], -x["fel"]))[:15]
        ut["ovat"] = sum(1 for b in bidrag if b.get("ovat"))
        prov = []
        for m in self.skola.mina_prov() if self.skola.s else [m for m in self.d["material"] if m.get("typ") == "prov" and m.get("datum")]:
            rader = [b["prov"][m["id"]] for b in bidrag if isinstance(b.get("prov"), dict) and m["id"] in b["prov"]]
            if len(rader) >= beh.INSIKT_MIN:
                pl = [x for x in rader if x.get("dagar")]
                prov.append({"titel": m.get("titel"), "datum": m.get("datum"), "med": len(rader), "pluggat": len(pl),
                             "snitt": round(sum(x["dagar"] for x in pl) / len(pl), 1) if pl else 0, "plan": sum(1 for x in rader if x.get("plan"))})
        ut["prov"] = prov
        return ut

    def ta_emot_insikt(self, x) -> None:
        if not isinstance(x, dict) or not re.fullmatch(r"[A-Za-z0-9_\-]{8,40}", str(x.get("token") or "")):
            return
        v = vecka_nu()
        ins = self.d.setdefault("insikt", {})
        for gammal in [k for k in ins if k != v]:
            ins.pop(gammal)
        ins.setdefault(v, {})[x["token"]] = {
            "ord": [[str(o)[:60], max(0, min(99, int(f)))] for o, f in (x.get("ord") or [])[:20] if isinstance(f, (int, float))],
            "ovat": bool(x.get("ovat")),
            "prov": {str(k)[:20]: {"dagar": max(0, min(60, int(v2.get("dagar") or 0))), "plan": bool(v2.get("plan"))}
                     for k, v2 in list((x.get("prov") or {}).items())[:30] if isinstance(v2, dict)}}

    def behorighet(self) -> dict:
        r = self.ratt()
        return {"niva": beh.niva_for(list(r)), "ratt": sorted(r), "nivaer": {str(k): list(v) for k, v in beh.NIVAER.items()},
                "rattigheter": {k: list(v) for k, v in beh.RATTIGHETER.items()}, "dolda": self.dolda(), "skyddad": self.skyddad,
                "kan_skydda": beh.kan_skydda(), "it_max": windows.it_policy().get("max_niva")}

    @property
    def url(self) -> str:
        return f"http://{lan_ip()}:{self.port}"

    def boss(self) -> dict:
        v = vecka_nu()
        ar, nr = int(v[:4]), int(v[-2:])
        ikon, namn = KLASSBOSSAR[(ar * 53 + nr) % len(KLASSBOSSAR)]
        med = [e for e in self.d["elever"] if (e.get("klass") or {}).get("vecka") == v]
        antal = len([e for e in self.d["elever"] if (e.get("foralder") or {}).get("klasslag")])
        hp = max(300, antal * KLASSBOSS_PER_ELEV)
        skada = sum(int(e["klass"].get("poang") or 0) for e in med) + int(self.d["extra"].get(v, 0))
        return {"namn": self.d["klass"] or "Klassen", "vecka": v, "ikon": ikon, "boss": namn, "hp": hp, "skada": min(skada, hp),
                "antal": antal, "klar": skada >= hp, "extra": int(self.d["extra"].get(v, 0))}

    def fil_data(self, fil: dict | None) -> dict | None:
        if not fil:
            return None
        import base64

        try:
            return {"namn": fil.get("orig") or fil["namn"], "mime": fil["mime"], "data": base64.b64encode((self.filer / fil["namn"]).read_bytes()).decode()}
        except OSError:
            return None

    @staticmethod
    def prov_id(m: dict, eid: str) -> str:
        """Ett nytt id när resultatet ändras, så att föräldern får det nya."""
        return f"{m['id']}-{eid}-{(m.get('resultat') or {}).get(eid, {}).get('ver', 0)}"

    def material_for(self, e: dict) -> list[dict]:
        ut = []
        for m in self.d["material"]:
            if m["typ"] in ("material", "schema") and (not m.get("till") or e["id"] in m["till"]):
                ut.append({"id": m["id"], "typ": m["typ"], "titel": m["titel"], "amne": m.get("amne", ""), "text": m.get("text", ""), "_fil": m.get("fil")})
            elif m["typ"] == "prov" and self.har("prov") and e["id"] in (m.get("resultat") or {}):
                r = {k: v for k, v in m["resultat"][e["id"]].items() if k != "ver"}
                ut.append({"id": self.prov_id(m, e["id"]), "prov_id": m["id"], "typ": "prov", "titel": m["titel"], "amne": m.get("amne", ""), "text": m.get("text", ""),
                           "datum": m.get("datum", ""), "resultat": {**r, **({"max": m["max"]} if m.get("max") and "poang" in r else {})}, "_fil": m.get("fil")})
        return ut[-20:]

    def publik(self) -> dict:
        """Det läraren ser. Inga poäng per elev."""
        kollegor = self.skola.fran_kollegor()
        elever = []
        for e in self.d["elever"]:
            elever.append({"id": e["id"], "namn": e.get("namn") or "?", "senast": e.get("senast", ""), "fel": e.get("fel", ""),
                           "foralder": e.get("foralder") or {}, "rapport": e.get("rapport") if self.far("rapport") else None,
                           "statistik": e.get("statistik") if self.far("statistik") else None,
                           "veckobrev_nya": e.get("veckobrev_nya", 0), "har_schema": bool(e.get("schema")) and bool(self.far("schema")),
                           "studieteknik": e.get("studieteknik") if self.far("studieteknik") else None,
                           "lappar": (e.get("lappar") or [])[-10:] if self.far("lapp") else [],
                           "samtal": e.get("samtal") if self.far("samtal") else None,
                           "lararna": [x for x in (e.get("lararna") or []) if x.get("id") != self.d["larar_id"]],
                           "anteckningar": self.skola.anteckningar_for(e) if self.har("anteckningar") else [],
                           "mentor": any(x.get("id") == self.d["larar_id"] and x.get("roll") == "mentor" for x in e.get("lararna") or []),
                           "fran_kollegor": kollegor.get(e.get("elev_id") or "-", []) if any(x.get("id") == self.d["larar_id"] and x.get("roll") == "mentor" for x in e.get("lararna") or []) else []})
        mott = {e["id"]: set(e.get("mottagna") or []) for e in self.d["elever"]}
        material = []
        for m in self.d["material"][::-1]:
            if m["typ"] == "prov":
                fatt = [self.elev_namn(eid) for eid in (m.get("resultat") or {}) if self.prov_id(m, eid) in mott.get(eid, ())]
            else:
                fatt = [self.elev_namn(eid) for eid, s in mott.items() if m["id"] in s]
            material.append({**m, "fatt": fatt})
        return {"version": VERSION, "klass": self.d["klass"], "larare": self.d["larare"], "inst": {k: self.far(k) for k in FUNKTIONER},
                "inst_val": self.d["inst"], "funktioner": FUNKTIONER,
                "larar_id": self.d["larar_id"], "regler_last": self.d.get("regler_last") == REGLER_VER,
                "behorighet": self.behorighet(), "insikt": self.insikt() if self.far("insikt") else None,
                "amne": self.d.get("amne", ""), "roll": self.d.get("roll", "mentor"), "skola": self.skola.publik(), "provkalender": self.skola.provkalender(),
                "elever": sorted(elever, key=lambda x: x["namn"].lower()), "veckobrev": self.d["veckobrev"][-10:][::-1],
                "boss": self.boss() if self.far("klasslag") else None, "adress": f"{lan_ip()}:{self.port}", "url": self.url,
                "grupper": [self.grupp_publik(g) for g in self.d["grupper"] if g.get("aktiv")],
                "gamla_grupper": [self.grupp_publik(g) for g in self.d["grupper"] if not g.get("aktiv")][-30:][::-1],
                "historik": [h for h in self.d["historik"] if self.historik_ok(h)][-300:][::-1], "material": [m if m["typ"] != "prov" or self.har("prov") else {**m, "resultat": {}, "fatt": []} for m in material],
                "veckobrev_fatt": {b["id"]: [self.elev_namn(eid) for eid, s in mott.items() if b["id"] in s] for b in self.d["veckobrev"][-10:]}}

    async def synka(self, session: ClientSession, lank: str) -> dict:
        """Synka med en elevs Skolan. Returnerar elevens rad."""
        # Samma elev även om familjens adress har bytts (gratistunneln får ny adress vid omstart): nyckeln i länken avgör
        svans = lank.rsplit("/", 1)[-1]
        e = next((x for x in self.d["elever"] if x["lank"] == lank or x["lank"].rsplit("/", 1)[-1] == svans), None)
        if not e:
            e = {"id": secrets.token_urlsafe(6), "lank": lank}
            self.d["elever"].append(e)
        elif e["lank"] != lank:
            e["lank"] = lank
            self.logga("synk", f"{e.get('namn') or 'En elev'} har en ny adress hemma (uppdaterad).")
        grupper = [{"id": g["id"], "namn": g["namn"], "uppgift": g["uppgift"], "datum": g.get("datum", ""),
                    "medlemmar": [self.elev_namn(x) for x in g["medlemmar"]]}
                   for g in self.d["grupper"] if g.get("aktiv") and e["id"] in g["medlemmar"]] if self.far("grupper") else []
        # Filer skickas bara en gång (elevens Läxspelet svarar med vad som har kommit fram) och bara om föräldern har slagit på funktionen.
        har = set(e.get("mottagna") or [])
        budget = [MAX_FILER_PER_SYNK]

        def med_fil(post: dict, fil: dict | None, funktion: str) -> dict | None:
            post = {k: v for k, v in post.items() if k not in ("fil", "_fil")}
            if not fil:
                return post
            if post["id"] in har or not (e.get("foralder") or {}).get(funktion):
                return None
            data = self.fil_data(fil)
            if not data or len(data["data"]) > budget[0]:
                return None  # för stort för den här synken, kommer nästa gång
            budget[0] -= len(data["data"])
            return {**post, "fil": data}

        brev = []
        if self.far("veckobrev"):
            for b in [b for b in self.d["veckobrev"] if b.get("vecka", "") >= vecka_nu()[:5]][-3:]:
                p = med_fil(b, b.get("fil"), "veckobrev")
                if p:
                    brev.append(p)
        material = []
        if self.far("material"):
            for m in self.material_for(e):
                if m["id"] not in har:
                    p = med_fil(m, m.get("_fil"), "material")
                    if p:
                        material.append(p)
        riktlinjer = []
        if self.far("riktlinjer") and (e.get("foralder") or {}).get("riktlinjer", True):
            for m in self.d["material"]:
                if m["typ"] == "riktlinje" and m["id"] not in har and (not m.get("till") or e["id"] in m["till"]):
                    riktlinjer.append({"id": m["id"], "amne": m.get("amne", ""), "text": m.get("text", "")})
        sk = self.d.get("skola")
        body = {"v": 2, "larar_id": self.d["larar_id"], "klass": self.d["klass"], "larare": self.d["larare"], "url": self.url,
                "amne": self.d.get("amne", ""), "roll": self.d.get("roll", "mentor"), "skola": {"id": sk["id"], "namn": sk["namn"]} if sk else None,
                "inst": {k: self.far(k) for k in FUNKTIONER}, "veckobrev": brev,
                "behorighet": {"niva": beh.niva_for(list(self.ratt())), "rektor": ((sk or {}).get("policy") or {}).get("rektor_namn")},
                "insikt_fraga": {"amne": self.d.get("amne", ""), "prov": [{k: m[k] for k in ("id", "titel", "amne", "datum")} for m in self.d["material"]
                                                                          if m.get("typ") == "prov" and m.get("datum", "") >= date.today().isoformat()][-20:]}
                if self.far("insikt") else None, "material": material, "riktlinjer": riktlinjer[-20:],
                "klass_status": self.boss() if self.far("klasslag") else None, "grupper": grupper}
        try:
            async with session.post(lank, json=body, timeout=ClientTimeout(total=120), allow_redirects=False) as r:
                svar = json.loads(await r.content.read(524288) or b"{}")
                if r.status == 404:
                    raise ValueError("Läxspelet hos eleven svarar inte på klasslänken (är skolfunktionerna på där?).")
                if r.status != 200:
                    raise ValueError(svar.get("fel") or f"Läxspelet hos eleven svarade {r.status}.")
        except ValueError as err:
            e["fel"] = str(err)
            self.spara()
            raise
        except Exception as err:  # noqa: BLE001
            e["fel"] = "Kunde inte nå elevens Läxspelet. Har familjen startat om? Be eleven trycka 🔄 Synka med läraren på lektionen, så får appen den nya adressen."
            self.spara()
            raise ValueError(e["fel"]) from err
        e.update({"namn": str(svar.get("namn") or "?")[:40] if self.har("namn") else self.pseudonym(e), "foralder": {k: bool((svar.get("foralder") or {}).get(k)) for k in FUNKTIONER},
                  "senast": time.strftime("%Y-%m-%d %H:%M"), "fel": "", "skolan": str(svar.get("skolan") or "")[:12],
                  "veckobrev_nya": int(svar.get("nya_veckobrev") or 0),
                  # elevens alla lärare (från familjens Läxspelet) och elev-id:t som är samma hos alla lärare
                  "lararna": [{"id": str(x.get("id") or "")[:40], "namn": str(x.get("namn") or "")[:60], "amne": str(x.get("amne") or "")[:60],
                               "roll": "amne" if x.get("roll") == "amne" else "mentor"} for x in (svar.get("lararna") or [])[:20] if isinstance(x, dict)],
                  "elev_id": str(svar.get("elev_id") or "")[:30]})
        if not (self.har("mentor") or self.har("anteckningar")):
            e.pop("lararna", None)
            e.pop("elev_id", None)
        if self.far("insikt"):
            self.ta_emot_insikt(svar.get("insikt"))
        for gid in (svar.get("grupp_klara") or [])[:20]:
            g = next((x for x in self.d["grupper"] if x["id"] == gid and e["id"] in x["medlemmar"]), None)
            if g and e["id"] not in g.setdefault("klara", {}):
                g["klara"][e["id"]] = time.strftime("%Y-%m-%d %H:%M")
                self.logga("grupp", f"{e['namn']} markerade gruppuppgiften i {g['namn']} som klar.")
        r = svar.get("rapport") if self.far("rapport") else None
        if isinstance(r, dict) and r.get("rader") and r.get("rader") != (e.get("rapport") or {}).get("rader"):
            self.logga("rapport", f"Rapport om {e['namn']} ({r.get('fran', '')} – {r.get('till', '')}): " + " ".join(str(x) for x in r["rader"][:20]))
        e["rapport"] = {"fran": str(r.get("fran", ""))[:10], "till": str(r.get("till", ""))[:10],
                        "rader": [str(x)[:200] for x in (r.get("rader") or [])][:20]} if isinstance(r, dict) else None
        e["statistik"] = svar["statistik"] if isinstance(svar.get("statistik"), dict) and self.far("statistik") else None
        e["studieteknik"] = svar["studieteknik"] if isinstance(svar.get("studieteknik"), dict) and self.far("studieteknik") else None
        kanda_lappar = {x["id"] for x in e.get("lappar", [])}
        for x in (svar.get("fran_foraldern") or [])[:20]:  # lappar och samtalsunderlag, godkända av föräldern
            if not isinstance(x, dict) or not str(x.get("id") or "").isalnum():
                continue
            if x.get("typ") == "lapp" and x["id"] not in kanda_lappar and self.far("lapp"):
                lp = {"id": str(x["id"])[:20], "tid": str(x.get("tid") or "")[:16], "namn": str(x.get("namn") or "")[:60], "text": str(x.get("text") or "")[:2000]}
                e.setdefault("lappar", []).append(lp)
                e["lappar"] = e["lappar"][-30:]
                self.logga("lapp", f"Lapp från föräldern om {e['namn']}: {lp['text'][:300]}")
            elif x.get("typ") == "samtal" and self.far("samtal") and (e.get("samtal") or {}).get("id") != x["id"]:
                e["samtal"] = {"id": str(x["id"])[:20], "tid": str(x.get("tid") or "")[:16], "fran": str(x.get("fran") or "")[:10], "till": str(x.get("till") or "")[:10],
                               "per_vecka": x.get("per_vecka") if isinstance(x.get("per_vecka"), (int, float)) else 0,
                               "amnen": {str(k)[:40]: {"gjort": [str(t)[:300] for t in (v.get("gjort") or [])][:10], "svart": [str(t)[:300] for t in (v.get("svart") or [])][:6]}
                                         for k, v in list((x.get("amnen") or {}).items())[:15] if isinstance(v, dict)},
                               "battre": [str(t)[:200] for t in (x.get("battre") or [])][:8], "ovrigt": [str(t)[:200] for t in (x.get("ovrigt") or [])][:4],
                               "ai": {k: [str(t)[:300] for t in ((x.get("ai") or {}).get(k) or [])][:4] for k in ("styrkor", "svart", "fragor")} if isinstance(x.get("ai"), dict) else None}
                self.logga("samtal", f"Underlag till utvecklingssamtalet om {e['namn']} kom från föräldern.")
        sc = svar.get("schema") if self.far("schema") else None
        e["schema"] = [{k: str(x.get(k) or "")[:80] for k in ("start", "slut", "namn", "sal", "larare", "info")} | {"dag": int(x.get("dag") or 0), "ej": bool(x.get("ej"))}
                       for x in sc[:80] if isinstance(x, dict)] if isinstance(sc, list) else None
        if isinstance(svar.get("mottagna"), list):
            e["mottagna"] = [str(x)[:60] for x in svar["mottagna"]][-300:]
        k = svar.get("klass")
        e["klass"] = {"vecka": str(k.get("vecka", ""))[:10], "poang": max(0, min(10**5, int(k.get("poang") or 0)))} if isinstance(k, dict) else None
        self.logga("synk", f"{e['namn']} synkade.")
        self.spara()
        return e


WIN: dict = {"windows": False, "brandvagg": True, "gammal": False}  # brandväggen och gammal installation (Windows)


def _bara_datorn(request: web.Request) -> None:
    if request.remote not in ("127.0.0.1", "::1"):
        raise web.HTTPForbidden(text="Bara lärarens dator kan ändra här.")


def bygg_app(klass: Klass, uppd: Uppdaterare | None = None) -> web.Application:
    @web.middleware
    async def aktivitet(request, handler):
        # automatisk uppdatering väntar tills ingen har använt appen en stund (sidans egna kollar räknas inte)
        if uppd and not (request.method == "GET" and request.path in ("/api/lage", "/api/uppdatering")):
            uppd.aktiv()
        return await handler(request)

    app = web.Application(client_max_size=MAX_FIL + 1024 * 1024, middlewares=[aktivitet])
    session_holder: dict = {}
    senast_ip: dict[str, float] = {}

    async def session() -> ClientSession:
        if "s" not in session_holder:
            session_holder["s"] = ClientSession()
        return session_holder["s"]

    async def stang(_app):
        if "s" in session_holder:
            await session_holder["s"].close()

    app.on_cleanup.append(stang)

    async def index(request):
        _bara_datorn(request)
        return web.FileResponse(WEBB / "index.html")

    async def elev(_request):
        return web.FileResponse(WEBB / "elev.html")

    async def ikon(_request):
        return web.FileResponse(WEBB / "ikon-64.png")

    async def lage(request):
        _bara_datorn(request)
        return web.json_response({**klass.publik(), "uppdatering": uppd.status() if uppd else None, "windows": WIN})

    async def uppdatering(request):
        _bara_datorn(request)
        if not uppd:
            raise web.HTTPNotFound
        if request.method == "POST":
            b = await request.json()
            try:
                if b.get("op") == "lage":
                    uppd.satt_lage(str(b.get("lage") or ""))
                elif b.get("op") == "kolla":
                    await uppd.kolla()
                elif b.get("op") == "kvittera":
                    uppd.kvittera()
                elif b.get("op") == "brandvagg":
                    await asyncio.get_running_loop().run_in_executor(None, windows.forbered)
                    for _ in range(20):  # vänta på att någon svarar på Windows-frågan
                        await asyncio.sleep(3)
                        WIN.update(await asyncio.get_running_loop().run_in_executor(None, windows.status))
                        if WIN["brandvagg"] and not WIN["gammal"]:
                            break
                elif b.get("op") == "installera":
                    if not uppd.ny:
                        await uppd.kolla()
                    asyncio.get_running_loop().create_task(uppd.installera())
                    await asyncio.sleep(0.2)
            except ValueError as err:
                return web.json_response({"fel": str(err)}, status=400)
        return web.json_response(uppd.status())

    async def schema_sida(request):
        _bara_datorn(request)
        e = next((x for x in klass.d["elever"] if x["id"] == request.match_info["eid"]), None)
        if not e or not e.get("schema") or not klass.far("schema"):
            raise web.HTTPNotFound
        return web.Response(text=schemavy.sida(f"{e.get('namn') or 'Elevens'}s schema", e["schema"]), content_type="text/html")

    async def qr(request):
        _bara_datorn(request)
        import io

        import qrcode
        import qrcode.image.svg

        buf = io.BytesIO()
        qrcode.make(klass.url + "/elev", image_factory=qrcode.image.svg.SvgPathImage, box_size=12).save(buf)
        return web.Response(body=buf.getvalue(), content_type="image/svg+xml")

    def fil_info(f) -> dict | None:
        """En fil som läraren har laddat upp med /api/fil."""
        if not isinstance(f, dict) or not re.fullmatch(r"[a-f0-9]{24}\.(pdf|jpg|png|webp)", str(f.get("namn") or "")):
            return None
        p = klass.filer / f["namn"]
        if not p.is_file():
            return None
        mime = next(k for k, v in FIL_TYPER.items() if v == p.suffix)
        return {"namn": f["namn"], "mime": mime, "orig": str(f.get("orig") or "")[:80], "storlek": p.stat().st_size}

    def ta_bort_fil(f) -> None:
        if isinstance(f, dict) and re.fullmatch(r"[a-f0-9]{24}\.(pdf|jpg|png|webp)", str(f.get("namn") or "")):
            (klass.filer / f["namn"]).unlink(missing_ok=True)

    async def fil_upp(request):
        _bara_datorn(request)
        form = await request.post()
        f = form.get("fil")
        if f is None or not hasattr(f, "file"):
            return web.json_response({"fel": "Ingen fil."}, status=400)
        b = f.file.read(MAX_FIL + 1)
        if len(b) > MAX_FIL:
            return web.json_response({"fel": "Filen är för stor (max 8 MB)."}, status=400)
        mime = "application/pdf" if b.startswith(b"%PDF") else "image/jpeg" if b[:3] == b"\xff\xd8\xff" else \
            "image/png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "image/webp" if b[8:12] == b"WEBP" else None
        if not mime:
            return web.json_response({"fel": "Bara PDF eller foto (JPG, PNG)."}, status=400)
        namn = secrets.token_hex(12) + FIL_TYPER[mime]
        (klass.filer / namn).write_bytes(b)
        return web.json_response({"namn": namn, "mime": mime, "orig": str(f.filename or "")[:80], "storlek": len(b)})

    async def fil_ner(request):
        _bara_datorn(request)
        namn = request.match_info["namn"]
        if not re.fullmatch(r"[a-f0-9]{24}\.(pdf|jpg|png|webp)", namn) or not (klass.filer / namn).is_file():
            raise web.HTTPNotFound
        return web.FileResponse(klass.filer / namn)

    async def andra(request):
        _bara_datorn(request)
        body = await request.json()
        op = body.get("op")
        d = klass.d
        try:
            if op == "installningar":
                d["klass"] = str(body.get("klass") or d["klass"])[:40]
                d["larare"] = str(body.get("larare") or d["larare"])[:60]
                if "amne" in body:
                    d["amne"] = re.sub(r"\s+", " ", str(body.get("amne") or "")).strip()[:60]
                if body.get("roll") in ("mentor", "amne"):
                    d["roll"] = body["roll"]
                for k in FUNKTIONER:
                    if k in body:
                        d["inst"][k] = bool(body[k])
            elif op == "veckobrev":
                ai = body.get("ai") if isinstance(body.get("ai"), dict) else {}
                d["veckobrev"].append({"id": secrets.token_urlsafe(8), "titel": str(body.get("titel") or "Veckobrev")[:80],
                                       "vecka": str(body.get("vecka") or vecka_nu())[:10], "skapad": time.strftime("%Y-%m-%d %H:%M"), "ai": ai,
                                       "fil": fil_info(body.get("fil"))})
                d["veckobrev"] = d["veckobrev"][-30:]
                klass.logga("veckobrev", f"Veckobrev {d['veckobrev'][-1]['titel']} (v.{d['veckobrev'][-1]['vecka']}).")
            elif op == "veckobrev_bort":
                for b in [b for b in d["veckobrev"] if b["id"] == body.get("id")]:
                    ta_bort_fil(b.get("fil"))
                d["veckobrev"] = [b for b in d["veckobrev"] if b["id"] != body.get("id")]
            elif op == "material_ny":
                typ = body.get("typ") if body.get("typ") in ("prov", "schema", "riktlinje") else "material"
                fil = fil_info(body.get("fil")) if typ != "riktlinje" else None
                titel = str(body.get("titel") or ("Riktlinje" if typ == "riktlinje" else "")).strip()[:80]
                if typ == "riktlinje" and len(str(body.get("text") or "").strip()) < 3:
                    raise ValueError("Skriv riktlinjen.")
                if not titel:
                    raise ValueError("Skriv en rubrik.")
                if typ in ("material", "schema") and not fil:
                    raise ValueError("Välj en PDF eller ett foto.")
                mx = body.get("max")
                m = {"id": secrets.token_urlsafe(8), "typ": typ, "titel": titel, "amne": str(body.get("amne") or "").strip()[:40],
                     "text": str(body.get("text") or "").strip()[:600 if typ == "riktlinje" else 1000], "datum": str(body.get("datum") or "")[:10],
                     "max": float(mx) if mx not in (None, "") and 0 < float(mx) <= 10000 else None, "fil": fil,
                     "till": [x for x in (body.get("till") or []) if any(e["id"] == x for e in d["elever"])], "resultat": {},
                     "skapad": time.strftime("%Y-%m-%d %H:%M")}
                d["material"].append(m)
                d["material"] = d["material"][-200:]
                klass.logga("prov" if typ == "prov" else "material", f"{({'prov': 'Prov', 'schema': 'Schema', 'riktlinje': 'Riktlinje till AI:n'}).get(typ, 'Studiematerial')}: {titel}" + (f" ({m['amne']})" if m["amne"] else ""))
            elif op == "material_bort":
                m = next(x for x in d["material"] if x["id"] == body.get("id"))
                ta_bort_fil(m.get("fil"))
                d["material"].remove(m)
            elif op == "prov_resultat":
                m = next(x for x in d["material"] if x["id"] == body.get("id") and x["typ"] == "prov")
                eid = str(body.get("elev") or "")
                if not any(e["id"] == eid for e in d["elever"]):
                    raise ValueError("Eleven finns inte.")
                gammal = m["resultat"].get(eid) or {}
                if body.get("rensa"):
                    m["resultat"].pop(eid, None)
                else:
                    r = {"kommentar": str(body.get("kommentar") or "").strip()[:200]}
                    betyg = str(body.get("betyg") or "").strip().upper()
                    if body.get("poang") not in (None, ""):
                        po = float(body["poang"])
                        if not m.get("max") or not 0 <= po <= m["max"]:
                            raise ValueError(f"Poängen måste vara mellan 0 och {m.get('max') or '?'}.")
                        r["poang"] = po
                    elif betyg in ("A", "B", "C", "D", "E", "F"):
                        r["betyg"] = betyg
                    else:
                        raise ValueError("Skriv poäng eller ett betyg (A–F).")
                    if {k: v for k, v in gammal.items() if k != "ver"} != r:
                        r["ver"] = gammal.get("ver", -1) + 1
                        m["resultat"][eid] = r
                        klass.logga("prov", f"Provresultat {m['titel']}, {klass.elev_namn(eid)}: "
                                    + (f"{r['poang']:g} av {m['max']:g}" if "poang" in r else f"betyg {r['betyg']}"))
            elif op == "grupp_ny":
                med = [x for x in dict.fromkeys(body.get("medlemmar") or []) if any(e["id"] == x for e in d["elever"])]
                if not med:
                    raise ValueError("Välj minst en elev.")
                g = {"id": secrets.token_urlsafe(6), "namn": str(body.get("namn") or f"Grupp {len(d['grupper']) + 1}")[:40],
                     "medlemmar": med, "uppgift": str(body.get("uppgift") or "")[:1000], "datum": str(body.get("datum") or "")[:10],
                     "skapad": time.strftime("%Y-%m-%d %H:%M"), "aktiv": True, "klara": {}}
                d["grupper"].append(g)
                klass.logga("grupp", f"Ny grupp {g['namn']}: {', '.join(klass.elev_namn(x) for x in med)}. Uppgift: {g['uppgift'] or '–'}"
                            + (f" (klar senast {g['datum']})" if g["datum"] else ""))
            elif op == "grupp_dela":  # dela slumpvis i lika stora grupper
                import random

                antal = max(1, min(20, int(body.get("antal") or 2)))
                ids = [e["id"] for e in d["elever"]]
                random.shuffle(ids)
                for i in range(antal):
                    med = ids[i::antal]
                    if med:
                        g = {"id": secrets.token_urlsafe(6), "namn": f"Grupp {i + 1}", "medlemmar": med, "uppgift": str(body.get("uppgift") or "")[:1000],
                             "datum": str(body.get("datum") or "")[:10], "skapad": time.strftime("%Y-%m-%d %H:%M"), "aktiv": True, "klara": {}}
                        d["grupper"].append(g)
                        klass.logga("grupp", f"Ny grupp {g['namn']}: {', '.join(klass.elev_namn(x) for x in med)}. Uppgift: {g['uppgift'] or '–'}")
            elif op == "grupp_avsluta":
                g = next(x for x in d["grupper"] if x["id"] == body.get("id"))
                g["aktiv"], g["avslutad"] = False, time.strftime("%Y-%m-%d %H:%M")
                klar = [klass.elev_namn(x) for x in g.get("klara", {})]
                klass.logga("grupp", f"Gruppen {g['namn']} avslutades. Klara: {', '.join(klar) or 'ingen'}. Anteckning: {str(body.get('anteckning') or '–')[:300]}")
            elif op == "anteckning":
                klass.logga("anteckning", str(body.get("text") or "")[:500])
            elif op == "elev_bort":
                d["elever"] = [e for e in d["elever"] if e["id"] != body.get("id")]
            elif op == "klassplugg":
                v = vecka_nu()
                d["extra"] = {v: max(0, int(d["extra"].get(v, 0)) + int(body.get("poang") or 0))}
                klass.logga("klasslag", f"Klassens plugg i klassrummet: +{int(body.get('poang') or 0)}.")
            elif op == "skola_ny":
                klass.skola.skapa(str(body.get("namn") or ""))
            elif op == "skola_ga_med":
                await klass.skola.ga_med(await session(), str(body.get("kod") or ""), str(body.get("adress") or "").strip() or None)
            elif op == "skola_kod":
                klass.skola.ny_kod()
            elif op == "skola_lamna":
                klass.skola.lamna()
            elif op == "skola_meddelande":
                klass.skola.skriv_meddelande(str(body.get("text") or ""), str(body.get("till") or "") or None)
                asyncio.get_running_loop().create_task(klass.skola.synka_alla(await session()))
            elif op == "skola_last":
                klass.skola.last_meddelanden()
            elif op == "anteckning_ny":
                e = next(x for x in d["elever"] if x["id"] == body.get("elev"))
                klass.skola.skriv_anteckning(e, str(body.get("amne") or ""), str(body.get("text") or ""))
            elif op == "anteckning_bort":
                d["anteckningar"] = [a for a in d.get("anteckningar", []) if a["id"] != body.get("id")]
            elif op == "rektor_bli":
                klass.skola.bli_rektor()
                asyncio.get_running_loop().create_task(klass.skola.synka_alla(await session()))
            elif op == "rektor_satt":
                klass.skola.satt_ratt(str(body.get("vem") or ""), body.get("ratt") or [], str(body.get("motivering") or ""))
                asyncio.get_running_loop().create_task(klass.skola.synka_alla(await session()))
            elif op == "rektor_aterstall":
                klass.skola.aterstall(str(body.get("vem") or ""), str(body.get("motivering") or ""))
                asyncio.get_running_loop().create_task(klass.skola.synka_alla(await session()))
            elif op == "rektor_overlat":
                klass.skola.overlat(str(body.get("vem") or ""))
                asyncio.get_running_loop().create_task(klass.skola.synka_alla(await session()))
            elif op == "regler_ok":
                d["regler_last"] = REGLER_VER
                klass.logga("behorighet", "Läste Så gör du rätt (version " + REGLER_VER + ").")
            elif op == "radera_dolda":
                klass.radera_dolda()
            elif op == "radera_klass":  # gallring, t.ex. vid läsårets slut: alla elevuppgifter bort, inställningar och skola kvar
                for m in d["material"]:
                    m["resultat"] = {}
                d.update({"elever": [], "grupper": [], "anteckningar": [], "insikt": {}, "extra": {},
                          "historik": [{"tid": time.strftime("%Y-%m-%d %H:%M"), "typ": "behorighet", "text": "All klassdata raderades (gallring)."}]})
                if klass.skola.s:
                    klass.skola.s["resultat"], klass.skola.s["anteckningar_in"] = {}, {}
                for f in klass.filer.iterdir():
                    if not any((x.get("fil") or {}).get("namn") == f.name for x in d["material"] + d["veckobrev"]):
                        f.unlink(missing_ok=True)
            elif op == "elev_lank":  # föräldern har skickat klasslänken (t.ex. med e-post), ingen mobil behövs i skolan
                await klass.synka(await session(), normal_lank(body.get("lank")))
            elif op == "skola_synka":
                await klass.skola.synka_alla(await session())
            elif op in ("synka", "synka_alla"):
                s = await session()
                for e in [x for x in d["elever"] if op == "synka_alla" or x["id"] == body.get("id")]:
                    try:
                        await klass.synka(s, e["lank"])
                    except ValueError:
                        pass
            else:
                raise ValueError("Okänd åtgärd.")
        except (ValueError, TypeError, StopIteration, KeyError, PermissionError) as err:
            return web.json_response({"fel": str(err) or "Finns inte."}, status=400)
        klass.spara()
        return web.json_response(klass.publik())

    async def skola_ga_med(request):
        """En kollega på skolans nätverk vill gå med (kräver skolans kod)."""
        try:
            return web.json_response(klass.skola.ta_emot_medlem(request.remote or "", await request.json()))
        except PermissionError as err:
            return web.json_response({"fel": str(err)}, status=403)
        except (ValueError, TypeError) as err:
            return web.json_response({"fel": str(err)}, status=400)

    async def skola_synk(request):
        """En kollega synkar (signerat med skolans nyckel)."""
        try:
            svar, sig = klass.skola.ta_emot_synk(await request.content.read(1 << 20), request.headers.get("X-Laxspelet-Signatur", ""), request.remote or "")
        except (PermissionError, ValueError) as err:
            return web.json_response({"fel": str(err)}, status=403)
        return web.Response(body=svar, content_type="application/json", headers={"X-Laxspelet-Signatur": sig})

    async def elev_koppla(request):
        """En elev ansluter från sin mobil på lektionen."""
        ip = request.remote or ""
        if time.monotonic() - senast_ip.get(ip, 0) < 3:
            return web.json_response({"fel": "Vänta lite och försök igen."}, status=429)
        senast_ip[ip] = time.monotonic()
        try:
            body = await request.json()
            lank = normal_lank(body.get("lank"))
            e = await klass.synka(await session(), lank)
        except (ValueError, TypeError) as err:
            return web.json_response({"fel": str(err)}, status=400)
        return web.json_response({"ok": True, "namn": e.get("namn"), "klass": klass.d["klass"], "nya": e.get("veckobrev_nya", 0)})

    async def historik_csv(request):
        _bara_datorn(request)
        import csv
        import io

        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Tid", "Typ", "Händelse"])
        for h in klass.d["historik"]:
            if klass.historik_ok(h):
                w.writerow([h["tid"], h["typ"], h["text"]])
        return web.Response(body=("\ufeff" + buf.getvalue()).encode("utf-8"), content_type="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="skolan-historik-{date.today()}.csv"'})

    async def beslut_csv(request):
        """Rektorns beslutslogg: vem som fått vilken behörighet, när och på vilken grund (till dataskyddsombudet)."""
        _bara_datorn(request)
        import csv
        import io

        p = klass.skola.policy or {}
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Tid", "Beslutat av", "Beslut"])
        for b in p.get("beslut", []):
            w.writerow([b.get("tid"), b.get("av"), b.get("text")])
        return web.Response(body=("\ufeff" + buf.getvalue()).encode("utf-8"), content_type="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="behorigheter-{date.today()}.csv"'})

    app.router.add_get("/api/historik.csv", historik_csv)
    app.router.add_get("/api/beslut.csv", beslut_csv)
    app.router.add_get("/", index)
    app.router.add_get("/elev", elev)
    app.router.add_get("/ikon.png", ikon)
    app.router.add_get("/api/lage", lage)
    app.router.add_get("/api/uppdatering", uppdatering)
    app.router.add_post("/api/uppdatering", uppdatering)
    app.router.add_get("/api/qr.svg", qr)
    app.router.add_get("/schema/{eid}", schema_sida)
    app.router.add_post("/api/andra", andra)
    app.router.add_post("/api/skola/ga_med", skola_ga_med)
    app.router.add_post("/api/skola/synk", skola_synk)
    app.router.add_post("/api/fil", fil_upp)
    app.router.add_get("/api/fil/{namn}", fil_ner)
    app.router.add_post("/api/elev/koppla", elev_koppla)
    return app


async def huvud(port: int = STD_PORT, nar_klar=None) -> None:
    mapp = datamapp()
    klass = Klass(mapp, port)
    uppd = Uppdaterare(mapp, VERSION, klass.d, klass.spara, port)
    runner = web.AppRunner(bygg_app(klass, uppd))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    uppd.starta()
    loop = asyncio.get_running_loop()
    skola_session: dict = {}

    async def sess() -> ClientSession:
        if "s" not in skola_session or skola_session["s"].closed:
            skola_session["s"] = ClientSession()
        return skola_session["s"]
    await klass.skola.starta(sess)
    WIN.update(await loop.run_in_executor(None, windows.status))
    # Bara den gamla installationen städas automatiskt. Brandväggen (som kräver administratör) öppnas först när läraren
    # själv vill att eleverna ska ansluta på lektionen; klasslänkar från föräldrarna fungerar utan den.
    if WIN["gammal"]:
        await loop.run_in_executor(None, windows.forbered)

        async def kolla_igen():
            for _ in range(40):
                await asyncio.sleep(3)
                WIN.update(await loop.run_in_executor(None, windows.status))
                if WIN["brandvagg"] and not WIN["gammal"]:
                    return
        loop.create_task(kolla_igen())
    _LOGGER.info("Läxspelet Lärare %s på port %s", VERSION, port)
    if nar_klar:
        nar_klar()
    await asyncio.Event().wait()
