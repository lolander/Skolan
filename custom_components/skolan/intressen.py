"""Det jag gillar: barnets intressen. Används i AI-uppgifterna (exempel, förklaringar, skrivuppdrag) och i
Lästal och Läs om det du gillar, som AI:n skriver om barnets intressen på rätt nivå.
"""
from __future__ import annotations

import ast
import operator
import random
from datetime import date

from homeassistant.util import dt as dt_util

from . import hjarngympa, skrivkrav

FORSLAG = ["⚽ Fotboll", "🏒 Hockey", "🏀 Basket", "🎮 Minecraft", "🎮 Fortnite", "🎮 Roblox", "🧱 Lego", "🐶 Djur", "🐴 Hästar",
           "🦖 Dinosaurier", "🚀 Rymden", "🏎️ Bilar", "✈️ Flygplan", "🤖 Robotar", "🧙 Magi och fantasy", "🦸 Superhjältar",
           "🎨 Rita", "🎵 Musik", "🎬 Film", "📺 YouTube", "🍕 Mat och bakning", "🏊 Simning", "🌊 Havet", "⚔️ Riddare och historia"]
MAX_ANTAL = 5
AI_PER_DAG = 6  # så många nya lästal/texter per barn och dag
P_KLAR = 3  # +3 ⭐ en gång per dag och aktivitet

# Matten på varje nivå (samma nivå som Snabbräkning i hjärngympan)
MATTE_NIVA = [
    "plus och minus med tal upp till 10",
    "plus och minus med tal upp till 20",
    "plus och minus med tal upp till 100",
    "gånger med tabellerna 2, 3, 4, 5 och 10",
    "gånger och delat med alla tabeller upp till 10",
    "plus, minus, gånger och delat med tal upp till 1000",
    "tvåsiffriga tal gånger ensiffriga, problem i två steg",
    "problem i två eller tre steg med alla fyra räknesätten",
    "flera steg, negativa tal och parenteser",
    "procent (10, 20, 25, 50 %), flera steg och större tal",
]


def alder(data: dict) -> int | None:
    try:
        f = date.fromisoformat(str(data.get("fodelsedag"))[:10])
    except ValueError:
        return None
    nu = dt_util.now().date()
    return nu.year - f.year - ((nu.month, nu.day) < (f.month, f.day))


def lista(data: dict) -> list[str]:
    return list((data.get("intressen") or {}).get("lista", []))


def satt(data: dict, nya: list) -> list[str]:
    rena = []
    for x in nya if isinstance(nya, list) else []:
        t = " ".join(str(x).split())[:30]
        if t and t not in rena:
            rena.append(t)
    data.setdefault("intressen", {})["lista"] = rena[:MAX_ANTAL]
    return data["intressen"]["lista"]


def prompt_rad(data: dict) -> str:
    """Läggs till i AI-instruktionerna så att exempel och uppgifter handlar om sådant barnet gillar."""
    li = lista(data)
    if not li:
        return ""
    return ("\n\nBARNETS INTRESSEN: " + ", ".join(li) + ". Använd gärna något av dem i exempel, liknelser eller uppgifter när det passar "
            "naturligt (inte i varje mening). Fakta och rätt svar går alltid före.")


def status(data: dict) -> dict:
    i = data.get("intressen") or {}
    idag = dt_util.now().date().isoformat()
    return {"lista": lista(data), "forslag": FORSLAG, "max": MAX_ANTAL,
            "lastal_klar": i.get("lastal_klar") == idag, "las_klar": i.get("las_klar") == idag,
            "kvar": max(0, AI_PER_DAG - (i.get("ai", {}).get(idag, 0))), "belonung": P_KLAR, "skrivkrav": skrivkrav.status(data)}


def rakna_ai(data: dict) -> None:
    i = data.setdefault("intressen", {})
    idag = dt_util.now().date().isoformat()
    if i.get("ai", {}).get(idag, 0) >= AI_PER_DAG:
        raise ValueError("Nu har AI:n skrivit många uppgifter idag. Kom tillbaka i morgon! 😴")
    i["ai"] = {idag: i.get("ai", {}).get(idag, 0) + 1}


def valj_amne(data: dict, amne: str | None) -> str:
    li = lista(data)
    if amne and amne in li:
        return amne
    if not li:
        raise ValueError("Välj först vad du gillar.")
    return random.choice(li)


# ---------- Lästal ----------
LASTAL_PROMPT = (
    "Skriv 5 korta, roliga lästal (textuppgifter i matte) på svenska för ett barn som är {alder} år. "
    "Alla ska handla om: {amne}. Matten ska vara: {matte}. Variera uppgifterna. Varje lästal 1–3 meningar, "
    "lätt att förstå, svaret ska vara ett heltal (inga decimaler, inga bråk). Hitta gärna på roliga detaljer men inga felaktiga fakta.\n"
    'Svara ENDAST med JSON: {{"uppgifter": [{{"text": "lästalet", "uttryck": "uträkningen med bara siffror och + - * / ( ), t.ex. (12+8)*3", '
    '"enhet": "kort enhet för svaret, t.ex. mål, kr, st, eller tom sträng"}}, ...]}}'
)
_OP = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg}


