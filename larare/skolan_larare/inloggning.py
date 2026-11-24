"""Inloggning med skolkontot (Microsoft eller Google) för att verifiera läraren.

Standardflödet för skrivbordsappar: webbläsaren öppnar skolans vanliga inloggning och skickar tillbaka en kod till
Lärarrummet på den här datorn (http://localhost/skolkonto/svar). Koden löses in med PKCE, utan hemlig nyckel.
Vi ber bara om namn och e-post (openid, profile, email) – ingen åtkomst till e-post, filer eller något annat.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout

from . import skolkonto

SVAR_VAG = "/skolkonto/svar"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def svar_adress(lev: str, port: int) -> str:
    # Microsoft godtar valfri port för http://localhost; Google vill ha 127.0.0.1 för skrivbordsappar.
    return f"http://{'localhost' if lev == 'microsoft' else '127.0.0.1'}:{port}{SVAR_VAG}"


class Inloggning:
    def __init__(self) -> None:
        self._vantar: dict[str, dict] = {}

    def starta(self, lev: str, port: int, pub: str, atgard: dict | None = None, epost: str = "") -> str:
        """atgard: en åtgärd som ska bekräftas med en ny inloggning (t.ex. tillsynsloggen). Intyget knyts då till just den
        åtgärden (nonce = hash av nyckeln + åtgärden) och inloggningen krävs på nytt, med skolans tvåstegsverifiering."""
        if lev not in skolkonto.tillgangliga():
            raise ValueError("Den här inloggningen är inte tillgänglig än.")
        nu = time.time()
        for k in [k for k, v in self._vantar.items() if nu - v["tid"] > 900]:
            self._vantar.pop(k)
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        bunden = pub + "|" + atgard["bind"] if atgard else pub
        self._vantar[state] = {"lev": lev, "verifier": verifier, "tid": nu, "pub": bunden, "atgard": atgard}
        param = {"client_id": skolkonto.klient(lev), "response_type": "code", "redirect_uri": svar_adress(lev, port),
                 "scope": "openid profile email", "state": state, "nonce": skolkonto.nonce_for(bunden),
                 "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
                 "prompt": "select_account"}
        if lev == "google":
            param["hd"] = "*"  # visa bara skol- och organisationskonton i kontoväljaren
        if atgard:
            param["max_age"] = "0"  # logga in på nytt, även om webbläsaren redan är inloggad
            if lev == "microsoft":
                param["prompt"] = "login"
            if epost:
                param["login_hint"] = epost
        return skolkonto.INLOGGNING[lev] + "?" + urlencode(param)

    async def avsluta(self, session: ClientSession, fraga: dict, port: int) -> dict:
        """Lös in koden och kontrollera intyget. Returnerar {"token": …, **kontrollerat}."""
        if fraga.get("error"):
            raise ValueError(_fel_text(str(fraga.get("error")), str(fraga.get("error_description") or "")))
        v = self._vantar.pop(str(fraga.get("state") or ""), None)
        if not v or time.time() - v["tid"] > 900:
            raise ValueError("Inloggningen tog för lång tid eller startades inte här. Försök igen.")
        lev = v["lev"]
        data = {"client_id": skolkonto.klient(lev), "grant_type": "authorization_code", "code": str(fraga.get("code") or ""),
                "redirect_uri": svar_adress(lev, port), "code_verifier": v["verifier"]}
        if lev == "google":
            data["client_secret"] = skolkonto.GOOGLE_HEMLIGHET
        async with session.post(skolkonto.INLOSEN[lev], data=data, timeout=ClientTimeout(total=30)) as r:
            svar = await r.json(content_type=None)
        if not isinstance(svar, dict) or not svar.get("id_token"):
            raise ValueError(_fel_text(str((svar or {}).get("error") or "okänt"), str((svar or {}).get("error_description") or "")))
        token = svar["id_token"]
        async with session.get(skolkonto.NYCKLAR[lev], timeout=ClientTimeout(total=30)) as r:
            jwks = await r.json(content_type=None)
        return {"token": token, "atgard": v.get("atgard"), **skolkonto.kontrollera(token, jwks, v["pub"])}


def _fel_text(kod: str, text: str) -> str:
    if kod == "access_denied" or "AADSTS65001" in text:
        return "Inloggningen avbröts, eller så behöver skolans IT godkänna Lärarrummet först (se informationen till IT)."
    if "AADSTS90072" in text or "AADSTS50020" in text:
        return "Kontot hör inte till en skola eller organisation. Använd ditt skolkonto."
    if "admin_policy_enforced" in kod or "org_internal" in text:
        return "Skolans Google-administratör behöver släppa igenom Lärarrummet först (se informationen till IT)."
    return f"Inloggningen misslyckades ({kod}). {text[:200]}".strip()
