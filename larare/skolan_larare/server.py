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

from . import VERSION

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
    "material": "📎 Skicka provresultat och studiematerial (PDF/foto)",
}
FIL_TYPER = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_FIL = 8 * 1024 * 1024  # samma gräns som i elevens Läxspelet
MAX_FILER_PER_SYNK = 14 * 1024 * 1024  # base64, under elevens gräns
KLASSBOSSAR = [("🐲", "Läxdraken"), ("🦖", "Glos-Rex"), ("🐙", "Kraken Glömska"), ("👹", "Jätten Slarv"),
               ("🤖", "Megaroboten"), ("🧊", "Isjätten"), ("🌋", "Lavamonstret"), ("👻", "Spökkungen")]
KLASSBOSS_PER_ELEV = 120  # ⭐ per elev som är med (ungefär en vanlig veckas plugg)
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
        self.port = port
        try:
            self.d = json.loads(self.fil.read_text("utf-8"))
        except (OSError, ValueError):
            self.d = {}
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
        self.filer = mapp / "filer"
        self.filer.mkdir(exist_ok=True)
        for k in FUNKTIONER:
            self.d["inst"].setdefault(k, False)
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
        tmp = self.fil.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.fil)

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
            if m["typ"] == "material" and (not m.get("till") or e["id"] in m["till"]):
                ut.append({"id": m["id"], "typ": "material", "titel": m["titel"], "amne": m.get("amne", ""), "text": m.get("text", ""), "_fil": m.get("fil")})
            elif m["typ"] == "prov" and e["id"] in (m.get("resultat") or {}):
                r = {k: v for k, v in m["resultat"][e["id"]].items() if k != "ver"}
                ut.append({"id": self.prov_id(m, e["id"]), "prov_id": m["id"], "typ": "prov", "titel": m["titel"], "amne": m.get("amne", ""), "text": m.get("text", ""),
                           "datum": m.get("datum", ""), "resultat": {**r, **({"max": m["max"]} if m.get("max") and "poang" in r else {})}, "_fil": m.get("fil")})
        return ut[-20:]

    def publik(self) -> dict:
        """Det läraren ser. Inga poäng per elev."""
        elever = []
        for e in self.d["elever"]:
            elever.append({"id": e["id"], "namn": e.get("namn") or "?", "senast": e.get("senast", ""), "fel": e.get("fel", ""),
                           "foralder": e.get("foralder") or {}, "rapport": e.get("rapport") if self.d["inst"].get("rapport") else None,
                           "statistik": e.get("statistik") if self.d["inst"].get("statistik") else None,
                           "veckobrev_nya": e.get("veckobrev_nya", 0)})
        mott = {e["id"]: set(e.get("mottagna") or []) for e in self.d["elever"]}
        material = []
        for m in self.d["material"][::-1]:
            if m["typ"] == "prov":
                fatt = [self.elev_namn(eid) for eid in (m.get("resultat") or {}) if self.prov_id(m, eid) in mott.get(eid, ())]
            else:
                fatt = [self.elev_namn(eid) for eid, s in mott.items() if m["id"] in s]
            material.append({**m, "fatt": fatt})
        return {"version": VERSION, "klass": self.d["klass"], "larare": self.d["larare"], "inst": self.d["inst"], "funktioner": FUNKTIONER,
                "elever": sorted(elever, key=lambda x: x["namn"].lower()), "veckobrev": self.d["veckobrev"][-10:][::-1],
                "boss": self.boss() if self.d["inst"].get("klasslag") else None, "adress": f"{lan_ip()}:{self.port}", "url": self.url,
                "grupper": [self.grupp_publik(g) for g in self.d["grupper"] if g.get("aktiv")],
                "gamla_grupper": [self.grupp_publik(g) for g in self.d["grupper"] if not g.get("aktiv")][-30:][::-1],
                "historik": self.d["historik"][-300:][::-1], "material": material,
                "veckobrev_fatt": {b["id"]: [self.elev_namn(eid) for eid, s in mott.items() if b["id"] in s] for b in self.d["veckobrev"][-10:]}}

    async def synka(self, session: ClientSession, lank: str) -> dict:
        """Synka med en elevs Skolan. Returnerar elevens rad."""
        e = next((x for x in self.d["elever"] if x["lank"] == lank), None)
        if not e:
            e = {"id": secrets.token_urlsafe(6), "lank": lank}
            self.d["elever"].append(e)
        grupper = [{"id": g["id"], "namn": g["namn"], "uppgift": g["uppgift"], "datum": g.get("datum", ""),
                    "medlemmar": [self.elev_namn(x) for x in g["medlemmar"]]}
                   for g in self.d["grupper"] if g.get("aktiv") and e["id"] in g["medlemmar"]] if self.d["inst"].get("grupper") else []
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
        if self.d["inst"].get("veckobrev"):
            for b in [b for b in self.d["veckobrev"] if b.get("vecka", "") >= vecka_nu()[:5]][-3:]:
                p = med_fil(b, b.get("fil"), "veckobrev")
                if p:
                    brev.append(p)
        material = []
        if self.d["inst"].get("material"):
            for m in self.material_for(e):
                if m["id"] not in har:
                    p = med_fil(m, m.get("_fil"), "material")
                    if p:
                        material.append(p)
        body = {"v": 1, "larar_id": self.d["larar_id"], "klass": self.d["klass"], "larare": self.d["larare"], "url": self.url,
                "inst": self.d["inst"], "veckobrev": brev, "material": material,
                "klass_status": self.boss() if self.d["inst"].get("klasslag") else None, "grupper": grupper}
        try:
            async with session.post(lank, json=body, timeout=ClientTimeout(total=120), allow_redirects=False) as r:
                svar = json.loads(await r.content.read(65536) or b"{}")
                if r.status == 404:
                    raise ValueError("Läxspelet hos eleven svarar inte på klasslänken (är skolfunktionerna på där?).")
                if r.status != 200:
                    raise ValueError(svar.get("fel") or f"Läxspelet hos eleven svarade {r.status}.")
        except ValueError as err:
            e["fel"] = str(err)
            self.spara()
            raise
        except Exception as err:  # noqa: BLE001
            e["fel"] = "Kunde inte nå elevens Läxspelet."
            self.spara()
            raise ValueError(e["fel"]) from err
        e.update({"namn": str(svar.get("namn") or "?")[:40], "foralder": {k: bool((svar.get("foralder") or {}).get(k)) for k in FUNKTIONER},
                  "senast": time.strftime("%Y-%m-%d %H:%M"), "fel": "", "skolan": str(svar.get("skolan") or "")[:12],
                  "veckobrev_nya": int(svar.get("nya_veckobrev") or 0)})
        for gid in (svar.get("grupp_klara") or [])[:20]:
            g = next((x for x in self.d["grupper"] if x["id"] == gid and e["id"] in x["medlemmar"]), None)
            if g and e["id"] not in g.setdefault("klara", {}):
                g["klara"][e["id"]] = time.strftime("%Y-%m-%d %H:%M")
                self.logga("grupp", f"{e['namn']} markerade gruppuppgiften i {g['namn']} som klar.")
        r = svar.get("rapport")
        if isinstance(r, dict) and r.get("rader") and r.get("rader") != (e.get("rapport") or {}).get("rader"):
            self.logga("rapport", f"Rapport om {e['namn']} ({r.get('fran', '')} – {r.get('till', '')}): " + " ".join(str(x) for x in r["rader"][:20]))
        e["rapport"] = {"fran": str(r.get("fran", ""))[:10], "till": str(r.get("till", ""))[:10],
                        "rader": [str(x)[:200] for x in (r.get("rader") or [])][:20]} if isinstance(r, dict) else None
        e["statistik"] = svar["statistik"] if isinstance(svar.get("statistik"), dict) else None
        if isinstance(svar.get("mottagna"), list):
            e["mottagna"] = [str(x)[:60] for x in svar["mottagna"]][-300:]
        k = svar.get("klass")
        e["klass"] = {"vecka": str(k.get("vecka", ""))[:10], "poang": max(0, min(10**5, int(k.get("poang") or 0)))} if isinstance(k, dict) else None
        self.logga("synk", f"{e['namn']} synkade.")
        self.spara()
        return e


