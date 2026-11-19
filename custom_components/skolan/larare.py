"""Till läraren: underlag till utvecklingssamtalet, veckans lapp (det som var svårt) och text om AI:n.

Allt går via föräldern: inget skickas till läraren automatiskt. Föräldern läser, ändrar och skickar själv
(kopiera, egen mejlapp eller skolans plattform). Inga stjärnor, husdjur, mående eller jämförelser med syskon.
"""
from __future__ import annotations

import html
from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from . import intressen, utveckling

SAMTAL_DAGAR = 56  # utvecklingssamtalet: de senaste 8 veckorna
LAPP_DAGAR = 7


def _d(t) -> date | None:
    try:
        return date.fromisoformat(str(t)[:10])
    except ValueError:
        return None


def fakta(data: dict, dagar: int) -> dict:
    """Det barnet har gjort och tyckt var svårt de senaste dagarna, per ämne."""
    idag = dt_util.now().date()
    fran = idag - timedelta(days=dagar)
    inom = lambda t: (x := _d(t)) is not None and x >= fran  # noqa: E731
    amnen = {a["id"]: a["namn"] for a in data.get("amnen", [])}
    per: dict[str, dict] = {}

    def a(namn: str) -> dict:
        return per.setdefault(namn or "Övrigt", {"gjort": [], "svart": []})

    for am in data.get("amnen", []):
        for g in am.get("glosor", []):
            res = [r for r in g.get("resultat", []) if inom(r.get("datum")) and r.get("av")]
            if res:
                pct = round(100 * sum(r["ratt"] for r in res) / sum(r["av"] for r in res))
                a(am["namn"])["gjort"].append(f"Övade glosorna \"{g['namn']}\" {len(res)} gånger ({pct} % rätt direkt)")
            svara = sorted((g.get("svara") or {}).items(), key=lambda kv: -kv[1])[:6]
            if svara and res:
                a(am["namn"])["svart"].append(f"Ord som ofta blev fel i \"{g['namn']}\": " + ", ".join(k for k, _ in svara))
    for f in data.get("forhor", []):
        if f.get("klart") and inom(f["klart"]) and f.get("fragor"):
            svar = f.get("svar", [])
            ratt = sum(1 for s in svar if s.get("ratt"))
            a(f.get("amne_namn") or amnen.get(f.get("amne")))["gjort"].append(f"Förhör \"{f['namn']}\": {ratt} av {len(f['fragor'])} rätt")
            fel = [q["fraga"] for q, s in zip(f["fragor"], svar) if not s.get("ratt")][:6]
            if fel:
                a(f.get("amne_namn") or amnen.get(f.get("amne")))["svart"].append(f"Fel på förhöret \"{f['namn']}\": " + ", ".join(fel))
    for u in data.get("uppdrag", []):
        namn = u.get("amne_namn") or amnen.get(u.get("amne"))
        if u.get("typ") == "prov" and (inom(u.get("datum")) or (u.get("datum") or "") >= idag.isoformat()):
            plugg = len([d for d in u.get("studiedagar", []) if inom(d)])
            res = u.get("resultat") or {}
            text = f"Prov \"{u['namn']}\" {u.get('datum') or ''}" + (f": pluggade {plugg} {'dag' if plugg == 1 else 'dagar'}" if plugg else "")
            if res.get("betyg") or res.get("ratt") is not None:
                text += f", resultat {res.get('betyg') or str(res.get('ratt')) + ' av ' + str(res.get('av'))}"
            a(namn)["gjort"].append(text)
        elif u.get("typ") in ("las", "hogl") and inom(u.get("skapad")):
            a(namn)["gjort"].append(f"{'Högläsning' if u['typ'] == 'hogl' else 'Läsläxa'} \"{u['namn']}\"" + (" (klar)" if u.get("klart") or u.get("allt_last") else ""))
    for s in data.get("svaga", []):
        if not s.get("klar") and inom(s.get("skapad")):
            a(amnen.get(s.get("amne")))["svart"].append(f"Svag punkt: {s.get('fraga', '')[:140]}")
    for namn in per:  # högst några per ämne, så det blir läsbart
        per[namn]["svart"] = per[namn]["svart"][:5]
        per[namn]["gjort"] = per[namn]["gjort"][:8]

    skriv = (data.get("skriv") or {}).get("historik", [])
    skriv = [x for x in skriv if inom(x.get("tid"))]
    penna = [x for x in (data.get("penna") or {}).get("inlamnat", []) if x.get("godkand") and inom(x.get("tid"))]
    lf = [x["wpm"] for x in (data.get("lasflyt") or []) if x.get("ok") and inom(x.get("tid"))]
    dagar_ovat = len([d for d in data.get("meriter", {}).get("ovningsdagar", []) if inom(d)])
    return {
        "fran": fran.isoformat(), "till": idag.isoformat(), "dagar": dagar,
        "dagar_ovat": dagar_ovat, "per_vecka": round(dagar_ovat / max(1, dagar / 7), 1),
        "amnen": {k: v for k, v in per.items() if v["gjort"] or v["svart"]},
        "skriv": f"{len(skriv)} övningar i Skrivverkstaden, {len(penna)} handskrivna texter" if skriv or penna else "",
        "lasflyt": f"{round(sum(lf) / len(lf))} ord per minut i snitt ({len(lf)} mätningar)" if lf else "",
        "battre": [f"{m['namn']}: från {m['da']:g} till {m['nu']:g}" for m in utveckling.matt(data)["battre"]],
        "intressen": intressen.lista(data),
    }


