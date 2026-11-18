"""Skrivverkstad: punkt och andra tecken, mellanrum, stycken och fritt skrivande.

Ren logik utan AI: rättning av tecken- och styckeövningar, nivåer och historik.
"""
from __future__ import annotations

import difflib
import re
import uuid

from homeassistant.util import dt as dt_util

from . import meriter, skrivkrav

# Nivåer för teckenövningen: varje nivå lägger till nya tecken.
NIVAER = {
    1: {"namn": "Punkt och stor bokstav", "tecken": ".", "info": "Sätt punkt när meningen är slut och stor bokstav i början av nästa mening och på namn."},
    2: {"namn": "Frågetecken och utropstecken", "tecken": ".?!", "info": "Punkt, frågetecken (?) när någon frågar och utropstecken (!) när något sägs med känsla."},
    3: {"namn": "Komma", "tecken": ".?!,", "info": "Som nivå 2 och kommatecken (,) där man gör en liten paus, t.ex. före men och i uppräkningar."},
    4: {"namn": "Repliker med talstreck", "tecken": ".?!,–:", "info": "Som nivå 3 och talstreck (–) när någon pratar, och kolon (:) före en uppräkning eller replik."},
}
OMRADEN = {"tecken": "Punkt och tecken", "stor": "Stor bokstav", "mellanrum": "Mellanrum", "stycken": "Stycken",
           "struktur": "Början och slut", "ordval": "Ordval", "meningar": "Variation i meningarna"}
P_OVNING = 3  # ⭐ per övning med minst 70 %
OVNING_MAX = 4  # övningar per dag som ger ⭐
P_FRITT = 6  # ⭐ för en bedömd text, en gång per dag
P_FORBATTRA = 3  # ⭐ när en ny version blev bättre, en gång per dag

ORD_RE = re.compile(r"([^\s\wåäöÅÄÖéÉüÜ]*)([\wåäöÅÄÖéÉüÜ'-]+)([^\s\wåäöÅÄÖéÉüÜ]*)")


def _s(data: dict) -> dict:
    return data.setdefault("skriv", {"niva": {}, "historik": []})


def start_niva(alder: int | None) -> int:
    a = alder or 11
    return 1 if a < 9 else 2 if a < 11 else 3


def niva(data: dict, alder: int | None) -> int:
    return int(_s(data)["niva"].get("tecken") or start_niva(alder))


def _tokens(text: str) -> list[tuple[str, str, str]]:
    text = re.sub(r"(^|\s)([–—-])\s+", r"\1\2", text or "")  # fristående talstreck hör till nästa ord
    return [(m.group(1), m.group(2), m.group(3)) for m in ORD_RE.finditer(text)]


def _norm_tecken(t: str, tillatna: str) -> str:
    t = t.replace("-", "–").replace("—", "–")
    return "".join(c for c in t if c in tillatna + "–")


def ovning_tecken(text: str, niva_: int) -> dict:
    """Gör övningen: alla tecken bort och bara små bokstäver (barnet sätter tillbaka dem)."""
    tillatna = NIVAER[niva_]["tecken"]
    toks = _tokens(text)
    visa = " ".join(o.lower() for _f, o, _e in toks)
    facit = [{"ord": o, "fore": _norm_tecken(f, tillatna), "efter": _norm_tecken(e, tillatna), "stor": o[:1].isupper()} for f, o, e in toks]
    return {"visa": visa, "facit": facit, "text": text}


