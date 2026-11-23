// Demo: svarar som lärarservern, men allt ligger bara i webbläsaren.
const DEMO = __LAGE__;
const DEMO_NAMN = (id) => (DEMO.elever.find((e) => e.id === id) || {}).namn || "?";
const DEMO_TID = () => new Date().toISOString().slice(0, 16).replace("T", " ");
const DEMO_LOGG = (typ, text) => DEMO.historik.unshift({ tid: DEMO_TID(), typ, text });
const DEMO_GRUPP = (namn, med, b) => ({ id: Math.random().toString(36).slice(2, 8), namn, medlemmar: med, namn_lista: med.map(DEMO_NAMN),
  uppgift: String(b.uppgift || ""), datum: String(b.datum || ""), skapad: DEMO_TID(), aktiv: true, klara: {}, klara_namn: [] });
function demoAndra(b) {
  const d = DEMO;
  switch (b.op) {
    case "installningar":
      if (b.klass) d.klass = b.klass; if (b.larare) d.larare = b.larare;
      for (const k in d.funktioner) if (k in b) { d.inst_val[k] = !!b[k]; d.inst[k] = !!b[k] && d.behorighet.ratt.includes(k); }
      break;
    case "veckobrev":
      d.veckobrev.unshift({ id: Math.random().toString(36).slice(2), titel: b.titel || "Veckobrev", vecka: b.vecka || d.boss.vecka, skapad: DEMO_TID(), ai: b.ai || {}, fil: b.fil || null });
      DEMO_LOGG("veckobrev", `Veckobrev ${d.veckobrev[0].titel} (v.${d.veckobrev[0].vecka}).`); break;
    case "veckobrev_bort": d.veckobrev = d.veckobrev.filter((x) => x.id !== b.id); break;
    case "grupp_ny": {
      const med = (b.medlemmar || []).filter((x) => d.elever.some((e) => e.id === x));
      if (!med.length) return { fel: "Välj minst en elev." };
      const g = DEMO_GRUPP(b.namn || `Grupp ${d.grupper.length + d.gamla_grupper.length + 1}`, med, b);
      d.grupper.push(g); DEMO_LOGG("grupp", `Ny grupp ${g.namn}: ${g.namn_lista.join(", ")}. Uppgift: ${g.uppgift || "–"}`); break;
    }
    case "grupp_dela": {
      const n = Math.max(1, Math.min(20, Number(b.antal) || 2)), ids = d.elever.map((e) => e.id).sort(() => Math.random() - 0.5);
      for (let i = 0; i < n; i++) { const med = ids.filter((_, j) => j % n === i); if (med.length) { const g = DEMO_GRUPP(`Grupp ${i + 1}`, med, b); d.grupper.push(g); DEMO_LOGG("grupp", `Ny grupp ${g.namn}: ${g.namn_lista.join(", ")}. Uppgift: ${g.uppgift || "–"}`); } }
      break;
    }
    case "grupp_avsluta": {
      const g = d.grupper.find((x) => x.id === b.id); if (!g) return { fel: "Finns inte." };
      d.grupper = d.grupper.filter((x) => x !== g); g.aktiv = false; g.avslutad = DEMO_TID(); d.gamla_grupper.unshift(g);
      DEMO_LOGG("grupp", `Gruppen ${g.namn} avslutades. Klara: ${g.klara_namn.join(", ") || "ingen"}. Anteckning: ${b.anteckning || "–"}`); break;
    }
    case "anteckning": DEMO_LOGG("anteckning", String(b.text || "")); break;
    case "elev_bort": d.elever = d.elever.filter((e) => e.id !== b.id); break;
    case "klassplugg": {
      const p = Number(b.poang) || 0; d.boss.extra += p; d.boss.skada = Math.min(d.boss.hp, d.boss.skada + p); d.boss.klar = d.boss.skada >= d.boss.hp;
      DEMO_LOGG("klasslag", `Klassens plugg i klassrummet: +${p}.`); break;
    }
    case "synka": case "synka_alla":
      d.elever.forEach((e) => { if (b.op === "synka_alla" || e.id === b.id) { e.senast = DEMO_TID(); if (!e.fel) DEMO_LOGG("synk", `${e.namn} synkade.`); } }); break;
    case "material_ny": {
      const typ = ["prov", "schema", "riktlinje"].includes(b.typ) ? b.typ : "material";
      if (typ === "riktlinje" && String(b.text || "").trim().length < 3) return { fel: "Skriv riktlinjen." };
      if (typ === "riktlinje") b.titel = "Riktlinje";
      if (!String(b.titel || "").trim()) return { fel: "Skriv en rubrik." };
      if ((typ === "material" || typ === "schema") && !b.fil) return { fel: "Välj en PDF eller ett foto." };
      d.material.unshift({ id: Math.random().toString(36).slice(2, 10), typ, titel: b.titel.trim(), amne: b.amne || "", text: b.text || "", datum: b.datum || "",
        max: b.max ? Number(b.max) : null, fil: b.fil || null, till: b.till || [], resultat: {}, skapad: DEMO_TID(), fatt: [] });
      DEMO_LOGG(typ === "riktlinje" ? "anteckning" : typ, `${{ prov: "Prov", schema: "Schema", riktlinje: "Riktlinje till AI:n" }[typ] || "Studiematerial"}: ${typ === "riktlinje" ? b.text : b.titel}${b.amne ? ` (${b.amne})` : ""}`); break;
    }
    case "material_bort": d.material = d.material.filter((m) => m.id !== b.id); break;
    case "prov_resultat": {
      const m = d.material.find((x) => x.id === b.id); if (!m) return { fel: "Finns inte." };
      const r = { kommentar: b.kommentar || "" };
      if (b.poang !== "" && b.poang != null) { const po = Number(b.poang); if (!m.max || po < 0 || po > m.max) return { fel: `Poängen måste vara mellan 0 och ${m.max}.` }; r.poang = po; }
      else if (["A", "B", "C", "D", "E", "F"].includes(String(b.betyg || "").toUpperCase())) r.betyg = b.betyg.toUpperCase();
      else return { fel: "Skriv poäng eller ett betyg (A–F)." };
      r.ver = (m.resultat[b.elev]?.ver ?? -1) + 1; m.resultat[b.elev] = r;
      m.fatt = m.fatt.filter((n) => n !== DEMO_NAMN(b.elev));
      DEMO_LOGG("prov", `Provresultat ${m.titel}, ${DEMO_NAMN(b.elev)}: ${"poang" in r ? `${r.poang} av ${m.max}` : `betyg ${r.betyg}`}`); break;
    }
    case "skola_last": if (d.skola) { d.skola.meddelanden.forEach((m) => (m.last = true)); d.skola.olasta = 0; } break;
    case "skola_meddelande": if (!String(b.text || "").trim()) return { fel: "Skriv ett meddelande." };
      d.skola.meddelanden.unshift({ id: Math.random().toString(36).slice(2), fran: "du", namn: d.larare, till: b.till || null, till_namn: (d.skola.medlemmar.find((m) => m.id === b.till) || {}).namn, text: b.text, tid: DEMO_TID(), egen: true, last: true }); break;
    case "anteckning_ny": { const e = d.elever.find((x) => x.id === b.elev); if (!e || !String(b.text || "").trim()) return { fel: "Skriv en anteckning." };
      (e.anteckningar = e.anteckningar || []).unshift({ id: Math.random().toString(36).slice(2), amne: b.amne || "", text: b.text, larare: d.larare, tid: DEMO_TID(), egen: true }); break; }
    case "anteckning_bort": d.elever.forEach((e) => (e.anteckningar = (e.anteckningar || []).filter((a) => a.id !== b.id))); break;
    case "rektor_satt": case "rektor_aterstall": {
      const r = d.skola.rektor, R = d.behorighet.rattigheter, jag = b.vem === d.larar_id;
      const ratt = b.op === "rektor_aterstall" ? r.standard : (b.ratt || []).filter((k) => R[k]);
      const niva = Math.max(0, ...ratt.map((k) => R[k][0]));
      if (b.op === "rektor_satt" && niva >= 1 && !String(b.motivering || "").trim()) return { fel: "Skriv vad beslutet bygger på, t.ex. dataskyddsombudets bedömning eller ett diarienummer." };
      const namn = b.vem === "standard" ? "Alla lärare (standard)" : jag ? d.larare : (d.skola.medlemmar.find((m) => m.id === b.vem) || {}).namn;
      if (b.vem === "standard") { r.standard = ratt; d.skola.medlemmar.forEach((m) => { if (!m.eget) m.ratt = ratt; }); if (!r.mina_eget) { r.jag_ratt = ratt; d.behorighet.ratt = ratt; } }
      else if (jag) { r.jag_ratt = ratt; r.mina_eget = b.op === "rektor_satt"; d.behorighet.ratt = ratt; }
      else { const m = d.skola.medlemmar.find((x) => x.id === b.vem); m.ratt = ratt; m.eget = b.op === "rektor_satt"; }
      d.behorighet.niva = Math.max(0, ...d.behorighet.ratt.map((k) => R[k][0]));
      const text = b.op === "rektor_aterstall" ? `${namn}: följer standarden igen.` : `${namn}: nivå ${niva} (${ratt.map((k) => R[k][1]).join(", ") || "inget"}).${b.motivering ? " Grund: " + b.motivering : ""}`;
      r.beslut.unshift({ tid: DEMO_TID(), av: d.larare, text }); DEMO_LOGG("behorighet", text); break;
    }
    case "rektor_mentor": {
      const lista = [...new Set(String(b.klasser || "").split(/[,;/]/).map((x) => x.trim().toUpperCase()).filter(Boolean))];
      const vem = b.vem === d.larar_id ? d.larar_id : b.vem, namn = vem === d.larar_id ? d.larare : (d.skola.medlemmar.find((m) => m.id === vem) || {}).namn;
      if (lista.length) d.skola.mentorer[vem] = lista; else delete d.skola.mentorer[vem];
      if (vem === d.larar_id) d.skola.min_roll = lista.length ? { ...d.skola.min_roll, roll: "mentor", klasser: lista, text: `Mentor för ${lista.join(", ")} (beslut av rektorn ${d.larare}).` }
        : { roll: null, intyg: true, text: "Ingen roll än: rektorn kan göra dig till mentor, eller en mentor godkänna dig som ämneslärare för sin klass." };
      const text = `${namn}: ${lista.length ? `mentor för ${lista.join(", ")}.` : "inte mentor för någon klass."}`;
      d.skola.rektor.beslut.unshift({ tid: DEMO_TID(), av: d.larare, text }); DEMO_LOGG("behorighet", text); break;
    }
    case "mentor_godkann": {
      const m = d.skola.medlemmar.find((x) => x.id === b.vem); if (!m) return { fel: "Kollegan finns inte." };
      const amnen = String(b.amnen || "").split(/[,/]/).map((x) => x.trim()).filter(Boolean);
      d.skola.godkanda = d.skola.godkanda.filter((g) => !(g.lid === b.vem && g.klass === b.klass));
      if (amnen.length) d.skola.godkanda.push({ lid: b.vem, klass: b.klass, amnen, elever: b.elever, namn: m.namn });
      DEMO_LOGG("behorighet", amnen.length ? `Godkände ${m.namn} som ämneslärare i ${amnen.join(", ")} för ${b.klass}.` : `Tog bort ${m.namn} som ämneslärare för ${b.klass}.`); break;
    }
    case "rektor_overlat": return { fel: "I demon går det inte att lämna över rektorsrollen." };
    case "regler_ok": d.regler_last = true; break;
    case "radera_klass": return { fel: "I demon raderas inget." };
    case "radera_dolda": d.behorighet.dolda = { anteckningar: 0, prov: 0, historik: 0, summa: 0 }; break;
    case "elev_lank": return { fel: "I demon finns inga riktiga familjer att lägga till." };
    case "skola_ny": case "skola_ga_med": case "skola_lamna": case "skola_kod": case "skola_synka": case "rektor_bli":
      return { fel: "I demon är skolan påhittad och går inte att ändra." };
    default: return { fel: "Okänd åtgärd." };
  }
  return null;
}
const DEMO_FILER = {};
document.addEventListener("click", (ev) => {
  const a = ev.target.closest('a[href^="/api/fil/"]');
  if (!a) return;
  ev.preventDefault();
  const url = DEMO_FILER[a.getAttribute("href").slice(9)];
  if (url) window.open(url, "_blank"); else alert("Den här filen finns bara i demon som exempel.");
});
window.fetch = async (url, opt) => {
  if (String(url).endsWith("/api/fil")) {
    const f = opt.body.get("fil");
    if (f.size > 8 * 1024 * 1024) return { ok: false, json: async () => ({ fel: "Filen är för stor (max 8 MB)." }) };
    const namn = Math.random().toString(16).slice(2) + (f.type === "application/pdf" ? ".pdf" : ".jpg");
    DEMO_FILER[namn] = URL.createObjectURL(f);
    return { ok: true, json: async () => ({ namn, mime: f.type, orig: f.name, storlek: f.size }) };
  }
  let fel = null;
  if (String(url).includes("/api/andra")) fel = demoAndra(JSON.parse(opt.body));
  const svar = fel || JSON.parse(JSON.stringify(DEMO));
  return { ok: !fel, json: async () => svar };
};