def fakta_text(f: dict) -> str:
    rader = [f"Period: {f['fran']} till {f['till']}. Pluggade {f['dagar_ovat']} dagar ({f['per_vecka']} per vecka)."]
    for namn, x in f["amnen"].items():
        rader.append(f"\n{namn}:")
        rader += [f"- {t}" for t in x["gjort"]]
        rader += [f"- SVÅRT: {t}" for t in x["svart"]]
    if f["skriv"]:
        rader.append(f"\nSkrivande: {f['skriv']}")
    if f["lasflyt"]:
        rader.append(f"Läshastighet: {f['lasflyt']}")
    if f["battre"]:
        rader.append("Blivit bättre på: " + "; ".join(f["battre"]))
    return "\n".join(rader)


SAMTAL_PROMPT = (
    "Du hjälper en förälder inför utvecklingssamtalet i skolan för {namn} ({alder} år). Här är vad barnet har gjort i Läxspelet "
    "(en läxapp hemma) de senaste veckorna:\n\n{fakta}\n\n"
    "Skriv en kort, saklig och vänlig sammanfattning på svenska som föräldern kan ta med till läraren. Bara det som står i underlaget, hitta inte på något. "
    "Inga betyg eller diagnoser. Skriv om styrkor, vad som är svårt, och 2–3 konkreta frågor föräldern kan ställa till läraren.\n"
    'Svara ENDAST med JSON: {{"styrkor": ["…"], "svart": ["…"], "fragor": ["…"]}} (högst 4 punkter var, korta meningar)'
)

LAPP_PROMPT = (
    "Skriv en kort lapp på svenska från en förälder till {namn}s lärare om vad {namn} ({alder} år) tyckte var svårt den här veckan, "
    "så att läraren kan ta upp det igen. Underlag från läxappen hemma:\n\n{fakta}\n\n"
    "Regler: vänlig och kort (högst 90 ord), börja med \"Hej!\", nämn bara det som verkligen var svårt (de viktigaste 1–3 sakerna, konkret), "
    "inga stjärnor, appar eller poäng, inga krav på läraren. Avsluta med \"Hälsningar\" och lämna namnet tomt. "
    "Finns inget svårt i underlaget: skriv en kort lapp om att det har gått bra och vad barnet har övat på.\n"
    'Svara ENDAST med JSON: {{"text": "lappen"}}'
)

OM_AI = (
    "Hej!\n\n"
    "Vi använder en läxapp hemma som heter Läxspelet. Den hjälper {namn} att planera och öva på läxorna: glosor, läsläxor, "
    "inför prov och skrivande. Lite information om hur den använder AI:\n\n"
    "• AI:n ger aldrig svaret på läxuppgifter eller provfrågor. Den ställer frågor, förklarar hur man tänker och ger ledtrådar, "
    "så att barnet löser uppgiften själv.\n"
    "• Den utgår från barnets eget material (fotade boksidor, glosor och läxor) och skriver aldrig av bokens text.\n"
    "• Skrivuppgifter skriver barnet själv, ofta för hand på papper. AI:n ger bara tips om till exempel stor bokstav, punkt och stycken.\n"
    "• Förhör görs utan hjälp och tips.\n"
    "• Vi föräldrar ser allt barnet gör i appen.\n\n"
    "Har du önskemål om hur ni vill att {namn} övar, eller om något ni hellre ser att vi inte hjälper till med hemma, säg gärna till!\n\n"
    "Vill du se hur {namn} pluggar, få lappar från oss och skicka veckobrev direkt till läxappen? Det finns en gratis lärarapp för Windows: "
    "https://github.com/lolander/Skolan/releases/latest/download/Laxspelet-Larare-Setup.exe\n\n"
    "Hälsningar"
)


def _lista(rubrik: str, punkter: list[str]) -> str:
    if not punkter:
        return ""
    return f"<h2>{html.escape(rubrik)}</h2><ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in punkter) + "</ul>"


