"""Packlista: vad som ska med till skolan, byggd av schemat, veckobrevet/kalendern, läxor och prov."""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from . import meriter

LEKTION = [
    (r"idrott|gympa|idh\b|i&h", "🩳 Gympapåse"),
    (r"sim", "🏊 Badkläder och handduk"),
    (r"slöjd|textil|trä", "🧵 Slöjdgrejer (om läraren sagt det)"),
    (r"hemkunskap|hkk", "🍳 Förkläde (om läraren sagt det)"),
]
SAKORD = re.compile(r"ta med|matsäck|utflykt|ombyte|kläder|pengar|matlåda|lunchlåda|vattenflaska|regnkläder|stövlar|underskrift|lappen|blankett|frukt", re.I)
P_PACKAT = 2


def _id(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:10]


def dag_for(nu=None) -> date:
    """Efter kl. 14 gäller listan nästa skoldag, annars idag (helger hoppas över)."""
    nu = nu or dt_util.now()
    d = nu.date() + timedelta(days=1 if nu.hour >= 14 else 0)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def lista(data: dict, dag: date) -> list[dict]:
    ut: list[dict] = []
    sett = set()

    def lagg(text: str, varfor: str) -> None:
        k = _id(text.lower())
        if k not in sett:
            sett.add(k)
            ut.append({"id": k, "text": text, "varfor": varfor})

    if not meriter.ledig(data, dag):
        for x in data.get("lektioner", []):
            if x.get("dag") == dag.weekday() and not x.get("ej"):
                for monster, sak in LEKTION:
                    if re.search(monster, str(x.get("namn") or ""), re.I):
                        lagg(sak, f"{x.get('namn')}{' kl. ' + x['start'] if x.get('start') else ''}")
    for x in meriter.skolinfo(data):
        if x.get("datum") == dag.isoformat() and SAKORD.search(x.get("text", "")):
            lagg(f"📌 {x['text'][:90]}", "från skolan")
    for u in data.get("uppdrag", []):
        if u.get("datum") != dag.isoformat() or (u.get("klart") and u.get("typ") != "prov"):
            continue
        if u.get("typ") == "prov":
            lagg("✏️ Penna, sudd (och linjal/miniräknare om det behövs)", f"prov: {u['namn']}")
        else:
            lagg(f"📚 {u['namn']} ({u.get('amne_namn')})", "läxa till den dagen")
    for t in ((data.get("packlista") or {}).get("fasta") or {}).get(str(dag.weekday()), []):
        lagg(t, "varje vecka")
    return ut


def status(data: dict) -> dict:
    dag = dag_for()
    rader = lista(data, dag)
    bockat = ((data.get("packlista") or {}).get("bockat") or {}).get(dag.isoformat(), [])
    return {"dag": dag.isoformat(), "rader": rader, "bockat": [b for b in bockat if b in {r["id"] for r in rader}],
            "fasta": (data.get("packlista") or {}).get("fasta") or {}}


def bocka(data: dict, dag: str, rid: str, pa: bool, belona: bool = True) -> int:
    pl = data.setdefault("packlista", {})
    b = pl.setdefault("bockat", {})
    lst = set(b.get(dag, []))
    lst.add(rid) if pa else lst.discard(rid)
    b[dag] = sorted(lst)
    for k in sorted(b)[:-7]:
        b.pop(k, None)
    try:
        rader = lista(data, date.fromisoformat(dag))
    except ValueError:
        return 0
    if belona and rader and {r["id"] for r in rader} <= lst and meriter.ge(data, P_PACKAT, "🎒 Packade väskan", f"packa:{dag}", "🎒"):
        return P_PACKAT
    return 0


def fast(data: dict, veckodag: int, text: str, bort: bool) -> None:
    f = data.setdefault("packlista", {}).setdefault("fasta", {})
    k = str(max(0, min(4, veckodag)))
    text = re.sub(r"\s+", " ", text or "").strip()[:60]
    if bort:
        f[k] = [x for x in f.get(k, []) if x != text]
    elif text and text not in f.get(k, []):
        f.setdefault(k, []).append(text)
        f[k] = f[k][-10:]
