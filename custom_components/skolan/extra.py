"""Mattemonster, läsflyt, läsa-lätt-läge och "Hur känns skolan?"."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util

from . import meriter

# ---------- Mattemonster: så många rätt som möjligt på 60 sekunder ----------
MATTE_TYPER = {"gange": "Gångertabellen", "plus": "Plus och minus", "delat": "Delat med", "blandat": "Blandat"}
P_MATTE_REKORD = 5
P_MATTE_DAG = 3  # första spelet per dag med minst 10 rätt


def matte_rekord(data: dict, typ: str, niva: int, poang: int) -> dict:
    typ = typ if typ in MATTE_TYPER else "blandat"
    poang = max(0, min(120, int(poang)))
    idag = dt_util.now().date().isoformat()
    m = data.setdefault("matte", {})
    rek = m.setdefault("rekord", {})
    k = f"{typ}:{niva}"
    gammalt = rek.get(k, 0)
    nytt = poang > gammalt
    if nytt:
        rek[k] = poang
    m["historik"] = (m.get("historik", []) + [{"tid": dt_util.now().isoformat(timespec="minutes"), "typ": typ, "niva": niva, "poang": poang}])[-100:]
    p = 0
    if poang >= 10:
        if meriter.ge(data, P_MATTE_DAG, f"🔢 Mattemonster: {poang} rätt", f"matte:{idag}", "🔢"):
            p += P_MATTE_DAG
        if nytt and gammalt and meriter.ge(data, P_MATTE_REKORD, f"🔢 Nytt matterekord ({MATTE_TYPER[typ]}): {poang}!", f"matterek:{k}:{idag}", "⚡"):
            p += P_MATTE_REKORD
        meriter.aktiv(data, idag)
    return {"nytt": nytt, "gammalt": gammalt, "p": p, "rekord": rek}


# ---------- Läsflyt: läsa en sida högt, ord per minut ----------
P_LASFLYT = 3
MAX_WPM = 260  # snabbare än så går inte att läsa högt: räknas inte


def lasflyt_spara(data: dict, bok: str, sida: str, ord_: int, sek: int, fil: str | None) -> dict:
    sek = max(1, int(sek))
    wpm = round(ord_ * 60 / sek) if ord_ else 0
    ok = ord_ >= 20 and sek >= 15 and wpm <= MAX_WPM
    lista = data.setdefault("lasflyt", [])
    lista.append({"tid": dt_util.now().isoformat(timespec="minutes"), "bok": bok, "sida": sida, "ord": ord_, "sek": sek, "wpm": wpm, "ok": ok, "fil": fil})
    del lista[:-100]
    p = 0
    idag = dt_util.now().date().isoformat()
    if ok:
        if meriter.ge(data, P_LASFLYT, f"📖 Läste högt: {wpm} ord/min", f"lasflyt:{idag}", "📖"):
            p = P_LASFLYT
        meriter.aktiv(data, idag)
    return {"wpm": wpm, "ok": ok, "p": p, "basta": max((x["wpm"] for x in lista if x.get("ok")), default=0)}


def lasflyt_gamla_filer(data: dict, behall: int = 15) -> list[str]:
    """Ljudfiler som kan tas bort (bara de senaste sparas)."""
    med = [x for x in data.get("lasflyt", []) if x.get("fil")]
    ut = []
    for x in med[:-behall]:
        ut.append(x["fil"])
        x["fil"] = None
    return ut


# ---------- Hur känns skolan? ----------
KANSLOR = {"super": ("😄", "Superbra"), "bra": ("🙂", "Bra"), "sadar": ("😐", "Sådär"), "ledsen": ("😢", "Ledsen"), "stressad": ("😰", "Stressad"), "arg": ("😠", "Arg")}
JOBBIGA = {"ledsen", "stressad", "arg"}
FRAGA_DAGAR = (0, 2, 4)  # måndag, onsdag, fredag


def mående_fraga(data: dict) -> bool:
    """Ska frågan visas idag? (mån/ons/fre efter kl. 13, inte om barnet redan svarat)."""
    nu = dt_util.now()
    if nu.weekday() not in FRAGA_DAGAR or nu.hour < 13:
        return False
    return not any(x["dag"] == nu.date().isoformat() for x in data.get("mående", []))


def mående_svar(data: dict, kansla: str, vad: list[str], text: str) -> dict:
    if kansla not in KANSLOR:
        raise ValueError("Välj hur det känns.")
    idag = dt_util.now().date().isoformat()
    lista = [x for x in data.setdefault("mående", []) if x["dag"] != idag]
    lista.append({"dag": idag, "kansla": kansla, "vad": [str(v)[:30] for v in vad][:5], "text": str(text or "").strip()[:300]})
    data["mående"] = lista[-120:]
    meriter.ge(data, 1, "💬 Berättade hur skolan känns", f"mående:{idag}", "💬")
    senaste = [x for x in data["mående"][-3:]]
    larm = len(senaste) == 3 and all(x["kansla"] in JOBBIGA for x in senaste) and data.get("mående_larm") != idag
    if larm:
        data["mående_larm"] = idag
    return {"larm": larm}


def mående_status(data: dict, foralder: bool) -> dict:
    lista = data.get("mående", [])
    ut = {"fraga": mående_fraga(data), "kanslor": {k: list(v) for k, v in KANSLOR.items()}}
    if foralder:
        fran = (dt_util.now().date() - timedelta(days=42)).isoformat()
        ut["historik"] = [x for x in lista if x["dag"] >= fran]
    return ut
