"""Automatiska uppdateringar av Lärarrummet (utan certifikat och utan att Windows frågar).

- Appen är installerad per användare (%LOCALAPPDATA%\\Programs), så installationen behöver ingen administratör.
- Var 6:e timme frågar appen GitHub (lolander/Skolan) om det finns en nyare Skolan-Larare-Setup.
- Filen kontrolleras mot sitt fingeravtryck (SHA-256, en .sha256-fil i samma release) innan den körs.
- Automatiskt (standard): installeras tyst när appen inte har använts på 15 minuter. Appen startar om själv.
- En vakt kollar efter några minuter att den nya versionen svarar. Gör den inte det installeras den förra
  versionen igen, och den trasiga versionen hoppas över tills en ännu nyare finns.
Hämtningar som appen gör själv får ingen "från internet"-märkning, så Windows SmartScreen varnar inte.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import subprocess
import time
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

RELEASER = "https://api.github.com/repos/lolander/Skolan/releases?per_page=30"
SIDA = "https://github.com/lolander/Skolan/releases"
KOLLA_VAR = 6 * 3600  # sekunder mellan kollarna
TYST_MIN = 15 * 60  # automatisk installation bara när ingen har använt appen på 15 minuter
VAKT_SEK = 240  # så länge vakten väntar innan den kollar att nya versionen svarar
SETUP = re.compile(r"^Skolan-Larare-Setup-(\d+(?:\.\d+)*)\.exe$")
TILLATET = ("https://github.com/lolander/Skolan/", "https://objects.githubusercontent.com/", "https://release-assets.githubusercontent.com/")
_LOSKOPPLAD = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def _ver(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s or "")[:4])


class Uppdaterare:
    def __init__(self, mapp: Path, version: str, inst: dict, spara, port: int = 8770) -> None:
        self.mapp = mapp
        self._s = None
        self.version = version
        self.inst = inst  # klassens data: inst["uppdatering"] = "manuell" | "automatisk"
        self.spara = spara
        self.port = port
        self.senaste: dict | None = None
        self.forra: dict | None = None  # installationsfilen för versionen som körs nu (för att kunna gå tillbaka)
        self.kollad = 0.0
        self.fel = ""
        self.steg = ""  # "", "laddar", "installerar"
        self.senast_aktiv = time.time()
        self._uppgift: asyncio.Task | None = None
        self._efter_start()

    def _efter_start(self) -> None:
        """Har vi precis uppdaterats (eller gått tillbaka)? Visa det en gång."""
        till = self.inst.pop("uppdatering_till", None)
        if not till:
            return
        if till.get("version") == self.version:
            self.inst["uppdaterad"] = {"fran": till.get("fran"), "till": self.version, "tid": time.strftime("%Y-%m-%d %H:%M")}
        else:  # vakten gick tillbaka: hoppa över den versionen
            self.inst["hoppa_over"] = till.get("version")
            self.fel = (f"Version {till.get('version')} startade inte, så appen gick tillbaka till {self.version}. "
                        "Den versionen hoppas över tills en nyare finns.")
            _LOGGER.warning("Uppdateringen till %s misslyckades, tillbaka på %s", till.get("version"), self.version)
        self.spara()

    @property
    def session(self):
        from aiohttp import ClientSession
        if self._s is None or self._s.closed:
            self._s = ClientSession()
        return self._s

    # ---------- inställning ----------
    @property
    def it_lage(self) -> str | None:
        from .windows import installation, it_policy

        if installation() != "anvandare":  # Store eller IT (Program Files) sköter uppdateringarna
            return "av"
        return it_policy().get("uppdateringar")

    @property
    def lage(self) -> str:
        return self.it_lage or ("manuell" if self.inst.get("uppdatering") == "manuell" else "automatisk")

    def satt_lage(self, lage: str) -> None:
        if self.it_lage:
            raise ValueError("Skolans IT har låst inställningen för uppdateringar.")
        self.inst["uppdatering"] = "manuell" if lage == "manuell" else "automatisk"
        self.spara()

    def aktiv(self) -> None:
        """Någon använder appen just nu (läraren eller en elev som synkar)."""
        self.senast_aktiv = time.time()

    @property
    def ny(self) -> bool:
        return bool(self.senaste) and _ver(self.senaste["version"]) > _ver(self.version) and self.senaste["version"] != self.inst.get("hoppa_over")

    def kvittera(self) -> None:
        """Läraren har sett att appen är uppdaterad."""
        if self.inst.pop("uppdaterad", None):
            self.spara()

    def status(self) -> dict:
        from .windows import installation

        return {
            "version": self.version, "lage": self.lage, "ny": self.ny,
            "senaste": self.senaste["version"] if self.senaste else None,
            "sida": self.senaste["sida"] if self.senaste else SIDA,
            "kollad": int(self.kollad), "fel": self.fel, "steg": self.steg,
            "kan_installera": os.name == "nt" and self.lage != "av", "uppdaterad": self.inst.get("uppdaterad"), "it_last": bool(self.it_lage),
            "installation": installation(),
        }

    # ---------- kolla ----------
    async def kolla(self) -> None:
        try:
            async with self.session.get(RELEASER, headers={"Accept": "application/vnd.github+json"}, timeout=20) as r:
                if r.status != 200:
                    raise RuntimeError(f"GitHub svarade {r.status}")
                lista = await r.json()
            basta = forra = None
            for rel in lista:
                if rel.get("draft"):
                    continue
                namn = {a.get("name", ""): a for a in rel.get("assets", [])}
                for a in rel.get("assets", []):
                    m = SETUP.match(a.get("name", ""))
                    if not m:
                        continue
                    sha = namn.get(a["name"] + ".sha256")
                    x = {"version": m.group(1), "url": a["browser_download_url"], "storlek": a.get("size", 0), "namn": a["name"],
                         "sha": sha["browser_download_url"] if sha else None, "sida": rel.get("html_url") or SIDA}
                    if x["sha"] and (not basta or _ver(x["version"]) > _ver(basta["version"])):
                        basta = x  # bara versioner med fingeravtryck installeras automatiskt
                    if x["version"] == self.version:
                        forra = x
            self.senaste, self.forra = basta, forra
            if not self.fel.startswith("Version "):
                self.fel = ""
        except Exception as err:  # noqa: BLE001
            self.fel = "Kunde inte kolla efter uppdateringar just nu. Appen försöker igen senare, och allt annat fungerar som vanligt."
            _LOGGER.info("Kunde inte kolla efter uppdateringar: %s", err)
        self.kollad = time.time()

    # ---------- ladda ner ----------
    async def _hamta(self, x: dict, mapp: Path) -> Path:
        if not x["url"].startswith(TILLATET):
            raise RuntimeError("Okänd adress för uppdateringen.")
        fil = mapp / x["namn"]
        forvantat = None
        if x.get("sha"):
            async with self.session.get(x["sha"], timeout=30) as r:
                if r.status != 200:
                    raise RuntimeError(f"Kunde inte hämta fingeravtrycket ({r.status})")
                forvantat = (await r.text()).split()[0].strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", forvantat):
                raise RuntimeError("Fingeravtrycket är trasigt.")

        def summa(p: Path) -> str:
            h = hashlib.sha256()
            with p.open("rb") as f:
                for bit in iter(lambda: f.read(1 << 20), b""):
                    h.update(bit)
            return h.hexdigest()

        if fil.is_file() and forvantat and await asyncio.to_thread(summa, fil) == forvantat:
            return fil
        tmp = fil.with_suffix(".del")
        async with self.session.get(x["url"], timeout=600) as r:
            if r.status != 200:
                raise RuntimeError(f"Nedladdningen misslyckades ({r.status})")
            with tmp.open("wb") as ut:
                async for bit in r.content.iter_chunked(1 << 16):
                    ut.write(bit)
        if forvantat and await asyncio.to_thread(summa, tmp) != forvantat:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("Filen stämmer inte med sitt fingeravtryck. Den installeras inte.")
        tmp.replace(fil)
        return fil

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
        self.steg, self.fel = "laddar", ""
        try:
            mapp.mkdir(exist_ok=True)
            for gammal in mapp.glob("Skolan-Larare-Setup-*"):
                if gammal.name not in (s["namn"], (self.forra or {}).get("namn")):
                    gammal.unlink(missing_ok=True)
            fil = await self._hamta(s, mapp)
            tillbaka = None
            if self.forra:  # den version som körs nu, för att kunna gå tillbaka
                try:
                    tillbaka = await self._hamta(self.forra, mapp)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.info("Kunde inte hämta förra versionen (vakten kan inte gå tillbaka): %s", err)
            self.steg = "installerar"
            self.inst["uppdatering_till"] = {"version": s["version"], "fran": self.version}
            self.spara()
            if tillbaka:
                self._starta_vakt(s["version"], tillbaka)
            # Tyst installation per användare: ingen fråga från Windows. Installationen stänger appen och startar den igen.
            subprocess.Popen([str(fil), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], creationflags=_LOSKOPPLAD, close_fds=True)
            _LOGGER.info("Startade uppdatering till %s", s["version"])
            await asyncio.sleep(300)  # appen borde ha stängts av installationen
            self.inst.pop("uppdatering_till", None)
            self.spara()
            self.fel = "Installationen startade inte. Försök igen."
        except Exception as err:  # noqa: BLE001
            self.fel = str(err) if isinstance(err, (ValueError, RuntimeError)) else f"Uppdateringen misslyckades: {err}"
            _LOGGER.warning("Uppdatering: %s", err)
        finally:
            self.steg = ""

    def _starta_vakt(self, ny_version: str, tillbaka: Path) -> None:
        """Ett litet PowerShell-skript som efter några minuter kollar att nya versionen svarar, annars går tillbaka."""
        logg = self.mapp / "uppdatering" / "vakt.log"
        ps = f"""
