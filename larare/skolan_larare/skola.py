"""Skolan: lärarnas appar i ett gemensamt "kluster" på skolans nätverk. Ingen server och inget moln.

- En lärare skapar skolan och får en kod (giltig 7 dagar). Kollegor skriver koden i sin app.
- Apparna hittar varandra på nätverket (UDP-sändning på samma port som appen). Fungerar inte det
  (vissa skolnät stoppar sändningar) skriver läraren in en kollegas adress, t.ex. 10.0.4.17:8770.
- Medlemmarna synkar var 10:e minut, signerat med skolans hemliga nyckel (HMAC-SHA256).
- Det som delas: vem som är med (namn, ämne, roll, klass) och provkalendern (titel, ämne, datum, klass).
- Elevdata delas bara med elevens mentor: ämneslärarens provresultat för just den eleven, så att mentorn
  får hela bilden. Eleven känns igen på elev_id (samma för alla lärare, från familjens Läxspelet).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import socket
import time

from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

SYNK_VAR = 600  # sekunder mellan synkarna med kollegorna
FYR_VAR = 60  # sekunder mellan "här är jag"-sändningarna på nätverket
KOD_GILTIG = 7 * 24 * 3600
MAX_SKEV = 900  # godta signerade meddelanden högst 15 minuter gamla
PROTO = b"LXS1"


def _t(x, n: int) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def ny_kod() -> str:
    alfabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    k = "".join(secrets.choice(alfabet) for _ in range(8))
    return f"{k[:4]}-{k[4:]}"


def _kodnyckel(kod: str) -> str:
    return hashlib.sha256(("kod:" + re.sub(r"[^A-Z0-9]", "", kod.upper())).encode()).hexdigest()[:16]


def signera(hemlighet: str, kropp: bytes) -> str:
    return hmac.new(hemlighet.encode(), kropp, hashlib.sha256).hexdigest()


class Skola:
    def __init__(self, klass) -> None:
        self.k = klass  # Klass (server.py): d, spara(), logga(), port
        self.d.setdefault("skola", None)
        self._fel_forsok: dict[str, list[float]] = {}
        self._uppgift: asyncio.Task | None = None
        self._udp = None

    @property
    def d(self) -> dict:
        return self.k.d

    @property
    def s(self) -> dict | None:
        return self.d.get("skola")

    @property
    def lid(self) -> str:
        return self.d["larar_id"]

    def min_info(self) -> dict:
        from .server import lan_ip
        return {"namn": self.d.get("larare") or "Läraren", "amne": self.d.get("amne", ""), "roll": self.d.get("roll", "mentor"),
                "klass": self.d.get("klass", ""), "adress": f"{lan_ip()}:{self.k.port}"}

    # ---------- skapa, gå med, lämna ----------
    def skapa(self, namn: str) -> dict:
        if self.s:
            raise ValueError("Du är redan med i en skola.")
        namn = _t(namn, 60)
        if not namn:
            raise ValueError("Skriv skolans namn.")
        self.d["skola"] = {"id": secrets.token_urlsafe(9), "namn": namn, "hemlighet": secrets.token_urlsafe(32),
                           "kod": ny_kod(), "kod_tid": time.time(), "medlemmar": {}, "prov": {}, "resultat": {}}
        self.k.logga("skola", f"Skolan {namn} skapades.")
        self.k.spara()
        return self.s

    def ny_kod(self) -> str:
        if not self.s:
            raise ValueError("Du är inte med i någon skola.")
        self.s["kod"], self.s["kod_tid"] = ny_kod(), time.time()
        self.k.spara()
        return self.s["kod"]

    def lamna(self) -> None:
        if self.s:
            self.k.logga("skola", f"Lämnade skolan {self.s['namn']}.")
        self.d["skola"] = None
        self.k.spara()

    def kod_ok(self, kod: str) -> bool:
        s = self.s
        return bool(s and s.get("kod") and time.time() - s.get("kod_tid", 0) < KOD_GILTIG
                    and hmac.compare_digest(_kodnyckel(s["kod"]), _kodnyckel(kod)))

    def ta_emot_medlem(self, ip: str, body: dict) -> dict:
        """En kollega vill gå med (POST /api/skola/ga_med). Kräver rätt kod. Max 10 fel per timme och adress."""
        f = [t for t in self._fel_forsok.get(ip, []) if time.time() - t < 3600]
        if len(f) >= 10:
            raise PermissionError("För många fel försök. Vänta en stund.")
        if not self.kod_ok(str(body.get("kod") or "")):
            self._fel_forsok[ip] = f + [time.time()]
            raise PermissionError("Fel kod, eller så har koden gått ut. Be kollegan om en ny.")
        lid = _t(body.get("larar_id"), 40)
        if not lid:
            raise ValueError("Saknar lärare.")
        self._spara_medlem(lid, body.get("info") or {}, ip)
        self.k.logga("skola", f"{_t((body.get('info') or {}).get('namn'), 60)} gick med i skolan.")
        self.k.spara()
        return {"id": self.s["id"], "namn": self.s["namn"], "hemlighet": self.s["hemlighet"],
                "medlemmar": {**self.s["medlemmar"], self.lid: {**self.min_info(), "sedd": time.strftime("%Y-%m-%d %H:%M")}}}

    async def ga_med(self, session: ClientSession, kod: str, adress: str | None = None) -> None:
        """Gå med i en kollegas skola: hitta kollegan på nätverket (eller via adress) och skicka koden."""
        if self.s:
            raise ValueError("Du är redan med i en skola. Lämna den först.")
        kod = _t(kod, 20).upper()
        if not re.fullmatch(r"[A-Z0-9]{4}-?[A-Z0-9]{4}", kod):
            raise ValueError("Koden ser ut så här: ABCD-EF23.")
        adresser = [adress] if adress else await self._sok_kod(kod)
        if not adresser:
            raise ValueError("Hittade ingen kollega med den koden på nätverket. Skriv in kollegans adress (den står på kollegans Översikt).")
        senaste_fel = ""
        for a in adresser:
            if not re.fullmatch(r"[\w.\-]+:\d{2,5}", a or ""):
                continue
            try:
                async with session.post(f"http://{a}/api/skola/ga_med", json={"kod": kod, "larar_id": self.lid, "info": self.min_info()},
                                        timeout=ClientTimeout(total=15)) as r:
                    j = await r.json()
                    if r.status != 200:
                        senaste_fel = j.get("fel") or f"Kollegans app svarade {r.status}."
                        continue
            except Exception as err:  # noqa: BLE001
                senaste_fel = f"Kunde inte nå {a}: {err}"
                continue
            self.d["skola"] = {"id": _t(j["id"], 40), "namn": _t(j["namn"], 60), "hemlighet": str(j["hemlighet"])[:100], "kod": "", "kod_tid": 0,
                               "medlemmar": {}, "prov": {}, "resultat": {}}
            for mlid, info in (j.get("medlemmar") or {}).items():
                if mlid != self.lid:
                    self._spara_medlem(_t(mlid, 40), info, None)
            self.k.logga("skola", f"Gick med i skolan {self.s['namn']}.")
            self.k.spara()
            asyncio.get_running_loop().create_task(self.synka_alla(session))
            return
        raise ValueError(senaste_fel or "Kunde inte gå med.")

    def _spara_medlem(self, lid: str, info: dict, ip: str | None) -> None:
        if lid == self.lid:
            return
        m = self.s["medlemmar"].setdefault(lid, {})
        adress = _t(info.get("adress"), 60)
        if ip and adress:  # lita på avsändarens ip, porten från meddelandet
            adress = f"{ip}:{adress.rsplit(':', 1)[-1]}"
        m.update({"namn": _t(info.get("namn"), 60) or m.get("namn") or "?", "amne": _t(info.get("amne"), 60), "roll": "amne" if info.get("roll") == "amne" else "mentor",
                  "klass": _t(info.get("klass"), 40), "sedd": time.strftime("%Y-%m-%d %H:%M")})
        if re.fullmatch(r"[\w.\-]+:\d{2,5}", adress or ""):
            m["adress"] = adress

    # ---------- det som delas ----------
    def mina_prov(self) -> list[dict]:
        return [{"id": m["id"], "titel": _t(m.get("titel"), 80), "amne": _t(m.get("amne"), 40), "datum": _t(m.get("datum"), 10), "klass": self.d.get("klass", "")}
                for m in self.d.get("material", []) if m.get("typ") == "prov" and m.get("datum")][-60:]

    def till_mentor(self, mentor_lid: str) -> dict:
        """Mina provresultat för de elever där mentor_lid är mentor (bara dem)."""
        ut: dict[str, list] = {}
        for e in self.d.get("elever", []):
            if not e.get("elev_id") or not any(x.get("id") == mentor_lid and x.get("roll") == "mentor" for x in e.get("lararna") or []):
                continue
            rader = []
            for m in self.d.get("material", []):
                r = (m.get("resultat") or {}).get(e["id"]) if m.get("typ") == "prov" else None
                if r:
                    rader.append({"titel": _t(m.get("titel"), 80), "amne": _t(m.get("amne"), 40), "datum": _t(m.get("datum"), 10), "max": m.get("max"),
                                  **{k: r[k] for k in ("poang", "betyg", "kommentar") if k in r}, "larare": self.d.get("larare") or ""})
            if rader:
                ut[e["elev_id"]] = rader[-30:]
        return ut

    def _paket(self, till: str | None) -> dict:
        return {"v": 1, "skola": self.s["id"], "fran": self.lid, "tid": time.time(), "info": self.min_info(), "prov": self.mina_prov(),
                "medlemmar": {k: {x: v.get(x) for x in ("namn", "amne", "roll", "klass", "adress")} for k, v in self.s["medlemmar"].items()},
                "till_mentor": self.till_mentor(till) if till else {}}

    def _ta_emot_paket(self, p: dict, ip: str | None) -> None:
        lid = _t(p.get("fran"), 40)
        if not lid or lid == self.lid:
            return
        self._spara_medlem(lid, p.get("info") or {}, ip)
        self.s["prov"][lid] = [{k: _t(x.get(k), 80) for k in ("id", "titel", "amne", "datum", "klass")} for x in (p.get("prov") or [])[:60] if isinstance(x, dict)]
        tm = p.get("till_mentor") or {}
        self.s["resultat"][lid] = {_t(eid, 30): [{k: (x.get(k) if k in ("poang", "max") and isinstance(x.get(k), (int, float)) else _t(x.get(k), 200))
                                                  for k in ("titel", "amne", "datum", "max", "poang", "betyg", "kommentar", "larare") if k in x}
                                                 for x in rader[:30] if isinstance(x, dict)]
                                   for eid, rader in list(tm.items())[:200] if isinstance(rader, list)}
        for mlid, info in (p.get("medlemmar") or {}).items():  # så hittar alla varandra
            if mlid not in self.s["medlemmar"] and mlid != self.lid and isinstance(info, dict):
                self._spara_medlem(_t(mlid, 40), info, None)

    def verifiera(self, kropp: bytes, signatur: str) -> dict:
        if not self.s:
            raise PermissionError("Inte med i någon skola.")
        if not hmac.compare_digest(signera(self.s["hemlighet"], kropp), signatur or ""):
            raise PermissionError("Fel signatur.")
        p = json.loads(kropp)
        if p.get("skola") != self.s["id"] or abs(time.time() - float(p.get("tid") or 0)) > MAX_SKEV:
            raise PermissionError("Fel skola eller för gammalt.")
        return p

    def ta_emot_synk(self, kropp: bytes, signatur: str, ip: str) -> tuple[bytes, str]:
        """En kollega synkar med oss (POST /api/skola/synk). Svarar med vårt paket, signerat."""
        p = self.verifiera(kropp, signatur)
        self._ta_emot_paket(p, ip)
        self.k.spara()
        svar = json.dumps(self._paket(_t(p.get("fran"), 40)), ensure_ascii=False).encode()
        return svar, signera(self.s["hemlighet"], svar)

    async def synka_alla(self, session: ClientSession) -> None:
        if not self.s:
            return
        for lid, m in list(self.s["medlemmar"].items()):
            if not m.get("adress"):
                continue
            kropp = json.dumps(self._paket(lid), ensure_ascii=False).encode()
            try:
                async with session.post(f"http://{m['adress']}/api/skola/synk", data=kropp, timeout=ClientTimeout(total=15),
                                        headers={"Content-Type": "application/json", "X-Laxspelet-Signatur": signera(self.s["hemlighet"], kropp)}) as r:
                    if r.status != 200:
                        m["fel"] = f"svarade {r.status}"
                        continue
                    svar = await r.read()
                    p = self.verifiera(svar, r.headers.get("X-Laxspelet-Signatur", ""))
                    self._ta_emot_paket(p, None)
                    m["fel"] = ""
            except Exception as err:  # noqa: BLE001
                m["fel"] = "nås inte just nu"
                _LOGGER.info("Skolan: kunde inte synka med %s: %s", m.get("namn"), err)
        self.k.spara()

    # ---------- det läraren ser ----------
    def publik(self) -> dict | None:
        s = self.s
        if not s:
            return None
        return {"id": s["id"], "namn": s["namn"], "kod": s.get("kod") if s.get("kod") and time.time() - s.get("kod_tid", 0) < KOD_GILTIG else "",
                "medlemmar": [{"id": k, **{x: v.get(x) for x in ("namn", "amne", "roll", "klass", "sedd", "fel", "adress")}}
                              for k, v in sorted(s["medlemmar"].items(), key=lambda kv: kv[1].get("namn", ""))]}

    def provkalender(self) -> list[dict]:
        if not self.s:
            return []
        ut = [{**x, "larare": self.d.get("larare") or "Du", "egen": True} for x in self.mina_prov()]
        for lid, lista in self.s["prov"].items():
            namn = (self.s["medlemmar"].get(lid) or {}).get("namn") or "?"
            ut += [{**x, "larare": namn, "egen": False} for x in lista]
        return sorted(ut, key=lambda x: x.get("datum", ""))

    def fran_kollegor(self) -> dict:
        """Provresultat från ämneslärarna, per elev_id (bara för elever där jag är mentor)."""
        if not self.s:
            return {}
        ut: dict[str, list] = {}
        for lista in self.s["resultat"].values():
            for eid, rader in lista.items():
                ut.setdefault(eid, []).extend(rader)
        return ut

    # ---------- hitta varandra på nätverket ----------
    async def _sok_kod(self, kod: str) -> list[str]:
        """Fråga på nätverket vem som har den här koden. Svar: kollegornas adresser."""
        loop = asyncio.get_running_loop()
        svar: list[str] = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("", 0))
        try:
            fraga = PROTO + b"? " + _kodnyckel(kod).encode()
            for _ in range(3):
                for mal in ("255.255.255.255", "<broadcast>"):
                    try:
                        sock.sendto(fraga, (mal, self.k.port))
                    except OSError:
                        pass
                slut = time.time() + 1.5
                while time.time() < slut:
                    try:
                        data, (ip, _p) = await asyncio.wait_for(loop.sock_recvfrom(sock, 512), timeout=max(0.05, slut - time.time()))
                    except (asyncio.TimeoutError, OSError):
                        break
                    m = re.fullmatch(rb"LXS1! (\d{2,5})", data.strip())
                    if m and f"{ip}:{m.group(1).decode()}" not in svar:
                        svar.append(f"{ip}:{m.group(1).decode()}")
                if svar:
                    break
        finally:
            sock.close()
        return svar

    def _udp_in(self, data: bytes, addr: tuple) -> None:
        ip = addr[0]
        s = self.s
        if not s:
            return
        m = re.fullmatch(rb"LXS1\? ([0-9a-f]{16})", data.strip())
        if m and s.get("kod") and time.time() - s.get("kod_tid", 0) < KOD_GILTIG and hmac.compare_digest(m.group(1).decode(), _kodnyckel(s["kod"])):
            if self._udp:
                self._udp.sendto(PROTO + b"! " + str(self.k.port).encode(), addr)  # svaret till frågans port
            return
        m = re.fullmatch(rb"LXS1 ([\w\-]{6,40}) ([\w\-]{4,40}) (\d{2,5})", data.strip())
        if m and m.group(1).decode() == s["id"] and m.group(2).decode() != self.lid:
            lid = m.group(2).decode()
            if lid in s["medlemmar"]:  # en känd kollega har (kanske) bytt adress
                s["medlemmar"][lid]["adress"] = f"{ip}:{m.group(3).decode()}"

    async def starta(self, session_fn) -> None:
        loop = asyncio.get_running_loop()
        skola = self

        class Udp(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):  # noqa: N802
                try:
                    skola._udp_in(data, addr)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("UDP: %s", err)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", self.k.port))
            self._udp, _ = await loop.create_datagram_endpoint(Udp, sock=sock)
        except OSError as err:
            _LOGGER.warning("Skolan: kunde inte lyssna på nätverket (UDP %s): %s", self.k.port, err)
        self._uppgift = loop.create_task(self._slinga(session_fn))

    async def _slinga(self, session_fn) -> None:
        senast_synk = 0.0
        while True:
            try:
                if self.s:
                    if self._udp:
                        fyr = f"LXS1 {self.s['id']} {self.lid} {self.k.port}".encode()
                        for mal in ("255.255.255.255",):
                            try:
                                self._udp.sendto(fyr, (mal, self.k.port))
                            except OSError:
                                pass
                    if time.time() - senast_synk >= SYNK_VAR:
                        senast_synk = time.time()
                        await self.synka_alla(await session_fn())
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Skolan: %s", err)
            await asyncio.sleep(FYR_VAR)
