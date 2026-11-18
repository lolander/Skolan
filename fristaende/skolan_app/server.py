"""Skolan fristående: webbserver + Skolans integration, utan Home Assistant.

Startas av __main__.py (med ikon vid klockan i Windows) eller direkt: python -m skolan_app --utan-ikon
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import socket
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiohttp import web

ROT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
for _p in (ROT / "ha_shim", ROT.parent / "custom_components" if (ROT.parent / "custom_components").exists() else ROT / "custom_components"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from . import ai as ai_mod  # noqa: E402
from .konto import COOKIE, Konto  # noqa: E402
from .push import Push, tjanst  # noqa: E402
from .tunnel import Tunnel  # noqa: E402
from .uppdatera import Uppdaterare  # noqa: E402
from .varden import Varden  # noqa: E402

_LOGGER = logging.getLogger("skolan_app")
WEBB = Path(__file__).resolve().parent / "webb"
STD_PORT = 8765


def datamapp() -> Path:
    if os.environ.get("SKOLAN_DATA"):
        m = Path(os.environ["SKOLAN_DATA"])
    elif os.name == "nt":
        m = Path(os.environ.get("APPDATA", Path.home())) / "Skolan"
    else:
        m = Path.home() / ".skolan"
    m.mkdir(parents=True, exist_ok=True)
    return m


def lokala_adresser(port: int) -> list[str]:
    ut = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ut.append(f"http://{s.getsockname()[0]}:{port}")
        s.close()
    except OSError:
        pass
    try:
        ut.append(f"http://{socket.gethostname().lower()}:{port}")
    except OSError:
        pass
    return ut


def _version() -> str:
    try:
        import skolan  # custom_components/skolan

        return str(skolan.VERSION)
    except Exception:  # noqa: BLE001
        return "0"


def _fran_datorn(request: web.Request) -> bool:
    return (request.remote or "") in ("127.0.0.1", "::1") and "cf-connecting-ip" not in {k.lower() for k in request.headers}


class App:
    """En körning av servern. Ändras familjen startas en ny körning (Skolans vyer kan bara registreras en gång)."""

    def __init__(self, mapp: Path, port: int) -> None:
        self.mapp = mapp
        self.port = port
        self.konto = Konto(mapp)
        self.omstart = asyncio.Event()
        self.avsluta = False
        self._signerade: dict[str, tuple[str, float]] = {}
        self.app = web.Application(client_max_size=60 * 1024 * 1024)
        self.push = Push(mapp)
        self.hass = Varden(mapp, self.app, self.konto, None, self.push)
        self.hass.config.internal_url = (lokala_adresser(port) or [f"http://localhost:{port}"])[0]
        inst = self.konto.inst
        self.hass.ai = ai_mod.fran_inst(inst, self.hass.http_session)
        self.tunnel = Tunnel(mapp, port, self.hass.http_session)
        self.uppd = Uppdaterare(mapp, self.hass.http_session, _version(), inst, self.konto.spara)

    # ---------- Skolans integration ----------
    def skolan_conf(self) -> dict:
        p = self.konto.personer
        return {
            "ai_task_entity": "ai_task.gemini",
            "barn": [{"id": x["id"], "namn": x["namn"], "user_id": x["id"], "notify": tjanst(x["id"])} for x in p if x["roll"] == "barn"],
            "foraldrar": [x["id"] for x in p if x["roll"] == "foralder"],
            "foralder_notify": {x["id"]: tjanst(x["id"]) for x in p if x["roll"] == "foralder"},
        }

    async def starta_skolan(self) -> None:
        import skolan  # custom_components/skolan

        conf = skolan.CONFIG_SCHEMA({"skolan": self.skolan_conf()})["skolan"]
        await skolan.async_setup(self.hass, {"skolan": conf})

    # ---------- appens egna sidor ----------
    def anvandare(self, request: web.Request):
        return self.konto.anvandare(request)

    def kraver_foralder(self, request: web.Request):
        u = self.anvandare(request)
        if not u or not u.is_admin:
            raise web.HTTPForbidden
        return u

    def rutter(self) -> None:
        r = self.app.router
        r.add_get("/", lambda _r: web.HTTPFound("/skolan"))
        for vag in ("/skolan", "/app/installning", "/app/koppla", "/app/in"):
            r.add_get(vag, self.sida)
        r.add_get("/sw.js", self.statisk("sw.js", "application/javascript", "no-cache"))
        r.add_get("/manifest.webmanifest", self.statisk("manifest.webmanifest", "application/manifest+json"))
        r.add_get("/app/app.js", self.statisk("app.js", "application/javascript", "no-cache"))
        r.add_static("/app/bilder", WEBB / "bilder")
        r.add_get("/app/start", self.start_info)
        r.add_post("/app/login", self.login)
        r.add_post("/app/logout", self.logout)
        r.add_post("/app/kopplingskod", self.kopplingskod)
        r.add_post("/app/login_kod", self.login_kod)
        r.add_post("/app/installera", self.installera)
        r.add_post("/app/signera", self.signera)
        r.add_get("/app/installningar", self.hamta_installningar)
        r.add_post("/app/installningar", self.andra_installningar)
        r.add_get("/app/qr.svg", self.qr)
        r.add_get("/app/push/nyckel", self.push_nyckel)
        r.add_post("/app/push/prenumerera", self.push_prenumerera)
        r.add_post("/app/push/test", self.push_test)
        r.add_get("/app/uppdatering", self.uppdatering)
        r.add_post("/app/uppdatering", self.andra_uppdatering)

        @web.middleware
        async def aktivitet(request, handler):
            if request.path.startswith("/api/skolan/"):
                self.uppd.aktiv()  # automatisk uppdatering väntar tills ingen använder Skolan
            return await handler(request)

        self.app.middlewares.append(aktivitet)

        @web.middleware
        async def signerat(request, handler):
            """Kortlivade länkar (utskrift m.m.) från /app/signera."""
            sig = request.query.get("authSig")
            if sig and sig in self._signerade:
                pid, giltig = self._signerade[sig]
                if time.time() < giltig and request.path == pid.split("|", 1)[1]:
                    request = request.clone(headers={**request.headers, "Authorization": f"Bearer {pid.split('|', 1)[0]}"})
            return await handler(request)

        self.app.middlewares.append(signerat)

    def statisk(self, namn: str, typ: str, cache: str = "public, max-age=3600"):
        async def h(_request):
            return web.Response(body=(WEBB / namn).read_bytes(), content_type=typ, headers={"Cache-Control": cache})
        return h

    async def sida(self, _request: web.Request) -> web.Response:
        return web.Response(body=(WEBB / "index.html").read_bytes(), content_type="text/html", headers={"Cache-Control": "no-cache"})

    async def start_info(self, request: web.Request) -> web.Response:
        u = self.anvandare(request)
        panel = self.hass.panel
        return web.json_response({
            "installerad": self.konto.ar_installerad(),
            "fran_datorn": _fran_datorn(request),
            "personer": self.konto.publika(),
            "anvandare": {"id": u.id, "name": u.name, "is_admin": u.is_admin} if u else None,
            "panel": {"modul": panel.get("module_url"), "komponent": panel.get("webcomponent_name")} if panel else None,
            "ai": bool(self.hass.ai),
            "uppdatering": {"ny": self.uppd.ny, "senaste": self.uppd.senaste and self.uppd.senaste["version"], "lage": self.uppd.lage}
            if u and u.is_admin else None,
            "adresser": {"lokala": lokala_adresser(self.port), "fjarr": self.tunnel.adress, "fjarr_status": self.tunnel.status}
            if _fran_datorn(request) or (u and u.is_admin) else None,
        })

    async def login(self, request: web.Request) -> web.Response:
        body = await request.json()
        try:
            token = self.konto.logga_in(str(body.get("id") or ""), str(body.get("pin") or ""))
        except ValueError as err:
            return web.json_response({"message": str(err)}, status=400)
        svar = web.json_response({"token": token})
        svar.set_cookie(COOKIE, token, max_age=180 * 86400, httponly=True, samesite="Lax",
                        secure=request.headers.get("X-Forwarded-Proto") == "https" or request.secure)
        return svar

    async def kopplingskod(self, request: web.Request) -> web.Response:
        """Förälder: QR-kod som loggar in en telefon direkt som barnet."""
        self.kraver_foralder(request)
        body = await request.json()
        try:
            kod = self.konto.kopplingskod(str(body.get("id") or ""))
        except ValueError as err:
            return web.json_response({"message": str(err)}, status=400)
        lokala = lokala_adresser(self.port)
        return web.json_response({
            "lokal": f"{lokala[0]}/app/in?kod={kod}" if lokala else None,
            "fjarr": f"{self.tunnel.adress}/app/in?kod={kod}" if self.tunnel.adress else None,
            "minuter": self.konto.KOD_SEK // 60,
        })

    async def login_kod(self, request: web.Request) -> web.Response:
        body = await request.json()
        try:
            token = self.konto.logga_in_kod(str(body.get("kod") or ""))
        except ValueError as err:
            return web.json_response({"message": str(err)}, status=400)
        svar = web.json_response({"token": token})
        svar.set_cookie(COOKIE, token, max_age=180 * 86400, httponly=True, samesite="Lax",
                        secure=request.headers.get("X-Forwarded-Proto") == "https" or request.secure)
        return svar

    async def logout(self, request: web.Request) -> web.Response:
        self.konto.logga_ut(self.konto.token_fran(request))
        svar = web.json_response({})
        svar.del_cookie(COOKIE)
        return svar

    async def signera(self, request: web.Request) -> web.Response:
        if not self.anvandare(request):
            raise web.HTTPUnauthorized
        vag = str((await request.json()).get("path") or "")
        bas = vag.split("?", 1)[0]
        if not bas.startswith("/api/skolan/"):
            raise web.HTTPBadRequest
        nu = time.time()
        self._signerade = {k: v for k, v in self._signerade.items() if v[1] > nu}
        sig = secrets.token_urlsafe(24)
        self._signerade[sig] = (f"{self.konto.token_fran(request)}|{bas}", nu + 120)
        return web.json_response({"path": f"{vag}{'&' if '?' in vag else '?'}authSig={sig}"})

    async def installera(self, request: web.Request) -> web.Response:
        """Första start: bara från datorn själv, och bara innan familjen finns."""
        if self.konto.ar_installerad() or not _fran_datorn(request):
            raise web.HTTPForbidden
        body = await request.json()
        try:
            personer = body.get("personer") or []
            if not any(p.get("roll") == "foralder" for p in personer) or not any(p.get("roll") == "barn" for p in personer):
                raise ValueError("Lägg till minst en förälder och ett barn.")
            for p in personer:
                self.konto._kolla_pin(p.get("pin"))
            for p in personer:
                self.konto.lagg_till(p.get("namn"), p.get("roll"), p.get("pin"))
            nyckel = str(body.get("gemini") or "").strip()
            if nyckel:
                self.konto.inst["ai"] = {"leverantor": "gemini", "nyckel": nyckel, "modell": ""}
                self.konto.spara()
        except ValueError as err:
            self.konto.inst["personer"] = []
            self.konto.spara()
            return web.json_response({"message": str(err)}, status=400)
        self.omstart.set()
        return web.json_response({"ok": True})

    async def hamta_installningar(self, request: web.Request) -> web.Response:
        self.kraver_foralder(request)
        inst = self.konto.inst
        return web.json_response({
            "personer": [{**p, "notiser": self.push.har(p["id"])} for p in self.konto.publika()],
            "ai": bool(self.hass.ai),
            "ai_val": ({"leverantor": self.hass.ai.lev, "modell": self.hass.ai.modell, "url": self.hass.ai.url, "beskrivning": self.hass.ai.beskrivning,
                        "har_nyckel": bool(self.hass.ai.nyckel)} if self.hass.ai else None),
            "leverantorer": ai_mod.publik_lista(),
            "fjarr": bool(inst.get("fjarr")), "fjarr_status": self.tunnel.status, "fjarr_adress": self.tunnel.adress,
            "lokala": lokala_adresser(self.port),
        })

    async def andra_installningar(self, request: web.Request) -> web.Response:
        self.kraver_foralder(request)
        body = await request.json()
        op = body.get("op")
        inst = self.konto.inst
        omstart = False
        try:
            if op == "lagg_till":
                self.konto.lagg_till(body.get("namn"), body.get("roll"), body.get("pin"))
                omstart = True
            elif op == "byt_pin":
                self.konto.byt_pin(str(body.get("id")), str(body.get("pin") or ""))
            elif op == "ta_bort":
                self.konto.ta_bort(str(body.get("id")))
                omstart = True
            elif op in ("ai", "ai_modeller"):
                lev = body.get("leverantor") if body.get("leverantor") in ai_mod.LEVERANTORER else "gemini"
                nyckel = str(body.get("nyckel") or "").strip()
                gammal = inst.get("ai") or {}
                if not nyckel and gammal.get("leverantor") == lev:  # samma leverantör: behåll sparad nyckel
                    nyckel = gammal.get("nyckel", "")
                url = str(body.get("url") or "").strip()
                if url and not url.startswith(("http://", "https://")):
                    raise ValueError("Adressen ska börja med http:// eller https://")
                ny = {"leverantor": lev, "nyckel": nyckel, "modell": str(body.get("modell") or "").strip()[:120], "url": url[:300]}
                test = ai_mod.AI(ny, self.hass.http_session)
                if not test.url:
                    raise ValueError("Fyll i adressen till AI-tjänsten.")
                if op == "ai_modeller":
                    try:
                        return web.json_response({"modeller": await test.modeller()})
                    except Exception as err:  # noqa: BLE001
                        raise ValueError(f"Kunde inte hämta modeller: {err}") from err
                try:
                    res = await test.testa()
                except Exception as err:  # noqa: BLE001
                    raise ValueError(f"AI:n fungerade inte: {err}") from err
                inst["ai"] = ny
                inst.pop("gemini", None)
                self.konto.spara()
                self.hass.ai = test
                if res.get("varning"):
                    return web.json_response({"ok": True, "varning": res["varning"]})
            elif op == "fjarr":
                inst["fjarr"] = bool(body.get("pa"))
                self.konto.spara()
                if inst["fjarr"]:
                    await self.tunnel.starta(self._ny_adress)
                else:
                    await self.tunnel.stoppa()
                    self.hass.config.external_url = ""
            else:
                raise ValueError("Okänd ändring.")
        except ValueError as err:
            return web.json_response({"message": str(err)}, status=400)
        if omstart:
            self.omstart.set()
        return web.json_response({"ok": True, "omstart": omstart})

    async def uppdatering(self, request: web.Request) -> web.Response:
        self.kraver_foralder(request)
        return web.json_response(self.uppd.status())

    async def andra_uppdatering(self, request: web.Request) -> web.Response:
        self.kraver_foralder(request)
        body = await request.json()
        op = body.get("op")
        try:
            if op == "lage":
                self.uppd.satt_lage(str(body.get("lage") or ""))
            elif op == "kolla":
                await self.uppd.kolla()
            elif op == "installera":
                if not self.uppd.ny:
                    raise ValueError("Det finns ingen nyare version.")
                if os.name != "nt":
                    raise ValueError("Uppdateringen kan bara installeras automatiskt i Windows. Ladda ner den från GitHub.")
                asyncio.get_running_loop().create_task(self.uppd.installera())
                await asyncio.sleep(0.2)
            else:
                raise ValueError("Okänd ändring.")
        except ValueError as err:
            return web.json_response({"message": str(err)}, status=400)
        return web.json_response(self.uppd.status())

    def _ny_adress(self, adress: str) -> None:
        self.hass.config.external_url = adress

    async def qr(self, request: web.Request) -> web.Response:
        import io

        import qrcode
        import qrcode.image.svg

        if not self.anvandare(request) and not _fran_datorn(request):
            raise web.HTTPUnauthorized
        text = str(request.query.get("text") or "")[:300]
        if not text.startswith(("http://", "https://")):
            raise web.HTTPBadRequest
        buf = io.BytesIO()
        qrcode.make(text, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=12, border=2).save(buf)
        return web.Response(body=buf.getvalue(), content_type="image/svg+xml")

    async def push_nyckel(self, request: web.Request) -> web.Response:
        if not self.anvandare(request):
            raise web.HTTPUnauthorized
        return web.json_response({"nyckel": self.push.publik_nyckel})

    async def push_prenumerera(self, request: web.Request) -> web.Response:
        u = self.anvandare(request)
        if not u:
            raise web.HTTPUnauthorized
        try:
            self.push.prenumerera(u.id, await request.json())
        except ValueError as err:
            return web.json_response({"message": str(err)}, status=400)
        return web.json_response({"ok": True})

    async def push_test(self, request: web.Request) -> web.Response:
        u = self.anvandare(request)
        if not u:
            raise web.HTTPUnauthorized
        await self.push.skicka(tjanst(u.id), {"title": "🔔 Läxspelet", "message": "Notiserna fungerar!", "data": {"url": "/skolan"}})
        return web.json_response({"ok": True})

    # ---------- körning ----------
    async def kor(self) -> bool:
        """Kör tills omstart eller avslut. True = starta om."""
        self.rutter()
        if self.konto.ar_installerad():
            await self.starta_skolan()
        runner = web.AppRunner(self.app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", self.port).start()
        await self.hass.starta()
        self.uppd.starta()
        if self.konto.inst.get("fjarr"):
            await self.tunnel.starta(self._ny_adress)
        _LOGGER.info("Skolan körs på http://localhost:%s", self.port)
        await self.omstart.wait()
        await self.uppd.stoppa()
        await self.tunnel.stoppa()
        await self.hass.stoppa()
        await runner.cleanup()
        return not self.avsluta


def logga(mapp: Path) -> None:
    h = RotatingFileHandler(mapp / "skolan.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handlers = [h] + ([logging.StreamHandler()] if sys.stderr else [])  # inget konsolfönster i Windows
    logging.basicConfig(level=logging.INFO, handlers=handlers)


async def huvud(port: int = STD_PORT, nar_klar=None, styr=None) -> None:
    """Kör servern. styr: dict som får "app" (den aktuella körningen) så att ikonen kan avsluta."""
    mapp = datamapp()
    forsta = True
    while True:
        app = App(mapp, port)
        if styr is not None:
            styr["app"] = app
            styr["loop"] = asyncio.get_running_loop()
        if forsta and nar_klar:
            asyncio.get_running_loop().call_later(1.5, nar_klar)
        forsta = False
        if not await app.kor():
            break


def port_upptagen(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0