def rakna_uttryck(uttryck: str) -> float:
    """Räknar ut AI:ns uttryck säkert (bara tal och + - * / och parenteser)."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OP:
            return _OP[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OP:
            return _OP[type(n.op)](ev(n.operand))
        raise ValueError("Ogiltigt uttryck")
    t = str(uttryck).replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", ".")
    if len(t) > 60:
        raise ValueError("För långt")
    return ev(ast.parse(t, mode="eval"))


def lastal_prompt(data: dict, amne: str) -> str:
    niva = ((data.get("hjarngympa") or {}).get("niva") or {}).get("rakna") or hjarngympa._start_niva(data)
    return LASTAL_PROMPT.format(alder=alder(data) or 10, amne=amne, matte=MATTE_NIVA[max(1, min(10, niva)) - 1])


def lastal_spara(data: dict, amne: str, ai: dict) -> dict:
    """Behåll bara lästal där uträkningen går att räkna ut till ett heltal. Facit sparas på servern."""
    ok = []
    for u in (ai.get("uppgifter") if isinstance(ai, dict) else None) or []:
        try:
            svar = rakna_uttryck(u.get("uttryck", ""))
        except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
            continue
        if abs(svar - round(svar)) > 1e-9 or not str(u.get("text") or "").strip():
            continue
        ok.append({"text": str(u["text"]).strip()[:400], "svar": int(round(svar)), "enhet": str(u.get("enhet") or "")[:15]})
    if len(ok) < 3:
        raise ValueError("AI:n gjorde inte bra lästal den här gången. Försök igen!")
    data.setdefault("intressen", {})["lastal"] = {"amne": amne, "uppg": ok[:5], "skapad": dt_util.now().isoformat(timespec="minutes")}
    return lastal_publik(data)


def lastal_publik(data: dict) -> dict | None:
    lt = (data.get("intressen") or {}).get("lastal")
    if not lt:
        return None
    return {"amne": lt["amne"], "uppg": [{"text": u["text"], "enhet": u["enhet"]} for u in lt["uppg"]], "res": lt.get("res")}


def lastal_svar(data: dict, svar: list) -> dict:
    lt = (data.get("intressen") or {}).get("lastal")
    if not lt:
        raise ValueError("Inga lästal.")
    if lt.get("res"):
        return lt["res"]
    rader = []
    for i, u in enumerate(lt["uppg"]):
        try:
            gissning = int(str(svar[i]).strip().replace(" ", "").replace("−", "-"))
        except (ValueError, IndexError, TypeError):
            gissning = None
        rader.append({"ratt": gissning == u["svar"], "svar": u["svar"], "gissning": gissning})
    ratt = sum(r["ratt"] for r in rader)
    p, vantar = _belona(data, "lastal", ratt * 2 >= len(rader), f"🧮 Lästal om {lt['amne']}: {ratt} av {len(rader)} rätt")
    lt["res"] = {"rader": rader, "ratt": ratt, "av": len(rader), "p": p, "vantar": vantar}
    return lt["res"]


# ---------- Läs om det du gillar ----------
LAS_PROMPT = (
    "Skriv en spännande, lättläst faktatext på svenska för ett barn som är {alder} år, om: {amne}. "
    "Längd: ungefär {ord} ord, i 2–4 korta stycken. Välj en intressant vinkel (en rolig fakta, hur något fungerar, en känd händelse). "
    "Använd bara fakta du är säker på. Avsluta inte med en fråga.\n"
    "Skriv sedan 3 frågor om texten med 4 svarsalternativ var, där exakt ett är rätt och svaret står i texten "
    "(en fråga får kräva att man tänker lite, t.ex. varför).\n"
    "Skriv till sist EN öppen skrivfråga om texten som barnet ska svara på med egna ord i {meningar} hela meningar "
    "(t.ex. vad barnet tyckte var mest spännande och varför, eller förklara något från texten).\n"
    'Svara ENDAST med JSON: {{"rubrik": "kort rubrik", "text": "texten, stycken åtskilda med \\n\\n", '
    '"fragor": [{{"fraga": "...", "alt": ["...", "...", "...", "..."], "ratt": index 0-3}}, ...], "skrivfraga": "..."}}'
)
SKRIV_BEDOM_PROMPT = (
    "Ett barn som är {alder} år har läst en text och svarat med egna ord på en skrivfråga. Bedöm svaret snällt men ärligt.\n"
    "TEXTEN:\n{text}\n\nSKRIVFRÅGAN: {fraga}\n\nBARNETS SVAR: {svar}\n\n"
    "ok = true om barnet svarar på frågan (det får vara barnets egen åsikt) i minst {meningar} meningar som börjar med stor bokstav och slutar med punkt, "
    "frågetecken eller utropstecken. Enstaka stavfel gör inget. ok = false om svaret är för kort, inte handlar om frågan, eller saknar stor bokstav/punkt.\n"
    'Svara ENDAST med JSON: {{"ok": true/false, "bra": "en sak som var bra, riktat till barnet", '
    '"tips": "ett konkret tips om skrivandet eller vad som saknas, riktat till barnet"}}'
)


def las_prompt(data: dict, amne: str) -> str:
    a = alder(data) or 10
    return LAS_PROMPT.format(alder=a, amne=amne, ord=120 if a <= 9 else 180 if a <= 11 else 250, meningar=_meningar(data))


def _meningar(data: dict) -> str:
    return "2–3" if (alder(data) or 10) <= 10 else "3–4"


def skriv_bedom_prompt(data: dict, svar: str) -> str | None:
    """Prompten som rättar skrivsvaret, eller None om texten saknar skrivfråga (äldre texter)."""
    x = (data.get("intressen") or {}).get("las") or {}
    if not x.get("skrivfraga") or x.get("res"):
        return None
    return SKRIV_BEDOM_PROMPT.format(alder=alder(data) or 10, text=x["text"][:2500], fraga=x["skrivfraga"], svar=svar[:1500],
                                     meningar=_meningar(data).split("–")[0])


def las_spara(data: dict, amne: str, ai: dict) -> dict:
    fr = []
    for f in (ai.get("fragor") if isinstance(ai, dict) else None) or []:
        alt = [str(x)[:150] for x in (f.get("alt") or [])][:4]
        try:
            ratt = int(f.get("ratt"))
        except (TypeError, ValueError):
            continue
        if len(alt) == 4 and 0 <= ratt < 4 and str(f.get("fraga") or "").strip():
            fr.append({"fraga": str(f["fraga"])[:250], "alt": alt, "ratt": ratt})
    text = str((ai or {}).get("text") or "").strip()
    if len(fr) < 2 or len(text) < 200:
        raise ValueError("AI:n skrev ingen bra text den här gången. Försök igen!")
    data.setdefault("intressen", {})["las"] = {"amne": amne, "rubrik": str(ai.get("rubrik") or amne)[:80], "text": text[:3000], "fragor": fr[:3],
                                               "skrivfraga": str(ai.get("skrivfraga") or "").strip()[:300] or f"Vad tyckte du var mest intressant i texten om {amne}? Förklara varför.",
                                               "skapad": dt_util.now().isoformat(timespec="minutes")}
    return las_publik(data)


def las_publik(data: dict) -> dict | None:
    x = (data.get("intressen") or {}).get("las")
    if not x:
        return None
    return {"amne": x["amne"], "rubrik": x["rubrik"], "text": x["text"],
            "fragor": [{"fraga": f["fraga"], "alt": f["alt"]} for f in x["fragor"]], "skrivfraga": x.get("skrivfraga"), "res": x.get("res")}


def las_svar(data: dict, svar: list, skrivsvar: str = "", bedomning: dict | None = None) -> dict:
    x = (data.get("intressen") or {}).get("las")
    if not x:
        raise ValueError("Ingen text.")
    if x.get("res"):
        return x["res"]
    rader = []
    for i, f in enumerate(x["fragor"]):
        try:
            g = int(svar[i])
        except (ValueError, IndexError, TypeError):
            g = None
        rader.append({"ratt": g == f["ratt"], "svar": f["ratt"], "gissning": g})
    ratt = sum(r["ratt"] for r in rader)
    skriv = None
    if x.get("skrivfraga"):
        if not bedomning:
            raise ValueError("Skriv ett svar på skrivfrågan först.")
        skriv = {"svar": skrivsvar[:1500], "ok": bool(bedomning.get("ok")), "bra": str(bedomning.get("bra") or "")[:300],
                 "tips": str(bedomning.get("tips") or "")[:300]}
        if not skriv["ok"]:  # skrivsvaret måste bli godkänt: barnet får skriva om (flervalssvaren sparas inte än)
            return {"skriv": skriv, "om": True}
    p, vantar = _belona(data, "las", ratt * 3 >= len(rader) * 2, f"📖 Läst och skrivit om {x['amne']}: {ratt} av {len(rader)} rätt")
    x["res"] = {"rader": rader, "ratt": ratt, "av": len(rader), "p": p, "vantar": vantar, "skriv": skriv}
    return x["res"]


def _belona(data: dict, typ: str, godkant: bool, orsak: str) -> tuple[int, bool]:
    if not godkant:
        return 0, False
    idag = dt_util.now().date().isoformat()
    data.setdefault("intressen", {})[f"{typ}_klar"] = idag
    return skrivkrav.belona(data, P_KLAR, orsak, f"intresse:{typ}:{idag}", "💡")
