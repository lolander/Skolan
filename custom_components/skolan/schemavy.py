"""Lektionsschemat som en fristående, utskriftsvänlig sida med sökning.

Samma fil finns i lärarappen (larare/skolan_larare/schemavy.py). Ändra båda.
"""
from __future__ import annotations

import html
import re

DAGAR = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag"]
FARGER = ["#4f8ef7", "#f7a14f", "#4fc98a", "#e05f8a", "#9b6cf0", "#2bb5c4", "#d4b02a", "#e0603a"]


def _min(t) -> int | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(t or ""))
    return int(m[1]) * 60 + int(m[2]) if m else None


def _farg(namn: str, farger: dict) -> str:
    f = farger.get(namn.lower())
    if f and re.fullmatch(r"#[0-9a-fA-F]{6}", f):
        return f
    return FARGER[sum(ord(c) for c in namn) % len(FARGER)]


def sida(titel: str, lektioner: list, farger: dict | None = None, hem: str = "/") -> str:
    """Hela HTML-sidan. farger: ämnesnamn (gemener) -> #rrggbb."""
    farger = farger or {}
    e = lambda s: html.escape(str(s or ""))  # noqa: E731
    lekt = [x for x in lektioner if isinstance(x, dict) and 0 <= int(x.get("dag", -1)) <= 4 and x.get("namn")]
    tider = []
    for x in lekt:
        st = _min(x.get("start"))
        if st is not None:
            tider += [st, _min(x.get("slut")) or st + 40]
    fran = (min(tider) // 60) * 60 if tider else 480
    till = -(-max(tider) // 60) * 60 if tider else 900
    px = 1.4  # pixlar per minut på skärmen; utskriften skalar om
    hojd = (till - fran) * px

    def kolumner_for(dag_lekt: list) -> dict:
        """Lektioner som krockar (delad tid) får dela bredden: id(lektion) -> (kolumn, antal)."""
        ut, grupp, slut = {}, [], -1
        def stang():
            cols, ej_kol = [], []
            for x in grupp:
                st = _min(x.get("start"))
                k = next((i for i, c in enumerate(cols) if c <= st), None)
                if k is None:
                    cols.append(0)
                    ej_kol.append(True)
                    k = len(cols) - 1
                cols[k] = _min(x.get("slut")) or st + 40
                if not x.get("ej"):
                    ej_kol[k] = False
                ut[id(x)] = [k, 0]
            # andra gruppens lektioner (ej) blir smala så att barnets egen lektion får plats
            vikt = [0.3 if e and not all(ej_kol) else 1 for e in ej_kol]
            summa = sum(vikt)
            for x in grupp:
                k = ut[id(x)][0]
                ut[id(x)] = [k, len(cols), sum(vikt[:k]) / summa * 100, vikt[k] / summa * 100]
        for x in sorted(dag_lekt, key=lambda y: _min(y.get("start"))):
            st, sl = _min(x.get("start")), _min(x.get("slut")) or _min(x.get("start")) + 40
            if grupp and st >= slut:
                stang()
                grupp, slut = [], -1
            grupp.append(x)
            slut = max(slut, sl)
        if grupp:
            stang()
        return ut

    plats = {}
    for d in range(5):
        plats.update(kolumner_for([x for x in lekt if int(x["dag"]) == d and _min(x.get("start")) is not None]))

    def block(x) -> str:
        st = _min(x.get("start"))
        sl = _min(x.get("slut")) or st + 40
        _k, n, vp, bp = plats.get(id(x), (0, 1, 0, 100))
        h = (sl - st) * px
        sok = " ".join(str(x.get(k) or "") for k in ("namn", "sal", "larare", "info")) + " " + DAGAR[int(x["dag"])]
        detalj = " · ".join(e(v) for v in (f"{x.get('start')}–{x.get('slut') or ''}", x.get("sal"), x.get("larare")) if v)
        rader = [f"<b>{e(x['namn'])}</b>", f"<span>{detalj}</span>"]
        if x.get("info"):
            rader.append(f"<span><i>{e(x['info'])}</i></span>")
        return (f'<div class="l{" delad" if n > 1 else ""}{" ej" if x.get("ej") else ""}" data-sok="{e(sok.lower())}" style="--c:{_farg(x["namn"], farger)};top:{(st - fran) * px:.0f}px;height:{max(16, h - 2):.0f}px;left:calc({vp:.3f}% + 2px);width:calc({bp:.3f}% - 4px)">'
                + "".join(rader) + "</div>")

    kolumner = "".join(
        f'<div class="dag"><div class="rub"><span class="lang">{d}</span><span class="kort">{d[:3]}</span></div><div class="kol" style="height:{hojd:.0f}px">'
        + "".join(f'<i class="lin" style="top:{(t - fran) * px:.0f}px"></i>' for t in range(fran, till + 1, 60))
        + "".join(block(x) for x in lekt if int(x["dag"]) == i and _min(x.get("start")) is not None)
        + "</div></div>"
        for i, d in enumerate(DAGAR))
    axel = "".join(f'<span style="top:{(t - fran) * px:.0f}px">{t // 60:02d}:00</span>' for t in range(fran, till + 1, 60))
    utan = [x for x in lekt if _min(x.get("start")) is None]
    utan_html = ("<h3>Utan tid</h3><ul>" + "".join(f"<li>{DAGAR[int(x['dag'])]}: {e(x['namn'])} {e(x.get('sal'))}</li>" for x in utan) + "</ul>") if utan else ""
    return f"""<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titel)}</title><style>
:root{{color-scheme:light}}
body{{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:16px;color:#1d2330;background:#fff}}
h1{{font-size:22px;margin:0 0 10px}}
.verktyg{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}
.verktyg input{{flex:1;min-width:180px;padding:9px 12px;font-size:16px;border:1px solid #c9ced8;border-radius:10px}}
.verktyg .bak{{background:#eef1f6;color:#1d2330}}
.verktyg button{{padding:9px 14px;font-size:15px;border:0;border-radius:10px;background:#4f8ef7;color:#fff;cursor:pointer}}
.schema{{display:grid;grid-template-columns:44px repeat(5,minmax(0,1fr));gap:4px}}
.axel{{position:relative;margin-top:26px}}
.axel span{{position:absolute;right:4px;font-size:11px;color:#667;transform:translateY(-50%)}}
.rub{{text-align:center;font-weight:700;height:26px;line-height:26px;background:#eef1f6;border-radius:6px}}
.kort{{display:none}}
@media (max-width:600px){{.lang{{display:none}}.kort{{display:inline}}body{{margin:10px}}.schema{{grid-template-columns:34px repeat(5,minmax(0,1fr))}}}}
.kol{{position:relative;background:#f7f8fa;border-radius:6px}}
.lin{{position:absolute;left:0;right:0;border-top:1px dashed #d5d9e0}}
.l{{position:absolute;box-sizing:border-box;border-left:5px solid var(--c);background:color-mix(in srgb,var(--c) 18%,#fff);
  border-radius:6px;padding:2px 5px;font-size:12px;line-height:1.2;overflow:hidden;display:flex;flex-direction:column}}
.l span{{font-size:11px;color:#3a4150;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.l b{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.l.dim{{opacity:.15}}
.l.ej{{opacity:.35;background:repeating-linear-gradient(135deg,#fff 0 6px,#eef0f4 6px 12px);border-left-style:dashed}}
.l.ej.delad>*{{display:none}}
.l.delad span,.l.delad b{{white-space:normal;overflow-wrap:anywhere}}
#traffar{{margin:0 0 10px;padding:0;list-style:none}}
#traffar li{{padding:6px 10px;border-bottom:1px solid #eee}}
.fot{{margin-top:10px;font-size:11px;color:#889}}
@media print{{
  @page{{size:A4 landscape;margin:10mm}}
  body{{margin:0}} .verktyg,#traffar{{display:none}} .l.dim{{opacity:1}}
  .rub,.kol,.l{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
}}
</style></head><body data-hem="{e(hem)}">
<h1>🗓️ {e(titel)}</h1>
<div class="verktyg"><button class="bak" onclick="tillbaka()">← Tillbaka</button><input id="sok" type="search" placeholder="Sök ämne, sal, lärare eller dag"><button onclick="window.print()">🖨️ Skriv ut</button></div>
<ul id="traffar"></ul>
<div class="schema"><div class="axel" style="height:{hojd:.0f}px">{axel}</div>{kolumner}</div>
{utan_html}
<div class="fot">Läxspelet · digital kopia av schemat{" · randiga lektioner = andra gruppens vid delad tid" if any(x.get("ej") for x in lekt) else ""}</div>
<script>
// Tillbaka: stäng fliken om den öppnades av appen, annars backa, och sist gå till startsidan.
function tillbaka(){{
  if(window.opener&&!window.opener.closed){{window.close();}}
  const forr=location.href;
  if(history.length>1)history.back();
  setTimeout(()=>{{if(location.href===forr)location.href=document.body.dataset.hem||"/";}},400);
}}
const sok=document.getElementById("sok"),ut=document.getElementById("traffar"),L=[...document.querySelectorAll(".l")];
sok.addEventListener("input",()=>{{const t=sok.value.trim().toLowerCase();ut.innerHTML="";
  L.forEach(l=>{{const m=!t||l.dataset.sok.includes(t);l.classList.toggle("dim",!m);
    if(t&&m){{const li=document.createElement("li");li.textContent=l.closest(".dag").querySelector(".rub .lang").textContent+" · "+[...l.children].map(c=>c.textContent).join(" · ");ut.appendChild(li);}}}});
  if(t&&!ut.children.length)ut.innerHTML="<li>Inget hittades.</li>";}});
</script></body></html>"""
