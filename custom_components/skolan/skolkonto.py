"""Verifiering med skolkonto (Microsoft eller Google).

Läraren loggar in med sitt skolkonto i Lärarrummet. Microsoft eller Google ger då ett signerat intyg (ID-token)
med namn, e-post och skolans organisation. Intyget är knutet till lärarens nyckel (nonce = hash av nyckeln),
så det går inte att använda för en annan lärarapp. Familjens Läxspelet kontrollerar signaturen själv mot
Microsofts och Googles publika nycklar – ingen server hos Läxspelet är inblandad.

Det här bevisar att skolan har gett personen ett konto (anställning), inte lärarlegitimation.
Privata konton (Outlook.com, Hotmail, Gmail) godtas inte.

Samma fil finns i custom_components/skolan/skolkonto.py och larare/skolan_larare/skolkonto.py. Ändra båda (de ska vara exakt lika). Inga Home Assistant-importer här.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time

# Läxspelets registreringar hos Microsoft (Entra, flera organisationer, publik klient) och Google (skrivbordsapp).
# Tomma tills apparna är registrerade: då visas inte verifieringen i Lärarrummet.
MICROSOFT_KLIENT = "ed3db50e-7a88-4dc3-8c0b-8f92e16ecf51"
GOOGLE_KLIENT = "643812673723-33m2dqh36du5mvtio6e2cdpkiafj6sin.apps.googleusercontent.com"
# Googles "hemlighet" för skrivbordsappar behövs bara i Lärarrummet vid inlösen. Den ligger inte i repot
# (GitHub/Google spärrar läckta hemligheter) utan i skolkonto_hemlighet.py, som bygget skapar från
# repo-hemligheten GOOGLE_HEMLIGHET. Familjens app behöver den inte: den kontrollerar bara intyg.
GOOGLE_HEMLIGHET = ""
try:
    from .skolkonto_hemlighet import GOOGLE_HEMLIGHET  # noqa: F811
except ImportError:
    pass

GILTIG_DAGAR = 100  # Lärarrummet ber läraren verifiera igen efter 90 dagar
NYCKLAR = {"microsoft": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
           "google": "https://www.googleapis.com/oauth2/v3/certs"}
INLOGGNING = {"microsoft": "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize",
              "google": "https://accounts.google.com/o/oauth2/v2/auth"}
INLOSEN = {"microsoft": "https://login.microsoftonline.com/organizations/oauth2/v2.0/token",
           "google": "https://oauth2.googleapis.com/token"}
NAMN = {"microsoft": "Microsoft", "google": "Google"}
# Microsofts organisation för privata konton (Outlook.com, Hotmail, Xbox …)
MS_PRIVAT = "9188040d-6c67-4c5b-b112-36a304b66dad"


def klient(lev: str) -> str:
    return {"microsoft": MICROSOFT_KLIENT, "google": GOOGLE_KLIENT}.get(lev, "")


def tillgangliga() -> list[str]:
    """Leverantörer läraren kan verifiera sig med (Google kräver hemligheten vid inlösen)."""
    return [x for x in ("microsoft", "google") if klient(x) and (x != "google" or GOOGLE_HEMLIGHET)]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _ub64(x: str) -> bytes:
    return base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))


def nonce_for(pub: str) -> str:
    """Knyter intyget till lärarens nyckel."""
    return _b64(hashlib.sha256(("lararrummet:" + str(pub)).encode()).digest())


def _delar(token: str) -> tuple[dict, dict, bytes, bytes]:
    if not isinstance(token, str) or len(token) > 8000 or token.count(".") != 2:
        raise ValueError("Intyget har fel format.")
    h, p, s = token.split(".")
    try:
        return json.loads(_ub64(h)), json.loads(_ub64(p)), f"{h}.{p}".encode(), _ub64(s)
    except (ValueError, TypeError) as err:
        raise ValueError("Intyget har fel format.") from err


def leverantor(token: str) -> str | None:
    """Vilken tjänst intyget säger sig komma från (inte kontrollerat än) – för att veta vilka nycklar som behövs."""
    try:
        iss = str(_delar(token)[1].get("iss") or "")
    except ValueError:
        return None
    if iss in ("accounts.google.com", "https://accounts.google.com"):
        return "google"
    if re.fullmatch(r"https://login\.microsoftonline\.com/[0-9a-f\-]{36}/v2\.0", iss):
        return "microsoft"
    return None


def nyckel_id(token: str) -> str:
    try:
        return str(_delar(token)[0].get("kid") or "")
    except ValueError:
        return ""


def _rsa_ok(jwk: dict, data: bytes, sig: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

    try:
        n = int.from_bytes(_ub64(jwk["n"]), "big")
        e = int.from_bytes(_ub64(jwk["e"]), "big")
        RSAPublicNumbers(e, n).public_key().verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False


def kontrollera(token: str, nycklar: dict, pub: str, nu: float | None = None) -> dict:
    """Kontrollera ett intyg. nycklar = JWKS från NYCKLAR[lev]. Returnerar {lev, namn, epost, doman, org, tid}.
    Kastar ValueError med en förklaring på svenska om något inte stämmer."""
    nu = time.time() if nu is None else nu
    lev = leverantor(token)
    if not lev or not klient(lev):
        raise ValueError("Intyget kommer inte från Microsoft eller Google.")
    head, p, data, sig = _delar(token)
    if head.get("alg") != "RS256":
        raise ValueError("Intyget har fel signaturtyp.")
    jwk = next((k for k in (nycklar or {}).get("keys", []) if isinstance(k, dict) and k.get("kid") == head.get("kid")), None)
    if not jwk:
        raise ValueError("Intygets nyckel finns inte längre hos " + NAMN[lev] + ". Läraren behöver verifiera sig igen.")
    if not _rsa_ok(jwk, data, sig):
        raise ValueError("Intygets signatur stämmer inte.")
    if p.get("aud") != klient(lev):
        raise ValueError("Intyget är inte utfärdat till Lärarrummet.")
    if p.get("nonce") != nonce_for(pub):
        raise ValueError("Intyget hör till en annan lärarapp.")
    try:
        iat = float(p.get("iat"))
    except (TypeError, ValueError) as err:
        raise ValueError("Intyget saknar datum.") from err
    if iat > nu + 600 or nu - iat > GILTIG_DAGAR * 86400:
        raise ValueError("Intyget är för gammalt. Läraren behöver verifiera sig igen.")
    namn = str(p.get("name") or "")[:80]
    if lev == "microsoft":
        tid = str(p.get("tid") or "")
        if not re.fullmatch(r"[0-9a-f\-]{36}", tid) or p.get("iss") != f"https://login.microsoftonline.com/{tid}/v2.0":
            raise ValueError("Intyget har fel utfärdare.")
        if tid == MS_PRIVAT:
            raise ValueError("Privata Microsoft-konton godtas inte. Använd skolkontot.")
        epost = str(p.get("email") or p.get("preferred_username") or "")[:120]
        org = tid
    else:
        if not p.get("email_verified"):
            raise ValueError("E-postadressen är inte bekräftad hos Google.")
        org = str(p.get("hd") or "")
        if not org:
            raise ValueError("Privata Google-konton godtas inte. Använd skolkontot (Google Workspace).")
        epost = str(p.get("email") or "")[:120]
    # Google: Workspace-domänen (hd). Microsoft: domänen i kontots e-post/användarnamn.
    doman = org.lower() if lev == "google" else (epost.rsplit("@", 1)[-1].lower() if "@" in epost else "")
    return {"lev": lev, "namn": namn, "epost": epost, "doman": doman[:80], "org": org[:80], "tid": int(iat)}


def publik(k: dict | None, nu: float | None = None) -> dict | None:
    """Det som visas för föräldern (och läraren)."""
    if not k:
        return None
    nu = time.time() if nu is None else nu
    giltig = nu - float(k.get("tid") or 0) <= GILTIG_DAGAR * 86400
    return {"lev": k.get("lev"), "lev_namn": NAMN.get(k.get("lev"), ""), "namn": k.get("namn"), "epost": k.get("epost"),
            "doman": k.get("doman"), "tid": k.get("tid"), "giltig": giltig}
