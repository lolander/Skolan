"""Grinden: gratis fjärråtkomst för Läxspelets publika länkar, utan Nabu Casa och utan konto.

Familjer utan Nabu Casa behöver ändå kunna nås utifrån för vänner, lärarappen, två hem och widgeten.
Läxspelet startar då Cloudflares gratis snabbtunnel (cloudflared, ingen inloggning) mot en liten grind på
datorn själv. Grinden släpper BARA fram Läxspelets publika länkar (som har en hemlig nyckel i adressen) och
skickar dem vidare till Home Assistant. Resten av Home Assistant går inte att nå genom tunneln.

Snabbtunneln får en ny adress vid varje start. Vännerna får den nya adressen automatiskt (vanner.py), och
lärarappen får den nästa gång eleven synkar på lektionen.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shutil
import stat
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web

_LOGGER = logging.getLogger(__name__)

PORT = 8769  # grinden lyssnar bara på datorn själv (127.0.0.1)
ADRESS_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
NEDLADDNING = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
NYCKEL = r"[A-Za-z0-9_\-]{16,64}"
SLAPP = [re.compile(x) for x in (
    rf"/api/skolan/van/{NYCKEL}(/(forfragan|adress|adressbok|tillsammans))?",
    rf"/api/skolan/klass/{NYCKEL}",
    rf"/api/skolan/widget/{NYCKEL}(/bild/(glad|nojd|hungrig|ledsen)\.png|/Husdjur\.scriptable)?",
    rf"/api/skolan/plankalender/{NYCKEL}(\.ics)?",
    rf"/api/skolan/hem/{NYCKEL}/[A-Za-z0-9_\-/.]{{0,80}}",
)]
MAX_KROPP = 32 * 1024 * 1024  # veckobrev och material från lärarappen kan ha filer


def slapps(vag: str) -> bool:
    return any(r.fullmatch(vag) for r in SLAPP)


def _filnamn() -> str | None:
    m = platform.machine().lower()
    if platform.system().lower() != "linux":
        return None
    if m in ("x86_64", "amd64"):
        return "cloudflared-linux-amd64"
    if m in ("aarch64", "arm64"):
        return "cloudflared-linux-arm64"
    if m.startswith("arm"):
        return "cloudflared-linux-arm"
    return None


class Grind:
    def __init__(self, mapp: Path, ha_port: int, session: ClientSession) -> None:
        self.mapp = mapp
        self.ha_port = ha_port
        self.session = session
        self.adress = ""
        self.status = "av"
        self._runner: web.AppRunner | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._uppgift: asyncio.Task | None = None

    # ---------- grinden ----------
    async def _vidare(self, request: web.Request) -> web.StreamResponse:
        if not slapps(request.path) or request.method not in ("GET", "POST"):
            return web.Response(status=404, text="Hittades inte.")
        kropp = await request.content.read(MAX_KROPP) if request.method == "POST" else None
        rubriker = {k: v for k, v in request.headers.items() if k.lower() in ("content-type", "x-laxspelet-signatur", "accept")}
        try:
            async with self.session.request(request.method, f"http://127.0.0.1:{self.ha_port}{request.path_qs}", data=kropp,
                                            headers=rubriker, timeout=ClientTimeout(total=120), allow_redirects=False) as r:
                body = await r.read()
                ut = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "cache-control", "content-disposition", "x-laxspelet-signatur")}
                return web.Response(status=r.status, body=body, headers=ut)
        except Exception as err:  # noqa: BLE001
            _LOGGER.info("Grinden: %s", err)
            return web.Response(status=502, text="Läxspelet svarar inte just nu.")

    # ---------- tunneln ----------
    @property
    def program(self) -> Path:
        return self.mapp / "cloudflared"

    async def _hamta_program(self) -> Path:
        namn = _filnamn()
        if not namn:
            raise RuntimeError("Tunneln stöds inte på den här datorn.")
        if not self.program.exists():
            self.status = "laddar ner"
            self.mapp.mkdir(parents=True, exist_ok=True)
            tmp = self.program.with_suffix(".tmp")
            async with self.session.get(NEDLADDNING + namn, timeout=ClientTimeout(total=300)) as r:
                if r.status != 200:
                    raise RuntimeError(f"Kunde inte ladda ner tunnelprogrammet ({r.status}).")
                with tmp.open("wb") as f:
                    async for bit in r.content.iter_chunked(1 << 16):
                        f.write(bit)
            tmp.replace(self.program)
        self.program.chmod(self.program.stat().st_mode | stat.S_IEXEC)
        return self.program

    async def _starta_tunnel(self, prog: Path) -> asyncio.subprocess.Process:
        args = ("tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}")
        try:
            return await asyncio.create_subprocess_exec(str(prog), *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except PermissionError:  # mappen får inte köra program: kör en kopia från /tmp
            kopia = Path("/tmp/laxspelet-cloudflared")
            shutil.copy2(prog, kopia)
            kopia.chmod(kopia.stat().st_mode | stat.S_IEXEC)
            return await asyncio.create_subprocess_exec(str(kopia), *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)

    async def _kor(self) -> None:
        forsok = 0
        while True:
            try:
                prog = await self._hamta_program()
                self.status = "startar"
                self._proc = await self._starta_tunnel(prog)
                async for rad in self._proc.stderr:
                    m = ADRESS_RE.search(rad.decode(errors="ignore"))
                    if m and m.group(0) != self.adress:
                        self.adress, self.status, forsok = m.group(0), "på", 0
                        _LOGGER.info("Läxspelets tunnel: %s", self.adress)
                await self._proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Läxspelets tunnel: %s", err)
                self.status = f"fel: {err}"
            self.adress = ""
            forsok += 1
            await asyncio.sleep(min(600, 15 * forsok))

    # ---------- start och stopp ----------
    async def starta(self) -> None:
        if self._uppgift:
            return
        app = web.Application(client_max_size=MAX_KROPP)
        app.router.add_route("*", "/{vag:.*}", self._vidare)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", PORT).start()
        self._uppgift = asyncio.get_running_loop().create_task(self._kor())

    async def stoppa(self) -> None:
        if self._uppgift:
            self._uppgift.cancel()
            self._uppgift = None
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self.adress, self.status = "", "av"