def samtal_sida(namn: str, f: dict, ai: dict | None) -> str:
    """Utskriftsvänlig sida (A4) för utvecklingssamtalet."""
    e = html.escape
    amnen = "".join(
        f"<div class='amne'><h3>{e(a)}</h3>{''.join(f'<p>{e(t)}</p>' for t in x['gjort'])}"
        f"{''.join(f'<p class=svart>⚠ {e(t)}</p>' for t in x['svart'])}</div>" for a, x in f["amnen"].items())
    ai_html = ""
    if ai:
        ai_html = (f"<section class='ai'>{_lista('Styrkor', ai.get('styrkor', []))}{_lista('Det som är svårt', ai.get('svart', []))}"
                   f"{_lista('Frågor till läraren', ai.get('fragor', []))}<p class='liten'>Sammanfattningen är skriven med AI utifrån underlaget nedan.</p></section>")
    ovrigt = [x for x in (f["skriv"] and f"Skrivande: {f['skriv']}", f["lasflyt"] and f"Läshastighet: {f['lasflyt']}") if x]
    return f"""<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(namn)}: underlag till utvecklingssamtalet</title><style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#222;line-height:1.45;font-size:14px}}
h1{{font-size:22px;margin:0}} h2{{font-size:16px;margin:16px 0 4px;border-bottom:2px solid #ddd}} h3{{font-size:14px;margin:10px 0 2px}}
.liten{{color:#666;font-size:12px}} .amne p{{margin:1px 0 1px 12px}} .svart{{color:#b23c17}} ul{{margin:4px 0;padding-left:20px}}
.ai{{background:#f5f7fa;border-radius:10px;padding:4px 14px 8px;margin-top:10px}} .knapp{{margin:12px 0}} button{{font-size:15px;padding:8px 14px}}
@media print{{.knapp{{display:none}} body{{margin:0}}}}
</style></head><body>
<div class="knapp"><button onclick="print()">🖨️ Skriv ut / spara som PDF</button></div>
<h1>{e(namn)}: underlag till utvecklingssamtalet</h1>
<p class="liten">Från läxappen hemma, {e(f['fran'])} till {e(f['till'])}. Pluggat {f['dagar_ovat']} dagar ({f['per_vecka']:g} per vecka).</p>
{ai_html}
{_lista('Blivit bättre på', f['battre'])}
<h2>Ämne för ämne</h2>{amnen or "<p>Inget registrerat under perioden.</p>"}
{_lista('Övrigt', ovrigt)}
{_lista('Intressen', f['intressen'])}
</body></html>"""


# ---------- veckans lapp ----------
def vecka_nu() -> str:
    return "{}-W{:02d}".format(*dt_util.now().date().isocalendar()[:2])


def har_svart(f: dict) -> bool:
    return any(x["svart"] for x in f["amnen"].values())


def lapp_status(s: dict) -> dict:
    lp = s.get("lapp") or {}
    return {**lp, "aktuell": lp.get("vecka") == vecka_nu()}


def lapp_satt(s: dict, text: str, status: str = "utkast") -> dict:
    s["lapp"] = {"vecka": vecka_nu(), "text": str(text or "").strip()[:2000], "status": status,
                 "tid": dt_util.now().isoformat(timespec="minutes")}
    return s["lapp"]


def skicka(s: dict, typ: str, innehall: dict, till: list | None = None) -> dict:
    """Lägg i kön till lärarappen (hämtas vid nästa synk). till = lärarnas id (tomt = alla som har funktionen på).
    Ett nytt samtalsunderlag ersätter det förra till samma lärare."""
    import secrets
    till = [str(x) for x in (till or []) if str(x) in (s.get("lararna") or {})] or None
    if typ == "samtal":
        s["utgaende"] = [x for x in s.get("utgaende", []) if x["typ"] != "samtal" or (till and x.get("till") and not set(x["till"]) & set(till))]
    post = {"id": secrets.token_hex(6), "typ": typ, "tid": dt_util.now().isoformat(timespec="minutes"), "till": till, **innehall}
    s.setdefault("utgaende", []).append(post)
    return post


def samtal_till_larare(namn: str, f: dict, ai: dict | None) -> dict:
    """Samtalsunderlaget som data till lärarappen (läraren visar det själv)."""
    return {"namn": namn, "fran": f["fran"], "till": f["till"], "per_vecka": f["per_vecka"], "dagar_ovat": f["dagar_ovat"],
            "amnen": {k: {"gjort": v["gjort"], "svart": v["svart"]} for k, v in list(f["amnen"].items())[:15]},
            "battre": f["battre"][:8], "ovrigt": [x for x in (f["skriv"], f["lasflyt"]) if x],
            "ai": {k: [str(x)[:300] for x in (ai or {}).get(k, [])][:4] for k in ("styrkor", "svart", "fragor")} if ai else None}
