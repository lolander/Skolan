"""Behörigheter: vad en lärare får göra med uppgifter om elever, beslutat av skolans rektor.

Tre nivåer (se NIVAER). Utan beslut från en rektor gäller nivå 0, alltså inga personuppgifter om elever.
En lärare i skolan är rektor. Rektorn bestämmer vad varje lärare får och signerar beslutet med en egen nyckel
(Ed25519), så att ingen annan lärare kan ändra det. Varje ändring sparas i en beslutslogg som kan laddas ner.

Här finns också krypteringen: synken mellan kollegor (AES-GCM med skolans nyckel) och klass.json på datorn
(Windows DPAPI, nyckeln hör till lärarens Windows-konto).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time

_LOGGER = logging.getLogger(__name__)

NIVAER = {
    0: ("Nivå 0", "Inga personuppgifter", "Veckobrev, studiematerial, provdatum, klasslag och klassens insikt (bara summor, minst 5 familjer). Inga elevnamn sparas."),
    1: ("Nivå 1", "Elevnamn", "Som nivå 0, och elevernas namn, grupper och scheman."),
    2: ("Nivå 2", "Uppgifter om enskilda elever", "Som nivå 1, och rapporter, statistik, studieteknik, lappar, samtalsunderlag, provresultat, anteckningar och delning med mentorn."),
}
# rättighet: (nivå, beskrivning)
RATTIGHETER = {
    "veckobrev": (0, "📬 Veckobrev"),
    "material": (0, "📎 Studiematerial och schema till klassen"),
    "riktlinjer": (0, "📝 Riktlinjer till elevernas AI-hjälplärare"),
    "klasslag": (0, "🏫 Klasslag (bara klassens summa)"),
    "insikt": (0, "🔎 Klassens insikt (summor, minst 5 familjer)"),
    "meddelanden": (0, "💬 Meddelanden mellan lärare"),
    "namn": (1, "👤 Elevernas namn"),
    "grupper": (1, "👥 Grupper och gruppuppgifter"),
    "schema": (1, "🗓️ Elevernas scheman"),
    "rapport": (2, "📊 Veckorapporter om enskilda elever"),
    "mejl": (2, "📧 Rapporter via e-post"),
    "statistik": (2, "📈 Statistik om enskilda elever"),
    "studieteknik": (2, "🧠 Studieteknik om enskilda elever"),
    "lapp": (2, "✉️ Lappar från föräldrar"),
    "samtal": (2, "🗣️ Underlag till utvecklingssamtal"),
    "prov": (2, "📝 Provresultat per elev"),
    "anteckningar": (2, "🗒️ Anteckningar om elever"),
    "mentor": (2, "🤝 Dela provresultat och anteckningar med elevens mentor"),
}
INSIKT_MIN = 5  # klassens insikt visas först när minst så här många familjer är med


def niva_ratt(niva: int) -> list[str]:
    return [k for k, (n, _) in RATTIGHETER.items() if n <= niva]


def niva_for(ratt: list[str]) -> int:
    """Den högsta nivån bland rättigheterna (för att visa en sammanfattning)."""
    return max([RATTIGHETER[k][0] for k in ratt if k in RATTIGHETER] or [0])


def rensa_ratt(x) -> list[str]:
    return [k for k in dict.fromkeys(x or []) if k in RATTIGHETER]


# ---------- nycklar och signaturer (Ed25519) ----------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _ub64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def ny_nyckel() -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    k = Ed25519PrivateKey.generate()
    return _b64(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))


def publik_nyckel(priv: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    k = Ed25519PrivateKey.from_private_bytes(_ub64(priv))
    return _b64(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def _kanon(p: dict) -> bytes:
    return json.dumps({k: v for k, v in p.items() if k != "sig"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def signera_policy(p: dict, priv: str) -> dict:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    p = {k: v for k, v in p.items() if k != "sig"}
    p["sig"] = _b64(Ed25519PrivateKey.from_private_bytes(_ub64(priv)).sign(_kanon(p)))
    return p


def _sig_ok(p: dict, pub: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(_ub64(pub)).verify(_ub64(str(p.get("sig") or "")), _kanon(p))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def godta_policy(nu: dict | None, ny: dict, skola_id: str) -> bool:
    """Ska vi byta till den nya policyn? Den måste vara nyare och signerad av den rektor vi redan litar på.

    Har skolan ingen policy än godtas den första giltiga (rektorn signerar sin egen utnämning)."""
    if not isinstance(ny, dict) or ny.get("skola") != skola_id or not isinstance(ny.get("ver"), int):
        return False
    if nu:
        if ny["ver"] <= nu.get("ver", 0):
            return False
        return _sig_ok(ny, nu["rektor_pub"])
    return ny["ver"] == 1 and _sig_ok(ny, str(ny.get("rektor_pub") or ""))


# ---------- intyg till familjerna (från 0.12.0) ----------
# Familjens Läxspelet litar inte på det lärarappen säger om sig själv. Den kräver:
# - ett INTYG från rektorn: vem läraren är (id + publik nyckel), behörigheterna och vilka klasser läraren är mentor för,
# - för en ämneslärare ett GODKÄNNANDE från elevens mentor: ämnen, klass och vilka elever (alla eller några),
# - att varje synk är signerad med lärarens nyckel.
# Föräldern godkänner skolan och rektorn en gång. Byter skolan rektor följer en signerad KEDJA med (gammal → ny),
# och föräldern godkänner den nya rektorn. Intyg och godkännanden gäller GILTIG sekunder och förnyas automatiskt.
GILTIG = 45 * 24 * 3600
FORNYA = 7 * 24 * 3600


def signera(d: dict, priv: str) -> dict:
    return signera_policy(d, priv)


def sig_ok(d: dict, pub: str) -> bool:
    return isinstance(d, dict) and _sig_ok(d, pub)


def signera_bytes(priv: str, data: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    return _b64(Ed25519PrivateKey.from_private_bytes(_ub64(priv)).sign(data))


def intyg(policy: dict, skola_namn: str, lid: str, namn: str, pub: str, priv: str) -> dict:
    """Rektorns intyg för en lärare (priv = rektorns nyckel)."""
    return signera({"typ": "intyg", "skola": policy["skola"], "skola_namn": skola_namn, "rektor_namn": policy.get("rektor_namn") or "",
                    "rektor_pub": policy["rektor_pub"], "lid": lid, "namn": namn, "pub": pub,
                    "ratt": rensa_ratt(policy.get("larare", {}).get(lid, policy.get("standard"))),
                    "mentor": list((policy.get("mentorer") or {}).get(lid) or []), "tid": round(time.time(), 3)}, priv)


def godkannande(skola_id: str, klass: str, mentor_lid: str, lid: str, pub: str, namn: str, amnen: list[str], elever: list[str] | None, priv: str) -> dict:
    """Mentorns godkännande av en ämneslärare (priv = mentorns nyckel). elever = None betyder hela klassen."""
    return signera({"typ": "amneslarare", "skola": skola_id, "klass": klass, "mentor": mentor_lid, "lid": lid, "pub": pub, "namn": namn,
                    "amnen": amnen, "elever": elever, "tid": round(time.time(), 3)}, priv)


def kedjelank(skola_id: str, fran_pub: str, till_pub: str, till_namn: str, priv: str) -> dict:
    """Rektorn lämnar över: signerat av den gamla rektorn."""
    return signera({"typ": "rektor", "skola": skola_id, "fran": fran_pub, "till": till_pub, "namn": till_namn, "tid": round(time.time(), 3)}, priv)


def ny_policy(skola_id: str, rektor_lid: str, rektor_namn: str, rektor_pub: str, priv: str) -> dict:
    p = {"skola": skola_id, "ver": 1, "rektor": rektor_lid, "rektor_namn": rektor_namn, "rektor_pub": rektor_pub,
         "standard": niva_ratt(0), "larare": {}, "beslut": [{"tid": time.strftime("%Y-%m-%d %H:%M"), "av": rektor_namn,
                                                            "text": f"{rektor_namn} blev skolans rektor i Läxspelet Lärare. Alla lärare har nivå 0."}],
         "tid": time.time()}
    return signera_policy(p, priv)


# ---------- kryptering av synken mellan kollegor (AES-GCM) ----------
def _aes(nyckel: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(nyckel)


def skolnyckel(hemlighet: str) -> bytes:
    return hashlib.sha256(("krypt:" + hemlighet).encode()).digest()


def kodnyckel(kod: str) -> bytes:
    """Nyckel av koden kollegan skrev in. Används en gång, för att skicka skolans hemlighet krypterat."""
    import re

    k = re.sub(r"[^A-Z0-9]", "", str(kod).upper())
    return hashlib.pbkdf2_hmac("sha256", k.encode(), b"LXS1-ga-med", 200_000)


def krypt(nyckel: bytes, data: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + _aes(nyckel).encrypt(nonce, data, None)


def dekrypt(nyckel: bytes, data: bytes) -> bytes:
    return _aes(nyckel).decrypt(data[:12], data[12:], None)


# ---------- klass.json på datorn (Windows DPAPI) ----------
def _dpapi(data: bytes, skydda: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inn = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    ut = Blob()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    entropi = b"LaxspeletLarare"
    ebuf = ctypes.create_string_buffer(entropi, len(entropi))
    e = Blob(len(entropi), ctypes.cast(ebuf, ctypes.POINTER(ctypes.c_char)))
    f = crypt32.CryptProtectData if skydda else crypt32.CryptUnprotectData
    if not f(ctypes.byref(inn), None, ctypes.byref(e), None, None, 0x01, ctypes.byref(ut)):  # 0x01 = inget fönster
        raise OSError("DPAPI misslyckades")
    try:
        return ctypes.string_at(ut.pbData, ut.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ut.pbData)  # type: ignore[attr-defined]


def kan_skydda() -> bool:
    return os.name == "nt"


def skydda(data: bytes) -> bytes:
    """Kryptera med lärarens Windows-konto. Kontrollerar att det går att läsa tillbaka innan det används."""
    blob = _dpapi(data, True)
    if _dpapi(blob, False) != data:
        raise OSError("DPAPI gav inte tillbaka samma data")
    return blob


def las_skyddad(blob: bytes) -> bytes:
    return _dpapi(blob, False)
