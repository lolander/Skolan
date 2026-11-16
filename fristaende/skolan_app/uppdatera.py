"""Uppdateringar av Windowsappen.

Appen frågar GitHub om det finns en nyare Skolan-Setup. Föräldrarna väljer i Inställningar:
- manuell: en förälder ser att en ny version finns och trycker "Uppdatera nu"
- automatisk: appen hämtar och startar installationen själv när ingen har använt Skolan på en stund
Windows frågar alltid "Vill du tillåta…" på datorn innan installationen körs (den behöver administratörsrätt).
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
TYST_MIN = 15 * 60  # automatisk installation bara när ingen har använt Skolan på 15 minuter
SETUP = re.compile(r"^Skolan-Setup-(\d+(?:\.\d+)*)\.exe$")


def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:4])


class Uppdaterare:
    def __init__(self, mapp: Path, session, version: str, inst: dict, spara) -> None:
        self.mapp = mapp
        self._session = session  # en ClientSession eller en funktion som ger en
        self.version = version
        self.inst = inst  # konto.inst: inst["uppdatering"] = "manuell" | "automatisk"
        self.spara = spara
        self.senaste: dict | None = None
        self.kollad = 0.0
        self.fel = ""
        self.steg = ""  # "", "laddar", "installerar"
        self.senast_aktiv = time.time()
        self._uppgift: asyncio.Task | None = None

    @property
    def session(self):
        return self._session() if callable(self._session) else self._session

    # ---------- inställning ----------
    @property
    def lage(self) -> str:
        return "automatisk" if self.inst.get("uppdatering") == "automatisk" else "manuell"

    def satt_lage(self, lage: str) -> None:
        self.inst["uppdatering"] = "automatisk" if lage == "automatisk" else "manuell"
        self.spara()

    def aktiv(self) -> None:
        """Någon använder Skolan just nu (anropas för varje förfrågan till Skolan)."""
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
            self.fel = f"Kunde inte kolla efter uppdateringar: {err}"
            _LOGGER.info(self.fel)
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
            for gammal in mapp.glob("Skolan-Setup-*.exe"):
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
            # Tyst installation. Windows frågar om lov (administratör). Installationen stänger Skolan
            # och startar den igen när den är klar.
            os.startfile(str(fil), "runas", "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS")  # type: ignore[attr-defined]
            _LOGGER.info("Startade uppdatering till %s", s["version"])
            await asyncio.sleep(300)  # stängs Skolan inte inom 5 min sa någon nej till Windows-frågan
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