Start-Sleep -Seconds {VAKT_SEK}
$ok = $false
for ($i = 0; $i -lt 6; $i++) {{
  try {{
    $l = Invoke-RestMethod -Uri 'http://127.0.0.1:{self.port}/api/lage' -TimeoutSec 10
    if ($l.version -eq '{ny_version}') {{ $ok = $true; break }}
  }} catch {{}}
  Start-Sleep -Seconds 20
}}
if ($ok) {{ "$(Get-Date) OK {ny_version}" | Out-File -Append -FilePath '{logg}'; exit 0 }}
"$(Get-Date) {ny_version} svarar inte, installerar {self.version} igen" | Out-File -Append -FilePath '{logg}'
$p = Start-Process -FilePath '{tillbaka}' -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -PassThru
$null = $p.WaitForExit(600000)
"""
        skript = self.mapp / "uppdatering" / "vakt.ps1"
        skript.write_text(ps, encoding="utf-8-sig")
        subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(skript)],
                         creationflags=_LOSKOPPLAD, close_fds=True)

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
            if self.lage == "av":  # skolans IT sköter uppdateringarna
                await asyncio.sleep(300)
                continue
            if time.time() - self.kollad >= KOLLA_VAR:
                await self.kolla()
            if self.lage == "automatisk" and self.ny and not self.steg and os.name == "nt" \
                    and time.time() - self.senast_aktiv >= TYST_MIN and not self._forsokt():
                await self.installera()
            await asyncio.sleep(300)

    def _forsokt(self) -> bool:
        """Automatiskt: försök högst en gång per version och dygn."""
        nyckel = f"{self.senaste['version']}|{time.strftime('%Y-%m-%d')}"
        if self.inst.get("uppdatering_forsok") == nyckel:
            return True
        self.inst["uppdatering_forsok"] = nyckel
        self.spara()
        return False
