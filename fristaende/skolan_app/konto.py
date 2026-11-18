"""Familjens personer, PIN-koder och inloggning (ersätter Home Assistants användare)."""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

from aiohttp import web

from .varden import Anvandare

COOKIE = "skolan_token"
MAX_FORSOK = 5  # felaktiga PIN-försök per person och 5 minuter
SPARR_SEK = 300
TOKEN_DAGAR = 180


def _hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def slug(namn: str, upptagna: set[str]) -> str:
    s = namn.lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "person"
    bas, n = s[:20], 2
    while s in upptagna:
        s = f"{bas}_{n}"
        n += 1
    return s


class Konto:
    def __init__(self, mapp: Path) -> None:
        self.mapp = mapp
        self.fil = mapp / "installning.json"
        self.tokenfil = mapp / "tokens.json"
        self.inst = self._las(self.fil, {"personer": []})
        self.tokens: dict[str, dict] = self._las(self.tokenfil, {})
        self._fel: dict[str, list[float]] = {}

    @staticmethod
    def _las(f: Path, std: dict) -> dict:
        try:
            return json.loads(f.read_text("utf-8")) if f.exists() else std
        except (OSError, ValueError):
            return std

    @staticmethod
    def _skriv(f: Path, d: dict) -> None:
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(f)

    def spara(self) -> None:
        self._skriv(self.fil, self.inst)

    # ---------- personer ----------
    @property
    def personer(self) -> list[dict]:
        return self.inst["personer"]

    def ar_installerad(self) -> bool:
        return any(p["roll"] == "foralder" for p in self.personer) and any(p["roll"] == "barn" for p in self.personer)

    def person(self, pid: str) -> dict | None:
        return next((p for p in self.personer if p["id"] == pid), None)

    def lagg_till(self, namn: str, roll: str, pin: str) -> dict:
        namn = re.sub(r"\s+", " ", str(namn or "")).strip()[:30]
        if not namn:
            raise ValueError("Skriv ett namn.")
        if roll not in ("barn", "foralder"):
            raise ValueError("Okänd roll.")
        self._kolla_pin(pin)
        salt = secrets.token_hex(16)
        p = {"id": slug(namn, {x["id"] for x in self.personer}), "namn": namn, "roll": roll, "salt": salt, "pin": _hash(pin, salt)}
        self.personer.append(p)
        self.spara()
        return p

    @staticmethod
    def _kolla_pin(pin: str) -> None:
        if not re.fullmatch(r"\d{4,8}", str(pin or "")):
            raise ValueError("PIN-koden ska vara 4–8 siffror.")

    def byt_pin(self, pid: str, pin: str) -> None:
        p = self.person(pid)
        if not p:
            raise ValueError("Hittar inte personen.")
        self._kolla_pin(pin)
        p["salt"] = secrets.token_hex(16)
        p["pin"] = _hash(pin, p["salt"])
        self.tokens = {t: x for t, x in self.tokens.items() if x["id"] != pid}  # logga ut överallt
        self._skriv(self.tokenfil, self.tokens)
        self.spara()

    def ta_bort(self, pid: str) -> None:
        p = self.person(pid)
        if not p:
            raise ValueError("Hittar inte personen.")
        if p["roll"] == "foralder" and sum(x["roll"] == "foralder" for x in self.personer) == 1:
            raise ValueError("Det måste finnas minst en förälder.")
        self.personer.remove(p)
        self.tokens = {t: x for t, x in self.tokens.items() if x["id"] != pid}
        self._skriv(self.tokenfil, self.tokens)
        self.spara()

    def publika(self) -> list[dict]:
        return [{"id": p["id"], "namn": p["namn"], "roll": p["roll"]} for p in self.personer]

    # ---------- inloggning ----------
    def logga_in(self, pid: str, pin: str) -> str:
        p = self.person(pid)
        nu = time.time()
        fel = [t for t in self._fel.get(pid, []) if nu - t < SPARR_SEK]
        self._fel[pid] = fel
        if len(fel) >= MAX_FORSOK:
            raise ValueError("För många fel. Vänta några minuter och försök igen.")
        if not p or not hmac.compare_digest(_hash(str(pin or ""), p["salt"]), p["pin"]):
            fel.append(nu)
            raise ValueError("Fel PIN-kod.")
        self._fel.pop(pid, None)
        return self._ny_token(pid)

    def _ny_token(self, pid: str) -> str:
        nu = time.time()
        token = secrets.token_urlsafe(32)
        self.tokens = {t: x for t, x in self.tokens.items() if x.get("tid", 0) > nu - TOKEN_DAGAR * 86400}
        self.tokens[token] = {"id": pid, "tid": nu}
        self._skriv(self.tokenfil, self.tokens)
        return token

    # Kopplingskod: en förälder visar en QR-kod som loggar in en telefon som en viss person (gäller 15 minuter, en gång).
    KOD_SEK = 15 * 60

    def kopplingskod(self, pid: str) -> str:
        if not self.person(pid):
            raise ValueError("Personen finns inte.")
        nu = time.time()
        self._koder = {k: v for k, v in getattr(self, "_koder", {}).items() if v[1] > nu}
        kod = secrets.token_urlsafe(18)
        self._koder[kod] = (pid, nu + self.KOD_SEK)
        return kod

    def logga_in_kod(self, kod: str) -> str:
        koder = getattr(self, "_koder", {})
        pid, giltig = koder.pop(kod, (None, 0))
        if not pid or time.time() > giltig or not self.person(pid):
            raise ValueError("Länken är för gammal eller redan använd. Be en förälder visa en ny QR-kod.")
        return self._ny_token(pid)

    def logga_ut(self, token: str) -> None:
        if self.tokens.pop(token, None):
            self._skriv(self.tokenfil, self.tokens)

    @staticmethod
    def token_fran(request: web.Request) -> str:
        h = request.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return h[7:].strip()
        return request.query.get("authSig") or request.cookies.get(COOKIE) or ""

    def anvandare(self, request: web.Request) -> Anvandare | None:
        token = self.token_fran(request)
        x = self.tokens.get(token) if token else None
        p = self.person(x["id"]) if x else None
        if not p:
            return None
        return Anvandare(p["id"], p["namn"], p["roll"] == "foralder")

    def skydda(self, fn, kraver_inloggning: bool = True):
        """Gör en Home Assistant-vy till en aiohttp-hanterare med inloggning."""

        @functools.wraps(fn)
        async def hanterare(request: web.Request) -> web.StreamResponse:
            if kraver_inloggning:
                u = self.anvandare(request)
                if not u:
                    raise web.HTTPUnauthorized
                request["hass_user"] = u
            return await fn(request, **request.match_info)

        return hanterare