def ratta_tecken(ov: dict, svar: str) -> dict:
    """Jämför barnets text med facit ord för ord. Ger poäng och en markering per ord."""
    tillatna = NIVAER[ov.get("niva", 1)]["tecken"]
    facit = ov["facit"]
    svar_t = _tokens(svar)
    a = [x["ord"].lower() for x in facit]
    b = [o.lower() for _f, o, _e in svar_t]
    match = {}
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            match[blk.b + k] = blk.a + k
    rad, tp, fp, fn, stor_ok, stor_fel = [], 0, 0, 0, 0, 0
    fel_typ = {"tecken": 0, "stor": 0}
    for j, (f, o, e) in enumerate(svar_t):
        i = match.get(j)
        if i is None:
            rad.append({"ord": f + o + e, "status": "okant"})
            continue
        fx = facit[i]
        mina = (_norm_tecken(f, tillatna), _norm_tecken(e, tillatna))
        ok_t = mina == (fx["fore"], fx["efter"])
        for m_, v_ in zip(mina, (fx["fore"], fx["efter"])):
            if v_ and m_ == v_:
                tp += 1
            elif v_ and m_ != v_:
                fn += 1
                if m_:
                    fp += 1
            elif m_ and not v_:
                fp += 1
        ok_s = o[:1].isupper() == fx["stor"]
        if fx["stor"] or o[:1].isupper():
            stor_ok += ok_s
            stor_fel += not ok_s
        if not ok_t:
            fel_typ["tecken"] += 1
        if not ok_s:
            fel_typ["stor"] += 1
        rad.append({"ord": f + o + e, "status": "ratt" if ok_t and ok_s else "fel",
                    "vantat": None if ok_t and ok_s else fx["fore"] + (fx["ord"] if fx["stor"] else fx["ord"].lower()) + fx["efter"]})
    saknas = len(facit) - len(set(match.values()))
    fn += sum(bool(facit[i]["efter"]) + bool(facit[i]["fore"]) for i in range(len(facit)) if i not in match.values())
    # mellanrum: tecken som sitter ihop med nästa ord, eller mellanslag före tecken
    mellan = len(re.findall(r"[.?!,:][A-Za-zÅÄÖåäö]", svar or "")) + len(re.findall(r"\s+[.?!,:]", svar or ""))
    tecken_p = tp / max(1, tp + fp + fn)
    stor_p = stor_ok / max(1, stor_ok + stor_fel)
    poang = round(100 * (0.6 * tecken_p + 0.3 * stor_p + 0.1 * (1 if not mellan else max(0, 1 - mellan / 4))))
    return {"poang": poang, "rad": rad, "facit": ov["text"], "mellanrum_fel": mellan, "saknade_ord": saknas,
            "omraden": {"tecken": round(tecken_p * 100), "stor": round(stor_p * 100), "mellanrum": 100 if not mellan else max(0, 100 - 25 * mellan)}}


def ratta_stycken(ov: dict, val: list) -> dict:
    """ov["starter"]: index för meningar där ett nytt stycke börjar (inte 0). val: barnets index."""
    ratt = set(ov["starter"])
    mina = {int(x) for x in val if str(x).isdigit() and 0 < int(x) < len(ov["meningar"])}
    poang = round(100 * len(ratt & mina) / max(1, len(ratt | mina)))
    return {"poang": poang, "starter": sorted(ratt), "mina": sorted(mina), "omraden": {"stycken": poang}}


def spara_resultat(data: dict, typ: str, poang: int, omraden: dict, alder: int | None, text: str = "") -> int:
    """Historik, nivåändring och ⭐. Returnerar ⭐."""
    s = _s(data)
    idag = dt_util.now().date().isoformat()
    s["historik"] = (s.get("historik", []) + [{"tid": dt_util.now().isoformat(timespec="minutes"), "typ": typ, "poang": poang,
                                                "omraden": omraden, "text": text[:60]}])[-300:]
    p = 0
    if typ == "tecken":
        n = niva(data, alder)
        senaste = [x["poang"] for x in s["historik"] if x["typ"] == "tecken"][-3:]
        if len(senaste) == 3 and min(senaste) >= 80 and n < 4:
            s["niva"]["tecken"] = n + 1
        elif len(senaste) >= 2 and max(senaste[-2:]) < 45 and n > 1:
            s["niva"]["tecken"] = n - 1
        else:
            s["niva"]["tecken"] = n
    if typ in ("tecken", "stycken") and poang >= 70:
        for k in range(1, OVNING_MAX + 1):
            if meriter.ge(data, P_OVNING, f"✍️ Skrivövning: {OMRADEN.get(typ, typ)} ({poang} %)", f"skrivovn:{idag}:{k}", "✍️"):
                p = P_OVNING
                meriter.energi_bonus(data, 1, 2)
                break
    elif typ == "fritt" and meriter.ge(data, P_FRITT, "✍️ Skrev en egen text", f"skrivfritt:{idag}", "✍️"):
        p = P_FRITT
    elif typ == "forbattrad" and meriter.ge(data, P_FORBATTRA, "✍️ Förbättrade sin text", f"skrivbattre:{idag}", "✍️"):
        p = P_FORBATTRA
    if p or poang >= 60:
        meriter.aktiv(data, idag)
    return p + skrivkrav.slapp(data)  # stjärnor som väntat på en skrivövning


def status(data: dict, alder: int | None) -> dict:
    s = _s(data)
    hist = s.get("historik", [])
    per = {}
    for x in hist[-60:]:
        for k, v in (x.get("omraden") or {}).items():
            per.setdefault(k, []).append(v)
    n = niva(data, alder)
    return {"niva": n, "niva_namn": NIVAER[n]["namn"], "niva_info": NIVAER[n]["info"], "senaste": hist[-20:],
            "omraden": {k: {"namn": OMRADEN.get(k, k), "snitt": round(sum(v[-8:]) / len(v[-8:]))} for k, v in per.items()},
            "idag": sum(1 for x in hist if x["tid"][:10] == dt_util.now().date().isoformat())}


def ny_id() -> str:
    return uuid.uuid4().hex[:10]
