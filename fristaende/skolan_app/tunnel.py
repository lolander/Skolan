"""Fjärråtkomst med en gratis Cloudflare-tunnel (https-adress utan konto eller portöppning).

Snabbtunnlar får en ny slumpad adress (xxx.trycloudflare.com) varje gång de startar. Appen visar
alltid den aktuella adressen och QR-koden; telefonerna behöver skanna om efter en omstart av datorn.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import stat
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
ADRESS_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
NEDLADDNING = "https://github.com/cloudflare/cloudflared/releases/latest/download/"


def _filnamn() -> str:
    system, maskin = platform.system().lower(), platform.machine().lower()
    arm = maskin in ("arm64", "aarch64")
    if system == "windows":
        return "cloudflared-windows-amd64.exe"
    if system == "darwin":
        return "cloudflared-darwin-arm64.tgz" if arm else "cloudflared-darwin-amd64.tgz"
    return "cloudflared-linux-arm64" if arm else "cloudflared-linux-amd64"


class Tunnel:
    def __init__(self, mapp: Path, port: int, session_fn) -> None:
        self.mapp = mapp
        self.port = port
        self._session_fn = session_fn
        self.adress = ""
        self.status = "av"
        self._proc: asyncio.subprocess.Process | None = None
        self._uppgift: asyncio.Task | None = None

    @property
    def program(self) -> Path:
        return self.mapp / ("cloudflared.exe" if os.name == "nt" else "cloudflared")

    async def _hamta_program(self) -> None:
        if self.program.exists():
            return
        namn = _filnamn()
        if namn.endswith(".tgz"):
            raise RuntimeError("Fjärråtkomst stöds inte automatiskt på den här datorn.")
        self.status = "laddar ner"
        tmp = self.program.with_suffix(".tmp")
        async with self._session_fn().get(NEDLADDNING + namn) as r:
            if r.status != 200:
                raise RuntimeError(f"Kunde inte ladda ner tunnelprogrammet ({r.status}).")
            with tmp.open("wb") as f:
                async for bit in r.content.iter_chunked(1 << 16):
                    f.write(bit)
        tmp.replace(self.program)
        if os.name != "nt":
            self.program.chmod(self.program.stat().st_mode | stat.S_IEXEC)

    async def starta(self, vid_adress=None) -> None:
        if self._uppgift and not self._uppgift.done():
            return
        self._uppgift = asyncio.get_running_loop().create_task(self._kor(vid_adress))

    async def _kor(self, vid_adress) -> None:
        forsok = 0
        while True:
            try:
                await self._hamta_program()
                self.status = "startar"
                skapa = {"creationflags": 0x08000000} if os.name == "nt" else {}  # inget svart fönster i Windows
                self._proc = await asyncio.create_subprocess_exec(
                    str(self.program), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, **skapa)
                async for rad in self._proc.stderr:
                    m = ADRESS_RE.search(rad.decode(errors="ignore"))
                    if m and m.group(0) != self.adress:
                        self.adress = m.group(0)
                        self.status = "på"
                        forsok = 0
                        _LOGGER.info("Fjärradress: %s", self.adress)
                        if vid_adress:
                            vid_adress(self.adress)
                await self._proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Tunneln: %s", err)
                self.status = f"fel: {err}"
            self.adress = ""
            forsok += 1
            await asyncio.sleep(min(300, 10 * forsok))

    async def stoppa(self) -> None:
        if self._uppgift:
            self._uppgift.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
        self.adress = ""
        self.status = "av"
