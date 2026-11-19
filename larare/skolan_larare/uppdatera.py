"""Uppdateringar av Läxspelet Lärare (samma sätt som Windowsappen Läxspelet).

Appen frågar GitHub om det finns en nyare Skolan-Larare-Setup. Läraren väljer under Inställningar:
- automatisk (standard): appen hämtar och startar installationen själv när ingen har använt den på en stund
- manuell: läraren ser att en ny version finns och trycker "Uppdatera nu"
Windows frågar alltid "Vill du tillåta…" på datorn innan installationen körs (den behöver administratörsrätt
för brandväggsregeln som låter eleverna ansluta).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

RELEASER = "https://api.github.com/repos/lolander/Skolan/releases?per_page=10"
SIDA = "https://github.com/lolander/Skolan/releases"
KOLLA_VAR = 6 * 3600  # sekunder mellan kollarna
TYST_MIN = 15 * 60  # automatisk installation bara när ingen har använt appen på 15 minuter
SETUP = re.compile(r"^Skolan-Larare-Setup-(\d+(?:\.\d+)*)\.exe$")


def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:4])


class Uppdaterare:
    def __init__(self, mapp: Path, version: str, inst: dict, spara) -> None:
        self.mapp = mapp
        self._s = None
        self.version = version
        self.inst = inst  # klassens data: inst["uppdatering"] = "manuell" | "automatisk"
        self.spara = spara
        self.senaste: dict | None = None
        self.kollad = 0.0
        self.fel = ""
        self.steg = ""  # "", "laddar", "installerar"
        self.senast_aktiv = time.time()
        self._uppgift: asyncio.Task | None = None

    @property
    def session(self):
        from aiohttp import ClientSession
        if self._s is None or self._s.closed:
            self._s = ClientSession()
        return self._s

    # ---------- inställning ----------
    @property
    def lage(self) -> str:
        return "manuell" if self.inst.get("uppdatering") == "manuell" else "automatisk"

    def satt_lage(self, lage: str) -> None:
        self.inst["uppdatering"] = "automatisk" if lage == "automatisk" else "manuell"
        self.spara()

    def aktiv(self) -> None:
        """Någon använder appen just nu (läraren eller en elev som synkar)."""
        self.senast_aktiv = time.time()

    @property
    def ny(self) -> bool:
        return bool(self.senaste) and _ver(self.senaste["version"]) > _ver(self.version)

    def status(self) -> dict:
        return {
            "version": self.version, "lage": self.lage, "ny": self.ny,
            "senaste": self.senaste["version"] if self.senaste else None,
            "sida": self.senaste["sida"] if self.senaste else SIDA,
            "kollad": int(self.kollad), "fel": self.fel, "steg": self.steg,
            "kan_installera": os.name == "nt",
        }

    # ---------- kolla ----------
    async def kolla(self) -> None:
        try:
            async with self.session.get(RELEASER, headers={"Accept": "application/vnd.github+json"}, timeout=20) as r:
                if r.status != 200:
                    raise RuntimeError(f"GitHub svarade {r.status}")
                lista = await r.json()
            basta = None
            for rel in lista:
                if rel.get("draft"):
                    continue
                for a in rel.get("assets", []):
                    m = SETUP.match(a.get("name", ""))
                    if m and (not basta or _ver(m.group(1)) > _ver(basta["version"])):
                        basta = {"version": m.group(1), "url": a["browser_download_url"], "storlek": a.get("size", 0),
                                 "namn": a["name"], "sida": rel.get("html_url") or SIDA}
            self.senaste = basta
            self.fel = ""
        except Exception as err:  # noqa: BLE001
            self.fel = "Kunde inte kolla efter uppdateringar just nu. Appen försöker igen senare, och allt annat fungerar som vanligt."
            _LOGGER.info("Kunde inte kolla efter uppdateringar: %s", err)
        self.kollad = time.time()

    # ---------- installera ----------
    async def installera(self) -> None:
        if os.name != "nt":
            raise ValueError("Uppdateringen kan bara installeras automatiskt i Windows. Ladda ner den från GitHub.")
        if not self.ny:
            raise ValueError("Det finns ingen nyare version.")
        if self.steg:
            return
        s = self.senaste
        mapp = self.mapp / "uppdatering"
        fil = mapp / s["namn"]
        self.steg, self.fel = "laddar", ""
        try:
            mapp.mkdir(exist_ok=True)
            for gammal in mapp.glob("Skolan-Larare-Setup-*.exe"):
                if gammal != fil:
                    gammal.unlink(missing_ok=True)
            if not fil.is_file() or (s["storlek"] and fil.stat().st_size != s["storlek"]):
                tmp = fil.with_suffix(".del")
                async with self.session.get(s["url"], timeout=600) as r:
                    if r.status != 200:
                        raise RuntimeError(f"Nedladdningen misslyckades ({r.status})")
                    with tmp.open("wb") as ut:
                        async for bit in r.content.iter_chunked(1 << 16):
                            ut.write(bit)
                if s["storlek"] and tmp.stat().st_size != s["storlek"]:
                    tmp.unlink(missing_ok=True)
                    raise RuntimeError("Filen blev inte hel. Försök igen.")
                tmp.replace(fil)
            self.steg = "installerar"
            # Tyst installation. Windows frågar om lov (administratör). Installationen stänger appen
            # och startar den igen när den är klar.
            os.startfile(str(fil), "runas", "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS")  # type: ignore[attr-defined]
            _LOGGER.info("Startade uppdatering till %s", s["version"])
            await asyncio.sleep(300)  # stängs appen inte inom 5 min sa någon nej till Windows-frågan
            self.fel = "Installationen startade inte. Sa någon nej när Windows frågade? Försök igen."
        except Exception as err:  # noqa: BLE001
            self.fel = str(err) if isinstance(err, (ValueError, RuntimeError)) else f"Uppdateringen misslyckades: {err}"
            _LOGGER.warning("Uppdatering: %s", err)
        finally:
            self.steg = ""

    # ---------- bakgrund ----------
    def starta(self) -> None:
        self._uppgift = asyncio.get_running_loop().create_task(self._slinga())

    async def stoppa(self) -> None:
        if self._uppgift:
            self._uppgift.cancel()
        if self._s is not None:
            await self._s.close()

    async def _slinga(self) -> None:
        await asyncio.sleep(60)
        while True:
            if time.time() - self.kollad >= KOLLA_VAR:
                await self.kolla()
            if self.lage == "automatisk" and self.ny and not self.steg and os.name == "nt" \
                    and time.time() - self.senast_aktiv >= TYST_MIN and not self._forsokt():
                await self.installera()
            await asyncio.sleep(300)

    def _forsokt(self) -> bool:
        """Automatiskt: försök högst en gång per version och dygn (om någon sa nej till Windows-frågan)."""
        nyckel = f"{self.senaste['version']}|{time.strftime('%Y-%m-%d')}"
        if self.inst.get("uppdatering_forsok") == nyckel:
            return True
        self.inst["uppdatering_forsok"] = nyckel
        self.spara()
        return False
