"""Skrivkravet: barnen ska inte kunna slippa skrivövningar.

Har barnet inte gjort en skrivövning (Skrivverkstaden eller ett godkänt Pennuppdrag) på SKRIV_DAGAR dagar, sparas
stjärnorna från Hjärngympan och Det jag gillar som "väntande". De betalas ut (och dagen räknas för sviten) så fort
barnet skriver igen.
"""
from __future__ import annotations

from datetime import date

from homeassistant.util import dt as dt_util

from . import meriter

SKRIV_DAGAR = 4


def senast(data: dict) -> date | None:
    tider = [x.get("tid", "") for x in (data.get("skriv") or {}).get("historik", [])]
    tider += [x.get("tid", "") for x in (data.get("penna") or {}).get("inlamnat", []) if x.get("godkand")]
    dagar = []
    for t in tider:
        try:
            dagar.append(date.fromisoformat(t[:10]))
        except ValueError:
            continue
    return max(dagar) if dagar else None


def ok(data: dict) -> bool:
    s = senast(data)
    return s is not None and (dt_util.now().date() - s).days < SKRIV_DAGAR


def _vantar(data: dict) -> list:
    return data.setdefault("skrivkrav", {}).setdefault("vantar", [])


def belona(data: dict, poang: int, orsak: str, nyckel: str, ikon: str) -> tuple[int, bool]:
    """Ge stjärnor och räkna dagen för sviten, eller spara dem tills barnet har skrivit. Returnerar (givet, väntar)."""
    idag = dt_util.now().date().isoformat()
    if ok(data):
        meriter.aktiv(data, idag)
        return (poang if meriter.ge(data, poang, orsak, nyckel, ikon) else 0), False
    v = _vantar(data)
    if nyckel not in meriter._m(data)["nycklar"] and not any(x["nyckel"] == nyckel for x in v):
        v.append({"p": poang, "orsak": orsak, "nyckel": nyckel, "ikon": ikon, "dag": idag})
        del v[:-30]
    return 0, True


def slapp(data: dict) -> int:
    """Barnet har skrivit: betala ut det som väntar. Anropas när en skrivövning sparas."""
    v = (data.get("skrivkrav") or {}).get("vantar") or []
    if not v or not ok(data):
        return 0
    givet = 0
    for x in v:
        meriter.aktiv(data, x["dag"])
        if meriter.ge(data, x["p"], f"{x['orsak']} (efter skrivövningen ✍️)", x["nyckel"], x["ikon"]):
            givet += x["p"]
    data["skrivkrav"]["vantar"] = []
    return givet


def status(data: dict) -> dict:
    s = senast(data)
    v = (data.get("skrivkrav") or {}).get("vantar") or []
    return {"ok": ok(data), "senast": s.isoformat() if s else None, "dagar": SKRIV_DAGAR,
            "vantar": sum(x["p"] for x in v)}