def _bara_datorn(request: web.Request) -> None:
    if request.remote not in ("127.0.0.1", "::1"):
        raise web.HTTPForbidden(text="Bara lärarens dator kan ändra här.")


def bygg_app(klass: Klass) -> web.Application:
    app = web.Application(client_max_size=MAX_FIL + 1024 * 1024)
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
        return web.json_response(klass.publik())

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
                typ = "prov" if body.get("typ") == "prov" else "material"
                fil = fil_info(body.get("fil"))
                titel = str(body.get("titel") or "").strip()[:80]
                if not titel:
                    raise ValueError("Skriv en rubrik.")
                if typ == "material" and not fil:
                    raise ValueError("Välj en PDF eller ett foto.")
                mx = body.get("max")
                m = {"id": secrets.token_urlsafe(8), "typ": typ, "titel": titel, "amne": str(body.get("amne") or "").strip()[:40],
                     "text": str(body.get("text") or "").strip()[:1000], "datum": str(body.get("datum") or "")[:10],
                     "max": float(mx) if mx not in (None, "") and 0 < float(mx) <= 10000 else None, "fil": fil,
                     "till": [x for x in (body.get("till") or []) if any(e["id"] == x for e in d["elever"])], "resultat": {},
                     "skapad": time.strftime("%Y-%m-%d %H:%M")}
                d["material"].append(m)
                d["material"] = d["material"][-200:]
                klass.logga("prov" if typ == "prov" else "material", f"{'Prov' if typ == 'prov' else 'Studiematerial'}: {titel}" + (f" ({m['amne']})" if m["amne"] else ""))
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
            elif op in ("synka", "synka_alla"):
                s = await session()
                for e in [x for x in d["elever"] if op == "synka_alla" or x["id"] == body.get("id")]:
                    try:
                        await klass.synka(s, e["lank"])
                    except ValueError:
                        pass
            else:
                raise ValueError("Okänd åtgärd.")
        except (ValueError, TypeError, StopIteration, KeyError) as err:
            return web.json_response({"fel": str(err) or "Finns inte."}, status=400)
        klass.spara()
        return web.json_response(klass.publik())

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
            w.writerow([h["tid"], h["typ"], h["text"]])
        return web.Response(body=("\ufeff" + buf.getvalue()).encode("utf-8"), content_type="text/csv",
                            headers={"Content-Disposition": f'attachment; filename="skolan-historik-{date.today()}.csv"'})

    app.router.add_get("/api/historik.csv", historik_csv)
    app.router.add_get("/", index)
    app.router.add_get("/elev", elev)
    app.router.add_get("/ikon.png", ikon)
    app.router.add_get("/api/lage", lage)
    app.router.add_get("/api/qr.svg", qr)
    app.router.add_post("/api/andra", andra)
    app.router.add_post("/api/fil", fil_upp)
    app.router.add_get("/api/fil/{namn}", fil_ner)
    app.router.add_post("/api/elev/koppla", elev_koppla)
    return app


async def huvud(port: int = STD_PORT, nar_klar=None) -> None:
    mapp = datamapp()
    klass = Klass(mapp, port)
    runner = web.AppRunner(bygg_app(klass))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    _LOGGER.info("Läxspelet Lärare %s på port %s", VERSION, port)
    if nar_klar:
        nar_klar()
    await asyncio.Event().wait()
