// Skolan – panel i Home Assistant.
// Varje barn har egna ämnen med läxböcker (foton/PDF) och glosor som man kan öva på.

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const norm = (s) =>
  String(s ?? "")
    .toLowerCase()
    .replace(/[.,!?;:"'()¿¡]/g, "")
    .replace(/\s+/g, " ")
    .trim();

// "springa / löpa" eller "springa, löpa" = flera rätta svar.
const answers = (s) => String(s ?? "").split(/[\/,;]| eller /).map(norm).filter(Boolean);

// Delar ett ämne kan ha. Väljs när ämnet skapas och kan ändras under ✏️ Redigera ämnet.
const DELAR = [
  { id: "bocker", ikon: "📚", namn: "Böcker", besk: "Foton eller PDF av skolboken, e-böcker" },
  { id: "glosor", ikon: "🗣️", namn: "Glosor", besk: "Ord på två språk att öva och få förhör på" },
  { id: "formler", ikon: "📐", namn: "Formler", besk: "Formler och ekvationer, t.ex. v = s / t" },
  { id: "begrepp", ikon: "💡", namn: "Begrepp", besk: "Ord med förklaring, t.ex. fotosyntes" },
  { id: "uppgifter", ikon: "✅", namn: "Uppgifter", besk: "Att göra, t.ex. räkna s. 34 uppg. 1–10" },
  { id: "anteckningar", ikon: "🗒️", namn: "Anteckningar", besk: "Fri text att komma ihåg" },
];
const delarFor = (a) => (Array.isArray(a?.delar) ? DELAR.map((d) => d.id).filter((id) => a.delar.includes(id)) : ["bocker", "glosor"]);
// Förslag utifrån ämnets namn. Går alltid att ändra.
const forslagDelar = (namn) => {
  const n = norm(namn);
  const ord = n.split(/[\s\/&-]+/);
  const har = (...x) => x.some((o) => n.includes(o));
  if (har("matte", "matematik", "math")) return ["bocker", "formler", "uppgifter"];
  if (har("fysik", "kemi", "teknik")) return ["bocker", "formler", "begrepp", "uppgifter"];
  if (ord.includes("no") || har("biologi", "natur")) return ["bocker", "begrepp", "uppgifter"];
  if (ord.includes("so") || har("historia", "geografi", "samhäll", "religion")) return ["bocker", "begrepp", "anteckningar"];
  if (har("engelska", "spanska", "tyska", "franska", "svenska", "språk", "english", "moderna", "italienska", "kinesiska", "arabiska", "norska", "finska"))
    return ["bocker", "glosor"];
  return ["bocker", "uppgifter"];
};
// Listor som övas som glosor: vanliga glosor, formler och begrepp.
const LISTTYP = {
  glosor: { del: "glosor", ikon: "📝", ny: "＋ Nya glosor", en: "ord", fler: "ord", sprak: ["", "Svenska"], plats: ["ord", "översättning"],
    titel: ["Nya glosor", "Ändra glosor"], bort: "Ta bort glosorna?", knapp: "Ta bort glosorna", namn: "t.ex. Kapitel 3" },
  formler: { del: "formler", ikon: "📐", ny: "＋ Nya formler", en: "formel", fler: "formler", sprak: ["Namn", "Formel"], plats: ["t.ex. Hastighet", "t.ex. v = s / t"],
    titel: ["Nya formler", "Ändra formler"], bort: "Ta bort formlerna?", knapp: "Ta bort formlerna", namn: "t.ex. Rörelse" },
  begrepp: { del: "begrepp", ikon: "💡", ny: "＋ Nya begrepp", en: "begrepp", fler: "begrepp", sprak: ["Begrepp", "Förklaring"], plats: ["t.ex. Fotosyntes", "t.ex. växter gör socker av solljus"],
    titel: ["Nya begrepp", "Ändra begrepp"], bort: "Ta bort begreppen?", knapp: "Ta bort begreppen", namn: "t.ex. Kapitel 2 Cellen" },
};
const gTyp = (g) => (LISTTYP[g?.typ] ? g.typ : "glosor");
// Formler jämförs utan mellanslag och gångertecken: "F = m · a" är samma som "F=ma".
const formelNorm = (s) =>
  String(s ?? "").toLowerCase().replace(/²/g, "^2").replace(/³/g, "^3").replace(/−/g, "-").replace(/÷/g, "/").replace(/,/g, ".")
    .replace(/[\s·×*⋅]/g, "").replace(/\.$/, "");
const amneRad = (a) => {
  const d = delarFor(a);
  const n = (k, en, fler) => `${k} ${k === 1 ? en : fler}`;
  const lista = (typ) => (a.glosor || []).filter((g) => gTyp(g) === typ).length;
  const delar = [];
  if (d.includes("bocker")) delar.push(n(a.bocker.length, "bok", "böcker"));
  if (d.includes("glosor")) delar.push(n(lista("glosor"), "glosläxa", "glosläxor"));
  if (d.includes("formler")) delar.push(n(lista("formler"), "formellista", "formellistor"));
  if (d.includes("begrepp")) delar.push(n(lista("begrepp"), "begreppslista", "begreppslistor"));
  if (d.includes("uppgifter")) { const k = (a.uppgifter || []).filter((u) => !u.klar).length; delar.push(k ? n(k, "uppgift kvar", "uppgifter kvar") : "inga uppgifter kvar"); }
  return delar.slice(0, 3).join(" · ");
};

// Stavningsjämförelse bokstav för bokstav (Levenshtein-uppställning).
// Ger delar av rätt svar: ok = barnet skrev rätt bokstav, fel = fel/saknad bokstav,
// samt antal bokstäver för mycket.
const stavning = (skrev, ratt) => {
  const a = [...String(skrev).trim().toLowerCase()];
  const b = [...String(ratt).trim()];
  const bl = b.map((c) => c.toLowerCase());
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === bl[j - 1] ? 0 : 1));
  const delar = [];
  let extra = 0;
  let i = a.length, j = b.length;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && d[i][j] === d[i - 1][j - 1] + (a[i - 1] === bl[j - 1] ? 0 : 1)) {
      delar.unshift({ c: b[j - 1], ok: a[i - 1] === bl[j - 1] });
      i--; j--;
    } else if (j > 0 && d[i][j] === d[i][j - 1] + 1) {
      delar.unshift({ c: b[j - 1], ok: false });
      j--;
    } else {
      extra++;
      i--;
    }
  }
  return { delar, extra, avstand: d[a.length][b.length] };
};

// Det rätta svaret (av flera möjliga) som ligger närmast det barnet skrev.
const narmast = (skrev, svar) => {
  const alt = String(svar).split(/\s*(?:[\/,;]| eller )\s*/).filter(Boolean);
  return [String(svar), ...alt]
    .map((x) => ({ x, ...stavning(skrev, x) }))
    .sort((p, q) => p.avstand - q.avstand)[0];
};

const SPRAK_KOD = {
  engelska: "en-GB", svenska: "sv-SE", spanska: "es-ES", tyska: "de-DE", franska: "fr-FR", italienska: "it-IT",
  norska: "nb-NO", danska: "da-DK", finska: "fi-FI", portugisiska: "pt-PT", nederländska: "nl-NL", latin: "it-IT",
};

const TYST_LJUD = "data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
let _ljud = null;

// Telefonens egen röst (reserv om molnrösten inte svarar)
const las_upp_lokalt = (text, kod, langsamt) => {
  if (!window.speechSynthesis) return false;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = kod;
  const roster = speechSynthesis.getVoices().filter((v) => v.lang.replace("_", "-").startsWith(kod.slice(0, 2)));
  const bra = (v) => /enhanced|premium|förbättrad/i.test(v.name) ? 2 : 0;
  const exakt = (v) => v.lang.replace("_", "-") === kod ? 1 : 0;
  const rost = roster.sort((a, b) => (bra(b) + exakt(b)) - (bra(a) + exakt(a)))[0];
  if (rost) u.voice = rost;
  u.rate = langsamt ? 0.45 : 0.65;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
  return true;
};

// Läser upp med Home Assistant Clouds röst. Trycker man igen på samma ord blir det långsammare.
const las_upp = (text, sprak, hass) => {
  const kod = SPRAK_KOD[String(sprak || "").toLowerCase().trim()] || "en-GB";
  const igen = las_upp.senast === text && Date.now() - las_upp.tid < 15000;
  las_upp.senast = text; las_upp.tid = Date.now();
  if (!hass) return las_upp_lokalt(text, kod, igen);
  // Lås upp ljudet direkt i klicket (krävs på iPhone), sen byts källan
  if (!_ljud) _ljud = new Audio();
  try { _ljud.pause(); _ljud.src = TYST_LJUD; _ljud.play().catch(() => {}); } catch (e) { /* ignorera */ }
  const nr = (las_upp.nr = (las_upp.nr || 0) + 1);
  hass.fetchWithAuth(`/api/skolan/uttal?text=${encodeURIComponent(text)}&sprak=${kod}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.blob(); })
    .then((b) => {
      if (nr !== las_upp.nr) return;
      if (_ljud._url) URL.revokeObjectURL(_ljud._url);
      _ljud._url = URL.createObjectURL(b);
      _ljud.src = _ljud._url;
      _ljud.preservesPitch = true; _ljud.webkitPreservesPitch = true;
      _ljud.playbackRate = igen ? 0.7 : 0.9;
      _ljud.defaultPlaybackRate = _ljud.playbackRate;
      return _ljud.play();
    })
    .catch(() => las_upp_lokalt(text, kod, igen));
  return true;
};

// Stavningsord: samma språk på båda sidor (t.ex. svenska veckans ord). Då förhörs orden genom uppläsning.
const stavLista = (g) => {
  if (g?.typ && g.typ !== "glosor") return false;
  const sp = (g?.sprak || []).map((x) => String(x || "").toLowerCase().trim());
  const par = g?.par || [];
  return (sp[0] && sp[0] === sp[1]) || (par.length > 0 && par.every((p) => !String(p[1] || "").trim() || String(p[0]).trim().toLowerCase() === String(p[1]).trim().toLowerCase()));
};

// Läser upp ordet i ett förhör utan att ordet skickas till barnets skärm.
const las_upp_forhor = (hass, barn, forhor, i, sprak) => {
  const kod = SPRAK_KOD[String(sprak || "").toLowerCase().trim()] || "sv-SE";
  const nyckel = `${forhor}#${i}`;
  const igen = las_upp_forhor.senast === nyckel && Date.now() - las_upp_forhor.tid < 15000;
  las_upp_forhor.senast = nyckel; las_upp_forhor.tid = Date.now();
  if (!_ljud) _ljud = new Audio();
  try { _ljud.pause(); _ljud.src = TYST_LJUD; _ljud.play().catch(() => {}); } catch (e) { /* ignorera */ }
  hass.fetchWithAuth(`/api/skolan/uttal?barn=${encodeURIComponent(barn)}&forhor=${encodeURIComponent(forhor)}&i=${i}&sprak=${kod}`)
    .then(async (r) => {
      if (r.ok) {
        const b = await r.blob();
        if (_ljud._url) URL.revokeObjectURL(_ljud._url);
        _ljud._url = URL.createObjectURL(b);
        _ljud.src = _ljud._url;
        _ljud.playbackRate = igen ? 0.7 : 0.9;
        _ljud.defaultPlaybackRate = _ljud.playbackRate;
        return _ljud.play();
      }
      const j = await r.json().catch(() => ({}));
      if (j.text) las_upp_lokalt(j.text, kod, igen); // ingen molnröst: telefonens röst
    })
    .catch(() => {});
};

// Ordpar som har både ord och översättning (krävs för Glosrekord)
const GS = { kombo: 5 };
const REPETERA = { dagar: 10, p: 10 }; // samma som REPETERA_DAGAR och P_REPETERA i meriter.py // glosstrid: så många rätt i rad ger dubbel skada
const spelbaraPar = (g) => (g?.par || []).filter((p) => p.length > 1 && String(p[0]).trim() && String(p[1]).trim());

// ---------- husdjuret som bild (SVG) ----------
// Utseende per art: färger, öron och särdrag
const DJUR_UTSEENDE = {
  "🐶": { kropp: "#c68642", mage: "#f3d9b1", ora: "hang", nos: "#4e342e" },
  "🐱": { kropp: "#ffa94d", mage: "#fff1dc", ora: "spets", morrhar: true, rander: true },
  "🦊": { kropp: "#f57c00", mage: "#ffffff", ora: "spets", nosvit: true },
  "🐼": { kropp: "#ffffff", mage: "#ffffff", ora: "rund", oraFarg: "#222", ogonflack: true, ben: "#222" },
  "🐉": { kropp: "#43a047", mage: "#c5e1a5", ora: "horn", taggar: "#2e7d32" },
  "🐢": { kropp: "#7cb342", mage: "#dcedc8", ora: "ingen", skal: "#6d4c41" },
  "🦄": { kropp: "#fafafa", mage: "#fce4ec", ora: "spets", horn: true, man: "#ba68c8" },
  "🐧": { kropp: "#263238", mage: "#ffffff", ora: "ingen", nabb: "#ffa000", ansiktVitt: true },
  "🐰": { kropp: "#e0e0e0", mage: "#ffffff", ora: "lang", oraInne: "#f8bbd0" },
  "🦖": { kropp: "#26a69a", mage: "#b2dfdb", ora: "ingen", taggar: "#00796b" },
  "🐻": { kropp: "#8d6e63", mage: "#d7ccc8", ora: "rund", oraFarg: "#6d4c41", nos: "#3e2723", ansiktLjust: "#bcaaa4" },
  "🐨": { kropp: "#90a4ae", mage: "#eceff1", ora: "ingen", oraStor: true, oraInne: "#eceff1", stornos: "#37474f", munNed: 10 },
  "🐷": { kropp: "#f8bbd0", mage: "#fce4ec", ora: "spets", oraInne: "#f48fb1", grisnos: "#f48fb1", munNed: 12 },
  "🐸": { kropp: "#7cb342", mage: "#dcedc8", ora: "ingen", grodogon: true },
  "🐯": { kropp: "#ff9800", mage: "#fff3e0", ora: "rund", rander: true, randSidor: true, randFarg: "#3e2723" },
  "🦁": { kropp: "#ffb74d", mage: "#fff3e0", ora: "rund", lejonman: "#e65100", nos: "#5d4037" },
  "🐭": { kropp: "#b0bec5", mage: "#eceff1", ora: "ingen", oraStor: true, oraInne: "#f8bbd0", nos: "#f06292", morrhar: true },
  "🐮": { kropp: "#fafafa", mage: "#fafafa", ora: "horn", flackar: "#3e2723", mule: "#f8bbd0", munNed: 8 },
  "🐵": { kropp: "#795548", mage: "#d7ccc8", ora: "rund", oraFarg: "#a1887f", ansiktLjust: "#ffe0b2" },
  "🐹": { kropp: "#ffcc80", mage: "#fff8e1", ora: "rund", oraInne: "#f8bbd0", nos: "#f06292", ansiktLjust: "#fff8e1" },
  "🦉": { kropp: "#8d6e63", mage: "#d7ccc8", ora: "spets", oraFarg: "#5d4037", nabb: "#ffb300", ansiktLjust: "#d7ccc8" },
  "🦝": { kropp: "#9e9e9e", mage: "#eeeeee", ora: "spets", oraInne: "#eeeeee", mask: "#37474f", nos: "#212121", rander: true, randFarg: "#616161" },
  // ---- exklusiva paketdjur ----
  "🐲": { kropp: "#ffc107", mage: "#fff8e1", ora: "horn", taggar: "#ff8f00", lejonman: null },
  "⛄": { ansikte: [100, 74, 30], topp: 42, form: () =>
    `<circle cx="100" cy="146" r="42" fill="#fff" stroke="#b0bec5" stroke-width="3"/>
     <circle cx="100" cy="76" r="36" fill="#fff" stroke="#b0bec5" stroke-width="3"/>
     <path d="M66 104 q34 14 68 0 l-4 12 q-30 10 -60 0 z" fill="#e53935"/><path d="M126 106 l8 26 l-12 -4 z" fill="#c62828"/>
     <circle cx="100" cy="134" r="4" fill="#37474f"/><circle cx="100" cy="150" r="4" fill="#37474f"/><circle cx="100" cy="166" r="4" fill="#37474f"/>
     <path d="M60 136 l-30 -20 M140 136 l30 -20" stroke="#6d4c41" stroke-width="5" stroke-linecap="round"/>
     <path d="M100 84 l20 4 l-20 4 z" fill="#ff9800"/>` },
  "🎃": { ansikte: [100, 120, 36], topp: 64, form: () =>
    `<path d="M96 66 q-2 -18 10 -24" stroke="#33691e" stroke-width="8" fill="none" stroke-linecap="round"/>
     <ellipse cx="72" cy="124" rx="34" ry="54" fill="#f57c00"/><ellipse cx="128" cy="124" rx="34" ry="54" fill="#f57c00"/>
     <ellipse cx="100" cy="124" rx="38" ry="58" fill="#ff9800" stroke="#e65100" stroke-width="3"/>
     <path d="M100 70 v108" stroke="#e65100" stroke-width="2" opacity=".5"/>` },
  "🐣": { ansikte: [100, 92, 34], topp: 52, form: () =>
    `<circle cx="100" cy="100" r="46" fill="#ffeb3b" stroke="#fbc02d" stroke-width="3"/>
     <path d="M88 50 q6 -12 12 0 q6 -12 12 0" fill="#ffeb3b" stroke="#fbc02d" stroke-width="2"/>
     <path d="M46 130 l12 -10 l12 10 l12 -10 l12 10 l12 -10 l12 10 l12 -10 l12 10 l12 -10 l8 8 C154 180 46 180 46 130 Z" fill="#fff8e1" stroke="#d7ccc8" stroke-width="3"/>` },
  "🍓": { ansikte: [100, 112, 32], topp: 58, form: () =>
    `<path d="M100 186 C50 160 36 110 52 84 C66 62 134 62 148 84 C164 110 150 160 100 186 Z" fill="#e53935" stroke="#b71c1c" stroke-width="3"/>
     <path d="M66 70 l14 10 l8 -18 l12 16 l12 -16 l8 18 l14 -10 l-6 20 h-56 z" fill="#43a047"/>
     <g fill="#ffeb3b"><ellipse cx="68" cy="118" rx="2.5" ry="4"/><ellipse cx="132" cy="114" rx="2.5" ry="4"/><ellipse cx="80" cy="152" rx="2.5" ry="4"/><ellipse cx="120" cy="152" rx="2.5" ry="4"/><ellipse cx="100" cy="166" rx="2.5" ry="4"/><ellipse cx="140" cy="140" rx="2.5" ry="4"/><ellipse cx="60" cy="140" rx="2.5" ry="4"/></g>` },
  "🍭": { ansikte: [100, 80, 30], topp: 32, form: () =>
    `<rect x="95" y="124" width="10" height="62" rx="5" fill="#fff" stroke="#bdbdbd" stroke-width="2"/>
     <circle cx="100" cy="80" r="48" fill="#f06292" stroke="#c2185b" stroke-width="3"/>
     <path d="M100 80 m0 -40 a40 40 0 0 1 0 80 a30 30 0 0 1 0 -60 a20 20 0 0 1 0 40 a10 10 0 0 1 0 -20" stroke="#fff" stroke-width="6" fill="none" opacity=".75"/>` },
  "🕯️": { ansikte: [100, 120, 26], topp: 40, form: () =>
    `<ellipse cx="100" cy="182" rx="40" ry="8" fill="#ffd54f"/>
     <rect x="72" y="74" width="56" height="108" rx="10" fill="#fff8e1" stroke="#ffe082" stroke-width="3"/>
     <path d="M76 80 q6 14 0 22 M120 80 q6 18 2 26" stroke="#fff" stroke-width="5" fill="none"/>
     <path d="M100 30 C112 46 112 62 100 70 C88 62 88 46 100 30 Z" fill="#ffb300"/><path d="M100 44 C106 54 106 62 100 66 C94 62 94 54 100 44 Z" fill="#fff59d"/>` },
  "🚀": { ansikte: [100, 96, 24], topp: 30, form: () =>
    `<path d="M88 150 q12 40 24 0" fill="#ff7043"/><path d="M94 150 q6 24 12 0" fill="#ffeb3b"/>
     <path d="M72 120 l-22 34 l26 -6 z M128 120 l22 34 l-26 -6 z" fill="#e53935"/>
     <path d="M100 26 C134 50 136 110 126 150 H74 C64 110 66 50 100 26 Z" fill="#eceff1" stroke="#90a4ae" stroke-width="3"/>
     <circle cx="100" cy="96" r="28" fill="#b3e5fc" stroke="#0288d1" stroke-width="4"/>` },
  "❤️": { ansikte: [100, 104, 34], topp: 58, form: () =>
    `<path d="M100 182 C40 140 26 104 40 78 C54 52 90 54 100 78 C110 54 146 52 160 78 C174 104 160 140 100 182 Z" fill="#e53935" stroke="#b71c1c" stroke-width="3"/>
     <ellipse cx="64" cy="80" rx="10" ry="6" fill="#ef9a9a" transform="rotate(-30 64 80)"/>` },
  "👽": { ansikte: [100, 92, 40], topp: 42, form: () =>
    `<path d="M80 50 l-10 -22 M120 50 l10 -22" stroke="#7cb342" stroke-width="4"/><circle cx="70" cy="26" r="6" fill="#c6ff00"/><circle cx="130" cy="26" r="6" fill="#c6ff00"/>
     <ellipse cx="100" cy="156" rx="30" ry="26" fill="#8bc34a"/>
     <path d="M100 40 C150 40 152 96 132 124 C120 140 80 140 68 124 C48 96 50 40 100 40 Z" fill="#9ccc65" stroke="#558b2f" stroke-width="3"/>
     <ellipse cx="82" cy="180" rx="11" ry="6" fill="#558b2f"/><ellipse cx="118" cy="180" rx="11" ry="6" fill="#558b2f"/>` },
  // ---- larviga husdjur: egen form, ansikte [x, y, r] och var hatten sitter ----
  "🐙": { ansikte: [100, 96, 36], topp: 42, form: () =>
    `<path d="M50 120 q-10 40 -26 50 M72 128 q-4 40 -20 54 M100 130 v56 M128 128 q4 40 20 54 M150 120 q10 40 26 50" stroke="#ab47bc" stroke-width="16" fill="none" stroke-linecap="round"/>
     <ellipse cx="100" cy="92" rx="56" ry="54" fill="#ba68c8" stroke="#8e24aa" stroke-width="3"/>
     <circle cx="70" cy="60" r="6" fill="#e1bee7"/><circle cx="132" cy="56" r="8" fill="#e1bee7"/>` },
  // Snake: Emils lila gosorm (ihoprullad, krämvit mage, ljust nätmönster, kluven tunga)
  "🐍": { ansikte: [100, 80, 32], topp: 46, form: () =>
    `<path d="M152 172 q26 2 30 -14 q2 -6 -4 -4" stroke="#b57edc" stroke-width="13" fill="none" stroke-linecap="round"/>
     <ellipse cx="100" cy="166" rx="62" ry="17" fill="none" stroke="#f3ead2" stroke-width="26"/>
     <ellipse cx="100" cy="160" rx="62" ry="17" fill="none" stroke="#b57edc" stroke-width="24"/>
     <ellipse cx="100" cy="160" rx="62" ry="17" fill="none" stroke="#efe2fa" stroke-width="24" stroke-dasharray="3 15" opacity=".8"/>
     <ellipse cx="100" cy="142" rx="46" ry="13" fill="none" stroke="#f3ead2" stroke-width="22"/>
     <ellipse cx="100" cy="137" rx="46" ry="13" fill="none" stroke="#b57edc" stroke-width="20"/>
     <ellipse cx="100" cy="137" rx="46" ry="13" fill="none" stroke="#efe2fa" stroke-width="20" stroke-dasharray="3 13" opacity=".8"/>
     <path d="M128 136 Q142 112 112 100" stroke="#b57edc" stroke-width="30" fill="none" stroke-linecap="round"/>
     <path d="M118 140 Q130 116 104 108" stroke="#f3ead2" stroke-width="10" fill="none" stroke-linecap="round"/>
     <ellipse cx="100" cy="80" rx="50" ry="38" fill="#b57edc" stroke="#8e5bb5" stroke-width="3"/>
     <path d="M70 52 l14 -6 l14 6 l-2 12 l-14 4 l-12 -6 z M104 46 l16 -2 l12 8 l-4 12 l-14 0 l-8 -8 z M56 72 l8 -10 M140 70 l-6 -10" fill="none" stroke="#efe2fa" stroke-width="3" stroke-linejoin="round" opacity=".9"/>
     <ellipse cx="100" cy="102" rx="36" ry="15" fill="#f3ead2"/>
     <path d="M97 99 h6 l-1 13 l7 9 l-9 -4 l-1 3 l-1 -3 l-9 4 l7 -9 z" fill="#d9b8f0" stroke="#b08ad0" stroke-width="1.5"/>` },
  "🍩": { ansikte: [100, 130, 28], topp: 52, form: () =>
    `<circle cx="100" cy="116" r="64" fill="#d7a35a" stroke="#a1662f" stroke-width="3"/>
     <path d="M40 104 C44 60 156 60 160 104 q-10 14 -20 2 q-10 14 -20 2 q-10 14 -20 2 q-10 14 -20 2 q-10 14 -20 2 q-10 14 -20 2 z" fill="#f48fb1"/>
     <ellipse cx="100" cy="92" rx="16" ry="10" fill="#a1662f"/>
     <path d="M60 86 l8 -4 M128 78 l8 4 M84 70 l2 8 M140 98 l6 -6 M66 104 l6 4 M112 66 l-6 4" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
     <path d="M74 82 l6 2 M150 86 l-4 6" stroke="#4fc3f7" stroke-width="4" stroke-linecap="round"/>` },
  "🥑": { ansikte: [100, 90, 26], topp: 46, form: () =>
    `<path d="M100 36 C130 36 140 80 150 110 C166 160 136 186 100 186 C64 186 34 160 50 110 C60 80 70 36 100 36 Z" fill="#33691e"/>
     <path d="M100 46 C124 46 132 84 140 112 C152 152 128 176 100 176 C72 176 48 152 60 112 C68 84 76 46 100 46 Z" fill="#dce775"/>
     <circle cx="100" cy="140" r="24" fill="#8d6e63"/><circle cx="92" cy="132" r="6" fill="#a1887f"/>` },
  "🍄": { ansikte: [100, 146, 26], topp: 50, form: () =>
    `<path d="M74 118 h52 v56 q0 10 -10 10 h-32 q-10 0 -10 -10 z" fill="#fff3e0" stroke="#d7ccc8" stroke-width="3"/>
     <path d="M30 120 C30 50 170 50 170 120 Z" fill="#e53935" stroke="#b71c1c" stroke-width="3"/>
     <circle cx="70" cy="90" r="10" fill="#fff"/><circle cx="110" cy="74" r="12" fill="#fff"/><circle cx="146" cy="100" r="8" fill="#fff"/><circle cx="96" cy="106" r="6" fill="#fff"/>` },
  "☁️": { ansikte: [100, 122, 32], topp: 76, form: () =>
    `<g fill="#fafafa" stroke="#cfd8dc" stroke-width="3"><circle cx="64" cy="128" r="32"/><circle cx="100" cy="104" r="40"/><circle cx="140" cy="126" r="34"/><rect x="40" y="128" width="124" height="34" rx="17"/></g>
     <path d="M70 172 v10 M100 172 v14 M130 172 v10" stroke="#4fc3f7" stroke-width="4" stroke-linecap="round"/>` },
  "🦷": { ansikte: [100, 98, 30], topp: 56, form: () =>
    `<path d="M56 60 C56 40 84 40 100 50 C116 40 144 40 144 60 C146 96 138 120 132 150 C128 172 120 184 114 184 C106 184 106 150 100 150 C94 150 94 184 86 184 C80 184 72 172 68 150 C62 120 54 96 56 60 Z" fill="#fff" stroke="#b0bec5" stroke-width="3"/>
     <path d="M118 62 q10 6 10 18" stroke="#e3f2fd" stroke-width="6" fill="none" stroke-linecap="round"/>` },
  "🥔": { ansikte: [100, 122, 34], topp: 76, form: () =>
    `<path d="M42 130 C34 90 70 72 104 74 C146 76 170 100 164 136 C158 172 120 184 92 182 C60 180 46 160 42 130 Z" fill="#c8a165" stroke="#8d6e3a" stroke-width="3"/>
     <circle cx="62" cy="112" r="3" fill="#8d6e3a"/><circle cx="148" cy="118" r="3" fill="#8d6e3a"/><circle cx="130" cy="164" r="3" fill="#8d6e3a"/><circle cx="70" cy="158" r="3" fill="#8d6e3a"/>` },
  "👻": { ansikte: [100, 96, 34], topp: 44, form: () =>
    `<path d="M48 186 V96 C48 30 152 30 152 96 V186 l-17 -14 l-17 14 l-18 -14 l-18 14 l-17 -14 z" fill="#f5f5f5" stroke="#cfd8dc" stroke-width="3" opacity=".95"/>
     <path d="M48 120 q-16 4 -20 -10 M152 120 q16 4 20 -10" stroke="#cfd8dc" stroke-width="10" fill="none" stroke-linecap="round"/>` },
  "🤖": { ansikte: [100, 88, 30], topp: 46, form: () =>
    `<line x1="100" y1="44" x2="100" y2="28" stroke="#78909c" stroke-width="4"/><circle cx="100" cy="24" r="7" fill="#ef5350"/>
     <rect x="56" y="44" width="88" height="78" rx="16" fill="#b0bec5" stroke="#607d8b" stroke-width="3"/>
     <rect x="64" y="56" width="72" height="56" rx="10" fill="#e0f7fa"/>
     <rect x="46" y="70" width="10" height="24" rx="4" fill="#78909c"/><rect x="144" y="70" width="10" height="24" rx="4" fill="#78909c"/>
     <rect x="68" y="126" width="64" height="50" rx="10" fill="#90a4ae" stroke="#607d8b" stroke-width="3"/>
     <circle cx="88" cy="146" r="6" fill="#66bb6a"/><circle cx="112" cy="146" r="6" fill="#ffca28"/>
     <rect x="72" y="176" width="18" height="10" rx="3" fill="#607d8b"/><rect x="110" y="176" width="18" height="10" rx="3" fill="#607d8b"/>` },
  "🌭": { ansikte: [100, 148, 30], topp: 104, form: () =>
    `<rect x="34" y="122" width="132" height="52" rx="26" fill="#e0a85a" stroke="#b07a35" stroke-width="3"/>
     <rect x="24" y="100" width="152" height="34" rx="17" fill="#c0503a" stroke="#8e3020" stroke-width="3"/>
     <path d="M40 112 q10 -10 20 0 t20 0 t20 0 t20 0 t20 0 t20 0" stroke="#ffd600" stroke-width="5" fill="none" stroke-linecap="round"/>
     <ellipse cx="70" cy="180" rx="12" ry="6" fill="#b07a35"/><ellipse cx="130" cy="180" rx="12" ry="6" fill="#b07a35"/>` },
  "🍉": { ansikte: [100, 112, 34], topp: 96, form: () =>
    `<path d="M28 84 A72 72 0 0 0 172 84 Z" fill="#2e7d32"/><path d="M38 84 A62 62 0 0 0 162 84 Z" fill="#f1f8e9"/>
     <path d="M44 84 A56 56 0 0 0 156 84 Z" fill="#ef5350"/>
     <ellipse cx="66" cy="100" rx="3" ry="5" fill="#222"/><ellipse cx="134" cy="100" rx="3" ry="5" fill="#222"/><ellipse cx="80" cy="128" rx="3" ry="5" fill="#222"/><ellipse cx="122" cy="130" rx="3" ry="5" fill="#222"/>
     <ellipse cx="78" cy="168" rx="11" ry="6" fill="#2e7d32"/><ellipse cx="122" cy="168" rx="11" ry="6" fill="#2e7d32"/>` },
  "🍫": { ansikte: [100, 104, 32], topp: 46, form: () =>
    `<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -1.5;0 0" dur="2.4s" repeatCount="indefinite"/>
     <rect x="50" y="140" width="100" height="32" rx="8" fill="#e0a050" stroke="#b07a35" stroke-width="3"/>
     <path d="M62 152 h6 M82 158 h6 M104 152 h6 M126 158 h6" stroke="#c4873e" stroke-width="3" stroke-linecap="round"/>
     <g><animateTransform attributeName="transform" type="scale" values="1 1;1.02 0.97;1 1" dur="2.4s" repeatCount="indefinite" additive="sum"/>
       <rect x="56" y="64" width="88" height="80" rx="26" fill="#fffdf7" stroke="#e0dbd0" stroke-width="3"/>
       <path d="M64 76 q10 -8 22 -6" stroke="#fff" stroke-width="5" fill="none" stroke-linecap="round"/></g>
     <path d="M46 138 q8 -6 16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 2 v8 h-108 z" fill="#7b4a2e" stroke="#5d3420" stroke-width="2.5" stroke-linejoin="round"/>
     <g><animateTransform attributeName="transform" type="rotate" values="0 100 160;8 100 160;0 100 160" dur="1.2s" repeatCount="indefinite"/>
       <path d="M86 166 C80 172 70 176 66 186 C62 196 88 198 92 188 C96 178 96 170 92 166 Z" fill="#fafafa" stroke="#d7d2c8" stroke-width="3"/></g>
     <g><animateTransform attributeName="transform" type="rotate" values="0 100 160;-8 100 160;0 100 160" dur="1.2s" begin="0.6s" repeatCount="indefinite"/>
       <path d="M114 166 C120 172 130 176 134 186 C138 196 112 198 108 188 C104 178 104 170 108 166 Z" fill="#fafafa" stroke="#d7d2c8" stroke-width="3"/></g>
     <circle cx="72" cy="116" r="7" fill="#f48fb1" opacity=".75"/><circle cx="128" cy="116" r="7" fill="#f48fb1" opacity=".75"/>
     <g><animateTransform attributeName="transform" type="rotate" values="-3 100 60;2 100 60;-3 100 60" dur="2.4s" repeatCount="indefinite"/>
       <animateTransform attributeName="transform" type="translate" values="0 0;0 -4;0 0" dur="2.4s" repeatCount="indefinite" additive="sum"/>
       <path d="M42 50 Q44 38 60 38 H142 Q158 38 160 52 L158 70 Q156 76 146 76 H54 Q44 76 42 68 Z" fill="#e0a050" stroke="#b07a35" stroke-width="3"/>
       <path d="M58 48 q30 -6 84 0" stroke="#f5c27a" stroke-width="4" fill="none" stroke-linecap="round"/>
       <path d="M70 60 h5 M96 64 h5 M124 60 h5" stroke="#c4873e" stroke-width="3" stroke-linecap="round"/></g></g>` },
  "🍞": { ansikte: [100, 128, 34], topp: 72, form: () =>
    `<path d="M46 178 V96 C30 92 30 52 64 52 C76 40 124 40 136 52 C170 52 170 92 154 96 V178 Z" fill="#c68642" />
     <path d="M56 170 V100 C42 94 44 62 68 62 C80 52 120 52 132 62 C156 62 158 94 144 100 V170 Z" fill="#ffe0b2"/>
     <ellipse cx="74" cy="184" rx="12" ry="6" fill="#8d5524"/><ellipse cx="126" cy="184" rx="12" ry="6" fill="#8d5524"/>` },
  "🌵": { ansikte: [100, 104, 28], topp: 66, form: () =>
    `<path d="M70 150 h60 l-8 34 h-44 z" fill="#d84315"/><rect x="64" y="144" width="72" height="12" rx="4" fill="#bf360c"/>
     <rect x="72" y="58" width="56" height="94" rx="28" fill="#66bb6a" stroke="#388e3c" stroke-width="3"/>
     <path d="M72 110 h-16 a10 10 0 0 1 -10 -10 v-20" stroke="#66bb6a" stroke-width="16" fill="none" stroke-linecap="round"/>
     <path d="M128 120 h16 a10 10 0 0 0 10 -10 v-24" stroke="#66bb6a" stroke-width="16" fill="none" stroke-linecap="round"/>
     <path d="M80 70 l-6 -3 M120 75 l6 -3 M78 135 l-6 2 M122 138 l6 2 M84 60 l-3 -5 M116 60 l3 -5" stroke="#1b5e20" stroke-width="2"/>
     <circle cx="100" cy="56" r="7" fill="#f06292"/>` },
  "🍕": { ansikte: [100, 106, 28], topp: 66, form: () =>
    `<path d="M34 64 L166 64 L100 186 Z" fill="#ffca28" stroke="#f9a825" stroke-width="3" stroke-linejoin="round"/>
     <rect x="28" y="52" width="144" height="22" rx="11" fill="#d7a35a" stroke="#a1662f" stroke-width="3"/>
     <circle cx="56" cy="82" r="8" fill="#c62828"/><circle cx="144" cy="82" r="8" fill="#c62828"/><circle cx="100" cy="156" r="8" fill="#c62828"/>
     <path d="M78 140 q3 12 0 20" stroke="#ffca28" stroke-width="6" stroke-linecap="round"/>` },
  "🍦": { ansikte: [100, 84, 38], topp: 50, form: () =>
    `<path d="M66 108 L134 108 L100 188 Z" fill="#e0a85a" stroke="#b07a35" stroke-width="3" stroke-linejoin="round"/>
     <path d="M76 118 l40 40 M92 112 l30 30 M70 132 l40 -24 M80 150 l32 -24" stroke="#b07a35" stroke-width="2"/>
     <circle cx="100" cy="84" r="44" fill="#f8bbd0" stroke="#ec407a" stroke-width="3"/>
     <path d="M58 104 q10 12 20 0 q10 12 22 0 q10 12 22 0 q10 12 20 0" fill="#f8bbd0" stroke="#ec407a" stroke-width="3"/>
     <circle cx="100" cy="36" r="8" fill="#e53935"/>` },
  "🧦": { ansikte: [92, 92, 30], topp: 54, form: () =>
    `<path d="M62 44 H122 V130 L150 152 C166 166 152 190 132 184 L72 156 C62 150 62 140 62 132 Z" fill="#42a5f5" stroke="#1565c0" stroke-width="3" stroke-linejoin="round"/>
     <rect x="58" y="40" width="68" height="18" rx="5" fill="#fff" stroke="#1565c0" stroke-width="3"/>
     <path d="M62 120 H122 M62 136 H124" stroke="#ef5350" stroke-width="7"/>
     <circle cx="146" cy="172" r="7" fill="#ffccbc"/>` },
  "🪨": { ansikte: [100, 132, 36], topp: 100, form: () =>
    `<path d="M40 176 C26 150 40 110 70 100 C84 82 124 80 138 98 C166 104 178 150 160 176 Z" fill="#9e9e9e" stroke="#616161" stroke-width="3"/>
     <path d="M62 120 l10 6 M140 150 l-8 8 M120 108 l8 -2" stroke="#757575" stroke-width="3" stroke-linecap="round"/>` },
  "🍌": { ansikte: [86, 112, 24], topp: 70, form: () =>
    `<path d="M56 40 C38 96 56 164 120 182 C150 190 170 178 172 170 C132 160 108 120 98 44 Z" fill="#ffeb3b" stroke="#f9a825" stroke-width="3" stroke-linejoin="round"/>
     <path d="M56 34 l40 4 l-2 10 l-38 -4 z" fill="#6d4c41"/>
     <ellipse cx="90" cy="186" rx="11" ry="5" fill="#f9a825"/><ellipse cx="128" cy="190" rx="11" ry="5" fill="#f9a825"/>` },
};
// Saker som sitter på ögonen i stället för på huvudet
const PA_OGONEN = new Set(["solglas", "sol_hatt2", "dykmask"]);

const STRID_CSS = `
#skolan-strid .mot-fx { position:absolute; inset:0; pointer-events:none; }
#skolan-strid .mot-fx i { position:absolute; left:50%; top:50%; font-size:30px; font-style:normal; opacity:0; animation:motFx calc(.8s*var(--f,1)) ease-out calc((3s + var(--d))*var(--f,1)) forwards; }
@keyframes motFx { 0% { opacity:0; transform:translate(-50%,-50%) rotate(var(--v)) translateY(-150px) scale(1.4); } 30% { opacity:1; } 60% { opacity:1; transform:translate(-50%,-50%) rotate(var(--v)) translateY(0) scale(1); } 100% { opacity:0; transform:translate(-50%,-50%) rotate(var(--v)) translateY(40px) scale(.4); } }
#skolan-strid .motlak { position:absolute; left:22%; top:28%; font:900 22px system-ui; color:#a5d6a7; text-shadow:2px 2px 0 #000; opacity:0; animation:sNamn calc(1.4s*var(--f,1)) ease-out calc(2.8s*var(--f,1)) forwards; }
#skolan-strid .meteor { position:absolute; left:50%; top:50%; font-size:var(--s); opacity:0; z-index:3; filter:drop-shadow(0 0 10px #ff6d00) drop-shadow(0 0 22px #ffab00);
  animation:mFall calc(.75s*var(--f,1)) cubic-bezier(.55,0,1,.45) calc(var(--d)*var(--f,1)) forwards; }
#skolan-strid .meteor.liten { filter:drop-shadow(0 0 6px #ff9100); }
#skolan-strid .nedslag { position:absolute; left:50%; top:50%; font-size:54px; opacity:0; z-index:4; animation:mSlag calc(.6s*var(--f,1)) ease-out calc(var(--d)*var(--f,1)) forwards; }
#skolan-strid .meteor-himmel { position:absolute; inset:-60vh -60vw; background:radial-gradient(ellipse at 30% 0%, rgba(255,109,0,.45), transparent 60%); opacity:0; animation:mHimmel calc(2.4s*var(--f,1)) ease-in-out forwards; pointer-events:none; }
#skolan-strid .meteor-antal { position:absolute; left:50%; top:-60px; transform:translateX(-50%); font:900 28px system-ui; color:#ffd180; text-shadow:0 0 12px #ff6d00; opacity:0; animation:mAntal calc(1.6s*var(--f,1)) ease-out calc(.4s*var(--f,1)) forwards; white-space:nowrap; }
#skolan-strid.strid:has(.meteor) .scen { animation:mSkak calc(1.8s*var(--f,1)) linear calc(.6s*var(--f,1)); }
@keyframes mFall { 0% { opacity:0; transform:translate(calc(var(--x) - 260px), calc(var(--y) - 340px)) rotate(-35deg) scale(.6); } 15% { opacity:1; } 100% { opacity:1; transform:translate(var(--x), var(--y)) rotate(-35deg) scale(1.1); } }
@keyframes mSlag { 0% { opacity:0; transform:translate(var(--x), var(--y)) scale(.2); } 25% { opacity:1; transform:translate(var(--x), var(--y)) scale(1.5); } 100% { opacity:0; transform:translate(var(--x), var(--y)) scale(2.2); } }
@keyframes mHimmel { 0% { opacity:0; } 25%,75% { opacity:1; } 100% { opacity:0; } }
@keyframes mAntal { 0% { opacity:0; transform:translateX(-50%) scale(.4); } 30% { opacity:1; transform:translateX(-50%) scale(1.25); } 80% { opacity:1; transform:translateX(-50%) scale(1); } 100% { opacity:0; } }
@keyframes mSkak { 0%,100% { transform:none; } 10% { transform:translate(-8px,5px); } 20% { transform:translate(7px,-6px); } 30% { transform:translate(-6px,-3px); } 40% { transform:translate(6px,4px); } 50% { transform:translate(-5px,3px); } 60% { transform:translate(4px,-4px); } 70% { transform:translate(-3px,2px); } 80% { transform:translate(2px,-2px); } }
#skolan-strid { --f:1; position:fixed; inset:0; z-index:99999; overflow:hidden; font-family:system-ui,sans-serif; color:#fff; cursor:pointer; user-select:none; animation:sIn calc(.25s*var(--f)) ease-out; }
#skolan-strid.lugn { --f:.5; }
#skolan-strid.ut { animation:sUt .35s ease-in forwards; }
#skolan-strid * { box-sizing:border-box; }
#skolan-strid .scen { position:absolute; inset:0; background:radial-gradient(ellipse at 50% 35%, color-mix(in srgb, var(--varld) 55%, #000) 0%, #07071a 75%); }
#skolan-strid .mark { position:absolute; left:-30%; right:-30%; bottom:0; height:62%; background:linear-gradient(color-mix(in srgb, var(--varld) 35%, #000), #050510); transform:perspective(500px) rotateX(48deg); transform-origin:bottom;
  background-image:repeating-linear-gradient(90deg, rgba(255,255,255,.06) 0 2px, transparent 2px 60px), linear-gradient(color-mix(in srgb, var(--varld) 35%, #000), #050510); }
#skolan-strid .ridaa { position:absolute; inset:0; z-index:5; display:flex; flex-direction:column; pointer-events:none; }
#skolan-strid .ridaa b { flex:1; background:#fff; animation:sRidaa calc(.45s*var(--f)) ease-in forwards; animation-delay:calc(var(--i)*.03s*var(--f)); }
#skolan-strid .ridaa b:nth-child(odd) { --dir:-1; } #skolan-strid .ridaa b:nth-child(even) { --dir:1; }
.strid .ruta, .strid .namnruta { background:linear-gradient(#2a3fb8, #0b1660); border:3px solid #e8eaf6; border-radius:8px; box-shadow:0 0 0 2px #0b1660, 0 6px 18px rgba(0,0,0,.6); text-shadow:2px 2px 0 #000; }
#skolan-strid .namnruta { position:absolute; top:6%; left:50%; transform:translateX(-50%); padding:8px 22px; font-size:20px; font-weight:800; white-space:nowrap; opacity:0; animation:sNamn calc(2.4s*var(--f)) ease-out forwards; animation-delay:calc(.45s*var(--f)); }
#skolan-strid .hpbar.liv div { background:linear-gradient(#b9f6ca, #00c853); }
#skolan-strid .hjalte .kropp { width:100%; height:100%; }
#skolan-strid.mot .figur { animation:sFiendeIdle 2s ease-in-out infinite, sTraff calc(.55s*var(--f)) ease-out calc(1.7s*var(--f)), sBossAnfall calc(.6s*var(--f)) ease-in-out calc(2.85s*var(--f)); }
#skolan-strid.mot:not(.miss) .hjalte .kropp { animation:sDjurTraff calc(.5s*var(--f)) ease-out calc(3.15s*var(--f)); }
#skolan-strid.mot.miss .hjalte .kropp { animation:sUndan calc(.5s*var(--f)) ease-out calc(3.05s*var(--f)); }
#skolan-strid.ko .hjalte .kropp { animation:sDjurTraff calc(.5s*var(--f)) ease-out calc(3.15s*var(--f)), sKo calc(.6s*var(--f)) ease-in calc(3.8s*var(--f)) forwards; }
#skolan-strid .motal { top:-30%; font-size:38px; }
#skolan-strid .motal span { color:#ff5252; animation-delay:calc(3.2s*var(--f) + var(--i)*.05s); }
#skolan-strid.miss .motal span { color:#e0e0e0; font-size:30px; }
#skolan-strid .motnamn, #skolan-strid .kotext { position:absolute; left:50%; transform:translateX(-50%); white-space:nowrap; font-weight:800; text-shadow:2px 2px 0 #000; opacity:0; }
#skolan-strid .motnamn { top:calc(6% + 52px); font-size:16px; color:#ff8a80; animation:sNamn calc(1.4s*var(--f)) ease-out calc(2.7s*var(--f)) forwards; }
#skolan-strid .kotext { top:24%; font-size:24px; text-align:center; color:#ffccbc; animation:sSeger calc(.6s*var(--f)) ease-out calc(4.3s*var(--f)) forwards; }
#skolan-strid .kotext small { display:block; font-size:15px; color:#fff; margin-top:4px; }
#skolan-strid.mot .namnruta { animation-duration:calc(2.1s*var(--f)); }
@keyframes sBossAnfall { 0%,100% { transform:none; } 45% { transform:translateX(16vw) scale(1.15); } 60% { transform:translateX(18vw) scale(1.1) rotate(8deg); } }
@keyframes sDjurTraff { 0% { filter:brightness(3) saturate(0); transform:translateX(12px); } 30% { transform:translateX(-8px); filter:none; } 50% { filter:brightness(2) hue-rotate(-40deg); transform:translateX(6px); } 100% { transform:none; filter:none; } }
@keyframes sUndan { 40% { transform:translate(30px,-26px) rotate(12deg); } 100% { transform:none; } }
@keyframes sKo { to { transform:rotate(80deg) translate(20px,10px); filter:grayscale(1) brightness(.7); } }
#skolan-strid.fortsatt .ridaa, #skolan-strid.idle .ridaa { display:none; }
#skolan-strid.fortsatt, #skolan-strid.idle { animation:none; }
#skolan-strid.idle .namnruta, #skolan-strid.idle .tal, #skolan-strid.idle .hjalte, #skolan-strid.idle .hjalte .kropp { animation:none !important; opacity:0; }
#skolan-strid.idle .hjalte, #skolan-strid.idle .hjalte .kropp { opacity:1; }
#skolan-strid.idle .namnruta { display:none; }
#skolan-strid.valjer .fx, #skolan-strid.valjer .fiende .tal, #skolan-strid.valjer .motnamn, #skolan-strid.valjer .namnruta, #skolan-strid.valjer .vem { display:none; }
#skolan-strid.valjer { cursor:default; }
#skolan-strid.valjer .meny { flex-direction:column; gap:6px; }
#skolan-strid.valjer .meny .vanster { padding:6px 12px; font-size:15px; }
#skolan-strid .kommandon { display:grid; grid-template-columns:1fr 1fr; gap:0 6px; margin-top:4px; max-height:40vh; overflow-y:auto; }
#skolan-strid .kommandon .srubrik, #skolan-strid .kommandon .stom, #skolan-strid .kommandon .sfel { grid-column:1 / -1; }
#skolan-strid .kommandon [data-s-lamna] { grid-column:1 / -1; margin-top:4px; }
#skolan-strid .kommandon button { all:unset; cursor:pointer; padding:5px 6px 5px 18px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; border-radius:4px; font-size:14px; font-weight:700; color:#fff; text-shadow:2px 2px 0 #000; position:relative; }
#skolan-strid .kommandon button small { font-size:11px; opacity:.8; }
#skolan-strid .shint { grid-column:1/-1; font-size:11px; color:#ffe082; text-shadow:1px 1px 0 #000; }
#skolan-strid .ladd-rad { grid-column:1/-1; display:flex; align-items:center; gap:6px; font-size:11px; color:#fff; text-shadow:1px 1px 0 #000; margin:2px 0 4px; }
#skolan-strid .ladd-bar { flex:1; height:8px; border-radius:5px; background:rgba(255,255,255,.2); overflow:hidden; }
#skolan-strid .ladd-bar div { height:100%; background:linear-gradient(90deg,#ffca28,#ff7043); transition:width .4s; }
#skolan-strid .ladd-rad.full .ladd-bar div, #skolan-strid .kommandon button.ladd-knapp.redo { animation:sLaddPuls .7s ease-in-out infinite alternate; }
#skolan-strid .kommandon button.ladd-knapp.redo { color:#ffe082; }
@keyframes sLaddPuls { from { filter:brightness(1); } to { filter:brightness(1.6); } }
#skolan-strid .kommandon button:hover:not(:disabled), #skolan-strid .kommandon button:focus-visible { background:rgba(255,255,255,.12); }
#skolan-strid .kommandon button:hover:not(:disabled)::before { content:"▶"; position:absolute; left:3px; color:#fff59d; }
#skolan-strid .kommandon button:disabled { opacity:.4; cursor:default; }
#skolan-strid .srubrik { font-size:12px; color:#9fa8da; margin-top:4px; text-shadow:none; }
#skolan-strid .stom { font-size:12px; opacity:.7; padding-left:18px; }
#skolan-strid .sfel { font-size:12px; color:#ffab91; }
#skolan-strid.dricker .hjalte .kropp { animation:sDrick 1.2s ease-out; }
#skolan-strid .laktal { top:-30%; left:50%; font-size:34px; color:#69f0ae; animation:sSeger .4s ease-out forwards; }
@keyframes sDrick { 0% { filter:none; } 30% { filter:drop-shadow(0 0 18px #69f0ae) brightness(1.4); transform:translateY(-10px); } 100% { filter:none; transform:none; } }
#skolan-strid .djur-fiende .figur { width:min(34vw,170px); height:min(34vw,170px); }
#skolan-strid .djur-fiende .figur svg { width:100%; height:100%; }
#skolan-strid .tal.jagmiss span { color:#e0e0e0; font-size:32px; }
#skolan-strid .vem { position:absolute; top:calc(6% + 52px); left:50%; transform:translateX(-50%); font-size:14px; font-weight:700; background:rgba(0,0,0,.45); padding:3px 12px; border-radius:12px; white-space:nowrap; }
#skolan-strid .fiende { position:absolute; left:4%; top:30%; width:44%; height:40%; display:flex; align-items:center; justify-content:center; }
#skolan-strid .figur { font-size:min(28vw,150px); filter:drop-shadow(0 10px 8px rgba(0,0,0,.6)); animation:sFiendeIdle 2s ease-in-out infinite, sTraff calc(.55s*var(--f)) ease-out calc(1.7s*var(--f)); }
#skolan-strid.seger .figur { animation:sFiendeIdle 2s ease-in-out infinite, sTraff calc(.55s*var(--f)) ease-out calc(1.7s*var(--f)), sDo calc(1s*var(--f)) ease-in calc(2.8s*var(--f)) forwards; }
#skolan-strid .skold-ikon { position:absolute; font-size:min(9vw,44px); z-index:3; filter:drop-shadow(0 3px 3px rgba(0,0,0,.6)); }
#skolan-strid .skold-ikon.hj { right:4%; top:58%; }
#skolan-strid .skold-ikon.fi { left:30%; top:30%; }
#skolan-strid .skyddtext { position:absolute; z-index:4; padding:4px 10px; border-radius:10px; background:rgba(0,0,0,.65); color:#80d8ff; font-weight:700; font-size:15px; opacity:0; }
#skolan-strid .skyddtext.fi { left:6%; top:24%; animation:sSkydd calc(1.6s*var(--f)) ease-out calc(1.4s*var(--f)) forwards; }
#skolan-strid .skyddtext.hj { right:4%; top:36%; animation:sSkydd calc(1.6s*var(--f)) ease-out calc(3.0s*var(--f)) forwards; }
@keyframes sSkydd { 0% { opacity:0; transform:scale(.6); } 15% { opacity:1; transform:scale(1.1); } 80% { opacity:1; transform:scale(1); } 100% { opacity:0; } }
#skolan-strid .hjalte { position:absolute; right:6%; top:42%; width:min(34vw,170px); height:min(34vw,170px); animation:sHjalte calc(2.1s*var(--f)) ease-in-out calc(.6s*var(--f)) both; }
#skolan-strid .hjalte svg { width:100%; height:100%; transform:scaleX(-1); filter:drop-shadow(0 8px 6px rgba(0,0,0,.6)); }
#skolan-strid.seger .hjalte { animation:sHjalte calc(2.1s*var(--f)) ease-in-out calc(.6s*var(--f)) both, sSegerHopp .5s ease-in-out calc(3.5s*var(--f)) infinite; }
#skolan-strid .fx { position:absolute; inset:0; pointer-events:none; }
#skolan-strid .fx > * { position:absolute; left:50%; top:50%; opacity:0; }
#skolan-strid .p { font-style:normal; font-size:30px; margin:-15px; animation-duration:calc(.9s*var(--f)); animation-delay:calc(1.05s*var(--f) + var(--d)); animation-fill-mode:forwards; }
#skolan-strid .p.upp { animation-name:pUpp; } #skolan-strid .p.virvel { animation-name:pVirvel; } #skolan-strid .p.fall { animation-name:pFall; }
#skolan-strid .p.bubbla { animation-name:pBubbla; } #skolan-strid .p.gnista { animation-name:pGnista; }
#skolan-strid .glod { width:220px; height:220px; margin:-110px; border-radius:50%; background:radial-gradient(var(--g), transparent 65%); animation:fxGlod calc(1s*var(--f)) ease-out calc(1.05s*var(--f)) forwards; }
#skolan-strid .bolt { width:70px; height:260px; margin:-230px 0 0 -35px; fill:none; stroke:#fffde7; stroke-width:7; stroke-linejoin:round; filter:drop-shadow(0 0 8px #ffeb3b) drop-shadow(0 0 18px #fff176); animation:fxBolt calc(.5s*var(--f)) steps(2) calc(1.15s*var(--f)) 2 forwards; }
#skolan-strid .blixtsken { position:fixed !important; inset:0; left:0 !important; top:0 !important; background:#fff; animation:fxSken calc(.5s*var(--f)) steps(2) calc(1.15s*var(--f)) 2; }
#skolan-strid .vag { width:420px; height:160px; margin:-60px 0 0 -40px; border-radius:50% 50% 0 0; background:linear-gradient(#b3e5fc, #0288d1 60%, transparent); filter:blur(1px); animation:fxVag calc(.9s*var(--f)) ease-in calc(1.05s*var(--f)) forwards; }
#skolan-strid .frost { width:200px; height:200px; margin:-100px; border-radius:30%; background:radial-gradient(rgba(225,245,254,.9), rgba(129,212,250,.3) 60%, transparent 70%); animation:fxFrost calc(1s*var(--f)) ease-out calc(1.5s*var(--f)) forwards; }
#skolan-strid .ring { width:40px; height:40px; margin:-20px; border-radius:50%; border:6px solid #fff59d; box-shadow:0 0 20px #ffeb3b; animation:fxRing calc(.8s*var(--f)) ease-out calc(1.1s*var(--f)) forwards; }
#skolan-strid .ring.r2 { animation-delay:calc(1.25s*var(--f)); border-color:#ff8a65; } #skolan-strid .ring.r3 { animation-delay:calc(1.4s*var(--f)); border-color:#ce93d8; }
#skolan-strid .jatte { font-size:120px; margin:-70px; animation:fxJatte calc(.8s*var(--f)) ease-out calc(1.15s*var(--f)) forwards; }
#skolan-strid.t-kraft .scen { animation:sSkak calc(.5s*var(--f)) linear calc(1.2s*var(--f)); }
#skolan-strid .tal { position:absolute; left:50%; top:8%; transform:translateX(-50%); display:flex; flex-direction:column; align-items:center; font-size:44px; font-weight:900; color:#fff; text-shadow:3px 3px 0 #000, -1px -1px 0 #000; pointer-events:none; }
#skolan-strid .tal { flex-direction:row; flex-wrap:wrap; justify-content:center; }
#skolan-strid .tal span { display:inline-block; opacity:0; animation:sSiffra calc(1.5s*var(--f)) ease-out forwards; animation-delay:calc(1.8s*var(--f) + var(--i)*.05s); }
#skolan-strid .tal.svag span { color:#ffeb3b; font-size:54px; }
#skolan-strid .tal small { flex-basis:100%; white-space:nowrap; text-align:center; font-size:15px; color:#ffab40; letter-spacing:1px; opacity:0; animation:sSiffra calc(1.5s*var(--f)) ease-out calc(1.95s*var(--f)) forwards; }
#skolan-strid .meny { position:absolute; left:3%; right:3%; bottom:4%; display:flex; gap:8px; font-size:17px; font-weight:700; animation:sMeny calc(.4s*var(--f)) ease-out calc(.3s*var(--f)) both; }
#skolan-strid .meny .vanster { flex:1.3; padding:10px 14px; }
#skolan-strid .meny .hoger { flex:1; padding:10px 14px; }
#skolan-strid .kommando { margin-top:4px; color:#fff59d; font-size:15px; animation:sBlink .6s steps(2) infinite; }
@keyframes sBlink { 50% { opacity:.55; } }
#skolan-strid .rad { display:flex; justify-content:space-between; gap:8px; }
#skolan-strid .rad span:first-child { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#skolan-strid .bosshp { position:absolute; top:-6px; left:50%; transform:translateX(-50%); width:70%; max-width:180px; height:16px; border-radius:8px; background:#300; border:2px solid #fff; box-shadow:0 2px 6px rgba(0,0,0,.6); overflow:hidden; z-index:1; }
#skolan-strid .bosshp div { height:100%; background:linear-gradient(#69f0ae, #00c853); transition:width calc(.8s*var(--f)) ease-out, background .3s; }
#skolan-strid .bosshp span { position:absolute; inset:0; text-align:center; font-size:11px; font-weight:800; line-height:12px; text-shadow:1px 1px 0 #000; }
#skolan-strid.seger .bosshp { animation:sUt .4s ease-in calc(2.8s*var(--f)) forwards; }
#skolan-strid .hpbar { margin-top:6px; height:10px; border-radius:5px; background:#300; border:2px solid #000; overflow:hidden; }
#skolan-strid .hpbar div { height:100%; background:linear-gradient(#ff8a80, #d50000); transition:width calc(.8s*var(--f)) ease-out; }
#skolan-strid .segertext { position:absolute; left:0; right:0; top:30%; text-align:center; font-size:min(16vw,84px); font-weight:900; letter-spacing:6px; color:#ffe082; text-shadow:0 0 18px #ffb300, 4px 4px 0 #000; opacity:0; display:none; }
#skolan-strid .segertext small { display:block; font-size:20px; letter-spacing:1px; color:#fff; }
#skolan-strid.seger .segertext { display:block; animation:sSeger calc(.7s*var(--f)) cubic-bezier(.2,1.6,.4,1) calc(3.4s*var(--f)) forwards; }
@keyframes sIn { from { opacity:0; } }
@keyframes sUt { to { opacity:0; transform:scale(1.05); } }
@keyframes sRidaa { 0% { transform:none; } 100% { transform:translateX(calc(var(--dir)*105%)); } }
@keyframes sNamn { 0% { opacity:0; transform:translate(-50%,-14px); } 12%,85% { opacity:1; transform:translate(-50%,0); } 100% { opacity:0; } }
@keyframes sMeny { from { transform:translateY(120%); } }
@keyframes sFiendeIdle { 50% { translate:0 -6px; } }
@keyframes sTraff { 0% { filter:brightness(4) saturate(0); transform:translateX(-14px); } 20% { transform:translateX(12px); } 40% { filter:brightness(2.5); transform:translateX(-8px); } 60% { filter:none; transform:translateX(5px); } 100% { transform:none; } }
@keyframes sDo { 0% { opacity:1; filter:sepia(1) hue-rotate(-50deg) saturate(5) brightness(1.4); clip-path:inset(0 0 0 0); } 100% { opacity:0; filter:sepia(1) hue-rotate(-50deg) saturate(5) brightness(2) blur(4px); clip-path:inset(0 0 100% 0); transform:scale(1.1,.6); } }
@keyframes sHjalte { 0% { transform:translateX(0); } 18% { transform:translateX(-18vw) scale(1.12); filter:drop-shadow(0 0 14px #fff); } 30%,70% { transform:translateX(-18vw) scale(1.12); } 85%,100% { transform:translateX(0); } }
@keyframes sSegerHopp { 50% { translate:0 -22px; } }
@keyframes pUpp { 0% { opacity:0; transform:translate(var(--x), 60px) scale(.4); } 30% { opacity:1; } 100% { opacity:0; transform:translate(var(--x), calc(var(--y) - 90px)) scale(1.5); } }
@keyframes pVirvel { 0% { opacity:0; transform:rotate(0) translateX(110px) rotate(0); } 30% { opacity:1; } 100% { opacity:0; transform:rotate(calc(var(--r) + 540deg)) translateX(8px) rotate(360deg); } }
@keyframes pFall { 0% { opacity:0; transform:translate(var(--x), -180px) rotate(0); } 25% { opacity:1; } 70% { opacity:1; transform:translate(calc(var(--x)*.4), var(--y)) rotate(var(--r)); } 100% { opacity:0; transform:translate(calc(var(--x)*.4), var(--y)) scale(1.6); } }
@keyframes pBubbla { 0% { opacity:0; transform:translate(calc(var(--x) + 80px), 60px) scale(.5); } 30% { opacity:1; } 100% { opacity:0; transform:translate(var(--x), calc(var(--y) - 60px)) scale(1.2); } }
@keyframes pGnista { 0% { opacity:0; transform:scale(0); } 40% { opacity:1; transform:translate(calc(var(--x)*1.6), calc(var(--y)*1.6)) scale(1.3); } 100% { opacity:0; transform:translate(calc(var(--x)*2.4), calc(var(--y)*2.4)) scale(.3); } }
@keyframes fxGlod { 0% { opacity:0; transform:scale(.3); } 40% { opacity:.9; } 100% { opacity:0; transform:scale(1.6); } }
@keyframes fxBolt { 0% { opacity:1; } 100% { opacity:0; } }
@keyframes fxSken { 0% { opacity:.7; } 100% { opacity:0; } }
@keyframes fxVag { 0% { opacity:0; transform:translateX(260px) scaleY(.4); } 30% { opacity:.9; } 70% { opacity:.9; transform:translateX(-120px) scaleY(1.1); } 100% { opacity:0; transform:translateX(-300px) scaleY(.6); } }
@keyframes fxFrost { 0% { opacity:0; transform:scale(.5) rotate(0); } 40% { opacity:1; } 100% { opacity:0; transform:scale(1.4) rotate(45deg); } }
@keyframes fxRing { 0% { opacity:1; transform:scale(.2); } 100% { opacity:0; transform:scale(7); } }
@keyframes fxJatte { 0% { opacity:0; transform:scale(.2) rotate(-20deg); } 30% { opacity:1; transform:scale(1.4) rotate(5deg); } 100% { opacity:0; transform:scale(2.2); } }
@keyframes sSkak { 0%,100% { transform:none; } 20% { transform:translate(-10px,6px); } 40% { transform:translate(9px,-7px); } 60% { transform:translate(-7px,-4px); } 80% { transform:translate(6px,5px); } }
@keyframes sSiffra { 0% { opacity:0; transform:translateY(0); } 8% { opacity:1; transform:translateY(-28px); } 18% { transform:translateY(0); } 26% { transform:translateY(-10px); } 34%,80% { opacity:1; transform:translateY(0); } 100% { opacity:0; } }
@keyframes sSeger { 0% { opacity:0; transform:scale(.3); } 100% { opacity:1; transform:scale(1); } }
`;

// Evolution: storleken (Stor, Jätte, Legend) och formen (efter barnets vanor) syns på husdjuret.
const EVO_FARG = { blixt: "#ffeb3b", visdom: "#b388ff", prick: "#ff5252", flit: "#69f0ae", boss: "#ff7043" };
function evoBak(steg, form) {
  const f = form?.id, farg = EVO_FARG[f] || "#fff59d";
  let s = "";
  if (steg >= 3) { // aura som pulserar, starkare ju större
    const op = { 3: 0.35, 4: 0.55, 5: 0.8 }[Math.min(5, steg)];
    s += `<defs><radialGradient id="evo-aura-${f || "x"}"><stop offset="0" stop-color="${farg}" stop-opacity=".9"/><stop offset="1" stop-color="${farg}" stop-opacity="0"/></radialGradient></defs>
      <circle cx="100" cy="125" r="${76 + steg * 4}" fill="url(#evo-aura-${f || "x"})" opacity="${op}"><animate attributeName="opacity" values="${op};${op * 0.5};${op}" dur="2.6s" repeatCount="indefinite"/></circle>`;
  }
  if (steg >= 5) { // legend: vingar
    const v = (sp) => `<path transform="${sp ? "translate(200 0) scale(-1 1)" : ""}" d="M72 128 C40 92 6 96 10 122 C22 116 26 128 18 138 C32 132 38 142 30 152 C46 146 56 150 66 148 Z" fill="#fffde7" stroke="#ffd54f" stroke-width="3"><animateTransform attributeName="transform" type="rotate" values="0 72 128;-8 72 128;0 72 128" dur="1.8s" repeatCount="indefinite" additive="sum"/></path>`;
    s += v(false) + v(true);
  }
  if (f === "boss") s += `<path d="M66 116 Q100 104 134 116 L150 184 Q125 174 100 182 Q75 174 50 184 Z" fill="#c62828" stroke="#8e0000" stroke-width="2"/><path d="M66 116 Q100 104 134 116 L132 126 Q100 116 68 126 Z" fill="#8e0000"/>`;
  if (f === "flit") s += `<g opacity=".75"><ellipse cx="60" cy="116" rx="30" ry="14" transform="rotate(-32 60 116)" fill="#e0f7fa" stroke="#4dd0e1" stroke-width="2"><animateTransform attributeName="transform" type="rotate" values="-32 60 116;-44 60 116;-32 60 116" dur=".35s" repeatCount="indefinite"/></ellipse>
    <ellipse cx="140" cy="116" rx="30" ry="14" transform="rotate(32 140 116)" fill="#e0f7fa" stroke="#4dd0e1" stroke-width="2"><animateTransform attributeName="transform" type="rotate" values="32 140 116;44 140 116;32 140 116" dur=".35s" repeatCount="indefinite"/></ellipse></g>`;
  if (f === "blixt") s += `<g stroke="#ffd600" stroke-width="5" fill="none" stroke-linejoin="round"><polyline points="30,60 44,92 32,96 48,132"/><polyline points="170,60 156,92 168,96 152,132"/>
    <animate attributeName="opacity" values="1;.2;1;1;.4;1" dur="1.4s" repeatCount="indefinite"/></g>`;
  if (f === "prick") s += `<g opacity=".35"><circle cx="100" cy="128" r="74" fill="none" stroke="#ff5252" stroke-width="6"/><circle cx="100" cy="128" r="54" fill="none" stroke="#fff" stroke-width="6"/></g>`;
  return s;
}
function evoFram(form, cx, cy, r, hatt) {
  const f = form?.id, ox = r * 0.36, oy = cy - r * 0.05;
  let s = "";
  const gr = Math.max(9, r * 0.24); // glasögonens storlek (minst så att de syns på små ansikten)
  if (f === "visdom") s += `<g fill="rgba(255,255,255,.18)" stroke="#4e342e" stroke-width="3"><circle cx="${cx - ox}" cy="${oy}" r="${gr}"/><circle cx="${cx + ox}" cy="${oy}" r="${gr}"/></g>${2 * ox > 2 * gr ? `<path d="M${cx - ox + gr} ${oy} h${2 * ox - 2 * gr}" stroke="#4e342e" stroke-width="3"/>` : ""}`;
  if (f === "prick") s += `<path d="M${cx - r * 0.95} ${cy - r * 0.42} Q${cx} ${cy - r * 0.62} ${cx + r * 0.95} ${cy - r * 0.42} L${cx + r * 0.92} ${cy - r * 0.26} Q${cx} ${cy - r * 0.46} ${cx - r * 0.92} ${cy - r * 0.26} Z" fill="#e53935"/><circle cx="${cx + r * 0.7}" cy="${cy - r * 0.4}" r="7" fill="#fff" stroke="#e53935" stroke-width="3"/><circle cx="${cx + r * 0.7}" cy="${cy - r * 0.4}" r="2.5" fill="#e53935"/>`;
  if (f === "blixt") {
    s += `<path d="M${cx - r * 0.75} ${cy + r * 0.12} l6 -4 l-2 6 l6 -3" stroke="#ffd600" stroke-width="3" fill="none"/><path d="M${cx + r * 0.6} ${cy + r * 0.12} l6 -4 l-2 6 l6 -3" stroke="#ffd600" stroke-width="3" fill="none"/>`;
    if (!hatt) s += `<path d="M${cx - 4} ${cy - r + 2} l12 -26 l-3 15 l11 -3 l-17 30 l3 -15 z" fill="#ffeb3b" stroke="#f9a825" stroke-width="2"/>`;
  }
  if (f === "flit") s += `<text x="${cx - r - 2}" y="${cy - r * 0.6}" font-size="18">✨<animate attributeName="opacity" values="1;.2;1" dur="1.2s" repeatCount="indefinite"/></text><text x="${cx + r - 8}" y="${cy - r * 0.9}" font-size="14">✨<animate attributeName="opacity" values=".2;1;.2" dur="1.2s" repeatCount="indefinite"/></text>`;
  if (f === "boss") s += `<circle cx="100" cy="120" r="6" fill="#ffd54f" stroke="#ff8f00" stroke-width="2"/>`;
  return s;
}

const TYP_TEXT = { eld: "🔥 Eld", natur: "🍃 Natur", blixt: "⚡ Blixt", vatten: "🌊 Vatten", is: "❄️ Is", kraft: "💥 Kraft" };

function ritaDjur(art, humor, steg, x = {}) {
  const u = DJUR_UTSEENDE[art] || DJUR_UTSEENDE["🐶"];
  const K = u.kropp, M = u.mage, linje = "#3e2723";
  const skala = steg === 0 ? 1 : 0.72 + steg * 0.06; // växer med storleken
  let ut = `<svg viewBox="0 0 200 200" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">`;
  if (x.deko) ut += `<text x="172" y="190" font-size="34" text-anchor="middle" opacity=".45">${x.deko}</text>`;
  ut += `<ellipse cx="100" cy="186" rx="${46 * skala}" ry="7" fill="rgba(0,0,0,.18)"/>`;
  // ansiktet (används både för ägget och djuret)
  const ansikte = (cx, cy, r, dm = 0) => {
    const ox = r * 0.36, oy = cy - r * 0.05, mY = cy + r * 0.32 + dm;
    let f = "";
    if (humor === "glad") {
      f += `<path d="M${cx - ox - 7} ${oy + 2} q7 -10 14 0 M${cx + ox - 7} ${oy + 2} q7 -10 14 0" stroke="${linje}" stroke-width="4" fill="none" stroke-linecap="round"/>`;
      f += `<path d="M${cx - 13} ${mY - 4} q13 18 26 0 z" fill="#5d1f1f"/><path d="M${cx - 6} ${mY + 4} q6 5 12 0" fill="#ef5350"/>`;
      f += `<circle cx="${cx - r * 0.6}" cy="${mY - 6}" r="7" fill="#ff8a80" opacity=".55"/><circle cx="${cx + r * 0.6}" cy="${mY - 6}" r="7" fill="#ff8a80" opacity=".55"/>`;
    } else if (humor === "nojd") {
      f += `<circle cx="${cx - ox}" cy="${oy}" r="7" fill="${linje}"/><circle cx="${cx + ox}" cy="${oy}" r="7" fill="${linje}"/>`;
      f += `<circle cx="${cx - ox + 2.5}" cy="${oy - 2.5}" r="2.5" fill="#fff"/><circle cx="${cx + ox + 2.5}" cy="${oy - 2.5}" r="2.5" fill="#fff"/>`;
      f += `<path d="M${cx - 9} ${mY - 2} q9 9 18 0" stroke="${linje}" stroke-width="3.5" fill="none" stroke-linecap="round"/>`;
    } else if (humor === "hungrig") {
      f += `<circle cx="${cx - ox}" cy="${oy + 1}" r="8" fill="${linje}"/><circle cx="${cx + ox}" cy="${oy + 1}" r="8" fill="${linje}"/>`;
      f += `<circle cx="${cx - ox + 3}" cy="${oy - 2}" r="3" fill="#fff"/><circle cx="${cx + ox + 3}" cy="${oy - 2}" r="3" fill="#fff"/>`;
      f += `<path d="M${cx - ox - 9} ${oy - 13} l14 5 M${cx + ox + 9} ${oy - 13} l-14 5" stroke="${linje}" stroke-width="3.5" stroke-linecap="round"/>`;
      f += `<ellipse cx="${cx}" cy="${mY + 2}" rx="6" ry="7" fill="#5d1f1f"/><path d="M${cx + 9} ${mY} q3 8 0 12 q-3 -4 0 -12" fill="#81d4fa"/>`;
    } else {
      f += `<path d="M${cx - ox - 8} ${oy} q8 6 16 0 M${cx + ox - 8} ${oy} q8 6 16 0" stroke="${linje}" stroke-width="4" fill="none" stroke-linecap="round"/>`;
      f += `<path d="M${cx - ox - 9} ${oy - 12} l14 -4 M${cx + ox + 9} ${oy - 12} l-14 -4" stroke="${linje}" stroke-width="3" stroke-linecap="round"/>`;
      f += `<path d="M${cx - 10} ${mY + 6} q10 -10 20 0" stroke="${linje}" stroke-width="3.5" fill="none" stroke-linecap="round"/>`;
      f += `<path class="tar" d="M${cx - ox - 2} ${oy + 6} q-5 10 0 14 q5 -4 0 -14" fill="#4fc3f7"/>`;
    }
    return f;
  };
  if (x.form) ut += `<circle cx="28" cy="28" r="20" fill="rgba(255,255,255,.75)" stroke="#ffd54f" stroke-width="3"/><text x="28" y="36" font-size="22" text-anchor="middle">${x.form.ikon}</text>`;
  ut += `<g class="kropp ${x.variant?.anim ? "variant-anim" : ""}" style="transform-origin:100px 185px;transform:scale(${skala});${x.variant ? `filter:${x.variant.filter};` : ""}">`;
  if (steg > 0) ut += evoBak(steg, x.form);
  if (steg === 0) {
    // ägget, med sprickor och ett litet ansikte
    ut += `<path d="M100 60 C140 60 152 120 150 145 C148 175 125 185 100 185 C75 185 52 175 50 145 C48 120 60 60 100 60 Z" fill="#fff8e1" stroke="#d7ccc8" stroke-width="3"/>`;
    ut += `<path d="M70 110 l10 8 l8 -10 l10 9 l9 -9 l10 8" stroke="#bcaaa4" stroke-width="3" fill="none"/>`;
    ut += `<circle cx="78" cy="140" r="6" fill="#ffcc80" opacity=".6"/><circle cx="124" cy="150" r="9" fill="#ffcc80" opacity=".6"/>`;
    ut += ansikte(100, 145, 34);
    ut += `</g></svg>`;
    return ut;
  }
  if (u.form) {
    // larvigt husdjur: egen form, samma ansikten och saker
    const [cx, cy, r] = u.ansikte;
    ut += u.form() + ansikte(cx, cy, r) + evoFram(x.form, cx, cy, r, x.hatt);
    if (x.hatt && PA_OGONEN.has(x.hatt.id)) ut += `<text x="${cx}" y="${cy + 14}" font-size="${r + 6}" text-anchor="middle">${x.hatt.ikon}</text>`;
    else if (x.hatt) ut += `<text x="${cx + 4}" y="${u.topp + 6}" font-size="50" text-anchor="middle" transform="rotate(-10 ${cx} ${u.topp})">${x.hatt.ikon}</text>`;
    else if (x.krona) ut += `<text x="${cx}" y="${u.topp + 4}" font-size="46" text-anchor="middle">👑</text>`;
    ut += `</g>`;
    if (x.kompis) ut += `<text class="kompis-svg" x="164" y="178" font-size="38" text-anchor="middle">${x.kompis.ikon}</text>`;
    if (x.eff?.partikel) [[30, 50], [170, 70], [40, 140]].forEach(([px, py], n) => (ut += `<text class="partikel p${n}" x="${px}" y="${py}" font-size="24" text-anchor="middle">${x.eff.partikel}</text>`));
    return ut + `</svg>`;
  }
  const hx = 100, hy = 98, hr = 44; // huvudet
  // svans / skal / taggar bakom kroppen
  if (u.skal) ut += `<ellipse cx="100" cy="150" rx="52" ry="34" fill="${u.skal}"/><path d="M70 140 l15 -14 h30 l15 14 l-15 14 h-30 z" fill="none" stroke="#a1887f" stroke-width="3"/>`;
  if (u.taggar) ut += `<path d="M62 70 l8 -18 l8 14 l8 -20 l8 18 l8 -22 l8 20 l8 -18 l8 16 l8 -14 l4 20 z" fill="${u.taggar}"/>`;
  if (u.man) ut += `<path d="M120 58 q30 10 22 60 q-12 -20 -22 -30 z" fill="${u.man}"/>`;
  // kropp
  ut += `<ellipse cx="100" cy="152" rx="36" ry="30" fill="${K}" stroke="rgba(0,0,0,.12)" stroke-width="2"/>`;
  ut += `<ellipse cx="100" cy="158" rx="22" ry="19" fill="${M}"/>`;
  ut += `<ellipse cx="80" cy="180" rx="13" ry="7" fill="${u.ben || K}"/><ellipse cx="120" cy="180" rx="13" ry="7" fill="${u.ben || K}"/>`;
  if (u.lejonman) ut += `<circle cx="100" cy="98" r="62" fill="${u.lejonman}"/><circle cx="100" cy="98" r="62" fill="none" stroke="#bf360c" stroke-width="6" stroke-dasharray="10 8"/>`;
  if (u.grodogon) ut += `<circle cx="78" cy="62" r="16" fill="${K}"/><circle cx="122" cy="62" r="16" fill="${K}"/>`;
  // öron
  const oF = u.oraFarg || K, oI = u.oraInne || "#ffccbc";
  if (u.oraStor) ut += `<circle cx="62" cy="62" r="24" fill="${oF}"/><circle cx="138" cy="62" r="24" fill="${oF}"/><circle cx="62" cy="62" r="13" fill="${oI}"/><circle cx="138" cy="62" r="13" fill="${oI}"/>`;
  if (u.ora === "spets") ut += `<path d="M64 80 L70 40 L92 62 Z" fill="${oF}"/><path d="M136 80 L130 40 L108 62 Z" fill="${oF}"/><path d="M70 72 L73 50 L86 63 Z" fill="${oI}"/><path d="M130 72 L127 50 L114 63 Z" fill="${oI}"/>`;
  if (u.ora === "hang") ut += `<ellipse cx="58" cy="92" rx="13" ry="28" fill="#8d5524" transform="rotate(18 58 92)"/><ellipse cx="142" cy="92" rx="13" ry="28" fill="#8d5524" transform="rotate(-18 142 92)"/>`;
  if (u.ora === "rund") ut += `<circle cx="66" cy="62" r="15" fill="${oF}"/><circle cx="134" cy="62" r="15" fill="${oF}"/>`;
  if (u.ora === "lang") ut += `<ellipse cx="80" cy="38" rx="11" ry="34" fill="${oF}"/><ellipse cx="120" cy="38" rx="11" ry="34" fill="${oF}"/><ellipse cx="80" cy="40" rx="5" ry="25" fill="${oI}"/><ellipse cx="120" cy="40" rx="5" ry="25" fill="${oI}"/>`;
  if (u.ora === "horn") ut += `<path d="M72 64 l-6 -26 l16 18 z M128 64 l6 -26 l-16 18 z" fill="#fff59d" stroke="#f9a825" stroke-width="2"/>`;
  // huvud
  ut += `<circle cx="${hx}" cy="${hy}" r="${hr}" fill="${K}" stroke="rgba(0,0,0,.12)" stroke-width="2"/>`;
  if (u.ansiktVitt) ut += `<ellipse cx="${hx}" cy="${hy + 6}" rx="32" ry="30" fill="#fff"/>`;
  if (u.nosvit) ut += `<path d="M${hx - 34} ${hy + 4} Q${hx} ${hy + 50} ${hx + 34} ${hy + 4} Q${hx} ${hy + 22} ${hx - 34} ${hy + 4}" fill="#fff"/>`;
  if (u.rander) ut += `<path d="M${hx - 10} ${hy - 42} l4 12 M${hx} ${hy - 44} v13 M${hx + 10} ${hy - 42} l-4 12" stroke="${u.randFarg || "#e8590c"}" stroke-width="4" stroke-linecap="round"/>`;
  if (u.randSidor) ut += `<path d="M${hx - 44} ${hy - 6} h14 M${hx - 43} ${hy + 8} h12 M${hx + 44} ${hy - 6} h-14 M${hx + 43} ${hy + 8} h-12" stroke="${u.randFarg}" stroke-width="5" stroke-linecap="round"/>`;
  if (u.flackar) ut += `<ellipse cx="${hx - 24}" cy="${hy - 26}" rx="12" ry="9" fill="${u.flackar}"/><ellipse cx="${hx + 30}" cy="${hy + 14}" rx="9" ry="12" fill="${u.flackar}"/><ellipse cx="118" cy="150" rx="10" ry="8" fill="${u.flackar}"/><ellipse cx="80" cy="140" rx="8" ry="6" fill="${u.flackar}"/>`;
  if (u.ansiktLjust) ut += `<ellipse cx="${hx}" cy="${hy + 8}" rx="32" ry="28" fill="${u.ansiktLjust}"/>`;
  if (u.mule) ut += `<ellipse cx="${hx}" cy="${hy + 20}" rx="26" ry="16" fill="${u.mule}"/>`;
  if (u.mask) ut += `<path d="M${hx - 40} ${hy - 10} Q${hx} ${hy - 26} ${hx + 40} ${hy - 10} L${hx + 34} ${hy + 8} Q${hx} ${hy - 4} ${hx - 34} ${hy + 8} Z" fill="${u.mask}"/>`;
  if (u.ogonflack) ut += `<ellipse cx="${hx - 16}" cy="${hy - 2}" rx="12" ry="15" fill="#222" transform="rotate(20 ${hx - 16} ${hy - 2})"/><ellipse cx="${hx + 16}" cy="${hy - 2}" rx="12" ry="15" fill="#222" transform="rotate(-20 ${hx + 16} ${hy - 2})"/>`;
  if (u.horn) ut += `<path d="M${hx - 7} ${hy - 40} L${hx} ${hy - 78} L${hx + 7} ${hy - 40} Z" fill="#ffd54f" stroke="#ffa000" stroke-width="2"/>`;
  // ansikte (pandan får vita ögon på de svarta fläckarna)
  let f = ansikte(hx, hy, hr, u.munNed || 0);
  if (u.ogonflack || u.mask) f = f.replaceAll(`fill="${linje}"`, 'fill="#fff"').replaceAll(`stroke="${linje}"`, 'stroke="#fff"');
  ut += f;
  if (u.nos) ut += `<ellipse cx="${hx}" cy="${hy + 3}" rx="6" ry="4" fill="${u.nos}"/>`;
  if (u.stornos) ut += `<ellipse cx="${hx}" cy="${hy + 8}" rx="11" ry="9" fill="${u.stornos}"/>`;
  if (u.grisnos) ut += `<ellipse cx="${hx}" cy="${hy + 8}" rx="13" ry="9" fill="${u.grisnos}" stroke="#ec407a" stroke-width="2"/><ellipse cx="${hx - 5}" cy="${hy + 8}" rx="2.5" ry="4" fill="#ad1457"/><ellipse cx="${hx + 5}" cy="${hy + 8}" rx="2.5" ry="4" fill="#ad1457"/>`;
  if (u.nabb) ut += `<path d="M${hx - 8} ${hy + 6} L${hx + 8} ${hy + 6} L${hx} ${hy + 16} Z" fill="${u.nabb}"/>`;
  if (u.morrhar) ut += `<path d="M${hx - 22} ${hy + 10} h-18 M${hx - 22} ${hy + 16} l-16 5 M${hx + 22} ${hy + 10} h18 M${hx + 22} ${hy + 16} l16 5" stroke="${linje}" stroke-width="2" opacity=".6"/>`;
  ut += evoFram(x.form, hx, hy, hr, x.hatt);
  // saker: på ögonen eller på huvudet, som en del av bilden
  if (x.hatt && PA_OGONEN.has(x.hatt.id)) ut += `<text x="${hx}" y="${hy + 14}" font-size="46" text-anchor="middle">${x.hatt.ikon}</text>`;
  else if (x.hatt) ut += `<text x="${hx + 4}" y="${hy - hr + 16}" font-size="50" text-anchor="middle" transform="rotate(-10 ${hx} ${hy - hr})">${x.hatt.ikon}</text>`;
  else if (x.krona) ut += `<text x="${hx}" y="${hy - hr + 14}" font-size="46" text-anchor="middle">👑</text>`;
  ut += `</g>`;
  if (x.kompis) ut += `<text class="kompis-svg" x="160" y="178" font-size="38" text-anchor="middle">${x.kompis.ikon}</text>`;
  if (x.eff?.partikel) [[30, 50], [170, 70], [40, 140]].forEach(([px, py], n) => (ut += `<text class="partikel p${n}" x="${px}" y="${py}" font-size="24" text-anchor="middle">${x.eff.partikel}</text>`));
  return ut + `</svg>`;
}

const DJUR_HUMOR = {
  glad: (n) => `😄 ${n} är mätt och glad!`,
  nojd: (n) => `🙂 ${n} väntar på dagens mat. Gör något i Läxspelet idag!`,
  hungrig: (n) => `😟 ${n} är hungrig! Gör något i Läxspelet för att mata ${n}.`,
  ledsen: (n) => `😢 ${n} saknar dig… Kom tillbaka och gör något i Läxspelet.`,
};

// "2026-11-21" -> { text: "fre 21 nov", kvar: "om 3 dagar", dagar: 3 }
// Provresultat: "18 av 20 p (90 %)" eller "Betyg B".
const provResText = (r) => `${r.andel >= 0.9 ? "🌟" : r.andel >= 0.6 ? "⭐" : "📝"} ${r.max ? `${r.poang} av ${r.max} p` : `Betyg ${r.betyg}`}`;

// Godkänt-gränsen (samma som servern): minst 80 % rätt.
const fhGrans = (n) => Math.ceil(n * 0.8 - 1e-9);
const fhMarke = (f) => (f.bedomning === "godkant" ? " ✅" : f.bedomning === "ej_godkant" ? " ❌" : "");

const forhorInfo = (iso) => {
  if (!iso) return null;
  const d = new Date(`${iso}T00:00:00`);
  const idag = new Date();
  idag.setHours(0, 0, 0, 0);
  const dagar = Math.round((d - idag) / 86400000);
  const text = d.toLocaleDateString("sv-SE", { weekday: "short", day: "numeric", month: "short" });
  const kvar = dagar < 0 ? "har varit" : dagar === 0 ? "idag!" : dagar === 1 ? "imorgon!" : `om ${dagar} dagar`;
  return { text, kvar, dagar };
};

// Dagens datum i lokal tid (toISOString är UTC och blir fel dag strax efter midnatt).
const idagISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const TYP_IKON = { prov: "📝", las: "📖", hogl: "🗣️", skriv: "✍️" };
const TYP_NAMN = { prov: "Prov", las: "Läsläxa", hogl: "Högläsning", skriv: "Läxboken" };
const PLAN_IKON = { las: "📖", forhor: "📝", ovningsprov: "🧪", repetera: "🔁", uppgifter: "✏️", glosor: "🗣️", sammanfatta: "🗒️", forklara: "🙋" };
const VECKODAG = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"];
const veckodag = (iso) => VECKODAG[(new Date(`${iso}T12:00:00`).getDay() + 6) % 7];
const plusDagar = (iso, n) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const shuffle = (a) => {
  const b = [...a];
  for (let i = b.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [b[i], b[j]] = [b[j], b[i]];
  }
  return b;
};

// Kapitel och avsnitt ur e-bokens sidor, för innehållsförteckningen.
const kapFor = (t, idx) => [...t].reverse().find((x) => x.niva === 1 && x.idx <= idx)?.text;

const sidnrInt = (v) => {
  const m = String(v ?? "").match(/^\s*(\d+)/);
  return m ? Number(m[1]) : null;
};

// Finns bokens innehållsförteckning används den (kapitel + startsida).
// Annars används de kapitel AI:n såg på varje sida.
const toc = (sidor, bokToc) => {
  const t = [];
  if (bokToc?.length) {
    for (const k of bokToc) {
      const idx = sidor.findIndex((s) => (sidnrInt(s.sidnr) ?? -1) >= k.sida);
      if (idx >= 0) t.push({ niva: 1, text: k.titel, idx, sida: k.sida });
    }
    sidor.forEach((s, idx) => {
      for (const r of s.rubriker || []) if (!/innehåll/i.test(r)) t.push({ niva: 2, text: r, idx });
    });
    return t.sort((a, b) => a.idx - b.idx || a.niva - b.niva);
  }
  sidor.forEach((s, idx) => {
    if (s.kapitel) t.push({ niva: 1, text: s.kapitel, idx });
    for (const r of s.rubriker || []) t.push({ niva: 2, text: r, idx });
  });
  return t;
};

// En kort berättelse för varje värld på kartan, och vad bossen säger.
const VARLD_BERATTELSE = {
  skog: ["I Glosskogen har orden rymt från böckerna och gömmer sig bland träden. Bara den som kan glosorna hittar vägen igenom.", "Glosmonstret har ätit upp alla glosor i skogen! Besegra det så kommer orden tillbaka."],
  hav: ["Havet är svart av bläck sedan någon välte ut alla pennor. Fiskarna hittar inte hem i mörkret.", "Bläckbläckfisken sprutar bläck på allt du har skrivit. Visa vem som bestämmer!"],
  berg: ["Uppe på Trollberget bor troll som tycker att läxor är det tråkigaste som finns. De bygger murar av struntprat.", "Läxtrollet har gömt alla läxböcker under sin bro. Hämta tillbaka dem!"],
  trask: ["I Sömnträsket blir alla så trötta att de somnar mitt i en mening. Håll dig vaken genom att plugga!", "Sömnzombien vill att alla ska sova över provet. Väck den med en riktig attack!"],
  fabrik: ["Robotarna i fabriken har glömt hur man räknar och har börjat gissa. Det blir fel överallt.", "Robotkungen påstår att 2 + 2 = 5. Bevisa att han har fel!"],
  vulkan: ["Det mullrar i Drakvulkanen. Där inne bor drakar som bränner upp allt man har lärt sig, om man slutar öva.", "Glömskedraken andas glömska. Allt du har övat på skyddar dig mot elden!"],
  slott: ["I Spökslottet spökar det bland halvfärdiga läxor. Ingen vågar gå in, utom du och ditt husdjur.", "Slarvspöket gör slarvfel i allt du skriver. Var noggrann så försvinner det!"],
  tid: ["Vid Tidshavet går klockorna åt alla håll. Den som skjuter upp sina läxor fastnar i tidsvirvlarna.", "Tidshajen äter upp all din tid. Gör läxan i tid så går den hungrig!"],
};

class SkolanPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._s = null; // svar från servern
    this._view = { name: "hem" };
    this._msg = null;
    this._busy = false;
    this._blobs = {};
    this._loaded = false;
    this._las = null; // { nyckel, t0 } sidan som läses just nu i e-boken
    setInterval(() => this._lasFlush(), 15000);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) this._lasFlush(true);
      else if (this._las) this._las.t0 = Date.now();
    });
  }

  // Skicka lästid för sidan som är öppen till de läsläxor/prov den ingår i (bara barn).
  _lasFlush(dold = false) {
    const l = this._las;
    if (!l || !this._s || this._s.kan_valja) return;
    if (document.hidden && !dold) { l.t0 = Date.now(); return; }
    const sek = Math.min(180, Math.round((Date.now() - l.t0) / 1000));
    l.t0 = Date.now();
    if (sek < 2) return;
    const upp = (this._s.data.uppdrag || []).filter((u) => !u.klart && u.sidor.some((x) => x.nyckel === l.nyckel));
    for (const u of upp) {
      this._hass
        .fetchWithAuth("/api/skolan/uppdrag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ barn: this._s.barn, op: "las_tid", id: u.id, nyckel: l.nyckel, sek }),
        })
        .then((r) => r.json())
        .then((body) => {
          if (!body.data) return;
          const fore = (this._s.data.uppdrag || []).find((x) => x.id === u.id)?.lasta;
          this._nyData(body.data);
          const efter = (this._s.data.uppdrag || []).find((x) => x.id === u.id)?.lasta;
          if (fore !== efter && this._view.name === "ebok") this._render();
        })
        .catch(() => {});
    }
  }

  _lasSek(bok, nyckel) {
    return this._s?.data?.lasning?.[bok]?.[nyckel] || 0;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._render();
      this._load();
    }
  }

  set narrow(n) {
    this._narrow = n;
    const b = this.shadowRoot.querySelector("#menu");
    if (b) b.style.display = n && !this._last ? "inline-flex" : "none";
  }

  // ---------- server ----------

  async _load(barn) {
    // Länk från en notis: /skolan?barn=anna&forhor=abc öppnar förhöret direkt.
    if (!this._lankLast) {
      this._lankLast = true;
      const q = new URLSearchParams(window.location.search);
      if (q.get("forhor")) {
        barn = barn || q.get("barn") || undefined;
        this._view = { name: "forhor", forhor: q.get("forhor") };
        try { history.replaceState(null, "", window.location.pathname); } catch (e) { /* ok */ }
      } else if (q.get("bok")) {
        barn = barn || q.get("barn") || undefined;
        this._lankBok = q.get("bok");
        try { history.replaceState(null, "", window.location.pathname); } catch (e) { /* ok */ }
      } else if (q.get("glosor")) {
        barn = barn || q.get("barn") || undefined;
        this._lankGlosor = q.get("glosor");
        try { history.replaceState(null, "", window.location.pathname); } catch (e) { /* ok */ }
      } else if (q.get("uppdrag")) {
        barn = barn || q.get("barn") || undefined;
        this._view = { name: "uppdrag", id: q.get("uppdrag") };
        try { history.replaceState(null, "", window.location.pathname); } catch (e) { /* ok */ }
      }
    }
    try {
      const q = barn ? `?barn=${encodeURIComponent(barn)}` : this._s ? `?barn=${encodeURIComponent(this._s.barn)}` : "";
      const res = await this._hass.fetchWithAuth(`/api/skolan/state${q}`);
      if (res.status === 403) throw new Error("Den här sidan är bara för barnen i Läxspelet och deras föräldrar.");
      const body = await res.json();
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._s = body;
      if (this._lankBok) {
        const a = (body.data.amnen || []).find((x) => (x.bocker || []).some((b) => b.id === this._lankBok));
        if (a) this._view = { name: "bok", amne: a.id, bok: this._lankBok };
        this._lankBok = null;
      }
      if (this._lankGlosor) {
        const a = (body.data.amnen || []).find((x) => x.glosor.some((g) => g.id === this._lankGlosor));
        if (a) this._view = { name: "glosor", amne: a.id, glosor: this._lankGlosor };
        else this._msg = { type: "error", text: "Glosorna i notisen finns inte längre (listan har tagits bort). Det finns inget att godkänna." };
        this._lankGlosor = null;
      }
      // Barn: ett förhör som väntar öppnas direkt. Ett påbörjat förhör går inte att lämna.
      if (!body.kan_valja) {
        const oppet = (body.data.forhor || []).find((f) => f.status === "pagar") ||
          (body.data.forhor || []).find((f) => f.status === "skickat" && f.id !== this._fhSenare);
        const tittarResultat = this._view.name === "forhor" && (body.data.forhor || []).some((f) => f.id === this._view.forhor && f.status === "klart");
        if (oppet && !(this._view.name === "forhor" && this._view.forhor === oppet.id) && !(oppet.status === "skickat" && tittarResultat)) {
          this._view = { name: "forhor", forhor: oppet.id, startad: oppet.status === "pagar" };
        }
      }
      this._hamtaVanner();
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    }
    this._render();
  }

  // ---------- vänner (dolt tills vänservern finns: pa === false) ----------
  async _hamtaVanner() {
    try {
      const res = await this._hass.fetchWithAuth(`/api/skolan/vanner?barn=${encodeURIComponent(this._s.barn)}`);
      const v = res.ok ? await res.json() : { pa: false };
      const fore = JSON.stringify(this._vanner || null);
      this._vanner = v.pa ? v : null;
      if (JSON.stringify(this._vanner) !== fore) this._render();
    } catch (e) { this._vanner = null; }
  }

  async _vanOp(op, args = {}) {
    this._busy = true; this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/vanner", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, op, ...args }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._vanner = body; this._msg = null; return true;
    } catch (e) { this._msg = { type: "error", text: e.message || String(e) }; return false; }
    finally { this._busy = false; this._render(); }
  }

  _vannerView() {
    const v = this._vanner, s = this._s;
    if (!v) return `<p class="muted">Vänner är inte påslaget.</p>`;
    const k = s.karta, d = s.meriter?.djur, f = v.foralder;
    const jag = { smeknamn: v.smeknamn || s.namn, art: d?.art, niva: k?.niva || 1, stjarnor: k?.stjarnor_tot || 0, jag: true };
    const lista = [...v.vanner, jag].sort((a, b) => b.niva - a.niva || b.stjarnor - a.stjarnor);
    const rad = (x, i) => `<li class="van-rad ${x.jag ? "jag" : ""}"><span class="van-plats">${i + 1}</span>
      <span class="van-djur">${x.art ? ritaDjur(x.art, "glad", 2, {}) : "🙂"}</span>
      <span class="van-namn"><b>${esc(x.smeknamn)}</b>${x.jag ? " (du)" : ""}${x.titel ? `<br><span class="titel-bricka">${esc(x.titel)}</span>` : ""}</span>
      <span class="van-niva">🗺️ ${x.niva}<br><span class="small">⭐ ${x.stjarnor}</span></span>
      ${!x.jag && x.attack ? this._reprisKnapp(x.attack, x.smeknamn, { art: x.art, steg: x.steg || 1, namn: x.smeknamn }, `van:${x.kod}`, true) : ""}
      ${!x.jag ? `<button class="mini ghost" data-van-bort="${esc(x.kod)}" title="Ta bort">✕</button>` : ""}</li>`;
    const vard = (kod) => { try { return new URL(kod).hostname.split(".")[0].slice(0, 8) + "…"; } catch (e) { return "?"; } };
    const ut = v.utgaende.map((x) => `<li>Ny vän (${esc(vard(x.kod))}) · ⏳ väntar på förälder
      ${f ? `<button class="mini primary" data-van-ut="${esc(x.kod)}" data-ja="1">Godkänn</button><button class="mini" data-van-ut="${esc(x.kod)}" data-ja="">Neka</button>` : ""}</li>`).join("");
    const inn = v.inkommande.map((x) => `<li>🤝 ${esc(x.smeknamn || x.kod)} vill bli vän
      ${f ? `<button class="mini primary" data-van-in="${esc(x.kod)}" data-ja="1">Godkänn</button><button class="mini" data-van-in="${esc(x.kod)}" data-ja="">Neka</button>` : " · ⏳ en förälder godkänner"}</li>`).join("");
    return `
      ${!v.kan_nas ? `<div class="card"><b>⚠️ Er Home Assistant går inte att nå utifrån.</b><div class="small">Vänner kräver fjärråtkomst, till exempel Nabu Casa.</div></div>`
        : v.kod ? `<div class="card center"><div class="small muted">Din vänlänk</div>
        <div class="actions"><button class="primary" id="van-dela">📤 Dela med en kompis</button><button id="van-kopiera">📋 Kopiera</button></div>
        <div class="small muted">Ge länken bara till kompisar. Den visar ditt smeknamn, husdjur, nivå och stjärnor.</div></div>`
        : `<div class="card center small muted">Din vänlänk kommer när smeknamnet är godkänt.</div>`}
      <div class="card">
        <div class="row"><input id="van-smek" maxlength="16" placeholder="Smeknamn" value="${esc(v.smeknamn)}"><button id="van-smek-spara">Spara</button></div>
        <div class="small ${v.smeknamn_ok ? "" : "muted"}">${!v.smeknamn ? "Välj ett smeknamn som kompisarna ser. Skriv inte ditt efternamn." : v.smeknamn_ok ? "✅ Godkänt smeknamn" : "⏳ En förälder behöver godkänna smeknamnet"}
          ${f && v.smeknamn && !v.smeknamn_ok ? `<button class="mini primary" id="van-smek-ok">Godkänn</button>` : ""}</div>
      </div>
      <div class="card"><div class="row"><input id="van-kod" placeholder="Klistra in kompisens vänlänk"><button class="primary" id="van-lagg">Lägg till</button></div>
        ${inn ? `<h3>Förfrågningar</h3><ul class="van-vantar">${inn}</ul>` : ""}
        ${ut ? `<h3>Väntar</h3><ul class="van-vantar">${ut}</ul>` : ""}</div>
      <h3>🏆 Vänner på kartan</h3><ol class="van-lista">${lista.map(rad).join("")}</ol>
      <div class="actions"><button class="ghost" id="van-synka">🔄 Uppdatera</button></div>
      <p class="small muted center">Kompisar ser bara ditt smeknamn, husdjur, nivå och stjärnor. En förälder godkänner varje ny vän.</p>`;
  }

  async _act(op, args = {}) {
    this._busy = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, op, ...args }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._nyData(body.data);
      this._msg = null;
      return true;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _upload(files, omslag = null) {
    const v = this._view;
    this._busy = true;
    this._msg = { type: "info", text: `Laddar upp ${files.length} fil${files.length === 1 ? "" : "er"}…` };
    this._render();
    try {
      const fd = new FormData();
      fd.append("barn", this._s.barn);
      fd.append("amne", v.amne);
      fd.append("bok", v.bok);
      if (omslag) fd.append("omslag", omslag);
      for (const f of files) fd.append("file", f, f.name);
      const res = await this._hass.fetchWithAuth("/api/skolan/upload", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._nyData(body.data);
      this._msg = { type: "ok", text: "Sparat!" };
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    }
    this._busy = false;
    this._render();
  }

  async _readGlosor(file) {
    this._busy = true;
    this._msg = { type: "info", text: "AI:n läser glosorna… (tar några sekunder)" };
    this._render();
    try {
      const fd = new FormData();
      fd.append("barn", this._s.barn);
      fd.append("file", file, file.name);
      const res = await this._hass.fetchWithAuth("/api/skolan/glosor_las", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      const v = this._view;
      v.sprak = body.sprak;
      if (!v.namn && body.namn) v.namn = body.namn;
      v.par = [...(v.par || []).filter((p) => p[0] || p[1]), ...body.par];
      this._msg = body.par.length
        ? { type: "ok", text: `${body.par.length} glosor hittades. Kolla att allt stämmer och spara.` }
        : { type: "error", text: body.note || "Inga glosor hittades." };
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    }
    this._busy = false;
    this._render();
  }

  async _blob(fil) {
    if (this._blobs[fil]) return this._blobs[fil];
    const res = await this._hass.fetchWithAuth(
      `/api/skolan/fil?barn=${encodeURIComponent(this._s.barn)}&fil=${encodeURIComponent(fil)}`
    );
    if (!res.ok) throw new Error("Kunde inte hämta filen");
    const url = URL.createObjectURL(await res.blob());
    this._blobs[fil] = url;
    return url;
  }

  // ---------- hjälp ----------

  // Ny data från servern. Har det kommit nya meriter visas en liten "+20 ⭐" och sammanfattningen hämtas.
  _nyData(data) {
    const fore = this._s.data?.meriter?.logg?.length || 0;
    this._s.data = data;
    const logg = data?.meriter?.logg || [];
    const nya = logg.slice(fore).filter((x) => x.p > 0);
    if (nya.length && !this._s.kan_valja) {
      this._toast = nya;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => { this._toast = null; this._render(); }, 4500);
    }
    if (logg.length !== fore) setTimeout(() => this._load(), 300);
  }

  _amne(id) {
    return this._s?.data?.amnen?.find((a) => a.id === id);
  }

  _go(view) {
    if (view.name !== "uppdrag") this._liveStopp();
    if (view.name === "tillsammans" || view.name === "duell") this._tillLoad();
    if (view.name === "duell") this._duellPoll(); else if (this._duellTimer) { clearInterval(this._duellTimer); this._duellTimer = null; }
    const nyBok = view.name === "bok" && !(this._view.name === "bok" && this._view.bok === view.bok);
    this._view = view;
    if (nyBok && this._s) this._ebokStatus(view.bok);
    this._msg = null;
    this._render();
    this.shadowRoot.querySelector(".content")?.scrollTo?.(0, 0);
  }

  _ask(text, def = "") {
    const v = window.prompt(text, def);
    return v === null ? null : v.trim();
  }

  // ---------- rendering ----------

  _render() {
    const r = this.shadowRoot;
    const s = this._s;
    const v = this._view;
    let title = "Läxspelet";
    let body = "";
    let back = null;

    if (!s) {
      body = this._msg ? "" : `<p class="muted">Laddar…</p>`;
    } else if (v.name === "hem") {
      title = `${esc(s.namn)}s skola`;
      body = this._hem();
    } else if (v.name === "uppdrag_ny") {
      title = v.typ === "prov" ? "📝 Nytt prov" : "📖 Ny läsläxa";
      back = v.guide ? { name: "laxa", steg: "typ", amne: v.amne } : { name: "hem" };
      body = this._uppdragNyView();
    } else if (v.name === "uppdrag") {
      const u = (s.data.uppdrag || []).find((x) => x.id === v.id);
      if (!u) {
        this._view = { name: "hem" };
        return this._render();
      }
      title = `${TYP_IKON[u.typ] || "📖"} ${esc(u.namn)}`;
      back = { name: "hem" };
      body = u.typ === "hogl" ? this._hoglView(u) : u.typ === "skriv" ? this._skrivView(u) : this._uppdragView(u);
    } else if (v.name === "pass") {
      title = "🎟️ Läxpasset";
      back = { name: "hem" };
      body = this._passView();
    } else if (v.name === "rum") {
      title = "🏠 Husdjurets rum";
      back = { name: "hem" };
      body = this._rumView();
    } else if (v.name === "widget") {
      title = "📱 Husdjuret på hemskärmen";
      back = { name: "hem" };
      body = v.kod
        ? `<p>Be mamma eller pappa om hjälp, det tar en minut. 🙂</p>
          <ol class="widget-steg">
            <li>Hämta den gratis appen <b>Scriptable</b> från App Store.</li>
            <li>Tryck på <b>⬇️ Installera</b> nedan och välj <b>Öppna i Scriptable</b> (eller tryck på hämtningen och välj Scriptable). Tryck <b>Lägg till</b>.</li>
            <li>Håll fingret på hemskärmen, tryck <b>+</b>, välj <b>Scriptable</b> och lägg till en widget.</li>
            <li>Håll på widgeten, välj <b>Redigera widget</b> och välj <b>Husdjur</b>.</li>
          </ol>
          <a class="primary stor-las knapp-lank" href="${esc(v.installera)}" target="_blank" rel="noopener">⬇️ Installera</a>
          <details style="margin-top:12px"><summary class="small">Funkar inte? Kopiera koden i stället</summary>
            <button class="ghost" id="kopiera-widget" style="margin-top:8px">📋 Kopiera koden</button>
            <p class="small">Öppna Scriptable, tryck <b>+</b>, klistra in och döp skriptet till <b>Husdjur</b>.</p>
          </details>
          <p class="small muted">Widgeten visar bara ditt husdjur. Dela inte länken med någon.</p>`
        : `<p class="muted">Hämtar…</p>`;
    } else if (v.name === "vanner") {
      title = "🤝 Vänner";
      back = { name: "hem" };
      body = this._vannerView();
    } else if (v.name === "skola") {
      title = "🏫 Skolan och läraren";
      back = { name: "hem" };
      body = this._skolaView();
    } else if (v.name === "tillsammans") {
      title = "🤝 Plugga ihop";
      back = { name: "hem" };
      body = this._tillView();
    } else if (v.name === "duell") {
      title = "⚔️ Glosduell";
      back = { name: "tillsammans" };
      body = this._duellView(v.id);
    } else if (v.name === "lag") {
      title = this._s.lag ? `${this._s.lag.marke} ${this._s.lag.namn}` : "🏳️ Lag";
      back = { name: "hem" };
      body = this._lagView();
    } else if (v.name === "lagstrid") {
      title = "⚔️ Lagstrid";
      back = { name: "lag" };
      body = this._lagstridView();
    } else if (v.name === "arena") {
      title = "🏟️ Arenan";
      back = { name: "hem" };
      body = this._arenaView();
    } else if (v.name === "album") {
      title = "🃏 Samlaralbum";
      back = { name: "hem" };
      body = this._albumView();
    } else if (v.name === "fraga") {
      title = `💬 Fråga ${esc(this._s.meriter?.djur?.namn || "husdjuret")}`;
      back = { name: "hem" };
      body = this._fragaView();
    } else if (v.name === "plan") {
      title = "📅 Pluggplan";
      back = v.g && (s.data.uppdrag || []).find((x) => x.id === v.uppdrag)?.plan?.delar?.length ? { name: "plan", uppdrag: v.uppdrag } : { name: "hem" };
      body = this._planView();
    } else if (v.name === "ovningsprov") {
      title = "🧪 Övningsprov";
      back = { name: "plan", uppdrag: v.uppdrag };
      body = this._ovningsprovView();
    } else if (v.name === "svaga") {
      title = "🔁 Svaga punkter";
      back = { name: "hem" };
      body = this._svagaView();
    } else if (v.name === "coach") {
      title = "🧠 Studiecoach";
      back = { name: "foralder" };
      body = this._coachView();
    } else if (v.name === "rapport") {
      title = "📊 Veckorapport";
      back = { name: "foralder" };
      body = this._rapportView();
    } else if (v.name === "hjalp") {
      title = `📚 Plugga med ${esc(this._s.meriter?.djur?.namn || "husdjuret")}`;
      back = { name: "hem" };
      body = this._hjalpView();
    } else if (v.name === "lar") {
      title = `🎓 Lär ${esc(this._s.meriter?.djur?.namn || "husdjuret")}`;
      back = { name: "glosor", amne: v.amne, glosor: v.glosor };
      body = this._larView();
    } else if (v.name === "fokus") {
      title = "⏱️ Fokusläge";
      back = { name: "hem" };
      body = this._fokusView();
    } else if (v.name === "glosstrid") {
      title = "⚔️ Glosstrid";
      back = v.gs && !v.gs.klar ? null : v.fran === "glosor" ? { name: "glosor", amne: v.amne, glosor: v.glosor } : { name: "hem" };
      body = this._glosstridView();
    } else if (v.name === "karta") {
      title = "🗺️ Äventyrskartan";
      back = { name: "hem" };
      body = this._kartaView();
    } else if (v.name === "djurbutik") {
      title = "🛍️ Husdjursbutik";
      back = { name: "hem" };
      body = this._djurbutikView();
    } else if (v.name === "laxa") {
      title = "📥 Lägg in läxa";
      back = v.steg === "typ" ? { name: "laxa", steg: "amne" } : v.steg === "uppgift" ? { name: "laxa", steg: "typ", amne: v.amne } : { name: "hem" };
      body = this._laxaView();
    } else if (v.name === "amne-form") {
      title = v.amne ? "✏️ Redigera ämnet" : "＋ Nytt ämne";
      back = v.amne ? { name: "amne", amne: v.amne } : v.franLaxa ? { name: "laxa", steg: "amne" } : { name: "hem" };
      body = this._amneFormView();
    } else if (v.name === "info") {
      title = "ℹ️ Så funkar det";
      back = v.fran || { name: "hem" };
      body = this._infoView();
    } else if (v.name === "lektioner") {
      title = s.kan_valja ? `🗓️ ${esc(s.namn)}s schema` : "🗓️ Mitt schema";
      back = { name: "hem" };
      body = this._lektionView();
    } else if (v.name === "kalender") {
      title = "📅 Skolkalendrar";
      if (v.ny) back = { name: "kalender" };
      back = { name: "foralder" };
      body = this._kalenderView();
    } else if (v.name === "veckobrev") {
      title = "📸 Veckobrev";
      back = { name: "foralder" };
      body = this._veckobrevView();
    } else if (v.name === "foralder") {
      title = "⚙️ Föräldrar";
      back = { name: "hem" };
      body = this._foralderView();
    } else if (v.name === "meriter") {
      title = "🏅 Meriter";
      back = { name: "hem" };
      body = this._meriterView();
    } else if (v.name === "fhlogg") {
      title = "📋 Alla förhör";
      back = { name: "hem" };
      body = this._fhLogg();
    } else if (v.name === "forhor") {
      const f = (s.data.forhor || []).find((x) => x.id === v.forhor);
      if (!f) {
        this._view = { name: "hem" };
        return this._render();
      }
      title = `📋 ${esc(f.namn)}`;
      back = v.franLogg ? { name: "fhlogg" } : { name: "hem" };
      body = this._forhorView(f);
    } else {
      const a = this._amne(v.amne);
      if (!a) {
        this._view = { name: "hem" };
        return this._render();
      }
      if (v.name === "amne") {
        title = esc(a.namn);
        back = { name: "hem" };
        body = this._amneView(a);
      } else if (v.name === "bok") {
        const b = a.bocker.find((x) => x.id === v.bok);
        if (!b) {
          this._view = { name: "amne", amne: a.id };
          return this._render();
        }
        title = esc(b.namn);
        back = { name: "amne", amne: a.id };
        body = this._bokView(a, b);
      } else if (v.name === "skicka") {
        const g = a.glosor.find((x) => x.id === v.glosor);
        if (!g) {
          this._view = { name: "amne", amne: a.id };
          return this._render();
        }
        title = "📋 Skicka förhör";
        back = { name: "glosor", amne: a.id, glosor: g.id };
        body = this._skickaView(a, g);
      } else if (v.name === "ebok") {
        const b = a.bocker.find((x) => x.id === v.bok);
        if (!b) {
          this._view = { name: "amne", amne: a.id };
          return this._render();
        }
        title = `📘 ${esc(b.namn)}`;
        back = v.uppdrag ? { name: "uppdrag", amne: a.id, id: v.uppdrag } : { name: "amne", amne: a.id };
        body = this._ebokView(b);
      } else if (v.name === "glosor") {
        const g = a.glosor.find((x) => x.id === v.glosor);
        if (!g) {
          this._view = { name: "amne", amne: a.id };
          return this._render();
        }
        title = esc(g.namn);
        back = { name: "amne", amne: a.id };
        body = this._glosorView(a, g);
      } else if (v.name === "redigera") {
        title = LISTTYP[v.typ || "glosor"].titel[v.glosor ? 1 : 0];
        back = v.glosor ? { name: "glosor", amne: a.id, glosor: v.glosor } : v.guide ? { name: "laxa", steg: "typ", amne: a.id } : { name: "amne", amne: a.id };
        body = this._redigeraView(a);
      } else if (v.name === "rekord") {
        const g = a.glosor.find((x) => x.id === v.glosor);
        title = `⚡ Glosrekord`;
        back = v.spel?.slut && !v.spel.klar ? null : { name: "glosor", amne: a.id, glosor: v.glosor };
        body = this._rekordView(g);
      } else if (v.name === "ova") {
        const g = a.glosor.find((x) => x.id === v.glosor);
        title = `Öva: ${esc(g?.namn)}`;
        back = { name: "glosor", amne: a.id, glosor: v.glosor };
        body = this._ovaView(a, g);
      }
    }
    // Låst medan barnet gör ett förhör: ingen tillbaka-pil eller meny.
    const fl = v.name === "forhor" && s && !s.kan_valja && (s.data.forhor || []).find((x) => x.id === v.forhor);
    this._last = !!(fl && fl.status !== "klart" && (v.startad || fl.svar.length));
    if (this._last) back = null;
    this._back = back;

    const barnVal =
      s?.kan_valja && v.name === "hem"
        ? `<div class="tabs">${s.alla_barn
            .map((b) => `<button class="tab ${b.id === s.barn ? "on" : ""}" data-barn="${b.id}">${esc(b.namn)}</button>`)
            .join("")}</div>`
        : "";

    // Helskärm: barnet gör ett förhör (täcker hela skärmen, även Home Assistants meny).
    const helskarm = !!(fl && fl.status !== "klart");
    r.innerHTML = `
      <style>${CSS}</style>
      <div class="${helskarm ? "helskarm" : ""}">
      <div class="toolbar">
        <button id="menu" class="icon" style="display:${this._narrow && !this._last ? "inline-flex" : "none"}" title="Meny">☰</button>
        ${back ? `<button id="back" class="icon" title="Tillbaka">←</button>` : ""}
        <div class="title">${title}</div>
      </div>
      <div class="content">
        ${barnVal}
        ${this._msg ? `<div class="msg ${this._msg.type}">${esc(this._msg.text)}</div>` : ""}
        ${body}
      </div>
      </div>
      ${this._busy ? `<div class="busy"><div class="spin"></div></div>` : ""}
      ${this._toast ? `<div class="toast">${this._toast.map((x) => `<div>${esc(x.ikon)} <b>+${x.p}</b> ${esc(x.orsak)}</div>`).join("")}</div>` : ""}
      ${this._viewer ? `<div class="viewer" id="viewer"><img src="${this._viewer}" alt="Sida" draggable="false"><button class="icon close" id="viewer-stang" title="Stäng">✕</button>
        <div class="zoom-knappar"><button id="zoom-ut">−</button><button id="zoom-in">+</button></div>
        <div class="zoom-tips">${this._viewerEbok && this._view.e ? `Sida ${esc(this._view.e.sidor[this._view.e.idx].sidnr || this._view.e.idx + 1)} · svep för att byta sida` : "Nyp eller dubbeltryck för att zooma"}</div></div>` : ""}
    `;
    this._wire();
    this._afterRender();
  }

  _fhLogg() {
    const lista = [...(this._s.data.forhor || [])].reverse();
    if (!lista.length) return `<p class="muted">Inga förhör än.</p>`;
    const klara = lista.filter((f) => f.status === "klart");
    const snitt = klara.length ? Math.round((klara.reduce((t, f) => t + f.svar.filter((x) => x.ratt).length / f.fragor.length, 0) / klara.length) * 100) : null;
    return `
      ${snitt !== null ? `<div class="forhor-kort">${klara.length} förhör gjorda · i snitt <b>${snitt}%</b> rätt</div>` : ""}
      <table class="glos logg">
        <tr><th>Datum</th><th>Glosor</th><th>Resultat</th></tr>
        ${lista
          .map((f) => {
            const ratt = f.svar.filter((x) => x.ratt).length;
            const res = f.status === "klart" ? `<b>${ratt}/${f.fragor.length}</b> ${ratt === f.fragor.length ? "🏆" : ""}${fhMarke(f)}` : (f.status === "pagar" ? "✏️ pågår" : "📨 ej startat") + (f.paminnelser?.length ? ` · 🔔${f.paminnelser.length}` : "");
            return `<tr data-open-forhor="${f.id}"><td>${esc((f.klart || f.skapad).slice(0, 10))}</td><td>${esc(f.namn)}<br><span class="muted small">${esc(f.amne_namn || "")} · ${esc(f.av_namn)}</span></td><td>${res}</td></tr>`;
          })
          .join("")}
      </table>`;
  }

  _forhorLista() {
    const s = this._s;
    const lista = [...(s.data.forhor || [])].reverse();
    if (s.kan_valja) {
      if (!lista.length) return "";
      return `<h3>📋 Förhör</h3><div class="list">${lista
        .slice(0, 4)
        .map((f) => {
          const ratt = f.svar.filter((x) => x.ratt).length;
          const status =
            f.status === "klart" ? `${ratt} av ${f.fragor.length} rätt${fhMarke(f)}` : f.status === "pagar" ? `✏️ Pågår ${f.svar.length}/${f.fragor.length}` : "📨 Skickat, inte startat";
          return `<button class="row" data-open-forhor="${f.id}"><span>${esc(f.namn)}<br><span class="muted small">${esc(f.skapad.slice(0, 10))} · från ${esc(f.av_namn)}</span></span><span class="small">${status} ›</span></button>`;
        })
        .join("")}<button class="row add" id="fh-logg">📋 Alla förhör (${lista.length})</button></div>`;
    }
    const oppna = lista.filter((f) => f.status !== "klart");
    const klara = lista.filter((f) => f.status === "klart").slice(0, 3);
    return `
      ${oppna
        .map(
          (f) => `<button class="forhor-nytt" data-open-forhor="${f.id}">
            <div class="fn-rubrik">📋 Förhör från ${esc(f.av_namn)}</div>
            <div class="fn-namn">${esc(f.namn)} <span class="small">(${f.fragor.length} ord)</span></div>
            ${f.meddelande ? `<div class="small">"${esc(f.meddelande)}"</div>` : ""}
            <div class="fn-start">${f.status === "pagar" ? `Fortsätt (${f.svar.length}/${f.fragor.length}) →` : "Starta →"}</div>
          </button>`
        )
        .join("")}
      ${klara.length ? `<h3>📋 Mina förhör</h3><div class="list">${klara
        .map((f) => `<button class="row" data-open-forhor="${f.id}"><span>${esc(f.namn)}</span><span class="small">${f.svar.filter((x) => x.ratt).length} av ${f.fragor.length} rätt${fhMarke(f)} ›</span></button>`)
        .join("")}<button class="row add" id="fh-logg">📋 Alla förhör (${lista.length})</button></div>` : ""}`;
  }

  _forhorView(f) {
    const s = this._s;
    const v = this._view;
    const n = f.fragor.length;
    const ratt = f.svar.filter((x) => x.ratt).length;
    // Barnet svarar
    if (!s.kan_valja && f.status !== "klart") {
      const i = f.svar.length;
      const q = f.fragor[i];
      if (!v.startad && i === 0) {
        return `
          <div class="flash">
            <div class="big">📋</div>
            ${f.omprov_av ? `<div class="fh-omprov">🔁 Nytt försök! Du behöver minst ${fhGrans(n)} av ${n} rätt för godkänt.</div>` : ""}
            <div class="word" style="font-size:24px">${esc(f.namn)}</div>
            <div>${n} ord · från ${esc(f.av_namn)}</div>
            ${f.meddelande ? `<div class="muted">"${esc(f.meddelande)}"</div>` : ""}
            <div class="muted small">Inga ledtrådar och du får inte se svaren förrän du är klar. När du har startat måste du göra klart förhöret. Lycka till!</div>
            <button class="primary" id="fh-start">Starta förhöret</button>
            <button class="ghost" id="fh-senare">Senare</button>
          </div>`;
      }
      return `
        <div class="progress"><div style="width:${(i / n) * 100}%"></div></div>
        <div class="muted small center">${q.dikt ? "Ord" : "Fråga"} ${i + 1} av ${n}</div>
        <div class="flash">
          ${q.dikt
            ? `<button class="lyssna" id="fh-lyssna">🔊</button>
               <div class="muted small">Lyssna och stava ordet. Tryck igen för att höra det långsammare.</div>`
            : `<div class="muted small">${esc(q.fran)}</div>
          <div class="word">${esc(q.fraga)}</div>`}
          <input id="fh-svar" placeholder="${q.dikt ? "Skriv ordet" : ["namn", "vad", "formel", "begrepp", "förklaring"].includes((q.till || "").toLowerCase()) ? `Skriv ${esc(q.till.toLowerCase())}` : `Skriv på ${esc((q.till || "").toLowerCase() || "det andra språket")}`}" autocomplete="off" autocapitalize="off" spellcheck="false">
          <button class="primary" id="fh-svara">${i === n - 1 ? "Lämna in ✓" : "Nästa →"}</button>
        </div>`;
    }
    // Resultat / förälderns vy
    const rader = f.fragor
      .map((q, i) => {
        const x = f.svar[i];
        if (!x) return `<tr><td>${esc(q.fraga)}</td><td class="muted">–</td><td class="muted">${esc(q.facit || "")}</td><td></td></tr>`;
        const diff = !x.ratt && x.svar && q.facit
          ? `<div class="stavning liten">${narmast(x.svar, q.facit).delar.map((d) => `<span class="${d.ok ? "ok" : "miss"}">${d.c === " " ? "&nbsp;" : esc(d.c)}</span>`).join("")}</div>`
          : "";
        return `<tr class="${x.ratt ? "r-ok" : "r-fel"}">
          <td>${esc(q.fraga)}</td>
          <td>${x.ratt ? "✓" : "✗"} ${esc(x.svar || "(tomt)")}${x.andrad ? ` <span class="muted small">(ändrat)</span>` : ""}</td>
          <td>${x.ratt ? "" : esc(q.facit || "")}${diff}</td>
          <td>${s.kan_valja && f.status === "klart" ? `<button class="mini" data-fh-andra="${i}" title="Ändra rätt/fel">⇄</button>` : ""}</td>
        </tr>`;
      })
      .join("");
    const pct = n ? Math.round((ratt / n) * 100) : 0;
    return `
      ${
        f.status === "klart"
          ? `<div class="done" style="padding:10px 0"><div class="big">${pct >= 90 ? "🏆" : pct >= 60 ? "⭐" : "💪"}</div>
             <div class="score">${ratt} av ${n} rätt</div>
             <div class="muted small">Klart ${esc((f.klart || "").replace("T", " "))}</div></div>
             ${this._fhBeslut(f, ratt, n)}`
          : f.status === "pagar"
          ? `<div class="forhor-kort folj">
               <div>✏️ <b>${esc(s.namn)} gör förhöret just nu</b></div>
               <div class="progress stor"><div style="width:${(f.svar.length / n) * 100}%"></div></div>
               <div>${f.svar.length} av ${n} svarade · ${ratt} rätt hittills</div>
               <div class="muted small">Startade ${esc((f.startad || "").slice(11, 16))}${f.senast ? ` · senaste svaret ${esc(f.senast.slice(11, 16))}` : ""} · uppdateras av sig själv</div>
             </div>`
          : `<div class="forhor-kort">📨 Skickat ${esc(f.skapad.replace("T", " "))}, inte startat än</div>`
      }
      ${f.manuell ? `<p class="muted">🗣️ ${esc(f.meddelande)}</p>` : `<table class="glos"><tr><th>Fråga</th><th>Svar</th><th>Rätt svar</th><th></th></tr>${rader}</table>`}
      ${!s.kan_valja && f.svar.some((x) => !x.ratt) ? `<p class="muted small">Orden du hade fel på har fått en 🔥 i glosorna, så du kan öva extra på dem.</p>` : ""}
      ${s.kan_valja && f.status !== "klart" ? `<button class="row foralder-knapp" id="fh-paminn"><span>🔔 <b>Påminn ${esc(s.namn)}</b><br><span class="muted small">Skickar en notis som öppnar förhöret direkt</span></span><span>›</span></button>` : ""}
      ${(f.paminnelser || []).length ? `<h3>🔔 Påminnelser</h3><div class="list">${[...f.paminnelser].reverse()
        .map((x) => `<div class="row static"><span>${esc(forhorInfo(x.tid.slice(0, 10)).text)} kl. ${esc(x.tid.slice(11, 16))}</span><span class="muted small">${esc(x.av || "")}</span></div>`)
        .join("")}</div>` : ""}
      ${s.kan_valja ? `<div class="actions"><button class="ghost danger" id="fh-ta-bort">Ta bort förhöret</button></div>` : ""}`;
  }

  _fhBeslut(f, ratt, n) {
    if (!f.bedomning || f.manuell) return "";
    const s = this._s;
    const ok = f.bedomning === "godkant";
    const krav = `minst ${fhGrans(n)} av ${n} rätt`;
    if (!s.kan_valja) {
      const om = (s.data.forhor || []).find((x) => x.id === f.omprov_id);
      return ok
        ? `<div class="fh-beslut ok"><div class="fb-rubrik">🎉 Godkänt!</div><div>Snyggt jobbat${f.bedomd_av ? `, ${esc(f.bedomd_av)} har godkänt förhöret` : ""}!</div></div>`
        : `<div class="fh-beslut fel"><div class="fb-rubrik">❌ Inte godkänt än</div>
            <div>${f.bedomd_av ? `${esc(f.bedomd_av)} har bedömt förhöret.` : `Du behövde ${krav}.`} Kolla orden du hade fel på och försök igen!</div>
            ${om && om.status !== "klart" ? `<button class="primary" data-open-forhor="${om.id}">🔁 Gör det nya förhöret →</button>` : ""}</div>`;
    }
    const vem = f.bedomd_av ? `Bedömt av ${esc(f.bedomd_av)}` : `Automatiskt: gränsen är ${krav}`;
    const forslag = f.forslag && f.forslag !== f.bedomning ? `<div class="muted small">Efter ändrade svar blir förslaget nu ${f.forslag === "godkant" ? "godkänt" : "inte godkänt"}.</div>` : "";
    const om = (s.data.forhor || []).find((x) => x.id === f.omprov_id);
    return `<div class="fh-beslut ${ok ? "ok" : "fel"}">
        <div class="fb-rubrik">${ok ? "✅ Godkänt" : "❌ Inte godkänt"}</div>
        <div class="muted small">${vem}${om ? ` · nytt förhör ${om.status === "klart" ? "gjort" : om.status === "pagar" ? "pågår" : "skickat"}` : ""}</div>${forslag}
        <div class="fb-knappar">
          <button class="${ok ? "primary" : "ghost"}" data-fh-bedom="godkant">✅ Godkänn</button>
          <button class="${ok ? "ghost" : "primary"}" data-fh-bedom="ej_godkant">❌ Inte godkänt</button>
        </div>
        <div class="muted small">Inte godkänt ger ${esc(s.namn)} ett nytt förhör på samma ord. Godkänner du tas ett nytt förhör som inte är påbörjat bort.</div>
      </div>`;
  }

  _fhFira() {
    // Fanfar och konfetti en gång per godkänt förhör (även om föräldern godkänner senare).
    const s = this._s;
    if (!s || s.kan_valja) return;
    const vecka = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    const f = [...(s.data.forhor || [])].reverse().find((x) => x.bedomning === "godkant" && (x.bedomd || x.klart || "") >= vecka);
    if (!f) return;
    const nyckel = `skolan_fh_firad_${s.barn}`;
    let firade = [];
    try { firade = JSON.parse(localStorage.getItem(nyckel) || "[]"); } catch (e) { /* ok */ }
    if (firade.includes(f.id)) return;
    try { localStorage.setItem(nyckel, JSON.stringify([...firade, f.id].slice(-30))); } catch (e) { /* ok */ }
    const lugn = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const el = document.createElement("div");
    el.id = "skolan-konfetti";
    el.innerHTML = `<style>
      #skolan-konfetti{position:fixed;inset:0;z-index:10000;pointer-events:none;overflow:hidden}
      #skolan-konfetti i{position:absolute;top:-20px;width:10px;height:16px;border-radius:2px;animation:sk-fall var(--t) cubic-bezier(.3,.6,.5,1) var(--d) forwards}
      #skolan-konfetti .sk-text{position:absolute;left:50%;top:30%;transform:translate(-50%,-50%) scale(.3);font:800 44px/1.1 system-ui,sans-serif;color:#fff;
        text-align:center;text-shadow:0 3px 0 #b8860b,0 6px 18px rgba(0,0,0,.45);animation:sk-pop 2.8s ease-out forwards;white-space:nowrap}
      #skolan-konfetti .sk-text small{display:block;font-size:20px;font-weight:700;margin-top:6px}
      @keyframes sk-fall{0%{transform:translate(0,0) rotate(0)}100%{transform:translate(var(--x),110vh) rotate(var(--r));opacity:.9}}
      @keyframes sk-pop{0%{transform:translate(-50%,-50%) scale(.3);opacity:0}15%{transform:translate(-50%,-50%) scale(1.15);opacity:1}25%{transform:translate(-50%,-50%) scale(1)}80%{opacity:1}100%{opacity:0}}
    </style><div class="sk-text">🎉 GODKÄNT! 🎉<small>${esc(f.namn)}</small></div>`;
    const farger = ["#ff4d6d", "#ffd23f", "#3bceac", "#4d96ff", "#b76eff", "#ff8c42"];
    for (let i = 0; i < (lugn ? 0 : 120); i++) {
      const b = document.createElement("i");
      b.style.cssText = `left:${Math.random() * 100}%;background:${farger[i % farger.length]};--t:${2.2 + Math.random() * 1.8}s;--d:${Math.random() * 0.7}s;--x:${(Math.random() - 0.5) * 240}px;--r:${(Math.random() - 0.5) * 1440}deg;${Math.random() < 0.4 ? "width:8px;height:8px;border-radius:50%;" : ""}`;
      el.appendChild(b);
    }
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4800);
    this._fanfar();
  }

  // Effekt över hela skärmen: stor text, emojis som sprutar ut och ev. konfetti. Respekterar "minska rörelse".
  _fx({ text = "", sub = "", emojis = ["✨"], antal = 26, konfetti = false, farg = "#ffd23f", ljud = false } = {}) {
    const lugn = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    document.getElementById("skolan-fx")?.remove();
    const el = document.createElement("div");
    el.id = "skolan-fx";
    el.innerHTML = `<style>
      #skolan-fx{position:fixed;inset:0;z-index:10000;pointer-events:none;overflow:hidden}
      #skolan-fx .fx-t{position:absolute;left:50%;top:38%;transform:translate(-50%,-50%) scale(.3);font:900 46px/1.1 system-ui,sans-serif;color:#fff;text-align:center;
        text-shadow:0 3px 0 ${farg},0 0 22px ${farg},0 8px 20px rgba(0,0,0,.5);animation:fx-pop 2.2s cubic-bezier(.2,1.4,.4,1) forwards;white-space:nowrap}
      #skolan-fx .fx-t small{display:block;font-size:20px;font-weight:700;margin-top:6px}
      #skolan-fx b{position:absolute;left:50%;top:42%;font-size:var(--s);animation:fx-spruta var(--t) cubic-bezier(.15,.7,.3,1) var(--d) forwards;opacity:0}
      #skolan-fx i{position:absolute;top:-20px;width:10px;height:16px;border-radius:2px;animation:fx-fall var(--t) cubic-bezier(.3,.6,.5,1) var(--d) forwards}
      #skolan-fx .fx-ring{position:absolute;left:50%;top:42%;width:40px;height:40px;margin:-20px;border-radius:50%;border:6px solid ${farg};animation:fx-ring .9s ease-out forwards}
      @keyframes fx-pop{0%{transform:translate(-50%,-50%) scale(.3) rotate(-8deg);opacity:0}18%{transform:translate(-50%,-50%) scale(1.2) rotate(3deg);opacity:1}30%{transform:translate(-50%,-50%) scale(1) rotate(0)}80%{opacity:1}100%{opacity:0;transform:translate(-50%,-60%) scale(1)}}
      @keyframes fx-spruta{0%{opacity:1;transform:translate(-50%,-50%) scale(.3) rotate(0)}70%{opacity:1}100%{opacity:0;transform:translate(calc(-50% + var(--x)),calc(-50% + var(--y))) scale(1.2) rotate(var(--r))}}
      @keyframes fx-fall{0%{transform:translate(0,0) rotate(0)}100%{transform:translate(var(--x),110vh) rotate(var(--r));opacity:.9}}
      @keyframes fx-ring{0%{opacity:1;transform:scale(.2)}100%{opacity:0;transform:scale(9)}}
    </style>${text ? `<div class="fx-t">${text}${sub ? `<small>${sub}</small>` : ""}</div>` : ""}${lugn ? "" : `<div class="fx-ring"></div>`}`;
    if (!lugn) {
      for (let i = 0; i < antal; i++) {
        const b = document.createElement("b"), v = Math.random() * Math.PI * 2, l = 90 + Math.random() * 170;
        b.textContent = emojis[i % emojis.length];
        b.style.cssText = `--x:${Math.cos(v) * l}px;--y:${Math.sin(v) * l - 40}px;--r:${(Math.random() - 0.5) * 720}deg;--t:${0.9 + Math.random() * 0.8}s;--d:${Math.random() * 0.25}s;--s:${22 + Math.random() * 22}px`;
        el.appendChild(b);
      }
      const farger = ["#ff4d6d", "#ffd23f", "#3bceac", "#4d96ff", "#b76eff", "#ff8c42"];
      for (let i = 0; i < (konfetti ? 90 : 0); i++) {
        const c = document.createElement("i");
        c.style.cssText = `left:${Math.random() * 100}%;background:${farger[i % farger.length]};--t:${2 + Math.random() * 1.6}s;--d:${Math.random() * 0.6}s;--x:${(Math.random() - 0.5) * 240}px;--r:${(Math.random() - 0.5) * 1440}deg;${Math.random() < 0.4 ? "width:8px;height:8px;border-radius:50%;" : ""}`;
        el.appendChild(c);
      }
    }
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3200);
    if (ljud) this._fanfar();
  }

  _fanfar() {
    // Egen kort segerfanfar (trumpetlik ton i C-dur).
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      const ac = (this._ac ||= new AC());
      ac.resume?.();
      const ut = ac.createGain();
      ut.gain.value = 0.1;
      ut.connect(ac.destination);
      const t0 = ac.currentTime + 0.05;
      const ton = (f, s, d) => {
        [1, 2.005].forEach((m, k) => {
          const o = ac.createOscillator(), g = ac.createGain();
          o.type = k ? "square" : "sawtooth"; o.frequency.value = f * m;
          g.gain.setValueAtTime(0.0001, t0 + s);
          g.gain.exponentialRampToValueAtTime(k ? 0.25 : 1, t0 + s + 0.02);
          g.gain.setValueAtTime(k ? 0.2 : 0.8, t0 + s + d * 0.7);
          g.gain.exponentialRampToValueAtTime(0.0001, t0 + s + d);
          o.connect(g).connect(ut); o.start(t0 + s); o.stop(t0 + s + d + 0.02);
        });
      };
      [[523, 0, 0.14], [523, 0.16, 0.14], [523, 0.32, 0.14], [659, 0.48, 0.3], [587, 0.8, 0.14], [659, 0.96, 0.14], [784, 1.12, 0.7],
       [392, 1.12, 0.7], [1047, 1.5, 0.6]].forEach(([f, s, d]) => ton(f, s, d));
    } catch (e) { /* inget ljud */ }
  }

  _skickaView(a, g) {
    const v = this._view;
    return `
      <p>Skicka ett förhör på <b>${esc(g.namn)}</b> (${g.par.length} ord) till <b>${esc(this._s.namn)}</b>.
      ${esc(this._s.namn)} får en notis och svarar i Läxspelet. Du får en notis med resultatet.</p>
      ${stavLista(g) ? `<div class="forhor-kort">🔊 Det här är stavningsord. Orden läses upp ett i taget och ${esc(this._s.namn)} skriver dem utan att se dem, som en diktamen.</div>` : `<div class="list">
        ${[0, 1, 2]
          .map(
            (r) => `<button class="row ${v.riktning === r ? "vald-rad" : ""}" data-riktning="${r}">${
              r === 0 ? `${esc(g.sprak[0] || "Ord")} → ${esc(g.sprak[1] || "Översättning")}` : r === 1 ? `${esc(g.sprak[1] || "Översättning")} → ${esc(g.sprak[0] || "Ord")}` : "Blandat"
            }${v.riktning === r ? " ✓" : ""}</button>`
          )
          .join("")}
      </div>`}
      <div class="form" style="margin-top:14px">
        <label>Meddelande (valfritt) <input id="fh-medd" maxlength="200" placeholder="t.ex. Lycka till! /Pappa" value="${esc(v.meddelande || "")}"></label>
      </div>
      <div class="actions"><button class="primary" id="fh-skicka">📨 Skicka förhöret</button></div>`;
  }

  async _forhorAct(op, args = {}) {
    this._busy = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/forhor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, op, ...args }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._nyData(body.data);
      this._msg = null;
      return body;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return null;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _meritKort() {
    const m = this._s.meriter;
    if (!m) return "";
    const n = m.niva;
    const medaljer = Object.keys(m.medaljer || {});
    const ikon = (id) => this._s.medaljlista.find((x) => x.id === id)?.ikon || "🏅";
    const vantar = (m.vantande || [])
      .map((x) => `<div class="vantar">📥 <b>${esc(x.namn)}</b> ${x.idag ? "brukar komma idag" : "kom igår"}. Lägg in den för <b>+${this._s.poang.i_tid} ⭐</b></div>`)
      .join("");
    return `
      ${this._s.kan_valja ? "" : vantar + this._veckokollRad()}
      <button class="merit-kort" id="open-meriter">
        <div class="mk-rad"><span class="mk-niva">Nivå ${n.niva} · ${esc(n.namn)}</span><span>⭐ ${m.saldo}</span></div>
        <div class="progress"><div style="width:${n.procent}%"></div></div>
        <div class="mk-rad small"><span>${n.kvar} meriter till nästa nivå</span><span></span></div>
        ${this._svitRad(m)}
        ${medaljer.length ? `<div class="mk-medaljer">${medaljer.slice(-8).map((id) => `<span>${ikon(id)}</span>`).join("")}</div>` : ""}
      </button>`;
  }

  // ---------- husdjuret ----------
  _djurKort() {
    const m = this._s.meriter;
    if (!m) return "";
    const d = m.djur;
    if (!d) {
      if (this._s.kan_valja) return "";
      return `<div class="djur-kort"><div class="djur-rubrik">🥚 Välj ditt husdjur!</div>
        <div class="small muted">Det växer när du gör läxor och blir hungrigt om du slutar.</div>
        <div class="djur-val">${(this._s.djurlista || []).map((a) => `<button data-djur-val="${a}" class="rit-val">${ritaDjur(a, "glad", 2)}</button>`).join("")}</div></div>`;
    }
    const agg = d.steg === 0;
    const kvar = d.nasta ? d.nasta - d.intjanat : 0;
    return `<div class="djur-kort humor-${d.humor}">
      ${this._djurFigur(d)}
      <div class="djur-info">
        ${this._s.prat && !agg ? `<div class="prat-bubbla">💬 ${esc(this._s.prat)}</div>` : ""}
        <div class="djur-rubrik">${esc(d.namn)} <span class="muted small">· ${d.form ? `${d.form.ikon} ${esc(d.form.namn)}` : esc(d.steg_namn)}</span>${d.element && !agg ? ` <span class="element-bricka" title="Attacker av samma typ gör +25 %">${d.element.namn}</span>` : ""}</div>
        ${this._s.titel ? `<div class="small"><b>${esc(this._s.titel)}</b></div>` : ""}
        ${d.bastis && !agg ? (() => { const k = (this._s.djurbutik || []).find((x) => x.id === d.pa?.kompis);
          return k ? `<div class="bastis-bricka">💞 ${esc(d.namn)} och ${k.ikon} ${esc(k.namn)} är bästisar!</div>` : ""; })() : ""}
        <div class="small">${agg ? `Ägget kläcks om ${kvar} ⭐. Gör läxor för att värma det!` : DJUR_HUMOR[d.humor](esc(d.namn))}</div>
        ${d.art === "🐍" && !agg ? (() => { const dag = idagISO(), n = 1 + [...dag].reduce((s, c) => s + c.charCodeAt(0), 0) % 4; return `<div class="small">🌙 ${esc(d.namn)} äter mardrömmar! I natt: ${"😋".repeat(n)} ${n} st. Extra stark (×1,5) i Sömnträsket och Spökslottet.</div>`; })() : ""}
        ${d.nasta ? `<div class="progress"><div style="width:${Math.min(100, Math.round((d.intjanat / d.nasta) * 100))}%"></div></div>
        <div class="small muted">${kvar} ⭐ kvar tills ${esc(d.namn)} växer</div>` : `<div class="small">👑 ${esc(d.namn)} är en legend!</div>`}
        <div class="djur-knappar"><button class="mini butik-knapp" id="open-hjalp">📚 Plugga med ${esc(d.namn)}</button><button class="mini butik-knapp" id="open-fraga">💬 Fråga ${esc(d.namn)}</button>${this._s.kan_valja ? "" : `<button class="mini butik-knapp" id="open-fokus">⏱️ Fokus</button>`}<button class="mini butik-knapp" id="open-djurbutik">🛍️ Butik</button><button class="mini butik-knapp" id="open-album">🃏 Album${this._s.kort ? ` ${this._s.kort.antal}/${this._s.kort.totalt}` : ""}</button><button class="mini butik-knapp" id="open-rum">🏠 Rummet</button></div>
        <button class="mini butik-knapp" id="open-widget">📱 ${this._s.kan_valja ? `${esc(this._s.namn)}s husdjur` : "Husdjuret"} på hemskärmen</button>
      </div></div>`;
  }

  // Djuret ritat som en bild: bakgrund, kropp med humör-ansikte, saker på rätt plats. stor = i butiken
  _djurFigur(d, stor = false) {
    const sak = (id) => (this._s.djurbutik || []).find((x) => x.id === id);
    const agg = d.steg === 0;
    const pa = d.pa || {};
    const bg = pa.bakgrund ? sak(pa.bakgrund) : null;
    const eff = pa.effekt && !agg ? sak(pa.effekt) : null;
    const hatt = pa.hatt && !agg ? sak(pa.hatt) : null;
    const kompis = pa.kompis && !agg ? sak(pa.kompis) : null;
    const px = stor ? 220 : 128;
    const standard = { glad: "linear-gradient(160deg,#e8f5e9,#a5d6a7)", nojd: "linear-gradient(160deg,#e3f2fd,#90caf9)",
      hungrig: "linear-gradient(160deg,#fff8e1,#ffcc80)", ledsen: "linear-gradient(160deg,#eceff1,#b0bec5)" }[d.humor];
    const glod = eff?.glod ? `glod-${eff.glod}` : "";
    return `<div class="djur-scen ${glod} humor-${d.humor}" style="width:${px}px;height:${px}px;background:${bg?.bg || standard}">
      ${ritaDjur(d.art, d.humor, d.steg, { hatt, kompis, eff, deko: bg?.deko, krona: d.steg >= 5 && !hatt, form: d.form,
        variant: d.variant ? (this._s.varianter || []).find((v) => v.id === d.variant) : null })}${kompis && d.bastis ? `<span class="scen-bastis" title="Bästisar!">💞</span>` : ""}</div>`;
  }

  _bgSak(d) {
    return d.pa?.bakgrund ? (this._s.djurbutik || []).find((x) => x.id === d.pa.bakgrund) : null;
  }
  _bgKlass(d) { return this._bgSak(d) ? "har-bg" : ""; }
  _bgStil(d) {
    const b = this._bgSak(d);
    return b?.bg ? `background:${b.bg};color:${b.fg || "#fff"};` : "";
  }
  _bgDeko(d) {
    const b = this._bgSak(d);
    return b?.deko ? `<span class="bg-deko">${b.deko}</span>` : "";
  }

  // Gåtor om vilka husdjur kompisarna trivs bäst med. Säger aldrig rakt ut vad det ger.
  static KOMPIS_GATA = {
    k_kyckling: "Längtar hem till bondgården.", k_mus: "Gillar snabbmat… och är konstigt nog inte rädd för katter.",
    k_groda: "Trivs bäst där det är blött och skuggigt.", k_nyckelpiga: "Hänger helst i trädgården bland gröna och saftiga saker.",
    k_snigel: "Vill ha en kompis som inte har så bråttom.", k_fjaril: "Dras till allt som är färgglatt och sött.",
    k_papegoja: "Pratar hela dagarna med djungelns invånare.", k_blackfisk: "Saknar havet och allt som simmar.",
    k_spoke: "Vaknar först när det blir mörkt.", k_robot: "Gillar sånt som är hårt, uråldrigt eller av metall.",
    k_alien: "Kommer uppifrån och gillar det som svävar eller är magiskt.", k_drake: "Vill bara umgås med de vildaste av de vilda.",
    k_enhorning: "Älskar sötsaker och allt som är magiskt.", ps_nalle: "Kramas helst med andra björnar.",
    ps_valp: "Vem har snott min strumpa?!", ps_katt: "Gillar kattdjur… och kanske något litet att jaga.",
    b_zombie: "Gillar sånt som är lite läskigt eller ruttet.", b_spoke: "Letar efter andra som är vakna på natten.",
    g_snogubbe: "Vill helst vara där det är kallt… eller högt uppe i himlen.", g_pepparkaka: "Trivs bäst bland andra bakverk och sötsaker.",
  };

  // En retsam rad om att kompisar kan göra mer än att bara hänga med. Byts varje dag.
  _kompisRetas(d) {
    if (d.bastis) return `<div class="kompis-retas">💞 ${esc(d.namn || "Ditt husdjur")} har hittat sin bästis. Det känns… på något sätt. 😏</div>`;
    const rader = [
      "🤫 Psst… vissa kompisar trivs extra bra med vissa husdjur. Mer än man kan tro.",
      "🤔 Har du märkt att vissa kompisar verkar göra mer än att bara hänga med?",
      "🔍 Läs ledtrådarna noga. Någon här kanske letar efter just ett husdjur som ditt…",
      "😏 Vi säger inget. Men det spelar roll vem du väljer.",
      `👀 ${esc(d.namn || "Ditt husdjur")} har inte hittat sin bästis än…`,
    ];
    return `<div class="kompis-retas">${rader[new Date().getDate() % rader.length]}</div>`;
  }

  _djurbutikView() {
    const s = this._s;
    const d = s.meriter?.djur;
    if (!d) return `<p>Välj ett husdjur på förstasidan först.</p>`;
    const saldo = s.meriter.saldo;
    const titta = s.kan_valja; // föräldrar ser butiken men handlar inte åt barnet
    const typer = [["hatt", "🎩 Hattar och tillbehör"], ["kompis", "🐥 Kompisar"], ["bakgrund", "🖼️ Bakgrunder"], ["effekt", "✨ Effekter"]];
    const kort = (x) => {
      const har = (d.agt || []).includes(x.id);
      const pa = d.pa?.[x.typ] === x.id;
      const last = d.steg < x.steg;
      let knapp;
      if (titta) knapp = pa ? `<span class="small">✅ På</span>` : har ? `<span class="small">Köpt</span>` : `<span class="small muted">${last ? "🔒 " + esc(s.djur_steg[x.steg]) + " · " : ""}${x.pris} ⭐</span>`;
      else if (pa) knapp = `<button class="mini" data-djur-av="${x.typ}">Ta av</button>`;
      else if (har) knapp = `<button class="mini primary" data-djur-pa="${x.id}" data-typ="${x.typ}" data-ikon="${esc(x.ikon || "")}">Ta på</button>`;
      else if (last) knapp = `<span class="small muted">🔒 ${esc(s.djur_steg[x.steg])}</span>`;
      else if (!x.kan_kopas) knapp = `<span class="small muted">Säsong slut</span>`;
      else knapp = `<button class="mini ${saldo >= x.pris ? "primary" : ""}" data-djur-kop="${x.id}" ${saldo >= x.pris ? "" : "disabled"}>${x.pris} ⭐</button>`;
      const gata = x.typ === "kompis" ? SkolanPanel.KOMPIS_GATA[x.id] : "";
      return `<div class="sak-kort ${pa ? "pa" : ""} ${last ? "last" : ""}"><div class="sak-ikon">${x.ikon}${pa && x.typ === "kompis" && d.bastis ? `<span class="bastis-hjarta" title="Bästisar!">💞</span>` : ""}</div><div class="small">${esc(x.namn)}</div>${gata ? `<div class="kompis-gata">${esc(gata)}</div>` : ""}${knapp}</div>`;
    };
    const fmt = (iso) => new Date(iso + "T12:00").toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
    const vanliga = (typ) => (s.djurbutik || []).filter((x) => x.typ === typ && ((!x.hogtid && !x.bara_paket) || (d.agt || []).includes(x.id))).sort((a, b) => a.pris - b.pris);
    const paketKort = (p) => {
      const sakIkon = p.saker.map((id) => (s.djurbutik || []).find((x) => x.id === id)).filter(Boolean)
        .map((x) => `<span title="${esc(x.namn)}">${x.ikon}${x.bara_paket ? "<sup>★</sup>" : ""}</span>`).join("");
      const last = d.steg < p.steg;
      const knapp = titta || p.kopt ? (p.kopt ? `<span class="small">✅ Köpt</span>` : `<b>${p.pris} ⭐</b>`)
        : last ? `<span class="small">🔒 ${esc(s.djur_steg[p.steg])}</span>`
        : `<button class="primary" data-paket="${p.id}" ${saldo >= p.pris ? "" : "disabled"}>${p.pris} ⭐</button>`;
      return `<div class="paket-kort ${p.hogtid ? "sasongs" : ""} ${p.kopt ? "kopt" : ""}">
        ${p.djur ? `<div class="paket-djur">${ritaDjur(p.djur, "glad", 3, {})}<span class="exkl">Bara i paketet!</span></div>` : `<div class="paket-ikon">${p.ikon}</div>`}
        <div class="paket-info"><div class="djur-rubrik">${p.ikon} ${esc(p.namn)}</div>
          <div class="paket-saker">${sakIkon}</div>
          <div class="small">${p.djur ? "Exklusivt husdjur + " : ""}${p.saker.length} saker · <s>${p.varde} ⭐</s>${p.slutar ? ` · ⏳ till ${fmt(p.slutar)}` : ""}</div>
          ${knapp}</div></div>`;
    };
    const paketHtml = (s.paket || []).length ? `<h3>📦 Paket <span class="small muted">★ = finns bara i paket</span></h3>${s.paket.map(paketKort).join("")}` : "";
    const am = s.karta, mon = am?.monster;
    const med = new Set(am?.uppsattning || []);
    const attackKort = (x) => {
      const last = d.steg < x.steg;
      const upp = x.lvl_pris == null ? `<span class="small">🏆 Max nivå!</span>`
        : titta ? `<span class="small muted">⬆️ ${x.lvl_pris} ⭐</span>`
        : `<button class="mini ${saldo >= x.lvl_pris ? "primary" : ""}" data-attack-upp="${x.id}" ${saldo >= x.lvl_pris ? "" : "disabled"}>⬆️ ${x.lvl_pris} ⭐</button>`;
      const knapp = x.har ? upp
        : titta ? `<span class="small muted">${last ? "🔒 " + esc(s.djur_steg[x.steg]) + " · " : ""}${x.pris} ⭐</span>`
        : last ? `<span class="small muted">🔒 ${esc(s.djur_steg[x.steg])}</span>`
        : `<button class="mini ${saldo >= x.pris ? "primary" : ""}" data-attack-kop="${x.id}" ${saldo >= x.pris ? "" : "disabled"}>${x.pris} ⭐</button>`;
      return `<div class="sak-kort attack-sak ${x.svag ? "svag" : ""} ${last ? "last" : ""}"><div class="sak-ikon">${x.ikon}</div>
        <div class="small"><b>${esc(x.namn)}</b>${x.har ? ` <span class="attack-lvl">Nv ${x.lvl}</span>` : ""}</div>
        ${x.har ? `<div class="attack-stjarnor">${"★".repeat(x.lvl)}${"☆".repeat(x.lvl_max - x.lvl)}</div>` : ""}
        <div class="small muted">${x.har ? x.skada_lvl : x.skada} skada${x.har && x.skada_nasta ? ` → <b>${x.skada_nasta}</b>` : ""} · ${x.energi} ⚡</div>
        <div class="small muted">${esc(x.info)}</div>${x.svag ? `<div class="small">🎯 Bra mot nivå ${am.niva}!</div>` : ""}
        ${x.pass > 1 ? `<div class="passform bra">💪 Passar ${esc(d.namn)}: +25 %</div>` : x.pass < 1 ? `<div class="passform dalig">😕 Passar inte ${esc(d.namn)}: −25 %</div>` : ""}
        ${x.ladd ? `<div class="small">🌟 Laddas ${x.ladd} · ${x.ganger}× per strid</div>` : ""}${knapp}
        ${x.har && !titta ? (med.has(x.id) ? `<button class="mini upps-med" data-upps="${x.id}" ${am.boss_las ? "disabled" : ""}>✅ Med i striden</button>`
          : `<button class="mini" data-upps="${x.id}" ${am.boss_las || med.size >= am.uppsattning_max ? "disabled" : ""}>➕ Ta med</button>`) : ""}</div>`;
    };
    const attackHtml = am ? `<h3>⚔️ Attacker för kartan</h3>
      <div class="small muted">Attackerna laddas med ⚡ energi när du pluggar. Varje monster är svagt mot en typ och tar då dubbel skada.</div>
      ${d.element ? `<div class="element-rad">${esc(d.namn)} är ett <b>${d.element.namn}-djur</b>: ${esc(am.typer[d.element.bra])}-attacker gör <b>+25 %</b>, ${esc(am.typer[d.element.dalig])}-attacker <b>−25 %</b>.</div>` : ""}
      <div class="upps-kort"><b>🎒 Stridsuppsättning</b> <span class="small muted">· ${med.size}/${am.uppsattning_max} platser</span>
        <div class="upps-platser">${[...Array(am.uppsattning_max)].map((_, i) => { const x = am.attacker.find((y) => y.id === am.uppsattning[i]); return `<div class="upps-plats ${x ? "" : "tom"}">${x ? `${x.ikon}<small>${esc(x.namn)}</small>` : "<small>tom</small>"}</div>`; }).join("")}</div>
        <div class="small muted">I arenan och mot världsbossar får ${esc(d.namn)} bara använda de här ${am.uppsattning_max}. Välj efter motståndaren! ${am.boss_las ? "<b>🔒 Låst tills bossen är besegrad.</b>" : ""}</div></div>
      <div class="sak-rutnat">${am.attacker.filter((x) => !x.ladd).map(attackKort).join("")}</div>
      <h3>🌟 Laddattacker</h3>
      <div class="small muted">Kostar ingen ⚡ men måste laddas upp med bra träffar. Träffa motståndarens svaga punkt så laddas de snabbare. Fungerar bara i arenan och mot världsbossar, och tar en plats i uppsättningen.</div>
      <div class="sak-rutnat">${am.attacker.filter((x) => x.ladd).map(attackKort).join("")}</div>
      <h3>⚡ Energi</h3>
      <div class="small muted">Du har ⚡ ${am.energi} av ${am.energi_max}. Pluggar du får du 1 ⚡ per ${am.p_energi} ⭐ och behåller stjärnorna. Du kan också köpa energi, högst ${am.energi_kop_kvar ?? 0} till idag.</div>
      <div class="sak-rutnat">${[1, 3].map((n) => {
        const pris = n * am.energi_pris, kan = saldo >= pris && am.energi + n <= am.energi_max && (am.energi_kop_kvar ?? 0) >= n;
        return `<div class="sak-kort"><div class="sak-ikon">⚡</div><div class="small"><b>${n} energi</b></div>
          ${titta ? `<span class="small muted">${pris} ⭐</span>` : `<button class="mini ${kan ? "primary" : ""}" data-energi-kop="${n}" ${kan && !this._busy ? "" : "disabled"}>${pris} ⭐</button>`}</div>`;
      }).join("")}</div>
      ${this._skoldButik(am, d, saldo, titta)}
      <h3>🧪 Livdrycker</h3>
      <div class="small muted">❤️ ${am.liv} av ${am.liv_max} liv. Monstren slår tillbaka när ${esc(d.namn)} attackerar. Plugga (1 ❤️ per ${am.p_liv} ⭐) eller drick en livdryck. Dryckerna hamnar i ryggsäcken 🎒.</div>
      <div class="sak-rutnat">${(am.drycker || []).map((x) => {
        const last = d.steg < x.steg, fullt = x.antal >= am.dryck_max;
        const knapp = titta ? `<span class="small muted">${x.pris} ⭐</span>`
          : last ? `<span class="small muted">🔒 ${esc(s.djur_steg[x.steg])}</span>`
          : fullt ? `<span class="small">🎒 Fullt</span>`
          : `<button class="mini ${saldo >= x.pris ? "primary" : ""}" data-dryck-kop="${x.id}" ${saldo >= x.pris ? "" : "disabled"}>${x.pris} ⭐</button>`;
        return `<div class="sak-kort ${last ? "last" : ""}"><div class="sak-ikon">${x.ikon}</div><div class="small"><b>${esc(x.namn)}</b></div>
          <div class="small muted">${esc(x.info)}</div><div class="small">🎒 ${x.antal}/${am.dryck_max}</div>${knapp}</div>`;
      }).join("")}</div>` : "";
    const antalAgt = (d.agt || []).length, antalAlla = (s.djurbutik || []).filter((x) => !x.hogtid).length;
    const sasong = (s.hogtider || []).map((h) => {
      const saker = (s.djurbutik || []).filter((x) => x.hogtid === h.id);
      return `<div class="sasong"><h3>${h.ikon} ${esc(h.namn)} <span class="small">· finns till ${fmt(h.slut)}</span></h3><div class="sak-rutnat">${saker.map(kort).join("")}</div></div>`;
    }).join("");
    const nasta = s.nasta_hogtid ? `<div class="small muted center" style="margin:8px 0">🔜 ${s.nasta_hogtid.ikon} ${esc(s.nasta_hogtid.namn)}-saker kommer ${fmt(s.nasta_hogtid.start)}</div>` : "";
    return `
      <div class="djur-kort humor-${d.humor}" style="justify-content:center">${this._djurFigur(d, true)}</div>
      <div class="butik-saldo">${titta ? `${esc(s.namn)} har <b>⭐ ${saldo}</b>. Bara ${esc(s.namn)} kan handla här.` : `Du har <b>⭐ ${saldo}</b> att handla för`}</div>
      <div class="small muted center">Samling: ${antalAgt} saker (${antalAlla} vanliga + säsongssaker)</div>
      ${paketHtml}${sasong}${nasta}${attackHtml}
      ${typer.map(([typ, rubrik]) => `<h3>${rubrik}</h3>${typ === "kompis" ? this._kompisRetas(d) : ""}<div class="sak-rutnat">${vanliga(typ).map(kort).join("")}</div>`).join("")}
      ${titta ? "" : (() => {
        const mina = d.mina || [], har = new Set(mina.map((h) => h.art));
        const paket = (d.agda_djur || []).filter((a) => !har.has(a)), nya = (s.djurlista || []).filter((a) => !har.has(a));
        const pris = s.nytt_djur_pris;
        const elIkon = (a) => { const e = (s.djur_element || {})[a]; return e ? `${(s.typer || {})[e]?.split(" ")[0] || ""}💪 ${(s.typer || {})[(s.element_dalig || {})[e]]?.split(" ")[0] || ""}😕` : ""; };
        return `<h3>🐾 Mina husdjur</h3>
        <div class="small muted">Varje husdjur växer och utvecklas av det du gör medan just det är med dig. Byt gratis mellan dina djur.</div>
        <div class="mina-djur">${mina.map((h) => `<div class="mitt-djur ${h.aktiv ? "aktiv" : ""}"><div class="rit-val">${ritaDjur(h.art, "glad", h.steg, { form: h.form })}</div>
          <div class="small"><b>${esc(h.namn)}</b><br>${h.form ? `${h.form.ikon} ${esc(h.form.namn)}` : esc(h.steg_namn)}<br>${h.element ? h.element.namn : ""}</div>
          ${h.aktiv ? `<div class="small"><b>✅ Med dig nu</b></div>` : `<button class="mini primary" data-djur-till="${h.id}">🔄 Byt</button>`}</div>`).join("")}</div>
        ${paket.length ? `<h3>📦 Dina paketdjur</h3><div class="small muted">Redan betalda. De börjar som ägg.</div><div class="djur-val">${paket.map((a) => `<button data-djur-nytt="${a}" data-gratis="1" class="rit-val med-element">${ritaDjur(a, "glad", 2)}<span class="el">${elIkon(a)}</span></button>`).join("")}</div>` : ""}
        <h3>🥚 Skaffa ett nytt husdjur · ${pris} ⭐</h3>
        <div class="small muted">Det nya djuret börjar om från början: ett ägg utan attacker och kompisar. Dina andra djur finns kvar med allt de har.</div>
        <div class="small muted">Varje djur har ett element. Attacker av samma typ gör +25 %, en typ passar dåligt (−25 %).</div>
        <div class="djur-val">${nya.map((a) => `<button data-djur-nytt="${a}" class="rit-val med-element" ${saldo >= pris ? "" : "disabled"}>${ritaDjur(a, "glad", 2)}<span class="el">${elIkon(a)}</span></button>`).join("")}</div>`;
      })()}
      ${titta ? "" : `<div class="actions"><button class="ghost" id="djur-dop">✏️ Döp om ${esc(d.namn)} (gratis)</button></div>`}`;
  }

  // ---------- läxpasset ----------
  _passKort() {
    const p = this._s.pass;
    if (!p || !this._s.meriter?.djur && this._s.kan_valja) return "";
    const att = p.beloningar.filter((b) => b.niva <= p.niva && !p.hamtat.includes(b.niva)).length;
    const nasta = p.beloningar.find((b) => b.niva === p.niva + 1);
    return `<button class="pass-kort" id="open-pass">
      <div class="djur-rubrik">🎟️ Läxpasset <span>Nivå ${p.niva}/30</span></div>
      <div class="progress"><div style="width:${p.niva >= 30 ? 100 : Math.round((p.xp_i_niva / p.xp_till_nasta) * 100)}%"></div></div>
      <div class="small">${att ? `🎁 <b>${att} belöning${att > 1 ? "ar" : ""} att hämta!</b>` : nasta ? `Nästa: ${nasta.ikon} ${esc(nasta.namn)} · ${p.xp_till_nasta - p.xp_i_niva} XP kvar` : "🌟 Hela passet klart!"} · ⏳ ${p.dagar_kvar} dagar kvar</div>
    </button>`;
  }

  _passView() {
    const s = this._s, p = s.pass;
    const d = s.meriter?.djur;
    const rad = (b) => {
      const nadd = b.niva <= p.niva, hamtad = p.hamtat.includes(b.niva);
      const knapp = s.kan_valja ? (hamtad ? "✅" : nadd ? "🎁" : "🔒")
        : hamtad ? `<span class="small">✅ Hämtad</span>` : nadd ? `<button class="mini primary" data-pass="${b.niva}">Hämta!</button>` : `<span class="small muted">🔒</span>`;
      return `<div class="pass-rad ${nadd ? "nadd" : ""} ${b.typ !== "stjarnor" ? "special" : ""} ${b.niva === 30 ? "final" : ""}">
        <span class="pass-niva">${b.niva}</span><span class="pass-ikon">${b.ikon}</span><span class="pass-namn">${esc(b.namn)}</span>${knapp}</div>`;
    };
    const varianter = (d?.varianter || []).map((id) => (s.varianter || []).find((v) => v.id === id)).filter(Boolean);
    return `
      <div class="forhor-kort">Varje merit du tjänar ger lika mycket <b>XP</b>. Klättra i nivåerna och hämta belöningarna. Passet börjar om den 1:a varje månad, så hinn till nivå 30 för månadens <b>glänsande husdjur</b>! ⏳ ${p.dagar_kvar} dagar kvar.</div>
      <div class="pass-xp">Nivå <b>${p.niva}</b> · ${p.niva >= 30 ? "Klart! 🌟" : `${p.xp_i_niva}/${p.xp_till_nasta} XP till nästa`}</div>
      <div class="pass-lista">${p.beloningar.map(rad).join("")}</div>
      ${varianter.length && !s.kan_valja ? `<h3>🌟 Dina glänsande varianter</h3><div class="djur-val">
        <button data-variant="" class="${!d.variant ? "vald" : ""}">Vanlig</button>
        ${varianter.map((v) => `<button data-variant="${v.id}" class="${d.variant === v.id ? "vald" : ""}">${esc(v.namn)}</button>`).join("")}</div>` : ""}`;
  }

  // ---------- äventyrskartan ----------
  _nivaKort() {
    const k = this._s.karta;
    if (!k) return "";
    const mon = k.monster, d = this._s.meriter?.djur, barn = !this._s.kan_valja;
    const kvar = k.hp - k.skada, anim = this._attackAnim;
    let attacker = "";
    const ko = d && k.liv <= 0;
    const an = this._s.arena;
    let upp = false;
    if (an && d && barn) {
      try {
        const nyckel = `skolan_djurniva_${this._s.barn}`, sedd = Number(localStorage.getItem(nyckel) || 0);
        if (sedd && an.niva.niva > sedd) upp = true;
        if (!sedd || an.niva.niva > sedd) setTimeout(() => { try { localStorage.setItem(nyckel, an.niva.niva); } catch (e) { /* privat läge */ } }, 8000);
      } catch (e) { /* privat läge */ }
    }
    const livRad = d ? `${upp ? `<div class="niva-upp">⬆️ ${esc(d.namn)} nådde nivå ${an.niva.niva}! Mer ❤️ liv och 💪 starkare attacker.</div>` : ""}${an ? `<div class="small djur-niva">⬆️ Nivå ${an.niva.niva} · 💪 CP ${an.cp} · ${this._defText(k.forsvar)}${an.niva.till ? ` · <span class="muted">${an.niva.xp - an.niva.fran}/${an.niva.till - an.niva.fran} XP</span>` : ""}</div>` : ""}<div class="liv-rad"><span>❤️ ${esc(d.namn)}</span><div class="progress djur-liv ${k.liv / k.liv_max < 0.3 ? "lag" : ""}"><div style="width:${Math.round((k.liv / k.liv_max) * 100)}%"></div></div><b>${k.liv}/${k.liv_max}</b></div>
      ${barn && (k.drycker || []).some((x) => x.antal) ? `<div class="attack-rad">🎒 ${(k.drycker || []).filter((x) => x.antal).map((x) => {
        const kan = !this._busy && (x.id === "d_fenix" ? ko : k.liv < k.liv_max);
        return `<button class="mini dryck-knapp" data-dryck="${x.id}" ${kan ? "" : "disabled"} title="${esc(x.namn)}: ${esc(x.info)}">${x.ikon} ×${x.antal}</button>`;
      }).join("")}</div>` : ""}
      ${ko ? `<div class="small ko-text">😵 ${esc(d.namn)} är utmattad. Plugga för att få tillbaka liv${barn ? ", eller drick en livdryck 🧪" : ""}.</div>` : ""}` : "";
    if (d && barn) {
      const boss = !!k.ladd, med = new Set(k.uppsattning || []);
      const mina = (k.attacker || []).filter((x) => x.har && (boss ? med.has(x.id) : !x.ladd));
      const laddKan = (x) => !x.ladd || (boss && k.ladd.p >= x.ladd && (k.ladd.anv?.[x.id] || 0) < x.ganger);
      attacker = mina.length
        ? `<div class="attack-rad"><span class="energi" title="Energi">⚡ ${k.energi}</span>${mina.map((x) => {
            const slut = x.slut || (x.ladd && (k.ladd?.anv?.[x.id] || 0) >= x.ganger);
            const kan = !slut && !ko && k.energi >= x.energi && !this._busy && laddKan(x);
            return `<button class="attack-knapp ${x.svag ? "svag" : ""}" data-attack="${x.id}" ${kan ? "" : "disabled"} title="${esc(x.namn)}: ${esc(x.info)}">
              <span class="ai">${x.ikon}</span><b>${x.nu}${x.pass > 1 ? "💪" : x.pass < 1 ? "😕" : ""}</b><small>${slut ? "använd" : x.energi + "⚡"}</small></button>`;
          }).join("")}</div>
          <div class="small muted">1 ⚡ per ${k.p_energi} ⭐ du tjänar (max ${k.energi_max})</div>
          ${boss ? `${this._laddRad(k.ladd.p, k.ladd.max)}<div class="small muted">⚔️ Bosstrid: bara din stridsuppsättning${k.boss_las ? " (låst tills bossen är besegrad)" : ""}. Träffa bossens svaga punkt så laddas 🌟 snabbare!</div>` : ""}`
        : `<div class="small">⚔️ ⚡ ${k.energi} energi · lär ${esc(d.namn)} attacker i <button class="mini butik-knapp" id="open-djurbutik">🛍️ Butiken</button></div>`;
    }
    const sen = k.klara?.length ? k.klara[k.klara.length - 1] : null;
    return `<div class="boss-kort ${mon.boss ? "varldsboss" : ""}" style="--varld:${mon.varld.farg}">
      ${anim ? `<div class="attack-anim"><div class="anim-djur">${ritaDjur(d.art, "glad", Math.max(1, d.steg), {})}</div><div class="anim-skott">${anim.ikon}</div>
        <div class="anim-skada ${anim.svag ? "svag" : ""}">−${anim.skada}${anim.svag ? "<small>SVAG PUNKT!</small>" : ""}${anim.klar ? "<small>NIVÅ KLAR! 🎉</small>" : ""}</div></div>` : ""}
      <div class="boss-figur ${anim ? "traff" : ""}">${mon.ikon}</div>
      <div class="djur-info">
        <div class="djur-rubrik">${mon.varld.ikon} Nivå ${k.niva}${mon.boss ? ` · 👑 ${esc(mon.namn)}` : ""}</div>
        ${VARLD_BERATTELSE[mon.varld.id] ? `<div class="varld-berattelse">📖 ${esc(VARLD_BERATTELSE[mon.varld.id][mon.boss ? 1 : 0])}</div>` : ""}
        <div class="progress boss-hp"><div style="width:${Math.round((kvar / k.hp) * 100)}%"></div></div>
        <div class="small">❤️ ${kvar} av ${k.hp} liv · 🎯 svag mot <b>${k.typer[mon.svag]}</b></div>
        ${(k.mon_attacker || []).length ? `<div class="small mon-kan">⚠️ Monstren här kan slå tillbaka med ${k.mon_attacker.map((x) => `<span title="${esc(x.namn)}">${x.ikon}</span>`).join(" ")}</div>` : ""}
        <div class="small muted">Varje merit du tjänar gör skada.${mon.boss && mon.sak ? ` Besegra bossen för ${mon.sak.ikon} ${esc(mon.sak.namn)}!` : ""}${sen ? ` Senast: nivå ${sen.niva} ${"⭐".repeat(sen.stjarnor)}` : ""}</div>
        ${livRad}
        ${d ? `<button class="mini primary strid-knapp" id="till-strid">${barn ? "⚔️ Till strid" : "👀 Se striden"}</button>` : ""}${d && barn ? ` <button class="mini primary strid-knapp" id="glosstrid-val">📝 Glosstrid</button>` : ""}
        ${attacker}
        ${this._reprisRad()}
        <button class="mini karta-knapp" id="open-karta">🗺️ Kartan · ⭐ ${k.stjarnor_tot}</button>${d ? ` <button class="mini karta-knapp" id="open-arena">🏟️ Arenan${this._s.arena?.pagar ? " ⚔️" : ""}</button>` : ""}${barn ? ` <button class="mini karta-knapp" id="open-till">🤝 Plugga ihop${this._tillNy ? " 🆕" : ""}</button>` : ""}${this._s.lag || this._s.lag_lista ? ` <button class="mini karta-knapp" id="open-lag">${this._s.lag ? `${this._s.lag.marke} Laget${this._s.lag.bonus ? ` · +${this._s.lag.bonus_pct} %` : ""}${this._s.lagstrid?.pagar ? " ⚔️" : ""}` : "🏳️ Lag"}</button>` : ""}${this._vanner ? ` <button class="mini karta-knapp" id="open-vanner">🤝 Vänner${this._vanner.inkommande.length ? ` (${this._vanner.inkommande.length})` : ""}</button>` : ""}
      </div></div>`;
  }

  _traningKort(a, d, barn) {
    const t = a.traning;
    if (!t) return "";
    const saldo = this._s.meriter?.saldo ?? 0, n = t.nasta;
    return `<div class="card traning-kort"><b>🎓 Försvarsträning: ${esc(t.namn)} (${t.niva}/${t.max})</b>
      <div class="small">När någon annan utmanar ${esc(d.namn)} styr datorn hen. Tränade husdjur slåss smartare och tar i mer${t.niva ? `: <b>+${t.liv} % liv och +${t.skada} % skada</b> när ${esc(d.namn)} försvarar sig` : ""}. Den som anfaller kan förlora!</div>
      ${n ? `<div class="small muted">Nästa: ${esc(n.namn)} · +${n.liv} % liv, +${n.skada} % skada${n.niva >= 2 ? " · ser när den kan slå ut" : ""}${n.niva >= 4 ? " · sparar energi till starkaste draget" : ""}</div>
        ${barn ? `<button class="mini ${saldo >= n.pris ? "primary" : ""}" id="traning-kop" ${saldo >= n.pris && !this._busy ? "" : "disabled"}>🎓 Träna · ${n.pris} ⭐</button>` : `<span class="small muted">${n.pris} ⭐</span>`}`
        : `<div class="small">🏅 Fullt tränad!</div>`}</div>`;
  }

  _defText(f) {
    if (!f) return "🛡️ DEF 0";
    const sk = (f.skoldar || []).find((x) => x.id === f.pa);
    return `${sk ? sk.ikon : "🛡️"} DEF ${f.def}${f.def ? ` <span class="muted">(−${f.minskar} % skada)</span>` : ""}`;
  }

  _skoldButik(am, d, saldo, titta) {
    const f = am.forsvar;
    if (!f) return "";
    const typer = am.typer || {};
    const kort = (x) => {
      const last = d.steg < x.steg, pa = f.pa === x.id;
      const knapp = x.har
        ? (titta ? `<span class="small">${pa ? "✅ På" : "✅ Har"}</span>`
          : pa ? `<button class="mini" data-skold-pa="">✅ På · ta av</button>` : `<button class="mini primary" data-skold-pa="${x.id}">Ta på</button>`)
        : titta ? `<span class="small muted">${last ? "🔒 " + esc(this._s.djur_steg[x.steg]) + " · " : ""}${x.pris} ⭐</span>`
        : last ? `<span class="small muted">🔒 ${esc(this._s.djur_steg[x.steg])}</span>`
        : `<button class="mini ${saldo >= x.pris ? "primary" : ""}" data-skold-kop="${x.id}" ${saldo >= x.pris && !this._busy ? "" : "disabled"}>${x.pris} ⭐</button>`;
      const bra = x.mot && x.mot === am.slag;
      return `<div class="sak-kort ${last ? "last" : ""} ${pa ? "vald" : ""} ${bra ? "svag" : ""}"><div class="sak-ikon">${x.ikon}</div>
        <div class="small"><b>${esc(x.namn)}</b></div><div class="small">🛡️ DEF ${x.def}</div>
        <div class="small muted">${esc(x.info)}</div>${bra ? `<div class="small">🎯 Bra mot nivå ${am.niva}!</div>` : ""}${knapp}</div>`;
    };
    return `<h3>🛡️ Sköldar</h3>
      <div class="small muted">${esc(d.namn)} har ${this._defText(f)}. Skadan blir skada × ${am.def_halv} / (${am.def_halv} + DEF). Skölden följer med om du byter husdjur. Monstren på nivå ${am.niva} slår med ${typer[am.slag] || "💥 Kraft"}.</div>
      <div class="sak-rutnat">${f.skoldar.map(kort).join("")}</div>`;
  }

  // ---------- skolan och läraren ----------
  // En post i inkorgen från läraren: veckobrev, studiematerial eller provresultat.
  _inkorgRad(x) {
    const typ = x.typ || "veckobrev";
    const fil = x.fil ? ` <button class="mini" data-open-fil="${esc(x.fil.namn)}">${x.fil.mime === "application/pdf" ? "📄" : "🖼️"} Öppna</button>` : "";
    const bort = ` <button class="mini" data-ink-avvisa="${x.id}">🗑️</button>`;
    if (typ === "veckobrev")
      return `<li>📬 <b>${esc(x.titel)}</b>${x.vecka ? ` · v.${esc(x.vecka)}` : ""}${x.fil ? `<div class="small muted">Brevet är bifogat. Läxspelet läser det när du granskar.</div>` : ""}
        <button class="mini primary" data-ink-granska="${x.id}">👀 Granska och lägg in</button>${fil}${bort}</li>`;
    if (typ === "schema")
      return `<li>🗓️ <b>${esc(x.titel)}</b> · schema från läraren${x.text ? `<div class="small muted">${esc(x.text)}</div>` : ""}
        <button class="mini primary" data-ink-schema="${x.id}">👀 Granska och lägg in</button>${fil}${bort}</li>`;
    const amnen = this._s.data?.amnen || [];
    const traff = amnen.find((a) => x.amne && a.namn.toLowerCase() === x.amne.toLowerCase()) || amnen.find((a) => x.amne && a.namn.toLowerCase().includes(x.amne.toLowerCase()));
    const val = `<select class="ink-amne" data-ink-amne="${x.id}">${x.amne && !traff ? `<option value="ny:${esc(x.amne)}">➕ Nytt ämne: ${esc(x.amne)}</option>` : ""}
      ${amnen.map((a) => `<option value="${a.id}" ${traff?.id === a.id ? "selected" : ""}>${esc(a.namn)}</option>`).join("")}
      ${!x.amne ? `<option value="">Välj ämne…</option>` : ""}</select>`;
    const r = x.resultat;
    const res = r ? ("max" in r ? `${r.poang} av ${r.max} poäng` : `betyg ${esc(r.betyg)}`) : "";
    return `<li>${typ === "prov" ? "📝" : "📎"} <b>${esc(x.titel)}</b>${x.amne ? ` · ${esc(x.amne)}` : ""}
      ${typ === "prov" ? `<div>${res ? `Resultat: <b>${res}</b>` : "Rättat prov"}${r?.kommentar ? ` · ”${esc(r.kommentar)}”` : ""}</div>` : ""}
      ${x.text ? `<div class="small muted">${esc(x.text)}</div>` : ""}
      <div class="small">Spara i ${val}</div>
      <button class="mini primary" data-ink-spara="${x.id}" data-ink-typ="${typ}">💾 ${typ === "prov" ? "Spara resultatet" : "Spara i ämnet"}</button>${fil}${bort}</li>`;
  }

  async _skolaAct(body, ok) {
    if (this._busy) return null;
    this._busy = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/skola", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ barn: this._s.barn, ...body }) });
      const svar = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(svar.message || res.statusText);
      if (!svar.forslag) this._s.skola = { ...this._s.skola, ...svar };
      if (ok) this._msg = { type: "ok", text: ok };
      return svar;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return null;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _klassSynk(ny = false) {
    const k = this._s.skola;
    if (!k?.lank) return;
    let url = !ny && k.larare?.url;
    if (!url) {
      const adr = this._ask("Skriv adressen som syns i lärarens app (t.ex. 192.168.1.20:8770)", "");
      if (!adr) return;
      url = /^https?:\/\//.test(adr) ? adr.replace(/\/+$/, "") : `http://${adr.trim()}`;
    }
    window.open(`${url}/elev#${encodeURIComponent(k.lank)}`, "_blank");
  }

  _klassKort() {
    const k = this._s.skola;
    if (!k || !k.lank) return "";
    const kl = k.klass, kvar = kl ? Math.max(0, kl.hp - kl.skada) : 0;
    return `<div class="card"><b>🏫 Klassen${k.larare?.klass ? `: ${esc(k.larare.klass)}` : ""}</b>
      ${kl ? `<div class="small">Klassens boss: ${esc(kl.ikon)} ${esc(kl.boss)} · ❤️ ${kvar} av ${kl.hp} kvar · ${kl.antal} elever med</div>
        <div class="progress boss-hp"><div style="width:${Math.round((kvar / kl.hp) * 100)}%"></div></div>
        <div class="small muted">Allt du pluggar hjälper klassen. Klarar ni bossen får alla ${30} ⭐. Synka på lektionen så räknas ditt plugg.</div>` : ""}
      ${(k.grupper || []).map((g) => `<div class="grupp-kort"><b>👥 ${esc(g.namn)}</b> <span class="small muted">med ${g.medlemmar.map(esc).join(", ")}</span>
        <div>${esc(g.uppgift) || "<span class='muted'>Ingen uppgift än</span>"}${g.datum ? ` <span class="small muted">· klar senast ${esc(g.datum)}</span>` : ""}</div>
        ${g.klar ? `<div class="small">✅ Du har bockat av uppgiften. Läraren ser det när du synkar.</div>` : `<button class="mini primary" data-grupp-klar="${g.id}">✔️ Vi är klara</button>`}</div>`).join("")}
      ${k.larare?.url ? `<button class="primary" id="klass-synk">🔄 Synka med läraren</button> <button class="mini" id="klass-anslut">Annan lärare</button>`
        : `<div class="small muted">Be läraren visa adressen i lärarappen.</div><button class="primary" id="klass-anslut">🏫 Anslut till läraren</button>`}
      ${k.larare?.synkad ? `<div class="small muted">Senast synkad ${new Date(k.larare.synkad).toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" })}</div>` : ""}</div>`;
  }

  _skolaView() {
    const k = this._s.skola, s = this._s;
    if (!k) return `<p class="muted">Hämtar…</p>`;
    const f = k.foralder || {}, lar = k.larare, inst = lar?.inst || {};
    const vd = ["mån", "tis", "ons", "tor", "fre", "lör", "sön"];
    const larText = (id) => id === "mejl" && !lar ? "inte kopplad (ditt val räcker)" : !lar ? "inte kopplad än" : inst[id] ? "✅ på" : "❌ av";
    const sm = k.smtp || {};
    return `<p class="small muted">Du och läraren bestämmer tillsammans. En funktion är bara på när <b>båda</b> har slagit på den: du här och läraren i lärarappen.</p>
      <div class="card"><b>Vad ska vara på?</b>
        ${k.funktioner.map((x) => `<div class="sk-rad"><label class="kap-rad"><input type="checkbox" data-sk-f="${x.id}" ${f[x.id] ? "checked" : ""} ${this._busy ? "disabled" : ""}> ${x.ikon} <b>${esc(x.namn)}</b></label>
          <div class="small muted">${esc(x.info)}</div>
          <div class="small">Läraren: ${larText(x.id)} · ${k.aktiv[x.id] ? "<b>🟢 Aktiv</b>" : "⚪ Inte aktiv"}</div></div>`).join("")}</div>
      <div class="card"><b>Läraren</b>
        <label class="small">Namnet läraren ser <input id="sk-namn" maxlength="40" value="${esc(f.namn || "")}" placeholder="${esc(s.namn)}"></label>
        <label class="small">Lärarens e-post <input id="sk-mejl" type="email" value="${esc(f.mejl_till || "")}" placeholder="larare@skolan.se"></label>
        <div class="small">Skicka e-postrapporten dessa dagar kl. 18:</div>
        <div class="lag-marken">${vd.map((d, i) => `<label><input type="checkbox" data-sk-dag="${i}" ${(f.mejl_dagar || []).includes(i) ? "checked" : ""}> ${d}</label>`).join("")}</div>
        <button class="primary" id="sk-spara">💾 Spara</button>
        ${lar ? `<div class="small" style="margin-top:8px">🏫 Kopplad till <b>${esc(lar.namn || "läraren")}</b>${lar.klass ? `, ${esc(lar.klass)}` : ""} · senast synkad ${esc((lar.synkad || "").replace("T", " "))}</div><button class="mini" id="sk-koppla-bort">Koppla bort läraren</button>` : ""}
        <div class="small" style="margin-top:8px"><b>Klasslänk</b> (läraren behöver den för att synka; eleven skickar den när hen ansluter på lektionen)</div>
        ${k.lank ? `<div class="small muted" style="word-break:break-all">${esc(k.lank)}</div><button class="mini" id="sk-kopiera">📋 Kopiera</button>` : `<div class="small muted">${k.kan_nas ? "Slå på något ovan först." : "Home Assistant behöver gå att nå utifrån (t.ex. Nabu Casa)."}</div>`}</div>
      ${k.inkorg?.length ? `<h3>📬 Från läraren</h3><ul class="lista">${k.inkorg.map((x) => this._inkorgRad(x)).join("")}</ul>` : ""}
      <details class="card"><summary><b>📧 E-post (SMTP)</b> ${sm.har_losen ? "✅ inställd" : "– behövs för rapport via e-post"}</summary>
        <div class="small muted">Home Assistant har ingen e-posttjänst, så Läxspelet skickar själv. För Gmail: server smtp.gmail.com, port 587 och ett <b>applösenord</b> (inte ditt vanliga lösenord). Lösenordet sparas bara i din Home Assistant.</div>
        <label class="small">Server <input id="smtp-server" value="${esc(sm.server || "smtp.gmail.com")}"></label>
        <label class="small">Port <input id="smtp-port" type="number" value="${esc(sm.port || 587)}"></label>
        <label class="small">Användare <input id="smtp-anv" value="${esc(sm.anvandare || "")}" autocomplete="off"></label>
        <label class="small">Från (avsändare) <input id="smtp-fran" value="${esc(sm.fran || "")}" placeholder="samma som användare"></label>
        <label class="small">Lösenord <input id="smtp-losen" type="password" autocomplete="new-password" placeholder="${sm.har_losen ? "oförändrat" : ""}"></label>
        <button class="primary" id="sk-smtp">💾 Spara e-post</button>
        <label class="small">Skicka testrapport till <input id="sk-test-till" type="email" placeholder="din egen adress"></label>
        <button class="mini" id="sk-test">📧 Skicka test</button></details>`;
  }

  // ---------- plugga ihop: pluggstund och glosduell ----------
  async _tillLoad() {
    try {
      const res = await this._hass.fetchWithAuth(`/api/skolan/tillsammans?barn=${encodeURIComponent(this._s?.barn || "")}`);
      if (!res.ok) return;
      this._till = await res.json();
      const jag = this._till.jag;
      this._tillNy = (this._till.stunder || []).some((s) => s.deltagare.some((d) => d.ref === jag && !d.med))
        || (this._till.dueller || []).some((x) => !x.slut && x.folk.some((f) => f.ref === jag && !f.med));
      this._render();
    } catch (e) { /* nätverk */ }
  }

  async _tillAct(body, ok) {
    if (this._busy) return false;
    this._busy = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/tillsammans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ barn: this._s.barn, ...body }) });
      const svar = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(svar.message || res.statusText);
      if (ok) this._msg = { type: "ok", text: ok };
      await this._tillLoad();
      return svar;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _duellPoll() {
    if (this._duellTimer) return;
    this._duellTimer = setInterval(() => {
      if (this._view?.name !== "duell") { clearInterval(this._duellTimer); this._duellTimer = null; return; }
      const x = (this._till?.dueller || []).find((y) => y.id === this._view.id);
      if (x?.slut) { clearInterval(this._duellTimer); this._duellTimer = null; this._load(); }
      if (!this._shadowInputAktiv()) this._tillLoad();
    }, 3000);
  }

  _shadowInputAktiv() {
    const el = this.shadowRoot.activeElement;
    return el && el.id === "duell-svar" && el.value;
  }

  async _duellSvara(id, i, svar) {
    if (this._busy) return;
    const x = (this._till?.dueller || []).find((y) => y.id === id);
    const res = await this._tillAct({ op: "duell_svara", id, i, svar });
    if (res) {
      this._duellSenast = { i, ratt: res.ratt, svar };
      this._duellFokus = false;
      if (x && res.ratt) navigator.vibrate?.(30);
    }
  }

  _tillView() {
    const t = this._till, barn = !this._s.kan_valja;
    if (!t) return `<p class="muted">Hämtar…</p>`;
    const jag = t.jag, komp = t.kompisar || [];
    const bar = (d, mal) => `<div class="progress"><div style="width:${Math.min(100, Math.round((d.poang / mal) * 100))}%"></div></div>`;
    const stunder = (t.stunder || []).map((s) => {
      const mig = s.deltagare.find((d) => d.ref === jag);
      return `<div class="card stund ${s.klar ? "klar" : ""}"><b>🤝 Pluggstund ${new Date(s.start).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" })}</b>
        ${s.deltagare.map((d) => `<div class="stund-rad"><span>${d.ref === jag ? "Du" : esc(d.namn)}${d.med ? "" : " <span class='muted small'>(inte med än)</span>"}</span>${bar(d, s.mal)}<b>${Math.min(d.poang, s.mal)}/${s.mal} ⭐</b></div>`).join("")}
        ${s.klar ? `<div>🎉 Alla klarade det! +${s.bonus} ⭐ till var och en.</div>`
          : mig && !mig.med ? (barn ? `<button class="primary" data-stund-med="${s.id}">🙋 Gå med</button>` : "")
          : `<div class="small muted">Alla som är med ska tjäna ${s.mal} ⭐ innan midnatt. Då får alla +${s.bonus} ⭐.</div>`}</div>`;
    }).join("");
    const dueller = (t.dueller || []).slice().reverse().map((x) => {
      const mig = x.folk.find((f) => f.ref === jag), de = x.folk.find((f) => f.ref !== jag);
      const status = x.slut ? (x.vinnare.length > 1 ? "🤝 Oavgjort" : x.vinnare.includes(jag) ? "🥇 Du vann" : `${esc(de?.namn || "")} vann`)
        : !mig.med ? "Du är utmanad!" : !de?.med ? "Väntar på svar…" : "Pågår";
      const knapp = !x.slut && !mig.med && barn ? `<button class="mini primary" data-duell-med="${x.id}">⚔️ Anta</button>`
        : `<button class="mini" data-duell-se="${x.id}">${!x.slut && mig.med && !mig.klar ? "▶️ Spela" : "👀 Se"}</button>`;
      return `<li>⚔️ <b>${esc(x.namn)}</b> mot ${esc(de?.namn || "?")} · ${status} ${mig.med ? `· ${mig.ratt}/${x.antal}` : ""} ${knapp}</li>`;
    }).join("");
    const glosor = t.glosor || [];
    return `${this._klassKort()}<p class="small muted">Plugga ihop med ${t.vanner_pa ? "syskon och kompisar" : "syskon"}! ${t.vanner_pa ? "Kompisar i andra hem ser bara ditt smeknamn och dina poäng." : ""}</p>
      ${stunder || ""}
      ${barn && komp.length ? `<div class="card"><b>🤝 Starta en pluggstund</b>
        <div class="small muted">Ni pluggar samtidigt i kväll. Når alla som är med ${t.stund_mal} ⭐ får alla +${t.stund_bonus} ⭐ (och lagbossen tar skada).</div>
        ${komp.map((k) => `<label class="kap-rad"><input type="checkbox" data-stund-gast="${esc(k.ref)}"> ${esc(k.namn)} ${k.typ === "van" ? "🤝" : ""}</label>`).join("")}
        <button class="primary" id="stund-ny" ${this._busy ? "disabled" : ""}>🤝 Starta pluggstund</button></div>` : ""}
      ${dueller ? `<h3>⚔️ Glosdueller</h3><ul class="lista">${dueller}</ul>` : ""}
      ${barn && komp.length ? `<div class="card"><b>⚔️ Utmana till glosduell</b>
        <div class="small muted">Ni får samma ${10} ord. Flest rätt vinner, och vid lika vinner den snabbaste. Alla som spelar klart får ${t.duell_delta} ⭐, vinnaren ${t.duell_delta + t.duell_vinst} ⭐.</div>
        ${glosor.length ? `<label class="small">Glosor <select id="duell-glosa">${glosor.map((g) => `<option value="${g.amne}|${g.id}">${esc(g.amne_namn)}: ${esc(g.namn)} (${g.antal})</option>`).join("")}</select></label>
        <label class="small">Mot <select id="duell-gast">${komp.map((k) => `<option value="${esc(k.ref)}">${esc(k.namn)}</option>`).join("")}</select></label>
        <button class="primary" id="duell-ny" ${this._busy ? "disabled" : ""}>⚔️ Utmana</button>` : `<p class="small muted">Du har inga glosor att duellera med än.</p>`}</div>` : ""}
      ${!komp.length ? `<p class="muted">Det finns ingen att plugga ihop med än.</p>` : ""}`;
  }

  _duellView(id) {
    const t = this._till, x = (t?.dueller || []).find((y) => y.id === id);
    if (!x) return `<p class="muted">Hämtar…</p>`;
    const jag = t.jag, mig = x.folk.find((f) => f.ref === jag), de = x.folk.find((f) => f.ref !== jag);
    const rad = (f, namn) => `<div class="stund-rad"><span>${namn}</span><div class="progress duell-bar"><div style="width:${Math.round((f.besvarade / x.antal) * 100)}%"></div></div><b>✅ ${f.ratt}</b></div>`;
    const topp = `<div class="card">${rad(mig, "Du")}${de ? rad(de, esc(de.namn) + (de.med ? "" : " <span class='muted small'>(inte med än)</span>")) : ""}</div>`;
    const sen = this._duellSenast;
    const senText = sen ? `<div class="duell-senast ${sen.ratt ? "ratt" : "fel"}">${sen.ratt ? "✅ Rätt!" : "❌ Fel"}</div>` : "";
    if (x.slut) {
      const vann = x.vinnare.includes(jag), lika = x.vinnare.length > 1;
      if (vann && !lika && !this._duellFirad?.[id]) { (this._duellFirad ||= {})[id] = true; setTimeout(() => this._fanfar?.(), 100); }
      return `${topp}<div class="ls-slut ${vann ? "vinst" : ""}">${lika ? "🤝 Oavgjort!" : vann ? "🥇 Du vann!" : `${esc(de?.namn || "")} vann!`}</div>
        <p class="small">Du fick ${mig.ratt} av ${x.antal} rätt${mig.tid != null ? ` på ${mig.tid} s` : ""}.</p>
        ${x.facit ? `<details><summary>Facit</summary><ul class="lista">${x.fragor.map((q, i) => `<li>${x.mina[i] === true ? "✅" : x.mina[i] === false ? "❌" : "–"} ${esc(q.fraga)} → <b>${esc(x.facit[i])}</b></li>`).join("")}</ul></details>` : ""}`;
    }
    if (!mig.med) return `${topp}<button class="primary" data-duell-med="${x.id}">⚔️ Anta utmaningen</button>`;
    if (mig.klar) return `${topp}${senText}<p>⏳ Du är klar! Väntar på ${esc(de?.namn || "kompisen")}…</p>`;
    const i = x.fragor.findIndex((_q, j) => !(String(j) in x.mina));
    const q = x.fragor[i];
    return `${topp}${senText}<div class="card duell-fraga"><div class="small muted">Ord ${i + 1} av ${x.antal} · ${esc(q.fran)} → ${esc(q.till)}</div>
      <div class="duell-ord">${esc(q.fraga)}</div>
      <input id="duell-svar" data-i="${i}" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Skriv på ${esc(q.till.toLowerCase())}…">
      <button class="primary" id="duell-skicka" ${this._busy ? "disabled" : ""}>Svara</button></div>`;
  }

  // ---------- lag ----------
  _lagView() {
    const s = this._s, L = s.lag, barn = !s.kan_valja, k = s.karta;
    const fmt = (iso) => new Date(iso.length === 10 ? iso + "T12:00" : iso).toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
    let html = "";
    if (L) {
      const b = L.boss, kvar = Math.max(0, b.hp - b.skada);
      html += `<div class="card lag-kort">
        <h3 style="margin:0">${L.marke} ${esc(L.namn)}</h3>
        <div class="lag-folk">${L.medlemmar.map((x) => `<div class="lag-pers"><div class="lag-djur">${x.art ? ritaDjur(x.art, "glad", Math.max(1, x.steg), {}) : "🥚"}</div>
          <b>${esc(x.namn)}${x.van ? " 🤝" : ""}</b><span class="small">${x.djur ? esc(x.djur) : x.van ? "Vän" : "Inget husdjur"}</span>
          <span class="small">💪 ${x.cp} · 🛡️ ${x.def}</span><span class="small">${x.idag ? "✅ Pluggat idag" : "⏳ Inte pluggat idag"}</span>
          <span class="small muted">${x.vecka} ⭐ i veckan</span></div>`).join("")}</div>
        <div class="small">💪 <b>Lagbonus idag: +${L.bonus_pct} % skada</b> för alla i laget (+${L.bonus_per} % för varje lagmedlem som har pluggat idag).</div></div>
      <div class="card lagboss ${b.klar ? "klar" : ""}">
        <div class="lagboss-figur">${b.klar ? "🏆" : b.ikon}</div>
        <div><h3 style="margin:0">Veckans lagboss: ${b.ikon} ${esc(b.namn)}</h3>
          <div class="progress boss-hp"><div style="width:${Math.round((kvar / b.hp) * 100)}%"></div></div>
          <div class="small">${b.klar ? `🎉 Besegrad! Alla i laget fick <b>${b.beloning} ⭐</b>.` : `❤️ ${kvar} av ${b.hp} liv kvar · besegra den senast söndag ${fmt(b.slut)}`}</div>
          <div class="small muted">Allt som någon i laget pluggar den här veckan gör skada. ${b.klar ? "" : `Belöning: <b>${b.beloning} ⭐</b> till var och en.`}</div>
          <div class="lag-bidrag">${L.medlemmar.map((x) => `<span>${esc(x.namn)}: <b>${x.vecka}</b></span>`).join("")}</div></div></div>`;
      const ls = s.lagstrid || {}, medDjur = L.medlemmar.filter((x) => x.art).length;
      html += `<h3>⚔️ Lagstrid ${L.medlemmar.length} mot ${L.medlemmar.length}</h3>
        <p class="small muted">Hela laget mot ett datorstyrt utmanarlag. Du styr ditt husdjur och datorn styr lagkamraterna. Kostar 1 ⚡. Vinst ger ${ls.vinst} 🏆 och XP, förlust ${ls.forlust} 🏆.</p>
        ${ls.pagar && barn ? `<button class="primary" id="lagstrid-fortsatt">⚔️ Fortsätt lagstriden</button>`
          : ls.pagar ? `<p class="small">⚔️ En lagstrid pågår.</p>` : barn ? `<button class="primary" id="lagstrid-start" ${medDjur >= 2 && s.meriter?.djur && k.energi >= 1 && !this._busy ? "" : "disabled"}>⚔️ Starta lagstrid · 1⚡ (du har ${k.energi})</button>${medDjur < 2 ? `<div class="small muted">Alla i laget behöver ett husdjur.</div>` : ""}`
          : `<p class="small muted">Barnen startar lagstrider själva.</p>`}
        ${(ls.hist || []).length ? `<ul class="lista">${ls.hist.slice().reverse().map((h) => `<li>${h.vann ? "🥇 Vinst" : h.gav_upp ? "🏳️ Gav upp" : "💔 Förlust"} mot ${esc(h.de_namn)} <span class="small muted">${fmt(h.tid)}</span></li>`).join("")}</ul>` : ""}`;
    } else if (!s.lag_lista) {
      html += `<p class="muted">Du är inte med i något lag än. Fråga mamma eller pappa!</p>`;
    }
    if (s.lag_lista) html += this._lagAdmin();
    return html;
  }

  _lagAdmin() {
    const s = this._s, red = this._lagRed || "", lag = s.lag_lista.find((x) => x.id === red);
    const namn = (id) => s.barn_lista.find((b) => b.id === id)?.namn || id;
    return `<h3>👨‍👩‍👧 Lag (bara föräldrar)</h3>
      ${s.lag_lista.length ? `<ul class="lista">${s.lag_lista.map((x) => `<li>${x.marke} <b>${esc(x.namn)}</b>: ${x.medlemmar.map((b) => esc(namn(b))).join(", ")}
        <button class="mini" data-lag-redigera="${x.id}">✏️</button> <button class="mini" data-lag-bort="${x.id}">🗑️</button></li>`).join("")}</ul>` : `<p class="small muted">Inga lag än.</p>`}
      <div class="card"><b>${lag ? "Ändra laget" : "Nytt lag"}</b>
        <label class="small">Namn <input id="lag-namn" maxlength="40" value="${esc(lag?.namn || "")}" placeholder="t.ex. Drakarna"></label>
        <div class="small">Märke</div><div class="lag-marken">${s.lag_marken.map((m, i) => `<label><input type="radio" name="lag-marke" value="${m}" ${(lag ? lag.marke === m : i === 0) ? "checked" : ""}> ${m}</label>`).join("")}</div>
        <div class="small">Barn i laget (minst 2, ett barn kan bara vara med i ett lag)</div>
        ${s.barn_lista.map((b) => `<label class="kap-rad"><input type="checkbox" data-lag-barn="${b.id}" ${lag ? (lag.medlemmar.includes(b.id) ? "checked" : "") : "checked"}> ${esc(b.namn)}</label>`).join("")}
        ${(s.lag_van_val || []).length ? `<div class="small">Vänner i andra hem (högst 4 i laget totalt)</div>${s.lag_van_val.map((x) => `<label class="kap-rad"><input type="checkbox" data-lag-van="${esc(x.kod)}" data-lag-van-barn="${esc(x.barn)}" ${lag?.vanner?.some((y) => y.kod === x.kod) ? "checked" : ""}> 🤝 ${esc(x.smeknamn)} <span class="small muted">(${esc(x.barn_namn)}s vän)</span></label>`).join("")}` : ""}
        <button class="primary" id="lag-spara">${lag ? "💾 Spara" : "➕ Skapa lag"}</button>${lag ? ` <button class="mini" data-lag-redigera="">Avbryt</button>` : ""}</div>
      <p class="small muted">Laget får en lagboss varje vecka som alla skadar när de pluggar, lagbonus (+5 % skada per lagmedlem som pluggat idag) och lagstrider i arenan.</p>`;
  }

  async _lagSpara(bort = null) {
    const r = this.shadowRoot || this;
    const args = bort ? { op: "lag_ta_bort", id: bort } : {
      op: "lag_spara", id: this._lagRed || "", namn: r.querySelector("#lag-namn")?.value || "",
      marke: r.querySelector("input[name=lag-marke]:checked")?.value || "🏳️",
      medlemmar: [...r.querySelectorAll("[data-lag-barn]")].filter((x) => x.checked).map((x) => x.dataset.lagBarn),
      vanner: [...r.querySelectorAll("[data-lag-van]")].filter((x) => x.checked).map((x) => ({ kod: x.dataset.lagVan, barn: x.dataset.lagVanBarn })) };
    if (bort && !confirm("Ta bort laget?")) return;
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ barn: this._s.barn, ...args }) });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._lagRed = null;
      this._msg = { type: "ok", text: bort ? "Laget är borttaget." : "Laget är sparat 🏳️" };
      await this._load();
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    }
    this._render();
  }

  async _lagstridStart() {
    if (this._busy) return;
    if (!(await this._act("lagstrid_start"))) return;
    await this._load();
    this._lsMal = 0;
    this._lsTur = null;
    this._go({ name: "lagstrid" });
  }

  async _lagstridDrag(drag) {
    if (this._busy) return;
    if (!(await this._act("lagstrid_drag", { drag, mal: this._lsMal || 0 }))) return;
    const k = this._s.data?.meriter?.karta || {};
    const p = k.lagstrid || (k.lagstrid_hist || []).at(-1);
    this._lsTur = p?.turer?.at(-1) || null;
    if (!k.lagstrid) this._lsSlut = { ...p, vann: this._lsTur?.slut === "vinst" };
    await this._load();
    this._render();
  }

  _lagstridView() {
    const s = this._s, info = s.arena?.drag || {}, p = s.lagstrid?.pagar || this._lsSlut;
    if (!p) return `<p class="muted">Ingen lagstrid pågår.</p><button id="ls-klar">⬅️ Tillbaka</button>`;
    const tur = this._lsTur, slut = !s.lagstrid?.pagar;
    const traffad = new Set((tur?.h || []).filter((x) => !x.miss && x.skada > 0).map((x) => `${x.mal_sida}${x.mal}`));
    const skoldIk = (id) => (s.karta?.forsvar?.skoldar || []).find((x) => x.id === id)?.ikon || "";
    const pers = (x, sida, i) => {
      const liv = slut && tur ? tur[`liv_${sida}`][i] : x.liv, ute = liv <= 0;
      const val = sida === "de" && !slut && !ute && (this._lsMal || 0) === i;
      return `<div class="ls-pers ${ute ? "ute" : ""} ${val ? "mal" : ""} ${traffad.has(sida + i) ? "traff" : ""}" ${sida === "de" && !slut && !ute ? `data-ls-mal="${i}"` : ""}>
        <div class="ls-djur">${x.art ? ritaDjur(x.art, ute ? "hungrig" : "glad", Math.max(1, x.steg), {}) : "🐾"}${x.skold ? `<span class="ls-skold">${skoldIk(x.skold)}</span>` : ""}</div>
        <b class="small">${esc(x.namn)}${sida === "lag" && i === 0 ? " (du)" : ""}</b>
        <div class="progress ls-liv"><div style="width:${Math.round((Math.max(0, liv) / x.max) * 100)}%"></div></div>
        <span class="small">${ute ? "😵" : `❤️ ${liv}/${x.max}`}${!slut && !ute ? ` · ⚡${x.ap}` : ""}</span>${val ? `<span class="small">🎯 Mål</span>` : ""}</div>`;
    };
    const namn = (sida, i) => esc((sida === "lag" ? p.lag : p.de)[i]?.namn || "?");
    const skyddT = { bubbla: " 🫧 bubblan tog träffen", block: " 🛡️ blockerad", spegel: " 🪞 speglad tillbaka", tagg: " 🦔 taggar", typ: " 🛡️ typskydd" };
    const logg = (tur?.h || []).map((x) => {
      const at = info[x.at] || { ikon: "⚔️", namn: x.at };
      return `<li class="${x.sida}">${namn(x.sida, x.i)} ${at.ikon} ${esc(at.namn)} → ${namn(x.mal_sida, x.mal)}: ${x.miss ? "MISS" : `<b>−${x.skada}</b>`}${skyddT[x.skydd] || ""}${x.tillbaka ? ` (−${x.tillbaka} tillbaka)` : ""}</li>`;
    }).join("");
    const jag = p.lag[0], ute = jag.liv <= 0;
    const knappar = slut ? `<div class="ls-slut ${this._lsSlut?.vann ? "vinst" : ""}">${this._lsSlut?.vann ? `🥇 VINST! +${s.lagstrid.vinst} 🏆` : `💔 Förlust · +${s.lagstrid.forlust} 🏆 · bra kämpat!`}</div><button class="primary" id="ls-klar">⬅️ Till laget</button>`
      : ute ? `<p class="small">😵 Ditt husdjur är utmattat. Lagkamraterna kämpar vidare!</p><button class="primary" id="ls-vidare" ${this._busy ? "disabled" : ""}>➡️ Nästa runda</button>`
      : `<div class="small">Tryck på en motståndare för att välja mål, sedan attack.</div><div class="attack-rad">${Object.keys(jag.drag).map((id) => {
          const at = info[id] || {}, kan = at.energi <= jag.ap && !this._busy;
          return `<button class="attack-knapp" data-ls-drag="${id}" ${kan ? "" : "disabled"}><span class="ai">${at.ikon}</span><b>${jag.drag[id]}</b><small>${at.energi}⚡</small></button>`;
        }).join("")}</div>`;
    return `<div class="ls-plan">
        <div class="ls-sida"><div class="small"><b>${esc(p.de_namn)}</b></div><div class="ls-rad">${p.de.map((x, i) => pers(x, "de", i)).join("")}</div></div>
        <div class="ls-vs">VS</div>
        <div class="ls-sida"><div class="ls-rad">${p.lag.map((x, i) => pers(x, "lag", i)).join("")}</div><div class="small"><b>${esc(p.lag_namn)}</b></div></div>
      </div>
      ${logg ? `<ul class="ls-logg">${logg}</ul>` : ""}
      ${knappar}
      ${slut ? "" : `<button class="mini" id="lagstrid-ge-upp">🏳️ Ge upp</button>`}`;
  }

  // ---------- arenan ----------
  _arenaView() {
    const s = this._s, a = s.arena, d = s.meriter?.djur, barn = !s.kan_valja;
    if (!a || !d) return `<p class="muted">Skaffa ett husdjur först.</p>`;
    const n = a.niva, pct = n.till ? Math.round(((n.xp - n.fran) / (n.till - n.fran)) * 100) : 100;
    const andra = (s.topplista || []).filter((t) => t.id !== s.barn && t.karta);
    const mig = (s.topplista || []).find((t) => t.id === s.barn);
    const tabell = [...(s.topplista || [])].filter((t) => t.karta).sort((x, y) => (y.karta.arena_poang || 0) - (x.karta.arena_poang || 0));
    this._arenaHist = {};
    const hist = [];
    (a.hist || []).forEach((h, i) => { this._arenaHist[`jag${i}`] = { h, vem: barn ? "Du" : s.namn }; hist.push({ h, nyckel: `jag${i}`, text: `${barn ? "Du" : esc(s.namn)} mot ${esc(h.mot_namn)}`, vann: h.vann }); });
    andra.forEach((t) => (t.karta.arena_hist || []).forEach((h, i) => {
      if (h.mot !== s.barn) return;
      this._arenaHist[`${t.id}${i}`] = { h, vem: t.namn };
      hist.push({ h, nyckel: `${t.id}${i}`, text: `${esc(t.namn)} utmanade ${barn ? "dig" : esc(s.namn)}`, vann: !h.vann });
    }));
    hist.sort((x, y) => (y.h.tid || "").localeCompare(x.h.tid || ""));
    const k = s.karta;
    return `<div class="card arena-jag">
        <div class="arena-djur">${ritaDjur(d.art, d.humor || "glad", Math.max(1, d.steg), {})}</div>
        <div><h3 style="margin:0">${esc(d.namn)}</h3>
          <div>⬆️ Nivå <b>${n.niva}</b> · 💪 CP <b>${a.cp}</b> · ❤️ ${k.liv_max} · ${this._defText(k.forsvar)}</div>
          <div class="progress"><div style="width:${pct}%"></div></div>
          <div class="small muted">${n.till ? `${n.xp - n.fran} av ${n.till - n.fran} XP till nivå ${n.niva + 1}. Allt du pluggar ger XP.` : "Högsta nivån!"}</div>
          <div class="small">🏆 ${a.poang} arenapoäng · ${a.vinster} vinster · ⚡ ${k.energi}</div></div></div>
      ${this._traningKort(a, d, barn)}
      ${a.pagar ? `<button class="primary" id="arena-fortsatt">⚔️ Fortsätt striden mot ${esc(a.pagar.mot_namn)}</button>` : ""}
      ${(() => { const pb = (s.provbossar || []).filter((b) => !b.vunnen); const tr = s.data?.meriter?.karta?.provtrofeer || [];
        if (!pb.length && !tr.length) return "";
        return `${pb.length ? `<h3>📝 Provbossar</h3>
          <div class="small muted">Varje prov du lägger in blir en boss. Varje dag du pluggar inför provet tar den skada. Slutstriden öppnar dagen före provet och kostar inget ⚡.</div>
          <ul class="lista arena-lista">${pb.map((b) => this._provbossRad(b, barn && !a.pagar)).join("")}</ul>` : ""}
          ${tr.length ? `<h3>🏆 Provtroféer</h3><div class="trofe-rad">${tr.slice(-12).reverse().map((t) => `<span class="trofe" title="${esc(t.prov)} ${esc(t.datum)}">${t.ikon}<span class="small">${esc(t.namn)}</span></span>`).join("")}</div>` : ""}`; })()}
      ${(() => { const rv = s.revansch; if (!rv?.bossar?.length) return "";
        return `<h3>🔁 Revansch mot bossar</h3>
        <div class="small muted">Slå en boss du redan har besegrat igen och vinn kort till albumet 🃏. Kostar ${rv.energi} ⚡. Din stridsuppsättning och dina laddattacker gäller. ${rv.kort_kvar > 0 ? `Kort kvar att vinna idag: <b>${rv.kort_kvar}</b>.` : "Dagens kort är slut, men du kan träna ändå."}</div>
        <ul class="lista arena-lista">${rv.bossar.map((b) => `<li><span class="van-djur" style="font-size:34px;text-align:center">${b.ikon}</span>
          <span><b>${esc(b.namn)}</b><br><span class="small">${esc(b.varld_namn)} · 🎯 svag mot ${TYP_TEXT[b.svag]} · 🃏 ${b.kort_kvar ? `${b.kort_kvar} kort saknas` : "alla kort!"}</span></span>
          ${barn && !a.pagar ? `<button class="mini primary" data-revansch="${b.varld}" ${k.energi >= rv.energi && !this._busy ? "" : "disabled"}>Revansch · ${rv.energi}⚡</button>` : ""}</li>`).join("")}</ul>`; })()}
      <h3>⚔️ Utmana</h3>
      ${andra.length ? `<ul class="lista arena-lista">${andra.map((t) => `<li><span class="van-djur">${t.karta.art ? ritaDjur(t.karta.art, "glad", Math.max(1, t.karta.steg || 1), {}) : "🥚"}</span>
          <span><b>${esc(t.namn)}</b>${t.karta.djur ? ` · ${esc(t.karta.djur)}` : ""}<br><span class="small">⬆️ ${t.karta.djur_niva || 1} · 💪 CP ${t.karta.cp || 0} · ${t.karta.skold || "🛡️"} DEF ${t.karta.def || 0}${t.karta.traning ? ` · 🎓 ${t.karta.traning}` : ""}</span>
          ${(() => { const el = a.element?.[t.karta.art]; return el ? `<br><span class="small">${TYP_TEXT[el]}-djur · 🎯 svag mot <b>${TYP_TEXT[a.svag_mot[el]]}</b></span>` : ""; })()}</span>
          ${barn && t.karta.art && !a.pagar ? `<button class="mini primary" data-arena-mot="${esc(t.id)}" ${k.energi >= 1 && !this._busy ? "" : "disabled"}>Utmana · 1⚡</button>` : ""}</li>`).join("")}</ul>`
        : `<p class="muted">Ingen att utmana än.</p>`}
      ${(this._vanner?.vanner || []).length ? `<h3>🤝 Vänner</h3><ul class="lista arena-lista">${this._vanner.vanner.map((x) => {
          const ver = x.arena_ver || 0;
          const hinder = !ver ? "Har en äldre Läxspelet" : ver < a.ver ? "Behöver uppdatera Läxspelet" : ver > a.ver ? "Du behöver uppdatera Läxspelet" : "";
          return `<li><span class="van-djur">${x.art ? ritaDjur(x.art, "glad", Math.max(1, x.steg || 1), {}) : "🥚"}</span>
            <span><b>${esc(x.smeknamn)}</b><br><span class="small">${hinder ? `⚠️ ${hinder}` : `🗺️ ${x.niva}`}</span></span>
            ${barn && x.art && !a.pagar && !hinder ? `<button class="mini primary" data-arena-van="${esc(x.kod)}" ${k.energi >= 1 && !this._busy ? "" : "disabled"}>Utmana · 1⚡</button>` : ""}</li>`;
        }).join("")}</ul><p class="small muted">Vänner i andra hem behöver samma version av Läxspelet för att ni ska kunna strida.</p>` : ""}
      <p class="small muted">Arenan kostar 1 ⚡. Striden tar inget riktigt liv. Vinst ger ${10} 🏆 och XP, förlust ${2} 🏆. Varje tur får man 1 stridsenergi, och starka attacker kostar mer.</p>
      <h3>🏆 Arenans topplista</h3>
      <ol class="lista">${tabell.map((t) => `<li>${esc(t.namn)} · ${t.karta.arena_poang || 0} 🏆</li>`).join("")}</ol>
      ${hist.length ? `<h3>📺 Senaste striderna</h3><ul class="lista">${hist.slice(0, 8).map((x) => `<li>${x.vann ? "🥇" : "💔"} ${x.text}
          <button class="mini" data-arena-repris="${x.nyckel}">📺 Se</button></li>`).join("")}</ul>` : ""}
      ${mig ? "" : ""}`;
  }

  _arenaO(a, tur, extra = {}) {
    const info = this._s.arena?.drag || {};
    const at = info[tur?.at] || { ikon: "⚔️", namn: "Strid", typ: "kraft" };
    const motAt = tur?.mot_at ? info[tur.mot_at] : null;
    const rv = a.revansch && (this._s.revansch?.bossar || []).find((x) => x.varld === a.revansch);
    return { at, djur: { art: a.jag.art, steg: Math.max(1, a.jag.steg), namn: a.jag.namn }, motDjur: a.de.boss ? null : { art: a.de.art, steg: Math.max(1, a.de.steg) },
      mon: a.de.boss ? { ikon: a.de.art, namn: `${a.de.namn}`, boss: true, varld: { farg: rv?.farg || (a.provboss ? "#c62828" : "#6a1b9a") } } : { ikon: "", namn: `${a.de.namn}`, boss: false, varld: { farg: "#6a1b9a" } }, hp: a.de.max, kvar: tur ? tur.de_fore : a.de.liv,
      skada: tur?.skada || 0, jagMiss: !!tur?.miss, svag: !!tur?.super, klar: tur?.slut === "vinst", mot: tur?.mot || 0, miss: !!tur?.mot_miss, motAt,
      livFore: tur ? tur.jag_fore : a.jag.liv, livMax: a.jag.max, arena: true,
      efter: tur?.de_efter, livEfter: tur?.jag_efter, skold: a.jag.skold, motSkold: a.de.skold,
      deSkydd: tur?.skydd, deTillbaka: tur?.tillbaka, skydd: tur?.mot_skydd, tillbaka: tur?.mot_tillbaka, ...extra };
  }

  _arenaVisa() {
    const a = this._s.arena?.pagar;
    if (a) this._strid(this._arenaO(a, null, { idle: true, live: true }));
  }

  async _arenaStart(mot, van = null) {
    if (this._busy) return;
    if (!(await this._act("arena_start", van ? { van } : { mot }))) return this._render();
    await this._load();
    this._arenaVisa();
  }

  async _arenaDrag(drag) {
    const fore = this._s.arena?.pagar;
    if (!fore || this._busy) return false;
    if (!(await this._act("arena_drag", { drag }))) return false;
    const k = this._s.data?.meriter?.karta || {};
    const a = k.arena || (fore.revansch || fore.provboss ? k.revansch_hist : k.arena_hist || [])?.at(-1);
    const tur = a?.turer?.at(-1);
    if (!tur) return false;
    const laddat = this._load();
    if (fore.provboss && tur.slut) laddat.then(() => setTimeout(() => {
      const h = (this._s.data?.meriter?.karta?.revansch_hist || []).at(-1);
      if (h?.vann && h.trofe) this._fx({ text: "🏆 PROVBOSSEN BESEGRAD!", sub: `${fore.mot_namn} · +20 ⭐ och en provtrofé`, emojis: ["🏆", "📝", fore.de.art, "⭐", "✨"], antal: 40, konfetti: true, farg: "#c62828", ljud: true });
      else if (!h?.vann) this._msg = { type: "info", text: `${fore.mot_namn} vann den här gången. Plugga lite till så blir den svagare, och försök igen!` };
    }, 2600));
    if (fore.revansch && tur.slut) laddat.then(() => setTimeout(() => {
      const h = (this._s.data?.meriter?.karta?.revansch_hist || []).at(-1);
      if (h?.vann && h.kort) this._fx({ text: "🃏 NYTT KORT!", sub: `${fore.mot_namn} tappade ett kort`, emojis: ["🃏", "✨", fore.de.art, "⭐"], antal: 30, konfetti: true, farg: "#7e57c2" });
      else if (h?.vann) this._msg = { type: "ok", text: "Du vann! Dagens revanschkort är slut, kom tillbaka i morgon för fler kort." };
    }, 2600));
    this._strid(this._arenaO({ ...fore, jag: { ...fore.jag }, de: { ...fore.de } }, tur, { live: true, fortsatt: true, laddat }));
    await laddat;
    return true;
  }

  // Spelar upp en hel arenastrid tur för tur.
  _arenaRepris(nyckel) {
    const x = this._arenaHist?.[nyckel];
    if (!x) return;
    const h = x.h, turer = h.turer || [];
    let i = 0;
    const nasta = () => {
      if (i >= turer.length) return;
      const tur = turer[i++];
      this._strid(this._arenaO(h, tur, { vem: `${x.vem} mot ${h.mot_namn} · tur ${i}/${turer.length}`, fortsatt: i > 1, efter: i < turer.length ? nasta : null }));
    };
    nasta();
  }

  // Läget just nu, i den form stridsscenen vill ha.
  _stridLage(extra = {}) {
    const k = this._s.karta, djur = this._s.meriter?.djur;
    return { at: { ikon: "⚔️", namn: "Strid", typ: "kraft" }, djur, mon: k.monster, hp: k.hp, kvar: k.hp - k.skada,
      skada: 0, livFore: k.liv, livMax: k.liv_max, mot: 0, live: true, ...extra };
  }

  async _gorAttack(id, fortsatt = false) {
    const x = (this._s.karta?.attacker || []).find((y) => y.id === id);
    if (!x || this._busy) return false;
    const k0 = this._s.karta, djur = this._s.meriter?.djur;
    const fore = { mon: k0.monster, hp: k0.hp, kvar: k0.hp - k0.skada };
    if (!(await this._act("attack", { attack: x.id }))) return false;
    const sen = this._s.data?.meriter?.karta?.senaste || {};
    const laddat = this._load();
    this._strid({ at: x, djur, ...fore, skada: sen.skada ?? x.nu, svag: sen.svag ?? x.svag, klar: !!sen.klar,
      mot: sen.mot || 0, miss: !!sen.miss, livFore: sen.liv_fore, livMax: sen.liv_max, live: true, fortsatt, laddat,
      skydd: sen.skydd, tillbaka: sen.tillbaka, skold: sen.skold, meteorer: sen.meteorer, motAt: sen.mot_at, motLak: sen.mot_lak });
    await laddat;
    return true;
  }

  // Menyn i stridsrutan: attacker, ryggsäcken och lämna.
  async _stridMeny(el, o) {
    if (el.classList.contains("valjer") || !el.isConnected) return;
    el.classList.add("valjer");
    await o.laddat;
    if (o.arena) return el.isConnected && this._arenaMeny(el, o);
    const k = this._s.karta, d = this._s.meriter?.djur;
    if (!k || !d || !el.isConnected) return;
    const satt = (sel, v) => el.querySelectorAll(sel).forEach((x) => { x.style.width = `${v * 100}%`; });
    if (!o.klar) {
      satt(".hpbar:not(.liv) div, .bosshp div", (k.hp - k.skada) / k.hp);
      el.querySelectorAll(".hpnum").forEach((x) => { x.textContent = `${k.hp - k.skada}/${k.hp}`; });
    }
    satt(".hpbar.liv div", k.liv / k.liv_max);
    const ln = el.querySelector(".livnum");
    if (ln) ln.textContent = `${k.liv}/${k.liv_max}`;
    const ko = k.liv <= 0, fel = this._msg?.type === "error" ? this._msg.text : "";
    const vecka = k.super_anvand;
    const boss = !!k.ladd, med = new Set(k.uppsattning || []);
    const at = (k.attacker || []).filter((x) => x.har && (boss ? med.has(x.id) : !x.ladd)).map((x) => {
      const anvand = x.ladd && (k.ladd?.anv?.[x.id] || 0) >= x.ganger;
      const kan = !o.titta && !ko && k.energi >= x.energi && !x.slut && !anvand && (!x.ladd || k.ladd.p >= x.ladd);
      if (x.ladd) return `<button class="ladd-knapp ${kan ? "redo" : ""}" data-s-attack="${x.id}" ${kan ? "" : "disabled"}>${x.ikon} ${esc(x.namn)} <small>${anvand ? "använd" : `🌟 ${x.ladd}`} · ${x.nu}</small></button>`;
      return `<button data-s-attack="${x.id}" ${kan ? "" : "disabled"}>${x.ikon} ${esc(x.namn)} <small>${x.energi}⚡ · ${x.nu}${x.pass > 1 ? " 💪" : x.pass < 1 ? " 😕" : ""}</small></button>`;
    }).join("");
    const dr = (k.drycker || []).filter((x) => x.antal).map((x) => {
      const kan = !o.titta && (x.id === "d_fenix" ? ko : k.liv < k.liv_max);
      return `<button data-s-dryck="${x.id}" ${kan ? "" : "disabled"}>${x.ikon} ${esc(x.namn)} <small>×${x.antal}</small></button>`;
    }).join("");
    const meny = el.querySelector(".kommandon") || el.querySelector(".ruta.hoger").appendChild(Object.assign(document.createElement("div"), { className: "kommandon" }));
    el.querySelector(".kommando")?.remove();
    meny.innerHTML = o.klar
      ? `<button data-s-nasta>➡️ Nästa nivå</button><button data-s-lamna>🏃 Lämna</button>`
      : `${fel ? `<div class="sfel">${esc(fel)}</div>` : ""}${o.titta ? `<div class="stom">👀 Du tittar. Bara ${esc(this._s.namn || "barnet")} kan attackera.</div>` : ""}<div class="srubrik">⚔️ Attack · ⚡ ${k.energi}</div>${boss ? this._laddRad(k.ladd.p, k.ladd.max) : ""}${at || `<div class="stom">Köp attacker i Butiken 🛍️</div>`}
         <div class="srubrik">🎒 Ryggsäck</div>${dr || `<div class="stom">Tom. Livdrycker finns i Butiken 🛍️</div>`}
         <button data-s-lamna>🏃 Lämna striden</button>`;
    this._msg = null;
    meny.onclick = async (e) => {
      e.stopPropagation();
      const b = e.target.closest("button");
      if (!b || b.disabled || this._busy) return;
      if (b.hasAttribute("data-s-lamna")) return el.dispatchEvent(new Event("stang"));
      if (b.hasAttribute("data-s-nasta")) return this._strid(this._stridLage({ idle: true, fortsatt: true }));
      meny.querySelectorAll("button").forEach((x) => { x.disabled = true; });
      if (b.dataset.sAttack) {
        if (!(await this._gorAttack(b.dataset.sAttack, true))) { el.classList.remove("valjer"); this._stridMeny(el, o); }
        return;
      }
      const fore = k.liv;
      const ok = await this._act("dryck", { dryck: b.dataset.sDryck });
      if (ok) await this._load();
      const nu = this._s.karta?.liv ?? fore;
      if (ok && nu > fore) {
        const tal = Object.assign(document.createElement("div"), { className: "tal laktal", innerHTML: `+${nu - fore}` });
        el.querySelector(".hjalte").appendChild(tal);
        el.classList.add("dricker");
        setTimeout(() => { el.classList.remove("dricker"); tal.remove(); }, 1300);
      }
      el.classList.remove("valjer");
      this._stridMeny(el, o);
    };
  }

  // Laddmätaren för laddattacker (mot världsbossar och i arenan).
  _laddRad(p, max = 100) {
    const pct = Math.min(100, Math.round((p / max) * 100));
    return `<div class="ladd-rad ${pct >= 100 ? "full" : ""}"><span>🌟 Laddning</span><div class="ladd-bar"><div style="width:${pct}%"></div></div><b>${p}/${max}</b></div>`;
  }

  _arenaMeny(el, o) {
    const a = this._s.arena?.pagar, info = this._s.arena?.drag || {}, barn = !this._s.kan_valja;
    const fel = this._msg?.type === "error" ? this._msg.text : "";
    this._msg = null;
    if (a) {
      el.querySelectorAll(".hpbar:not(.liv) div, .bosshp div").forEach((x) => { x.style.width = `${(a.de.liv / a.de.max) * 100}%`; });
      el.querySelectorAll(".hpnum").forEach((x) => { x.textContent = `${a.de.liv}/${a.de.max}`; });
      el.querySelectorAll(".hpbar.liv div").forEach((x) => { x.style.width = `${(a.jag.liv / a.jag.max) * 100}%`; });
      const ln = el.querySelector(".livnum");
      if (ln) ln.textContent = `${a.jag.liv}/${a.jag.max}`;
    }
    const meny = el.querySelector(".kommandon") || el.querySelector(".ruta.hoger").appendChild(Object.assign(document.createElement("div"), { className: "kommandon" }));
    el.querySelector(".kommando")?.remove();
    meny.innerHTML = !a
      ? `<button data-s-arena>🏟️ Till arenan</button><button data-s-lamna>🏃 Lämna</button>`
      : `${fel ? `<div class="sfel">${esc(fel)}</div>` : ""}<div class="srubrik">⚔️ Drag · ⚡ ${a.jag.ap}</div>
         ${this._laddRad(a.jag.ladd || 0, this._s.arena?.ladd_max || 100)}
         ${(() => { const svag = this._s.arena?.svag_mot?.[a.de.element || this._s.arena?.element?.[a.de.art] || "kraft"]; return svag ? `<div class="shint">🎯 ${esc(a.de.namn)} är svag mot ${TYP_TEXT[svag] || svag}</div>` : ""; })()}
         ${Object.entries(a.jag.drag).map(([id, dmg]) => {
           const x = info[id] || { ikon: "⚔️", namn: id, energi: 0 };
           if (x.ladd) {
             const anv = (a.jag.ladd_anv?.[id] || 0) >= x.ganger, kan = barn && !anv && (a.jag.ladd || 0) >= x.ladd;
             return `<button class="ladd-knapp ${kan ? "redo" : ""}" data-s-drag="${id}" ${kan ? "" : "disabled"}>${x.ikon} ${esc(x.namn)} <small>${anv ? "använd" : `🌟 ${x.ladd}`} · ${dmg}</small></button>`;
           }
           const sv = this._s.arena?.svag_mot?.[a.de.element || this._s.arena?.element?.[a.de.art] || "kraft"] === x.typ && id !== "knuff";
           return `<button data-s-drag="${id}" ${barn && x.energi <= a.jag.ap ? "" : "disabled"}>${x.ikon} ${esc(x.namn)} <small>${x.energi}⚡ · ${dmg}${sv ? " 🎯" : ""}</small></button>`;
         }).join("")}
         <button data-s-geupp ${barn ? "" : "disabled"}>🏳️ Ge upp</button><button data-s-lamna>🏃 Pausa</button>`;
    meny.onclick = async (e) => {
      e.stopPropagation();
      const b = e.target.closest("button");
      if (!b || b.disabled || this._busy) return;
      if (b.hasAttribute("data-s-lamna")) return el.dispatchEvent(new Event("stang"));
      if (b.hasAttribute("data-s-arena")) { el.dispatchEvent(new Event("stang")); return this._go({ name: "arena" }); }
      meny.querySelectorAll("button").forEach((x) => { x.disabled = true; });
      if (b.hasAttribute("data-s-geupp")) {
        if (!confirm("Ge upp striden?")) { el.classList.remove("valjer"); return this._stridMeny(el, o); }
        await this._act("arena_ge_upp");
        await this._load();
        return el.dispatchEvent(new Event("stang"));
      }
      if (!(await this._arenaDrag(b.dataset.sDrag))) { el.classList.remove("valjer"); this._stridMeny(el, o); }
    };
  }

  // Knappar för att titta på senaste attacken från syskon (och sig själv).
  _reprisRad() {
    const s = this._s;
    const knappar = (s.topplista || []).filter((t) => t.karta?.repriser?.length).map((t) => {
      const r = t.karta.repriser[t.karta.repriser.length - 1];
      const egen = t.id === s.barn;
      return this._reprisKnapp(r, egen && !s.kan_valja ? "Din attack" : t.namn, { art: t.karta.art, steg: t.karta.steg || 1, namn: t.karta.djur }, `barn:${t.id}`, !egen);
    });
    return knappar.length ? `<div class="repris-rad">📺 ${knappar.join("")}</div>` : "";
  }

  _reprisKnapp(r, vem, djur, nyckel, markeraNy) {
    if (!r) return "";
    (this._repriser ||= {})[nyckel] = { r, vem, djur };
    let sedd = "";
    try { sedd = localStorage.getItem(`skolan_repris_${nyckel}`) || ""; } catch (e) { /* privat läge */ }
    const ny = markeraNy && sedd !== r.tid;
    const t = r.tid ? new Date(r.tid) : null;
    const nar = t && !isNaN(t) ? (t.toDateString() === new Date().toDateString()
      ? t.toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" })
      : t.toLocaleDateString("sv-SE", { day: "numeric", month: "short" })) : "";
    return `<button class="mini repris-knapp ${ny ? "ny" : ""}" data-repris="${esc(nyckel)}" title="Se attacken">${r.ikon} ${esc(vem)}${nar ? ` · ${nar}` : ""}${ny ? " 🆕" : ""}</button>`;
  }

  _spelaRepris(nyckel) {
    const x = this._repriser?.[nyckel];
    if (!x) return;
    try { localStorage.setItem(`skolan_repris_${nyckel}`, x.r.tid || ""); } catch (e) { /* privat läge */ }
    const r = x.r;
    this._strid({ at: { ikon: r.ikon, namn: r.namn, typ: r.typ }, djur: x.djur, mon: r.mon, hp: r.hp, kvar: r.kvar,
      skada: r.skada, svag: r.svag, klar: r.klar, mot: r.mot || 0, miss: !!r.miss, livFore: r.liv_fore, livMax: r.liv_max,
      skydd: r.skydd, tillbaka: r.tillbaka, skold: r.skold, vem: x.vem === "Din attack" ? "Repris" : `${x.vem} attackerar!` });
    this._render();
  }

  // Stridsscen i stil med klassiska rollspel. Läggs i document.body så att omritningar inte avbryter den.
  _strid(o) {
    document.getElementById("skolan-strid")?.remove();
    const lugn = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const typ = o.idle ? "" : o.at.typ || "kraft";
    const efter = o.efter ?? Math.max(0, o.kvar - o.skada - (o.arena ? 0 : o.tillbaka || 0));
    const motFas = !o.idle && !o.klar && o.livMax != null && o.livFore != null;
    const livEfter = o.livEfter ?? (motFas ? Math.max(0, o.livFore - o.mot) : o.livFore);
    const skoldIk = (id) => (this._s.karta?.forsvar?.skoldar || []).find((x) => x.id === id)?.ikon || (id ? "🛡️" : "");
    const skyddText = (sk, tb) => ({ bubbla: "🫧 Bubblan tog träffen!", block: "🛡️ Blockerad!", spegel: `🪞 Speglad! −${tb} tillbaka`,
      tagg: `🦔 Taggar! −${tb} tillbaka`, typ: "🛡️ Typskydd: halv skada!" })[sk] || "";
    const ko = motFas && livEfter <= 0;
    const slump = (a, b) => a + Math.random() * (b - a);
    const partiklar = (n, tecken, cls) => Array.from({ length: n }, (_, i) =>
      `<i class="p ${cls}" style="--x:${slump(-60, 60).toFixed(0)}px;--y:${slump(-50, 40).toFixed(0)}px;--r:${slump(-180, 180).toFixed(0)}deg;--d:${(i * 0.06).toFixed(2)}s">${tecken[i % tecken.length]}</i>`).join("");
    const effekt = {
      eld: `<div class="glod" style="--g:#ff6d00"></div>${partiklar(12, ["🔥"], "upp")}`,
      natur: `<div class="glod" style="--g:#66bb6a"></div>${partiklar(14, ["🍃", "🌿"], "virvel")}`,
      blixt: `<svg class="bolt" viewBox="0 0 60 200"><polyline points="30,0 18,70 36,80 14,150 40,120 26,200" /></svg><div class="blixtsken"></div>${partiklar(6, ["✨"], "gnista")}`,
      vatten: `<div class="vag"></div>${partiklar(10, ["💧", "🫧"], "bubbla")}`,
      is: `<div class="glod" style="--g:#4fc3f7"></div>${partiklar(12, ["❄️", "🧊"], "fall")}<div class="frost"></div>`,
      kraft: `<div class="ring"></div><div class="ring r2"></div><div class="ring r3"></div><div class="jatte">💥</div>${partiklar(10, ["⭐", "✨"], "gnista")}`,
    }[typ] || "";
    const meteor = !o.idle && o.at.id === "a_meteor"; // meteorregn: egen effekt med nedslag
    const antalMeteorer = o.meteorer || 5;
    const meteorFx = meteor ? `<div class="meteor-himmel"></div>${Array.from({ length: antalMeteorer + 4 }, (_, i) => {
      const stor = i < antalMeteorer;
      return `<i class="meteor ${stor ? "" : "liten"}" style="--x:${slump(-90, 90).toFixed(0)}px;--y:${slump(-30, 40).toFixed(0)}px;--d:${(i * (stor ? 0.22 : 0.15) + (stor ? 0 : 0.1)).toFixed(2)}s;--s:${stor ? slump(42, 60).toFixed(0) : slump(18, 26).toFixed(0)}px">☄️</i>${stor ? `<b class="nedslag" style="--x:${slump(-70, 70).toFixed(0)}px;--y:${slump(-20, 40).toFixed(0)}px;--d:${(i * 0.22 + 0.55).toFixed(2)}s">💥</b>` : ""}`;
    }).join("")}<div class="meteor-antal">☄️ ×${antalMeteorer}</div>` : "";
    if (o.idle) this._msg = null;
    const siffror = (o.jagMiss ? "MISS!" : String(o.skada)).split("").map((c, i) => `<span style="--i:${i}">${c}</span>`).join("");
    const el = document.createElement("div");
    el.id = "skolan-strid";
    el.className = `strid t-${typ}${o.klar ? " seger" : ""}${o.svag ? " svag" : ""}${lugn ? " lugn" : ""}${motFas ? " mot" : ""}${o.miss ? " miss" : ""}${ko ? " ko" : ""}${o.idle ? " idle" : ""}${o.fortsatt ? " fortsatt" : ""}`;
    el.style.setProperty("--varld", o.mon?.varld?.farg || "#5c6bc0");
    el.innerHTML = `<style>${STRID_CSS}</style>
      <div class="ridaa">${Array.from({ length: 8 }, (_, i) => `<b style="--i:${i}"></b>`).join("")}</div>
      <div class="scen">
        <div class="mark"></div>
        <div class="namnruta">${o.at.ikon} ${esc(o.at.namn)}</div>${o.vem ? `<div class="vem">📺 ${esc(o.vem)}</div>` : ""}
        <div class="fiende ${o.motDjur ? "djur-fiende" : ""}"><div class="bosshp"><div style="width:${(o.kvar / o.hp) * 100}%"></div><span class="hpnum">${o.kvar}/${o.hp}</span></div><div class="figur">${o.motDjur ? ritaDjur(o.motDjur.art, ko ? "glad" : o.klar ? "hungrig" : "glad", o.motDjur.steg, {}) : o.mon?.ikon || "👾"}</div><div class="fx">${meteor ? meteorFx : effekt}</div>
          <div class="tal ${o.svag ? "svag" : ""} ${o.jagMiss ? "jagmiss" : ""}">${siffror}${o.svag ? "<small>SVAG PUNKT!</small>" : ""}</div></div>
        ${o.skold ? `<div class="skold-ikon hj">${skoldIk(o.skold)}</div>` : ""}${o.motSkold ? `<div class="skold-ikon fi">${skoldIk(o.motSkold)}</div>` : ""}
        ${!o.idle && skyddText(o.deSkydd, o.deTillbaka) ? `<div class="skyddtext fi">${skyddText(o.deSkydd, o.deTillbaka)}</div>` : ""}
        ${motFas && !o.miss && skyddText(o.skydd, o.tillbaka) ? `<div class="skyddtext hj">${skyddText(o.skydd, o.tillbaka)}</div>` : ""}
        <div class="hjalte"><div class="kropp">${o.djur ? ritaDjur(o.djur.art, ko ? "hungrig" : "glad", Math.max(1, o.djur.steg), { form: o.djur.form }) : "🐾"}</div>
          ${motFas && o.motAt && !o.miss ? `<div class="mot-fx">${Array.from({ length: 9 }, (_, i) => `<i style="--v:${i * 40}deg;--d:${(i * 0.04).toFixed(2)}s">${o.motAt.id === "a_meteor" ? "☄️" : o.motAt.ikon}</i>`).join("")}</div>` : ""}
          ${motFas ? `<div class="tal motal">${o.miss ? "<span>MISS!</span>" : String(o.mot).split("").map((c, i) => `<span style="--i:${i}">${c}</span>`).join("")}</div>` : ""}</div>
        ${motFas ? `<div class="motnamn">${o.motAt ? `${esc(o.mon?.namn || "")} använder ${o.motAt.ikon} ${esc(o.motAt.namn)}!` : `${o.mon?.ikon || "👾"} ${esc(o.mon?.boss ? o.mon.namn : "Monstret")} slår tillbaka!`}</div>` : ""}
        ${motFas && o.motLak ? `<div class="motlak">🌸 +${o.motLak} ❤️</div>` : ""}
        ${ko ? `<div class="kotext">😵 ${esc(o.djur?.namn || "Husdjuret")} orkar inte mer<small>${o.arena ? "Förlust · +2 🏆 · bra kämpat!" : "Plugga för att få tillbaka liv ❤️"}</small></div>` : ""}
        <div class="segertext">${o.arena ? "VINST!" : "SEGER!"}<small>${o.arena ? "+10 🏆 · +15 XP" : "Nivå klar 🎉"}</small></div>
        <div class="meny">
          <div class="ruta vanster"><div class="rad"><span>${esc(o.mon?.boss ? "👑 " + o.mon.namn : o.mon?.namn || "Monster")}</span><span class="hpnum">${o.kvar}/${o.hp}</span></div>
            <div class="hpbar"><div style="width:${(o.kvar / o.hp) * 100}%"></div></div></div>
          <div class="ruta hoger"><div class="rad"><span>${esc(o.djur?.namn || "")}</span>${o.livMax != null ? `<span class="livnum">${o.livFore}/${o.livMax}</span>` : ""}</div>
            ${o.livMax != null ? `<div class="hpbar liv"><div style="width:${(o.livFore / o.livMax) * 100}%"></div></div>` : ""}
            <div class="kommando">▶ ${o.at.ikon} ${esc(o.at.namn)}</div></div>
        </div>
      </div>`;
    document.body.appendChild(el);
    const ljud = o.idle ? null : this._stridLjud(typ, o.klar, !motFas ? "" : ko ? "ko" : o.miss ? "miss" : o.mot > 0 ? "traff" : "");
    const fart = lugn ? 0.5 : 1, t = (ms) => ms * fart;
    const timers = [];
    const vid = (ms, fn) => timers.push(setTimeout(fn, t(ms)));
    vid(1750, () => {
      el.querySelectorAll(".hpbar div, .bosshp div").forEach((x) => { x.style.width = `${(efter / o.hp) * 100}%`; });
      const num = el.querySelectorAll(".hpnum"), start = performance.now();
      const steg = (nu) => {
        const f = Math.min(1, (nu - start) / t(800));
        num.forEach((x) => { x.textContent = `${Math.round(o.kvar - (o.kvar - efter) * f)}/${o.hp}`; });
        if (f < 1) requestAnimationFrame(steg);
      };
      requestAnimationFrame(steg);
    });
    const stang = () => {
      timers.forEach(clearTimeout);
      ljud?.stop();
      el.classList.add("ut");
      setTimeout(() => el.remove(), 350);
      this._render();
    };
    if (motFas && o.mot > 0) vid(3250, () => {
      el.querySelector(".hpbar.liv div").style.width = `${(livEfter / o.livMax) * 100}%`;
      const num = el.querySelector(".livnum"), start = performance.now();
      const steg = (nu) => {
        const f = Math.min(1, (nu - start) / t(700));
        num.textContent = `${Math.round(o.livFore - (o.livFore - livEfter) * f)}/${o.livMax}`;
        if (f < 1) requestAnimationFrame(steg);
      };
      requestAnimationFrame(steg);
    });
    const slut = o.idle ? 0 : o.klar ? 5600 : ko ? 6200 : motFas ? 5000 : 3700;
    el.addEventListener("stang", stang);
    if (o.live) {
      const meny = () => { timers.forEach(clearTimeout); this._stridMeny(el, o); };
      if (o.idle) meny(); else vid(slut, meny);
      el.addEventListener("click", () => { if (!el.classList.contains("valjer")) meny(); });
    } else if (o.efter) {
      vid(slut, o.efter);
      el.addEventListener("click", () => { timers.forEach(clearTimeout); o.efter(); });
    } else {
      vid(slut, stang);
      el.addEventListener("click", stang);
    }
  }

  // Korta, egna ljudeffekter med Web Audio (inga ljudfiler).
  _stridLjud(typ, klar, mot = "") {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      const ac = (this._ac ||= new AC());
      ac.resume?.();
      const ut = ac.createGain();
      ut.gain.value = 0.12;
      ut.connect(ac.destination);
      const t0 = ac.currentTime;
      const ton = (f, s, d, form = "square", till = null) => {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = form; o.frequency.setValueAtTime(f, t0 + s);
        if (till) o.frequency.exponentialRampToValueAtTime(till, t0 + s + d);
        g.gain.setValueAtTime(0.0001, t0 + s);
        g.gain.exponentialRampToValueAtTime(1, t0 + s + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + s + d);
        o.connect(g).connect(ut); o.start(t0 + s); o.stop(t0 + s + d + 0.02);
      };
      const brus = (s, d) => {
        const b = ac.createBuffer(1, ac.sampleRate * d, ac.sampleRate), x = b.getChannelData(0);
        for (let i = 0; i < x.length; i++) x[i] = (Math.random() * 2 - 1) * (1 - i / x.length);
        const k = ac.createBufferSource(), g = ac.createGain();
        g.gain.value = 0.6; k.buffer = b; k.connect(g).connect(ut); k.start(t0 + s);
      };
      ton(220, 0.05, 0.25, "triangle", 880);
      ({ eld: () => { brus(1.1, 0.6); ton(160, 1.1, 0.5, "sawtooth", 60); },
         natur: () => { [0, 0.12, 0.24, 0.36].forEach((d) => ton(900, 1.1 + d, 0.1, "triangle", 1400)); },
         blixt: () => { brus(1.25, 0.35); ton(1800, 1.2, 0.3, "square", 90); },
         vatten: () => { ton(300, 1.1, 0.7, "sine", 120); brus(1.3, 0.4); },
         is: () => { [1760, 1568, 2093, 1760].forEach((f, i) => ton(f, 1.1 + i * 0.09, 0.25, "triangle")); },
         kraft: () => { ton(80, 1.0, 0.9, "sawtooth", 40); brus(1.4, 0.8); } }[typ] || (() => {}))();
      ton(120, 1.75, 0.15, "square", 60);
      if (mot === "traff") { ton(140, 3.0, 0.2, "sawtooth", 50); brus(3.2, 0.25); }
      if (mot === "miss") ton(600, 3.15, 0.2, "triangle", 1200);
      if (mot === "ko") [392, 349, 311, 262].forEach((f, i) => ton(f, 4.0 + i * 0.22, 0.25, "triangle"));
      if (klar) [523, 659, 784, 659, 784, 1047].forEach((f, i) => ton(f, 3.3 + i * 0.14, i === 5 ? 0.6 : 0.13, "square"));
      return { stop: () => { try { ut.gain.setTargetAtTime(0, ac.currentTime, 0.05); } catch (_) {} } };
    } catch (_) {
      return null;
    }
  }

  _kartaView() {
    const s = this._s, k = s.karta;
    if (!k) return `<p class="muted">Hämtar…</p>`;
    const syskon = (s.topplista || []).filter((t) => t.id !== s.barn && t.karta);
    const d = s.meriter?.djur;
    const noder = [...k.karta].reverse(); // högst upp = framtiden
    let senVarld = null;
    const rader = noder.map((n, i) => {
      const x = [50, 72, 80, 66, 42, 24, 18, 32][n.niva % 8];
      const klar = n.niva < k.niva, nu = n.niva === k.niva;
      const har = syskon.filter((t) => t.karta.niva === n.niva);
      let rubrik = "";
      if (senVarld !== null && senVarld !== n.varld.nr) {
        const v = noder[i - 1].varld;
        rubrik = `<div class="karta-varld" style="background:${v.farg}">${v.ikon} Värld ${v.nr}: ${esc(v.namn)}${v.varv ? " ★".repeat(v.varv) : ""}</div>`;
      }
      senVarld = n.varld.nr;
      return `${rubrik}<div class="karta-rad" style="--x:${x}%; --farg:${n.varld.farg}">
        <div class="karta-nod ${klar ? "klar" : nu ? "nu" : "last"} ${n.boss ? "boss" : ""}">
          <span class="nod-ikon">${klar || nu || n.boss ? n.ikon : "🔒"}</span>
          <span class="nod-nr">${n.niva}</span>
          ${klar ? `<span class="nod-stj">${"⭐".repeat(n.stjarnor)}</span>` : ""}
          ${nu && d ? `<span class="nod-djur">${ritaDjur(d.art, "glad", Math.max(1, d.steg), {})}</span>` : ""}
          ${har.map((t) => `<span class="nod-syskon" title="${esc(t.namn)}">${t.karta.art ? ritaDjur(t.karta.art, "glad", 2, {}) : "🙂"}<b>${esc(t.namn)}</b></span>`).join("")}
        </div></div>`;
    }).join("");
    const sista = noder[noder.length - 1].varld;
    const forbi = syskon.filter((t) => t.karta.niva < k.karta[0].niva || t.karta.niva > k.karta[k.karta.length - 1].niva);
    const nuVarld = k.monster?.varld;
    return `<div class="karta-topp">⭐ ${k.stjarnor_tot} stjärnor · nivå ${k.niva}${syskon.map((t) => ` · ${esc(t.namn)}: nivå ${t.karta.niva}`).join("")}</div>
      ${nuVarld && VARLD_BERATTELSE[nuVarld.id] ? `<div class="varld-berattelse stor" style="--farg:${nuVarld.farg}"><b>${nuVarld.ikon} ${esc(nuVarld.namn)}</b><br>${esc(VARLD_BERATTELSE[nuVarld.id][0])}</div>` : ""}
      <div class="karta">${rader}<div class="karta-varld" style="background:${sista.farg}">${sista.ikon} Värld ${sista.nr}: ${esc(sista.namn)}${sista.varv ? " ★".repeat(sista.varv) : ""}</div></div>
      ${forbi.length ? `<div class="small muted center">${forbi.map((t) => `${esc(t.namn)} är på nivå ${t.karta.niva}`).join(" · ")}</div>` : ""}
      <p class="small muted center">Klara nivån snabbt för ⭐⭐⭐. Var tionde nivå är en världsboss med en egen pris-sak.</p>`;
  }

  // ---------- husdjurets rum ----------
  _rumScen(d) {
    const sak = (id) => (this._s.djurbutik || []).find((x) => x.id === id);
    const r = d.rum || {};
    const t = sak(r.tapet), g = sak(r.golv);
    const em = (plats, cls) => (r[plats] ? `<span class="rum-sak ${cls}">${sak(r[plats])?.ikon || ""}</span>` : "");
    return `<div class="rum-scen" style="background:${t?.farg || "#fff3e0"}">
      <div class="rum-golv" style="background:${g?.farg || "#bcaaa4"}"></div>
      ${r.fonster ? `<span class="rum-sak rum-fonster">${sak(r.fonster)?.ikon}</span>` : `<span class="rum-sak rum-fonster tomt">🪟</span>`}
      ${em("tavla", "rum-tavla")}${em("lampa", "rum-lampa")}${em("sang", "rum-sang")}${em("vaxt", "rum-vaxt")}${em("leksak", "rum-leksak")}
      <div class="rum-djur">${this._djurFigur({ ...d, pa: { ...(d.pa || {}), bakgrund: null } })}</div>
    </div>`;
  }

  _rumView() {
    const s = this._s;
    const d = s.meriter?.djur;
    if (!d) return `<p>Välj ett husdjur på förstasidan först.</p>`;
    const saldo = s.meriter.saldo, titta = s.kan_valja;
    const namn = { tapet: "🎨 Tapet", golv: "🟫 Golv", sang: "🛏️ Säng", lampa: "💡 Lampa", tavla: "🖼️ Väggen", vaxt: "🪴 Växt", leksak: "🧸 Leksak", fonster: "🪟 Fönster" };
    const kort = (x) => {
      const har = (d.agt || []).includes(x.id), pa = d.rum?.[x.plats] === x.id, last = d.steg < x.steg;
      let knapp;
      if (titta) knapp = pa ? `<span class="small">✅ I rummet</span>` : har ? `<span class="small">Köpt</span>` : `<span class="small muted">${x.pris} ⭐</span>`;
      else if (pa) knapp = `<button class="mini" data-rum-av="${x.plats}">Ta bort</button>`;
      else if (har) knapp = `<button class="mini primary" data-rum-pa="${x.id}" data-plats="${x.plats}">Ställ in</button>`;
      else if (last) knapp = `<span class="small muted">🔒 ${esc(s.djur_steg[x.steg])}</span>`;
      else knapp = `<button class="mini ${saldo >= x.pris ? "primary" : ""}" data-djur-kop="${x.id}" ${saldo >= x.pris ? "" : "disabled"}>${x.pris} ⭐</button>`;
      return `<div class="sak-kort ${pa ? "pa" : ""} ${last ? "last" : ""}"><div class="sak-ikon">${x.ikon}</div><div class="small">${esc(x.namn)}</div>${knapp}</div>`;
    };
    return `${this._rumScen(d)}
      <div class="butik-saldo">${titta ? `${esc(s.namn)} har <b>⭐ ${saldo}</b>.` : `Du har <b>⭐ ${saldo}</b> att inreda för`}</div>
      ${(s.rum_platser || []).map((pl) => `<h3>${namn[pl] || pl}</h3><div class="sak-rutnat">${(s.djurbutik || []).filter((x) => x.typ === "rum" && x.plats === pl).sort((a, b) => a.pris - b.pris).map(kort).join("")}</div>`).join("")}`;
  }

  // ---------- dagens utmaning ----------
  _utmaningKort() {
    const m = this._s.meriter;
    const u = m?.utmaning || [];
    if (!u.length) return "";
    const klara = u.filter((x) => x.klar).length;
    const allt = klara === u.length;
    return `<div class="utmaning-kort ${allt ? "klar" : ""}">
      <div class="djur-rubrik">🎯 Dagens utmaning <span class="small">${allt ? `Klar! +${m.utmaning_p} ⭐` : `${klara}/${u.length} · +${m.utmaning_p} ⭐`}</span></div>
      ${u.map((x) => `<div class="utm-rad ${x.klar ? "ok" : ""}">${x.klar ? "✅" : "⬜"} ${x.ikon} ${esc(x.text)}</div>`).join("")}
    </div>`;
  }

  // ---------- Glosrekord ----------
  _rekordFraga() {
    const sp = this._view.spel;
    const par = sp.par;
    const i = Math.floor(Math.random() * par.length);
    const vand = Math.random() < 0.5 ? 0 : 1; // fråga åt båda hållen
    const fraga = par[i][vand], svar = par[i][1 - vand];
    const andra = [...new Set(par.map((p) => p[1 - vand]).filter((x) => x !== svar))].sort(() => Math.random() - 0.5).slice(0, 3);
    sp.fraga = { text: fraga, svar, alt: [svar, ...andra].sort(() => Math.random() - 0.5) };
    sp.flash = null;
  }

  _rekordStart() {
    const v = this._view;
    const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
    clearInterval(this._rekordTimer);
    v.spel = { par: spelbaraPar(g), poang: 0, fel: 0, slut: Date.now() + 60000, gammalt: g.rekord?.poang || 0 };
    this._rekordFraga();
    this._render();
    this._rekordTimer = setInterval(() => {
      const sp = this._view.spel;
      if (this._view.name !== "rekord" || !sp) return clearInterval(this._rekordTimer);
      const kvar = Math.max(0, Math.ceil((sp.slut - Date.now()) / 1000));
      const el = this.shadowRoot.querySelector("#rek-tid");
      if (el) { el.textContent = kvar; el.classList.toggle("bradskande", kvar <= 10); }
      if (kvar <= 0 && !sp.klar) this._rekordSlut();
    }, 200);
  }

  async _rekordSlut() {
    const v = this._view;
    const sp = v.spel;
    clearInterval(this._rekordTimer);
    sp.klar = true;
    sp.nytt = sp.poang > sp.gammalt;
    this._render();
    if (!this._s.kan_valja) await this._act("rekord", { amne: v.amne, glosor: v.glosor, poang: sp.poang });
    this._render();
  }

  _rekordView(g) {
    const sp = this._view.spel;
    if (!g) return "";
    if (!sp) {
      return `<div class="rekord-intro"><div class="big">⚡</div>
        <p>Svara rätt på så många glosor du hinner på <b>60 sekunder</b>. Fel svar kostar tid!</p>
        <p>${g.rekord ? `Ditt rekord: <b>🏆 ${g.rekord.poang}</b>` : "Du har inget rekord än."}</p>
        <p class="small muted">Slår du ditt rekord: +5 ⭐. ${5}+ rätt räknas för sviten och dagens utmaning.</p>
        <button class="primary stor-las" id="rekord-go">▶ Starta!</button></div>`;
    }
    if (sp.klar) {
      return `<div class="done"><div class="big">${sp.nytt ? "🏆" : sp.poang >= 5 ? "⚡" : "💪"}</div>
        <div class="score">${sp.poang} rätt!</div>
        <p>${sp.nytt ? (sp.gammalt ? `NYTT REKORD! Förra var ${sp.gammalt}.` : "Ditt första rekord!") : `Rekordet är ${sp.gammalt}. ${sp.gammalt - sp.poang <= 3 ? "Så nära!" : "Försök igen!"}`}</p>
        <div class="actions" style="justify-content:center"><button class="primary" id="rekord-go">🔁 En gång till</button><button class="ghost" id="rekord-tillbaka">Klar</button></div></div>`;
    }
    const kvar = Math.max(0, Math.ceil((sp.slut - Date.now()) / 1000));
    return `<div class="rekord-topp"><span class="rek-tid ${kvar <= 10 ? "bradskande" : ""}" id="rek-tid">${kvar}</span><span class="rek-poang">⚡ ${sp.poang}</span>${sp.gammalt ? `<span class="muted small">🏆 ${sp.gammalt}</span>` : ""}</div>
      <div class="rek-fraga ${sp.flash || ""}">${esc(sp.fraga.text)}</div>
      <div class="rek-alt">${sp.fraga.alt.map((x, i) => `<button class="${sp.flash && x === sp.fraga.svar ? "ratt" : ""}" data-rek="${i}" ${sp.flash ? "disabled" : ""}>${esc(x)}</button>`).join("")}</div>`;
  }

  // Regler och meriter förklarade för barnen. Håll siffrorna i synk med meriter.py.
  _infoView() {
    const kort = (ikon, rubrik, rader) => `<div class="info-kort"><h3>${ikon} ${rubrik}</h3>${rader.map((r) => `<div class="info-rad">${r}</div>`).join("")}</div>`;
    const p = (n) => `<b class="plus">+${n} ⭐</b>`;
    return `
      <p>I Läxspelet får du <b>meriter ⭐</b> när du gör dina läxor. Ju tidigare och noggrannare du gör dem, desto fler meriter. Varje vecka finns det också en <b>tävling</b> där alla har lika stor chans att vinna.</p>

      ${kort("📥", "Lägg in läxan", [
        `Tryck <b>📥 Lägg in läxa</b> på startsidan. Välj ämne och vad du ska göra, så frågar Läxspelet resten.`,
        `Lägg in läxan i Läxspelet samma dag den kommer eller dagen efter: ${p(20)}`,
        `Senare samma vecka: ${p(5)}`,
        `Du får en påminnelse kl. 17.15 den dagen läxan brukar komma.`,
      ])}

      ${kort("✏️", "Glosor och veckans ord", [
        `Öva på <b>hela</b> glosläxan: ${p(5)} varje gång (högst 3 gånger per läxa och dag)`,
        `Alla rätt på första försöket: ${p(5)} extra`,
        `Öva minst 2 dagar före förhöret: ${p(10)} extra (en gång per dag)`,
        `🔁 Du har 2 gratis försök på varje ord. Därefter kostar ett fel svar med <b>Kolla</b> 1 ⭐. Rätt svar är alltid gratis.`,
        `💡 Fastnar du? Köp ett <b>tips</b> för 1 ⭐. Då visas nästa bokstav. Ordet räknas inte som rätt på första försöket. Tips finns bara när du övar, aldrig i förhör.`,
        `🔊 <b>Svenska veckans ord</b> övar du genom att lyssna och stava, eller titta, gömma och skriva. I förhöret läses orden upp och du stavar dem.`,
        `🔥 <b>Öva svåra ord</b> hjälper dig att lära dig orden du ofta gör fel på. Det räknas för sviten men ger inga meriter.`,
        `✍️ Har du övat på papper, till exempel i glosboken? Tryck på <b>Jag har övat på papper idag</b> och visa mamma eller pappa. När de godkänner får du samma meriter som om du övat i appen.`,
      ])}

      ${kort("📋", "Förhör", [
        `Förhör som mamma eller pappa skickar: ${p(2)} för varje rätt ord`,
        `Alla rätt: ${p(20)} extra`,
        `Gör förhöret samma dag som det kommer: ${p(5)} extra`,
        `När du har startat ett förhör måste du göra klart det innan du kan göra något annat.`,
        `✅ Minst 80 % rätt är godkänt, och då blir det fanfar och konfetti 🎉. ❌ Inte godkänt ger ett nytt förhör på samma ord. Mamma eller pappa kan ändra beslutet.`,
      ])}

      ${kort("🗣️", "Högläsning", [
        `Läs kapitlet högt för mamma eller pappa och tryck på <b>Jag har läst högt idag</b>.`,
        `När de godkänner: ${p(6)} för den dagen`,
        `Alla läsdagar i veckan: ${p(20)} extra`,
      ])}

      ${kort("✍️", "Läxboken", [
        `Tryck på <b>Jag har gjort läxboken</b> när du är klar. Mamma eller pappa kollar och godkänner.`,
        `Klar senast inlämningsdagen: ${p(25)}`,
        `Klar för sent: ${p(10)}`,
      ])}

      ${kort("📖", "Läsläxa och prov i appen", [
        `Läs sidorna i e-boken. En sida räknas som läst när du har läst den en stund.`,
        `Sedan kommer några kontrollfrågor. Har du minst 2 av 3 rätt är du klar. Annars läser du igen och får nya frågor.`,
        `Läsläxa klar i tid: ${p(30)} (för sent: ${p(10)})`,
        `Registrera ett prov minst 3 dagar innan: ${p(10)}`,
        `Plugga inför provet en dag före provet: ${p(10)} per dag (högst 5 dagar)`,
        `📝 När mamma eller pappa lägger in provresultatet: minst 90 % rätt (eller betyg A/B) ${p(50)}, 75 % (C) ${p(30)}, 60 % (D/E) ${p(15)}. Toppresultat ger medaljen 🌟 Provstjärna.`,
        `Allt läst och kontrollfrågorna klara före provdagen: ${p(40)}`,
        `📸 Fotar du en bok själv (minst 10 sidor) kan du be om lön: ${p(1)} per 2 sidor, högst 50 per bok. Mamma eller pappa kollar först att fotona är skarpa och i rätt ordning.`,
      ])}

      ${kort("🔥", "Sviten", [
        `Gör något i Läxspelet <b>varje dag</b>, även på helgen. Varje dag i rad blir en stjärna på förstasidan.`,
        `Dag 2 i rad: ${p(2)}, dag 3: ${p(3)} och så vidare upp till ${p(10)} per dag när du har 10 stjärnor.`,
        `Missar du en dag börjar sviten om från början, om du inte har ett 🛡️ svitskydd.`,
      ])}

      ${kort("🐾", "Ditt husdjur", [
        `Välj ett husdjur på förstasidan. Det börjar som ett ägg och <b>växer</b> när du samlar meriter: Ägg → Bebis → Liten → Stor → Jätte → Legend 👑.`,
        `Husdjuret äter när du gör något i Läxspelet. Gör du inget på ett par dagar blir det <b>hungrigt</b> och ledset.`,
        `🛍️ I <b>Husdjursbutiken</b> kan du köpa hattar, bakgrunder och effekter för dina stjärnor. Djuret växer ändå, för storleken räknas på alla meriter du har tjänat.`,
        `🎉 Inför högtider (jul, påsk, Halloween, sommarlov med flera) finns specialsaker i 2 veckor. Det du köper får du behålla för alltid.`,
        `🐾 Du kan ha <b>flera husdjur</b>. Ett nytt kostar 100 ⭐ och börjar som ett ägg. Byt gratis mellan dina djur i butiken. Bara djuret som är med dig växer, får XP och utvecklas av det du gör. Attacker, försvarsträning och kompisar hör till djuret du köper dem till, så ett nytt djur börjar om från början. Allt finns kvar när du byter tillbaka.`,
        `🃏 <b>Samlarkort:</b> besegrade monster tappar ibland sitt kort (50 %). I 🏟️ Arenan kan du ta <b>🔁 revansch</b> på bossar du redan har slagit (2 ⚡) och vinna kort, högst 3 kort per dag.`,
        `🎁 <b>Kistor:</b> varje gång du lägger in en läxa eller ett prov får du en kista med ⭐, ⚡ eller ett kort. Ett prov inlagt minst 3 dagar innan ger en 💎 silverkista, minst 7 dagar innan en 👑 guldkista. Högst 4 kistor per dag.`,
        `📝 <b>Provbossar:</b> varje prov blir en boss. Varje dag du pluggar inför provet tar den 15 % skada (allt klart i tid ger 20 % till). Dagen före provet öppnar slutstriden. Vinst: +20 ⭐ och en 🏆 provtrofé.`,
        `📅 <b>Veckans koll:</b> lägg in alla läxor i läxschemat i tid under veckan så får du +15 ⭐, ett 🛡️ svitskydd och en 👑 guldkista.`,
        `🗓️ <b>Mitt schema:</b> mamma, pappa eller läraren lägger in ditt schema som en digital kopia som du kan söka i och skriva ut. Efter skolan frågar husdjuret om du fick någon läxa. Svarar du ärligt nej får du +2 ⭐. Husdjuret frågar också efter studiematerial till ämnen som inte har något än, och första materialet i ett ämne ger en 💎 silverkista.`,
        `🎒 <b>Stridsuppsättning:</b> i arenan och mot världsbossar får djuret bara ta med 4 attacker. Välj dem i butiken. Mot bossen låses de när striden har börjat.`,
        `🎯 I arenan är varje djur svagt mot en typ: 🔥 mot 🌊, 🌊 mot ⚡, ⚡ mot 🍃, 🍃 mot 🔥, ❄️ mot 💥 och 💥 mot ❄️. Träffar du den svaga punkten blir det <b>×1,5</b> skada.`,
        `🌟 <b>Laddattacker</b> köps i butiken. De laddas upp av bra träffar (mest av träffar på den svaga punkten) och kan bara användas 1–2 gånger per strid.`,
        `🔥 Varje djur har ett <b>element</b>. Attacker av samma typ gör <b>+25 %</b> 💪, och en typ passar dåligt och gör <b>−25 %</b> 😕. Välj attacker som passar ditt djur och som monstren är svaga mot!`,
      ])}

      ${kort("🎯", "Dagens utmaning", [
        `Varje dag finns 2–3 mål som passar dina läxor, till exempel öva glosor, läsa högt eller spela Glosrekord.`,
        `Klarar du alla mål samma dag: ${p(15)}`,
      ])}

      ${kort("⚡", "Glosrekord", [
        `Svara rätt på så många glosor du hinner på 60 sekunder. Fel svar kostar 3 sekunder.`,
        `Slå ditt eget rekord: ${p(5)} (en gång per glosläxa och dag)`,
        `Minst 5 rätt räknas för sviten och dagens utmaning.`,
      ])}

      ${kort("🎟️", "Läxpasset", [
        `Varje merit du tjänar ger lika mycket XP. Passet har 30 nivåer med belöningar: stjärnor, saker som bara finns i passet och på nivå 30 ett glänsande husdjur.`,
        `Passet börjar om den 1:a varje månad med nya belöningar.`,
      ])}

      ${kort("🗺️", "Äventyrskartan", [
        `Kartan har nivåer med monster genom världar som 🌲 Glosskogen, 🌊 Bläckhavet och 🌋 Drakvulkanen. Varje merit du tjänar gör skada på nivåns monster.`,
        `När monstret är besegrat kommer du direkt till nästa nivå. Klarar du nivån snabbt får du ⭐⭐⭐ och fler meriter.`,
        `Var tionde nivå är en 👑 världsboss. Den ger +50 ⭐ och en sak som bara finns hos bossen.`,
        `Nivåerna blir längre ju längre du kommer, och monstrens styrka beror på hur mycket du brukar plugga och hur många läxor och prov du har.`,
        `⚔️ Attacker köper du i husdjursbutiken. De laddas med ⚡ energi: 1 energi per 25 ⭐ du tjänar.`,
        `🎯 Varje monster är svagt mot en typ (🔥 🍃 ⚡ 🌊 ❄️). Då gör attacken dubbel skada.`,
      ])}

      ${kort("⚔️", "Så strider du mot bossen", [
        `<b>1.</b> Öppna Läxspelet. Bosskortet med monstret och dess ❤️ livmätare finns på startsidan.`,
        `<b>2.</b> Tryck <b>⚔️ Till strid</b>. Då öppnas stridsscenen där du väljer attack eller öppnar 🎒 ryggsäcken.`,
        `Du kan också attackera direkt med attackknapparna under bossen.`,
        `Det här behöver du: ett kläckt husdjur, minst en attack från 🛍️ Butiken och ⚡ energi (du får energi när du pluggar).`,
        `Bossen slår tillbaka! Ibland missar den. Ditt husdjurs ❤️ liv syns i striden.`,
        `😵 Är ditt husdjur utmattat (0 liv) kan det inte attackera. Plugga för att få tillbaka liv, eller drick en 🧪 livdryck från butiken.`,
        `📺 Du kan se när syskonet attackerar under repriserna på bosskortet.`,
      ])}

      ${kort("❤️", "Husdjurets liv och nivå", [
        `Husdjuret får tillbaka 1 ❤️ liv för varje 3 ⭐ du tjänar.`,
        `⚡ Energi kan du också köpa i butiken: <b>20 ⭐</b> per ⚡, högst 5 per dag.`,
        `🧪 Livdrycker köper du i butiken och har i ryggsäcken (högst 5 av varje). 🪶 Fenixfjädern väcker ett utmattat husdjur.`,
        `Allt du tjänar ger husdjuret XP. Ny nivå ger mer ❤️ liv och starkare attacker. <b>CP</b> visar hur starkt husdjuret är.`,
      ])}

      ${kort("🛡️", "Sköldar och försvar (DEF)", [
        `Köp sköldar i 🛍️ Butiken. Skölden hör till dig och följer med när du byter husdjur. Du har en sköld på dig åt gången.`,
        `<b>🛡️ DEF</b> minskar skadan ditt husdjur tar. DEF 50 halverar skadan. DEF räknas också in i 💪 CP.`,
        `Vissa sköldar har något extra: blockera helt, skicka tillbaka skada, läka eller halv skada från en typ (🔥 🌊 ❄️ ⚡ 🍃).`,
        `Monstren slår med sin världs typ, till exempel 🔥 i Drakvulkanen. Rätt typsköld tar halva skadan.`,
        `Skölden gäller både mot bossarna och i arenan.`,
      ])}

      ${kort("🎓", "Försvarsträning", [
        `När någon utmanar ditt husdjur i arenan styr datorn det. I arenan kan du köpa träning för stjärnor (5 nivåer).`,
        `Ett tränat husdjur får mer ❤️ liv och gör mer skada när det försvarar sig. Det väljer också smartare drag.`,
        `Träningen hjälper bara när du blir utmanad, inte när du själv anfaller.`,
      ])}

      ${kort("🤝", "Plugga ihop", [
        `Tryck <b>🤝 Plugga ihop</b> på bosskortet.`,
        `<b>Pluggstund:</b> bjud in ett syskon. Ni pluggar samma kväll, och når alla som är med 20 ⭐ före midnatt får alla +10 ⭐.`,
        `<b>Glosduell:</b> utmana någon på 10 ord från dina glosor. Ni ser varandras framsteg medan ni spelar. Flest rätt vinner, och vid lika vinner den snabbaste.`,
      ])}

      ${kort("🏳️", "Lag", [
        `En förälder skapar laget under <b>🏳️ Lag</b> på bosskortet. Där väljer ni namn och märke.`,
        `<b>Lagboss:</b> varje vecka finns en stor lagboss. Allt som någon i laget pluggar gör skada. Besegrar ni den före söndag får <b>alla</b> i laget 40 ⭐.`,
        `<b>Lagbonus:</b> +5 % skada för varje lagmedlem som har pluggat idag. Peppa varandra!`,
        `<b>Lagstrid:</b> hela laget mot ett datorstyrt utmanarlag. Du styr ditt husdjur och väljer mål, datorn styr lagkamraterna. Kostar 1 ⚡.`,
      ])}

      ${kort("🏟️", "Arenan", [
        `Tryck <b>🏟️ Arenan</b> på bosskortet för att låta ditt husdjur möta syskonets husdjur.`,
        `Ni turas om att attackera. Varje tur får du mer ⚡ AP att använda på attacker. Den med liv kvar till sist vinner.`,
        `Vinst ger 10 🏆 och XP till husdjuret. Förlust ger 2 🏆. Ger du upp får du inget.`,
      ])}

      ${kort("💬", "Fråga husdjuret", [
        `Undrar du något om spelet? Tryck <b>💬 Fråga</b> på husdjurskortet. Husdjuret vet hur det går för dig och ger tips om attacker, monster och ⭐.`,
        `Läxsvar får du inte, men en ledtråd kan du få. 😉`,
      ])}

      ${kort("📚", "Plugga med husdjuret", [
        `Tryck <b>📚 Plugga med</b> på husdjurskortet, eller vid en provboss. Husdjuret blir din hjälplärare och använder dina böcker, glosor och läxor.`,
        `<b>🙋 Förklara</b>: fråga om något du inte förstår. <b>📝 Förhör mig</b>: en fråga i taget. Var 5:e rätt svar ger +8 ⭐ (2 gånger per dag), och pluggar du inför ett prov blir det en pluggdag som skadar provbossen.`,
        `<b>📷 Hjälp med uppgift</b>: fota uppgiften så hjälper husdjuret dig steg för steg. Svaret säger det aldrig, det ska du klura ut själv! 😉`,
      ])}

      ${kort("📅", "Pluggplan, övningsprov och svaga punkter", [
        `<b>📅 Pluggplan:</b> tryck på ett prov eller en provboss och välj Pluggplan. Svara på några frågor (vad som ingår, vad du kan, hur mycket tid du har, hur du pluggar bäst) så gör AI:n en plan bara för dig. Varje klar del ger +3 ⭐ och skadar provbossen.`,
        `<b>🧪 Övningsprov:</b> ett prov på ditt material, +10 ⭐. <b>🔁 Svaga punkter:</b> det du svarar fel på kommer tillbaka efter 1, 3 och 7 dagar tills det sitter.`,
        `<b>📋 Dagens läxlista</b> på startsidan visar vad du ska göra idag och i vilken ordning.`,
      ])}

      ${kort("🏠", "Husdjurets rum", [
        `Inred ditt husdjurs rum med tapet, säng, lampa, fönster och mycket mer.`,
      ])}

      ${kort("🧬", "Djuret utvecklas", [
        `När djuret är Liten utvecklas det efter det du gör mest: ⚡ Glosrekord, 📚 läsläxor, 🎯 alla rätt på förhör, ✨ många övningar eller ⚔️ besegrade bossar. Du får också en titel som syns på topplistan.`,
      ])}

      ${kort("🛡️", "Svitskydd", [
        `Var 7:e dag i rad får du ett svitskydd 🛡️ (högst 2 sparade).`,
        `Missar du en eller två dagar räddar svitskyddet sviten automatiskt när du kommer tillbaka.`,
      ])}

      ${kort("🏅", "Medaljer och nivåer", [
        `Varje ny medalj: ${p(25)}. Alla medaljer ser du under 🏅 Meriter.`,
        `Var 100:e merit går du upp en nivå.`,
      ])}

      ${kort("🏆", "Veckans tävling", [
        `Tävlingen börjar om varje måndag. Kl. 17 varje dag får du veta vem som leder.`,
        `Du tävlar mot <b>dig själv</b> lika mycket som mot syskonet. Veckopoängen räknas så här:`,
        `<b>1.</b> Hur stor del av <b>dina egna</b> läxor du har gjort i tid den här veckan.`,
        `<b>2.</b> Hur flitig du är jämfört med <b>dina egna</b> senaste 4 veckor. Lika flitig som vanligt ger 50, dubbelt så flitig ger 100.`,
        `Har du gjort <b>alla</b> läxor i tid och förra veckan också var perfekt får du full poäng på del 2.`,
        `Varje perfekt vecka i rad ger <b>+5 bonus</b> (högst +20). Därför lönar det sig alltid att hålla 100 %.`,
        `Eftersom alla jämförs med sig själva har både den yngre och den äldre lika stor chans att vinna.`,
      ])}

      ${kort("⚖️", "Regler", [
        `👍 Det du gör utanför appen ger meriter först när mamma eller pappa har godkänt det.`,
        `🙋 Tryck bara på knappen när du verkligen har gjort läxan. Säger du att du gjort något du inte gjort blir det nekat.`,
        `🚫 Fusk lönar sig inte. Gör du fel med flit missar du bonusen för alla rätt, och svåra ord ger inga meriter.`,
        `➖ Mamma och pappa kan ge bonusmeriter när du gjort något bra, och dra av meriter om någon fuskar.`,
        `🤝 Hjälp gärna varandra, men gör din egen läxa själv.`,
      ])}`;
  }

  // En stjärna per dag i rad, upp till dagen då svitbonusen är som högst.
  _svitRad(m) {
    const max = m.streak_max || 10;
    const n = m.streak || 0;
    const stjarnor = Array.from({ length: max }, (_, i) => `<span class="${i < n ? "full" : ""} ${i === n && !m.streak_idag ? "nasta" : ""}">${i < n ? "⭐" : "☆"}</span>`).join("");
    const text = n >= max
      ? `🏆 ${n} dagar i rad! Högsta bonusen: +${max} ⭐ varje dag`
      : m.streak_idag
      ? `🔥 ${n} dag${n === 1 ? "" : "ar"} i rad. Kom tillbaka imorgon för +${Math.min(max, n + 1)} ⭐`
      : n
      ? `🔥 ${n} dag${n === 1 ? "" : "ar"} i rad. Gör något idag för +${Math.min(max, n + 1)} ⭐!`
      : `Gör något i Läxspelet idag och starta en svit!`;
    const skydd = m.skydd ? ` <span class="skydd">${"🛡️".repeat(m.skydd)}</span>` : "";
    const radda = m.skydd_raddar ? `<div class="small"><b>🛡️ Svitskyddet räddar din svit på ${m.skydd_raddar} dagar om du gör något idag!</b></div>` : "";
    return `<div class="svit"><div class="svit-stj">${stjarnor}${skydd}</div><div class="small">${text}</div>${radda}</div>`;
  }

  _meriterView() {
    const s = this._s;
    const m = s.meriter;
    const v = this._view;
    const n = m.niva;
    const logg = [...(s.data.meriter?.logg || [])].reverse().slice(0, 25);
    const p = s.poang;
    const vd = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"];
    return this._meriterInnehall(m, n, logg, p);
  }

  _foralderView() {
    const s = this._s;
    const m = s.meriter;
    const v = this._view;
    const p = s.poang;
    const vd = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"];
    let foralder = "";
    {
      const schema = v.schema || (s.data.schema || []).map((x) => ({ ...x }));
      v.schema = schema;
      const amnen = s.data.amnen || [];
      const opt = (lista, val) => lista.map(([k, t]) => `<option value="${esc(k)}" ${String(val) === String(k) ? "selected" : ""}>${esc(t)}</option>`).join("");
      const butik = s.butik?.beloningar || [];
      foralder = `
        ${s.skola ? `<button class="row foralder-knapp" id="open-skola" style="margin-top:4px"><span>🏫 <b>Skolan och läraren</b>${s.skola.inkorg?.length ? ` <span class="badge">📬 ${s.skola.inkorg.length}</span>` : ""}<br><span class="muted small">Välj vad läraren får, veckobrev från läraren, rapport via e-post och klasslag</span></span><span>›</span></button>` : ""}
        ${s.djurbrev ? `<div class="card djurbrev"><b>📬 ${esc(s.djurbrev.titel)}</b><div class="small muted">${esc(s.djurbrev.period)}</div>
          ${s.djurbrev.rader.map((x) => `<p>${esc(x)}</p>`).join("")}</div>` : ""}
        <div class="row static"><span>🎂 Födelsedag för ${esc(s.namn)}<br><span class="muted small">Då väntar en present i appen</span></span>
          <span><input type="date" id="fd-datum" value="${esc(s.data.fodelsedag || "")}"> <button class="mini" id="fd-spara">Spara</button></span></div>
        ${this._hejaropForalder()}
        <button class="row foralder-knapp" id="open-lektioner" style="margin-top:4px"><span>🗓️ <b>Schema</b><br><span class="muted small">Fota ${esc(s.namn)}s lektionsschema så läser AI:n av lektioner och ämnen</span></span><span>›</span></button>
        <button class="row foralder-knapp" id="open-kalender" style="margin-top:4px"><span>📅 <b>Skolkalendrar</b><br><span class="muted small">${s.kalender ? `${s.kalender.antal} händelser för ${esc(s.namn)} · ` : ""}Koppla in skolans kalender: länk, Home Assistant, webbsida, fil eller foto</span></span><span>›</span></button>
        <button class="row foralder-knapp" id="open-coach" style="margin-top:4px"><span>🧠 <b>Studiecoach</b><br><span class="muted small">Påverka hur ${esc(s.namn)}s pluggplaner görs (t.ex. hur strikta) och prata med AI:n om studietaktiken</span></span><span>›</span></button>
        <button class="row foralder-knapp" id="open-rapport" style="margin-top:4px"><span>📊 <b>Veckorapport</b><br><span class="muted small">Vad ${esc(s.namn)} har pluggat, vad som är svårt, AI:ns tankar om studietaktiken och frågor till middagen</span></span><span>›</span></button>
        <button class="row foralder-knapp" id="open-veckobrev" style="margin-top:4px"><span>📸 <b>Veckobrev</b><br><span class="muted small">Fota brevet från skolan så lägger AI:n in veckans läxor åt ${esc(s.namn)}</span></span><span>›</span></button>
        <h3 style="margin-top:4px">📅 Läxschema för ${esc(s.namn)}</h3>
        <p class="muted small">När läxan brukar komma. Lägger ${esc(s.namn)} in den samma dag eller dagen efter blir det +${p.i_tid} ⭐. Glosor får förhörsdagen ifylld automatiskt. ${esc(s.namn)} får en påminnelse kl. 17.15 den dagen läxan brukar komma.</p>
        ${amnen.length ? "" : `<p class="muted">Skapa ett ämne först.</p>`}
        <div class="list">
          ${schema
            .map(
              (x, i) => `<div class="schema-rad">
                <input data-sch="${i}" data-f="namn" value="${esc(x.namn || "")}" placeholder="t.ex. Spanska glosor">
                <select data-sch="${i}" data-f="amne">${opt([["", "Ämne…"], ...amnen.map((a) => [a.id, a.namn])], x.amne)}</select>
                <select data-sch="${i}" data-f="typ">${opt([["glosor", "Glosor"], ["bok", "Bok/sidor"]], x.typ || "glosor")}</select>
                <label class="small">Kommer <select data-sch="${i}" data-f="kommer">${opt(vd.map((d, j) => [j, d]), x.kommer ?? 0)}</select></label>
                <label class="small">Förhör <select data-sch="${i}" data-f="forhor">${opt([["", "inget"], ...vd.map((d, j) => [j, d])], x.forhor ?? "")}</select></label>
                <button class="mini danger" data-sch-del="${i}" title="Ta bort">✕</button>
              </div>`
            )
            .join("")}
        </div>
        <div class="actions">
          <button class="ghost" id="sch-add">＋ Läxa</button>
          <button class="primary" id="sch-spara">Spara schemat</button>
        </div>

        ${(m.schema_status || []).length ? `<h3>✅ Veckans läxor</h3>
        <p class="muted small">Har ${esc(s.namn)} gjort läxan direkt i boken? Registrera den här så blir meriterna och veckopoängen rätt.</p>
        <div class="list">${m.schema_status
          .map((x) => {
            const d = forhorInfo(x.ankomst);
            const status = { i_tid: "✅ Gjord i tid", sent: "📥 Gjord sent", kommande: "⏳ Kommer senare", ej: "" }[x.status];
            return `<div class="row static"><span><b>${esc(x.namn)}</b><br><span class="muted small">kom ${esc(d.text)}</span></span>
              <span>${status || `<button class="mini" data-man-sch="${x.id}" data-ank="${x.ankomst}" data-itid="1">Gjord i tid</button> <button class="mini" data-man-sch="${x.id}" data-ank="${x.ankomst}" data-itid="0">Gjord sent</button>`}</span></div>`;
          })
          .join("")}</div>` : ""}

        <h3>🎉 Ge bonus</h3>
        <div class="actions" style="margin-top:0">
          ${[10, 25, 50].map((x) => `<button class="ghost" data-bonus="${x}">+${x} ⭐</button>`).join("")}
          <button class="ghost" id="bonus-egen">Annat…</button>
        </div>

        <h3>🎁 Belöningsbutik <span class="muted small">(bara föräldrar ser den)</span></h3>
        <p class="muted small">${esc(s.namn)} har <b>${m.saldo} ⭐</b> att lösa in.</p>
        <div class="list">
          ${butik
            .map(
              (b) => `<div class="row static"><span>🎁 ${esc(b.namn)} <span class="muted small">· ${b.kostnad} ⭐</span></span>
                <span><button class="mini" data-los-in="${b.id}" ${m.saldo < b.kostnad ? "disabled" : ""}>Lös in för ${esc(s.namn)}</button>
                <button class="mini danger" data-butik-del="${b.id}" title="Ta bort">✕</button></span></div>`
            )
            .join("")}
          <button class="row add" id="butik-add">＋ Ny belöning</button>
        </div>`;
    }
    return `
      <div class="tabs">${s.alla_barn
        .map((b) => `<button class="tab ${b.id === s.barn ? "on" : ""}" data-barn="${b.id}">${esc(b.namn)}</button>`)
        .join("")}</div>
      ${foralder}`;
  }

  // Veckans topplista: tydlig ledare, poängstaplar och en tabell där syskonen kan jämföra mer än poängen.
  _topplista() {
    const s = this._s, lista = s.topplista || [];
    if (!lista.length) return "";
    const max = Math.max(100, ...lista.map((t) => t.vecka.poang));
    const forsta = lista[0], andra = lista[1];
    const jamnt = andra && andra.vecka.poang === forsta.vecka.poang;
    const ledare = forsta.vecka.poang === 0 ? `<div class="tl-ledare tom">🏁 Veckan har precis börjat. Bli först!</div>`
      : `<div class="tl-ledare"><div class="tl-krona">🥇</div><div><b>${esc(forsta.namn)}</b> ${forsta.id === s.barn ? "(du)" : ""} leder veckan
          <div class="small">${forsta.vecka.poang} veckopoäng${andra ? (jamnt ? ` · lika med ${esc(andra.namn)}, avgjort på ${forsta.vecka.klara !== andra.vecka.klara ? "läxor i tid" : "veckans ⭐"}` : ` · ${forsta.vecka.poang - andra.vecka.poang} före ${esc(andra.namn)}`) : ""}</div></div></div>`;
    const staplar = lista.map((t, i) => `<div class="tl-rad ${t.id === s.barn ? "jag" : ""}">
        <div class="tl-namn">${["🥇", "🥈", "🥉"][i] || `${i + 1}.`} <b>${esc(t.namn)}</b>${t.titel ? ` <span class="titel-bricka">${esc(t.titel)}</span>` : ""}</div>
        <div class="tl-bar"><div style="width:${Math.max(2, (t.vecka.poang / max) * 100)}%"></div><span>${t.vecka.poang}</span></div></div>`).join("");
    // [rubrik, värde för barnet, text att visa, högst är bäst]
    const rader = [
      ["Den här veckan"],
      ["🏆 Veckopoäng", (t) => t.vecka.poang, (t) => t.vecka.poang + (t.vecka.bonus ? ` <span class="small">(+${t.vecka.bonus})</span>` : "")],
      ["✅ Läxor i tid", (t) => t.vecka.andel ?? -1, (t) => t.vecka.antal ? `${t.vecka.klara}/${t.vecka.antal}` : "–"],
      ["📈 Insats mot förr", (t) => t.vecka.forbattring ?? -1, (t) => t.vecka.forbattring !== null ? `${t.vecka.forbattring}` : "–"],
      ["⭐ Stjärnor", (t) => t.vecka.denna, (t) => t.vecka.denna],
      ["📅 Dagar pluggat", (t) => t.jamfor?.dagar ?? 0, (t) => `${t.jamfor?.dagar ?? 0}/${t.jamfor?.dagar_av ?? 7}`],
      ["📋 Förhör", (t) => t.jamfor?.forhor ?? 0, (t) => t.jamfor?.forhor ?? 0],
      ["🎯 Rätt på förhör", (t) => t.jamfor?.forhor_ratt ?? -1, (t) => t.jamfor?.forhor_ratt != null ? `${t.jamfor.forhor_ratt} %` : "–"],
      ["📝 Glosövningar", (t) => t.jamfor?.glosor ?? 0, (t) => t.jamfor?.glosor ?? 0],
      ["Totalt"],
      ["🧭 Nivå", (t) => t.niva?.niva ?? 0, (t) => t.niva?.niva ?? "–"],
      ["🌟 Stjärnor totalt", (t) => t.intjanat ?? 0, (t) => t.intjanat ?? 0],
      ["🔥 Dagar i rad", (t) => t.streak ?? 0, (t) => t.streak ?? 0],
      ["🏅 Bästa svit", (t) => t.jamfor?.basta_streak ?? 0, (t) => t.jamfor?.basta_streak ?? 0],
      ["⚡ Glosrekord", (t) => t.jamfor?.rekord ?? 0, (t) => t.jamfor?.rekord ?? 0],
      ["🎖️ Medaljer", (t) => t.jamfor?.medaljer ?? 0, (t) => t.jamfor?.medaljer ?? 0],
      ["🗺️ Kartnivå", (t) => t.karta?.niva ?? 0, (t) => t.karta?.niva ?? "–"],
      ["🐾 Husdjursnivå", (t) => t.karta?.djur_niva ?? 0, (t) => t.karta?.djur_niva ?? "–"],
    ];
    const tabell = `<div class="tl-tabell-wrap"><table class="tl-tabell"><tr><th></th>${lista.map((t) => `<th class="${t.id === s.barn ? "jag" : ""}">${esc(t.namn)}</th>`).join("")}</tr>
      ${rader.map(([rub, varde, visa]) => {
        if (!varde) return `<tr class="tl-grupp"><td colspan="${lista.length + 1}">${rub}</td></tr>`;
        const v = lista.map(varde), basta = Math.max(...v), unik = v.filter((x) => x === basta).length === 1;
        return `<tr><td>${rub}</td>${lista.map((t, i) => `<td class="${t.id === s.barn ? "jag" : ""} ${v[i] === basta && basta > 0 && unik ? "basta" : ""}">${visa(t)}${v[i] === basta && basta > 0 && unik ? " 👑" : ""}</td>`).join("")}</tr>`;
      }).join("")}</table></div>`;
    return `<h3>🏆 Veckans topplista</h3>${ledare}<div class="tl-staplar">${staplar}</div>
      <h3>📊 Jämför</h3>${tabell}
      <details class="small muted tl-info"><summary>Hur räknas veckopoängen?</summary>
        <p>Veckopoäng = hur stor del av dina egna läxor du klarat i tid + din insats jämfört med dina senaste 4 veckor. Har du alla läxor i tid vecka efter vecka får du full insats och +5 bonus för varje perfekt vecka i rad (max +20). Så har alla samma chans.</p>
        <p>Har två lika många poäng vinner den som har klarat flest läxor i tid, och sedan den som har fått flest ⭐ den här veckan. 👑 visar vem som är bäst på varje rad.</p></details>`;
  }

  _meriterInnehall(m, n, logg, p) {
    const s = this._s;
    return `
      <div class="merit-stor">
        <div class="big">${n.niva >= 7 ? "👑" : n.niva >= 4 ? "🦸" : "🧒"}</div>
        <div class="score">Nivå ${n.niva} · ${esc(n.namn)}</div>
        <div class="progress stor"><div style="width:${n.procent}%"></div></div>
        <div class="muted small">${m.intjanat} meriter totalt · ${n.kvar} till nästa nivå${m.streak ? ` · 🔥 ${m.streak} dagar i rad` : ""}</div>
      </div>

      ${this._topplista()}
      ${(s.rekord || []).length ? `<h3>🏅 Dina rekord</h3><div class="list">${s.rekord.map((x) => `<div class="row static rekord-rad ${x.ny ? "ny" : ""}">
        <span>${x.ikon} ${esc(x.namn)}${x.info ? `<br><span class="muted small">${esc(x.info)}</span>` : ""}</span><span><b>${esc(x.varde)}</b>${x.ny ? ` <span class="ny-bricka">🆕 nytt!</span>` : ""}</span></div>`).join("")}</div>` : ""}

      <h3>🏅 Medaljer</h3>
      <div class="medaljer">
        ${s.medaljlista
          .map((x) => {
            const d = m.medaljer[x.id];
            return `<div class="medalj ${d ? "har" : ""}"><div class="mi">${x.ikon}</div><div class="mn">${esc(x.namn)}</div><div class="muted small">${d ? `Klar ${esc(d)}` : esc(x.beskrivning)}</div></div>`;
          })
          .join("")}
      </div>

      <button class="row foralder-knapp" id="open-info"><span>ℹ️ <b>Så funkar meriter och tävlingen</b><br><span class="muted small">Alla regler på ett ställe</span></span><span>›</span></button>
      <h3>💡 Så får du meriter</h3>
      <div class="hur small">
        <div>⏰ Lägg in läxan samma dag den kommer: <b>+${p.i_tid}</b></div>
        <div>✏️ Öva på hela glosläxan: <b>+${p.ovning}</b> per övning (max 3 per läxa och dag)</div>
        <div>🔥 Öva svåra ord: räknas för sviten (meriter får du när du övar hela läxan)</div>
        <div>🐦 Öva minst 2 dagar före förhöret: <b>+${p.tidigt}</b> extra</div>
        <div>📋 Förhör: <b>+${p.forhor_ratt}</b> per rätt ord, alla rätt <b>+${p.forhor_alla}</b></div>
        <div>🔥 Gör något i Läxspelet varje dag, även helger: dag 2 i rad <b>+2</b>, dag 3 <b>+3</b> … upp till <b>+10</b> per dag. Missar du en dag börjar sviten om.</div>
        <div>🗣️ Högläsning som mamma eller pappa godkänner: <b>+6</b> per dag, alla dagar <b>+20</b> extra</div>
        <div>✍️ Läxboken klar i tid: <b>+25</b></div>
        <div>🏅 Varje ny medalj: <b>+${p.medalj}</b></div>
      </div>

      <h3>📜 Senaste meriterna</h3>
      ${logg.length ? `<div class="list">${logg
        .map((x) => `<div class="row static"><span>${esc(x.ikon)} ${esc(x.orsak)} <span class="muted small">${esc(x.tid.slice(5, 10))}</span></span><span class="${x.p < 0 ? "minus" : "plus"}">${x.p > 0 ? "+" : ""}${x.p}</span></div>`)
        .join("")}</div>` : `<p class="muted">Inga meriter än. Öva på glosor eller lägg in en läxa!</p>`}`;
  }

  _uppdragLista() {
    const s = this._s;
    const idag = new Date().toISOString().slice(0, 10);
    const lista = (s.data.uppdrag || [])
      .filter((u) => !u.klart || (u.klart || "").slice(0, 10) >= new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10) ||
        (u.typ === "prov" && (u.resultat ? (u.resultat.tid || "").slice(0, 10) >= plusDagar(idag, -7) : s.kan_valja && u.datum <= idag && u.datum >= plusDagar(idag, -30))))
      .sort((a, b) => (a.klart ? 1 : 0) - (b.klart ? 1 : 0) || a.datum.localeCompare(b.datum));
    const kort = lista
      .map((u) => {
        const f = forhorInfo(u.datum);
        const pct = u.sidor.length ? (u.lasta / u.sidor.length) * 100 : 0;
        const sen = !u.klart && u.datum < idag;
        if (u.typ === "hogl" || u.typ === "skriv") return this._veckoKort(u, f, sen);
        return `<button class="uppdrag-kort ${u.typ} ${u.klart ? "klar" : ""} ${sen ? "sen" : ""}" data-open-uppdrag="${u.id}" data-amne="${u.amne}">
          <div class="uk-rad"><b>${TYP_IKON[u.typ] || "📖"} ${TYP_NAMN[u.typ] || "Läsläxa"}: ${esc(u.namn)}</b><span class="small">${u.resultat ? `${provResText(u.resultat)}` : u.typ === "prov" && s.kan_valja && u.datum <= idag ? "✏️ Lägg in resultat" : u.klart ? "✅ Klar" : u.typ === "prov" ? `${esc(f.text)} · ${f.kvar}` : `senast ${esc(f.text)}`}</span></div>
          ${u.sidor.length ? `<div class="small">${esc(u.kapitel || `Sidorna ${u.fran}–${u.till}`)} · ${u.lasta}/${u.sidor.length} sidor lästa</div><div class="progress"><div style="width:${pct}%"></div></div>` : ""}
          ${u.glosor?.length ? `<div class="small">+ ${u.glosor.length} glosläx${u.glosor.length === 1 ? "a" : "or"}</div>` : ""}
        </button>`;
      })
      .join("");
    return `
      <h3>📖 Veckans läxor & prov</h3>
      ${kort}
      <button class="primary laxa-knapp" id="ny-laxa">📥 Lägg in läxa</button>`;
  }

  // Guidad inläggning av alla sorters läxor: ämne → vad ska göras → frågor för just den läxan.
  _laxaView() {
    const v = this._view;
    const amnen = this._s.data.amnen || [];
    if (v.steg === "amne" || !v.steg) {
      return `
        <p class="guide-fraga">Vilket ämne är läxan i?</p>
        <div class="grid">
          ${amnen.map((a) => `<button class="card amne" style="--c:${a.farg}" data-laxa-amne="${a.id}"><div class="amne-namn">${esc(a.namn)}</div></button>`).join("")}
          <button class="card add" id="laxa-nytt-amne">＋ Nytt ämne</button>
        </div>`;
    }
    const a = this._amne(v.amne);
    if (!a) return `<p class="muted">Ämnet finns inte längre.</p>`;
    if (v.steg === "typ") {
      const d = delarFor(a);
      const val = [
        { id: "glosor", del: "glosor", ikon: "🗣️", text: "Lära mig glosor", besk: "Ord på ett annat språk, eller veckans ord" },
        { id: "formler", del: "formler", ikon: "📐", text: "Lära mig formler", besk: "T.ex. v = s / t eller arean av en cirkel" },
        { id: "begrepp", del: "begrepp", ikon: "💡", text: "Lära mig begrepp", besk: "Ord och vad de betyder, t.ex. fotosyntes" },
        { id: "las", del: "bocker", ikon: "📖", text: "Läsa i boken", besk: "Sidor eller kapitel som ska läsas" },
        { id: "prov", del: null, ikon: "📝", text: "Plugga till ett prov", besk: "Provdatum, vad som ingår och plugga varje dag" },
        { id: "uppgift", del: "uppgifter", ikon: "✅", text: "Göra en uppgift", besk: "Räkna, skriva, lösa, ta med något…" },
      ];
      const passar = val.filter((x) => !x.del || d.includes(x.del));
      const andra = val.filter((x) => x.del && !d.includes(x.del));
      const knapp = (x) => `<button class="row guide-val" data-laxa-typ="${x.id}"><span>${x.ikon} <b>${esc(x.text)}</b><br><span class="muted small">${esc(x.besk)}</span></span><span>›</span></button>`;
      return `
        <p class="guide-fraga">Vad ska du göra i <b>${esc(a.namn)}</b>?</p>
        <div class="list">${passar.map(knapp).join("")}</div>
        ${andra.length ? `<p class="small muted" style="margin-top:14px">Annat</p><div class="list">${andra.map(knapp).join("")}</div>` : ""}`;
    }
    if (v.steg === "uppgift") {
      const idag = idagISO();
      const fredag = plusDagar(idag, ((4 - ((new Date(`${idag}T12:00:00`).getDay() + 6) % 7)) + 7) % 7 || 7);
      const snabb = [["Imorgon", plusDagar(idag, 1)], ["Om 2 dagar", plusDagar(idag, 2)], ["Fredag", fredag], ["Om en vecka", plusDagar(idag, 7)]];
      return `
        <p class="guide-fraga">Vad ska du göra?</p>
        <input id="lx-text" class="guide-input" maxlength="200" placeholder="t.ex. Räkna s. 34 uppg. 1–10" value="${esc(v.text || "")}">
        <p class="guide-fraga">När ska det vara klart?</p>
        <div class="snabb-datum">
          ${snabb.map(([n, d]) => `<button class="${v.datum === d ? "primary" : "ghost"}" data-lx-datum="${d}">${n}<br><span class="small">${esc(veckodag(d))}</span></button>`).join("")}
          <button class="${v.datum === "" ? "primary" : "ghost"}" data-lx-datum="">Inget datum</button>
        </div>
        <label class="small">…eller välj dag <input id="lx-datum" type="date" value="${esc(v.datum || "")}"></label>
        <div class="actions"><button class="primary" id="lx-spara" ${this._busy ? "disabled" : ""}>✅ Spara uppgiften</button></div>`;
    }
    return "";
  }

  _uppdragNyView() {
    const s = this._s;
    const v = this._view;
    const amnen = s.data.amnen || [];
    const a = amnen.find((x) => x.id === v.amne);
    const bocker = (a?.bocker || []).filter((b) => b.ebok);
    const kapitel = v.kapitelLista || [];
    return `
      <div class="form">
        <label>Namn <input id="u-namn" value="${esc(v.namn || "")}" placeholder="${v.typ === "prov" ? "t.ex. SO-prov vikingatiden" : "t.ex. Läs kapitel 3"}" maxlength="40"></label>
        <label>Ämne <select id="u-amne"><option value="">Välj…</option>${amnen.map((x) => `<option value="${x.id}" ${x.id === v.amne ? "selected" : ""}>${esc(x.namn)}</option>`).join("")}</select></label>
        ${
          a
            ? `<label>Bok ${v.typ === "prov" ? "(valfritt)" : ""} <select id="u-bok"><option value="">${bocker.length ? "Välj…" : "Inga böcker med e-bok i ämnet"}</option>${bocker
                .map((b) => `<option value="${b.id}" ${b.id === v.bok ? "selected" : ""}>${esc(b.namn)}</option>`)
                .join("")}</select></label>`
            : ""
        }
        ${
          v.bok
            ? `${kapitel.length ? `<div class="small muted">Välj kapitel:</div><div class="kap-val">${kapitel
                .map((k, i) => `<label class="kap-rad"><input type="checkbox" data-kap="${i}" ${v.valda?.includes(i) ? "checked" : ""}> ${esc(k.text)} <span class="muted small">s. ${k.fran}–${k.till}</span></label>`)
                .join("")}</div><div class="small muted">…eller skriv sidorna:</div>` : ""}
               <div class="two">
                 <label>Från sida <input id="u-fran" type="number" inputmode="numeric" value="${esc(v.fran ?? "")}"></label>
                 <label>Till sida <input id="u-till" type="number" inputmode="numeric" value="${esc(v.till ?? "")}"></label>
               </div>`
            : ""
        }
        ${
          v.typ === "prov" && a?.glosor?.length
            ? `<div class="small muted">Glosor som ingår i provet:</div><div class="kap-val">${a.glosor
                .map((g) => `<label class="kap-rad"><input type="checkbox" data-u-glosor="${g.id}" ${v.glosor?.includes(g.id) ? "checked" : ""}> ${esc(g.namn)}</label>`)
                .join("")}</div>`
            : ""
        }
        <label>${v.typ === "prov" ? "Provdatum" : "Klart senast"} <input id="u-datum" type="date" value="${esc(v.datum || "")}"></label>
      </div>
      <div class="actions"><button class="primary" id="u-spara">Spara</button></div>
      ${!s.kan_valja && v.typ === "prov" ? `<p class="muted small">Registrerar du provet minst 3 dagar innan får du +10 ⭐.</p>` : ""}`;
  }

  _uppdragView(u) {
    const s = this._s;
    const v = this._view;
    const f = forhorInfo(u.datum);
    const las = s.data.lasning?.[u.bok] || {};
    const a = this._amne(u.amne);
    const bok = a?.bocker.find((b) => b.id === u.bok);
    const forstaOlast = u.sidor.find((x) => (las[x.nyckel] || 0) < 20);
    let fragor = "";
    if (u.klart) {
      const sista = (u.forsok || []).slice(-1)[0];
      fragor = `<div class="done" style="padding:14px 0"><div class="big">🎉</div><div class="score">Klar!</div>
        <div class="muted small">${u.utan_fragor ? "Alla sidor lästa." : sista ? `${sista.ratt} av ${sista.av} rätt på kontrollfrågorna.` : ""}</div></div>`;
    } else if (u.fragor?.length && !s.kan_valja) {
      const svar = v.svar || [];
      fragor = `<h3>✅ Kontrollfrågor</h3>
        ${u.fragor
          .map(
            (q, i) => `<div class="kontroll"><div><b>${i + 1}. ${esc(q.fraga)}</b></div>${q.alternativ
              .map((alt, j) => `<button class="row ${svar[i] === j ? "vald-rad" : ""}" data-kq="${i}" data-ka="${j}">${esc(alt)}</button>`)
              .join("")}</div>`
          )
          .join("")}
        <div class="actions"><button class="primary" id="u-svara" ${svar.filter((x) => x !== undefined).length === u.fragor.length ? "" : "disabled"}>Lämna in svaren</button></div>`;
    } else if (u.allt_last && !s.kan_valja) {
      fragor = `<button class="primary stor-las" id="u-fragor">✅ Gör kontrollfrågorna</button>
        <p class="muted small center">Klarar du dem får du ${u.typ === "las" ? "+30" : "+40"} ⭐</p>`;
    } else if (u.allt_last) {
      fragor = `<div class="forhor-kort">Alla sidor är lästa. Väntar på att ${esc(s.namn)} gör kontrollfrågorna.</div>`;
    }
    const misslyckade = (u.forsok || []).filter((x) => x.ratt * 3 < x.av * 2);
    return `
      <div class="forhor-kort ${!u.klart && f.dagar >= 0 && f.dagar <= 2 ? "snart" : ""}">
        ${u.typ === "prov" ? "📝 Prov" : "📖 Läsläxa"} i ${esc(u.amne_namn)} · ${u.typ === "prov" ? "provet är" : "klart senast"} <b>${esc(f.text)}</b> · ${f.kvar}
      </div>
      ${
        u.sidor.length
          ? `<div class="small">${esc(bok?.namn || "")}: ${esc(u.kapitel || "")} sidorna ${esc(u.fran)}–${esc(u.till)}</div>
             <div class="progress stor" style="margin:8px 0"><div style="width:${(u.lasta / u.sidor.length) * 100}%"></div></div>
             <div class="small">${u.lasta} av ${u.sidor.length} sidor lästa</div>
             <div class="sid-prickar">${u.sidor.map((x) => `<span class="${(las[x.nyckel] || 0) >= (x.sek || 20) ? "last" : ""}" title="Sida ${esc(x.sidnr || "")}">${esc(x.sidnr || "·")}</span>`).join("")}</div>
             ${!u.klart && !u.allt_last ? `<button class="primary stor-las" id="u-las" data-nyckel="${esc(forstaOlast?.nyckel || "")}">📖 ${u.lasta ? "Läs vidare" : "Börja läsa"}</button>` : ""}`
          : ""
      }
      ${misslyckade.length && !u.klart ? `<p class="muted small">Förra gången blev det för många fel. Läs igenom sidorna igen och försök på nytt. Det blir nya frågor.</p>` : ""}
      ${fragor}
      ${
        u.glosor?.length
          ? `<h3>🗣️ Glosor i provet</h3><div class="list">${u.glosor
              .map((gid) => a?.glosor.find((g) => g.id === gid))
              .filter(Boolean)
              .map((g) => `<button class="row" data-open-glosor="${g.id}" data-amne="${u.amne}"><span>📝 ${esc(g.namn)}</span><span class="muted small">Öva ›</span></button>`)
              .join("")}</div>`
          : ""
      }
      ${u.typ === "prov" && u.datum > idagISO() ? `<div class="actions"><button class="primary" data-plan="${u.id}">📅 ${u.plan?.delar?.length ? `Pluggplan (${u.plan.delar.filter((x) => x.klar).length}/${u.plan.delar.length})` : "Gör en pluggplan"}</button><button class="ghost" data-ovp="${u.id}">🧪 Övningsprov</button>${s.meriter?.djur ? `<button class="ghost" data-hjalp-prov="${u.id}">📚 Plugga med ${esc(s.meriter.djur.namn)}</button>` : ""}</div>` : ""}
      ${(u.typ === "las" || u.typ === "hogl") && s.meriter?.djur && u.sidor?.length ? `<button class="row" data-hjalp-las="${u.amne}|${u.id}"><span>🧠 <b>Prata om boken med ${esc(s.meriter.djur.namn)}</b><br><span class="muted small">Husdjuret ställer frågor om det du har läst. Rätt svar räknas mot ⭐</span></span><span>›</span></button>` : ""}
      ${u.typ === "prov" ? this._provResultat(u) : ""}
      ${s.kan_valja && !u.klart ? `<button class="row foralder-knapp" id="u-manuell"><span>✅ <b>Gjord i boken</b><br><span class="muted small">Registrera att ${esc(s.namn)} har gjort den utanför appen, så blir meriterna rätt</span></span><span>›</span></button>` : ""}
      ${u.manuell ? `<p class="muted small">Registrerad som gjord i boken.</p>` : ""}
      ${s.kan_valja && u.typ === "prov" && !u.klart ? this._dagValjare("📚 Pluggat inför provet utanför appen", u.studiedagar || [], (d) => d < u.datum, "data-man-plugg") : ""}
      ${s.kan_valja || u.av_id === s.user_id ? `<div class="actions"><button class="ghost danger" id="u-ta-bort">Ta bort</button></div>` : ""}`;
  }

  _provResultat(u) {
    const s = this._s;
    const r = u.resultat;
    const idag = idagISO();
    const kort = r
      ? `<div class="prov-res ${r.andel >= 0.9 ? "topp" : r.andel >= 0.6 ? "bra" : ""}">
          <div class="pr-rubrik">${provResText(r)}${r.max ? ` <span class="small">(${Math.round(r.andel * 100)} %)</span>` : ""}</div>
          ${r.p ? `<div>${r.andel >= 0.9 ? "Toppresultat" : r.andel >= 0.75 ? "Mycket bra resultat" : "Bra resultat"}! <b>+${r.p} ⭐</b></div>` : `<div>${s.kan_valja ? "Under 60 %, ingen belöning." : "Nästa gång går det bättre. Plugga i god tid! 💪"}</div>`}
          ${r.kommentar ? `<div class="muted">"${esc(r.kommentar)}"</div>` : ""}
          <div class="muted small">Inlagt av ${esc(r.av || "")}</div>
        </div>`
      : "";
    if (!s.kan_valja) return r ? `<h3>📝 Provresultat</h3>${kort}` : "";
    if (!r && u.datum > idag) return "";
    const b = this._view.provBetyg ?? (r?.betyg ? "betyg" : "poang");
    return `<h3>📝 Provresultat</h3>${kort}
      <div class="forhor-kort prov-form">
        <div class="pf-val"><label><input type="radio" name="pr-typ" value="poang" ${b === "poang" ? "checked" : ""}> Poäng</label>
          <label><input type="radio" name="pr-typ" value="betyg" ${b === "betyg" ? "checked" : ""}> Betyg A–F</label></div>
        ${b === "poang"
          ? `<div class="pf-rad"><input id="pr-poang" type="number" inputmode="decimal" min="0" step="0.5" placeholder="Poäng" value="${r?.max ? r.poang : ""}"> av
             <input id="pr-max" type="number" inputmode="decimal" min="1" step="0.5" placeholder="Max" value="${r?.max || ""}"></div>`
          : `<div class="pf-rad">${["A", "B", "C", "D", "E", "F"].map((x) => `<label class="pf-betyg"><input type="radio" name="pr-betyg" value="${x}" ${r?.betyg === x ? "checked" : ""}> ${x}</label>`).join("")}</div>`}
        <input id="pr-komm" placeholder="Kommentar (frivilligt)" value="${esc(r?.kommentar || "")}" maxlength="200">
        <div class="muted small">Belöning: minst 90 % +50 ⭐ · 75 % +30 ⭐ · 60 % +15 ⭐ (betyg A/B = topp, C = mycket bra, E–D = bra). Ändrar du resultatet justeras meriterna.</div>
        <div class="actions"><button class="primary" id="pr-spara">${r ? "Spara ändring" : "💾 Spara resultat"}</button>${r ? `<button class="ghost danger" id="pr-rensa">Ta bort resultat</button>` : ""}</div>
      </div>`;
  }

  // Förälder: tryck på dagen då barnet gjorde något utanför appen (senaste 7 dagarna). Meriterna räknas som den dagen.
  _dagValjare(rubrik, gjorda, tillaten, attr, angra = null) {
    const idag = idagISO();
    const dagar = Array.from({ length: 7 }, (_, i) => plusDagar(idag, i - 6)).filter(tillaten);
    if (!dagar.length) return "";
    return `<div class="dag-val"><div class="small"><b>${rubrik}</b><br><span class="muted">Tryck på dagen det gjordes, så blir meriterna som om det gjorts i appen just då.${angra ? " Tryck på en grön dag för att ta bort den." : ""}</span></div>
      <div class="dag-prickar">${dagar
        .map((d) => angra && angra.dagar.includes(d)
          ? `<button class="mini ok-knapp" ${angra.attr}="${d}">${esc(veckodag(d).slice(0, 2))} ✓</button>`
          : gjorda.includes(d)
          ? `<span class="ok">${esc(veckodag(d).slice(0, 2))} ✓</span>`
          : `<button class="mini" ${attr}="${d}">${esc(d === idag ? "idag" : veckodag(d).slice(0, 2) + " " + Number(d.slice(8)))}</button>`)
        .join("")}</div></div>`;
  }

  _sidText(u) {
    if (!u.fran) return "";
    return u.till && String(u.till) !== String(u.fran) ? `s. ${esc(u.fran)}–${esc(u.till)}` : `s. ${esc(u.fran)}`;
  }

  _veckoKort(u, f, sen) {
    const idag = idagISO();
    let rad = "";
    if (u.typ === "hogl") {
      const ok = u.dagar.filter((d) => d.status === "ok").length;
      rad = `<div class="dag-prickar">${u.dagar
        .map((d) => `<span class="${d.status || ""} ${d.datum === idag ? "idag" : ""}">${esc(veckodag(d.datum).slice(0, 2))}${d.status === "ok" ? " ✓" : d.status === "vantar" ? " ⏳" : ""}</span>`)
        .join("")}</div><div class="small muted">${ok} av ${u.dagar.length} dagar godkända</div>`;
    } else {
      rad = `<div class="small">${u.vantar && !u.klart ? "⏳ Väntar på godkännande" : esc(u.kapitel || "")}</div>`;
    }
    return `<button class="uppdrag-kort ${u.typ} ${u.klart ? "klar" : ""} ${sen ? "sen" : ""}" data-open-uppdrag="${u.id}" data-amne="${u.amne}">
      <div class="uk-rad"><b>${TYP_IKON[u.typ]} ${esc(u.namn)}</b><span class="small">${u.klart ? "✅ Klar" : u.typ === "skriv" ? `lämnas ${esc(f.text)}` : `${esc(u.kapitel || "")}`}</span></div>
      ${rad}
    </button>`;
  }

  _kopplad(u) {
    const l = (this._s.data.uppdrag || []).find((x) => (u.kopplad && x.id === u.kopplad) || x.kopplad === u.id);
    if (!l) return "";
    const f = forhorInfo(l.datum);
    return `<button class="row" data-open-uppdrag="${l.id}" data-amne="${l.amne}"><span>${TYP_IKON[l.typ]} Hör ihop med: <b>${esc(l.namn)}</b><br><span class="muted small">${l.klart ? "✅ Klar" : l.typ === "skriv" ? `lämnas in ${esc(f.text)}` : esc(l.kapitel || "")}</span></span><span>›</span></button>`;
  }

  _hoglView(u) {
    const s = this._s;
    const idag = idagISO();
    const a = this._amne(u.amne);
    const bok = a?.bocker.find((b) => b.id === u.bok);
    const dagIdag = u.dagar.find((d) => d.datum === idag);
    const ok = u.dagar.filter((d) => d.status === "ok").length;
    const rader = u.dagar
      .map((d) => {
        const status = { ok: "✅ Godkänd", vantar: "⏳ Väntar på godkännande", nej: "❌ Inte godkänd" }[d.status] || (d.datum < idag ? "Inte gjord" : "");
        let knappar = "";
        if (s.kan_valja && d.status !== "ok") {
          knappar = d.status === "vantar"
            ? `<button class="mini" data-godkann="${d.datum}" data-ok="1">👍 Godkänn</button> <button class="mini danger" data-godkann="${d.datum}" data-ok="0">Neka</button>`
            : d.datum <= idag ? `<button class="mini" data-hogl-bocka="${d.datum}">✅ Bocka av</button>` : "";
        }
        const live = s.kan_valja && d.datum === idag && !["ok", "vantar"].includes(d.status) && !u.klart
          ? this._live?.uid === u.id
            ? `<div class="insp-ruta"><div class="insp-rad">🎧 ${esc(this._live.text)}</div><button class="ghost" id="live-stopp">⏹ Sluta lyssna</button></div>`
            : `<button class="mini" data-live="${esc(u.id)}">🎧 Lyssna live</button>`
          : "";
        const lyssna = live || (d.inspelning
          ? this._lyssna?.fil === d.inspelning
            ? `<audio controls autoplay src="${this._lyssna.url}" style="width:100%;margin-top:6px"></audio>`
            : `<button class="mini" data-lyssna="${esc(d.inspelning)}">🎧 Lyssna${d.insp_sek ? ` (${Math.floor(d.insp_sek / 60)}:${String(d.insp_sek % 60).padStart(2, "0")})` : ""}</button>`
          : "");
        return `<div class="row static ${d.datum === idag ? "idag-rad" : ""}" style="flex-wrap:wrap"><span><b>${esc(veckodag(d.datum))}</b> <span class="muted small">${esc(forhorInfo(d.datum).text)}</span><br><span class="small">${status}</span></span><span>${knappar}</span>${lyssna ? `<div style="flex-basis:100%">${lyssna}</div>` : ""}</div>`;
      })
      .join("");
    let stor = "";
    if (!s.kan_valja && dagIdag && !u.klart) {
      stor = dagIdag.status === "ok"
        ? `<div class="forhor-kort">✅ Dagens högläsning är godkänd. Bra jobbat!</div>`
        : dagIdag.status === "vantar"
        ? `<div class="forhor-kort">⏳ Väntar på att mamma eller pappa godkänner.</div>`
        : this._insp?.uid === u.id
        ? this._inspRuta(u)
        : `${this._inspRuta(u)}
           <button class="ghost" id="hogl-klar" style="width:100%">🗣️ Jag har läst högt för mamma eller pappa</button>
           <p class="muted small center">Spela in när du läser högt, eller läs för mamma eller pappa. När de godkänner får du +6 ⭐. Alla dagar = +20 ⭐ extra!</p>`;
    }
    return `
      <div class="forhor-kort">🗣️ Högläsning i ${esc(u.amne_namn)}${bok ? ` · ${esc(bok.namn)}` : ""}<br>
        <b>${esc(u.kapitel || u.namn)}</b> ${this._sidText(u)}</div>
      ${u.klart ? `<div class="done" style="padding:10px 0"><div class="big">🌟</div><div class="score">Alla dagar klara!</div></div>` : ""}
      ${stor}
      ${u.sidor.length ? `<button class="ghost" id="u-las" data-nyckel="${esc(u.sidor[0].nyckel)}" style="width:100%;margin:6px 0">📘 Öppna kapitlet i e-boken</button>` : ""}
      <h3>📅 Läsdagar · ${ok} av ${u.dagar.length}</h3>
      <div class="list">${rader}</div>
      ${this._kopplad(u)}
      ${s.kan_valja || u.av_id === s.user_id ? `<div class="actions"><button class="ghost danger" id="u-ta-bort">Ta bort</button></div>` : ""}`;
  }

  // ---------- inspelning av högläsning ----------
  _inspRuta(u) {
    const i = this._insp?.uid === u.id ? this._insp : null;
    if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) return "";
    if (!i) return `<button class="primary stor-las" data-insp-start="${esc(u.id)}">🎙️ Spela in när jag läser högt</button>`;
    const tid = (sek) => `${Math.floor(sek / 60)}:${String(sek % 60).padStart(2, "0")}`;
    if (i.rec) {
      return `<div class="insp-ruta"><div class="insp-rad"><span class="insp-prick"></span> Spelar in <b id="insp-tid">${tid(Math.round((Date.now() - i.start) / 1000))}</b></div>
        <div class="muted small">Läs högt och tydligt. Du kan bläddra i e-boken medan du läser.</div>
        <button class="primary" id="insp-stopp">⏹ Jag är klar</button></div>`;
    }
    return `<div class="insp-ruta"><div class="insp-rad">🎙️ Inspelning klar (${tid(i.sek)})</div>
      <audio controls src="${i.url}" style="width:100%"></audio>
      <div class="actions" style="margin-top:6px"><button class="primary" id="insp-skicka">📤 Skicka till mamma och pappa</button>
      <button class="ghost" id="insp-om">🔄 Spela in igen</button></div></div>`;
  }

  async _inspStart(uid) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const typ = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"].find((t) => MediaRecorder.isTypeSupported?.(t)) || "";
      const rec = new MediaRecorder(stream, typ ? { mimeType: typ, audioBitsPerSecond: 48000 } : undefined);
      const i = { uid, rec, stream, bitar: [], start: Date.now(), typ: rec.mimeType || typ || "audio/mp4" };
      i.ko = this._inspLive({ steg: "start", typ: rec.mimeType || typ }).then((r) => { i.live = !!r?.fil; }).catch(() => {});
      rec.ondataavailable = (e) => {
        if (!e.data?.size) return;
        i.bitar.push(e.data);
        i.ko = i.ko.then(() => i.live && this._inspLive({ steg: "del" }, e.data)).catch(() => {});
      };
      rec.onstop = () => {
        i.stream.getTracks().forEach((t) => t.stop());
        clearInterval(i.timer);
        i.wake?.release?.().catch?.(() => {});
        i.sek = Math.round((Date.now() - i.start) / 1000);
        i.blob = new Blob(i.bitar, { type: i.typ });
        i.url = URL.createObjectURL(i.blob);
        i.rec = null;
        this._render();
      };
      rec.start(5000);
      i.timer = setInterval(() => {
        const el = this.shadowRoot.querySelector("#insp-tid");
        const sek = Math.round((Date.now() - i.start) / 1000);
        if (el) el.textContent = `${Math.floor(sek / 60)}:${String(sek % 60).padStart(2, "0")}`;
        if (sek >= 30 * 60 && i.rec) i.rec.stop(); // max 30 minuter
      }, 1000);
      try { i.wake = await navigator.wakeLock?.request?.("screen"); } catch (e) { /* skärmen får släckas */ }
      this._insp = i;
      this._msg = null;
    } catch (e) {
      this._msg = { type: "error", text: "Kunde inte starta mikrofonen. Tillåt mikrofonen för Home Assistant-appen i telefonens inställningar." };
    }
    this._render();
  }

  async _inspLive(falt, bit) {
    const fd = new FormData();
    fd.append("barn", this._s.barn);
    fd.append("id", this._insp?.uid || falt.id || "");
    for (const [k, val] of Object.entries(falt)) fd.append(k, val);
    if (bit) fd.append("file", bit, "del");
    const res = await this._hass.fetchWithAuth("/api/skolan/inspelning", { method: "POST", body: fd });
    return res.ok ? res.json() : null;
  }

  // ---------- medhörning (förälder) ----------
  async _liveStart(uid) {
    this._liveStopp();
    const ljud = new Audio();
    try { ljud.src = TYST_LJUD; ljud.play().catch(() => {}); } catch (e) { /* ok */ }
    const L = (this._live = { uid, ljud, storlek: 0, pos: 0, text: "Ansluter…", forsta: true });
    this._render();
    const barn = this._s.barn;
    const info = async () => (await this._hass.fetchWithAuth(`/api/skolan/inspelning?barn=${encodeURIComponent(barn)}&id=${encodeURIComponent(uid)}`)).json();
    const hamta = async () => {
      if (this._live !== L) return;
      try {
        const x = await info();
        if (!x.fil) { L.text = "Ingen läser just nu."; L.slut = true; this._render(); return; }
        const res = await this._hass.fetchWithAuth(`/api/skolan/fil?barn=${encodeURIComponent(barn)}&fil=${encodeURIComponent(x.fil)}&t=${Date.now()}`);
        const blob = await res.blob();
        if (this._live !== L) return;
        if (blob.size > L.storlek && (L.forsta || ljud.paused || ljud.ended)) {
          L.storlek = blob.size;
          const pos = L.forsta ? null : ljud.currentTime || L.pos;
          if (L.url) URL.revokeObjectURL(L.url);
          L.url = URL.createObjectURL(blob);
          ljud.src = L.url;
          ljud.onloadedmetadata = () => {
            try {
              if (pos === null) {
                // Börja nära det barnet läser just nu
                const slut = ljud.seekable?.length ? ljud.seekable.end(0) : ljud.duration;
                if (Number.isFinite(slut) && slut > 4) ljud.currentTime = slut - 4;
              } else ljud.currentTime = pos;
            } catch (e) { /* ok */ }
            ljud.play().catch(() => { L.text = "Tryck på 🎧 igen för att lyssna."; this._render(); });
          };
          L.forsta = false;
          L.text = x.aktiv ? `🔴 Lyssnar live (${Math.floor(x.sek / 60)}:${String(x.sek % 60).padStart(2, "0")})` : "Lyssnar…";
          this._render();
        } else if (!x.aktiv && blob.size <= L.storlek && (ljud.paused || ljud.ended)) {
          L.text = "Inläsningen är slut. ✅"; L.slut = true; this._render(); return;
        }
      } catch (e) { /* försök igen */ }
      L.timer = setTimeout(hamta, 3000);
    };
    ljud.onended = () => { L.pos = ljud.currentTime; };
    hamta();
  }

  _liveStopp() {
    const L = this._live;
    if (!L) return;
    clearTimeout(L.timer);
    try { L.ljud.pause(); } catch (e) { /* ok */ }
    if (L.url) URL.revokeObjectURL(L.url);
    this._live = null;
  }

  _inspAvbryt() {
    const i = this._insp;
    if (!i) return;
    if (i.rec) { i.rec.onstop = null; i.rec.stop(); i.stream.getTracks().forEach((t) => t.stop()); clearInterval(i.timer); }
    if (i.url) URL.revokeObjectURL(i.url);
    this._insp = null;
  }

  async _inspSkicka() {
    const i = this._insp;
    if (!i?.blob) return;
    this._busy = true;
    this._render();
    try {
      const fd = new FormData();
      fd.append("barn", this._s.barn);
      fd.append("id", i.uid);
      fd.append("sek", String(i.sek));
      fd.append("file", i.blob, i.typ.includes("webm") ? "inspelning.webm" : "inspelning.m4a");
      const res = await this._hass.fetchWithAuth("/api/skolan/inspelning", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._nyData(body.data);
      this._inspAvbryt();
      this._msg = { type: "ok", text: "Skickat! Mamma eller pappa lyssnar och godkänner. 🎙️" };
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _skrivView(u) {
    const s = this._s;
    const f = forhorInfo(u.datum);
    const a = this._amne(u.amne);
    const bok = a?.bocker.find((b) => b.id === u.bok);
    let mitt = "";
    if (u.klart) {
      mitt = `<div class="done" style="padding:10px 0"><div class="big">🎉</div><div class="score">Klar!</div>${u.manuell ? `<div class="muted small">Registrerad som gjord i boken.</div>` : ""}</div>`;
    } else if (u.vantar) {
      mitt = s.kan_valja
        ? `<div class="forhor-kort">${esc(s.namn)} säger att läxboken är gjord. Har du kollat?</div>
           <div class="actions"><button class="primary" data-godkann="" data-ok="1">👍 Godkänn</button><button class="ghost danger" data-godkann="" data-ok="0">Neka</button></div>`
        : `<div class="forhor-kort">⏳ Väntar på att mamma eller pappa kollar och godkänner.</div>`;
    } else if (!s.kan_valja) {
      mitt = `<button class="primary stor-las" id="skriv-klar">✅ Jag har gjort läxboken</button>
        <p class="muted small center">Klar senast ${esc(f.text)} = +25 ⭐ när mamma eller pappa har godkänt.</p>`;
    }
    return `
      <div class="forhor-kort ${!u.klart && f.dagar >= 0 && f.dagar <= 1 ? "snart" : ""}">✍️ Läxboken i ${esc(u.amne_namn)}${bok ? ` · ${esc(bok.namn)}` : ""}<br>
        <b>${esc(u.kapitel || u.namn)}</b> ${this._sidText(u)} · lämnas in <b>${esc(f.text)}</b> · ${f.kvar}</div>
      ${mitt}
      ${u.sidor.length ? `<button class="ghost" id="u-las" data-nyckel="${esc(u.sidor[0].nyckel)}" style="width:100%;margin:6px 0">📘 Visa sidan i läxboken</button>` : ""}
      ${this._kopplad(u)}
      ${s.kan_valja && !u.klart && !u.vantar ? `<button class="row foralder-knapp" id="u-manuell"><span>✅ <b>Gjord i boken</b><br><span class="muted small">Registrera att ${esc(s.namn)} har gjort den</span></span><span>›</span></button>` : ""}
      ${s.kan_valja || u.av_id === s.user_id ? `<div class="actions"><button class="ghost danger" id="u-ta-bort">Ta bort</button></div>` : ""}`;
  }

  _veckobrevView() {
    const s = this._s;
    const v = this._view;
    const amnen = s.data.amnen || [];
    const opt = (lista, val) => lista.map(([k, t]) => `<option value="${esc(k)}" ${String(val ?? "") === String(k) ? "selected" : ""}>${esc(t)}</option>`).join("");
    const ladda = this._fotoVal("vb-foto", v.f ? "Fota ett nytt brev" : "Fota veckobrevet", "Är brevet flera bilder eller skärmdumpar? Välj alla på en gång, eller lägg till en i taget, och tryck sedan Läs brevet.", "Läs brevet");
    if (!v.f) {
      return `${ladda}<p class="muted small">AI:n läser brevet och föreslår veckans läxor åt ${esc(s.namn)}: högläsning varje dag, läxboken och veckans ord. Du ser förslaget och kan ändra innan något sparas.</p>`;
    }
    const f = v.f;
    const bokVal = (x, del) => {
      const a = amnen.find((y) => y.id === x.amne);
      const kap = f.kapitel[x.bok] || [];
      return `
        <label>Ämne <select data-vb="${del}" data-f="amne">${opt([["", "Välj…"], ...amnen.map((y) => [y.id, y.namn])], x.amne)}</select></label>
        <label>Bok <select data-vb="${del}" data-f="bok">${opt([["", "Ingen"], ...(a?.bocker || []).map((b) => [b.id, b.namn])], x.bok)}</select></label>
        ${kap.length ? `<label>Kapitel <select data-vb-kap="${del}">${opt([["", "Välj…"], ...kap.map((k, i) => [i, `${k.nr ? k.nr + ". " : ""}${k.namn} (s. ${k.fran}${k.till !== k.fran ? "–" + k.till : ""})`])], kap.findIndex((k) => k.namn === x.kapitel && k.fran === Number(x.fran)))}</select></label>` : ""}
        <div class="two">
          <label>Från sida <input data-vb="${del}" data-f="fran" type="number" inputmode="numeric" value="${esc(x.fran ?? "")}"></label>
          <label>Till sida <input data-vb="${del}" data-f="till" type="number" inputmode="numeric" value="${esc(x.till ?? "")}"></label>
        </div>`;
    };
    const avbock = (del, text) => `<label class="kap-rad vb-med"><input type="checkbox" data-vb-med="${del}" ${v.med[del] ? "checked" : ""}> <b>${text}</b></label>`;
    let html = ladda;
    if (f.regler?.length || f.note) {
      html += `<div class="forhor-kort small"><b>Det här står i brevet:</b><ul style="margin:4px 0 0;padding-left:18px">${(f.regler || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>${f.note ? `<div class="muted">${esc(f.note)}</div>` : ""}</div>`;
    }
    if (f.las) {
      const x = f.las;
      const vecka = [0, 1, 2, 3, 4].map((i) => plusDagar(f.mandag, i));
      html += `<h3>${avbock("las", "🗣️ Läsläxa")}</h3>${v.med.las ? `<div class="form">
        <label>Namn <input data-vb="las" data-f="namn" value="${esc(x.namn)}" maxlength="40"></label>
        ${bokVal(x, "las")}
        <label class="kap-rad"><input type="checkbox" data-vb-hogl ${x.hogl ? "checked" : ""}> Högläsning (en förälder godkänner varje dag)</label>
        <div class="small muted">Läsdagar:</div>
        <div class="kap-val">${vecka.map((d) => `<label class="kap-rad"><input type="checkbox" data-vb-dag="${d}" ${x.dagar.includes(d) ? "checked" : ""}> ${esc(veckodag(d))} <span class="muted small">${esc(forhorInfo(d).text)}</span></label>`).join("")}</div>
      </div>` : ""}`;
    }
    if (f.skriv) {
      const x = f.skriv;
      html += `<h3>${avbock("skriv", "✍️ Läxboken")}</h3>${v.med.skriv ? `<div class="form">
        <label>Namn <input data-vb="skriv" data-f="namn" value="${esc(x.namn)}" maxlength="40"></label>
        ${bokVal(x, "skriv")}
        <label>Lämnas in <input data-vb="skriv" data-f="datum" type="date" value="${esc(x.datum || "")}"></label>
        ${f.las && v.med.las ? `<div class="small muted">Kopplas till läsläxan, samma kapitel.</div>` : ""}
      </div>` : ""}`;
    }
    if (f.ord) {
      const x = f.ord;
      const a = amnen.find((y) => y.id === x.amne);
      html += `<h3>${avbock("ord", "📝 Veckans ord")}</h3>${v.med.ord ? `<div class="form">
        <label>Ämne <select data-vb="ord" data-f="amne">${opt([["", "Välj…"], ...amnen.map((y) => [y.id, y.namn])], x.amne)}</select></label>
        <label>Lista <select data-vb="ord" data-f="glosor">${opt([["", "＋ Ny lista"], ...(a?.glosor || []).map((g) => [g.id, g.namn])], x.glosor || "")}</select></label>
        ${x.glosor ? "" : `<label>Namn <input data-vb="ord" data-f="namn" value="${esc(x.namn)}" maxlength="40"></label>`}
        ${x.glosor && x.befintliga?.length ? `<div class="small muted">Listan har nu: ${esc(x.befintliga.join(", "))}. Den ersätts med orden nedan.</div>` : ""}
        <label>Ord (ett per rad) <textarea data-vb="ord" data-f="ordtext" rows="6">${esc(x.ord.join("\n"))}</textarea></label>
        <label>Diktamen <input data-vb="ord" data-f="forhor" type="date" value="${esc(x.forhor || "")}"></label>
        <div class="small muted">Övar ${esc(s.namn)} på orden varje dag före diktamen blir det meriter för varje övning plus bonus för att vara i god tid.</div>
      </div>` : ""}`;
    }
    const amnOpt = (val, nytt) => opt([...(nytt ? [] : [["", "Välj ämne…"]]), ...amnen.map((y) => [y.id, y.namn])], val);
    if (f.prov?.length) {
      html += `<h3>📝 Prov</h3>${f.prov.map((x, i) => `<div class="form vb-rad ${x.med === false ? "av" : ""}">
        <label class="kap-rad"><input type="checkbox" data-vbp-med="${i}" ${x.med === false ? "" : "checked"}> <b>Lägg in provet</b> <span class="small muted">(blir en provboss 📝)</span></label>
        <label>Namn <input data-vbp="${i}" data-f="namn" value="${esc(x.namn)}" maxlength="40"></label>
        <div class="two"><label>Ämne <select data-vbp="${i}" data-f="amne">${!x.amne && x.amne_namn ? `<option value="" selected>➕ Nytt ämne: ${esc(x.amne_namn)}</option>` : ""}${amnOpt(x.amne, !x.amne && x.amne_namn)}</select></label>
          <label>Datum <input data-vbp="${i}" data-f="datum" type="date" value="${esc(x.datum)}"></label></div>
        <label>Vad provet handlar om <input data-vbp="${i}" data-f="omfattning" value="${esc(x.omfattning || "")}" maxlength="200"></label></div>`).join("")}`;
    }
    if (f.info?.length) {
      html += `<h3>📌 Händelser och kom ihåg</h3><div class="small muted">Visas på förstasidan. Med datum får ${esc(s.namn)} och ni föräldrar en påminnelse kvällen innan.</div>
        ${f.info.map((x, i) => `<div class="form vb-rad ${x.med === false ? "av" : ""}"><label class="kap-rad"><input type="checkbox" data-vbi-med="${i}" ${x.med === false ? "" : "checked"}> <b>Spara</b></label>
          <textarea data-vbi="${i}" data-f="text" rows="2" maxlength="200" placeholder="t.ex. Utflykt – ta med matsäck">${esc(x.text)}</textarea>
          <div class="two"><label>Datum (valfritt) <input data-vbi="${i}" data-f="datum" type="date" value="${esc(x.datum || "")}"></label><label>Tid <input data-vbi="${i}" data-f="tid" type="time" value="${esc(x.tid || "")}"></label></div></div>`).join("")}`;
    }
    html += `<button class="ghost" id="vb-info-ny">＋ Lägg till något att komma ihåg</button>`;
    const nagot = f.las || f.skriv || f.ord || f.prov?.length || f.info?.length;
    if (!f.las && !f.skriv && !f.ord) html += `<p class="muted">AI:n hittade inga läxor i brevet.${f.prov?.length || f.info?.length ? " Men prov och annat viktigt sparas ändå." : ""}</p>`;
    if (nagot) html += `<div class="actions"><button class="primary" id="vb-spara">Spara</button></div>`;
    return html;
  }


  // Välj en eller flera bilder (t.ex. två skärmdumpar av samma brev) innan AI:n läser dem tillsammans.
  _fotoVal(id, titel, nyText, lasText) {
    const filer = this._fotoFiler?.[id] || [];
    const val = `<label class="${filer.length ? "ghost" : "primary"} upload">📷 ${filer.length ? "＋ Lägg till en bild till" : titel}<input type="file" id="${id}" accept="image/*,application/pdf" multiple hidden></label>`;
    if (!filer.length) return `${val}<div class="small muted">${nyText}</div>`;
    return `<div class="foto-val"><b>${filer.length} ${filer.length === 1 ? "bild vald" : "bilder valda"}</b>
      <ul class="lista">${filer.map((f, i) => `<li>${f.type === "application/pdf" ? "📄" : "🖼️"} ${esc(f.name || `Bild ${i + 1}`)} <button class="mini" data-foto-bort="${id}:${i}">✕</button></li>`).join("")}</ul>
      <div class="actions">${val}<button class="primary" data-foto-las="${id}" ${this._busy ? "disabled" : ""}>🤖 ${lasText}</button></div></div>`;
  }

  async _veckobrevLas(filer) {
    this._busy = true;
    this._msg = { type: "info", text: "AI:n läser veckobrevet… (tar några sekunder)" };
    this._render();
    try {
      const fd = new FormData();
      fd.append("barn", this._s.barn);
      (Array.isArray(filer) ? filer : [filer]).forEach((f) => fd.append("file", f, f.name));
      const res = await this._hass.fetchWithAuth("/api/skolan/veckobrev", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      if (body.ord) body.ord.ord = body.ord.ord || [];
      this._view.f = body;
      this._view.med = { las: !!body.las, skriv: !!body.skriv, ord: !!body.ord };
      this._msg = { type: "ok", text: "Kolla förslaget och tryck Spara." };
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    }
    this._busy = false;
    this._render();
  }

  async _uppdragAct(op, args = {}) {
    this._busy = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/uppdrag", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, op, ...args }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._nyData(body.data);
      this._msg = null;
      return true;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  // Födelsedagen: en present att öppna (⭐ och Födelsedagshatten).
  _fodelsedagKort() {
    const f = this._s.fodelsedag;
    if (!f || this._s.kan_valja) return "";
    return `<div class="card fodelsedag-kort"><div class="fd-tarta">🎂</div>
      <div class="fd-text">Grattis på födelsedagen, ${esc(this._s.namn)}!<br><small>Du fyller ${f.alder} år idag! 🎉</small></div>
      ${f.hamtad ? `<div class="small">🥳 Du har fått Födelsedagshatten och +${f.p} ⭐. Ha en fantastisk dag!</div>` : `<button class="primary fd-knapp" id="fd-oppna">🎁 Öppna din present</button>`}</div>`;
  }

  // Julkalendern 1–24 december.
  _julKort() {
    const j = this._s.jul;
    if (!j || this._s.kan_valja) return "";
    const barn = !this._s.kan_valja;
    return `<div class="card jul-kort"><div class="jul-rubrik">🎄 Julkalendern <span class="small">${j.dag <= 24 ? `${24 - j.dag} dagar kvar till julafton` : "God jul! 🎅"}</span></div>
      <div class="jul-luckor">${j.luckor.map((l) => l.oppnad
        ? `<div class="lucka oppnad" title="${esc((l.innehall || []).join(", "))}"><span>${l.dag}</span>${(l.innehall || [])[0]?.split(" ")[0] || "🎁"}</div>`
        : l.kan && barn ? `<button class="lucka kan ${l.dag === 24 ? "julafton" : ""}" data-lucka="${l.dag}">${l.dag}</button>`
        : `<div class="lucka last ${l.dag === 24 ? "julafton" : ""}">${l.dag}</div>`).join("")}</div></div>`;
  }

  // Nya samlarkort: vänds upp när barnet trycker.
  _kortRuta(k, dold = false) {
    return `<div class="samlarkort ${k.sallsynt} ${dold ? "dold" : ""}" style="--farg:${(this._s.kort?.album || []).find((a) => a.id === k.varld)?.farg || "#5c6bc0"}">
      <div class="sk-ikon">${dold ? "❓" : k.ikon}</div><div class="sk-namn">${dold ? "???" : esc(k.namn)}</div>
      ${dold ? "" : `<div class="sk-sallsynt">${{ vanlig: "Vanlig", ovanlig: "✨ Ovanlig", legendarisk: "🌟 Legendarisk" }[k.sallsynt]}</div>`}
      ${!dold && k.antal > 1 ? `<div class="sk-antal">×${k.antal}</div>` : ""}</div>`;
  }

  _nyaKort() {
    const nya = this._s.kort?.nya || [];
    if (this._s.kan_valja || !nya.length) return "";
    const vand = this._kortVanda;
    return `<div class="card kort-nya"><b>🃏 ${nya.length === 1 ? "Ett nytt kort" : `${nya.length} nya kort`}!</b>
      <div class="kort-rad">${nya.map((k, i) => `<div class="kort-vand ${vand ? "vand" : ""}" style="animation-delay:${i * 0.15}s">${this._kortRuta(k, !vand)}${vand ? `<div class="small center">${k.ny ? "🆕 Nytt!" : "Dubblett +3 ⭐"}</div>` : ""}</div>`).join("")}</div>
      ${vand ? `<div class="actions"><button class="primary" id="kort-album">📖 Till albumet</button><button class="ghost" id="kort-ok">OK</button></div>`
        : `<button class="primary" id="kort-vand">✨ Vänd korten</button>`}</div>`;
  }

  // Fångstkistor: belöning direkt när barnet lägger in läxor och prov.
  _kistKort() {
    const ks = this._s.kistor?.kistor || [];
    const senast = this._kistaVisa;
    if (this._s.kan_valja || (!ks.length && !senast)) return "";
    return `<div class="card kista-kort">
      <div class="djur-rubrik">🎁 ${ks.length ? (ks.length === 1 ? "Du har en kista!" : `Du har ${ks.length} kistor!`) : "Kistan är öppnad"}</div>
      ${senast ? `<div class="kista-innehall">${senast.saker.map((x, i) => `<div class="kista-sak" style="animation-delay:${i * 0.25}s"><span>${x.ikon}</span><b>${esc(x.text)}</b></div>`).join("")}</div>` : ""}
      ${ks.length ? `<div class="kista-rad">${ks.map((x) => `<button class="kista ${x.typ}" data-kista="${x.id}" ${this._busy ? "disabled" : ""}>
          <span class="kista-ikon">${x.ikon}</span><span class="small"><b>${esc(x.namn)}</b><br>${esc(x.orsak)}</span></button>`).join("")}</div>
        <div class="small muted">Tryck för att öppna. Du får en kista varje gång du lägger in en läxa eller ett prov, och ett prov inlagt i god tid ger en finare kista.</div>`
        : `<button class="ghost" id="kista-ok">OK</button>`}
    </div>`;
  }

  // Husdjuret frågar efter skolan om det blev någon läxa.
  _laxfragaKort() {
    const f = this._s.laxfraga, d = this._s.meriter?.djur;
    if (!f || this._s.kan_valja) return "";
    const amnen = f.amnen.length ? ` Du hade ${f.amnen.slice(0, 5).map(esc).join(", ")} idag.` : "";
    const schema = f.schema.length ? ` ${esc(f.schema[0])} brukar komma idag.` : "";
    return `<div class="card laxfraga-kort">
      ${d ? `<div class="laxfraga-djur">${ritaDjur(d.art, "glad", Math.max(1, d.steg), {})}</div>` : ""}
      <div><div class="pratbubbla"><b>${d ? esc(d.namn) : "Husdjuret"}:</b> Hej! Fick du någon läxa eller något prov idag?${amnen}${schema}</div>
        <div class="actions"><button class="primary" id="laxfraga-ja">📥 Ja, lägg in</button><button class="ghost" id="laxfraga-nej">🙅 Nej, ingen idag (+${f.p} ⭐)</button></div></div>
    </div>`;
  }

  // Husdjuret frågar efter studiematerial till ett ämne som saknar det.
  _materialKort() {
    const f = this._s.material, d = this._s.meriter?.djur;
    if (!f || this._s.kan_valja || this._s.laxfraga) return "";
    return `<div class="card laxfraga-kort">
      ${d ? `<div class="laxfraga-djur">${ritaDjur(d.art, "nojd", Math.max(1, d.steg), {})}</div>` : ""}
      <div><div class="pratbubbla"><b>${d ? esc(d.namn) : "Husdjuret"}:</b> ${f.idag ? `Du hade ${esc(f.namn)} idag! ` : ""}Vi har inget att plugga med i <b>${esc(f.namn)}</b> än.
        Fota en sida ur boken, lägg in glosor eller skriv anteckningar, så kan vi öva tillsammans! Du får en 💎 silverkista.${f.fler ? ` <span class="small muted">(${f.fler} ämne${f.fler === 1 ? "" : "n"} till saknar material)</span>` : ""}</div>
        <div class="actions"><button class="primary" id="material-ja" data-amne="${f.amne}">📷 Lägg in material</button><button class="ghost" id="material-sen" data-amne="${f.amne}">Inte nu</button></div></div>
    </div>`;
  }

  // Händelser och kom ihåg från veckobrevet.
  _skolinfoKort() {
    const lista = this._s.skolinfo || [];
    if (!lista.length) return "";
    const dagNamn = (x) => `${veckodag(x.datum)} ${Number(x.datum.slice(8))}/${Number(x.datum.slice(5, 7))}`;
    const nar = (x) => x.dagar == null ? "" : x.dagar === 0 ? `Idag, ${dagNamn(x)}` : x.dagar === 1 ? `Imorgon, ${dagNamn(x)}` : dagNamn(x).replace(/^./, (c) => c.toUpperCase());
    return `<div class="card skolinfo-kort"><div class="djur-rubrik">📌 Från skolan</div>
      <ul class="lista">${lista.slice(0, 8).map((x) => `<li class="${x.dagar != null && x.dagar <= 1 ? "snart" : ""}">${x.ledig ? "🏖️ " : ""}${x.dagar != null ? `<b>${nar(x)}${x.tid ? " kl. " + esc(x.tid) : ""}:</b> ` : "Kom ihåg: "}${esc(x.text)}
        ${this._s.kan_valja ? `<button class="mini" data-skolinfo-bort="${x.id}" title="Ta bort">✕</button>` : ""}</li>`).join("")}</ul></div>`;
  }

  // Skolkalendrar: föräldrar kopplar in kalendrar på olika sätt, och väljer vilka barn de gäller.
  _kalenderView() {
    const k = this._kal, v = this._view, s = this._s;
    if (!k) return `<p class="muted">Hämtar…</p>`;
    const dag = (iso) => `${veckodag(iso)} ${Number(iso.slice(8))}/${Number(iso.slice(5, 7))}`;
    const TYPER = {
      ics: { ikon: "🔗", namn: "Prenumerationslänk (iCal/webcal)", besk: "Bäst om skolans plattform kan dela kalendern. Uppdateras av sig själv var tredje timme." },
      ha: { ikon: "🏠", namn: "Kalender i Home Assistant", besk: "En kalender ni redan har kopplat in i Home Assistant, t.ex. Google, Outlook eller CalDAV. Uppdateras var tredje timme." },
      webb: { ikon: "🌐", namn: "Skolans webbsida", besk: "En sida på skolans hemsida med kalender eller läsårstider. AI:n läser sidan en gång per dygn." },
      fil: { ikon: "📄", namn: "Kalenderfil (.ics)", besk: "En fil som skolan har skickat. Läses in en gång." },
      foto: { ikon: "📷", namn: "Foto eller PDF", besk: "Läsårsplanering, terminsplan eller lovlista på papper. AI:n läser av datumen en gång." },
    };
    const barnVal = (valda, attr) => k.barn.map((b) => `<label class="kap-rad"><input type="checkbox" ${attr}="${b.id}" ${valda.includes(b.id) ? "checked" : ""}> ${esc(b.namn)}</label>`).join("");
    if (v.ny) {
      const t = v.ny;
      if (t === "val") return `<p class="small">Hur delar skolan sin kalender? Välj det som passar. Ni kan lägga till flera.</p>
        <div class="list">${Object.entries(TYPER).map(([id, x]) => `<button class="row" data-kal-typ="${id}"><span>${x.ikon} <b>${x.namn}</b><br><span class="small muted">${x.besk}</span></span><span>›</span></button>`).join("")}</div>`;
      const x = TYPER[t];
      const guide = t === "ics" ? `<details class="kal-guide"><summary>Var hittar jag länken?</summary><ul class="small">
          <li><b>InfoMentor:</b> öppna Kalender och välj Prenumerera. Länken börjar ofta med webcals://.</li>
          <li><b>Vklass, SchoolSoft, Unikum, IST/Edlevo, Skolplattformen:</b> leta i kalendern efter Prenumerera, Exportera, Dela eller iCal.</li>
          <li><b>Google Kalender</b> (om skolan delar en Google-kalender): Inställningar för kalendern → Hemlig adress i iCal-format.</li>
          <li><b>Outlook / Microsoft 365:</b> Inställningar → Kalender → Delade kalendrar → Publicera en kalender → kopiera ICS-länken.</li>
          <li><b>iCloud:</b> dela kalendern som Offentlig kalender och kopiera länken.</li>
          <li>Har ni bara en "Lägg till i kalender"-knapp på telefonen? Håll inne den och välj Kopiera länk.</li></ul>
          <p class="small muted">Länken är hemlig: den visas bara för föräldrar, aldrig för barnen.</p></details>` : "";
      const falt = t === "ics" ? `<label>Länk <input id="kn-url" placeholder="webcal://… eller https://…" autocomplete="off"></label>`
        : t === "webb" ? `<label>Adress till sidan <input id="kn-url" placeholder="https://skolan.se/kalender" autocomplete="off"></label>`
        : t === "ha" ? (k.ha.length ? `<label>Kalender <select id="kn-entity">${k.ha.map((c) => `<option value="${esc(c.id)}">${esc(c.namn)}</option>`).join("")}</select></label>`
          : `<p class="muted">Det finns inga kalendrar i Home Assistant än. Lägg till t.ex. Google Kalender eller CalDAV under Inställningar → Enheter och tjänster, och kom sedan tillbaka hit.</p>`)
        : `<label class="primary upload">${t === "fil" ? "📄 Välj .ics-fil" : "📷 Välj foton eller PDF"}<input type="file" id="kn-fil" ${t === "fil" ? 'accept=".ics,text/calendar"' : 'accept="image/*,application/pdf" multiple'} hidden></label>
          <div class="small" id="kn-filnamn">${(this._kalFiler || []).map((f) => esc(f.name)).join(", ")}</div>`;
      return `<h3>${x.ikon} ${x.namn}</h3><p class="small muted">${x.besk}</p>${guide}
        <div class="form">${falt}
          <label>Namn <input id="kn-namn" value="${esc(t === "ha" ? "" : "Skolkalender")}" maxlength="40" placeholder="t.ex. Filosofiska skolan"></label>
          <div class="small">Gäller</div><div class="kap-val">${barnVal([s.barn], "data-kn-barn")}</div></div>
        <div class="actions"><button class="primary" id="kn-spara" ${this._busy ? "disabled" : ""}>Spara och hämta</button><button class="ghost" id="kn-avbryt">Avbryt</button></div>`;
    }
    return `<p class="small">Koppla in skolans kalender så kommer lov, utvecklingsdagar, möten och utflykter in av sig själva. De visas på förstasidan, ger påminnelse kvällen innan, och lediga dagar gör att widgeten och husdjuret inte räknar med lektioner. En kalender kan gälla flera barn.</p>
      ${k.kallor.map((x) => `<div class="card kal-kalla"><div class="djur-rubrik">${TYPER[x.typ]?.ikon || "📅"} ${esc(x.namn)} <span class="small muted">${TYPER[x.typ]?.namn || ""}</span></div>
        <div class="small">${x.fel ? `⚠️ ${esc(x.fel)} · ` : ""}${x.antal} händelser${x.hamtad ? ` · hämtad ${esc(x.hamtad.replace("T", " "))}` : ""}${["ics", "ha", "webb"].includes(x.typ) ? " · uppdateras automatiskt" : ""}</div>
        <div class="small" style="margin-top:6px">Gäller:</div><div class="kap-val">${barnVal(x.barn, `data-kal-barn="${x.id}" data-b`)}</div>
        <details><summary class="small">Kommande (${x.kommande.length})</summary><ul class="lista small">${x.kommande.map((h) => `<li>${h.ledig ? "🏖️" : "📅"} <b>${dag(h.start)}${h.slut !== h.start ? ` – ${dag(h.slut)}` : ""}${h.tid ? " kl. " + esc(h.tid) : ""}</b>: ${esc(h.text)}</li>`).join("") || "<li class='muted'>Inga.</li>"}</ul></details>
        <div class="actions">${["ics", "ha", "webb"].includes(x.typ) ? `<button class="mini" data-kal-upd="${x.id}">🔄 Hämta nu</button>` : ""}<button class="mini" data-kal-namn="${x.id}">✏️ Byt namn</button><button class="mini danger" data-kal-bort="${x.id}">🗑️ Ta bort</button></div></div>`).join("")}
      <button class="primary" id="kal-ny">＋ Lägg till kalender</button>
      <p class="small muted">🏖️ = ledig dag (lov, utvecklingsdag). Enskilda händelser kan döljas med ✕ på förstasidans kort "Från skolan".</p>`;
  }

  async _kalHamta(op = null) {
    this._busy = true;
    this._render();
    try {
      const res = op instanceof FormData
        ? await this._hass.fetchWithAuth("/api/skolan/kalendrar", { method: "POST", body: op })
        : await this._hass.fetchWithAuth("/api/skolan/kalendrar", op ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(op) } : {});
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._kal = body;
      return true;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return false;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _veckokollRad() {
    const v = this._s.veckokoll;
    if (!v || this._s.kan_valja) return "";
    if (v.klar) return `<div class="vantar ok">📅 <b>Veckans koll klar!</b> Alla läxor inlagda i tid: +${v.p} ⭐, 🛡️ svitskydd och 👑 guldkista.</div>`;
    if (v.miss) return "";
    return `<div class="vantar">📅 <b>Veckans koll ${v.klara}/${v.av}</b>: lägg in alla veckans läxor i tid så får du +${v.p} ⭐, ett 🛡️ svitskydd och en 👑 guldkista.</div>`;
  }

  // Provbossar: varje prov blir ett monster som blir svagare för varje dag man pluggar.
  _provbossRad(b, knapp) {
    const kvar = b.dagar_kvar;
    const nar = kvar > 1 ? `Provet om ${kvar} dagar` : kvar === 1 ? "Provet är i morgon" : kvar === 0 ? "Provet är idag" : "Provet är gjort";
    return `<li class="provboss ${b.vunnen ? "vunnen" : ""}"><span class="pb-ikon">${b.ikon}</span>
      <span><b>${esc(b.namn)}</b> <span class="small muted">· ${esc(b.prov)}</span><br>
        <span class="small">${nar} · 🎯 svag mot ${TYP_TEXT[b.svag] || b.svag} · 📚 ${b.pluggdagar} pluggdag${b.pluggdagar === 1 ? "" : "ar"}${b.klart ? " · ✅ allt klart" : ""}</span>
        <div class="pb-liv" title="Skada från plugget"><div style="width:${100 - b.skada}%"></div></div>
        <span class="small">${b.vunnen ? "🏆 Besegrad!" : b.skada ? `💥 ${b.skada} % skadad av ditt plugg` : "Oskadd: plugga inför provet så blir den svagare!"}</span>
        ${knapp && !b.vunnen && b.dagar_kvar >= 1 ? `<br><button class="mini" data-plan="${b.id}">📅 Pluggplan</button> <button class="mini" data-hjalp-prov="${b.id}">📚 Plugga med ${esc(this._s.meriter?.djur?.namn || "husdjuret")}</button>` : ""}</span>
      ${knapp && !b.vunnen ? (b.oppen ? `<button class="mini primary" data-provboss="${b.id}" ${this._busy || this._s.arena?.pagar ? "disabled" : ""}>⚔️ Slutstrid</button>`
        : `<span class="small muted center">Öppnar dagen före provet</span>`) : ""}</li>`;
  }

  _provbossKort() {
    if (this._s.kan_valja || !this._s.meriter?.djur) return "";
    const lista = (this._s.provbossar || []).filter((b) => !b.vunnen && (b.dagar_kvar >= 0 || b.oppen));
    if (!lista.length) return "";
    return `<div class="card provboss-kort"><div class="djur-rubrik">📝 Provbossar</div>
      <ul class="lista arena-lista">${lista.map((b) => this._provbossRad(b, true)).join("")}</ul>
      <div class="small muted">Varje dag du pluggar inför provet tar bossen ${15} % skada. Dagen före provet kan du slåss mot den. Vinst: +20 ⭐ och en 🏆 provtrofé.</div></div>`;
  }

  // Lektionsschemat som ett digitalt schema: tidsaxel, dagens kolumn, nu-linje, sök och redigering.
  _lektionView() {
    const v = this._view, s = this._s;
    const ladda = this._fotoVal("ls-foto", s.lektioner?.length || v.f ? "Fota schemat igen" : "Fota schemat", "Är schemat flera bilder eller skärmdumpar? Välj alla, eller lägg till en i taget, och tryck sedan Läs schemat.", "Läs schemat");
    if (v.f) {
      const f = v.f;
      return `<p class="small">Så här läste AI:n schemat. Tryck på en lektion för att rätta den, och tryck sedan Spara. Nya ämnen skapas bara om de är ibockade.</p>
        ${this._schemaVy(f.lektioner)}
        <h3>📚 Ämnen i schemat</h3>
        <div class="list">${f.amnen.map((a, i) => a.amne ? `<div class="row static"><span>✅ <b>${esc(a.namn)}</b></span><span class="small muted">finns redan${a.amne_namn.toLowerCase() !== a.namn.toLowerCase() ? ` som ${esc(a.amne_namn)}` : ""}</span></div>`
          : `<label class="row del-val"><span>＋ <b>${esc(a.namn)}</b><br><span class="small muted">Skapa ämnet</span></span><input type="checkbox" data-ls-skapa="${i}" ${a.skapa !== false ? "checked" : ""}></label>`).join("")}</div>
        <div class="actions"><button class="primary" id="ls-spara" ${this._busy ? "disabled" : ""}>Spara schemat</button>${ladda}</div>`;
    }
    if (!s.kan_valja && !s.lektioner?.length)
      return `<p class="muted">Du har inget schema här än. Be mamma eller pappa fota ditt schema, eller be läraren skicka det. Sen kan du söka i det, se vad som händer idag och skriva ut det.</p>`;
    if (!s.lektioner?.length)
      return `${ladda}<p class="muted small">${s.kan_valja ? `Fota ${esc(s.namn)}s lektionsschema så gör AI:n en digital kopia med lektioner, salar och lärare. Ämnen som saknas kan skapas direkt. Läraren kan också skicka schemat via inkorgen.` : "Fota ditt lektionsschema så gör AI:n en digital kopia med lektioner, salar och lärare som du kan söka i. Efter skolan frågar ditt husdjur om du fick någon läxa på lektionerna."}</p>
        <button class="ghost" id="ls-tomt">✏️ Skriv in schemat själv</button>`;
    return `${this._schemaVy(s.lektioner)}<div class="actions"><button class="primary" id="ls-utskrift">🖨️ Skriv ut / öppna som sida</button>${s.kan_valja ? ladda : ""}</div>
      ${s.kan_valja ? "" : `<p class="small muted">Stämmer något inte? Be mamma eller pappa ändra schemat.</p>`}`;
  }

  _schemaLista() {
    return this._view.f ? this._view.f.lektioner : (this._view.utkast || this._s.lektioner || []);
  }

  _schemaVy(lekt) {
    const v = this._view, s = this._s;
    const DAGAR = ["Mån", "Tis", "Ons", "Tor", "Fre"];
    const min = (t) => { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; };
    const farg = (x) => (s.data.amnen || []).find((a) => a.id === x.amne || a.namn.toLowerCase() === (x.namn || "").toLowerCase())?.farg
      || ["#4f8ef7", "#f7a14f", "#4fc98a", "#e05f8a", "#9b6cf0", "#2bb5c4", "#d4b02a", "#e0603a"][[...(x.namn || "")].reduce((n, c) => n + c.charCodeAt(0), 0) % 8];
    const tider = lekt.flatMap((x) => [min(x.start), min(x.slut) ?? (min(x.start) != null ? min(x.start) + 40 : null)]).filter((x) => x != null);
    const fran = tider.length ? Math.floor(Math.min(...tider) / 60) * 60 : 480, till = tider.length ? Math.ceil(Math.max(...tider) / 60) * 60 : 900;
    const PX = 1.15, H = (till - fran) * PX;
    const nu = new Date(), idag = (nu.getDay() + 6) % 7, klocka = nu.getHours() * 60 + nu.getMinutes();
    const sokText = (x) => [x.namn, x.sal, x.larare, x.info, DAGAR[x.dag]].filter(Boolean).join(" ").toLowerCase();
    // Lektioner som krockar (delad tid) delar på bredden och ligger bredvid varandra.
    const plats = {};
    for (let d = 0; d < 5; d++) {
      const dl = lekt.map((x, i) => [x, i]).filter(([x]) => x.dag === d && min(x.start) != null).sort((a, b) => min(a[0].start) - min(b[0].start));
      let grupp = [], slut = -1;
      const stang = () => {
        const cols = [], ejKol = [];
        grupp.forEach(([x, i]) => { const st = min(x.start); let k = cols.findIndex((c) => c <= st); if (k < 0) { cols.push(0); ejKol.push(true); k = cols.length - 1; } cols[k] = min(x.slut) ?? st + 40; if (!x.ej) ejKol[k] = false; plats[i] = [k, 0]; });
        // andra gruppens lektioner (ej) blir smala så att barnets egen lektion får plats
        const vikt = ejKol.map((e) => (e && ejKol.some((y) => !y) ? 0.3 : 1)), sum = vikt.reduce((a, b) => a + b, 0);
        const vanster = vikt.map((_, k) => vikt.slice(0, k).reduce((a, b) => a + b, 0) / sum * 100);
        grupp.forEach(([, i]) => { const k = plats[i][0]; plats[i] = [k, cols.length, vanster[k], vikt[k] / sum * 100]; });
      };
      dl.forEach((p) => { const st = min(p[0].start), sl = min(p[0].slut) ?? st + 40; if (grupp.length && st >= slut) { stang(); grupp = []; slut = -1; } grupp.push(p); slut = Math.max(slut, sl); });
      if (grupp.length) stang();
    }
    const block = (x, i) => {
      const st = min(x.start), sl = min(x.slut) ?? (st != null ? st + 40 : null);
      const [, n, vp = 0, bp = 100] = plats[i] || [0, 1];
      const pagar = !x.ej && x.dag === idag && st != null && st <= klocka && klocka < sl;
      return `<button class="ls-lektion ${pagar ? "pagar" : ""} ${n > 1 ? "delad" : ""} ${x.ej ? "ej" : ""}" data-ls-i="${i}" data-sok="${esc(sokText(x))}" style="--c:${farg(x)};top:${(st - fran) * PX}px;height:${Math.max(18, (sl - st) * PX - 2)}px;left:calc(${vp}% + 1px);width:calc(${bp}% - 2px)">
        <b>${esc(x.namn)}</b>${(sl - st) * PX > 30 ? `<span>${esc(x.start)}</span>` : ""}${x.sal && (sl - st) * PX > 44 ? `<span>📍 ${esc(x.sal)}</span>` : ""}${x.info && (sl - st) * PX > 58 ? `<span>ℹ️ ${esc(x.info)}</span>` : ""}</button>`;
    };
    const utanTid = lekt.map((x, i) => [x, i]).filter(([x]) => min(x.start) == null);
    const idagLista = lekt.map((x, i) => [x, i]).filter(([x]) => x.dag === idag && !x.ej && min(x.start) != null).sort((a, b) => min(a[0].start) - min(b[0].start));
    const red = s.kan_valja ? v.red : null; // bara föräldrar ändrar schemat
    const r = red === "ny" ? { dag: idag < 5 ? idag : 0, start: "", slut: "", namn: "", sal: "", larare: "", info: "" } : red != null ? lekt[red] : null;
    const timmar = [];
    for (let t = fran; t <= till; t += 60) timmar.push(t);
    return `<div class="ls-sok"><input id="ls-sok" type="search" placeholder="🔍 Sök ämne, sal, lärare eller dag" value="${esc(v.sok || "")}" autocomplete="off"></div>
      <div id="ls-traffar" class="list"></div>
      ${idag < 5 && idagLista.length && !v.f ? `<div class="card ls-idag"><b>📅 Idag, ${VECKODAG[idag]}</b>
        ${idagLista.map(([x, i]) => { const st = min(x.start), sl = min(x.slut) ?? st + 40; const tag = klocka >= sl ? "klar" : klocka >= st ? "nu" : "";
          return `<div class="ls-idag-rad ${tag}" data-ls-i="${i}"><span class="ls-prick" style="background:${farg(x)}"></span><span>${esc(x.start)}${x.slut ? "–" + esc(x.slut) : ""}</span><b>${esc(x.namn)}</b><span class="small muted">${[x.sal && "📍 " + x.sal, x.larare && "👤 " + x.larare].filter(Boolean).map(esc).join(" · ")}</span>${tag === "nu" ? `<span class="badge">Nu</span>` : ""}</div>`; }).join("")}</div>` : ""}
      ${s.kan_valja && lekt.some((x, i) => !x.ej && min(x.start) != null && lekt.some((y, j) => j !== i && !y.ej && y.dag === x.dag && min(y.start) != null && min(y.start) < (min(x.slut) ?? min(x.start) + 40) && (min(y.slut) ?? min(y.start) + 40) > min(x.start)))
        ? `<div class="vantar">🔀 Vissa lektioner har delad tid. Tryck på den som gäller ${esc(s.namn)} och välj <b>✔️ Den här gäller ${esc(s.namn)}</b>.</div>` : ""}
      ${tider.length ? `<div class="ls-schema">
        <div class="ls-tider" style="height:${H}px">${timmar.map((t) => `<span style="top:${(t - fran) * PX}px">${String(t / 60).padStart(2, "0")}</span>`).join("")}</div>
        ${DAGAR.map((dn, d) => `<div class="ls-dag ${d === idag ? "idag" : ""}"><div class="ls-dag-rubrik">${dn}</div>
          <div class="ls-kolumn" style="height:${H}px">${timmar.map((t) => `<i class="ls-linje" style="top:${(t - fran) * PX}px"></i>`).join("")}
            ${lekt.map((x, i) => [x, i]).filter(([x]) => x.dag === d && min(x.start) != null).map(([x, i]) => block(x, i)).join("")}
            ${d === idag && klocka > fran && klocka < till ? `<i class="ls-nu" style="top:${(klocka - fran) * PX}px"></i>` : ""}</div></div>`).join("")}
      </div>` : ""}
      ${utanTid.length ? `<h3>Utan tid</h3><div class="list">${utanTid.map(([x, i]) => `<button class="row" data-ls-i="${i}" data-sok="${esc(sokText(x))}"><span><b>${esc(x.namn)}</b> · ${DAGAR[x.dag]}</span><span class="small muted">${esc(x.sal || "")}</span></button>`).join("")}</div>` : ""}
      ${r ? `<div class="card form ls-red" id="ls-red"><b>${red === "ny" ? "＋ Ny lektion" : "✏️ Ändra lektionen"}</b>
        <label>Ämne <input id="lr-namn" list="lr-amnen" value="${esc(r.namn)}" maxlength="40"></label>
        <datalist id="lr-amnen">${(s.data.amnen || []).map((a) => `<option value="${esc(a.namn)}">`).join("")}</datalist>
        <div class="two"><label>Dag <select id="lr-dag">${DAGAR.map((dn, d) => `<option value="${d}" ${r.dag === d ? "selected" : ""}>${VECKODAG[d]}</option>`).join("")}</select></label>
          <label>Sal <input id="lr-sal" value="${esc(r.sal || "")}" maxlength="20"></label></div>
        <div class="two"><label>Börjar <input id="lr-start" type="time" value="${esc(r.start || "")}"></label><label>Slutar <input id="lr-slut" type="time" value="${esc(r.slut || "")}"></label></div>
        <label>Lärare <input id="lr-larare" value="${esc(r.larare || "")}" maxlength="40"></label>
        ${(() => { if (red === "ny" || !r) return "";
          const st = min(r.start), sl = min(r.slut) ?? st + 40;
          const krock = lekt.filter((y, i) => i !== red && y.dag === r.dag && min(y.start) != null && min(y.start) < sl && (min(y.slut) ?? min(y.start) + 40) > st);
          if (!krock.length || st == null) return "";
          const vald = !r.ej && krock.every((y) => y.ej);
          return `<div class="ls-delad-val">${vald ? `✔️ Det här är ${esc(s.namn)}s lektion.` : r.ej ? "⚪ Den andra gruppens lektion." : `Delad tid med ${krock.map((y) => esc(y.namn)).join(", ")}. Vilken gäller ${esc(s.namn)}?`}
            ${vald ? "" : `<button class="mini primary" id="lr-min">✔️ Den här gäller ${esc(s.namn)}</button>`}</div>`; })()}
        <label>Info <input id="lr-info" value="${esc(r.info || "")}" maxlength="80" placeholder="t.ex. ta med ombyte"></label>
        <div class="small muted">Delad tid? Lägg till en lektion till med samma tid, så hamnar de bredvid varandra.</div>
        <div class="actions"><button class="primary" id="lr-ok">${v.f ? "OK" : "Spara"}</button>${red !== "ny" ? `<button class="danger" id="lr-bort">🗑️ Ta bort</button>` : ""}<button class="ghost" id="lr-avbryt">Avbryt</button></div></div>`
        : s.kan_valja ? `<button class="ghost" id="ls-ny">＋ Lägg till lektion</button>` : ""}`;
  }

  // Sök utan att rita om sidan (så att tangentbordet inte stängs).
  _schemaSok(q) {
    const r = this.shadowRoot;
    this._view.sok = q;
    const t = q.trim().toLowerCase();
    const lekt = this._schemaLista();
    r.querySelectorAll(".ls-lektion[data-sok], .row[data-sok]").forEach((el) => el.classList.toggle("dim", !!t && !el.dataset.sok.includes(t)));
    const ut = r.querySelector("#ls-traffar");
    if (!ut) return;
    const DAGAR = ["Mån", "Tis", "Ons", "Tor", "Fre"];
    const traff = t ? lekt.map((x, i) => [x, i]).filter(([x]) => [x.namn, x.sal, x.larare, x.info, DAGAR[x.dag], VECKODAG[x.dag]].filter(Boolean).join(" ").toLowerCase().includes(t))
      .sort((a, b) => a[0].dag - b[0].dag || (a[0].start || "").localeCompare(b[0].start || "")) : [];
    ut.innerHTML = !t ? "" : traff.length ? traff.map(([x, i]) => `<button class="row" data-ls-traff="${i}"><span><b>${esc(x.namn)}</b><br><span class="small muted">${[x.sal && "📍 " + x.sal, x.larare && "👤 " + x.larare, x.info && "ℹ️ " + x.info].filter(Boolean).map(esc).join(" · ")}</span></span>
        <span class="small">${VECKODAG[x.dag]} ${esc(x.start || "")}${x.slut ? "–" + esc(x.slut) : ""}</span></button>`).join("")
      : `<div class="row static muted small">Inget hittades.</div>`;
    if (this._s.kan_valja) ut.querySelectorAll("[data-ls-traff]").forEach((b) => b.addEventListener("click", () => { this._view.red = Number(b.dataset.lsTraff); this._render(); }));
  }

  async _schemaSpara(lista) {
    if (this._view.f) { this._view.f.lektioner = lista; this._view.red = null; return this._render(); }
    if (!(await this._act("lektioner_spara", { lektioner: lista, skapa: [] }))) return;
    this._view.red = null;
    await this._load(this._s.barn);
    this._render();
  }

  async _lektionLas(filer) {
    this._busy = true;
    this._msg = { type: "info", text: "AI:n läser schemat… (tar några sekunder)" };
    this._render();
    try {
      const fd = new FormData();
      fd.append("barn", this._s.barn);
      (Array.isArray(filer) ? filer : [filer]).forEach((f) => fd.append("file", f, f.name));
      const res = await this._hass.fetchWithAuth("/api/skolan/lektionsschema", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._view.f = body;
      this._msg = { type: "ok", text: "Kolla förslaget och tryck Spara." };
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
    }
    this._busy = false;
    this._render();
  }

  _albumView() {
    const k = this._s.kort;
    if (!k) return `<p class="muted">Hämtar…</p>`;
    return `<p class="small muted">Du får ett kort när du tjänar ${k.granser.join(", ")} ⭐ samma dag, ibland när du besegrar ett monster på kartan, och bossens kort när du besegrar den. Saknar du kort? Ta 🔁 revansch på gamla bossar i 🏟️ Arenan. Fullt album ger +${k.p_album} ⭐!</p>
      <div class="karta-topp">🃏 ${k.antal} av ${k.totalt} kort</div>
      ${k.album.map((a) => { const har = a.kort.filter((x) => x.antal).length;
        return `<h3>${a.ikon} ${esc(a.namn)} <span class="small muted">${har}/10${har === 10 ? " 📖 Komplett!" : ""}</span></h3>
          <div class="album-rutnat">${a.kort.map((x) => x.antal ? this._kortRuta(x) : `<div class="samlarkort saknas"><div class="sk-ikon">❓</div><div class="sk-namn">${x.sallsynt === "legendarisk" ? "Boss" : "?"}</div></div>`).join("")}</div>`; }).join("")}`;
  }

  // Veckans syskonuppdrag: ett gemensamt mål, alla får belöningen.
  _syskonKort() {
    const u = this._s.syskon;
    if (!u) return "";
    const pct = Math.round((u.nu / u.mal) * 100);
    const del = u.bidrag.map((b) => `<span class="sy-del ${b.id === this._s.barn ? "jag" : ""}">${esc(b.namn)}: <b>${b.varde}</b>${u.satt === "alla" ? `/${u.per}` : ""}</span>`).join("");
    return `<div class="card syskon-kort ${u.klar ? "klar" : ""}"><div class="sy-rubrik">🤝 Veckans syskonuppdrag</div>
      <div class="sy-text">${u.ikon} ${esc(u.text)}</div>
      <div class="progress stor"><div style="width:${pct}%"></div></div>
      <div class="small">${u.nu} av ${u.mal}${u.klar ? ` · 🎉 Klart! Alla får +${u.beloning} ⭐` : ` · alla får +${u.beloning} ⭐ när ni klarar det`}</div>
      <div class="sy-delar">${del}</div></div>`;
  }

  // Listor som inte har övats på länge: repetera för extra ⭐ (gamla glosor glöms annars).
  _repeteraKort() {
    if (this._s.kan_valja) return "";
    const idag = new Date(), dagar = (iso) => Math.floor((idag - new Date(iso + "T12:00")) / 86400000);
    const lista = (this._s.data.amnen || []).flatMap((a) => a.glosor.filter((g) => (g.ovat_dagar || []).length && spelbaraPar(g).length)
      .map((g) => ({ a, g, sen: dagar(g.ovat_dagar[g.ovat_dagar.length - 1]) }))).filter((x) => x.sen >= REPETERA.dagar).sort((x, y) => y.sen - x.sen).slice(0, 3);
    if (!lista.length) return "";
    return `<div class="card repetera-kort"><b>🔁 Dags att repetera!</b> <span class="small">+${REPETERA.p} ⭐ extra per lista</span>
      <div class="small muted">Det du inte har övat på länge börjar glömmas. Ett varv räcker!</div>
      ${lista.map(({ a, g, sen }) => `<button class="row" data-rep="${a.id}|${g.id}"><span><b>${esc(g.namn)}</b><br><span class="muted small">${esc(a.namn)} · övade för ${sen} dagar sedan</span></span><span>▶</span></button>`).join("")}</div>`;
  }

  // Fråga husdjuret: barnet frågar om spelet och strategier, husdjuret (AI) svarar.
  _fragaView() {
    const d = this._s.meriter?.djur;
    if (!d) return `<p class="muted">Välj ett husdjur först.</p>`;
    const k = `${this._s.barn}`;
    this._fraga = this._fraga && this._fraga.barn === k ? this._fraga : { barn: k, historik: [] };
    const f = this._fraga;
    const ikon = `<div class="lar-ikon">${d.art}</div>`;
    const bubbla = (x) => x.vem === "barn" ? `<div class="lar-rad barn"><div class="lar-bubbla">${esc(x.text)}</div></div>`
      : `<div class="lar-rad djur">${ikon}<div class="lar-bubbla">${esc(x.text)}</div></div>`;
    const forslag = ["Vilken attack ska jag använda nu?", "Hur får jag flest ⭐?", "Hur besegrar jag bossen?", "Vad ska jag köpa?", "Hur funkar sviten?"];
    return `<div class="lar-chatt">${bubbla({ vem: "djur", text: `Hej! Undrar du något om spelet? Fråga mig om attacker, monster, ⭐ eller vad som helst! ${d.art}` })}
      ${f.historik.map(bubbla).join("")}
      ${f.tanker ? `<div class="lar-rad djur">${ikon}<div class="lar-bubbla tanker">🤔 …</div></div>` : ""}</div>
      ${f.historik.length ? "" : `<div class="fraga-forslag">${forslag.map((q) => `<button class="mini" data-fraga="${esc(q)}">${esc(q)}</button>`).join("")}</div>`}
      <div class="lar-input"><textarea id="fraga-text" rows="2" maxlength="300" placeholder="Skriv din fråga…" ${f.tanker ? "disabled" : ""}></textarea>
        <button class="primary" id="fraga-skicka" ${f.tanker ? "disabled" : ""}>💬 Fråga</button></div>`;
  }

  async _fragaSkicka(fraga) {
    const f = this._fraga, el = this.shadowRoot.querySelector("#fraga-text"), text = (fraga || el?.value || "").trim();
    if (!f || !text || f.tanker) return;
    f.historik.push({ vem: "barn", text });
    f.tanker = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/fraga", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, text, historik: f.historik.slice(0, -1) }) });
      const x = await res.json();
      if (!res.ok) throw new Error(x.message || res.statusText);
      f.historik.push({ vem: "djur", text: x.svar });
      f.historik = f.historik.slice(-20);
    } catch (e) {
      f.historik.pop();
      this._msg = { type: "error", text: e.message || String(e) };
    } finally {
      f.tanker = false;
      this._render();
      const c = this.shadowRoot.querySelector(".lar-chatt");
      c?.lastElementChild?.scrollIntoView({ block: "nearest" });
      if (!f.tanker) this.shadowRoot.querySelector("#fraga-text")?.focus();
    }
  }

  // ---------- pluggplan, övningsprov, svaga punkter, dagens läxlista, veckorapport ----------
  async _plan(op, args = {}, filer = null) {
    this._busy = true;
    this._render();
    try {
      const json = { barn: this._s.barn, op, ...args };
      let res;
      if (filer?.length) {
        const fd = new FormData();
        fd.append("json", JSON.stringify(json));
        filer.forEach((f) => fd.append("file", f, f.name || "bild.jpg"));
        res = await this._hass.fetchWithAuth("/api/skolan/plan", { method: "POST", body: fd });
      } else {
        res = await this._hass.fetchWithAuth("/api/skolan/plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) });
      }
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._msg = null;
      return body;
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      return null;
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _dagensListaKort() {
    const l = this._s.dagens_lista;
    if (!l?.rader?.length) return "";
    return `<div class="card dagens-lista"><div class="djur-rubrik">📋 ${this._s.kan_valja ? `${esc(this._s.namn)}s läxlista idag` : "Din läxlista idag"} <span class="small muted">· ca ${l.min} min</span></div>
      ${l.rader.map((r, i) => `<button class="row" data-dl="${i}"><span>${r.ikon} ${esc(r.text)}${r.missad ? ` <span class="small muted">(missad)</span>` : ""}</span><span class="small muted">${r.min} min ›</span></button>`).join("")}
      ${this._s.kan_valja ? "" : `<div class="small muted" style="margin-top:6px">Gör det översta först. Tips: starta ett ⏱️ fokuspass medan du pluggar!</div><div class="actions" style="margin-top:8px"><button class="ghost" id="dl-fokus">⏱️ Starta fokus</button></div>`}</div>`;
  }

  _planView() {
    const v = this._view, s = this._s, u = (s.data.uppdrag || []).find((x) => x.id === v.uppdrag);
    if (!u) return `<p class="muted">Provet finns inte.</p>`;
    const f = forhorInfo(u.datum), plan = u.plan;
    const huvud = `<div class="forhor-kort">📝 <b>${esc(u.namn)}</b> · ${esc(u.amne_namn || "")} · provet är <b>${esc(f?.text || "")}</b> · ${f?.kvar || ""}</div>`;
    if (!plan?.delar?.length || v.g) return huvud + this._planGuide(u);
    const d = s.meriter?.djur, idag = idagISO();
    const dagar = [...new Set(plan.delar.map((x) => x.dag))].sort();
    const klara = plan.delar.filter((x) => x.klar).length, missade = plan.delar.filter((x) => !x.klar && x.dag < idag).length;
    const START = { forhor: ["📝", "Förhör"], forklara: ["🙋", "Förklara"], glosor: ["📝", "Förhör"], uppgifter: ["✏️", "Hjälp"], ovningsprov: ["🧪", "Gör provet"], repetera: ["🔁", "Repetera"], sammanfatta: ["✍️", "Visa husdjuret"] };
    const rad = (x) => {
      const st = START[x.typ];
      return `<div class="pd-rad ${x.klar ? "klar" : ""}"><button class="pd-check" data-pd-klar="${x.id}" title="Klar">${x.klar ? "✅" : "⬜"}</button>
        <div class="pd-text"><b>${PLAN_IKON[x.typ] || "📅"} ${esc(x.titel)}</b> <span class="small muted">· ${x.min} min</span>${x.vad ? `<div class="small">${esc(x.vad)}</div>` : ""}</div>
        ${st && !x.klar ? `<button class="mini" data-pd-start="${x.typ}">${st[0]} ${st[1]}</button>` : ""}</div>`;
    };
    const ops = (plan.ovningsprov || []).filter((o) => o.resultat);
    return `${huvud}
      ${plan.inst?.tips && d ? `<div class="lar-rad djur"><div class="lar-ikon">${d.art}</div><div class="lar-bubbla">${esc(plan.inst.tips)}</div></div>` : ""}
      ${s.kan_valja && plan.inst?.tankar ? `<div class="card hjalp-kort pd-tankar"><b>🧠 AI:ns tankar om ${esc(s.namn)}s studietaktik</b><div class="small" style="margin-top:6px">${esc(plan.inst.tankar)}</div><div class="small muted" style="margin-top:6px">Visas bara för föräldrar.</div></div>` : ""}
      <div class="small">${klara} av ${plan.delar.length} delar klara</div><div class="progress stor" style="margin:6px 0 10px"><div style="width:${(klara / plan.delar.length) * 100}%"></div></div>
      ${missade ? `<div class="card hjalp-kort">⚠️ ${missade} ${missade === 1 ? "del" : "delar"} hann inte bli gjorda. Ingen fara! <button class="mini primary" id="pd-om">🔄 Gör om planen</button><div class="small muted">Då anpassas planen efter hur det har gått.</div></div>` : ""}
      ${dagar.map((dag) => `<div class="pd-dag ${dag === idag ? "idag" : dag < idag ? "forr" : ""}"><div class="pd-rubrik">${dag === idag ? "Idag · " : ""}${veckodag(dag)} ${Number(dag.slice(8))}/${Number(dag.slice(5, 7))}</div>
        ${plan.delar.filter((x) => x.dag === dag).map(rad).join("")}</div>`).join("")}
      ${plan.omraden?.length ? `<h3>🎯 Områden</h3><div class="list">${plan.omraden.map((o) => `<div class="row static"><span>${esc(o.namn)}</span><span>${["😟 kan inte än", "🤔 osäker", "😀 kan"][o.kan]}</span></div>`).join("")}</div>` : ""}
      ${ops.length ? `<h3>🧪 Övningsprov</h3><div class="list">${ops.map((o) => `<button class="row" data-ovp-visa="${o.id}"><span>${esc((o.klar || o.skapad).slice(0, 10))}</span><span>${o.ratt} av ${o.fragor.length} rätt ›</span></button>`).join("")}</div>` : ""}
      <div class="actions"><button class="primary" data-ovp="${u.id}">🧪 Övningsprov</button>${d ? `<button class="ghost" data-hjalp-prov="${u.id}">📚 Plugga med ${esc(d.namn)}</button>` : ""}<button class="ghost" id="pd-om2">🔄 Gör om planen</button>${s.kan_valja ? `<button class="ghost danger" id="pd-bort">Ta bort planen</button>` : ""}</div>`;
  }

  _planGuide(u) {
    const v = this._view, s = this._s, p = s.studieprofil || { min_dag: 20, dagar: [0, 1, 2, 3, 6], satt: [], svart: "" }, inst = u.plan?.inst || {};
    v.g = v.g || { provtyp: inst.provtyp || (u.glosor?.length ? "glosor" : "skriftligt"), omfattning: inst.omfattning || u.kapitel || "", omraden: (u.plan?.omraden || []).map((o) => ({ ...o })),
      min_dag: p.min_dag, dagar: [...p.dagar], satt: [...p.satt], svart: p.svart || "", mal: inst.mal || "bra", uteslut: [], foton: [] };
    const g = v.g, idag = idagISO();
    const chip = (attr, val, text, pa) => `<button class="mini ${pa ? "primary" : ""}" data-${attr}="${val}">${text}</button>`;
    const TYP = { skriftligt: "✍️ Skriftligt", glosor: "🗣️ Glosförhör", muntligt: "🎤 Muntligt", praktiskt: "🔧 Praktiskt", inlamning: "📄 Inlämning" };
    const SATT = { forhor: "📝 Bli förhörd", lasa: "📖 Läsa", skriva: "✍️ Skriva anteckningar", forklara: "🙋 Förklara för någon", rita: "🎨 Rita/tankekartor", lyssna: "🎧 Lyssna och prata", uppgifter: "✏️ Göra uppgifter", ovningsprov: "🧪 Övningsprov" };
    const MAL = { godkant: "👍 Klara provet", bra: "⭐ Bra resultat", toppen: "🏆 Toppresultat" };
    const dagarLista = [];
    for (let d = idag; d < u.datum && dagarLista.length < 21; d = plusDagar(d, 1)) if (g.dagar.includes((new Date(`${d}T12:00`).getDay() + 6) % 7)) dagarLista.push(d);
    const pga = dagarLista.filter((d) => !g.uteslut.includes(d)).length;
    return `<div class="pg">
      <p class="small muted">${u.plan ? "Ändra det du vill, så gör AI:n om planen och lär sig av hur det har gått." : "Svara på några frågor så gör AI:n en plan som passar just dig."}</p>
      <h4>1. Vad är det för prov?</h4><div class="fraga-forslag">${Object.entries(TYP).map(([k, t]) => chip("pg-typ", k, t, g.provtyp === k)).join("")}</div>
      <h4>2. Vad ska ingå?</h4>
      <textarea id="pg-omf" rows="3" placeholder="T.ex. kapitel 2, sidorna 30–52, bråk och procent. Skriv vad läraren har sagt.">${esc(g.omfattning)}</textarea>
      <div class="actions" style="margin-top:6px"><label class="ghost upload mini">📷 Fota provinfon${g.foton.length ? ` (${g.foton.length})` : ""}<input type="file" id="pg-foto" accept="image/*,application/pdf" multiple hidden></label>
        <button class="mini primary" id="pg-hitta" ${this._busy ? "disabled" : ""}>🤖 Hitta områdena</button></div>
      ${g.foton.length ? `<div class="small">${g.foton.map((f) => `🖼️ ${esc(f.name || "bild")}`).join(" · ")} <button class="mini" id="pg-foto-bort">✕</button></div>` : ""}
      <h4>3. Hur säker känner du dig?</h4>
      ${g.omraden.length ? g.omraden.map((o, i) => `<div class="pg-omr"><span>${esc(o.namn)}${o.info ? `<br><span class="small muted">${esc(o.info)}</span>` : ""}</span>
        <span class="pg-kan">${["😟", "🤔", "😀"].map((e, k) => `<button class="mini ${o.kan === k ? "primary" : ""}" data-pg-kan="${i}:${k}" title="${["Kan inte än", "Osäker", "Kan"][k]}">${e}</button>`).join("")}<button class="mini" data-pg-bort="${i}">✕</button></span></div>`).join("")
        : `<p class="small muted">Tryck på 🤖 Hitta områdena, eller skriv in dem själv.</p>`}
      <div class="pg-ny"><input id="pg-ny" placeholder="Lägg till ett område"><button class="mini" id="pg-ny-ok">➕</button></div>
      <div class="small muted">😟 kan inte än · 🤔 osäker · 😀 kan. Planen lägger mest tid på 😟 och 🤔.</div>
      <h4>4. Hur mycket och när?</h4>
      <div class="fraga-forslag">${[10, 15, 20, 30, 45, 60].map((m) => chip("pg-min", m, `${m} min/dag`, g.min_dag === m)).join("")}</div>
      <div class="fraga-forslag">${["Mån", "Tis", "Ons", "Tor", "Fre", "Lör", "Sön"].map((n, i) => chip("pg-dag", i, n, g.dagar.includes(i))).join("")}</div>
      ${dagarLista.length ? `<div class="small muted">Någon dag du inte kan (träning, kalas)? Tryck bort den.</div><div class="fraga-forslag">${dagarLista.map((d) => chip("pg-ut", d, `${veckodag(d).slice(0, 3)} ${Number(d.slice(8))}/${Number(d.slice(5, 7))}`, !g.uteslut.includes(d))).join("")}</div>` : ""}
      <div class="small">${pga} pluggdag${pga === 1 ? "" : "ar"} före provet.</div>
      <h4>5. Vad är ditt mål?</h4><div class="fraga-forslag">${Object.entries(MAL).map(([k, t]) => chip("pg-mal", k, t, g.mal === k)).join("")}</div>
      <h4>6. Hur pluggar du bäst?</h4><div class="fraga-forslag">${Object.entries(SATT).map(([k, t]) => chip("pg-satt", k, t, g.satt.includes(k))).join("")}</div>
      <textarea id="pg-svart" rows="2" placeholder="Är det något som brukar vara svårt? (frivilligt)">${esc(g.svart)}</textarea>
      <div class="actions"><button class="primary" id="pg-skapa" ${this._busy || !pga ? "disabled" : ""}>✨ ${u.plan ? "Gör om min plan" : "Gör min plan"}</button>${u.plan?.delar?.length ? `<button class="ghost" id="pg-avbryt">Avbryt</button>` : ""}</div>
      ${this._busy ? `<p class="small muted">AI:n tänker… (tar några sekunder)</p>` : ""}</div>`;
  }

  _ovningsprovView() {
    const v = this._view, s = this._s, u = (s.data.uppdrag || []).find((x) => x.id === v.uppdrag);
    if (!u) return `<p class="muted">Provet finns inte.</p>`;
    const sparade = u.plan?.ovningsprov || [];
    const o = v.p || sparade.find((x) => x.id === v.prov) || (!v.ny && sparade.filter((x) => !x.resultat).slice(-1)[0]);
    if (!o) {
      return `<div class="card hjalp-kort center"><div class="big">🧪</div><p>Ett övningsprov på <b>${esc(u.namn)}</b>, som ett riktigt prov fast utan stress. AI:n gör frågorna av ditt material och lägger fler frågor på det du är osäker på.</p>
        <p class="small muted">Klart prov: +10 ⭐ (en gång per dag) och en pluggdag mot provbossen. Fel svar sparas som 🔁 svaga punkter.</p>
        <div class="actions" style="justify-content:center"><button class="primary" id="ovp-skapa" ${this._busy ? "disabled" : ""}>🧪 Skapa övningsprov</button></div>${this._busy ? `<p class="small muted">AI:n skriver frågorna…</p>` : ""}</div>`;
    }
    const res = v.res || (o.resultat ? { resultat: o.resultat, ratt: o.ratt, av: o.fragor.length, facit: o.fragor.map((q) => q.facit) } : null);
    v.svar = v.svar || [];
    if (res) {
      return `<div class="card hjalp-kort center"><div class="big">${res.ratt / res.av >= 0.8 ? "🌟" : res.ratt / res.av >= 0.5 ? "👍" : "💪"}</div><div class="score">${res.ratt} av ${res.av} rätt</div>${res.p ? `<div class="lar-beloning">+${res.p} ⭐</div>` : ""}${res.prov_lage ? `<div class="small muted">Förälder provade: inga ⭐ och inget sparas.</div>` : ""}</div>
        ${o.fragor.map((q, i) => { const r = res.resultat[i] || {}; return `<div class="kontroll ${r.ratt ? "ratt" : "fel"}"><div><b>${r.ratt ? "✅" : "❌"} ${i + 1}. ${esc(q.fraga)}</b></div>
          <div class="small">Ditt svar: ${esc(r.svar || "–")}</div>${!r.ratt ? `<div class="small">Rätt svar: <b>${esc(res.facit?.[i] || q.facit || "")}</b></div>` : ""}${r.kommentar ? `<div class="small muted">${esc(r.kommentar)}</div>` : ""}</div>`; }).join("")}
        ${res.resultat.some((r) => !r.ratt) && !res.prov_lage ? `<p class="small">🔁 Frågorna du missade kommer tillbaka som svaga punkter, så att de fastnar.</p>` : ""}
        <div class="actions"><button class="primary" data-plan="${u.id}">📅 Till pluggplanen</button><button class="ghost" id="ovp-ny">🧪 Ett nytt övningsprov</button></div>`;
    }
    return `<p class="small muted">Svara så gott du kan. Stavningen spelar ingen roll. Hoppa över om du inte vet.</p>
      ${o.fragor.map((q, i) => `<div class="kontroll"><div><b>${i + 1}. ${esc(q.fraga)}</b></div>${q.alternativ?.length
        ? q.alternativ.map((a) => `<button class="row ${v.svar[i] === a ? "vald-rad" : ""}" data-ovp-alt="${i}" data-alt="${esc(a)}">${esc(a)}</button>`).join("")
        : `<textarea rows="2" data-ovp-svar="${i}" placeholder="Ditt svar">${esc(v.svar[i] || "")}</textarea>`}</div>`).join("")}
      <div class="actions"><button class="primary" id="ovp-in" data-prov="${o.id}" ${this._busy ? "disabled" : ""}>📤 Lämna in</button></div>${this._busy ? `<p class="small muted">AI:n rättar…</p>` : ""}`;
  }

  _svagaView() {
    const v = this._view, s = this._s, lista = s.svaga_idag || [], st = s.svaga || {};
    if (!lista.length) return `<div class="card hjalp-kort center"><div class="big">🎉</div><p>Inga svaga punkter att repetera idag!</p>
      <p class="small muted">${st.totalt ? `${st.totalt} kommer tillbaka de närmaste dagarna. ` : ""}${st.befasta ? `${st.befasta} har du redan befäst. 💪` : "Frågor du svarar fel på i förhör och övningsprov hamnar här och kommer tillbaka efter 1, 3 och 7 dagar tills de sitter."}</p></div>`;
    const x = lista[0], a = (s.data.amnen || []).find((y) => y.id === x.amne);
    return `<div class="small muted">${lista.length} kvar idag · kommer tillbaka efter 1, 3 och 7 dagar tills den sitter (${x.steg} av 3)</div>
      <div class="card hjalp-kort"><div class="small muted">${esc(a?.namn || "")}</div><div class="duell-ord" style="font-size:20px">${esc(x.fraga)}</div>
        ${v.visa ? `<div class="sv-facit">Rätt svar: <b>${esc(x.facit)}</b></div>` : `<textarea id="sv-text" rows="2" placeholder="Tänk ut svaret (eller skriv det här)"></textarea>`}</div>
      <div class="actions">${v.visa ? `<button class="primary" data-sv="1">😀 Jag kunde</button><button class="ghost" data-sv="0">😟 Inte än</button>` : `<button class="primary" id="sv-visa">👀 Visa svaret</button>`}</div>`;
  }

  // Föräldrarnas studiecoach: önskemål som AI:n väger in (inte order) och ett samtal om barnets studietaktik.
  _coachView() {
    const v = this._view, s = this._s;
    const o = (v.o = v.o || { ...(s.onskemal || { strikthet: "lagom", text: "" }) });
    if (!this._coach || this._coach.barn !== s.barn) this._coach = { barn: s.barn, historik: [] };
    const c = this._coach;
    const STR = { mild: ["🌱 Mild", "Flexibelt, korta pass och mycket pepp"], lagom: ["⚖️ Lagom", "Tydlig plan med lite luft"], strang: ["🎯 Sträng", "Tydliga krav och regelbunden repetition"] };
    const bubbla = (x, i) => x.vem === "jag" ? `<div class="lar-rad barn"><div class="lar-bubbla">${esc(x.text)}</div></div>`
      : `<div class="lar-rad djur"><div class="lar-ikon">🧠</div><div class="lar-bubbla coach-svar">${esc(x.text)}${x.onskemal ? `<div class="coach-forslag"><b>Förslag på önskemål:</b> ${esc(STR[x.onskemal.strikthet]?.[0] || "")}${x.onskemal.text ? ` · ${esc(x.onskemal.text)}` : ""}<br><button class="mini primary" data-coach-anvand="${i}">💾 Använd förslaget</button></div>` : ""}</div></div>`;
    const forslag = [`Hur pluggar ${s.namn} bäst?`, "Vad kan vi göra annorlunda inför nästa prov?", "Är planerna för hårda eller för lätta?", `Hur kan vi peppa ${s.namn} utan att tjata?`];
    return `<div class="card hjalp-kort"><b>🎛️ Era önskemål för ${esc(s.namn)}s pluggplaner</b>
        <div class="small muted" style="margin:4px 0 8px">AI:n väger in det här när den gör planer och rapporter, men ${esc(s.namn)}s egna svar och bästa går först. Det är förslag, inte order.</div>
        <div class="fraga-forslag">${Object.entries(STR).map(([k, [t, info]]) => `<button class="mini ${o.strikthet === k ? "primary" : ""}" data-coach-str="${k}" title="${esc(info)}">${t}</button>`).join("")}</div>
        <div class="small">${esc(STR[o.strikthet]?.[1] || "")}</div>
        <textarea id="coach-onsk" rows="3" placeholder="T.ex. mer läsning och mindre skärm, max 30 min på vardagar, gärna att vi förhör hemma på söndagar…">${esc(o.text || "")}</textarea>
        <div class="actions" style="margin-top:8px"><button class="primary" id="coach-spara" ${this._busy ? "disabled" : ""}>💾 Spara önskemålen</button></div>
        ${s.onskemal?.uppdaterad ? `<div class="small muted">Senast ändrat ${esc(s.onskemal.uppdaterad.replace("T", " "))}${s.onskemal.av ? ` av ${esc(s.onskemal.av)}` : ""}</div>` : ""}</div>
      <h3>💬 Prata med studiecoachen</h3>
      <div class="lar-chatt">${bubbla({ vem: "ai", text: `Hej! Jag har koll på ${s.namn}s pluggplaner, prov, övningsprov och veckan som gått. Fråga mig om studietaktiken, eller säg hur du vill att planerna ska vara.` }, -1)}
        ${c.historik.map(bubbla).join("")}${c.tanker ? `<div class="lar-rad djur"><div class="lar-ikon">🧠</div><div class="lar-bubbla tanker">🤔 …</div></div>` : ""}</div>
      ${c.historik.length ? "" : `<div class="fraga-forslag">${forslag.map((q) => `<button class="mini" data-coach-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>`}
      <div class="lar-input"><textarea id="coach-text" rows="2" maxlength="800" placeholder="Skriv till coachen…" ${c.tanker ? "disabled" : ""}></textarea>
        <button class="primary" id="coach-skicka" ${c.tanker ? "disabled" : ""}>💬 Skicka</button></div>
      <p class="small muted">Samtalet syns bara för föräldrar och sparas inte.</p>`;
  }

  async _coachSkicka(fast) {
    const c = this._coach, el = this.shadowRoot.querySelector("#coach-text"), text = (fast || el?.value || "").trim();
    if (!c || !text || c.tanker) return;
    c.historik.push({ vem: "jag", text });
    c.tanker = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/plan", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, op: "coach", text, historik: c.historik.slice(0, -1).map(({ vem, text }) => ({ vem, text })) }) });
      const x = await res.json();
      if (!res.ok) throw new Error(x.message || res.statusText);
      c.historik.push({ vem: "ai", text: x.svar, onskemal: x.onskemal });
      c.historik = c.historik.slice(-30);
    } catch (e) {
      c.historik.pop();
      this._msg = { type: "error", text: e.message || String(e) };
    } finally {
      c.tanker = false;
      this._render();
      this.shadowRoot.querySelector(".lar-chatt")?.lastElementChild?.scrollIntoView({ block: "nearest" });
    }
  }

  _rapportView() {
    const v = this._view, s = this._s;
    if (!v.r && !v.hamtar && !this._busy) {
      v.hamtar = true;
      this._plan("rapport", {}).then((x) => { v.hamtar = false; if (x) { v.r = x; this._render(); } });
    }
    if (!v.r) return `<p class="muted">${v.hamtar ? "AI:n skriver veckorapporten… (tar några sekunder)" : "Kunde inte hämta rapporten."}</p>`;
    const r = v.r.rapport || {};
    const lista = (rub, l) => (l?.length ? `<h3>${rub}</h3><ul class="lista">${l.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "");
    return `<div class="card hjalp-kort"><b>📊 Vecka ${esc(String(v.r.vecka).slice(5))} · ${esc(s.namn)}</b><p>${esc(r.sammanfattning || "")}</p></div>
      ${lista("👍 Det här har gått bra", r.bra)}${lista("🤔 Det här behöver mer övning", r.svart)}${lista("📅 Nästa vecka", r.kommande)}
      ${r.studietaktik ? `<div class="card hjalp-kort pd-tankar"><b>🧠 AI:ns tankar om studietaktiken</b><div class="small" style="margin-top:6px">${esc(r.studietaktik)}</div></div>` : ""}
      ${lista("🤝 Så kan ni hjälpa", r.tips)}${lista("🍽️ Frågor vid middagen", r.middagsfragor)}
      <div class="small muted">Skriven ${esc(String(v.r.skapad || "").replace("T", " ").slice(0, 16))} av AI:n utifrån det ${esc(s.namn)} gjort i appen.</div>
      <div class="actions"><button class="ghost" id="rap-ny" ${this._busy ? "disabled" : ""}>🔄 Skriv om rapporten</button></div>`;
  }

  // Plugga med husdjuret: en hjälplärare som utgår från barnets eget material och aldrig säger svaret.
  _hjalpView() {
    const d = this._s.meriter?.djur;
    if (!d) return `<p class="muted">Välj ett husdjur först.</p>`;
    const k = this._s.barn, amnen = this._s.data.amnen || [];
    if (!this._hjalp || this._hjalp.barn !== k) this._hjalp = { barn: k, historik: [], lage: "forklara" };
    const h = this._hjalp, idag = idagISO();
    if (!h.amne) {
      const kommande = (this._s.data.uppdrag || []).filter((u) => u.datum && u.datum >= idag && (u.typ === "prov" || !u.klart) && amnen.some((a) => a.id === u.amne))
        .sort((x, y) => (x.typ === "prov" ? 0 : 1) - (y.typ === "prov" ? 0 : 1) || x.datum.localeCompare(y.datum)).slice(0, 6);
      const om = (iso) => { const n = Math.round((new Date(`${iso}T12:00`) - new Date(`${idag}T12:00`)) / 86400000); return n === 0 ? "idag" : n === 1 ? "i morgon" : `om ${n} dagar`; };
      return `<div class="lar-chatt"><div class="lar-rad djur"><div class="lar-ikon">${d.art}</div><div class="lar-bubbla">Hej! Jag är din hjälplärare. Vad ska vi plugga på? Jag kan förklara, förhöra dig eller hjälpa dig med en uppgift. Men jag säger aldrig svaret, du ska klura ut det själv! 😉</div></div></div>
        ${kommande.length ? `<div class="card hjalp-kort"><b>📅 Snart</b>${kommande.map((u) => `<button class="row" data-hjalp-u="${u.amne}|${u.id}"><span>${u.typ === "prov" ? "📝" : "📖"} <b>${esc(u.namn)}</b><br><span class="small muted">${esc(u.amne_namn || "")} · ${u.typ === "prov" ? "provet" : "klart"} ${om(u.datum)}</span></span><span>▶</span></button>`).join("")}</div>` : ""}
        ${this._s.svaga?.idag ? `<button class="row" id="open-svaga" style="margin-bottom:10px"><span>🔁 <b>Svaga punkter</b><br><span class="small muted">${this._s.svaga.idag} att repetera idag</span></span><span>›</span></button>` : ""}
        <div class="card hjalp-kort"><b>📚 Välj ämne</b><div class="fraga-forslag" style="margin-top:8px">${amnen.map((a) => `<button class="mini" data-hjalp-u="${a.id}|">${esc(a.namn)}</button>`).join("")}</div></div>`;
    }
    const a = amnen.find((x) => x.id === h.amne), u = (this._s.data.uppdrag || []).find((x) => x.id === h.uppdrag);
    const p = h.poang || this._s.hjalp || { ratt: 0, pass: 0, per_pass: 5, max: 2, p: 8 };
    const ikon = `<div class="lar-ikon">${d.art}</div>`;
    const bubbla = (x) => x.vem === "barn" ? `<div class="lar-rad barn"><div class="lar-bubbla">${x.bild ? "📷 " : ""}${esc(x.text)}</div></div>`
      : `<div class="lar-rad djur">${ikon}<div class="lar-bubbla">${x.ratt === true ? "✅ " : x.ratt === false ? "❌ " : ""}${esc(x.text)}</div></div>`;
    const LAGEN = { forklara: ["🙋", "Förklara"], forhor: ["📝", "Förhör mig"], uppgift: ["📷", "Hjälp med uppgift"], ...(u && (u.typ === "las" || u.typ === "hogl") ? { las: ["🧠", "Prata om boken"] } : {}), skriv: ["✍️", "Tips på min text"] };
    const start = { forklara: "Vad vill du förstå bättre? Skriv vad du undrar över, så förklarar jag! 💡", forhor: "Tryck på Starta så ställer jag en fråga i taget. Varje gång du får 5 rätt blir det ⭐!", uppgift: "Fota uppgiften (eller skriv av den) så hjälper jag dig steg för steg. 📷",
      las: "Har du läst? Tryck på Starta så pratar vi om boken! Jag ställer en fråga i taget. 📖", skriv: "Fota din text (eller klistra in den) så säger jag vad som är bra och ger några tips. Jag skriver inte om den, det gör du! ✍️" }[h.lage];
    const forhorLage = h.lage === "forhor" || h.lage === "las", fotoLage = h.lage === "uppgift" || h.lage === "skriv";
    const bild = h.bild ? `<div class="small">🖼️ ${esc(h.bild.name || "Bild")} <button class="mini" id="hjalp-bild-bort">✕</button></div>` : "";
    const tom = !h.historik.length;
    return `<div class="card hjalp-topp"><span>${u ? (u.typ === "prov" ? "📝 " : "📖 ") + `<b>${esc(u.namn)}</b> · ` : ""}<b>${esc(a?.namn || "")}</b></span><button class="mini ghost" id="hjalp-byt">Byt ämne</button></div>
      <div class="hjalp-lagen">${Object.entries(LAGEN).map(([id, [i, t]]) => `<button class="mini ${h.lage === id ? "primary" : ""}" data-hjalp-lage="${id}" ${h.tanker ? "disabled" : ""}>${i} ${t}</button>`).join("")}</div>
      ${forhorLage ? `<div class="small hjalp-poang">✅ ${p.ratt} rätt idag${p.pass < p.max ? ` · ${p.per_pass - (p.ratt % p.per_pass)} kvar till +${p.p} ⭐${u?.typ === "prov" ? " och en pluggdag mot provbossen" : ""}` : " · dagens ⭐ är tagna, men det är bra plugg ändå!"}</div>` : ""}
      <div class="lar-chatt">${bubbla({ vem: "djur", text: start })}${h.historik.map(bubbla).join("")}
        ${h.tanker ? `<div class="lar-rad djur">${ikon}<div class="lar-bubbla tanker">🤔 …</div></div>` : ""}</div>
      ${forhorLage && tom ? `<div class="actions"><button class="primary" id="hjalp-starta" ${h.tanker ? "disabled" : ""}>${h.lage === "las" ? "🧠 Starta" : "📝 Starta förhöret"}</button></div>`
        : `${fotoLage ? `${bild}<label class="ghost upload mini">📷 ${h.bild ? "Byt bild" : h.lage === "skriv" ? "Fota din text" : "Fota uppgiften"}<input type="file" id="hjalp-foto" accept="image/*" hidden></label>` : ""}
      ${h.lage === "uppgift" && !tom ? `<button class="mini" id="hjalp-likadan" ${h.tanker ? "disabled" : ""}>🔁 En till likadan</button>` : ""}
      <div class="lar-input"><textarea id="hjalp-text" rows="2" maxlength="${h.lage === "skriv" ? 3000 : 600}" placeholder="${forhorLage && !tom ? "Ditt svar…" : h.lage === "uppgift" ? "Skriv uppgiften eller hur du tänker…" : h.lage === "skriv" ? "Klistra in texten, eller skriv vad uppgiften var…" : "Skriv vad du undrar…"}" ${h.tanker ? "disabled" : ""}></textarea>
        <div class="actions"><button class="primary" id="hjalp-skicka" ${h.tanker ? "disabled" : ""}>${forhorLage && !tom ? "✔️ Svara" : "💬 Skicka"}</button>${forhorLage && !tom ? `<button class="ghost" id="hjalp-ny" ${h.tanker ? "disabled" : ""}>⏭️ Ny fråga</button>` : ""}</div></div>`}
      <div class="small muted">Husdjuret använder dina böcker, glosor och läxor. Ju mer material du har lagt in i ämnet, desto bättre kan det hjälpa.</div>`;
  }

  async _hjalpSkicka(fast) {
    const h = this._hjalp, el = this.shadowRoot.querySelector("#hjalp-text"), text = (fast || el?.value || "").trim();
    if (!h || h.tanker || (!text && !h.bild)) return;
    const bild = h.lage === "uppgift" || h.lage === "skriv" ? h.bild : null;
    h.historik.push({ vem: "barn", text: text || "Här är uppgiften.", bild: !!bild });
    h.tanker = true;
    this._render();
    try {
      const json = { barn: this._s.barn, amne: h.amne, uppdrag: h.uppdrag || null, lage: h.lage, text: text || "", historik: h.historik.slice(0, -1).map(({ vem, text }) => ({ vem, text })) };
      let res;
      if (bild) {
        const fd = new FormData();
        fd.append("json", JSON.stringify(json));
        fd.append("file", bild, bild.name || "uppgift.jpg");
        res = await this._hass.fetchWithAuth("/api/skolan/hjalp", { method: "POST", body: fd });
      } else {
        res = await this._hass.fetchWithAuth("/api/skolan/hjalp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) });
      }
      const x = await res.json();
      if (!res.ok) throw new Error(x.message || res.statusText);
      if (bild) h.bild = null;
      h.historik.push({ vem: "djur", text: x.svar, ratt: x.ratt });
      h.historik = h.historik.slice(-24);
      if (x.poang) h.poang = x.poang;
      if (x.poang?.pass_klart && x.poang.p_ny) {
        this._fx({ text: "📚 BRA PLUGGAT!", sub: `+${x.poang.p_ny} ⭐${x.poang.studiedag ? " · pluggdag mot provbossen!" : ""}`, emojis: ["📚", "🧠", "⭐", "💡"], antal: 30, konfetti: true, farg: "#43a047" });
        this._load(this._s.barn);
      }
    } catch (e) {
      h.historik.pop();
      this._msg = { type: "error", text: e.message || String(e) };
    } finally {
      h.tanker = false;
      this._render();
      this.shadowRoot.querySelector(".lar-chatt")?.lastElementChild?.scrollIntoView({ block: "nearest" });
      this.shadowRoot.querySelector("#hjalp-text")?.focus();
    }
  }

  // Lär husdjuret: barnet förklarar, husdjuret (AI) frågar vidare eller tackar.
  _larView() {
    const v = this._view, d = this._s.meriter?.djur, a = this._amne(v.amne), g = a?.glosor.find((x) => x.id === v.glosor);
    if (!g || !d) return `<p class="muted">Listan finns inte.</p>`;
    if (v.i == null) {
      const idx = g.par.map((p, i) => i).filter((i) => g.par[i].length > 1 && String(g.par[i][0]).trim() && String(g.par[i][1]).trim());
      v.i = idx[Math.floor(Math.random() * idx.length)];
      v.historik = [];
    }
    const term = g.par[v.i][0];
    const vad = gTyp(g) === "begrepp" ? "begreppet" : gTyp(g) === "formler" ? "formeln" : "ordet";
    const fraga = `Hej! Jag har hört ${vad} <b>${esc(term)}</b> men fattar inte vad det betyder. Kan du förklara för mig? 🤔`;
    const bubbla = (x) => x.vem === "barn" ? `<div class="lar-rad barn"><div class="lar-bubbla">${esc(x.text)}</div></div>`
      : `<div class="lar-rad djur"><div class="lar-ikon">${d.art}</div><div class="lar-bubbla">${x.html || esc(x.text)}</div></div>`;
    return `<div class="lar-chatt">${bubbla({ vem: "djur", html: fraga })}${v.historik.map(bubbla).join("")}
      ${v.tanker ? `<div class="lar-rad djur"><div class="lar-ikon">${d.art}</div><div class="lar-bubbla tanker">🤔 …</div></div>` : ""}</div>
      ${v.klar ? `<div class="card center">${v.p ? `<div class="lar-beloning">🎓 +${v.p} ⭐</div>` : ""}${v.facit ? `<div class="small">Det betyder: <b>${esc(v.facit)}</b></div>` : ""}
          <div class="actions"><button class="primary" id="lar-igen">🎓 ${{ begreppet: "Ett begrepp", formeln: "En formel", ordet: "Ett ord" }[vad]} till</button><button class="ghost" id="lar-klar">Klar</button></div></div>`
        : `<div class="lar-input"><textarea id="lar-text" rows="3" maxlength="400" placeholder="Förklara med egna ord, gärna med ett exempel…" ${v.tanker ? "disabled" : ""}></textarea>
          <button class="primary" id="lar-skicka" ${v.tanker ? "disabled" : ""}>💬 Förklara</button></div>`}`;
  }

  async _larSkicka() {
    const v = this._view, el = this.shadowRoot.querySelector("#lar-text"), text = (el?.value || "").trim();
    if (!text || v.tanker) return;
    v.historik.push({ vem: "barn", text });
    v.tanker = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/lar", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, amne: v.amne, glosor: v.glosor, i: v.i, text, historik: v.historik.slice(0, -1) }) });
      const x = await res.json();
      if (!res.ok) throw new Error(x.message || res.statusText);
      v.historik.push({ vem: "djur", text: x.svar });
      if (x.klar) {
        v.klar = true; v.p = x.p; v.facit = x.facit;
        if (x.p) { this._fx({ text: x.betyg >= 3 ? "🎓 SUPERFÖRKLARAT!" : "🎓 BRA FÖRKLARAT!", sub: `+${x.p} ⭐`, emojis: ["🎓", "💡", "⭐", "🧠"], antal: 30, konfetti: x.betyg >= 3, farg: "#43a047" }); this._load(this._s.barn); }
      }
    } catch (e) {
      v.historik.pop();
      this._msg = { type: "error", text: e.message || String(e) };
    } finally {
      v.tanker = false;
      this._render();
    }
  }

  // Fokusläge: en timer medan husdjuret sover bredvid. Klar tid ger ⭐.
  _fokusView() {
    const d = this._s.meriter?.djur, f = this._s.data.meriter?.fokus;
    if (!f) {
      return `<div class="card center"><div class="fokus-djur">${d ? ritaDjur(d.art, "glad", Math.max(1, d.steg), {}) : "⏱️"}</div>
        <p>Plugga utan att göra något annat. ${d ? esc(d.namn) : "Husdjuret"} sover bredvid och vaknar när tiden är slut.</p>
        <div class="fokus-val">${[[10, 5], [15, 8], [20, 10], [25, 12]].map(([m, p]) => `<button class="primary" data-fokus="${m}">${m} min<br><small>+${p} ⭐</small></button>`).join("")}</div>
        <p class="small muted">Lägg undan telefonen eller ha bara läxan öppen. Två fokuspass om dagen ger ⭐.</p></div>`;
    }
    const slut = new Date(f.start).getTime() + f.min * 60000;
    return `<div class="card center fokus-pagar"><div class="fokus-djur sover">${d ? ritaDjur(d.art, "nojd", Math.max(1, d.steg), { form: d.form }) : ""}<span class="zzz">💤</span></div>
      <div class="fokus-tid" id="fokus-tid" data-slut="${slut}">--:--</div>
      <p class="small">${d ? esc(d.namn) : "Husdjuret"} sover. Plugga på så länge! 📚</p>
      <button class="primary" id="fokus-klar" style="display:none">🎉 Klar! Väck ${d ? esc(d.namn) : "husdjuret"}</button>
      <button class="ghost" id="fokus-avbryt">Avbryt</button></div>`;
  }

  _fokusTick() {
    const el = this.shadowRoot?.querySelector("#fokus-tid");
    if (!el) { clearInterval(this._fokusTimer); this._fokusTimer = null; return; }
    const kvar = Math.max(0, Math.round((Number(el.dataset.slut) - Date.now()) / 1000));
    el.textContent = `${String(Math.floor(kvar / 60)).padStart(2, "0")}:${String(kvar % 60).padStart(2, "0")}`;
    if (!kvar) {
      clearInterval(this._fokusTimer); this._fokusTimer = null;
      el.textContent = "⏰ Klart!";
      const k = this.shadowRoot.querySelector("#fokus-klar");
      if (k) k.style.display = "";
    }
  }

  // Lappar från mamma eller pappa som har kommit fram.
  _hejaropKort() {
    if (this._s.kan_valja) return "";
    return (this._s.data.hejarop || []).map((h) => `<div class="card heja-kort">
      <div class="heja-ikon">💌</div>
      <div class="heja-text"><div class="small">Från ${esc(h.av || "mamma eller pappa")}</div><div class="heja-lapp">${esc(h.text)}</div>
      <button class="primary" data-heja-las="${h.id}">❤️ Tack!${h.boost ? ` (+${h.boost} ⭐)` : ""}</button></div></div>`).join("");
  }

  // Föräldern skickar hejarop: direkt, ett visst datum eller när barnet når en svit.
  _hejaropForalder() {
    const s = this._s, lista = (s.data.hejarop || []).slice().reverse();
    const status = (h) => h.last ? `✅ läst ${esc(h.last.replace("T", " "))}` : h.nar === "datum" ? `📅 kommer ${esc(h.varde)}` : h.nar === "svit" ? `🔥 kommer vid ${h.varde} dagar i rad` : "⏳ visas nästa gång";
    return `<h3>💌 Hejarop till ${esc(s.namn)}</h3>
      <p class="small muted">En lapp som dyker upp hos ${esc(s.namn)}. Skicka med ⭐ om du vill.</p>
      <div class="card"><textarea id="heja-text" rows="2" maxlength="300" placeholder="t.ex. Heja dig på provet imorgon! ❤️"></textarea>
        <div class="heja-val">
          <label class="small">När <select id="heja-nar"><option value="nu">Nästa gång appen öppnas</option><option value="datum">Ett visst datum</option><option value="svit">När ${esc(s.namn)} pluggat X dagar i rad</option></select></label>
          <input id="heja-varde" style="display:none">
          <label class="small">Bonus <select id="heja-boost"><option value="0">Ingen</option><option value="5">+5 ⭐</option><option value="10">+10 ⭐</option><option value="20">+20 ⭐</option></select></label>
        </div>
        <button class="primary" id="heja-skicka">💌 Skicka</button></div>
      ${lista.length ? `<div class="list">${lista.slice(0, 8).map((h) => `<div class="row static"><span>${esc(h.text)}<br><span class="muted small">${status(h)}${h.boost ? ` · +${h.boost} ⭐` : ""}</span></span>
        <button class="mini" data-heja-bort="${h.id}">🗑️</button></div>`).join("")}</div>` : ""}`;
  }

  // Dagens hälsning, veckans händelse och dagens gåta (svaret kommer i morgon).
  _dagensKort() {
    const g = this._s.dagens, h = this._s.handelse;
    if (!g) return "";
    const barn = !this._s.kan_valja;
    const ig = g.igar;
    let igar = "";
    if (ig.visad) igar = `<div class="gata-igar">🔓 Gårdagens gåta: <i>${esc(ig.gata)}</i><br>Svar: <b>${esc(ig.svar)}</b>${ig.gissning ? ` · du gissade ”${esc(ig.gissning)}” ${ig.ratt ? `✅ Rätt! +${g.p_gata} ⭐` : "❌"}` : ""}</div>`;
    else if (barn) igar = `<button class="mini" id="gata-visa">🔓 Se svaret på gårdagens gåta${ig.gissning ? " (du gissade!)" : ""}</button>`;
    const fraga = g.gissning
      ? `<div class="small">Din gissning: <b>${esc(g.gissning)}</b> · svaret kommer i morgon 🤫 ${barn ? `<button class="mini" id="gata-andra">Ändra</button>` : ""}</div>`
      : barn ? `<div class="gata-rad"><input id="gata-svar" maxlength="60" placeholder="Din gissning…"><button class="mini primary" id="gata-gissa">Gissa</button></div>`
      : `<div class="small muted">Barnet har inte gissat än.</div>`;
    return `<div class="card dagens-kort">
      <div class="dagens-halsning">🌞 ${esc(g.halsning)}</div>
      ${h ? `<div class="handelse"><b>${h.ikon} ${esc(h.namn)}</b> · ${esc(h.info)}</div>` : ""}
      <div class="gata"><div class="gata-rubrik">🧩 Dagens gåta</div><div class="gata-fraga">${esc(g.gata)}</div>${this._gataAndra ? `<div class="gata-rad"><input id="gata-svar" maxlength="60" value="${esc(g.gissning)}"><button class="mini primary" id="gata-gissa">Spara</button></div>` : fraga}
      <div class="small muted">Rätt svar ger +${g.p_gata} ⭐ när du öppnar svaret i morgon.</div></div>
      ${igar}</div>`;
  }

  // ---------- glosstrid: svara rätt på glosor för att attackera kartans monster ----------
  _glosstridView() {
    const v = this._view, s = this._s, k = s.karta, d = s.meriter?.djur;
    if (!k || !d) return `<p class="muted">Du behöver ett husdjur och kartan först.</p>`;
    if (!v.glosor) { // välj lista
      const listor = (s.data.amnen || []).flatMap((a) => a.glosor.filter((g) => spelbaraPar(g).length >= 3).map((g) => ({ a, g })));
      return `<p class="small muted">Välj en lista. Varje rätt svar är en attack mot ${esc(k.monster.namn)} ${k.monster.ikon}, och ${GS.kombo} rätt i rad ger dubbel skada!</p>
        <div class="list">${listor.map(({ a, g }) => `<button class="row" data-gs-lista="${a.id}|${g.id}"><span><b>${esc(g.namn)}</b><br><span class="muted small">${esc(a.namn)} · ${spelbaraPar(g).length} ord</span></span><span>⚔️</span></button>`).join("")
          || `<p class="muted">Lägg in glosor, formler eller begrepp först.</p>`}</div>`;
    }
    const a = this._amne(v.amne), g = a?.glosor.find((x) => x.id === v.glosor);
    if (!g) return `<p class="muted">Listan finns inte.</p>`;
    if (!v.gs) {
      const idx = g.par.map((p, i) => i).filter((i) => g.par[i].length > 1 && String(g.par[i][0]).trim() && String(g.par[i][1]).trim());
      for (let i = idx.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
      const typ = gTyp(g);
      v.gs = { ordning: idx, pos: 0, r: idx.map(() => (typ === "begrepp" ? 1 : typ === "formler" ? 0 : Math.random() < 0.5 ? 0 : 1)),
        kombo: 0, ratt: 0, skada: 0, ord: [], hp: k.hp, kvar: Math.max(0, k.hp - k.skada), liv: k.liv, liv_max: k.liv_max, mon: k.monster, senaste: null };
    }
    const gs = v.gs, mon = gs.mon;
    const bar = (x, mx, kl) => `<div class="progress ${kl}"><div style="width:${mx ? Math.round((x / mx) * 100) : 0}%"></div></div>`;
    const sen = gs.senaste, ny = sen && gs.animId !== gs.visadAnim; // animationen spelas bara en gång per svar
    if (ny) gs.visadAnim = gs.animId;
    const kombo = gs.kombo >= GS.kombo;
    const skott = kombo ? "🔥" : ["✨", "⚡", "💫", "⭐"][gs.pos % 4];
    const scen = `<div class="gs-scen ${kombo ? "kombo" : ""} ${ny && sen?.ratt && kombo ? "skak" : ""}" style="--varld:${k.monster.varld?.farg || "#5c6bc0"}">
      ${ny && sen?.ratt && sen.skada ? `<div class="gs-skott">${skott}</div><div class="gs-siffra ${kombo ? "stor" : ""}">−${sen.skada}</div>` : ""}
      ${ny && sen && !sen.ratt ? `<div class="gs-blixt"></div>` : ""}
      <div class="gs-sida"><div class="gs-figur ${ny && sen && !sen.ratt ? "traffad" : ""} ${ny && sen?.ratt ? "skjuter" : ""}">${ritaDjur(d.art, sen && !sen.ratt ? "ledsen" : "glad", Math.max(1, d.steg), { form: d.form })}</div>${bar(gs.liv, gs.liv_max, "liv")}<div class="small">❤️ ${gs.liv}/${gs.liv_max}</div></div>
      <div class="gs-mitt">${sen ? (sen.ratt ? `<div class="gs-traff">${kombo ? "🔥 KOMBO" : "TRÄFF!"}${sen.trott ? "<small>Monstret är trött på glosor idag</small>" : ""}</div>` : `<div class="gs-miss">💥 −${sen.mot} ❤️</div>`) : "⚔️"}</div>
      <div class="gs-sida"><div class="gs-figur mon ${ny && sen?.ratt ? "traff" : ""} ${ny && sen && !sen.ratt ? "anfall" : ""}">${mon.ikon}</div>${bar(gs.kvar, gs.hp, "boss-hp")}<div class="small">${mon.boss ? "👑 " : ""}${esc(mon.namn)} · ${gs.kvar}/${gs.hp}</div></div></div>
      <div class="gs-kombo">${gs.kombo ? `🔥 ${gs.kombo} i rad${gs.kombo >= GS.kombo ? " · dubbel skada!" : ` · ${GS.kombo - gs.kombo} till kombo`}` : "&nbsp;"}</div>`;
    if (gs.klar) {
      return `${scen}<div class="card center"><h3>${gs.niva_klar ? "🎉 Du klarade nivån!" : "Bra kämpat! 💪"}</h3>
        <p>${gs.ratt} av ${gs.ordning.length} rätt · ⚔️ ${gs.skada} skada på monstren</p>
        <div class="actions"><button class="primary" id="gs-igen">⚔️ En gång till</button><button class="ghost" id="gs-klar">Klar</button></div></div>`;
    }
    const i = gs.ordning[gs.pos], r = gs.r[gs.pos], fraga = g.par[i][r];
    const sprak = (g.sprak || LISTTYP[gTyp(g)]?.sprak || ["", ""])[1 - r];
    return `${scen}
      <div class="card gs-fraga-kort"><div class="small muted">Ord ${gs.pos + 1} av ${gs.ordning.length}${sprak ? ` · svara på ${esc(sprak).toLowerCase()}` : ""}</div>
        <div class="gs-fraga">${esc(fraga)}</div>
        ${gs.visaFacit ? `<div class="gs-facit">Rätt svar: <b>${esc(gs.visaFacit)}</b></div><button class="primary" id="gs-nasta">Nästa ›</button>`
          : `<div class="gata-rad"><input id="gs-svar" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Ditt svar…"><button class="primary" id="gs-skicka" ${this._busy ? "disabled" : ""}>⚔️ Attack</button></div>`}</div>`;
  }

  async _glosstridSvar() {
    const v = this._view, gs = v.gs, inp = this.shadowRoot.querySelector("#gs-svar");
    const svar = (inp?.value || "").trim();
    if (!svar || this._gsVantar) return;
    this._gsVantar = true;
    const i = gs.ordning[gs.pos], r = gs.r[gs.pos];
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/glosstrid", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, amne: v.amne, glosor: v.glosor, i, r, svar }) });
      const x = await res.json();
      if (!res.ok) throw new Error(x.message || res.statusText);
      const g = this._amne(v.amne).glosor.find((y) => y.id === v.glosor);
      gs.ord.push({ o: g.par[i][0], r: x.ratt });
      gs.senaste = x;
      gs.animId = (gs.animId || 0) + 1;
      if (x.ratt) gs.ratt++;
      if (x.niva_klar) this._fx({ text: "🎉 NIVÅ KLAR!", sub: "Monstret är besegrat!", emojis: ["⭐", "🎉", "⚔️", "✨"], antal: 36, konfetti: true, farg: "#ffb300", ljud: true });
      else if (x.ratt && x.kombo === GS.kombo) this._fx({ text: "🔥 KOMBO!", sub: "Dubbel skada!", emojis: ["🔥", "💥", "⚡"], antal: 24, farg: "#ff5722" });
      if (!x.prov) {
        gs.kombo = x.kombo; gs.skada += x.skada || 0; gs.liv = x.liv; gs.liv_max = x.liv_max; gs.niva_klar = gs.niva_klar || x.niva_klar;
        gs.hp = x.hp; gs.kvar = x.kvar; gs.mon = { ...gs.mon, ...x.mon };
      } else gs.kombo = x.ratt ? gs.kombo + 1 : 0;
      if (x.ratt) this._gsNasta(); else { gs.visaFacit = x.facit; this._render(); }
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      this._render();
    } finally {
      this._gsVantar = false;
    }
  }

  _gsNasta() {
    const v = this._view, gs = v.gs;
    gs.visaFacit = null;
    gs.pos++;
    if (gs.pos >= gs.ordning.length) {
      gs.klar = true;
      // räknas som en vanlig övning (meriter och svit)
      this._act("ova_resultat", { amne: v.amne, glosor: v.glosor, ratt: gs.ratt, av: gs.ordning.length, ord: gs.ord }).then(() => this._load(this._s.barn));
    }
    this._render();
    setTimeout(() => this.shadowRoot.querySelector("#gs-svar")?.focus(), 30);
  }

  _hem() {
    const amnen = this._s.data.amnen || [];
    return `
      ${this._s.kan_valja ? `<button class="row foralder-knapp" id="open-foralder"><span>⚙️ <b>Föräldrar</b><br><span class="muted small">Läxschema, bonus och belöningsbutik för ${esc(this._s.namn)}</span></span><span>›</span></button>` : ""}
      ${this._fodelsedagKort()}
      ${this._skolinfoKort()}
      ${this._julKort()}
      ${this._kistKort()}
      ${this._nyaKort()}
      ${this._laxfragaKort()}
      ${this._materialKort()}
      ${this._hejaropKort()}
      ${this._dagensListaKort()}
      ${this._dagensKort()}
      ${this._syskonKort()}
      ${this._repeteraKort()}
      ${this._forhorLista()}
      ${this._djurKort()}
      ${this._provbossKort()}
      ${this._utmaningKort()}
      ${this._passKort()}
      ${this._nivaKort()}
      ${this._meritKort()}
      <button class="info-lank" id="open-info">ℹ️ Så funkar meriter och tävlingen ›</button>
      ${this._uppdragLista()}
      <h3>📚 Ämnen</h3>
      <button class="row" id="open-lektioner"><span>🗓️ <b>${this._s.kan_valja ? `${esc(this._s.namn)}s schema` : "Mitt schema"}</b><br><span class="muted small">${this._s.kan_valja ? (this._s.lektioner?.length ? "Lektionerna i veckan" : "Fota schemat så läser AI:n av lektioner och ämnen") : this._s.lektioner?.length ? "Dina lektioner i veckan, sök och skriv ut" : "Be mamma eller pappa fota ditt schema"}</span></span><span>›</span></button>
      <div class="grid">
        ${amnen
          .map(
            (a) => `
          <button class="card amne" style="--c:${a.farg}" data-open-amne="${a.id}">
            <div class="amne-namn">${esc(a.namn)}</div>
            <div class="muted small">${esc(amneRad(a))}</div>
          </button>`
          )
          .join("")}
        <button class="card add" id="add-amne">＋ Nytt ämne</button>
      </div>
      ${amnen.length ? "" : `<p class="muted">Börja med att skapa ett ämne, till exempel Engelska eller Matte.</p>`}`;
  }

  _amneFormView() {
    const v = this._view;
    const a = v.amne ? this._amne(v.amne) : null;
    const innehall = (id) => {
      if (!a) return 0;
      if (id === "bocker") return a.bocker.length;
      if (LISTTYP[id]) return a.glosor.filter((g) => gTyp(g) === id).length;
      if (id === "uppgifter") return (a.uppgifter || []).length;
      if (id === "anteckningar") return a.anteckningar?.trim() ? 1 : 0;
      return 0;
    };
    return `
      <div class="form">
        <label>Vad heter ämnet? <input id="af-namn" value="${esc(v.namn || "")}" placeholder="t.ex. Matte, Engelska, SO" maxlength="40"></label>
      </div>
      <p class="small muted">${a ? "Välj vad ämnet ska innehålla." : "Vad tror du att ämnet kommer att innehålla? Det går att ändra sen."}</p>
      <div class="list">
        ${DELAR.map((d) => {
          const pa = v.delar.includes(d.id);
          const n = innehall(d.id);
          return `<label class="row del-val ${pa ? "vald-rad" : ""}"><span>${d.ikon} <b>${esc(d.namn)}</b><br><span class="muted small">${esc(d.besk)}${
            n && !pa ? (LISTTYP[d.id] ? " · har innehåll, visas så länge det finns kvar" : " · har innehåll som sparas och kommer tillbaka om du slår på den igen") : ""}</span></span>
            <input type="checkbox" data-del="${d.id}" ${pa ? "checked" : ""}></label>`;
        }).join("")}
      </div>
      <div class="actions">
        <button class="primary" id="af-spara" ${this._busy ? "disabled" : ""}>${a ? "Spara" : "Skapa ämnet"}</button>
      </div>`;
  }

  _listSektion(a, typ) {
    const lt = LISTTYP[typ];
    const d = DELAR.find((x) => x.id === typ);
    const listor = a.glosor.filter((g) => gTyp(g) === typ);
    return `
      <h3>${d.ikon} ${esc(d.namn)}</h3>
      <div class="list">
        ${[...listor]
          .sort((x, y) => {
            // kommande förhör först (närmast överst), sen listor utan datum, sist gamla förhör
            const v = (g) => { const f = forhorInfo(g.forhor)?.dagar; return f == null ? 9000 : f < 0 ? 9500 - f : f; };
            return v(x) - v(y);
          })
          .map((g) => {
            const last = (g.resultat || []).slice(-1)[0];
            const f = forhorInfo(g.forhor);
            const snart = f && f.dagar >= 0 && f.dagar <= 3;
            return `<button class="row ${snart ? "snart" : ""}" data-open-glosor="${g.id}">
              <span>${lt.ikon} ${esc(g.namn)}${f && f.dagar >= 0 ? `<br><span class="small forhor">📅 Förhör ${esc(f.text)} · ${f.kvar}</span>` : ""}</span>
              <span class="muted small">${g.par.length} ${g.par.length === 1 ? lt.en : lt.fler}${last ? ` · senast ${last.ratt}/${last.av}` : ""} ›</span></button>`;
          })
          .join("")}
        <button class="row add" data-add-lista="${typ}">${lt.ny}</button>
      </div>`;
  }

  _uppgiftSektion(a) {
    const u = a.uppgifter || [];
    const kvar = u.filter((x) => !x.klar).sort((x, y) => (x.datum || "9999").localeCompare(y.datum || "9999"));
    const klara = u.filter((x) => x.klar).sort((x, y) => y.klar.localeCompare(x.klar));
    const visaKlara = this._view.allaKlara ? klara : klara.slice(0, 3);
    const rad = (x) => {
      const f = x.datum && !x.klar ? forhorInfo(x.datum) : null;
      return `<div class="row static uppg ${x.klar ? "klar" : f && f.dagar >= 0 && f.dagar <= 1 ? "snart" : ""}">
        <label class="uppg-text"><input type="checkbox" data-uppg-klar="${x.id}" ${x.klar ? "checked" : ""}>
          <span>${esc(x.text)}${f ? `<br><span class="small ${f.dagar < 0 ? "danger-text" : "forhor"}">📅 ${esc(f.text)} · ${f.dagar < 0 ? "försenad" : f.kvar}</span>` : ""}</span></label>
        <button class="mini danger" data-uppg-bort="${x.id}" title="Ta bort">✕</button></div>`;
    };
    return `
      <h3>✅ Uppgifter</h3>
      <div class="list">
        ${kvar.map(rad).join("") || `<div class="row static muted small">Inga uppgifter kvar 🎉</div>`}
        ${visaKlara.map(rad).join("")}
        ${klara.length > 3 ? `<button class="row add" id="uppg-alla">${this._view.allaKlara ? "Visa färre" : `Visa alla klara (${klara.length})`}</button>` : ""}
      </div>
      <div class="uppg-ny">
        <input id="uppg-text" placeholder="Ny uppgift, t.ex. Räkna s. 34 uppg. 1–10" maxlength="200" value="${esc(this._view.uppgUtkast || "")}">
        <input id="uppg-datum" type="date" title="Klar senast (valfritt)">
        <button class="primary" id="uppg-add" ${this._busy ? "disabled" : ""}>＋</button>
      </div>`;
  }

  _amneView(a) {
    const d = delarFor(a);
    const del = {
      bocker: () => `
      <h3>📚 Böcker</h3>
      <div class="hylla">
        ${a.bocker
          .map(
            (b) => `<button class="bok-tile" data-open-bok="${b.id}">
              ${b.framsida ? `<img data-fil="${esc(b.framsida)}" alt="">` : `<div class="bok-utan">📖</div>`}
              <div class="bok-namn">${esc(b.namn)}</div>
              <div class="muted small">${b.ebok ? "📘 Tryck för att läsa" : `${b.sidor.length} sid${b.sidor.length === 1 ? "a" : "or"}`}</div>
            </button>`
          )
          .join("")}
        <button class="bok-tile add" id="add-bok"><div class="bok-utan">＋</div><div class="bok-namn">Ny bok</div></button>
      </div>`,
      glosor: () => this._listSektion(a, "glosor"),
      formler: () => this._listSektion(a, "formler"),
      begrepp: () => this._listSektion(a, "begrepp"),
      uppgifter: () => this._uppgiftSektion(a),
      anteckningar: () => `
      <h3>🗒️ Anteckningar</h3>
      <textarea id="ant-text" class="anteckning" rows="6" maxlength="10000" placeholder="Skriv det du vill komma ihåg…">${esc(this._view.antUtkast ?? a.anteckningar ?? "")}</textarea>
      <div class="actions"><button class="primary" id="ant-spara" ${this._busy ? "disabled" : ""}>Spara anteckningarna</button></div>`,
    };
    // Listor i delar som är avslagna syns ändå om det finns något i dem, så inget försvinner.
    const gomda = Object.keys(LISTTYP).filter((typ) => !d.includes(typ) && a.glosor.some((g) => gTyp(g) === typ));
    return `
      ${d.map((id) => del[id]()).join("")}
      ${gomda.map((typ) => this._listSektion(a, typ)).join("")}
      <div class="actions">
        <button class="ghost" id="edit-amne">✏️ Redigera ämnet</button>
        <button class="ghost danger" id="del-amne">Ta bort ämnet</button>
      </div>`;
  }

  _omslagSlot(b, sida, rubrik, red) {
    const f = b[sida === "fram" ? "framsida" : "baksida"];
    if (!red) return f ? `<div class="omslag"><div class="small muted">${rubrik}</div><img data-fil="${esc(f)}" data-open-fil="${esc(f)}" alt="${rubrik}"></div>` : "";
    return `
      <div class="omslag">
        <div class="small muted">${rubrik}</div>
        ${
          f
            ? `<img data-fil="${esc(f)}" data-open-fil="${esc(f)}" alt="${rubrik}">
               <div class="page-bar">
                 <label class="mini">Byt<input type="file" data-omslag="${sida}" accept="image/*" hidden></label>
                 <button class="mini danger" data-del-omslag="${sida}" title="Ta bort">✕</button>
               </div>`
            : `<label class="omslag-tom">📷<span>Fota ${rubrik.toLowerCase()}</span><input type="file" data-omslag="${sida}" accept="image/*" hidden></label>`
        }
      </div>`;
  }

  _ebokKort(b, red) {
    const j = this._jobb?.[b.id];
    if (j?.kor) {
      const pct = j.av ? (j.klar / j.av) * 100 : 0;
      return `<div class="ebok-kort">
        <div><b>📘 AI:n gör e-boken…</b></div>
        <div class="progress"><div style="width:${pct}%"></div></div>
        <div class="muted small">${j.steg === "kapitel" ? "Läser innehållsförteckningen…" : j.av ? `Sida ${Math.min(j.klar + 1, j.av)} av ${j.av}` : "Startar…"} · du kan lämna sidan under tiden</div>
      </div>`;
    }
    const klara = new Set(b.ebok?.filer || []);
    const nya = b.sidor.filter((f) => !klara.has(f)).length;
    if (!b.ebok) {
      return `<div class="ebok-kort">
        <div><b>📘 E-bok</b></div>
        <div class="muted small">AI:n går igenom fotona och gör en e-bok med sidnummer, kapitel, innehållsförteckning och en kort förklaring till varje sida.</div>
        <button class="primary" id="gor-ebok" ${b.sidor.length ? "" : "disabled"}>Gör e-bok av ${b.sidor.length} sid${b.sidor.length === 1 ? "a" : "or"}</button>
        ${j?.fel ? `<div class="msg error">${esc(j.fel)}</div>` : ""}
      </div>`;
    }
    if (!red) return `<button class="primary stor-las" id="las-ebok">📘 Läs</button>`;
    return `<div class="ebok-kort">
      <div><b>📘 E-bok</b></div>
      <div class="actions">
        ${nya ? `<button class="ghost" id="gor-ebok">Lägg till ${nya} ny${nya === 1 ? "" : "a"} sid${nya === 1 ? "a" : "or"} i e-boken</button>` : !b.ebok.toc_kollad ? `<button class="ghost" id="gor-ebok">📑 Hämta kapitel</button>` : ""}
        <button class="ghost" id="gor-om-ebok">Gör om hela e-boken</button>
      </div>
    </div>`;
  }

  async _ebokStatus(bokId) {
    const v = this._view;
    try {
      const res = await this._hass.fetchWithAuth(
        `/api/skolan/ebok?bara_status=1&barn=${encodeURIComponent(this._s.barn)}&bok=${encodeURIComponent(bokId)}`
      );
      const body = await res.json();
      const forr = this._jobb?.[bokId]?.kor;
      this._jobb = { ...(this._jobb || {}), [bokId]: body.jobb };
      if (forr && !body.jobb?.kor) {
        await this._load();
        if (!body.jobb?.fel) this._msg = { type: "ok", text: "E-boken är klar! 📘" };
      }
      if (this._view === v) this._render();
      if (body.jobb?.kor) {
        clearTimeout(this._poll);
        this._poll = setTimeout(() => {
          if (this._view.name === "bok" && this._view.bok === bokId) this._ebokStatus(bokId);
        }, 3000);
      }
    } catch (e) {
      /* försök igen när sidan öppnas */
    }
  }

  async _ebokStarta(gorOm) {
    const v = this._view;
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/ebok", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, amne: v.amne, bok: v.bok, gor_om: gorOm }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      this._jobb = { ...(this._jobb || {}), [v.bok]: body.jobb };
      this._render();
      this._ebokStatus(v.bok);
    } catch (e) {
      this._msg = { type: "error", text: e.message || String(e) };
      this._render();
    }
  }

  async _ebokOppna(amne, bok, startNyckel = null, uppdrag = null) {
    const v = { amne: amne || this._view.amne, bok: bok || this._view.bok };
    this._busy = true;
    this._render();
    try {
      const res = await this._hass.fetchWithAuth(
        `/api/skolan/ebok?barn=${encodeURIComponent(this._s.barn)}&amne=${encodeURIComponent(v.amne)}&bok=${encodeURIComponent(v.bok)}`
      );
      const body = await res.json();
      if (!res.ok) throw new Error(body.message || res.statusText);
      let idx = 0;
      try { idx = Number(localStorage.getItem(`skolan-ebok-${v.bok}`)) || 0; } catch (e) { /* ok */ }
      if (startNyckel) {
        const i = body.sidor.findIndex((x) => `${x.fil}#${x.del}` === startNyckel);
        if (i >= 0) idx = i;
      }
      this._busy = false;
      this._go({ name: "ebok", amne: v.amne, bok: v.bok, uppdrag, e: { sidor: body.sidor, fel: body.fel, toc: body.toc, idx: Math.min(idx, Math.max(0, body.sidor.length - 1)), visaToc: false } });
    } catch (e) {
      this._busy = false;
      this._msg = { type: "error", text: e.message || String(e) };
      this._render();
    }
  }

  _ebokView(b) {
    const e = this._view.e;
    if (!e.sidor.length) return `<p class="muted">E-boken är tom. AI:n kunde inte läsa några sidor.</p>`;
    const t = toc(e.sidor, e.toc);
    const s = e.sidor[e.idx];
    const kap = [...t].reverse().find((x) => x.niva === 1 && x.idx <= e.idx);
    const sidLabel = s.sidnr ? `Sida ${esc(s.sidnr)}` : `Sida ${e.idx + 1}`;
    if (e.visaToc) {
      const q = norm(e.sok || "");
      const traffar = q
        ? e.sidor
            .map((x, idx) => ({ x, idx }))
            .filter(({ x, idx }) => norm([kapFor(t, idx), x.kapitel, ...(x.rubriker || []), x.sammanfattning, x.sidnr].join(" ")).includes(q))
        : [];
      return `
        <input id="ebok-sok" class="sok" type="search" placeholder="🔍 Sök kapitel, rubrik, ord eller sidnummer" value="${esc(e.sok || "")}" autocomplete="off">
        ${
          q
            ? `<div class="toc"><h3>${traffar.length} träff${traffar.length === 1 ? "" : "ar"}</h3>${traffar
                .map(
                  ({ x, idx }) => `<button class="toc-rad sok-rad" data-ga="${idx}"><span><b>${esc(kapFor(t, idx) || x.kapitel || (x.rubriker || [])[0] || "Sida")}</b><br><span class="muted small">${esc(x.sammanfattning || "")}</span></span><span class="muted small">${esc(x.sidnr || idx + 1)}</span></button>`
                )
                .join("")}</div>`
            : ""
        }
        <div class="toc" ${q ? 'style="display:none"' : ""}>
          <h3>📑 Innehåll</h3>
          ${t.length ? t.map((x) => `<button class="toc-rad niva${x.niva}" data-ga="${x.idx}"><span>${esc(x.text)}</span><span class="muted small">${esc(e.sidor[x.idx].sidnr || x.idx + 1)}</span></button>`).join("") : `<p class="muted">Inga kapitelrubriker hittades.</p>`}
        </div>
        <div class="actions"><button class="ghost" id="stang-toc">Tillbaka till sidan</button></div>`;
    }
    const nyckel = `${s.fil}#${s.del}`;
    const mina = (this._s.data.uppdrag || []).filter((u) => !u.klart && u.bok === b.id && !["hogl", "skriv"].includes(u.typ) && u.sidor.some((x) => x.nyckel === nyckel));
    const aktuell = (this._s.data.uppdrag || []).find((u) => u.id === this._view.uppdrag) || mina[0];
    let banner = "";
    if (aktuell && ["hogl", "skriv"].includes(aktuell.typ)) {
      const dagIdag = aktuell.typ === "hogl" && !this._s.kan_valja && (aktuell.dagar || []).find((d) => d.datum === idagISO());
      const kanSpela = dagIdag && !["ok", "vantar"].includes(dagIdag.status);
      banner = `<div class="las-banner"><div>${TYP_IKON[aktuell.typ]} <b>${esc(aktuell.namn)}</b>${aktuell.kapitel ? `: ${esc(aktuell.kapitel)}` : ""}${aktuell.fran ? ` · s. ${esc(aktuell.fran)}${aktuell.till && aktuell.till !== aktuell.fran ? `–${esc(aktuell.till)}` : ""}` : ""}</div>
        ${kanSpela ? this._inspRuta(aktuell) : ""}
        <button class="ghost" id="till-uppdrag">← Tillbaka till läxan</button></div>`;
    } else if (aktuell && !aktuell.klart) {
      const sek = this._lasSek(b.id, nyckel);
      const iUppdrag = aktuell.sidor.some((x) => x.nyckel === nyckel);
      const behov = aktuell.sidor.find((x) => x.nyckel === nyckel)?.sek || 20;
      banner = `<div class="las-banner">
        <div>${aktuell.typ === "prov" ? "📝" : "📖"} <b>${esc(aktuell.namn)}</b>: ${aktuell.lasta} av ${aktuell.sidor.length} sidor lästa</div>
        <div class="progress"><div style="width:${(aktuell.lasta / aktuell.sidor.length) * 100}%"></div></div>
        ${
          aktuell.allt_last
            ? `<button class="primary" id="till-uppdrag">✅ Alla sidor lästa! Gör kontrollfrågorna →</button>`
            : iUppdrag
            ? `<div class="small">${sek >= behov ? "✓ Den här sidan är läst" : "⏱ Läs sidan ordentligt, den räknas efter en stund"}</div>`
            : `<div class="small muted">Den här sidan ingår inte i läxan (sidorna ${esc(aktuell.fran)}–${esc(aktuell.till)}).</div>`
        }
      </div>`;
    }
    const doljSammanf = !this._s.kan_valja && mina.length > 0;
    return `
      ${banner}
      <div class="ebok-bar">
        <button class="ghost" id="visa-toc">📑 Innehåll</button>
        <span class="muted small kap">${kap ? esc(kap.text) : ""}</span>
        <button class="ghost" id="bok-meny" title="Skriv ut och ändra">⚙️</button>
      </div>
      <div class="ebok-sida">
        ${t.filter((x) => x.niva === 1 && x.idx === e.idx).map((x) => `<div class="ebok-kapitel">${esc(x.text)}</div>`).join("")}
        ${
          s.fil.toLowerCase().endsWith(".pdf")
            ? `<button class="pdf" data-open-fil="${esc(s.fil)}">📄 Öppna PDF:en</button>`
            : `<img data-fil="${esc(s.fil)}" data-open-fil="${esc(s.fil)}" alt="${sidLabel}"><div class="muted small center" style="margin-top:6px">🔍 Tryck på sidan för att förstora</div>`
        }
        ${s.sammanfattning && !doljSammanf ? `<details class="om-sidan"><summary>💡 Vad handlar sidan om?</summary><p>${esc(s.sammanfattning)}</p></details>` : ""}
      </div>
      <div class="ebok-nav">
        <button class="ghost" id="ebok-fore" ${e.idx === 0 ? "disabled" : ""}>←</button>
        <div class="center"><div>${sidLabel}</div><div class="muted small">${e.idx + 1} av ${e.sidor.length}</div></div>
        <button class="ghost" id="ebok-nasta" ${e.idx >= e.sidor.length - 1 ? "disabled" : ""}>→</button>
      </div>
      ${e.fel?.length ? `<p class="muted small center">${e.fel.length} foto kunde inte läsas. Gå tillbaka och välj "Gör e-bok" för att försöka igen.</p>` : ""}`;
  }

  // Egen zoom i bildvisningen (Home Assistant-appen stänger av telefonens nyp-zoom)
  _zoomViewer(vw) {
    if (!vw) return;
    const img = vw.querySelector("img");
    let s = 1, x = 0, y = 0, start = null, senastTryck = 0, flyttat = false;
    const satt = (anim) => {
      img.style.transition = anim ? "transform .2s" : "none";
      img.style.transform = `translate(${x}px, ${y}px) scale(${s})`;
    };
    // Zooma till ny skala med punkten (px, py) på skärmen still
    const zooma = (ns, px, py, s0 = s, x0 = x, y0 = y) => {
      ns = Math.max(1, Math.min(6, ns));
      const L = img.offsetLeft, T = img.offsetTop;
      const u = (px - L - x0) / s0, w = (py - T - y0) / s0;
      s = ns; x = px - L - s * u; y = py - T - s * w;
      if (s === 1) { x = 0; y = 0; }
    };
    const mitt = (t) => [(t[0].clientX + t[1].clientX) / 2, (t[0].clientY + t[1].clientY) / 2];
    const avst = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    vw.addEventListener("touchstart", (e) => {
      if (e.target.closest("button")) return;
      flyttat = false;
      if (e.touches.length === 2) {
        const [mx, my] = mitt(e.touches);
        start = { pinch: true, d: avst(e.touches), s, x, y, mx, my };
      } else if (e.touches.length === 1) {
        start = { pinch: false, px: e.touches[0].clientX, py: e.touches[0].clientY, x, y };
      }
    }, { passive: true });
    vw.addEventListener("touchmove", (e) => {
      if (!start) return;
      e.preventDefault();
      flyttat = true;
      if (start.pinch && e.touches.length === 2) {
        const [mx, my] = mitt(e.touches);
        zooma(start.s * avst(e.touches) / start.d, start.mx, start.my, start.s, start.x, start.y);
        x += mx - start.mx; y += my - start.my;
        if (s === 1) { x = 0; y = 0; }
      } else if (!start.pinch && e.touches.length === 1 && s > 1) {
        x = start.x + e.touches[0].clientX - start.px;
        y = start.y + e.touches[0].clientY - start.py;
      }
      satt(false);
    }, { passive: false });
    vw.addEventListener("touchend", (e) => {
      if (e.touches.length) { start = null; return; }
      if (flyttat && start && !start.pinch && s === 1 && this._viewerEbok) {
        const dx = e.changedTouches[0].clientX - start.px, dy = e.changedTouches[0].clientY - start.py;
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) this._viewerByt(dx < 0 ? 1 : -1);
      }
      if (!flyttat && start && !start.pinch) {
        const nu = Date.now();
        if (nu - senastTryck < 300) {
          if (s > 1) { s = 1; x = 0; y = 0; } else zooma(2.5, start.px, start.py);
          satt(true);
          senastTryck = 0;
        } else senastTryck = nu;
      }
      start = null;
    });
    // Datorer: dubbelklick och mushjul
    vw.addEventListener("dblclick", (e) => {
      if (e.target.closest("button")) return;
      if (s > 1) { s = 1; x = 0; y = 0; } else zooma(2.5, e.clientX, e.clientY);
      satt(true);
    });
    vw.addEventListener("wheel", (e) => {
      e.preventDefault();
      zooma(s * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
      satt(false);
    }, { passive: false });
    const knapp = (id, f) => vw.querySelector(id)?.addEventListener("click", (e) => {
      e.stopPropagation();
      zooma(s * f, vw.clientWidth / 2, vw.clientHeight / 2);
      satt(true);
    });
    knapp("#zoom-in", 1.5);
    knapp("#zoom-ut", 1 / 1.5);
  }

  async _viewerByt(steg) {
    const e = this._view.e;
    if (!e) return;
    const ni = e.idx + steg;
    if (ni < 0 || ni >= e.sidor.length) return;
    const fil = e.sidor[ni].fil;
    if (fil.toLowerCase().endsWith(".pdf")) {
      this._viewer = null;
      this._ebokGa(ni);
      return;
    }
    try {
      const url = await this._blob(fil);
      this._viewer = url;
      this._ebokGa(ni); // ritar om med nya sidan
    } catch (err) {
      this._viewer = null;
      this._msg = { type: "error", text: err.message };
      this._ebokGa(ni);
    }
  }

  _ebokGa(idx) {
    const e = this._view.e;
    e.idx = Math.max(0, Math.min(e.sidor.length - 1, idx));
    e.visaToc = false;
    try { localStorage.setItem(`skolan-ebok-${this._view.bok}`, String(e.idx)); } catch (err) { /* ok */ }
    this._render();
    this.shadowRoot.querySelector(".content")?.scrollTo?.(0, 0);
    window.scrollTo?.(0, 0);
  }

  _sidorLista(b) {
    return `<div class="sidor-innehall">
      <label class="primary upload">
        📷 Lägg till sidor (foto eller PDF)
        <input type="file" id="pages" accept="image/*,application/pdf" multiple hidden>
      </label>
      <div class="pages">
        ${b.sidor
          .map(
            (f, i) => `
          <div class="page">
            ${
              f.toLowerCase().endsWith(".pdf")
                ? `<button class="pdf" data-open-fil="${esc(f)}">📄 PDF ${i + 1}</button>`
                : `<img data-fil="${esc(f)}" data-open-fil="${esc(f)}" alt="Sida ${i + 1}">`
            }
            <div class="page-bar">
              <span class="small muted">${i + 1}</span>
              <span>
                <button class="mini" data-move="${esc(f)}" data-steg="-1" title="Flytta upp">↑</button>
                <button class="mini" data-move="${esc(f)}" data-steg="1" title="Flytta ner">↓</button>
                <button class="mini danger" data-del-sida="${esc(f)}" title="Ta bort">✕</button>
              </span>
            </div>
          </div>`
          )
          .join("")}
      </div>
    </div>`;
  }

  _bokView(a, b) {
    const val = this._view.utskrift;
    const red = (!b.sidor.length && !b.framsida && !b.baksida) || this._redigera?.[b.id];
    if (val) {
      const ruta = (key, fil, label) => `
        <button class="valj ${val.has(key) ? "vald" : ""}" data-valj="${esc(key)}">
          ${fil.toLowerCase().endsWith(".pdf") ? `<div class="pdf">📄 PDF<br><small>kan inte skrivas ut</small></div>` : `<img data-fil="${esc(fil)}" alt="${label}">`}
          <span class="bock">${val.has(key) ? "✓" : ""}</span>
          <span class="small">${label}</span>
        </button>`;
      const alla = b.sidor.length + (b.framsida ? 1 : 0) + (b.baksida ? 1 : 0);
      return `
        <div class="ut-bar">
          <button class="ghost" id="ut-avbryt">Avbryt</button>
          <button class="ghost" id="ut-alla">${val.size === alla ? "Avmarkera alla" : "Välj alla"}</button>
          <button class="primary" id="ut-skriv" ${val.size ? "" : "disabled"}>🖨️ Skriv ut ${val.size || ""}</button>
        </div>
        <div class="pages">
          ${b.framsida ? ruta("fram", b.framsida, "Framsida") : ""}
          ${b.sidor.map((f, i) => ruta(f, f, `Sida ${i + 1}`)).join("")}
          ${b.baksida ? ruta("bak", b.baksida, "Baksida") : ""}
        </div>`;
    }
    if (!red) {
      return `
        ${b.framsida ? `<img class="stort-omslag" data-fil="${esc(b.framsida)}" ${b.ebok ? 'id="omslag-las"' : `data-open-fil="${esc(b.framsida)}"`} alt="Omslag">` : ""}
        ${this._ebokKort(b, false)}
        ${this._fotoLon(b)}
        <div class="actions">
          ${b.sidor.length || b.framsida ? `<button class="ghost" id="skriv-ut">🖨️ Skriv ut</button>` : ""}
          <button class="ghost" id="redigera-bok">✏️ Redigera</button>
        </div>`;
    }
    return `
      <div class="red-bar">
        <b>✏️ Redigera boken</b>
        ${b.sidor.length || b.framsida || b.baksida ? `<button class="primary" id="redigera-klar">✓ Klar</button>` : ""}
      </div>
      <div class="omslag-rad">
        ${this._omslagSlot(b, "fram", "Framsida", true)}
        ${this._omslagSlot(b, "bak", "Baksida", true)}
      </div>
      ${b.ebok || this._jobb?.[b.id]?.kor ? this._ebokKort(b, true) : ""}
      <h3>📷 Sidor (${b.sidor.length})</h3>
      ${this._sidorLista(b)}
      ${b.sidor.length ? "" : `<p class="muted">Inga sidor än. Fota läxan och lägg till den här.</p>`}
      <div class="actions">
        <button class="ghost" id="rename-bok">Byt namn på boken</button>
        <button class="ghost danger" id="del-bok">Ta bort boken</button>
      </div>`;
  }

  _fotoLon(b) {
    // Lön för att fota boken: barnet ber om den, en förälder kollar fotona och godkänner.
    const s = this._s;
    const betalda = new Set(b.foto_betalda || []);
    const nya = (b.barn_sidor || []).filter((f) => b.sidor.includes(f) && !betalda.has(f)).length;
    const pris = Math.max(0, Math.min(Math.floor(nya / 2), 50 - (b.foto_lon || 0)));
    const v = b.foto_vantar;
    if (s.kan_valja) {
      if (!v) return b.foto_lon ? `<div class="muted small">📸 ${esc(s.namn)} har fått ${b.foto_lon} ⭐ för att fota boken.</div>` : "";
      return `<div class="forhor-kort foto-lon">📸 <b>${esc(s.namn)} har fotat ${v.sidor} nya sidor</b> och ber om lön (<b>+${pris} ⭐</b>).
        <div class="muted small">Tryck ✏️ Redigera för att se sidorna. Kolla att de är skarpa, hela och i rätt ordning.</div>
        <div class="actions" style="margin-top:6px"><button class="primary" data-foto-lon="1">👍 Godkänn</button><button class="ghost danger" data-foto-lon="0">Neka</button></div></div>`;
    }
    if (v) return `<div class="forhor-kort">⏳ Väntar på att mamma eller pappa kollar dina foton (${v.sidor} sidor).</div>`;
    if (!pris) return b.foto_lon ? `<div class="muted small">📸 Du har fått ${b.foto_lon} ⭐ för att fota boken. Tack!</div>` : "";
    if (nya < 10) return `<div class="muted small">📸 Fotar du minst 10 sidor själv kan du be om lön: 1 ⭐ per 2 sidor (du har ${nya}).</div>`;
    return `<button class="row foto-lon" id="foto-lon-be"><span>📸 <b>Jag har fotat klart, be om lön</b><br><span class="muted small">${nya} nya sidor ger +${pris} ⭐ när mamma eller pappa har kollat fotona</span></span><span>›</span></button>`;
  }

  _svara(g) {
    const s = g.svara || {};
    return g.par.map((p, i) => i).filter((i) => (s[g.par[i][0].trim().toLowerCase()] || 0) >= 2);
  }

  _glosorView(a, g) {
    const res = (g.resultat || []).slice(-5).reverse();
    const svara = new Set(this._svara(g));
    const f = forhorInfo(g.forhor);
    return `
      ${f ? `<div class="forhor-kort ${f.dagar >= 0 && f.dagar <= 3 ? "snart" : ""}">📅 Förhör <b>${esc(f.text)}</b> · ${f.kvar}</div>` : ""}
      <div class="actions top">
        <button class="primary" id="ova">▶ Öva</button>
        ${svara.size ? `<button class="primary svar-knapp" id="ova-svara">🔥 Öva svåra ord (${svara.size})</button>` : ""}
        <button class="ghost" id="edit-glosor">Ändra</button>
      </div>
      ${spelbaraPar(g).length && this._s.meriter?.djur ? `<button class="row lar-knapp" id="lar-start"><span>🎓 <b>Lär ${esc(this._s.meriter.djur.namn)}</b><br><span class="small">Förklara ${gTyp(g) === "begrepp" ? "ett begrepp" : gTyp(g) === "formler" ? "en formel" : "ett ord"} med egna ord. Den som förklarar lär sig mest!</span></span><span>›</span></button>` : ""}
      ${spelbaraPar(g).length >= 3 && this._s.karta && this._s.meriter?.djur ? `<button class="row glosstrid-knapp" id="glosstrid-start"><span>⚔️ <b>Glosstrid</b><br><span class="small">Varje rätt svar är en attack mot ${esc(this._s.karta.monster?.namn || "monstret")} ${this._s.karta.monster?.ikon || ""}</span></span><span>›</span></button>` : ""}
      ${spelbaraPar(g).length >= 4 ? `<button class="row rekord-knapp" id="rekord-start"><span>⚡ <b>Glosrekord</b><br><span class="small">Så många rätt du hinner på 60 sekunder!</span></span><span class="rekord-siffra">${g.rekord ? `🏆 ${g.rekord.poang}` : "Nytt!"}</span></button>` : ""}
      ${this._s.kan_valja ? `<button class="row skicka-forhor" id="skicka-forhor">📋 Skicka förhör till ${esc(this._s.namn)} ›</button>
        <button class="row skicka-forhor" id="man-forhor">🗣️ Registrera förhör gjort muntligt/på papper ›</button>
        ${(g.papper_vantar || []).map((d) => `<div class="forhor-kort">✍️ ${esc(this._s.namn)} säger att hen övat på papper <b>${esc(veckodag(d))}</b>.
          <div class="actions" style="margin-top:6px"><button class="primary" data-godkann-glosor="${d}" data-ok="1">👍 Godkänn</button><button class="ghost danger" data-godkann-glosor="${d}" data-ok="0">Neka</button></div></div>`).join("")}
        ${this._dagValjare("✍️ Övat på papper (t.ex. i glosboken)", [...(g.ovat_dagar || []), ...(g.papper_vantar || [])], g.forhor ? (d) => d < g.forhor : () => true, "data-man-ova", { attr: "data-angra-ova", dagar: g.ovat_dagar || [] })}` : (() => {
          const idag = idagISO();
          if ((g.ovat_dagar || []).includes(idag)) return "";
          if ((g.papper_vantar || []).includes(idag)) return `<div class="forhor-kort">⏳ Väntar på att mamma eller pappa godkänner din övning på papper.</div>`;
          return `<button class="row skicka-forhor" id="ova-papper">✍️ Jag har övat på papper idag ›</button>`;
        })()}
      <table class="glos">
        <tr><th>${esc(g.sprak[0] || "Ord")}</th><th>${esc(g.sprak[1] || "Översättning")}</th>${gTyp(g) !== "formler" ? "<th></th>" : ""}</tr>
        ${g.par.map((p, i) => `<tr><td>${svara.has(i) ? "🔥 " : ""}${esc(p[0])}</td><td>${esc(p[1])}</td>${gTyp(g) !== "formler"
          ? `<td class="ex-knapp"><button class="mini" data-exempel="${i}" title="Visa en exempelmening">💬</button></td>` : ""}</tr>
          ${this._exVisa?.has(`${g.id}:${i}`) ? `<tr class="ex-rad"><td colspan="3">${this._exempelRuta(g, i)}</td></tr>` : ""}`).join("")}
      </table>
      ${gTyp(g) !== "formler" ? `<p class="muted small">💬 = AI:n visar hur ordet används i en mening.</p>` : ""}
      ${svara.size ? `<p class="muted small">🔥 = ord du ofta stavar fel. De försvinner när du har klarat dem några gånger.</p>` : ""}
      ${
        res.length
          ? `<h3>Senaste övningarna</h3><div class="list">${res
              .map((r) => `<div class="row static"><span>${esc(r.datum.replace("T", " ").slice(0, 16))}</span><span>${r.ratt} av ${r.av} rätt</span></div>`)
              .join("")}</div>`
          : ""
      }
      <div class="actions">
        <button class="ghost danger" id="del-glosor">${LISTTYP[gTyp(g)].knapp}</button>
      </div>`;
  }

  // Exempelmening från AI:n (sparas på glosan, så samma ord kostar bara en gång).
  _exempelRuta(g, i) {
    const p = g.par[i] || [];
    const ex = g.exempel?.[`${String(p[0] ?? "").trim()}|${String(p[1] ?? "").trim()}`.slice(0, 250)];
    const nyckel = `${g.id}:${i}`;
    if (this._exLaddar?.has(nyckel)) return `<div class="exempel muted">💬 AI:n skriver en mening…</div>`;
    if (!ex) return `<div class="exempel muted">${esc(this._exFel?.[nyckel] || "Ingen mening än.")}</div>`;
    const ordet = String(ex.ord || "").trim();
    let mening = esc(ex.mening);
    if (ordet) {
      const re = new RegExp(`(${ordet.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\S*)`, "i");
      mening = mening.replace(re, "<b>$1</b>");
    }
    return `<div class="exempel">
      <div class="ex-mening">💬 ${mening}</div>
      ${ex.svenska ? `<div class="muted small">🇸🇪 ${esc(ex.svenska)}</div>` : ""}
      ${ex.forklaring ? `<div class="small">💡 ${esc(ex.forklaring)}</div>` : ""}
      <button class="mini ghost" data-exempel-ny="${i}">🔄 En annan mening</button>
    </div>`;
  }

  async _exempel(amne, gid, i, ny = false) {
    const nyckel = `${gid}:${i}`;
    this._exVisa = this._exVisa || new Set();
    this._exLaddar = this._exLaddar || new Set();
    this._exFel = this._exFel || {};
    const g = this._amne(amne)?.glosor.find((x) => x.id === gid);
    const p = g?.par[i];
    if (!p) return;
    this._exVisa.add(nyckel);
    if (g.exempel?.[`${String(p[0] ?? "").trim()}|${String(p[1] ?? "").trim()}`.slice(0, 250)] && !ny) return this._render();
    this._exLaddar.add(nyckel);
    delete this._exFel[nyckel];
    this._render();
    try {
      const res = await this._hass.fetchWithAuth("/api/skolan/exempel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barn: this._s.barn, amne, glosor: gid, i, ny }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || res.statusText);
      const g2 = this._amne(amne)?.glosor.find((x) => x.id === gid);
      if (g2) g2.exempel = { ...(g2.exempel || {}), [body.nyckel]: body.exempel };
    } catch (e) {
      this._exFel[nyckel] = e.message || String(e);
    } finally {
      this._exLaddar.delete(nyckel);
      this._render();
    }
  }

  _redigeraView(a) {
    const v = this._view;
    const typ = v.typ || "glosor";
    const lt = LISTTYP[typ];
    const par = v.par.length ? v.par : [["", ""]];
    return `
      ${typ === "glosor" ? `<label class="primary upload">
        📷 Läs in från foto (AI)
        <input type="file" id="glosfoto" accept="image/*,application/pdf" hidden>
      </label>` : ""}
      <div class="form">
        <label>Namn <input id="g-namn" value="${esc(v.namn || "")}" placeholder="${esc(lt.namn)}" maxlength="40"></label>
        <label>📅 Förhör/prov (datum) <input id="g-forhor" type="date" value="${esc(v.forhor || "")}"></label>
        ${typ === "glosor" ? `<div class="two">
          <label>Språk 1 <input id="g-s0" value="${esc(v.sprak?.[0] || "")}" placeholder="Engelska"></label>
          <label>Språk 2 <input id="g-s1" value="${esc(v.sprak?.[1] || "")}" placeholder="Svenska"></label>
        </div>` : ""}
        ${typ === "formler" ? `<p class="small muted">Mellanslag och gångertecken spelar ingen roll när svaret rättas: <b>F = m · a</b> och <b>F=ma</b> räknas som samma. Skriv ² som ^2 om det är lättare.</p>` : ""}
        ${typ === "begrepp" ? `<p class="small muted">När du övar visas förklaringen och du skriver begreppet. Du kan också öva åt andra hållet och själv bedöma om du hade rätt.</p>` : ""}
      </div>
      <div class="pairs">
        ${par
          .map(
            (p, i) => `
          <div class="pair">
            <input data-p="${i}" data-k="0" value="${esc(p[0])}" placeholder="${esc(lt.plats[0])}">
            <input data-p="${i}" data-k="1" value="${esc(p[1])}" placeholder="${esc(lt.plats[1])}">
            <button class="mini danger" data-del-par="${i}" title="Ta bort">✕</button>
          </div>`
          )
          .join("")}
      </div>
      <div class="actions">
        <button class="ghost" id="add-par">＋ Rad</button>
        <button class="primary" id="save-glosor">Spara</button>
      </div>`;
  }

  _ovaView(a, g) {
    const o = this._view.ova;
    if (!o && stavLista(g)) {
      return `
        ${this._view.svara ? `<p><b>🔥 Svåra ord (${this._svara(g).length} st)</b></p>` : ""}
        <p>Hur vill du öva på stavningen?</p>
        <div class="list">
          <button class="row" data-start="3">🔊 Lyssna och stava<br><span class="muted small">Ordet läses upp, du skriver det utan att se det</span></button>
          <button class="row" data-start="4">👀 Titta, göm och skriv<br><span class="muted small">Titta på ordet, sedan göms det och du skriver det</span></button>
        </div>`;
    }
    if (!o) {
      return `
        ${this._view.svara ? `<p><b>🔥 Svåra ord (${this._svara(g).length} st)</b></p>` : ""}
        <p>Hur vill du öva?</p>
        <div class="list">
          <button class="row" data-start="0">${esc(g.sprak[0] || "Ord")} → ${esc(g.sprak[1] || "Översättning")}</button>
          <button class="row" data-start="1">${esc(g.sprak[1] || "Översättning")} → ${esc(g.sprak[0] || "Ord")}</button>
          <button class="row" data-start="2">Blandat</button>
          ${window.speechSynthesis && gTyp(g) === "glosor" ? `<button class="row" data-start="3">🔊 Lyssna och stava (${esc(g.sprak[0] || "ordet")})</button>` : ""}
        </div>`;
    }
    if (!o.kvar.length) {
      const pct = Math.round((o.forstaRatt / o.totalt) * 100);
      return `
        <div class="done">
          <div class="big">${pct >= 90 ? "🏆" : pct >= 60 ? "⭐" : "💪"}</div>
          <div class="score">${o.forstaRatt} av ${o.totalt} rätt på första försöket</div>
          <p class="muted">${pct >= 90 ? "Superbra!" : pct >= 60 ? "Bra jobbat! Öva lite till så sitter de." : "Fortsätt öva, det blir bättre för varje gång!"}</p>
          <div class="actions center">
            <button class="primary" id="igen">Öva igen</button>
            <button class="ghost" id="till-glosor">Klar</button>
          </div>
        </div>`;
    }
    const k = o.kvar[0];
    const diktamen = k.fran === -1;
    const titta = k.fran === -2;
    const fraga = titta ? g.par[k.i][0] : diktamen ? g.par[k.i][1] : g.par[k.i][k.fran];
    const svar = diktamen || titta ? g.par[k.i][0] : g.par[k.i][1 - k.fran];
    const fran = diktamen ? g.sprak[1] || "" : titta ? g.sprak[0] || "" : g.sprak[k.fran] || "";
    const till = diktamen || titta ? g.sprak[0] || "" : g.sprak[1 - k.fran] || "";
    const betyder = fraga && String(fraga).trim().toLowerCase() !== String(svar).trim().toLowerCase();
    const klara = o.totalt - o.kvar.length;
    let rattning = "";
    if (o.visat === "fel" && o.skrev.trim()) {
      const n = narmast(o.skrev, svar);
      rattning = `
        <div class="stavning">${n.delar.map((x) => `<span class="${x.ok ? "ok" : "miss"}">${x.c === " " ? "&nbsp;" : esc(x.c)}</span>`).join("")}</div>
        <div class="muted small">${n.avstand <= 2 ? "Nästan! " : ""}Röda bokstäver = fel eller saknas${n.extra ? ` · ${n.extra} bokstav${n.extra === 1 ? "" : "er"} för mycket` : ""}</div>`;
    }
    return `
      <div class="progress"><div style="width:${(klara / o.totalt) * 100}%"></div></div>
      <div class="muted small center">${klara} av ${o.totalt} klara</div>
      <div class="flash">
        ${
          titta
            ? o.tittar && !o.visat
              ? `<div class="muted small">Titta noga på ordet</div><div class="word">${esc(fraga)}</div>
                 <button class="primary" id="gom">🙈 Göm och skriv</button>`
              : `<div class="muted small">Skriv ordet du just såg</div><div class="word gomt">🙈</div>`
            : diktamen
            ? `<button class="lyssna" id="lyssna">🔊</button>
               <div class="muted small">Lyssna och skriv ordet på ${esc(till.toLowerCase())}${betyder ? ` (betyder: <b>${esc(fraga)}</b>)` : ""}</div>`
            : `<div class="muted small">${esc(fran)}</div>
               <div class="word">${esc(fraga)}</div>`
        }
        ${
          titta && o.tittar && !o.visat
            ? ""
            : o.visat
            ? `<div class="answer ${o.visat}">${o.visat === "ratt" ? "✓ Rätt!" : o.visat === "fel" ? "✗ Rätt svar:" : "Svar:"} <b>${esc(svar)}</b></div>
               ${o.skrev && o.visat === "fel" ? `<div class="muted small">Du skrev: ${esc(o.skrev)}</div>` : ""}
               ${rattning}
               ${gTyp(g) !== "formler" && k.fran >= 0 ? (this._exVisa?.has(`${g.id}:${k.i}`) ? this._exempelRuta(g, k.i) : `<button class="ghost" id="ova-exempel">💬 Visa en exempelmening</button>`) : ""}
               <button class="primary" id="nasta">Nästa →</button>
               ${this._hadeRattOk(o, svar) ? `<button class="ghost" id="hade-ratt">Jag hade rätt</button>` : ""}`
            : `${o.tips?.[k.i] ? `<div class="tips-rad">💡 ${[...String(svar)].map((c, j) => (j < o.tips[k.i] || c === " " ? esc(c) : "_")).join("&#8203;")}</div>` : ""}
               <input id="svar" placeholder="${gTyp(g) === "glosor" ? `Skriv på ${esc(till.toLowerCase() || "det andra språket")}` : `Skriv ${esc(till.toLowerCase() || "svaret")}`}" autocomplete="off" autocapitalize="off" spellcheck="false" value="${esc(o.utkast || "")}">
               <div class="actions center">
                 <button class="primary" id="kolla" ${this._busy ? "disabled" : ""}>Kolla${!this._s.kan_valja && (o.forsok?.[k.i] || 0) >= 2 ? " (1 ⭐ om fel)" : ""}</button>
                 ${(o.tips?.[k.i] || 0) < [...String(svar)].length - 1 ? `<button class="ghost" id="tips" ${this._busy ? "disabled" : ""}>💡 Tips (${this._s.kan_valja ? "gratis" : "1 ⭐"})</button>` : ""}
                 <button class="ghost" id="visa">Visa svaret</button>
               </div>
               ${o.tips?.[k.i] ? `<div class="muted small">Med tips räknas ordet inte som rätt på första försöket.</div>` : ""}
               ${!this._s.kan_valja && o.forsok?.[k.i] ? `<div class="muted small">${(o.forsok[k.i] || 0) >= 2 ? "Dina 2 gratis försök på ordet är slut. Rätt svar är gratis, fel svar kostar 1 ⭐. Osäker? Tryck Visa svaret." : "1 gratis försök kvar på ordet."}</div>` : ""}`
        }
      </div>`;
  }

  // ---------- händelser ----------

  _wire() {
    const r = this.shadowRoot;
    const $ = (sel) => r.querySelector(sel);
    const on = (sel, fn) => $(sel)?.addEventListener("click", fn);
    const v = this._view;

    on("#menu", () => this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })));
    on("#back", () => this._go(this._back));
    on("#viewer-stang", (e) => {
      e.stopPropagation();
      this._viewer = null;
      this._render();
    });
    this._zoomViewer($("#viewer"));
    r.querySelectorAll("[data-barn]").forEach((b) =>
      b.addEventListener("click", () => {
        this._view = { name: this._view.name === "foralder" ? "foralder" : "hem" };
        this._load(b.dataset.barn);
      })
    );

    // hem
    on("#add-amne", () => this._go({ name: "amne-form", namn: "", delar: ["bocker", "uppgifter"], valt: false }));
    // nytt / redigera ämne
    if (v.name === "amne-form") {
      $("#af-namn")?.addEventListener("input", (e) => {
        v.namn = e.target.value;
        if (!v.amne && !v.valt) {
          v.delar = forslagDelar(v.namn);
          r.querySelectorAll("[data-del]").forEach((cb) => {
            cb.checked = v.delar.includes(cb.dataset.del);
            cb.closest(".del-val")?.classList.toggle("vald-rad", cb.checked);
          });
        }
      });
      r.querySelectorAll("[data-del]").forEach((cb) =>
        cb.addEventListener("change", () => {
          v.valt = true;
          v.delar = DELAR.map((d) => d.id).filter((id) => r.querySelector(`[data-del="${id}"]`)?.checked);
          cb.closest(".del-val")?.classList.toggle("vald-rad", cb.checked);
        })
      );
      on("#af-spara", async () => {
        v.namn = $("#af-namn")?.value ?? v.namn;
        if (!v.namn.trim()) {
          this._msg = { type: "error", text: "Skriv vad ämnet heter." };
          return this._render();
        }
        if (!v.delar.length) {
          this._msg = { type: "error", text: "Välj minst en del." };
          return this._render();
        }
        if (v.amne) {
          if (await this._act("amne_andra", { amne: v.amne, namn: v.namn, delar: v.delar })) this._go({ name: "amne", amne: v.amne });
        } else if (await this._act("add_amne", { namn: v.namn, delar: v.delar })) {
          const ny = (this._s.data.amnen || []).find((x) => x.namn.toLowerCase() === v.namn.trim().toLowerCase());
          this._go(ny ? (v.franLaxa ? { name: "laxa", steg: "typ", amne: ny.id } : { name: "amne", amne: ny.id }) : { name: "hem" });
        }
      });
    }
    r.querySelectorAll("[data-open-amne]").forEach((b) =>
      b.addEventListener("click", () => this._go({ name: "amne", amne: b.dataset.openAmne }))
    );

    // ämne
    on("#add-bok", async () => {
      const n = this._ask("Vad heter boken?");
      if (n) await this._act("add_bok", { amne: v.amne, namn: n });
    });
    r.querySelectorAll("[data-add-lista]").forEach((b) =>
      b.addEventListener("click", () => {
        const typ = b.dataset.addLista;
        this._go({ name: "redigera", amne: v.amne, typ, namn: "", sprak: [...LISTTYP[typ].sprak], par: [] });
      })
    );
    on("#edit-amne", () => {
      const a = this._amne(v.amne);
      this._go({ name: "amne-form", amne: a.id, namn: a.namn, delar: delarFor(a), valt: true });
    });
    // uppgifter
    const uppgAdd = async () => {
      const text = $("#uppg-text")?.value.trim() || "";
      if (!text) return $("#uppg-text")?.focus();
      v.uppgUtkast = text;
      if (await this._act("uppgift_ny", { amne: v.amne, text, datum: $("#uppg-datum")?.value || null })) {
        v.uppgUtkast = "";
        this._render();
        $("#uppg-text")?.focus();
      }
    };
    on("#uppg-add", uppgAdd);
    $("#uppg-text")?.addEventListener("keydown", (e) => { if (e.key === "Enter") uppgAdd(); });
    on("#uppg-alla", () => { v.allaKlara = !v.allaKlara; this._render(); });
    r.querySelectorAll("[data-uppg-klar]").forEach((cb) =>
      cb.addEventListener("change", () => this._act("uppgift_klar", { amne: v.amne, uppgift: cb.dataset.uppgKlar, klar: cb.checked }))
    );
    r.querySelectorAll("[data-uppg-bort]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (confirm("Ta bort uppgiften?")) await this._act("uppgift_bort", { amne: v.amne, uppgift: b.dataset.uppgBort });
      })
    );
    // anteckningar
    $("#ant-text")?.addEventListener("input", (e) => { v.antUtkast = e.target.value; });
    on("#ant-spara", async () => {
      const text = $("#ant-text")?.value ?? "";
      v.antUtkast = text;
      if (await this._act("anteckning_spara", { amne: v.amne, text })) {
        v.antUtkast = undefined;
        this._msg = { type: "ok", text: "Sparat ✓" };
        this._render();
      }
    });
    on("#del-amne", async () => {
      if (confirm("Ta bort ämnet med alla böcker, sidor och glosor? Det går inte att ångra.")) {
        if (await this._act("del_amne", { amne: v.amne })) this._go({ name: "hem" });
      }
    });
    r.querySelectorAll("[data-open-bok]").forEach((b) =>
      b.addEventListener("click", () => {
        const bok = this._amne(v.amne)?.bocker.find((x) => x.id === b.dataset.openBok);
        if (bok?.ebok) this._ebokOppna(v.amne, bok.id);
        else this._go({ name: "bok", amne: v.amne, bok: b.dataset.openBok });
      })
    );
    r.querySelectorAll("[data-open-glosor]").forEach((b) =>
      b.addEventListener("click", () => this._go({ name: "glosor", amne: v.amne, glosor: b.dataset.openGlosor }))
    );

    // bok
    $("#pages")?.addEventListener("change", (e) => {
      const files = [...e.target.files];
      if (files.length) this._upload(files);
    });
    r.querySelectorAll("input[data-omslag]").forEach((inp) =>
      inp.addEventListener("change", (e) => {
        const f = e.target.files[0];
        if (f) this._upload([f], inp.dataset.omslag);
      })
    );
    r.querySelectorAll("[data-del-omslag]").forEach((b) =>
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (confirm("Ta bort omslagsbilden?")) await this._act("del_omslag", { amne: v.amne, bok: v.bok, sida: b.dataset.delOmslag });
      })
    );
    const setRed = (pa) => {
      this._redigera = { ...(this._redigera || {}), [v.bok]: pa };
      this._render();
      this.shadowRoot.querySelector(".content")?.scrollTo?.(0, 0);
    };
    on("#redigera-bok", () => setRed(true));
    on("#redigera-klar", () => setRed(false));
    on("#gor-ebok", () => this._ebokStarta(false));
    on("#gor-om-ebok", () => {
      if (confirm("Läsa om alla sidor från början? Det tar en stund.")) this._ebokStarta(true);
    });
    on("#las-ebok", () => this._ebokOppna());
    on("#omslag-las", () => this._ebokOppna());
    on("#foto-lon-be", async () => {
      if (await this._act("bok_lon_be", { amne: v.amne, bok: v.bok })) {
        this._msg = { type: "ok", text: "Mamma och pappa har fått en fråga. När de har kollat fotona får du din lön 📸" };
        this._render();
      }
    });
    r.querySelectorAll("[data-foto-lon]").forEach((b) =>
      b.addEventListener("click", async () => {
        const ok = b.dataset.fotoLon === "1";
        if (await this._uppdragAct("godkann", { id: `bok-${v.bok}`, ok })) {
          this._msg = { type: "ok", text: ok ? `Godkänt! ${this._s.namn} har fått sin lön 📸` : `Nekat. ${this._s.namn} får veta att fotona behöver göras om.` };
          this._render();
        }
      })
    );
    on("#bok-meny", () => this._go({ name: "bok", amne: v.amne, bok: v.bok }));
    on("#visa-toc", () => { v.e.visaToc = true; this._render(); });
    on("#stang-toc", () => { v.e.visaToc = false; this._render(); });
    $("#ebok-sok")?.addEventListener("input", (ev) => {
      const pos = ev.target.selectionStart;
      v.e.sok = ev.target.value;
      this._render();
      const inp = this.shadowRoot.querySelector("#ebok-sok");
      inp?.focus();
      inp?.setSelectionRange?.(pos, pos);
    });
    on("#ebok-fore", () => this._ebokGa(v.e.idx - 1));
    on("#ebok-nasta", () => this._ebokGa(v.e.idx + 1));
    r.querySelectorAll("[data-ga]").forEach((b) => b.addEventListener("click", () => this._ebokGa(Number(b.dataset.ga))));
    const sida = $(".ebok-sida");
    if (sida) {
      let x0 = null, y0 = null;
      sida.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
      sida.addEventListener("touchend", (e) => {
        if (x0 === null) return;
        const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
        x0 = null;
        if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.5) this._ebokGa(v.e.idx + (dx < 0 ? 1 : -1));
      });
    }
    on("#skriv-ut", () => {
      v.utskrift = new Set();
      this._msg = { type: "info", text: "Tryck på sidorna du vill skriva ut." };
      this._render();
    });
    on("#ut-avbryt", () => {
      delete v.utskrift;
      this._msg = null;
      this._render();
    });
    on("#ut-alla", () => {
      const b = this._amne(v.amne)?.bocker.find((x) => x.id === v.bok);
      const alla = [...b.sidor, ...(b.framsida ? ["fram"] : []), ...(b.baksida ? ["bak"] : [])];
      v.utskrift = v.utskrift.size === alla.length ? new Set() : new Set(alla);
      this._render();
    });
    r.querySelectorAll("[data-valj]").forEach((el) =>
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        const k = el.dataset.valj;
        v.utskrift.has(k) ? v.utskrift.delete(k) : v.utskrift.add(k);
        this._render();
      })
    );
    on("#ut-skriv", async () => {
      const b = this._amne(v.amne)?.bocker.find((x) => x.id === v.bok);
      const val = v.utskrift;
      if (!b || !val.size) return;
      const idx = b.sidor.map((f, i) => (val.has(f) ? i + 1 : null)).filter(Boolean);
      // Öppna fönstret direkt (inne i klicket) så att det inte blockeras, och fyll det sen.
      const w = window.open("", "_blank");
      try {
        const q = new URLSearchParams({
          barn: this._s.barn, amne: v.amne, bok: v.bok,
          sidor: idx.length ? idx.join(",") : "ingen",
          fram: val.has("fram") ? "1" : "0", bak: val.has("bak") ? "1" : "0",
        });
        const res = await this._hass.callWS({ type: "auth/sign_path", path: `/api/skolan/utskrift?${q}`, expires: 120 });
        if (w) w.location.href = res.path;
        else window.location.href = res.path;
        delete v.utskrift;
        this._msg = null;
        this._render();
      } catch (e) {
        w?.close();
        this._msg = { type: "error", text: `Kunde inte öppna utskriften: ${e.message || e}` };
        this._render();
      }
    });
    on("#rename-bok", async () => {
      const b = this._amne(v.amne)?.bocker.find((x) => x.id === v.bok);
      const n = this._ask("Nytt namn på boken:", b?.namn);
      if (n) await this._act("rename_bok", { amne: v.amne, bok: v.bok, namn: n });
    });
    on("#del-bok", async () => {
      if (confirm("Ta bort boken och alla dess sidor?")) {
        if (await this._act("del_bok", { amne: v.amne, bok: v.bok })) this._go({ name: "amne", amne: v.amne });
      }
    });
    r.querySelectorAll("[data-del-sida]").forEach((b) =>
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (confirm("Ta bort sidan?")) await this._act("del_sida", { amne: v.amne, bok: v.bok, fil: b.dataset.delSida });
      })
    );
    r.querySelectorAll("[data-move]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        this._act("move_sida", { amne: v.amne, bok: v.bok, fil: b.dataset.move, steg: Number(b.dataset.steg) });
      })
    );
    r.querySelectorAll("[data-open-fil]").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          const url = await this._blob(b.dataset.openFil);
          if (b.dataset.openFil.toLowerCase().endsWith(".pdf")) window.open(url, "_blank");
          else {
            this._viewer = url;
            this._viewerEbok = !!b.closest(".ebok-sida") && this._view.name === "ebok";
            this._render();
          }
        } catch (err) {
          this._msg = { type: "error", text: err.message };
          this._render();
        }
      })
    );

    // glosor
    on("#ova", () => this._go({ name: "ova", amne: v.amne, glosor: v.glosor }));
    on("#man-forhor", async () => {
      const g = this._amne(v.amne)?.glosor.find((x) => x.id === v.glosor);
      if (!g) return;
      const av = Number(this._ask("Hur många ord förhördes?", String(g.par.length)));
      if (!av) return;
      const ratt = Number(this._ask(`Hur många av ${av} var rätt?`, String(av)));
      if (Number.isNaN(ratt)) return;
      if (await this._act("manuell_forhor", { amne: v.amne, glosor: v.glosor, av, ratt, av_namn: this._hass.user?.name })) {
        this._msg = { type: "ok", text: `Förhöret är registrerat: ${ratt} av ${av} rätt ✅` };
        this._load();
      }
    });
    on("#skicka-forhor", () => this._go({ name: "skicka", amne: v.amne, glosor: v.glosor, riktning: 0 }));
    r.querySelectorAll("[data-riktning]").forEach((b) =>
      b.addEventListener("click", () => {
        v.meddelande = $("#fh-medd")?.value || "";
        v.riktning = Number(b.dataset.riktning);
        this._render();
      })
    );
    on("#fh-skicka", async () => {
      const ok = await this._forhorAct("skapa", { amne: v.amne, glosor: v.glosor, riktning: v.riktning, meddelande: $("#fh-medd")?.value || "" });
      if (ok) {
        this._go({ name: "hem" });
        this._msg = { type: "ok", text: `Förhöret är skickat till ${this._s.namn}! 📨` };
        this._render();
      }
    });
    r.querySelectorAll("[data-open-forhor]").forEach((b) =>
      b.addEventListener("click", () => this._go({ name: "forhor", forhor: b.dataset.openForhor, franLogg: v.name === "fhlogg" }))
    );
    const fhLas = () => {
      const f = (this._s.data.forhor || []).find((x) => x.id === v.forhor);
      const i = f ? f.svar.length : -1;
      if (f && f.fragor[i]?.dikt) las_upp_forhor(this._hass, this._s.barn, f.id, i, f.fragor[i].fran);
    };
    on("#fh-lyssna", fhLas);
    on("#fh-start", () => {
      v.startad = true;
      fhLas(); // första uppläsningen i klicket (krävs på iPhone)
      this._forhorAct("starta", { forhor: v.forhor }); // föräldern får en notis
      // Riktig helskärm där det går (Android, dator, iPad). iPhone använder bara helskärmsvyn.
      try { document.documentElement.requestFullscreen?.()?.catch?.(() => {}); } catch (e) { /* ok */ }
      this._render();
    });
    on("#fh-senare", () => { this._fhSenare = v.forhor; this._go({ name: "hem" }); });
    on("#fh-logg", () => this._go({ name: "fhlogg" }));
    on("#open-meriter", () => this._go({ name: "meriter" }));
    // läsläxor & prov
    r.querySelectorAll("[data-open-uppdrag]").forEach((b) =>
      b.addEventListener("click", () => this._go({ name: "uppdrag", id: b.dataset.openUppdrag, amne: b.dataset.amne }))
    );
    on("#ny-laxa", () => this._go({ name: "laxa", steg: "amne" }));
    if (v.name === "laxa") {
      r.querySelectorAll("[data-laxa-amne]").forEach((b) => b.addEventListener("click", () => this._go({ name: "laxa", steg: "typ", amne: b.dataset.laxaAmne })));
      on("#laxa-nytt-amne", () => this._go({ name: "amne-form", namn: "", delar: ["bocker", "uppgifter"], valt: false, franLaxa: true }));
      r.querySelectorAll("[data-laxa-typ]").forEach((b) =>
        b.addEventListener("click", () => {
          const typ = b.dataset.laxaTyp;
          if (LISTTYP[typ]) return this._go({ name: "redigera", amne: v.amne, typ, namn: "", sprak: [...LISTTYP[typ].sprak], par: [], guide: true });
          if (typ === "las" || typ === "prov") return this._go({ name: "uppdrag_ny", typ, amne: v.amne, guide: true });
          this._go({ name: "laxa", steg: "uppgift", amne: v.amne, text: "", datum: null });
        })
      );
      $("#lx-text")?.addEventListener("input", (e) => { v.text = e.target.value; });
      $("#lx-datum")?.addEventListener("change", (e) => { v.datum = e.target.value; this._render(); });
      r.querySelectorAll("[data-lx-datum]").forEach((b) => b.addEventListener("click", () => { v.text = $("#lx-text")?.value ?? v.text; v.datum = b.dataset.lxDatum; this._render(); }));
      if (v.steg === "uppgift" && !v.text) setTimeout(() => $("#lx-text")?.focus(), 0);
      on("#lx-spara", async () => {
        v.text = $("#lx-text")?.value ?? v.text;
        if (!v.text.trim()) {
          this._msg = { type: "error", text: "Skriv vad du ska göra." };
          return this._render();
        }
        if (await this._act("uppgift_ny", { amne: v.amne, text: v.text, datum: v.datum || null })) {
          const amne = v.amne;
          this._go({ name: "amne", amne });
          this._msg = { type: "ok", text: "Uppgiften är sparad! ✅" };
          this._render();
        }
      });
    }
    const uSync = () => {
      if (v.name !== "uppdrag_ny") return;
      v.namn = $("#u-namn")?.value ?? v.namn;
      v.datum = $("#u-datum")?.value ?? v.datum;
      v.fran = $("#u-fran")?.value ?? v.fran;
      v.till = $("#u-till")?.value ?? v.till;
    };
    $("#u-amne")?.addEventListener("change", (e) => {
      uSync();
      Object.assign(v, { amne: e.target.value, bok: "", kapitelLista: [], valda: [], glosor: [], fran: "", till: "" });
      this._render();
    });
    $("#u-bok")?.addEventListener("change", async (e) => {
      uSync();
      Object.assign(v, { bok: e.target.value, kapitelLista: [], valda: [], fran: "", till: "" });
      if (v.bok) {
        try {
          const res = await this._hass.fetchWithAuth(
            `/api/skolan/ebok?barn=${encodeURIComponent(this._s.barn)}&amne=${encodeURIComponent(v.amne)}&bok=${encodeURIComponent(v.bok)}`
          );
          const body = await res.json();
          const t = toc(body.sidor, body.toc).filter((x) => x.niva === 1);
          const maxNr = Math.max(0, ...body.sidor.map((x) => sidnrInt(x.sidnr) || 0));
          v.kapitelLista = t
            .map((k, i) => {
              const fran = k.sida ?? sidnrInt(body.sidor[k.idx]?.sidnr);
              const nasta = t[i + 1];
              const till = nasta ? (nasta.sida ?? sidnrInt(body.sidor[nasta.idx]?.sidnr)) - 1 : maxNr;
              return { text: k.text, fran, till };
            })
            .filter((k) => k.fran != null && k.till >= k.fran);
        } catch (err) { /* bara sidnummer då */ }
      }
      this._render();
    });
    r.querySelectorAll("[data-kap]").forEach((cb) =>
      cb.addEventListener("change", () => {
        uSync();
        const i = Number(cb.dataset.kap);
        v.valda = cb.checked ? [...(v.valda || []), i] : (v.valda || []).filter((x) => x !== i);
        const valda = v.valda.map((x) => v.kapitelLista[x]);
        if (valda.length) {
          v.fran = Math.min(...valda.map((k) => k.fran));
          v.till = Math.max(...valda.map((k) => k.till));
        }
        this._render();
      })
    );
    r.querySelectorAll("[data-u-glosor]").forEach((cb) =>
      cb.addEventListener("change", () => {
        uSync();
        const id = cb.dataset.uGlosor;
        v.glosor = cb.checked ? [...(v.glosor || []), id] : (v.glosor || []).filter((x) => x !== id);
      })
    );
    on("#u-spara", async () => {
      uSync();
      const kap = (v.valda || []).sort((x, y) => x - y).map((x) => v.kapitelLista[x].text).join(", ");
      const ok = await this._uppdragAct("skapa", {
        typ: v.typ, namn: v.namn, amne: v.amne, bok: v.bok || null, fran: v.fran, till: v.till,
        kapitel: kap, datum: v.datum, glosor: v.glosor || [],
      });
      if (ok) {
        this._go({ name: "hem" });
        this._msg = { type: "ok", text: v.typ === "prov" ? "Provet är registrerat! 📝" : "Läsläxan är sparad! 📖" };
        this._render();
      }
    });
    on("#u-las", (e) => {
      const u = (this._s.data.uppdrag || []).find((x) => x.id === v.id);
      this._ebokOppna(u.amne, u.bok, e.currentTarget.dataset.nyckel, u.id);
    });
    on("#till-uppdrag", () => {
      const u = (this._s.data.uppdrag || []).find((x) => x.id === v.uppdrag) ||
        (this._s.data.uppdrag || []).find((x) => !x.klart && x.allt_last && x.bok === v.bok);
      if (u) this._go({ name: "uppdrag", id: u.id, amne: u.amne });
    });
    on("#u-fragor", () => this._uppdragAct("fragor", { id: v.id }));
    r.querySelectorAll("input[name=pr-typ]").forEach((x) =>
      x.addEventListener("change", () => { v.provBetyg = x.value; this._render(); })
    );
    on("#pr-spara", async () => {
      const typ = r.querySelector("input[name=pr-typ]:checked")?.value || "poang";
      const args = { id: v.id, kommentar: $("#pr-komm")?.value || "" };
      if (typ === "poang") {
        const po = $("#pr-poang")?.value, mx = $("#pr-max")?.value;
        if (po === "" || mx === "") { this._msg = { type: "error", text: "Skriv in poäng och maxpoäng." }; this._render(); return; }
        Object.assign(args, { poang: Number(po.replace(",", ".")), max: Number(mx.replace(",", ".")) });
      } else {
        const b = r.querySelector("input[name=pr-betyg]:checked")?.value;
        if (!b) { this._msg = { type: "error", text: "Välj ett betyg." }; this._render(); return; }
        args.betyg = b;
      }
      if (await this._uppdragAct("prov_resultat", args)) {
        const u = (this._s.data.uppdrag || []).find((x) => x.id === v.id);
        const p = u?.resultat?.p || 0;
        this._msg = { type: "ok", text: p ? `Resultatet är sparat. ${this._s.namn} får +${p} ⭐ totalt för provet 🌟` : "Resultatet är sparat." };
        this._render();
      }
    });
    on("#pr-rensa", async () => {
      if (confirm("Ta bort provresultatet? Meriterna för det dras tillbaka.") && (await this._uppdragAct("prov_resultat", { id: v.id, rensa: true }))) {
        this._msg = { type: "ok", text: "Resultatet är borttaget." };
        this._render();
      }
    });
    on("#u-manuell", async () => {
      const idag = new Date().toISOString().slice(0, 10);
      const datum = this._ask("Vilket datum blev den klar? (ÅÅÅÅ-MM-DD)", idag);
      if (!datum) return;
      if (await this._act("manuell_uppdrag", { id: v.id, datum })) {
        this._msg = { type: "ok", text: "Registrerad som klar ✅" };
        this._load();
      }
    });
    r.querySelectorAll("[data-kq]").forEach((b) =>
      b.addEventListener("click", () => {
        v.svar = v.svar || [];
        v.svar[Number(b.dataset.kq)] = Number(b.dataset.ka);
        this._render();
      })
    );
    on("#u-svara", async () => {
      const svar = v.svar;
      v.svar = [];
      if (await this._uppdragAct("svara", { id: v.id, svar })) {
        const u = (this._s.data.uppdrag || []).find((x) => x.id === v.id);
        this._msg = u?.klart ? { type: "ok", text: "Snyggt! Du klarade kontrollfrågorna 🎉" } : { type: "error", text: "Inte riktigt. Läs sidorna igen och försök en gång till." };
        this._render();
      }
    });
    on("#u-ta-bort", async () => {
      if (confirm("Ta bort?") && (await this._uppdragAct("ta_bort", { id: v.id }))) this._go({ name: "hem" });
    });
    on("#open-foralder", () => this._go({ name: "foralder" }));
    // veckobrev
    on("#open-info", () => this._go({ name: "info", fran: { name: this._view.name } }));
    on("#open-veckobrev", () => this._go({ name: "veckobrev" }));
    ["vb-foto", "ls-foto"].forEach((id) => $(`#${id}`)?.addEventListener("change", (e) => {
      const nya = [...(e.target.files || [])];
      if (!nya.length) return;
      this._fotoFiler = this._fotoFiler || {};
      this._fotoFiler[id] = [...(this._fotoFiler[id] || []), ...nya].slice(0, 6);
      this._render();
    }));
    r.querySelectorAll("[data-foto-bort]").forEach((b) => b.addEventListener("click", () => {
      const [id, i] = b.dataset.fotoBort.split(":");
      this._fotoFiler[id].splice(Number(i), 1);
      this._render();
    }));
    r.querySelectorAll("[data-foto-las]").forEach((b) => b.addEventListener("click", async () => {
      const id = b.dataset.fotoLas, filer = this._fotoFiler?.[id] || [];
      if (!filer.length) return;
      if (id === "vb-foto") await this._veckobrevLas(filer); else await this._lektionLas(filer);
      if (this._msg?.type !== "error") { delete this._fotoFiler[id]; this._render(); }
    }));
    const vbSync = () => {
      if (v.name !== "veckobrev" || !v.f) return;
      r.querySelectorAll("[data-vb]").forEach((el) => {
        const x = v.f[el.dataset.vb];
        if (!x || el.tagName === "SELECT") return;
        if (el.dataset.f === "ordtext") x.ord = el.value.split("\n").map((o) => o.trim()).filter(Boolean);
        else x[el.dataset.f] = el.value;
      });
    };
    r.querySelectorAll("select[data-vb]").forEach((el) =>
      el.addEventListener("change", () => {
        vbSync();
        const x = v.f[el.dataset.vb];
        x[el.dataset.f] = el.value;
        if (el.dataset.f === "amne") Object.assign(x, { bok: "", glosor: "", befintliga: [] });
        if (el.dataset.f === "glosor") {
          const g = this._amne(x.amne)?.glosor.find((y) => y.id === el.value);
          x.befintliga = g ? g.par.map((p) => p[0]) : [];
        }
        this._render();
      })
    );
    r.querySelectorAll("[data-vb-kap]").forEach((el) =>
      el.addEventListener("change", () => {
        vbSync();
        const x = v.f[el.dataset.vbKap];
        const k = (v.f.kapitel[x.bok] || [])[Number(el.value)];
        if (k) Object.assign(x, { kapitel: k.namn, fran: k.fran, till: k.till });
        this._render();
      })
    );
    r.querySelectorAll("[data-vb-med]").forEach((el) =>
      el.addEventListener("change", () => { vbSync(); v.med[el.dataset.vbMed] = el.checked; this._render(); })
    );
    r.querySelectorAll("[data-vb-dag]").forEach((el) =>
      el.addEventListener("change", () => {
        vbSync();
        const d = el.dataset.vbDag;
        v.f.las.dagar = el.checked ? [...new Set([...v.f.las.dagar, d])].sort() : v.f.las.dagar.filter((x) => x !== d);
      })
    );
    $("[data-vb-hogl]")?.addEventListener("change", (e) => { vbSync(); v.f.las.hogl = e.target.checked; });
    const vbListSync = () => {
      if (v.name !== "veckobrev" || !v.f) return;
      r.querySelectorAll("[data-vbp]").forEach((el) => { v.f.prov[Number(el.dataset.vbp)][el.dataset.f] = el.value; });
      r.querySelectorAll("[data-vbi]").forEach((el) => { v.f.info[Number(el.dataset.vbi)][el.dataset.f] = el.value; });
    };
    r.querySelectorAll("[data-vbp-med]").forEach((el) => el.addEventListener("change", () => { vbListSync(); v.f.prov[Number(el.dataset.vbpMed)].med = el.checked; this._render(); }));
    r.querySelectorAll("[data-vbi-med]").forEach((el) => el.addEventListener("change", () => { vbListSync(); v.f.info[Number(el.dataset.vbiMed)].med = el.checked; this._render(); }));
    on("#vb-info-ny", () => { vbListSync(); v.f.info = [...(v.f.info || []), { text: "", datum: "", tid: "" }]; this._render(); });
    on("#vb-spara", async () => {
      vbSync();
      vbListSync();
      const f = v.f;
      const args = { mandag: f.mandag };
      if (f.las && v.med.las) args.las = f.las;
      if (f.skriv && v.med.skriv) args.skriv = f.skriv;
      if (f.ord && v.med.ord) args.ord = f.ord;
      const prov = (f.prov || []).filter((x) => x.med !== false);
      if (prov.some((x) => !x.datum)) { this._msg = { type: "error", text: "Välj datum för provet." }; return this._render(); }
      if (prov.length) args.prov = prov;
      const info = (f.info || []).filter((x) => x.med !== false && x.text.trim());
      if (info.length) args.info = info;
      if (Object.keys(args).length === 1) return;
      if (await this._uppdragAct("veckoplan", args)) {
        if (v.inkorg) await this._skolaAct({ op: "inkorg_klar", id: v.inkorg });
        this._go({ name: "hem" });
        this._msg = { type: "ok", text: "Veckobrevet är inlagt! 📅" };
        this._render();
      }
    });
    // husdjur
    r.querySelectorAll("[data-djur-val]").forEach((b) =>
      b.addEventListener("click", async () => {
        const namn = this._ask(`Vad ska din ${b.dataset.djurVal} heta?`, "");
        if (namn === null) return;
        await this._act("djur", { art: b.dataset.djurVal, namn: namn || "Kompis" });
      })
    );
    on("#open-djurbutik", () => this._go({ name: "djurbutik" }));
    on("#open-karta", () => this._go({ name: "karta" }));
    on("#open-arena", () => this._go({ name: "arena" }));
    on("#open-lag", () => this._go({ name: "lag" }));
    on("#open-till", () => this._go({ name: "tillsammans" }));
    on("#open-skola", () => this._go({ name: "skola" }));
    r.querySelectorAll("[data-sk-f]").forEach((b) => b.addEventListener("change", () => this._skolaAct({ op: "installningar", [b.dataset.skF]: b.checked })));
    on("#sk-spara", () => this._skolaAct({ op: "installningar", namn: $("#sk-namn")?.value || "", mejl_till: $("#sk-mejl")?.value || "",
      mejl_dagar: [...r.querySelectorAll("[data-sk-dag]")].filter((x) => x.checked).map((x) => Number(x.dataset.skDag)) }, "Sparat ✅"));
    on("#sk-smtp", () => this._skolaAct({ op: "smtp", server: $("#smtp-server")?.value, port: $("#smtp-port")?.value, anvandare: $("#smtp-anv")?.value, fran: $("#smtp-fran")?.value, losen: $("#smtp-losen")?.value }, "E-posten är inställd ✅"));
    on("#sk-test", () => this._skolaAct({ op: "mejl_test", till: $("#sk-test-till")?.value || "" }, "Testmejlet är skickat 📧"));
    on("#sk-koppla-bort", () => { if (confirm("Koppla bort läraren? Klasslänken byts ut och läraren behöver koppla in eleven igen.")) this._skolaAct({ op: "koppla_bort" }, "Läraren är bortkopplad."); });
    on("#sk-kopiera", () => navigator.clipboard?.writeText(this._s.skola?.lank || "").then(() => { this._msg = { type: "ok", text: "Klasslänken är kopierad 📋" }; this._render(); }));
    r.querySelectorAll("[data-rep]").forEach((b) => b.addEventListener("click", () => { const [am, gl] = b.dataset.rep.split("|"); this._go({ name: "glosor", amne: am, glosor: gl }); }));
    on("#open-fokus", () => this._go({ name: "fokus" }));
    on("#fd-spara", async () => { if (await this._act("fodelsedag_satt", { datum: $("#fd-datum")?.value || "" })) this._msg = { type: "ok", text: "🎂 Födelsedagen är sparad." }; this._render(); });
    on("#fd-oppna", async () => {
      if (await this._act("fodelsedag_hamta", {})) {
        this._fx({ text: "🎂 GRATTIS!", sub: `${esc(this._s.namn)} fyller ${this._s.fodelsedag?.alder} år!`, emojis: ["🎂", "🎉", "🎁", "🥳", "🎈"], antal: 44, konfetti: true, farg: "#ec407a", ljud: true });
        await this._load(this._s.barn);
      }
      this._render();
    });
    r.querySelectorAll("[data-lucka]").forEach((b) => b.addEventListener("click", async () => {
      const dag = Number(b.dataset.lucka);
      b.classList.add("oppnas");
      if (await this._act("lucka", { dag })) {
        await this._load(this._s.barn);
        const l = this._s.jul?.luckor?.find((x) => x.dag === dag);
        const inn = l?.innehall || [];
        this._fx({ text: dag === 24 ? "🎅 GOD JUL!" : `🎄 Lucka ${dag}`, sub: inn.join(" · "), emojis: ["🎁", "❄️", "⭐", "🎄", "✨"], antal: dag === 24 ? 50 : 28, konfetti: dag === 24, farg: "#c62828", ljud: dag === 24 });
      }
      this._render();
    }));
    on("#open-album", () => this._go({ name: "album" }));
    on("#kort-vand", () => {
      const nya = this._s.kort?.nya || [];
      const legend = nya.some((k) => k.sallsynt === "legendarisk"), ovanlig = nya.some((k) => k.sallsynt === "ovanlig");
      this.shadowRoot.querySelectorAll(".kort-vand").forEach((x) => x.classList.add("skakar"));
      setTimeout(() => {
        this._kortVanda = true; this._render();
        if (legend) this._fx({ text: "🌟 LEGENDARISK!", sub: nya.find((k) => k.sallsynt === "legendarisk").namn, emojis: ["🌟", "✨", "👑", "💫"], antal: 40, konfetti: true, farg: "#ffb300", ljud: true });
        else if (ovanlig) this._fx({ text: "✨ Ovanligt kort!", emojis: ["✨", "💎", "⭐"], antal: 28, farg: "#29b6f6" });
        else this._fx({ emojis: ["✨", "⭐", "🃏"], antal: 18, farg: "#b388ff" });
      }, 700);
    });
    const kortSett = async (album) => { this._kortVanda = false; await this._act("kort_sett", {}); await this._load(this._s.barn); if (album) this._go({ name: "album" }); else this._render(); };
    on("#kort-ok", () => kortSett(false));
    r.querySelectorAll("[data-kista]").forEach((b) => b.addEventListener("click", async () => {
      if (this._busy) return;
      b.classList.add("skakar");
      await new Promise((ok) => setTimeout(ok, 600));
      if (!(await this._act("kista_oppna", { id: b.dataset.kista }))) return;
      const ut = this._s.data?.meriter?.kista_senast;
      this._kistaVisa = ut;
      await this._load(this._s.barn);
      if (ut) this._fx({ text: ut.typ === "guld" ? "👑 GULDKISTA!" : ut.typ === "silver" ? "💎 Silverkista!" : "🎁 Kistan öppnad!", sub: ut.saker.map((x) => x.text).join(" · "),
        emojis: ["🎁", "✨", ...ut.saker.map((x) => x.ikon)], antal: ut.typ === "guld" ? 40 : 24, konfetti: ut.typ !== "brons", farg: ut.typ === "guld" ? "#ffb300" : "#7e57c2", ljud: ut.typ === "guld" });
      this._render();
    }));
    on("#kista-ok", () => { this._kistaVisa = null; this._render(); });
    on("#laxfraga-ja", async () => { if (await this._act("laxfraga_svar", { ja: true })) this._go({ name: "laxa", steg: "amne" }); });
    on("#laxfraga-nej", async () => { if (await this._act("laxfraga_svar", { ja: false })) { await this._load(this._s.barn); this._fx({ emojis: ["🐾", "⭐"], antal: 12 }); this._render(); } });
    r.querySelectorAll("[data-provboss]").forEach((b) => b.addEventListener("click", async () => {
      if (this._busy || !(await this._act("provboss_start", { id: b.dataset.provboss }))) return this._render();
      await this._load();
      this._arenaVisa();
    }));
    on("#open-lektioner", () => this._go({ name: "lektioner" }));
    on("#open-kalender", () => { this._kal = null; this._go({ name: "kalender" }); this._kalHamta(); });
    if (v.name === "kalender" && this._kal) {
      on("#kal-ny", () => { v.ny = "val"; this._render(); });
      r.querySelectorAll("[data-kal-typ]").forEach((b) => b.addEventListener("click", () => { v.ny = b.dataset.kalTyp; this._kalFiler = []; this._render(); }));
      on("#kn-avbryt", () => { v.ny = null; this._render(); });
      $("#kn-fil")?.addEventListener("change", (e) => { this._kalFiler = [...(e.target.files || [])].slice(0, 6); this._render(); });
      on("#kn-spara", async () => {
        const barn = [...r.querySelectorAll("[data-kn-barn]")].filter((x) => x.checked).map((x) => x.dataset.knBarn);
        const namn = r.querySelector("#kn-namn")?.value || "";
        let ok;
        this._msg = { type: "info", text: v.ny === "foto" || v.ny === "webb" ? "AI:n läser kalendern… (kan ta en halv minut)" : "Hämtar kalendern…" };
        if (v.ny === "fil" || v.ny === "foto") {
          if (!this._kalFiler?.length) { this._msg = { type: "error", text: "Välj en fil först." }; return this._render(); }
          const fd = new FormData();
          fd.append("typ", v.ny); fd.append("namn", namn); fd.append("barn", barn.join(","));
          this._kalFiler.forEach((f) => fd.append("file", f, f.name));
          ok = await this._kalHamta(fd);
        } else {
          ok = await this._kalHamta({ op: "lagg_till", typ: v.ny, namn: namn || (v.ny === "ha" ? r.querySelector("#kn-entity")?.selectedOptions[0]?.textContent : ""), barn,
            url: r.querySelector("#kn-url")?.value, entity: r.querySelector("#kn-entity")?.value });
        }
        if (ok) { v.ny = null; this._kalFiler = []; this._msg = { type: "ok", text: "Kalendern är inkopplad 📅" }; await this._load(this._s.barn); this._render(); }
      });
      r.querySelectorAll("[data-kal-barn]").forEach((el) => el.addEventListener("change", () => {
        const id = el.dataset.kalBarn;
        const barn = [...r.querySelectorAll(`[data-kal-barn="${id}"]`)].filter((x) => x.checked).map((x) => x.dataset.b);
        this._kalHamta({ op: "barn", id, barn });
      }));
      r.querySelectorAll("[data-kal-upd]").forEach((b) => b.addEventListener("click", () => { this._msg = { type: "info", text: "Hämtar…" }; this._kalHamta({ op: "uppdatera", id: b.dataset.kalUpd }); }));
      r.querySelectorAll("[data-kal-namn]").forEach((b) => b.addEventListener("click", () => { const n = this._ask("Nytt namn på kalendern:", ""); if (n) this._kalHamta({ op: "namn", id: b.dataset.kalNamn, namn: n }); }));
      r.querySelectorAll("[data-kal-bort]").forEach((b) => b.addEventListener("click", async () => { if (confirm("Ta bort kalendern? Händelserna försvinner från barnens förstasida.") && (await this._kalHamta({ op: "ta_bort", id: b.dataset.kalBort }))) { await this._load(this._s.barn); this._render(); } }));
    }
    r.querySelectorAll("[data-skolinfo-bort]").forEach((b) => b.addEventListener("click", async () => { if (await this._act("skolinfo_bort", { id: b.dataset.skolinfoBort })) await this._load(this._s.barn); }));
    on("#material-ja", () => this._go({ name: "amne", amne: r.querySelector("#material-ja").dataset.amne }));
    on("#material-sen", async () => { if (await this._act("laxfraga_svar", { material: r.querySelector("#material-sen").dataset.amne })) { await this._load(this._s.barn); this._render(); } });
    if (v.name === "lektioner") {
      const sok = $("#ls-sok");
      if (sok) { sok.addEventListener("input", () => this._schemaSok(sok.value)); if (v.sok) this._schemaSok(v.sok); }
      if (this._s.kan_valja) r.querySelectorAll("[data-ls-i]").forEach((b) => b.addEventListener("click", () => { v.red = Number(b.dataset.lsI); this._render(); setTimeout(() => this.shadowRoot.querySelector("#ls-red")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50); }));
      on("#ls-ny", () => { v.red = "ny"; this._render(); setTimeout(() => this.shadowRoot.querySelector("#ls-red")?.scrollIntoView({ behavior: "smooth", block: "center" }), 50); });
      on("#ls-utskrift", async () => {
        const w = window.open("", "_blank"); // öppnas direkt i klicket så att det inte blockeras
        try {
          const res = await this._hass.callWS({ type: "auth/sign_path", path: `/api/skolan/schema_sida?barn=${encodeURIComponent(this._s.barn)}`, expires: 300 });
          if (w) w.location.href = res.path; else window.location.href = res.path;
        } catch (e) { w?.close(); this._msg = { type: "error", text: `Kunde inte öppna schemat: ${e.message || e}` }; this._render(); }
      });
      on("#ls-tomt", () => { v.f = { lektioner: [], amnen: [] }; v.red = "ny"; this._render(); });
      on("#lr-avbryt", () => { v.red = null; this._render(); });
      on("#lr-min", () => { // delad tid: den här gäller barnet, de som krockar med den gäller den andra gruppen
        const min = (t) => { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; };
        const l = this._schemaLista().map((x) => ({ ...x }));
        const x = l[v.red], st = min(x.start), sl = min(x.slut) ?? st + 40;
        l.forEach((y, i) => { const a = min(y.start), b = min(y.slut) ?? a + 40;
          if (i === v.red) y.ej = false; else if (y.dag === x.dag && a != null && a < sl && b > st) y.ej = true; });
        this._schemaSpara(l);
      });
      on("#lr-bort", () => { const l = [...this._schemaLista()]; l.splice(v.red, 1); this._schemaSpara(l); });
      on("#lr-ok", () => {
        const g = (id) => r.querySelector(id).value.trim();
        const x = { dag: Number(g("#lr-dag")), start: g("#lr-start"), slut: g("#lr-slut"), namn: g("#lr-namn"), sal: g("#lr-sal"), larare: g("#lr-larare"), info: g("#lr-info") };
        if (!x.namn) { this._msg = { type: "error", text: "Skriv vilket ämne det är." }; return this._render(); }
        const l = [...this._schemaLista()];
        if (v.red === "ny") l.push(x); else l[v.red] = { ...l[v.red], ...x, amne: l[v.red].namn === x.namn ? l[v.red].amne : null };
        l.sort((a, b) => a.dag - b.dag || (a.start || "").localeCompare(b.start || ""));
        if (v.f && !v.f.amnen.some((a) => a.namn.toLowerCase() === x.namn.toLowerCase()) && !(this._s.data.amnen || []).some((a) => a.namn.toLowerCase() === x.namn.toLowerCase()))
          v.f.amnen.push({ namn: x.namn, amne: null });
        this._schemaSpara(l);
      });
    }
    r.querySelectorAll("[data-ls-skapa]").forEach((el) => el.addEventListener("change", () => { v.f.amnen[Number(el.dataset.lsSkapa)].skapa = el.checked; }));
    on("#ls-spara", async () => {
      const f = v.f;
      if (!f || !(await this._act("lektioner_spara", { lektioner: f.lektioner, skapa: f.amnen.filter((a) => !a.amne && a.skapa !== false).map((a) => a.namn) }))) return;
      if (v.inkorg) await this._skolaAct({ op: "inkorg_klar", id: v.inkorg });
      await this._load(this._s.barn);
      this._msg = { type: "ok", text: "Schemat är sparat! 🗓️" };
      this._go({ name: "lektioner" });
    });
    on("#kort-album", () => kortSett(true));
    on("#lar-start", () => this._go({ name: "lar", amne: v.amne, glosor: v.glosor }));
    on("#lar-skicka", () => this._larSkicka());
    on("#open-fraga", () => this._go({ name: "fraga" }));
    on("#open-hjalp", () => this._go({ name: "hjalp" }));
    const hjalpNy = (amne, uppdrag) => { this._hjalp = { barn: this._s.barn, historik: [], lage: uppdrag && (this._s.data.uppdrag || []).find((x) => x.id === uppdrag)?.typ === "prov" ? "forhor" : "forklara", amne, uppdrag: uppdrag || null }; };
    r.querySelectorAll("[data-hjalp-u]").forEach((b) => b.addEventListener("click", () => { const [a, u] = b.dataset.hjalpU.split("|"); hjalpNy(a, u); this._render(); }));
    r.querySelectorAll("[data-hjalp-prov]").forEach((b) => b.addEventListener("click", () => { const u = (this._s.data.uppdrag || []).find((x) => x.id === b.dataset.hjalpProv); if (!u) return; hjalpNy(u.amne, u.id); this._go({ name: "hjalp" }); }));
    r.querySelectorAll("[data-hjalp-lage]").forEach((b) => b.addEventListener("click", () => { if (this._hjalp.lage !== b.dataset.hjalpLage) { this._hjalp.lage = b.dataset.hjalpLage; this._hjalp.historik = []; } this._render(); }));
    on("#hjalp-byt", () => { this._hjalp = null; this._render(); });
    on("#hjalp-skicka", () => this._hjalpSkicka());
    on("#hjalp-starta", () => this._hjalpSkicka("Förhör mig!"));
    on("#hjalp-ny", () => this._hjalpSkicka("Jag vet inte, ge mig en ny fråga."));
    on("#hjalp-bild-bort", () => { this._hjalp.bild = null; this._render(); });
    on("#hjalp-likadan", () => this._hjalpSkicka("Ge mig en till likadan uppgift med andra siffror eller ord, så jag får öva. Säg inte svaret."));
    r.querySelectorAll("[data-hjalp-las]").forEach((b) => b.addEventListener("click", () => { const [a, u] = b.dataset.hjalpLas.split("|"); this._hjalp = { barn: this._s.barn, historik: [], lage: "las", amne: a, uppdrag: u }; this._go({ name: "hjalp" }); }));
    on("#open-svaga", () => this._go({ name: "svaga" }));
    // pluggplan
    r.querySelectorAll("[data-plan]").forEach((b) => b.addEventListener("click", () => this._go({ name: "plan", uppdrag: b.dataset.plan })));
    r.querySelectorAll("[data-ovp]").forEach((b) => b.addEventListener("click", () => this._go({ name: "ovningsprov", uppdrag: b.dataset.ovp })));
    r.querySelectorAll("[data-ovp-visa]").forEach((b) => b.addEventListener("click", () => this._go({ name: "ovningsprov", uppdrag: v.uppdrag, prov: b.dataset.ovpVisa })));
    r.querySelectorAll("[data-dl]").forEach((b) => b.addEventListener("click", () => {
      const m = this._s.dagens_lista.rader[Number(b.dataset.dl)]?.mal || {};
      if (m.forhor) this._go({ name: "forhor", forhor: m.forhor });
      else if (m.uppdrag) this._go({ name: "uppdrag", id: m.uppdrag });
      else if (m.plan) this._go({ name: "plan", uppdrag: m.plan });
      else if (m.svaga) this._go({ name: "svaga" });
    }));
    on("#dl-fokus", () => this._go({ name: "fokus" }));
    on("#open-rapport", () => this._go({ name: "rapport" }));
    on("#open-coach", () => this._go({ name: "coach" }));
    if (v.name === "coach") {
      const sync = () => { if (v.o) v.o.text = $("#coach-onsk")?.value ?? v.o.text; };
      r.querySelectorAll("[data-coach-str]").forEach((b) => b.addEventListener("click", () => { sync(); v.o.strikthet = b.dataset.coachStr; this._render(); }));
      on("#coach-spara", async () => { sync(); if (await this._plan("onskemal", { strikthet: v.o.strikthet, text: v.o.text })) { await this._load(this._s.barn); this._msg = { type: "ok", text: "Önskemålen är sparade. De vägs in i nästa plan. 🎛️" }; v.o = null; this._render(); } });
      r.querySelectorAll("[data-coach-anvand]").forEach((b) => b.addEventListener("click", async () => {
        const f = this._coach.historik[Number(b.dataset.coachAnvand)]?.onskemal;
        if (f && await this._plan("onskemal", f)) { await this._load(this._s.barn); this._msg = { type: "ok", text: "Förslaget är sparat som era önskemål. 🎛️" }; v.o = null; this._render(); }
      }));
      on("#coach-skicka", () => { sync(); this._coachSkicka(); });
      r.querySelectorAll("[data-coach-q]").forEach((b) => b.addEventListener("click", () => { sync(); this._coachSkicka(b.dataset.coachQ); }));
      $("#coach-text")?.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sync(); this._coachSkicka(); } });
    }
    on("#rap-ny", async () => { const x = await this._plan("rapport", { ny: true }); if (x) { v.r = x; this._render(); } });
    if (v.name === "plan") {
      const u = (this._s.data.uppdrag || []).find((x) => x.id === v.uppdrag), g = v.g;
      const om = () => { v.g = null; this._planGuide(u); this._render(); };
      on("#pd-om", om);
      on("#pd-om2", om);
      on("#pd-bort", async () => { if (confirm("Ta bort pluggplanen?") && await this._plan("plan_bort", { uppdrag: v.uppdrag })) await this._load(this._s.barn); this._render(); });
      r.querySelectorAll("[data-pd-klar]").forEach((b) => b.addEventListener("click", async () => {
        const d = u.plan.delar.find((x) => x.id === b.dataset.pdKlar);
        const x = await this._plan("del_klar", { uppdrag: v.uppdrag, del: d.id, klar: !d.klar });
        if (x) {
          if (!d.klar) this._fx({ text: x.alla ? "📅 HELA PLANEN KLAR!" : "✅ KLART!", sub: x.p ? `+${x.p} ⭐ · pluggdag mot provbossen` : "Pluggdag mot provbossen", emojis: ["📚", "⭐", "✅"], antal: x.alla ? 40 : 18, konfetti: !!x.alla, farg: "#43a047" });
          await this._load(this._s.barn);
          this._render();
        }
      }));
      r.querySelectorAll("[data-pd-start]").forEach((b) => b.addEventListener("click", () => {
        const t = b.dataset.pdStart;
        if (t === "ovningsprov") return this._go({ name: "ovningsprov", uppdrag: v.uppdrag });
        if (t === "repetera") return this._go({ name: "svaga" });
        const lage = { forhor: "forhor", glosor: "forhor", forklara: "forklara", uppgifter: "uppgift", sammanfatta: "skriv" }[t] || "forklara";
        this._hjalp = { barn: this._s.barn, historik: [], lage, amne: u.amne, uppdrag: u.id };
        this._go({ name: "hjalp" });
      }));
      if (g) {
        const sync = () => { g.omfattning = $("#pg-omf")?.value ?? g.omfattning; g.svart = $("#pg-svart")?.value ?? g.svart; };
        const klick = (attr, fn) => r.querySelectorAll(`[data-${attr}]`).forEach((b) => b.addEventListener("click", () => { sync(); fn(b.getAttribute(`data-${attr}`)); this._render(); }));
        klick("pg-typ", (x) => (g.provtyp = x));
        klick("pg-min", (x) => (g.min_dag = Number(x)));
        klick("pg-mal", (x) => (g.mal = x));
        klick("pg-dag", (x) => { const i = Number(x); g.dagar = g.dagar.includes(i) ? g.dagar.filter((y) => y !== i) : [...g.dagar, i].sort(); });
        klick("pg-ut", (x) => { g.uteslut = g.uteslut.includes(x) ? g.uteslut.filter((y) => y !== x) : [...g.uteslut, x]; });
        klick("pg-satt", (x) => { g.satt = g.satt.includes(x) ? g.satt.filter((y) => y !== x) : [...g.satt, x]; });
        klick("pg-kan", (x) => { const [i, k] = x.split(":").map(Number); g.omraden[i].kan = k; });
        klick("pg-bort", (x) => g.omraden.splice(Number(x), 1));
        const ny = () => { sync(); const t = ($("#pg-ny")?.value || "").trim(); if (t) { g.omraden.push({ namn: t, kan: 1 }); this._render(); } };
        on("#pg-ny-ok", ny);
        $("#pg-ny")?.addEventListener("keydown", (e) => { if (e.key === "Enter") ny(); });
        $("#pg-foto")?.addEventListener("change", (e) => { sync(); g.foton = [...g.foton, ...(e.target.files || [])].slice(0, 6); this._render(); });
        on("#pg-foto-bort", () => { sync(); g.foton = []; this._render(); });
        on("#pg-avbryt", () => { v.g = null; this._render(); });
        on("#pg-hitta", async () => {
          sync();
          const x = await this._plan("omraden", { uppdrag: v.uppdrag, provtyp: g.provtyp, omfattning: g.omfattning }, g.foton);
          if (x) {
            const har = new Set(g.omraden.map((o) => o.namn.toLowerCase()));
            g.omraden = [...g.omraden, ...x.omraden.filter((o) => !har.has(o.namn.toLowerCase()))];
            if (x.omfattning && !g.omfattning.includes(x.omfattning)) g.omfattning = (g.omfattning ? g.omfattning + "\n" : "") + x.omfattning;
            g.foton = [];
            this._render();
          }
        });
        on("#pg-skapa", async () => {
          sync();
          const x = await this._plan("plan_skapa", { uppdrag: v.uppdrag, provtyp: g.provtyp, omfattning: g.omfattning, omraden: g.omraden, min_dag: g.min_dag, dagar: g.dagar, satt: g.satt, svart: g.svart, mal: g.mal, uteslut: g.uteslut });
          if (x) { v.g = null; await this._load(this._s.barn); this._fx({ text: "📅 PLANEN ÄR KLAR!", emojis: ["📅", "✨", "📚"], antal: 24, farg: "#5c6bc0" }); this._render(); }
        });
      }
    }
    if (v.name === "ovningsprov") {
      on("#ovp-skapa", async () => { const x = await this._plan("ovningsprov_skapa", { uppdrag: v.uppdrag }); if (x) { v.p = x.prov; v.svar = []; v.res = null; v.ny = false; this._render(); } });
      on("#ovp-ny", () => { v.p = null; v.prov = null; v.res = null; v.svar = []; v.ny = true; this._render(); });
      r.querySelectorAll("[data-ovp-svar]").forEach((t) => t.addEventListener("input", () => { v.svar[Number(t.dataset.ovpSvar)] = t.value; }));
      r.querySelectorAll("[data-ovp-alt]").forEach((b) => b.addEventListener("click", () => { v.svar[Number(b.dataset.ovpAlt)] = b.dataset.alt; this._render(); }));
      on("#ovp-in", async (e) => {
        const id = e.currentTarget.dataset.prov, u = (this._s.data.uppdrag || []).find((x) => x.id === v.uppdrag);
        const o = v.p || (u.plan?.ovningsprov || []).find((x) => x.id === id);
        const tomma = o.fragor.filter((q, i) => !(v.svar[i] || "").trim()).length;
        if (tomma && !confirm(`${tomma} frågor är obesvarade. Lämna in ändå?`)) return;
        const x = await this._plan("ovningsprov_ratta", { uppdrag: v.uppdrag, prov: id, svar: o.fragor.map((q, i) => v.svar[i] || "") });
        if (x) {
          v.p = o; v.res = x;
          if (x.p) this._fx({ text: "🧪 ÖVNINGSPROV KLART!", sub: `${x.ratt} av ${x.av} rätt · +${x.p} ⭐`, emojis: ["🧪", "⭐", "🧠"], antal: 30, konfetti: x.ratt / x.av >= 0.8, farg: "#26a69a" });
          await this._load(this._s.barn);
          this._render();
        }
      });
    }
    if (v.name === "svaga") {
      on("#sv-visa", () => { v.visa = true; this._render(); });
      r.querySelectorAll("[data-sv]").forEach((b) => b.addEventListener("click", async () => {
        const x = this._s.svaga_idag[0];
        const res = await this._plan("svag_svar", { id: x.id, kunde: b.dataset.sv === "1" });
        if (res) { if (res.befast) this._fx({ text: "💪 BEFÄST!", sub: "Den sitter nu!", emojis: ["💪", "🧠", "✨"], antal: 20, farg: "#43a047" }); v.visa = false; await this._load(this._s.barn); this._render(); }
      }));
    }
    $("#hjalp-foto")?.addEventListener("change", (e) => { const f = e.target.files?.[0]; if (f) { this._hjalp.bild = f; this._render(); } });
    r.querySelector("#hjalp-text")?.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this._hjalpSkicka(); } });
    on("#fraga-skicka", () => this._fragaSkicka());
    r.querySelectorAll("[data-fraga]").forEach((b) => b.addEventListener("click", () => this._fragaSkicka(b.dataset.fraga)));
    r.querySelector("#fraga-text")?.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this._fragaSkicka(); } });
    on("#lar-igen", () => this._go({ name: "lar", amne: this._view.amne, glosor: this._view.glosor }));
    on("#lar-klar", () => this._go({ name: "glosor", amne: this._view.amne, glosor: this._view.glosor }));
    r.querySelectorAll("[data-fokus]").forEach((b) => b.addEventListener("click", async () => { if (await this._act("fokus_start", { min: Number(b.dataset.fokus) })) await this._load(this._s.barn); this._render(); }));
    on("#fokus-avbryt", async () => { if (confirm("Avbryta fokuspasset? Då blir det inga ⭐.") && await this._act("fokus_avbryt", {})) await this._load(this._s.barn); this._render(); });
    on("#fokus-klar", async () => { if (await this._act("fokus_klar", {})) { this._msg = { type: "ok", text: "⏱️ Bra fokuserat! 🎉" }; this._fx({ text: "⏱️ BRA FOKUSERAT!", emojis: ["⭐", "🧠", "✨", "💪"], antal: 30, konfetti: true, farg: "#26a69a", ljud: true }); await this._load(this._s.barn); } this._render(); });
    if ($("#fokus-tid") && !this._fokusTimer) { this._fokusTick(); this._fokusTimer = setInterval(() => this._fokusTick(), 1000); }
    r.querySelectorAll("[data-heja-las]").forEach((b) => b.addEventListener("click", async () => {
      if (await this._act("hejarop_las", { id: b.dataset.hejaLas })) { this._msg = { type: "ok", text: "💌 Lappen är sparad i hjärtat ❤️" }; this._fx({ emojis: ["💖", "💕", "❤️", "💗", "⭐"], antal: 34, farg: "#ec407a" }); await this._load(this._s.barn); }
      this._render();
    }));
    const hejaNar = $("#heja-nar"), hejaVarde = $("#heja-varde");
    hejaNar?.addEventListener("change", () => {
      hejaVarde.style.display = hejaNar.value === "nu" ? "none" : "";
      hejaVarde.type = hejaNar.value === "datum" ? "date" : "number";
      hejaVarde.placeholder = hejaNar.value === "svit" ? "dagar, t.ex. 5" : "";
      hejaVarde.value = "";
    });
    on("#heja-skicka", async () => {
      const text = $("#heja-text")?.value.trim();
      if (!text) return;
      if (await this._act("hejarop_ny", { text, nar: hejaNar.value, varde: hejaVarde.value, boost: Number($("#heja-boost").value) })) {
        this._msg = { type: "ok", text: "💌 Hejaropet är skickat!" }; await this._load(this._s.barn);
      }
      this._render();
    });
    r.querySelectorAll("[data-heja-bort]").forEach((b) => b.addEventListener("click", async () => {
      if (confirm("Ta bort hejaropet?") && await this._act("hejarop_bort", { id: b.dataset.hejaBort })) await this._load(this._s.barn);
      this._render();
    }));
    on("#gata-gissa", async () => {
      const v = $("#gata-svar")?.value.trim();
      if (!v) return;
      this._gataAndra = false;
      if (await this._act("gata_gissa", { svar: v })) { this._msg = { type: "ok", text: "Gissningen är sparad. Svaret kommer i morgon! 🤫" }; await this._load(this._s.barn); }
      this._render();
    });
    $("#gata-svar")?.addEventListener("keydown", (e) => { if (e.key === "Enter") $("#gata-gissa")?.click(); });
    on("#gata-andra", () => { this._gataAndra = true; this._render(); });
    on("#gata-visa", async () => {
      if (await this._act("gata_svar", {})) {
        await this._load(this._s.barn);
        const ig = this._s.dagens?.igar;
        if (ig?.ratt) this._fx({ text: "🧩 RÄTT!", sub: `+${this._s.dagens.p_gata} ⭐`, emojis: ["🧩", "⭐", "✨", "🎉"], antal: 30, konfetti: true, farg: "#43a047" });
        else this._fx({ text: "🔓", sub: ig?.svar || "", emojis: ["❓", "💡"], antal: 10, farg: "#7e57c2" });
      }
      this._render();
    });
    r.querySelectorAll("[data-ink-avvisa]").forEach((b) => b.addEventListener("click", () => confirm("Ta bort det här från inkorgen?") && this._skolaAct({ op: "inkorg_avvisa", id: b.dataset.inkAvvisa }, "Borttaget från inkorgen.")));
    r.querySelectorAll("[data-ink-spara]").forEach((b) => b.addEventListener("click", async () => {
      const v = r.querySelector(`[data-ink-amne="${b.dataset.inkSpara}"]`)?.value || "";
      if (!v) { this._msg = { type: "error", text: "Välj ett ämne först." }; this._render(); return; }
      const svar = await this._skolaAct({ op: b.dataset.inkTyp === "prov" ? "inkorg_prov" : "inkorg_material", id: b.dataset.inkSpara,
        ...(v.startsWith("ny:") ? { nytt_amne: v.slice(3) } : { amne: v }) }, b.dataset.inkTyp === "prov" ? "Provresultatet är sparat 📝" : "Materialet ligger nu i ämnet 📎");
      if (svar) await this._load(this._s.barn);
    }));
    r.querySelectorAll("[data-ink-schema]").forEach((b) => b.addEventListener("click", async () => {
      this._msg = { type: "info", text: "AI:n läser schemat… (tar några sekunder)" };
      this._render();
      const svar = await this._skolaAct({ op: "inkorg_schema", id: b.dataset.inkSchema });
      if (!svar?.forslag) return;
      this._go({ name: "lektioner", f: svar.forslag, inkorg: b.dataset.inkSchema });
      this._msg = { type: "ok", text: "Lärarens schema. Kolla och tryck Spara." };
      this._render();
    }));
    r.querySelectorAll("[data-ink-granska]").forEach((b) => b.addEventListener("click", async () => {
      const svar = await this._skolaAct({ op: "inkorg_forslag", id: b.dataset.inkGranska });
      if (!svar?.forslag) return;
      const f = svar.forslag;
      if (f.ord) f.ord.ord = f.ord.ord || [];
      this._go({ name: "veckobrev", f, inkorg: b.dataset.inkGranska, med: { las: !!f.las, skriv: !!f.skriv, ord: !!f.ord } });
      this._msg = { type: "ok", text: "Lärarens förslag. Kolla och tryck Spara." };
      this._render();
    }));
    on("#klass-synk", () => this._klassSynk());
    r.querySelectorAll("[data-grupp-klar]").forEach((b) => b.addEventListener("click", () => this._skolaAct({ op: "grupp_klar", id: b.dataset.gruppKlar }, "✅ Bra jobbat! Synka med läraren så ser hen det.")));
    on("#klass-anslut", () => this._klassSynk(true));
    on("#stund-ny", () => this._tillAct({ op: "stund_ny", gaster: [...r.querySelectorAll("[data-stund-gast]")].filter((x) => x.checked).map((x) => x.dataset.stundGast) }, "🤝 Pluggstunden är startad! Nu pluggar ni."));
    on("#duell-ny", () => {
      const g = (r.querySelector("#duell-glosa")?.value || "").split("|"), gast = r.querySelector("#duell-gast")?.value;
      this._tillAct({ op: "duell_ny", amne: g[0], glosor: g[1], gast }, "⚔️ Utmaningen är skickad!");
    });
    r.querySelectorAll("[data-stund-med]").forEach((b) => b.addEventListener("click", () => this._tillAct({ op: "stund_ga_med", id: b.dataset.stundMed }, "Du är med! Plugga på 💪")));
    r.querySelectorAll("[data-duell-med]").forEach((b) => b.addEventListener("click", async () => {
      if (await this._tillAct({ op: "duell_ga_med", id: b.dataset.duellMed })) this._go({ name: "duell", id: b.dataset.duellMed });
    }));
    r.querySelectorAll("[data-duell-se]").forEach((b) => b.addEventListener("click", () => this._go({ name: "duell", id: b.dataset.duellSe })));
    const dsvar = r.querySelector("#duell-svar");
    if (dsvar) {
      if (!this._duellFokus) { this._duellFokus = true; setTimeout(() => dsvar.focus(), 50); }
      const skicka = () => this._duellSvara(v.id, Number(dsvar.dataset.i), dsvar.value);
      dsvar.addEventListener("keydown", (e) => { if (e.key === "Enter") skicka(); });
      on("#duell-skicka", skicka);
    }
    on("#traning-kop", async () => {
      const n = this._s.arena?.traning?.nasta;
      if (!n || !confirm(`Träna ${this._s.meriter?.djur?.namn || "husdjuret"} till ${n.namn} för ${n.pris} ⭐?`)) return;
      if (await this._act("traning_kop")) { this._msg = { type: "ok", text: `🎓 ${n.namn}! Nu försvarar sig husdjuret bättre.` }; await this._load(); }
      this._render();
    });
    on("#lagstrid-start", () => this._lagstridStart());
    on("#lagstrid-fortsatt", () => this._go({ name: "lagstrid" }));
    on("#lagstrid-ge-upp", async () => { if (confirm("Ge upp lagstriden?") && (await this._act("lagstrid_ge_upp"))) { await this._load(); this._go({ name: "lag" }); } });
    r.querySelectorAll("[data-ls-mal]").forEach((b) => b.addEventListener("click", () => { this._lsMal = Number(b.dataset.lsMal); this._render(); }));
    r.querySelectorAll("[data-ls-drag]").forEach((b) => b.addEventListener("click", () => this._lagstridDrag(b.dataset.lsDrag)));
    r.querySelector("#ls-vidare")?.addEventListener("click", () => this._lagstridDrag(""));
    r.querySelector("#ls-klar")?.addEventListener("click", () => { this._lsSlut = null; this._go({ name: "lag" }); });
    r.querySelector("#lag-spara")?.addEventListener("click", () => this._lagSpara());
    r.querySelectorAll("[data-lag-bort]").forEach((b) => b.addEventListener("click", () => this._lagSpara(b.dataset.lagBort)));
    r.querySelectorAll("[data-lag-redigera]").forEach((b) => b.addEventListener("click", () => { this._lagRed = b.dataset.lagRedigera; this._render(); }));
    r.querySelectorAll("[data-arena-mot]").forEach((b) => b.addEventListener("click", () => this._arenaStart(b.dataset.arenaMot)));
    r.querySelectorAll("[data-revansch]").forEach((b) => b.addEventListener("click", async () => {
      if (this._busy || !(await this._act("revansch_start", { varld: b.dataset.revansch }))) return this._render();
      await this._load();
      this._arenaVisa();
    }));
    r.querySelectorAll("[data-arena-van]").forEach((b) => b.addEventListener("click", () => this._arenaStart(null, b.dataset.arenaVan)));
    r.querySelector("#arena-fortsatt")?.addEventListener("click", () => this._arenaVisa());
    r.querySelectorAll("[data-arena-repris]").forEach((b) => b.addEventListener("click", () => this._arenaRepris(b.dataset.arenaRepris)));
    on("#open-vanner", () => this._go({ name: "vanner" }));
    on("#van-smek-spara", () => this._vanOp("smeknamn", { namn: r.querySelector("#van-smek").value }));
    on("#van-smek-ok", () => this._vanOp("godkann_smeknamn"));
    on("#van-lagg", async () => { if (await this._vanOp("lagg_till", { kod: r.querySelector("#van-kod").value })) this._msg = { type: "ok", text: "Tillagd! 🤝" }; this._render(); });
    on("#van-synka", () => this._vanOp("synka"));
    on("#van-kopiera", async () => {
      try { await navigator.clipboard.writeText(this._vanner.kod); this._msg = { type: "ok", text: "Vänlänken är kopierad! 📋" }; }
      catch (e) { prompt("Kopiera vänlänken:", this._vanner.kod); }
      this._render();
    });
    on("#van-dela", async () => {
      const text = `Bli min vän i Läxspelet! 🤝`;
      if (navigator.share) { try { await navigator.share({ title: "Läxspelet", text, url: this._vanner.kod }); } catch (e) { /* avbröt */ } }
      else { try { await navigator.clipboard.writeText(this._vanner.kod); this._msg = { type: "ok", text: "Vänlänken är kopierad! 📋" }; this._render(); } catch (e) { prompt("Kopiera vänlänken:", this._vanner.kod); } }
    });
    r.querySelectorAll("[data-van-ut]").forEach((b) => b.addEventListener("click", () => this._vanOp("svar_utgaende", { kod: b.dataset.vanUt, ja: !!b.dataset.ja })));
    r.querySelectorAll("[data-van-in]").forEach((b) => b.addEventListener("click", () => this._vanOp("svar_inkommande", { kod: b.dataset.vanIn, ja: !!b.dataset.ja })));
    r.querySelectorAll("[data-van-bort]").forEach((b) => b.addEventListener("click", () => { if (confirm("Ta bort vännen?")) this._vanOp("ta_bort", { kod: b.dataset.vanBort }); }));
    on("#open-rum", () => this._go({ name: "rum" }));
    on("#open-pass", () => this._go({ name: "pass" }));
    r.querySelectorAll("[data-pass]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (await this._act("pass_hamta", { niva: Number(b.dataset.pass) })) this._msg = { type: "ok", text: "🎁 Belöningen är din!" };
        this._render();
      })
    );
    r.querySelectorAll("[data-variant]").forEach((b) => b.addEventListener("click", () => this._act("djur_pa", { typ: "variant", sak: b.dataset.variant || null })));
    r.querySelectorAll("[data-rum-pa]").forEach((b) => b.addEventListener("click", () => this._act("rum_stall", { plats: b.dataset.plats, sak: b.dataset.rumPa })));
    r.querySelectorAll("[data-rum-av]").forEach((b) => b.addEventListener("click", () => this._act("rum_stall", { plats: b.dataset.rumAv, sak: null })));
    on("#open-widget", async () => {
      this._go({ name: "widget" });
      try {
        const res = await this._hass.fetchWithAuth(`/api/skolan/widgetnyckel?barn=${encodeURIComponent(this._s.barn)}`);
        const x = await res.json();
        if (!res.ok) throw new Error(x.message || res.statusText);
        this._view.kod = x.kod;
        this._view.installera = x.installera;
      } catch (e) {
        this._msg = { type: "error", text: e.message || String(e) };
      }
      this._render();
    });
    on("#kopiera-widget", async () => {
      try { await navigator.clipboard.writeText(this._view.kod); } catch (e) { this._msg = { type: "error", text: "Kunde inte kopiera." }; return this._render(); }
      this._msg = { type: "ok", text: "Koden är kopierad! Klistra in den i Scriptable. 📋" };
      this._render();
    });
    r.querySelectorAll("[data-djur-kop]").forEach((b) =>
      b.addEventListener("click", async () => {
        const x = (this._s.djurbutik || []).find((y) => y.id === b.dataset.djurKop);
        if (!x || !confirm(`Köpa ${x.namn} ${x.ikon} för ${x.pris} ⭐?`)) return;
        if (await this._act("djur_kop", { sak: x.id })) this._msg = { type: "ok", text: `${x.ikon} ${x.namn} är köpt!` };
        this._render();
      })
    );
    r.querySelectorAll("[data-attack-upp]").forEach((b) =>
      b.addEventListener("click", async () => {
        const x = (this._s.karta?.attacker || []).find((y) => y.id === b.dataset.attackUpp);
        if (!x || !confirm(`Träna upp ${x.namn} ${x.ikon} till nivå ${x.lvl + 1} för ${x.lvl_pris} ⭐? Skadan blir ${x.skada_nasta} i stället för ${x.skada_lvl}.`)) return;
        if (await this._act("attack_upp", { attack: x.id })) { this._msg = { type: "ok", text: `⬆️ ${x.ikon} ${x.namn} är nu nivå ${x.lvl + 1}! 💪` }; this._fx({ text: `⬆️ NIVÅ ${x.lvl + 1}!`, sub: `${x.ikon} ${x.namn}`, emojis: [x.ikon, "⚡", "✨", "💥"], antal: 30, farg: "#ff7043" }); await this._load(); }
        this._render();
      })
    );
    r.querySelectorAll("[data-attack-kop]").forEach((b) =>
      b.addEventListener("click", async () => {
        const x = (this._s.karta?.attacker || []).find((y) => y.id === b.dataset.attackKop);
        if (!x || !confirm(`Lära ${this._s.meriter?.djur?.namn || "husdjuret"} ${x.namn} ${x.ikon} för ${x.pris} ⭐?`)) return;
        if (await this._act("attack_kop", { attack: x.id })) { this._msg = { type: "ok", text: `${x.ikon} ${x.namn} är inlärd! Använd den på bossen.` }; await this._load(); }
        this._render();
      })
    );
    r.querySelectorAll("[data-skold-kop]").forEach((b) =>
      b.addEventListener("click", async () => {
        const x = (this._s.karta?.forsvar?.skoldar || []).find((y) => y.id === b.dataset.skoldKop);
        if (!x || !confirm(`Köpa ${x.namn} ${x.ikon} (DEF ${x.def}) för ${x.pris} ⭐?`)) return;
        if (await this._act("skold_kop", { skold: x.id })) { this._msg = { type: "ok", text: `${x.ikon} ${x.namn} är på! 🛡️ DEF ${x.def}` }; await this._load(); }
        this._render();
      })
    );
    r.querySelectorAll("[data-skold-pa]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (await this._act("skold_pa", { skold: b.dataset.skoldPa })) await this._load();
        this._render();
      })
    );
    r.querySelectorAll("[data-energi-kop]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (await this._act("energi_kop", { n: Number(b.dataset.energiKop) })) {
          this._msg = { type: "ok", text: `+${b.dataset.energiKop} ⚡ energi!` };
          this._load();
        }
      })
    );
    r.querySelectorAll("[data-dryck-kop]").forEach((b) =>
      b.addEventListener("click", async () => {
        const x = (this._s.karta?.drycker || []).find((y) => y.id === b.dataset.dryckKop);
        if (!x || !confirm(`Köpa ${x.namn} ${x.ikon} för ${x.pris} ⭐?`)) return;
        if (await this._act("dryck_kop", { dryck: x.id })) { this._msg = { type: "ok", text: `${x.ikon} ${x.namn} ligger i ryggsäcken 🎒` }; await this._load(); }
        this._render();
      })
    );
    r.querySelectorAll("[data-dryck]").forEach((b) =>
      b.addEventListener("click", async () => {
        const x = (this._s.karta?.drycker || []).find((y) => y.id === b.dataset.dryck);
        if (!x || this._busy) return;
        const fore = this._s.karta.liv;
        if (await this._act("dryck", { dryck: x.id })) {
          await this._load();
          const nu = this._s.karta?.liv ?? fore;
          this._msg = { type: "ok", text: `${x.ikon} Glugg glugg! ${this._s.meriter?.djur?.namn || "Husdjuret"} fick +${nu - fore} ❤️` };
        }
        this._render();
      })
    );
    r.querySelectorAll("[data-repris]").forEach((b) => b.addEventListener("click", () => this._spelaRepris(b.dataset.repris)));
    r.querySelectorAll("[data-attack]").forEach((b) =>
      b.addEventListener("click", async () => {
        this._gorAttack(b.dataset.attack);
      })
    );
    r.querySelector("#till-strid")?.addEventListener("click", () => this._strid(this._stridLage({ idle: true, titta: !!this._s.kan_valja })));
    r.querySelectorAll("[data-djur-pa]").forEach((b) => b.addEventListener("click", async () => {
      const ok = await this._act("djur_pa", { typ: b.dataset.typ, sak: b.dataset.djurPa });
      if (ok && b.dataset.typ === "kompis") { // en liten ledtråd om kompisens hemliga boost, inga siffror
        await this._load(this._s.barn);
        const d = this._s.meriter?.djur, ikon = b.dataset.ikon || "✨";
        const rad = ["viskar något i örat på", "blinkar hemlighetsfullt mot", "ger en hemlig high five till", "delar ett hemligt mellanmål med"];
        if (d?.bastis) this._fx({ text: "💞 BÄSTISAR!", emojis: ["💞", "💖", ikon, "✨"], antal: 32, farg: "#ec407a" });
        this._msg = { type: "ok", text: d?.bastis ? `💞 ${ikon} och ${d.art} ${d.namn || ""} är bästisar! Tillsammans känns de extra starka… ✨`
          : `${ikon} ${rad[Math.floor(Math.random() * rad.length)]} ${d?.namn || "ditt husdjur"}… ✨` };
        this._render();
      }
    }));
    r.querySelectorAll("[data-djur-av]").forEach((b) => b.addEventListener("click", () => this._act("djur_pa", { typ: b.dataset.djurAv, sak: null })));
    r.querySelectorAll("[data-upps]").forEach((b) => b.addEventListener("click", () => this._act("uppsattning", { attack: b.dataset.upps })));
    r.querySelectorAll("[data-djur-till]").forEach((b) => b.addEventListener("click", async () => {
      const h = (this._s.meriter?.djur?.mina || []).find((x) => x.id === b.dataset.djurTill);
      if (h && await this._act("djur", { id: h.id, art: h.art, namn: "" })) this._msg = { type: "ok", text: `${h.art} ${h.namn} är med dig nu! Allt du gör nu hjälper ${h.namn} att växa.` };
      this._render();
    }));
    r.querySelectorAll("[data-djur-nytt]").forEach((b) => b.addEventListener("click", async () => {
      const art = b.dataset.djurNytt, gratis = b.dataset.gratis === "1";
      if (!confirm(`Skaffa ${art}${gratis ? "" : ` för ${this._s.nytt_djur_pris} ⭐`}? Det börjar om från början, utan attacker och kompisar. Dina andra djur finns kvar med allt de har.`)) return;
      const namn = this._ask("Vad ska ditt nya husdjur heta?", "");
      if (namn === null) return;
      if (await this._act("djur", { art, namn: namn || "" })) this._fx({ text: "🥚 NYTT HUSDJUR!", sub: `${art} ${namn || ""}`, emojis: ["🥚", art, "✨", "💖"], antal: 28, farg: "#ffb300" });
      this._render();
    }));
    r.querySelectorAll("[data-paket]").forEach((b) =>
      b.addEventListener("click", async () => {
        const p = (this._s.paket || []).find((x) => x.id === b.dataset.paket);
        if (!p || !confirm(`Köpa ${p.namn} för ${p.pris} ⭐?${p.djur ? " Du får ett exklusivt husdjur!" : ""}`)) return;
        if (await this._act("djur_paket", { paket: p.id })) this._msg = { type: "ok", text: `📦 ${p.namn} är ditt! ${p.djur ? "Säg hej till ditt nya husdjur!" : ""}` };
        this._render();
      })
    );
    on("#djur-dop", async () => {
      const d = this._s.meriter?.djur;
      const namn = this._ask("Vad ska husdjuret heta?", d?.namn || "");
      if (namn) await this._act("djur", { art: d.art, namn });
    });
    // Glosrekord
    on("#rekord-start", () => this._go({ name: "rekord", amne: v.amne, glosor: v.glosor }));
    on("#glosstrid-start", () => this._go({ name: "glosstrid", amne: v.amne, glosor: v.glosor, fran: "glosor" }));
    on("#glosstrid-val", () => this._go({ name: "glosstrid" }));
    r.querySelectorAll("[data-gs-lista]").forEach((b) => b.addEventListener("click", () => { const [am, gl] = b.dataset.gsLista.split("|"); this._go({ name: "glosstrid", amne: am, glosor: gl }); }));
    on("#gs-skicka", () => this._glosstridSvar());
    $("#gs-svar")?.addEventListener("keydown", (e) => { if (e.key === "Enter") this._glosstridSvar(); });
    on("#gs-nasta", () => this._gsNasta());
    on("#gs-igen", () => { const v2 = this._view; this._go({ name: "glosstrid", amne: v2.amne, glosor: v2.glosor, fran: v2.fran }); });
    on("#gs-klar", () => this._go(this._view.fran === "glosor" ? { name: "glosor", amne: this._view.amne, glosor: this._view.glosor } : { name: "hem" }));
    on("#rekord-go", () => this._rekordStart());
    on("#rekord-tillbaka", () => this._go({ name: "glosor", amne: v.amne, glosor: v.glosor }));
    r.querySelectorAll("[data-rek]").forEach((b) =>
      b.addEventListener("click", () => {
        const sp = v.spel;
        if (!sp || sp.klar || sp.flash) return;
        const val = sp.fraga.alt[Number(b.dataset.rek)];
        if (val === sp.fraga.svar) {
          sp.poang++;
          sp.flash = "ratt-flash";
          this._render();
          setTimeout(() => { if (!sp.klar) { this._rekordFraga(); this._render(); } }, 150);
        } else {
          sp.fel++;
          sp.slut -= 3000; // fel kostar 3 sekunder
          sp.flash = "fel-flash";
          this._render();
          setTimeout(() => { if (!sp.klar) { this._rekordFraga(); this._render(); } }, 900);
        }
      })
    );
    // inspelning av högläsning
    r.querySelectorAll("[data-insp-start]").forEach((b) => b.addEventListener("click", () => this._inspStart(b.dataset.inspStart)));
    on("#insp-stopp", () => this._insp?.rec?.stop());
    on("#insp-om", () => { const uid = this._insp?.uid; this._inspAvbryt(); this._inspStart(uid); });
    on("#insp-skicka", () => this._inspSkicka());
    r.querySelectorAll("[data-live]").forEach((b) => b.addEventListener("click", () => this._liveStart(b.dataset.live)));
    on("#live-stopp", () => { this._liveStopp(); this._render(); });
    r.querySelectorAll("[data-lyssna]").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          this._lyssna = { fil: b.dataset.lyssna, url: await this._blob(b.dataset.lyssna) };
        } catch (e) {
          this._msg = { type: "error", text: e.message };
        }
        this._render();
      })
    );
    // högläsning och läxbok
    on("#hogl-klar", async () => {
      if (await this._uppdragAct("hogl_klar", { id: v.id })) {
        this._msg = { type: "ok", text: "Snyggt! Mamma eller pappa får en fråga om att godkänna. 🗣️" };
        this._render();
      }
    });
    on("#skriv-klar", async () => {
      if (await this._uppdragAct("skriv_klar", { id: v.id })) {
        this._msg = { type: "ok", text: "Bra! Mamma eller pappa får en fråga om att kolla och godkänna. ✍️" };
        this._render();
      }
    });
    r.querySelectorAll("[data-man-ova]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (await this._act("manuell_ovning", { amne: v.amne, glosor: v.glosor, datum: b.dataset.manOva })) this._msg = { type: "ok", text: "Övningen är registrerad ✍️" };
        this._render();
      })
    );
    r.querySelectorAll("[data-angra-ova]").forEach((b) =>
      b.addEventListener("click", async () => {
        const d = b.dataset.angraOva;
        if (!confirm(`Ta bort övningen ${veckodag(d)}? Meriterna för den dagen dras tillbaka.`)) return;
        if (await this._act("angra_ovning", { amne: v.amne, glosor: v.glosor, datum: d })) this._msg = { type: "ok", text: "Övningen är borttagen ↩️" };
        this._render();
      })
    );
    on("#ova-papper", async () => {
      if (await this._uppdragAct("ova_papper", { amne: v.amne, glosor: v.glosor })) {
        this._msg = { type: "ok", text: "Bra! Visa mamma eller pappa, så får de en fråga om att godkänna. ✍️" };
        this._render();
      }
    });
    r.querySelectorAll("[data-godkann-glosor]").forEach((b) =>
      b.addEventListener("click", () => this._uppdragAct("godkann", { id: `glosor-${v.glosor}`, datum: b.dataset.godkannGlosor, ok: b.dataset.ok === "1" }))
    );
    r.querySelectorAll("[data-man-plugg]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (await this._act("manuell_plugg", { id: v.id, datum: b.dataset.manPlugg })) this._msg = { type: "ok", text: "Pluggdagen är registrerad 📚" };
        this._render();
      })
    );
    r.querySelectorAll("[data-hogl-bocka]").forEach((b) =>
      b.addEventListener("click", () => this._uppdragAct("hogl_klar", { id: v.id, datum: b.dataset.hoglBocka }))
    );
    r.querySelectorAll("[data-godkann]").forEach((b) =>
      b.addEventListener("click", () => this._uppdragAct("godkann", { id: v.id, datum: b.dataset.godkann || null, ok: b.dataset.ok === "1" }))
    );
    // läxschema
    r.querySelectorAll("[data-sch]").forEach((el) =>
      el.addEventListener("change", () => {
        const x = v.schema[Number(el.dataset.sch)];
        x[el.dataset.f] = el.dataset.f === "kommer" ? Number(el.value) : el.dataset.f === "forhor" ? (el.value === "" ? null : Number(el.value)) : el.value;
      })
    );
    on("#sch-add", () => { v.schema.push({ namn: "", amne: "", typ: "glosor", kommer: 0, forhor: null }); this._render(); });
    r.querySelectorAll("[data-sch-del]").forEach((b) =>
      b.addEventListener("click", () => { v.schema.splice(Number(b.dataset.schDel), 1); this._render(); })
    );
    on("#sch-spara", async () => {
      r.querySelectorAll("[data-sch][data-f=namn]").forEach((el) => (v.schema[Number(el.dataset.sch)].namn = el.value));
      if (v.schema.some((x) => !x.namn.trim() || !x.amne)) {
        this._msg = { type: "error", text: "Varje läxa behöver ett namn och ett ämne." };
        return this._render();
      }
      if (await this._act("schema_spara", { schema: v.schema })) {
        delete v.schema;
        this._msg = { type: "ok", text: "Läxschemat är sparat." };
        this._load();
      }
    });
    r.querySelectorAll("[data-man-sch]").forEach((b) =>
      b.addEventListener("click", async () => {
        if (await this._act("manuell_schema", { schema: b.dataset.manSch, ankomst: b.dataset.ank, i_tid: b.dataset.itid === "1" })) this._load();
      })
    );
    r.querySelectorAll("[data-bonus]").forEach((b) =>
      b.addEventListener("click", async () => {
        const orsak = this._ask("Varför? (syns för barnet)", "Bra jobbat!");
        if (orsak !== null && (await this._act("bonus", { poang: Number(b.dataset.bonus), orsak }))) this._load();
      })
    );
    on("#bonus-egen", async () => {
      const p = Number(this._ask("Hur många meriter? (minus för att dra av)", "15"));
      if (!p) return;
      const orsak = this._ask("Varför? (syns för barnet)", p > 0 ? "Bra jobbat!" : "");
      if (orsak !== null && (await this._act("bonus", { poang: p, orsak }))) this._load();
    });
    const butik = async (op, args) => {
      try {
        const res = await this._hass.fetchWithAuth("/api/skolan/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ barn: this._s.barn, op, ...args }),
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.message || res.statusText);
        this._s.butik = body.butik;
      } catch (e) {
        this._msg = { type: "error", text: e.message || String(e) };
      }
      this._render();
    };
    on("#butik-add", () => {
      const namn = this._ask("Belöning (t.ex. 30 min extra skärmtid):", "");
      if (!namn) return;
      const kostnad = Number(this._ask("Hur många meriter kostar den?", "200"));
      if (kostnad > 0) butik("butik_lagg_till", { namn, kostnad });
    });
    r.querySelectorAll("[data-butik-del]").forEach((b) =>
      b.addEventListener("click", () => { if (confirm("Ta bort belöningen?")) butik("butik_ta_bort", { id: b.dataset.butikDel }); })
    );
    r.querySelectorAll("[data-los-in]").forEach((b) =>
      b.addEventListener("click", async () => {
        const bel = this._s.butik.beloningar.find((x) => x.id === b.dataset.losIn);
        if (bel && confirm(`Lös in "${bel.namn}" för ${bel.kostnad} ⭐ åt ${this._s.namn}?`) && (await this._act("los_in", { beloning: bel.id }))) {
          this._msg = { type: "ok", text: `${bel.namn} inlöst! 🎁` };
          this._load();
        }
      })
    );
    const fhSvara = async () => {
      const f = (this._s.data.forhor || []).find((x) => x.id === v.forhor);
      if (!f || this._busy) return;
      const i = f.svar.length;
      const sista = i === f.fragor.length - 1;
      const svar = $("#fh-svar")?.value || "";
      if (!svar.trim() && !confirm("Du har inte skrivit något. Gå vidare ändå?")) return;
      const ok = await this._forhorAct("svara", { forhor: f.id, index: i, svar });
      if (ok && !sista) fhLas();
      if (ok && sista) {
        this._msg = { type: "ok", text: "Inlämnat! Här är ditt resultat." };
        try { if (document.fullscreenElement) document.exitFullscreen(); } catch (e) { /* ok */ }
      }
      this._render();
    };
    on("#fh-svara", fhSvara);
    $("#fh-svar")?.addEventListener("keydown", (e) => { if (e.key === "Enter") fhSvara(); });
    r.querySelectorAll("[data-fh-andra]").forEach((b) =>
      b.addEventListener("click", () => this._forhorAct("andra", { forhor: v.forhor, index: Number(b.dataset.fhAndra) }))
    );
    r.querySelectorAll("[data-fh-bedom]").forEach((b) =>
      b.addEventListener("click", async () => {
        const beslut = b.dataset.fhBedom;
        const f = (this._s.data.forhor || []).find((x) => x.id === v.forhor);
        if (!f || f.bedomning === beslut) return;
        if (beslut === "ej_godkant" && !confirm(`Underkänna förhöret? ${this._s.namn} får ett nytt förhör på samma ord.`)) return;
        if (await this._forhorAct("bedom", { forhor: v.forhor, bedomning: beslut })) {
          this._msg = { type: "ok", text: beslut === "godkant" ? `Godkänt! ${this._s.namn} får fanfar och konfetti 🎉` : `Nytt förhör skickat till ${this._s.namn} 📨` };
          this._render();
        }
      })
    );
    on("#fh-paminn", async () => {
      if (await this._forhorAct("paminn", { forhor: v.forhor })) {
        this._msg = { type: "ok", text: `Påminnelse skickad till ${this._s.namn} 🔔` };
        this._render();
      }
    });
    on("#fh-ta-bort", async () => {
      if (confirm("Ta bort förhöret?") && (await this._forhorAct("ta_bort", { forhor: v.forhor }))) this._go({ name: "hem" });
    });
    r.querySelectorAll("[data-exempel]").forEach((b) =>
      b.addEventListener("click", () => {
        const nyckel = `${v.glosor}:${b.dataset.exempel}`;
        if (this._exVisa?.has(nyckel)) { this._exVisa.delete(nyckel); return this._render(); }
        this._exempel(v.amne, v.glosor, Number(b.dataset.exempel));
      })
    );
    r.querySelectorAll("[data-exempel-ny]").forEach((b) => b.addEventListener("click", () => this._exempel(v.amne, v.glosor, Number(b.dataset.exempelNy), true)));
    on("#ova-exempel", () => this._exempel(v.amne, v.glosor, v.ova.kvar[0].i));
    on("#ova-svara", () => this._go({ name: "ova", amne: v.amne, glosor: v.glosor, svara: true }));
    on("#edit-glosor", () => {
      const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
      this._go({ name: "redigera", amne: v.amne, glosor: g.id, typ: gTyp(g), namn: g.namn, forhor: g.forhor || "", sprak: [...g.sprak], par: g.par.map((p) => [...p]) });
    });
    on("#del-glosor", async () => {
      if (confirm(LISTTYP[gTyp(this._amne(v.amne).glosor.find((x) => x.id === v.glosor))].bort)) {
        if (await this._act("del_glosor", { amne: v.amne, glosor: v.glosor })) this._go({ name: "amne", amne: v.amne });
      }
    });

    // redigera glosor
    const syncForm = () => {
      if (v.name !== "redigera") return;
      v.namn = $("#g-namn")?.value ?? v.namn;
      v.forhor = $("#g-forhor")?.value ?? v.forhor;
      v.sprak = (v.typ || "glosor") === "glosor" ? [$("#g-s0")?.value ?? "", $("#g-s1")?.value ?? ""] : [...LISTTYP[v.typ].sprak];
      const par = v.par.length ? v.par : [["", ""]];
      r.querySelectorAll("[data-p]").forEach((inp) => {
        par[Number(inp.dataset.p)][Number(inp.dataset.k)] = inp.value;
      });
      v.par = par;
    };
    $("#glosfoto")?.addEventListener("change", (e) => {
      syncForm();
      const f = e.target.files[0];
      if (f) this._readGlosor(f);
    });
    on("#add-par", () => {
      syncForm();
      v.par.push(["", ""]);
      this._render();
      const inputs = r.querySelectorAll('[data-k="0"]');
      inputs[inputs.length - 1]?.focus();
    });
    r.querySelectorAll("[data-del-par]").forEach((b) =>
      b.addEventListener("click", () => {
        syncForm();
        v.par.splice(Number(b.dataset.delPar), 1);
        this._render();
      })
    );
    on("#save-glosor", async () => {
      syncForm();
      const par = v.par.filter((p) => p[0].trim() || p[1].trim());
      if (!v.namn.trim()) {
        this._msg = { type: "error", text: "Ge listan ett namn." };
        return this._render();
      }
      const ok = await this._act("save_glosor", { amne: v.amne, glosor: v.glosor || null, typ: v.typ || "glosor", namn: v.namn, sprak: v.sprak, par, forhor: v.forhor || null });
      if (ok) {
        const a = this._amne(v.amne);
        const g = v.glosor ? a.glosor.find((x) => x.id === v.glosor) : a.glosor[a.glosor.length - 1];
        this._go({ name: "glosor", amne: v.amne, glosor: g.id });
      }
    });

    // öva
    r.querySelectorAll("[data-start]").forEach((b) =>
      b.addEventListener("click", () => this._startOva(Number(b.dataset.start)))
    );
    const check = async () => {
      const o = v.ova;
      const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
      const k = o.kvar[0];
      const skrev = $("#svar")?.value || "";
      if (this._busy) return;
      const facit = k.fran < 0 ? g.par[k.i][0] : g.par[k.i][1 - k.fran];
      const ratt = answers(facit);
      const formel = gTyp(g) === "formler" && k.fran === 0;
      const ok = formel
        ? !!formelNorm(skrev) && String(facit).split(/;| eller /).map(formelNorm).includes(formelNorm(skrev))
        : ratt.includes(norm(skrev)) || (ratt.length > 1 && norm(skrev) === norm(facit));
      // 2 gratis försök per ord. Sedan kostar ett FEL svar 1 ⭐ (rätt svar är alltid gratis, liksom tomma svar och föräldrar).
      if (skrev.trim()) {
        o.forsok = o.forsok || {};
        if (!ok && !this._s.kan_valja && (o.forsok[k.i] || 0) >= 2) {
          o.utkast = skrev;
          if (!(await this._act("ova_forsok"))) return;
          o.utkast = "";
        }
        o.forsok[k.i] = (o.forsok[k.i] || 0) + 1;
      }
      o.skrev = skrev;
      o.visat = ok ? "ratt" : "fel";
      this._render();
    };
    on("#kolla", check);
    $("#svar")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") check();
    });
    on("#visa", () => {
      v.ova.visat = "visa";
      v.ova.skrev = "";
      this._render();
    });
    on("#hade-ratt", () => {
      const o = v.ova, k = o.kvar[0];
      if (!this._s.kan_valja) {  // barn: klart, men inte rätt på första försöket (inga extra meriter)
        o.fel.add(k.i);
        if (!(k.i in o.forsta)) o.forsta[k.i] = false;
      }
      o.visat = "ratt";
      this._next();
    });
    on("#nasta", () => this._next());
    on("#tips", async () => {
      const o = v.ova;
      const k = o.kvar[0];
      const saldo = this._s.data.meriter?.saldo ?? 0;
      if (!this._s.kan_valja && saldo < 1) { this._msg = { type: "error", text: "Du behöver 1 ⭐ för ett tips." }; this._render(); return; }
      o.utkast = $("#svar")?.value || "";
      if (await this._act("ova_tips")) {
        o.tips = o.tips || {};
        o.tips[k.i] = (o.tips[k.i] || 0) + 1;
        o.fel.add(k.i); // med tips räknas det inte som rätt på första försöket
        if (!(k.i in o.forsta)) o.forsta[k.i] = false;
      }
      this._render();
    });
    on("#gom", () => { clearTimeout(this._gomTimer); v.ova.tittar = false; this._render(); });
    on("#lyssna", () => {
      const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
      las_upp(g.par[v.ova.kvar[0].i][0], g.sprak[0], this._hass);
    });
    on("#igen", () => this._startOva(v.ova.lage));
    on("#till-glosor", () => this._go({ name: "glosor", amne: v.amne, glosor: v.glosor }));
  }

  _startOva(lage) {
    const v = this._view;
    const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
    let index = g.par.map((_, i) => i);
    if (v.svara) {
      const s = this._svara(g);
      if (s.length) index = s;
    }
    const kvar = shuffle(index.map((i) => ({ i, fran: lage === 4 ? -2 : lage === 3 ? -1 : lage === 2 ? Math.round(Math.random()) : lage })));
    v.ova = { lage, kvar, totalt: kvar.length, forstaRatt: 0, fel: new Set(), forsta: {}, visat: null, skrev: "" };
    if (lage === 4) this._tittaStart();
    this._render();
    if (lage === 3) las_upp(g.par[kvar[0].i][0], g.sprak[0], this._hass); // första uppläsningen i klicket (krävs på iPhone)
  }

  // "Jag hade rätt" (t.ex. en synonym eller ett litet stavfel som borde godkännas).
  // Barn: bara efter ett eget svar som ligger nära rätt svar, och ordet räknas inte som rätt på första försöket.
  _hadeRattOk(o, svar) {
    if (o.visat === "ratt") return false;
    if (this._s.kan_valja) return true;
    if (o.visat !== "fel" || !o.skrev.trim()) return false;
    const n = narmast(o.skrev, svar);
    return n.avstand <= Math.max(1, Math.floor(String(svar).length / 4));
  }

  _tittaStart() {
    // Titta, göm och skriv: ordet syns i 4 sekunder och göms sedan.
    const o = this._view.ova;
    o.tittar = true;
    clearTimeout(this._gomTimer);
    this._gomTimer = setTimeout(() => {
      if (this._view.ova === o && o.tittar) { o.tittar = false; this._render(); }
    }, 4000);
  }

  _next() {
    const v = this._view;
    const o = v.ova;
    const k = o.kvar.shift();
    if (!(k.i in o.forsta)) o.forsta[k.i] = o.visat === "ratt";
    if (o.visat === "ratt") {
      if (!o.fel.has(k.i)) o.forstaRatt++;
    } else {
      o.fel.add(k.i);
      o.kvar.push(k); // fel → kommer tillbaka på slutet
    }
    o.visat = null;
    o.skrev = "";
    o.utkast = "";
    if (!o.kvar.length) {
      const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
      const ord = Object.entries(o.forsta).map(([i, r]) => ({ o: g.par[i][0], r }));
      this._act("ova_resultat", { amne: v.amne, glosor: v.glosor, ratt: o.forstaRatt, av: o.totalt, ord });
    } else {
      this._render();
      const n = o.kvar[0];
      if (n.fran === -2) { this._tittaStart(); this._render(); }
      if (n.fran === -1) {
        const g = this._amne(v.amne).glosor.find((x) => x.id === v.glosor);
        las_upp(g.par[n.i][0], g.sprak[0], this._hass);
      }
    }
  }

  async _afterRender() {
    const r = this.shadowRoot;
    // Vilken e-bokssida är öppen? Byt sida = skicka tiden för den förra.
    const ev = this._view;
    const nyckel = ev.name === "ebok" && ev.e?.sidor?.[ev.e.idx] && !ev.e.visaToc ? `${ev.e.sidor[ev.e.idx].fil}#${ev.e.sidor[ev.e.idx].del}` : null;
    if (nyckel !== this._las?.nyckel) {
      this._lasFlush(true);
      this._las = nyckel ? { nyckel, t0: Date.now() } : null;
    }
    r.querySelector("#svar")?.focus();
    r.querySelector("#fh-svar")?.focus();
    this._fhFira();
    clearTimeout(this._fhPoll);
    const v = this._view;
    const f = v.name === "forhor" && (this._s?.data?.forhor || []).find((x) => x.id === v.forhor);
    if (f && this._s.kan_valja && f.status !== "klart") {
      this._fhPoll = setTimeout(async () => {
        if (this._view === v && !this._busy) await this._load();
      }, 5000);
    }
    r.querySelector("#nasta")?.focus();
    for (const img of r.querySelectorAll("img[data-fil]")) {
      try {
        img.src = await this._blob(img.dataset.fil);
      } catch (e) {
        img.alt = "Kunde inte visa";
      }
    }
  }
}

const CSS = `
  :host { display:block; height:100%; background:var(--primary-background-color); color:var(--primary-text-color);
          font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .toolbar { display:flex; align-items:center; gap:8px; height:56px; padding:0 12px; background:var(--app-header-background-color, var(--primary-color));
             color:var(--app-header-text-color, #fff); position:sticky; top:0; z-index:2; }
  .title { font-size:20px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .icon { background:none; border:none; color:inherit; font-size:22px; cursor:pointer; padding:6px 8px; display:inline-flex; }
  .content { max-width:760px; margin:0 auto; padding:16px; box-sizing:border-box; overflow-x:hidden; }
  h3 { margin:22px 0 8px; font-size:17px; }
  .muted { color:var(--secondary-text-color); } .small { font-size:13px; } .center { text-align:center; justify-content:center; }
  button { font:inherit; color:inherit; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:12px; }
  .card { background:var(--card-background-color); border:none; border-radius:14px; padding:18px 14px; text-align:left; cursor:pointer;
          box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); min-height:92px; }
  .card.amne { border-left:6px solid var(--c); }
  .amne-namn { font-size:18px; font-weight:600; margin-bottom:6px; }
  .card.add, .row.add { color:var(--primary-color); font-weight:600; }
  .card.add { text-align:center; border:2px dashed var(--divider-color); box-shadow:none; background:none; }
  .list { display:flex; flex-direction:column; gap:8px; }
  .row { display:flex; justify-content:space-between; align-items:center; gap:8px; background:var(--card-background-color); border:none;
         border-radius:12px; padding:14px; cursor:pointer; text-align:left; box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .row.static { cursor:default; }
  .row.add { justify-content:center; background:none; border:2px dashed var(--divider-color); box-shadow:none; }
  .actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:20px; } .actions.top { margin:0 0 14px; }
  .primary { background:var(--primary-color); color:var(--text-primary-color, #fff); border:none; border-radius:10px; padding:12px 18px;
             font-weight:600; cursor:pointer; }
  .upload { display:block; text-align:center; margin-bottom:14px; }
  .ghost { background:none; border:1px solid var(--divider-color); border-radius:10px; padding:10px 14px; cursor:pointer; }
  .danger { color:var(--error-color, #db4437); }
  .mini { background:none; border:1px solid var(--divider-color); border-radius:8px; padding:4px 9px; cursor:pointer; }
  .msg { padding:12px 14px; border-radius:10px; margin-bottom:14px; }
  .exempel { background:rgba(3,169,244,.10); border-radius:10px; padding:8px 10px; margin:6px 0; text-align:left; display:grid; gap:4px; }
  .ex-mening { font-size:1.05em; } .exempel .mini { justify-self:start; } .ex-knapp { width:36px; text-align:right; } .ex-rad td { padding-top:0; }
  .laxa-knapp { width:100%; margin-top:6px; padding:14px; font-size:1.05em; }
  .guide-fraga { font-size:1.15em; font-weight:600; margin:14px 0 8px; }
  .guide-input { width:100%; box-sizing:border-box; font-size:1.05em; padding:12px; }
  .snabb-datum { display:grid; grid-template-columns:repeat(auto-fit, minmax(92px, 1fr)); gap:6px; margin-bottom:8px; }
  .snabb-datum button { padding:10px 6px; line-height:1.25; }
  .del-val { cursor:pointer; } .del-val.vald-rad .muted { font-weight:400; } .del-val input { width:22px; height:22px; flex:none; }
  .uppg { gap:8px; } .uppg.klar .uppg-text span { text-decoration:line-through; opacity:.6; }
  .uppg-text { display:flex; gap:10px; align-items:flex-start; flex:1; cursor:pointer; } .uppg-text input { width:20px; height:20px; margin-top:2px; flex:none; }
  .uppg-ny { display:grid; grid-template-columns:1fr auto auto; gap:6px; margin-top:8px; } .uppg-ny input { min-width:0; }
  .danger-text { color:var(--error-color, #db4437); }
  textarea.anteckning { width:100%; box-sizing:border-box; font:inherit; padding:10px; border-radius:10px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); resize:vertical; }
  @media (max-width:420px) { .uppg-ny { grid-template-columns:1fr auto; } .uppg-ny #uppg-text { grid-column:1 / -1; } }
  .msg.error { background:rgba(219,68,55,.15); } .msg.ok { background:rgba(67,160,71,.15); } .msg.info { background:rgba(3,169,244,.13); }
  .tabs { display:flex; gap:8px; margin-bottom:14px; }
  .tab { border:1px solid var(--divider-color); background:none; border-radius:20px; padding:8px 16px; cursor:pointer; }
  .tab.on { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
  .pages { display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:12px; }
  .page { background:var(--card-background-color); border-radius:10px; overflow:hidden; box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .page img { width:100%; height:180px; object-fit:cover; display:block; cursor:zoom-in; background:var(--secondary-background-color); }
  .pdf { width:100%; height:180px; border:none; background:var(--secondary-background-color); font-size:18px; cursor:pointer; }
  .omslag-rad { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:6px; }
  .omslag { background:var(--card-background-color); border-radius:10px; overflow:hidden; padding-top:6px; text-align:center;
            box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .omslag img { width:100%; height:220px; object-fit:contain; display:block; cursor:zoom-in; background:var(--secondary-background-color); margin-top:6px; }
  .omslag-tom { height:220px; margin-top:6px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px;
                font-size:34px; cursor:pointer; border-top:2px dashed var(--divider-color); color:var(--primary-color); }
  .omslag-tom span { font-size:14px; font-weight:600; }
  label.mini { display:inline-block; }
  .bokrad { display:flex; align-items:center; gap:10px; }
  .mini-omslag { width:34px; height:46px; object-fit:cover; border-radius:4px; background:var(--secondary-background-color); }
  .ebok-kort { background:var(--card-background-color); border-radius:12px; padding:14px; margin:14px 0 4px; display:flex; flex-direction:column; gap:10px;
               box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .ebok-kort .actions { margin-top:0; }
  .primary:disabled, .ghost:disabled { opacity:.4; cursor:default; }
  .ebok-bar { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:12px; }
  .ebok-bar .kap { flex:1; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ebok-sida { background:var(--card-background-color); border-radius:12px; padding:12px; box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
  .ebok-sida img { width:100%; display:block; border-radius:8px; cursor:zoom-in; background:var(--secondary-background-color); min-height:200px; }
  .ebok-kapitel { font-size:20px; font-weight:700; color:var(--primary-color); margin-bottom:10px; }
  .om-sidan { margin-top:12px; } .om-sidan summary { cursor:pointer; font-weight:600; } .om-sidan p { margin:8px 0 0; line-height:1.5; }
  .ebok-nav { display:grid; grid-template-columns:64px 1fr 64px; align-items:center; gap:10px; margin-top:14px; }
  .ebok-nav button { font-size:22px; padding:10px 0; }
  .sok { width:100%; margin-bottom:6px; }
  .sok-rad { align-items:flex-start; } .sok-rad b { font-weight:600; }
  .toc { display:flex; flex-direction:column; gap:6px; }
  .toc-rad { display:flex; justify-content:space-between; gap:10px; background:var(--card-background-color); border:none; border-radius:10px;
             padding:12px 14px; cursor:pointer; text-align:left; }
  .toc-rad.niva1 { font-weight:600; } .toc-rad.niva2 { margin-left:22px; padding:9px 14px; font-size:14px; }
  .stavning { font-size:26px; font-weight:700; letter-spacing:2px; font-family:monospace; word-break:break-all; }
  .stavning .ok { color:var(--success-color, #43a047); }
  .stavning .miss { color:var(--error-color, #db4437); text-decoration:underline; }
  .lyssna { font-size:44px; background:var(--secondary-background-color); border:none; border-radius:50%; width:90px; height:90px;
            margin:0 auto; cursor:pointer; }
  .svar-knapp { background:#e0603a; }
  .hylla { display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:14px; }
  .bok-tile { background:var(--card-background-color); border:none; border-radius:14px; padding:10px; cursor:pointer; text-align:center;
              display:flex; flex-direction:column; gap:6px; box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
  .bok-tile img { width:100%; aspect-ratio:3/4; object-fit:cover; border-radius:8px; background:var(--secondary-background-color); }
  .bok-utan { width:100%; aspect-ratio:3/4; border-radius:8px; background:var(--secondary-background-color); display:flex;
              align-items:center; justify-content:center; font-size:54px; }
  .bok-tile.add { box-shadow:none; background:none; border:2px dashed var(--divider-color); color:var(--primary-color); }
  .bok-tile.add .bok-utan { background:none; }
  .bok-namn { font-weight:600; font-size:16px; }
  .stort-omslag { display:block; width:auto; max-width:70%; max-height:50vh; margin:4px auto 16px; border-radius:10px; cursor:pointer;
                  box-shadow:0 4px 14px rgba(0,0,0,.35); }
  .stor-las { display:block; width:100%; font-size:24px; padding:18px; border-radius:14px; }
  .red-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
  .forhor { color:var(--primary-color); font-weight:600; }
  .row.snart { border-left:5px solid #e0603a; } .row.snart .forhor { color:#e0603a; }
  .forhor-kort { background:var(--card-background-color); border-radius:12px; padding:12px 14px; margin-bottom:12px; font-size:17px; }
  .forhor-kort.snart { background:rgba(224,96,58,.15); }
  .fh-beslut { border-radius:14px; padding:14px; margin:0 0 14px; text-align:center; display:flex; flex-direction:column; gap:8px; }
  .fh-beslut.ok { background:rgba(59,206,172,.18); border:2px solid #3bceac; }
  .fh-beslut.fel { background:rgba(224,96,58,.14); border:2px solid #e0603a; }
  .fh-beslut .fb-rubrik { font-size:22px; font-weight:800; }
  .fh-beslut .fb-knappar { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; }
  .prov-res { border-radius:14px; padding:14px; margin-bottom:12px; text-align:center; background:var(--card-background-color); border:2px solid var(--divider-color); display:flex; flex-direction:column; gap:4px; }
  .prov-res.topp { border-color:#ffd23f; background:rgba(255,210,63,.14); } .prov-res.bra { border-color:#3bceac; background:rgba(59,206,172,.12); }
  .prov-res .pr-rubrik { font-size:24px; font-weight:800; }
  .prov-form { display:flex; flex-direction:column; gap:10px; }
  .prov-form .pf-val, .prov-form .pf-rad { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .prov-form input[type=number] { width:90px; font-size:18px; padding:6px; }
  .prov-form #pr-komm { font-size:16px; padding:8px; }
  .pf-betyg { font-size:18px; font-weight:700; }
  .word.gomt { opacity:.5; }
  .tips-rad { font-size:26px; letter-spacing:4px; font-weight:700; font-family:monospace; margin:6px 0; color:#ffb300; word-break:break-all; }
  .fh-omprov { background:rgba(224,96,58,.15); border-radius:10px; padding:8px 12px; font-weight:600; }
  .forhor-nytt { display:block; width:100%; text-align:left; border:none; border-radius:16px; padding:16px; margin-bottom:14px; cursor:pointer;
                 background:linear-gradient(135deg, #e0603a, #f7a14f); color:#fff; box-shadow:0 3px 10px rgba(224,96,58,.4); }
  .fn-rubrik { font-size:14px; opacity:.9; } .fn-namn { font-size:22px; font-weight:700; margin:4px 0; }
  .fn-start { margin-top:10px; font-weight:700; font-size:18px; text-align:right; }
  .skicka-forhor { margin-bottom:14px; font-weight:600; color:var(--primary-color); }
  .vald-rad { outline:2px solid var(--primary-color); font-weight:600; }
  .r-ok td:nth-child(2) { color:var(--success-color, #43a047); } .r-fel td:nth-child(2) { color:var(--error-color, #db4437); }
  .stavning.liten { font-size:15px; letter-spacing:1px; margin-top:4px; }
  .logg tr[data-open-forhor] { cursor:pointer; }
  .helskarm { position:fixed; inset:0; z-index:1000; background:var(--primary-background-color); overflow-y:auto;
              padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left); }
  .helskarm .toolbar { position:static; justify-content:center; }
  .helskarm .content { padding-top:24px; }
  .folj { display:flex; flex-direction:column; gap:8px; }
  .progress.stor { height:16px; border-radius:8px; margin:0; }
  .merit-kort { display:block; width:100%; text-align:left; border:none; border-radius:16px; padding:14px 16px; margin-bottom:16px; cursor:pointer;
                background:linear-gradient(135deg, #4f8ef7, #9b6cf0); color:#fff; box-shadow:0 3px 10px rgba(79,142,247,.35); }
  .merit-kort .progress { background:rgba(255,255,255,.3); margin:8px 0 6px; } .merit-kort .progress div { background:#ffd54f; }
  .mk-rad { display:flex; justify-content:space-between; gap:8px; } .mk-niva { font-weight:700; font-size:18px; }
  .mk-medaljer { margin-top:8px; font-size:22px; letter-spacing:4px; }
  .vantar { background:rgba(247,161,79,.18); border-radius:12px; padding:12px 14px; margin-bottom:12px; }
  .merit-stor { text-align:center; display:flex; flex-direction:column; gap:8px; }
  .medaljer { display:grid; grid-template-columns:repeat(auto-fill, minmax(105px, 1fr)); gap:10px; }
  .medalj { background:var(--card-background-color); border-radius:12px; padding:10px 6px; text-align:center; opacity:.45; filter:grayscale(1); }
  .medalj.har { opacity:1; filter:none; box-shadow:0 0 0 2px #ffd54f inset; }
  .medalj .mi { font-size:32px; } .medalj .mn { font-weight:600; font-size:14px; margin:2px 0; }
  .hur { display:flex; flex-direction:column; gap:6px; background:var(--card-background-color); border-radius:12px; padding:12px 14px; }
  .plus { color:var(--success-color, #43a047); font-weight:700; } .minus { color:var(--error-color, #db4437); font-weight:700; }
  .row.jag { outline:2px solid var(--primary-color); }
  .schema-rad { display:grid; grid-template-columns:1fr 1fr; gap:6px; background:var(--card-background-color); border-radius:12px; padding:10px; position:relative; }
  .schema-rad input { grid-column:1 / -1; margin-right:40px; } .schema-rad label { display:flex; flex-direction:column; gap:2px; }
  .schema-rad [data-sch-del] { position:absolute; top:12px; right:10px; }
  select { font:inherit; padding:8px; border-radius:8px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); }
  .toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); z-index:1200; background:#2e7d32; color:#fff; border-radius:14px;
           padding:12px 18px; box-shadow:0 4px 16px rgba(0,0,0,.35); display:flex; flex-direction:column; gap:4px; max-width:90vw; animation:upp .3s ease-out; }
  @keyframes upp { from { transform:translate(-50%, 30px); opacity:0; } }
  .foralder-knapp { margin-bottom:14px; border-left:5px solid var(--primary-color); }
  .uppdrag-kort { display:block; width:100%; text-align:left; border:none; border-radius:14px; padding:12px 14px; margin-bottom:10px; cursor:pointer;
                  background:var(--card-background-color); border-left:6px solid #4fc98a; box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
  .uppdrag-kort.prov { border-left-color:#e05f8a; } .uppdrag-kort.klar { opacity:.6; } .uppdrag-kort.sen { border-left-color:#db4437; }
  .uppdrag-kort .progress { margin:6px 0 0; }
  .uk-rad { display:flex; justify-content:space-between; gap:8px; margin-bottom:4px; }
  .kap-val { display:flex; flex-direction:column; gap:4px; margin-bottom:10px; }
  .kap-rad { flex-direction:row !important; align-items:center; gap:8px !important; color:var(--primary-text-color) !important; font-size:15px !important; }
  .kap-rad input { width:20px; height:20px; }
  .uppdrag-kort.hogl { border-left-color:#4fc98a; } .uppdrag-kort.skriv { border-left-color:#f7a14f; }
  .dag-val { margin:10px 0; padding:10px 12px; border-radius:12px; background:var(--secondary-background-color); }
  .dag-val .dag-prickar span, .dag-val .dag-prickar button { min-width:44px; }
  .info-lank { display:block; width:100%; margin:-4px 0 12px; padding:6px; border:none; background:none; color:var(--primary-color); font-size:14px; text-align:center; cursor:pointer; }
  .info-kort { margin:12px 0; padding:4px 14px 10px; border-radius:14px; background:var(--card-background-color, var(--secondary-background-color)); box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
  .info-kort h3 { margin:10px 0 6px; }
  .info-rad { padding:5px 0; line-height:1.4; border-top:1px solid var(--divider-color, rgba(127,127,127,.2)); }
  .info-rad:first-of-type { border-top:none; }
  .svit { margin:8px 0 2px; }
  .svit-stj { display:flex; justify-content:space-between; font-size:22px; line-height:1.2; }
  .svit-stj span { opacity:.35; } .svit-stj span.full { opacity:1; }
  .svit-stj span.nasta { opacity:.8; animation: svitpuls 1.4s ease-in-out infinite; }
  @keyframes svitpuls { 50% { transform: scale(1.25); } }
  .dag-prickar { display:flex; gap:4px; margin:8px 0 4px; flex-wrap:wrap; }
  .dag-prickar span { min-width:34px; padding:3px 6px; border-radius:8px; text-align:center; font-size:12px; background:var(--secondary-background-color); }
  .dag-prickar span.ok { background:#4fc98a; color:#fff; } .dag-prickar span.vantar { background:#f7d34f; color:#000; }
  .dag-prickar button.ok-knapp { background:#4fc98a; color:#fff; border-color:#4fc98a; }
  .dag-prickar span.nej { background:#db4437; color:#fff; } .dag-prickar span.idag { outline:2px solid var(--primary-color); }
  .idag-rad { border-left:4px solid var(--primary-color); }
  .vb-med { font-size:17px; }
  .sid-prickar { display:flex; flex-wrap:wrap; gap:4px; margin:10px 0; }
  .sid-prickar span { min-width:28px; padding:3px 4px; border-radius:6px; text-align:center; font-size:12px; background:var(--secondary-background-color); }
  .sid-prickar span.last { background:#4fc98a; color:#fff; }
  .las-banner { background:rgba(79,201,138,.15); border-radius:12px; padding:10px 12px; margin-bottom:10px; display:flex; flex-direction:column; gap:6px; }
  .las-banner .progress { margin:0; }
  .kontroll { display:flex; flex-direction:column; gap:6px; margin-bottom:14px; }
  .topp-p { display:flex; flex-direction:column; align-items:center; font-size:22px; line-height:1.1; }
  .ut-bar { position:sticky; top:56px; z-index:1; display:flex; gap:8px; justify-content:space-between; padding:10px 0; background:var(--primary-background-color); }
  .valj { position:relative; padding:0; border:3px solid transparent; border-radius:12px; overflow:hidden; background:var(--card-background-color);
          cursor:pointer; display:flex; flex-direction:column; text-align:center; }
  .valj img, .valj .pdf { width:100%; height:180px; object-fit:cover; display:block; background:var(--secondary-background-color); }
  .valj > .small { padding:6px; }
  .valj.vald { border-color:var(--primary-color); }
  .valj:not(.vald) img { opacity:.55; }
  .bock { position:absolute; top:8px; right:8px; width:30px; height:30px; border-radius:50%; border:2px solid #fff; background:rgba(0,0,0,.35);
          color:#fff; font-weight:700; display:flex; align-items:center; justify-content:center; }
  .valj.vald .bock { background:var(--primary-color); }
  .page-bar { display:flex; justify-content:space-between; align-items:center; padding:6px 8px; gap:4px; }
  table.glos { width:100%; border-collapse:collapse; background:var(--card-background-color); border-radius:12px; overflow:hidden; }
  .glos th, .glos td { padding:10px 12px; text-align:left; border-bottom:1px solid var(--divider-color); word-break:break-word; }
  .glos th { background:var(--secondary-background-color); font-size:14px; }
  .form label, .two label { display:flex; flex-direction:column; gap:4px; font-size:13px; color:var(--secondary-text-color); margin-bottom:10px; }
  .two { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  input { font:inherit; font-size:16px; padding:10px; border-radius:8px; border:1px solid var(--divider-color);
          background:var(--card-background-color); color:var(--primary-text-color); min-width:0; box-sizing:border-box; }
  .pairs { display:flex; flex-direction:column; gap:6px; }
  .pair { display:grid; grid-template-columns:1fr 1fr auto; gap:6px; align-items:center; }
  .progress { height:8px; background:var(--divider-color); border-radius:4px; overflow:hidden; margin-bottom:6px; }
  .progress div { height:100%; background:var(--primary-color); transition:width .3s; }
  .flash { background:var(--card-background-color); border-radius:16px; padding:28px 18px; margin-top:14px; text-align:center;
           display:flex; flex-direction:column; gap:14px; align-items:stretch; box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
  .word { font-size:30px; font-weight:700; word-break:break-word; }
  .flash input { text-align:center; font-size:20px; }
  .answer { font-size:18px; } .answer.ratt { color:var(--success-color, #43a047); } .answer.fel { color:var(--error-color, #db4437); }
  .done { text-align:center; padding:30px 0; } .big { font-size:64px; } .score { font-size:20px; font-weight:600; margin:10px 0; }
  .busy { position:fixed; inset:0; background:rgba(0,0,0,.15); display:flex; align-items:center; justify-content:center; z-index:1100; }
  .spin { width:42px; height:42px; border:4px solid var(--divider-color); border-top-color:var(--primary-color); border-radius:50%; animation:s 1s linear infinite; }
  .viewer { position:fixed; inset:0; background:rgba(0,0,0,.95); z-index:6; display:flex; align-items:center; justify-content:center; overflow:hidden; touch-action:none; }
  .viewer img { max-width:100%; max-height:100%; object-fit:contain; transform-origin:0 0; will-change:transform; user-select:none; -webkit-user-select:none; -webkit-touch-callout:none; }
  .djur-kort { display:flex; gap:14px; align-items:center; background:var(--card-background-color); border-radius:16px; padding:12px 16px; margin-bottom:12px;
               box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .djur-figur { position:relative; line-height:1; min-width:70px; text-align:center; }
  .humor-glad .djur-figur { animation:hopp 1.6s ease-in-out infinite; }
  .humor-hungrig .djur-figur { animation:vicka 2s ease-in-out infinite; }
  .humor-ledsen .djur-figur { filter:grayscale(.8); opacity:.7; }
  .djur-figur .krona { position:absolute; top:-18px; left:50%; transform:translateX(-50%); font-size:24px; }
  @keyframes hopp { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-8px); } }
  @keyframes vicka { 0%,100% { transform:rotate(0); } 25% { transform:rotate(-6deg); } 75% { transform:rotate(6deg); } }
  .djur-info { flex:1; display:flex; flex-direction:column; gap:4px; }
  .djur-info .progress div { background:#ffb300; }
  .djur-rubrik { font-weight:700; font-size:16px; display:flex; justify-content:space-between; gap:8px; }
  .djur-kort:not(.humor-glad):not(.humor-nojd):not(.humor-hungrig):not(.humor-ledsen) { flex-direction:column; align-items:stretch; }
  .djur-val { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
  .djur-val button { font-size:34px; background:var(--secondary-background-color); border:none; border-radius:12px; width:58px; height:58px; cursor:pointer; }
  .scen-bastis { position:absolute; right:6%; bottom:30%; font-size:22px; animation:bastis 1.6s ease-in-out infinite; filter:drop-shadow(0 0 4px #fff); }
  .bastis-bricka { display:inline-block; font-size:12px; font-weight:600; padding:2px 10px; margin:3px 0; border-radius:12px; background:linear-gradient(90deg,#f8bbd0,#e1bee7); color:#6a1b9a; }
  .djur-scen { position:relative; flex:none; border-radius:22px; overflow:hidden; box-shadow:inset 0 0 0 3px rgba(255,255,255,.4); }
  .djur-scen svg { display:block; }
  .djur-scen.humor-glad .kropp { animation:hoppSvg 1.6s ease-in-out infinite; }
  .djur-scen.humor-hungrig .kropp { animation:vickaSvg 2s ease-in-out infinite; }
  .djur-scen.humor-ledsen .kropp { filter:saturate(.5); }
  @keyframes hoppSvg { 0%,100% { translate:0 0; } 50% { translate:0 -8px; } }
  @keyframes vickaSvg { 0%,100% { rotate:0deg; } 25% { rotate:-4deg; } 75% { rotate:4deg; } }
  .djur-scen .kropp { transform-box:view-box; }
  .kompis-svg { animation:hoppSvg 1.2s ease-in-out infinite; animation-delay:.3s; }
  .partikel { animation:gnistra 1.8s ease-in-out infinite; transform-box:fill-box; transform-origin:center; }
  .partikel.p1 { animation-delay:.6s; } .partikel.p2 { animation-delay:1.2s; }
  .djur-scen.glod-regnbage .kropp { animation:regnbage 3s linear infinite; }
  .djur-scen.glod-puls .kropp { animation:pulseraSvg 1.2s ease-in-out infinite; } @keyframes pulseraSvg { 50% { scale:1.08; } }
  .djur-scen.glod-snurr .kropp { animation:snurraSvg 4s linear infinite; } @keyframes snurraSvg { to { rotate:360deg; } }
  .rit-val { width:72px !important; height:72px !important; padding:4px !important; }
  .rit-val svg { width:100%; height:100%; }
  .djur-figur { display:flex; flex-direction:column; align-items:center; }
  .djur-figur .kropp { display:block; line-height:1; }
  .djur-figur .hatt { display:block; line-height:1; margin-bottom:-.25em; position:relative; z-index:1; }
  .djur-figur .hatt-solglas { margin-bottom:-.75em; margin-top:.2em; order:0; }
  .eff-regnbage .kropp { animation:regnbage 3s linear infinite; }
  @keyframes regnbage { 0% { filter:drop-shadow(0 0 8px #f44336); } 33% { filter:drop-shadow(0 0 8px #4caf50); } 66% { filter:drop-shadow(0 0 8px #2196f3); } 100% { filter:drop-shadow(0 0 8px #f44336); } }
  .eff-glitter { position:relative; }
  .gnista { position:absolute; font-size:16px; animation:gnistra 1.8s ease-in-out infinite; }
  .gnista.g1 { top:0; left:-6px; } .gnista.g2 { top:35%; right:-10px; animation-delay:.6s; } .gnista.g3 { bottom:0; left:10%; animation-delay:1.2s; }
  @keyframes gnistra { 0%,100% { opacity:0; transform:scale(.5); } 50% { opacity:1; transform:scale(1.1); } }
  .djur-kort.bg-hav { background:linear-gradient(160deg,#4fc3f7,#0277bd); color:#fff; }
  .djur-kort.bg-djungel { background:linear-gradient(160deg,#9ccc65,#2e7d32); color:#fff; }
  .djur-kort.bg-vinter { background:linear-gradient(160deg,#e3f2fd,#90caf9); color:#0d47a1; }
  .djur-kort.bg-rymd { background:radial-gradient(circle at 30% 20%,#5c6bc0,#1a1040 70%); color:#fff; }
  .djur-kort.bg-slott { background:linear-gradient(160deg,#f8bbd0,#8e24aa); color:#fff; }
  .djur-kort.har-bg { position:relative; overflow:hidden; }
  .djur-kort.har-bg .muted { color:inherit; opacity:.8; }
  .djur-kort.har-bg .progress { background:rgba(255,255,255,.35); }
  .bg-deko { position:absolute; right:10px; bottom:4px; font-size:38px; opacity:.35; pointer-events:none; }
  .glod-regnbage .kropp { animation:regnbage 3s linear infinite; }
  .djur-figur .kompis { position:absolute; right:-0.55em; bottom:0; animation:hopp 1.2s ease-in-out infinite; animation-delay:.3s; }
  .glod-puls .kropp { animation:pulsera 1.2s ease-in-out infinite; } @keyframes pulsera { 50% { transform:scale(1.12); } }
  .glod-is .kropp { filter:drop-shadow(0 0 8px #4fc3f7) drop-shadow(0 0 16px #b3e5fc); }
  .glod-eld .kropp { filter:drop-shadow(0 0 8px #ff5722) drop-shadow(0 0 18px #ffab00); }
  .glod-skugga .kropp { filter:drop-shadow(6px 6px 0 rgba(0,0,0,.55)); }
  .glod-snurr .kropp { animation:snurra 4s linear infinite; } @keyframes snurra { to { transform:rotate(360deg); } }
  .attack-lvl { font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px; background:#ffb300; color:#3e2723; vertical-align:middle; }
  .attack-stjarnor { color:#ffb300; font-size:13px; letter-spacing:1px; }
  .kompis-gata { font-size:11px; font-style:italic; opacity:.75; margin:2px 0 4px; line-height:1.25; }
  .kompis-retas { font-size:13px; font-style:italic; padding:8px 12px; margin:-4px 0 10px; border-radius:10px; background:rgba(156,39,176,.10); }
  .sak-ikon { position:relative; }
  .bastis-hjarta { position:absolute; top:-6px; right:-10px; font-size:16px; animation:bastis 1.6s ease-in-out infinite; }
  @keyframes bastis { 0%,100% { transform:scale(1); } 50% { transform:scale(1.25); } }
  .lar-knapp { background:linear-gradient(135deg,#00897b,#43a047) !important; color:#fff !important; }
  .lar-chatt { display:flex; flex-direction:column; gap:8px; margin-bottom:10px; }
  .lar-rad { display:flex; gap:8px; align-items:flex-end; }
  .lar-rad.barn { justify-content:flex-end; }
  .lar-ikon { font-size:30px; }
  .lar-bubbla { max-width:78%; padding:9px 12px; border-radius:16px; font-size:15px; line-height:1.35; }
  .lar-rad.djur .lar-bubbla { background:#e8f5e9; color:#1b5e20; border-bottom-left-radius:4px; }
  .lar-rad.barn .lar-bubbla { background:#e3f2fd; color:#0d47a1; border-bottom-right-radius:4px; }
  .lar-bubbla.tanker { animation:andas 1s ease-in-out infinite; }
  .lar-input { display:flex; flex-direction:column; gap:6px; }
  .upps-kort { border:2px solid #7e57c2; border-radius:12px; padding:8px 10px; margin:8px 0; background:rgba(126,87,194,.06); }
  .upps-platser { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin:6px 0; }
  .upps-plats { border:2px solid #7e57c2; border-radius:10px; text-align:center; font-size:24px; padding:4px 2px; display:flex; flex-direction:column; align-items:center; }
  .upps-plats small { font-size:10px; line-height:1.1; } .upps-plats.tom { border-style:dashed; opacity:.5; }
  .upps-med { background:#ede7f6; border-color:#7e57c2; }
  .ladd-rad { display:flex; align-items:center; gap:6px; font-size:12px; margin:4px 0; }
  .ladd-bar { flex:1; height:10px; border-radius:6px; background:rgba(0,0,0,.12); overflow:hidden; }
  .ladd-bar div { height:100%; background:linear-gradient(90deg,#ffca28,#ff7043); transition:width .4s; }
  .ladd-rad.full .ladd-bar div { animation:laddPuls 0.8s ease-in-out infinite alternate; }
  @keyframes laddPuls { from { filter:brightness(1); } to { filter:brightness(1.5); box-shadow:0 0 8px #ffca28; } }
  .ladd-knapp.redo { background:linear-gradient(90deg,#ffe082,#ffab91) !important; font-weight:700; animation:laddPuls 0.8s ease-in-out infinite alternate; }
  .passform { font-size:12px; font-weight:600; border-radius:8px; padding:2px 6px; margin:3px 0; }
  .passform.bra { background:#e8f5e9; color:#1b5e20; } .passform.dalig { background:#fbe9e7; color:#bf360c; }
  .element-rad { background:rgba(33,150,243,.08); border-radius:10px; padding:6px 10px; margin:6px 0; font-size:13px; }
  .element-bricka { font-size:12px; background:rgba(0,0,0,.06); border-radius:10px; padding:1px 7px; white-space:nowrap; }
  .rit-val.med-element { position:relative; } .rit-val.med-element .el { position:absolute; left:0; right:0; bottom:2px; font-size:11px; text-align:center; }
  .mina-djur { display:grid; grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); gap:8px; margin:8px 0; }
  .mitt-djur { text-align:center; border:2px solid var(--divider-color); border-radius:12px; padding:6px; }
  .mitt-djur.aktiv { border-color:#43a047; background:rgba(67,160,71,.08); }
  .mitt-djur .rit-val { width:90px; height:90px; margin:0 auto; border:none; background:none; }
  .fraga-forslag { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
  .hjalp-topp { display:flex; justify-content:space-between; align-items:center; gap:8px; min-height:0; padding:10px 14px; margin-bottom:10px; cursor:default; }
  .hjalp-kort { min-height:0; margin-bottom:10px; cursor:default; }
  .hjalp-kort .row { width:100%; box-sizing:border-box; margin-top:8px; }
  .hjalp-lagen { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px; }
  .hjalp-lagen .mini { border-radius:14px; }
  .hjalp-poang { margin:0 0 8px; }
  .dagens-lista .row { width:100%; box-sizing:border-box; margin-top:6px; }
  .dagens-lista { min-height:0; cursor:default; }
  .pg h4 { margin:16px 0 6px; }
  .pg textarea, .pg-ny input { width:100%; box-sizing:border-box; font:inherit; padding:8px; border-radius:10px; border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); }
  .pg-omr { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--divider-color); }
  .pg-kan { display:flex; gap:4px; flex-shrink:0; }
  .pg-ny { display:flex; gap:6px; margin:8px 0 4px; }
  .pd-dag { margin:10px 0; }
  .pd-dag.forr { opacity:.75; }
  .pd-rubrik { font-weight:700; margin-bottom:4px; text-transform:capitalize; }
  .pd-dag.idag .pd-rubrik { color:var(--primary-color); }
  .pd-rad { display:flex; align-items:flex-start; gap:8px; padding:8px 10px; border-radius:12px; background:var(--card-background-color); box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); margin-bottom:6px; }
  .pd-rad.klar .pd-text { opacity:.55; text-decoration:line-through; }
  .pd-check { background:none; border:none; font-size:22px; cursor:pointer; padding:0; line-height:1; }
  .pd-text { flex:1; min-width:0; }
  .pd-tankar { border-left:5px solid #7e57c2; }
  .coach-svar { white-space:pre-wrap; }
  .coach-forslag { margin-top:8px; padding-top:8px; border-top:1px dashed currentColor; font-size:13px; white-space:normal; }
  #coach-onsk { width:100%; box-sizing:border-box; font:inherit; padding:8px; border-radius:10px; border:1px solid var(--divider-color); margin-top:8px; background:var(--card-background-color); color:var(--primary-text-color); }
  .kontroll.ratt { border-left:4px solid #43a047; padding-left:8px; }
  .kontroll.fel { border-left:4px solid #e53935; padding-left:8px; }
  .kontroll textarea { width:100%; box-sizing:border-box; font:inherit; padding:8px; border-radius:10px; border:1px solid var(--divider-color); margin-top:6px; }
  .sv-facit { margin-top:10px; padding:10px; border-radius:10px; background:#e8f5e9; color:#1b5e20; }
  #sv-text { width:100%; box-sizing:border-box; font:inherit; padding:8px; border-radius:10px; border:1px solid var(--divider-color); margin-top:10px; }
  .fraga-forslag .mini { border-radius:14px; }
  .lar-beloning { font-size:28px; font-weight:800; color:#2e7d32; animation:gs-pop .6s; }
  .fokus-djur { position:relative; display:inline-block; }
  .fokus-djur svg { width:140px; height:140px; }
  .fokus-djur.sover svg { animation:andas 3s ease-in-out infinite; }
  @keyframes andas { 0%,100% { transform:scale(1); } 50% { transform:scale(1.04); } }
  .zzz { position:absolute; top:0; right:-10px; font-size:28px; animation:bastis 2s ease-in-out infinite; }
  .fokus-val { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin:10px 0; }
  .fokus-val button { min-width:70px; }
  .fokus-tid { font-size:56px; font-weight:800; font-variant-numeric:tabular-nums; margin:8px 0; }
  .samlarkort { position:relative; width:84px; min-height:112px; border-radius:10px; padding:6px 4px; text-align:center; color:#fff;
    background:linear-gradient(160deg, var(--farg), color-mix(in srgb, var(--farg) 45%, #000)); box-shadow:0 2px 6px rgba(0,0,0,.25); border:3px solid #cfd8dc; }
  .samlarkort.ovanlig { border-color:#4fc3f7; box-shadow:0 0 10px #4fc3f7; }
  .samlarkort.legendarisk { border-color:#ffd54f; box-shadow:0 0 14px #ffb300; }
  .samlarkort.dold, .samlarkort.saknas { background:repeating-linear-gradient(45deg,#546e7a,#546e7a 6px,#607d8b 6px,#607d8b 12px); border-color:#90a4ae; box-shadow:none; }
  .samlarkort.saknas { opacity:.45; }
  .sk-ikon { font-size:38px; margin:6px 0 2px; }
  .sk-namn { font-size:11px; font-weight:700; line-height:1.15; }
  .sk-sallsynt { font-size:9px; opacity:.9; margin-top:2px; }
  .sk-antal { position:absolute; top:2px; right:4px; font-size:10px; font-weight:800; background:rgba(0,0,0,.4); border-radius:6px; padding:0 4px; }
  .kort-rad, .album-rutnat { display:flex; gap:8px; flex-wrap:wrap; justify-content:center; margin:8px 0; }
  .kort-rad { perspective:800px; }
  .kort-vand.skakar { animation:kort-skak .7s ease-in-out; }
  @keyframes kort-skak { 0%,100% { transform:none; } 15% { transform:rotate(-6deg) scale(1.04); } 30% { transform:rotate(6deg) scale(1.08); } 45% { transform:rotate(-8deg) scale(1.1); } 60% { transform:rotate(8deg) scale(1.12); } 80% { transform:rotate(-3deg) scale(1.15); } }
  .kort-vand.vand { animation:vand .8s cubic-bezier(.2,1.5,.4,1) both; }
  @keyframes vand { 0% { transform:rotateY(180deg) scale(.6); opacity:.3; } 100% { transform:rotateY(0) scale(1); opacity:1; } }
  .kort-vand.vand .samlarkort.legendarisk { animation:kort-legend 1.4s ease-in-out .8s infinite; }
  @keyframes kort-legend { 50% { box-shadow:0 0 26px #ffd54f, 0 0 50px #ff8f00; transform:translateY(-4px); } }
  .kort-vand.vand .samlarkort.ovanlig { animation:kort-ovanlig 1.6s ease-in-out .8s infinite; }
  @keyframes kort-ovanlig { 50% { box-shadow:0 0 20px #4fc3f7; } }
  .kort-nya { background:linear-gradient(135deg,#ede7f6,#fff8e1); color:#311b92; }
  .kista-kort { background:linear-gradient(135deg,#fff8e1,#fce4ec); color:#4a2c00; }
  .kista-rad { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0; }
  .kista { display:flex; align-items:center; gap:8px; text-align:left; border:2px solid #d7a85b; background:#fffdf5; color:#4a2c00; border-radius:14px; padding:8px 12px; cursor:pointer; flex:1 1 200px; }
  .kista.silver { border-color:#64b5f6; background:#f3f9ff; }
  .kista.guld { border-color:#ffb300; background:linear-gradient(135deg,#fff8e1,#ffecb3); box-shadow:0 0 12px rgba(255,179,0,.5); }
  .kista-ikon { font-size:34px; animation:kista-hopp 1.6s ease-in-out infinite; }
  .kista.skakar .kista-ikon { animation:kista-skak .15s linear infinite; }
  @keyframes kista-hopp { 0%,80%,100% { transform:translateY(0) } 88% { transform:translateY(-6px) rotate(-6deg) } 94% { transform:translateY(-2px) rotate(5deg) } }
  @keyframes kista-skak { 0% { transform:rotate(-12deg) } 50% { transform:rotate(12deg) } 100% { transform:rotate(-12deg) } }
  .kista-innehall { display:flex; flex-wrap:wrap; gap:10px; margin:8px 0; }
  .kista-sak { display:flex; flex-direction:column; align-items:center; background:#fff; border-radius:12px; padding:8px 12px; animation:kista-pop .5s both; }
  .kista-sak span { font-size:30px; }
  @keyframes kista-pop { from { transform:scale(0); opacity:0 } to { transform:scale(1); opacity:1 } }
  .laxfraga-kort { display:flex; gap:12px; align-items:center; }
  .laxfraga-djur { width:64px; flex:none; }
  .laxfraga-kort .actions { flex-wrap:wrap; }
  .pratbubbla { background:var(--secondary-background-color,#f1f1f1); border-radius:14px; padding:8px 12px; position:relative; }
  .provboss-kort { border:2px solid #ef9a9a; }
  .provboss .pb-ikon { font-size:34px; text-align:center; flex:none; width:42px; }
  .arena-lista li.provboss > span:nth-child(2) { flex:1 1 auto; min-width:0; }
  .provboss > :nth-child(3) { flex:none; max-width:92px; }
  .provboss.vunnen { opacity:.7; }
  .pb-liv { height:8px; border-radius:6px; background:#e0e0e0; overflow:hidden; margin:4px 0 2px; max-width:220px; }
  .pb-liv div { height:100%; background:linear-gradient(90deg,#e53935,#ff7043); }
  .trofe-rad { display:flex; flex-wrap:wrap; gap:8px; }
  .trofe { display:flex; flex-direction:column; align-items:center; font-size:28px; background:linear-gradient(135deg,#fff8e1,#ffe082); border-radius:12px; padding:6px 10px; color:#4a2c00; }
  .vantar.ok { background:#e8f5e9; color:#1b5e20; }
  .skolinfo-kort { border:2px solid #90caf9; }
  .skolinfo-kort li { display:flex; gap:6px; align-items:baseline; justify-content:space-between; }
  .skolinfo-kort li.snart { font-weight:600; color:var(--primary-color,#1976d2); }
  .vb-rad.av { opacity:.5; }
  .vb-rad textarea { width:100%; box-sizing:border-box; font:inherit; padding:8px; border-radius:8px; }
  .kal-kalla .kap-val { display:flex; flex-wrap:wrap; gap:4px 14px; }
  .kal-guide { margin:8px 0; }
  .kal-guide li { margin:4px 0; }
  .foto-val { background:var(--secondary-background-color,#f5f5f5); border-radius:12px; padding:10px 12px; margin:8px 0; }
  .foto-val .lista li { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .ls-sok input { width:100%; box-sizing:border-box; padding:10px 12px; border-radius:12px; border:1px solid var(--divider-color,#ccc); font-size:16px; background:var(--card-background-color,#fff); color:inherit; }
  #ls-traffar { margin:6px 0; }
  .ls-idag { margin:10px 0; }
  .ls-idag-rad { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--divider-color,#eee); cursor:pointer; flex-wrap:wrap; }
  .ls-idag-rad.klar { opacity:.5; }
  .ls-idag-rad.nu { font-weight:600; }
  .ls-prick { width:10px; height:10px; border-radius:50%; flex:none; }
  .ls-schema { display:grid; grid-template-columns:24px repeat(5,minmax(0,1fr)); gap:3px; margin:10px 0; }
  .ls-tider { position:relative; margin-top:22px; }
  .ls-tider span { position:absolute; right:2px; font-size:10px; opacity:.6; transform:translateY(-50%); }
  .ls-dag-rubrik { text-align:center; font-weight:700; font-size:13px; height:22px; line-height:22px; border-radius:6px; }
  .ls-dag.idag .ls-dag-rubrik { background:var(--primary-color,#4f8ef7); color:#fff; }
  .ls-kolumn { position:relative; background:var(--secondary-background-color,#f5f5f5); border-radius:6px; }
  .ls-dag.idag .ls-kolumn { background:color-mix(in srgb, var(--primary-color,#4f8ef7) 10%, var(--secondary-background-color,#f5f5f5)); }
  .ls-linje { position:absolute; left:0; right:0; border-top:1px dashed rgba(127,127,127,.25); }
  .ls-nu { position:absolute; left:-2px; right:-2px; border-top:2px solid #e53935; z-index:2; }
  .ls-nu::before { content:""; position:absolute; left:-3px; top:-5px; width:8px; height:8px; border-radius:50%; background:#e53935; }
  .ls-lektion { position:absolute; box-sizing:border-box; border:0; border-left:4px solid var(--c); background:color-mix(in srgb, var(--c) 22%, var(--card-background-color,#fff));
    color:inherit; border-radius:5px; padding:2px 3px; text-align:left; font-size:11px; line-height:1.2; overflow:hidden; cursor:pointer; display:flex; flex-direction:column; transition:opacity .2s; }
  .ls-lektion b { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ls-lektion span { font-size:10px; opacity:.8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ls-lektion.pagar { box-shadow:0 0 0 2px #e53935; }
  .ls-lektion.dim, .row.dim { opacity:.18; }
  .ls-lektion.ej { opacity:.4; border-left-style:dashed; background:repeating-linear-gradient(135deg, transparent 0 6px, rgba(127,127,127,.15) 6px 12px); }
  .ls-lektion.ej.delad > * { display:none; }
  .ls-delad-val { background:var(--secondary-background-color,#f5f5f5); border-radius:10px; padding:8px 10px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .ls-lektion.delad { padding:2px 2px 2px 3px; border-left-width:3px; }
  .ls-lektion.delad b, .ls-lektion.delad span { white-space:normal; overflow-wrap:anywhere; text-overflow:clip; }
  .ls-red { margin-top:10px; }
  .schema-rutnat { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:4px; margin:8px 0; }
  .schema-rubrik { font-weight:700; text-align:center; font-size:13px; margin-bottom:4px; }
  .schema-lektion { border-left:4px solid var(--c); background:var(--secondary-background-color,#f5f5f5); border-radius:6px; padding:3px 4px; margin-bottom:3px; font-size:12px; overflow:hidden; overflow-wrap:anywhere; }
  .schema-lektion span { display:block; opacity:.7; font-size:11px; }
  .fodelsedag-kort { text-align:center; background:linear-gradient(135deg,#fce4ec,#fff9c4,#e1f5fe); color:#880e4f; }
  .fd-tarta { font-size:64px; animation:hopp 1.2s ease-in-out infinite; }
  .fd-text { font-size:22px; font-weight:800; margin:4px 0 10px; }
  .fd-text small { font-size:15px; font-weight:600; }
  .fd-knapp { animation:bastis 1.4s ease-in-out infinite; }
  .jul-kort { background:linear-gradient(160deg,#b71c1c,#1b5e20); color:#fff; }
  .jul-rubrik { font-weight:800; font-size:17px; margin-bottom:8px; }
  .jul-luckor { display:grid; grid-template-columns:repeat(6,1fr); gap:6px; }
  .lucka { aspect-ratio:1; border-radius:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; font-weight:800; font-size:16px;
    border:2px dashed rgba(255,255,255,.5); background:rgba(255,255,255,.08); color:#fff; padding:0; }
  .lucka.kan { background:linear-gradient(135deg,#ffd54f,#ff8f00); color:#b71c1c; border:2px solid #fff; cursor:pointer; animation:bastis 1.6s ease-in-out infinite; }
  .lucka.julafton { grid-column:span 2; aspect-ratio:auto; font-size:20px; }
  .lucka.oppnad { background:rgba(255,255,255,.9); color:#1b5e20; border-style:solid; font-size:20px; }
  .lucka.oppnad span { font-size:9px; }
  .lucka.last { opacity:.55; }
  .lucka.oppnas { animation:vand .6s; }
  .djurbrev { background:#fffde7; color:#5d4037; font-family:Georgia,serif; }
  .djurbrev p { margin:6px 0; }
  .syskon-kort { background:linear-gradient(135deg,#e8eaf6,#e0f7fa); color:#1a237e; }
  .syskon-kort.klar { background:linear-gradient(135deg,#e8f5e9,#c8e6c9); color:#1b5e20; }
  .sy-rubrik { font-weight:700; font-size:13px; opacity:.8; }
  .sy-text { font-size:16px; font-weight:600; margin:4px 0 8px; }
  .sy-delar { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
  .sy-del { font-size:12px; padding:2px 8px; border-radius:10px; background:rgba(255,255,255,.6); }
  .sy-del.jag { outline:2px solid currentColor; }
  .repetera-kort { border-left:4px solid #7e57c2; }
  .heja-kort { display:flex; gap:12px; align-items:flex-start; background:linear-gradient(135deg,#fce4ec,#f8bbd0); color:#4a148c; animation:gs-pop .6s; }
  .heja-ikon { font-size:40px; animation:bastis 1.6s ease-in-out infinite; }
  .heja-text { flex:1; }
  .heja-lapp { font-size:17px; font-weight:600; margin:4px 0 8px; font-family:"Comic Sans MS","Chalkboard SE",cursive; }
  .heja-val { display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end; margin:6px 0; }
  .dagens-kort { background:linear-gradient(135deg,#fff8e1,#e1f5fe); color:#263238; }
  .dagens-halsning { font-size:15px; font-weight:600; margin-bottom:8px; }
  .handelse { font-size:13px; padding:6px 10px; border-radius:10px; background:rgba(255,152,0,.18); margin-bottom:8px; }
  .gata { padding:8px 10px; border-radius:10px; background:rgba(255,255,255,.6); margin-bottom:6px; }
  .gata-rubrik { font-weight:700; font-size:13px; }
  .gata-fraga { font-size:15px; margin:4px 0 6px; font-style:italic; }
  .gata-rad { display:flex; gap:6px; align-items:center; margin-bottom:4px; }
  .gata-rad input { flex:1; min-width:0; }
  .gata-igar { font-size:13px; padding:6px 10px; border-radius:10px; background:rgba(76,175,80,.15); }
  .prat-bubbla { position:relative; font-size:13px; padding:6px 10px; margin-bottom:6px; border-radius:12px; background:var(--secondary-background-color, #f1f1f1); }
  .rekord-rad.ny { background:rgba(255,193,7,.15); }
  .ny-bricka { font-size:11px; font-weight:700; color:#e65100; }
  .varld-berattelse { font-size:12px; font-style:italic; opacity:.9; margin:4px 0 6px; }
  .varld-berattelse.stor { font-size:14px; padding:10px 12px; border-radius:12px; border-left:4px solid var(--farg); background:color-mix(in srgb, var(--farg) 12%, transparent); font-style:normal; }
  .glosstrid-knapp { background:linear-gradient(135deg,#311b92,#c62828) !important; color:#fff !important; }
  .gs-scen { position:relative; overflow:hidden; display:flex; align-items:center; justify-content:space-between; gap:8px; padding:12px; border-radius:16px; color:#fff;
    background:radial-gradient(ellipse at 50% 30%, color-mix(in srgb, var(--varld) 60%, #000), #0b0b20 80%); }
  .gs-sida { flex:1; text-align:center; min-width:0; }
  .gs-sida .progress { height:8px; background:rgba(255,255,255,.2); margin:4px 8px; }
  .gs-sida .progress.liv div { background:#66bb6a; }
  .gs-figur { height:96px; display:flex; align-items:center; justify-content:center; }
  .gs-figur svg { width:90px; height:90px; }
  .gs-figur.mon { font-size:64px; }
  .gs-figur.traff { animation:gs-skaka .4s; }
  @keyframes gs-skaka { 0%,100% { transform:translateX(0); } 25% { transform:translateX(-8px) rotate(-6deg); } 75% { transform:translateX(8px) rotate(6deg); } }
  .gs-mitt { font-size:28px; text-align:center; min-width:70px; }
  .gs-traff { color:#ffeb3b; font-weight:800; animation:gs-pop .5s; }
  .gs-traff small, .gs-miss small { display:block; font-size:11px; }
  .gs-miss { color:#ff8a80; font-weight:800; animation:gs-pop .5s; }
  @keyframes gs-pop { 0% { transform:scale(.4); opacity:0; } 60% { transform:scale(1.3); opacity:1; } 100% { transform:scale(1); } }
  .gs-scen.kombo { box-shadow:0 0 0 3px #ff6d00, 0 0 22px #ff6d00; animation:gs-glod 1.2s ease-in-out infinite; }
  @keyframes gs-glod { 50% { box-shadow:0 0 0 3px #ffab00, 0 0 34px #ff3d00; } }
  .gs-scen.skak { animation:gs-skak .45s, gs-glod 1.2s ease-in-out infinite; }
  @keyframes gs-skak { 0%,100% { transform:none; } 20% { transform:translate(-10px,6px); } 40% { transform:translate(9px,-7px); } 60% { transform:translate(-7px,-4px); } 80% { transform:translate(6px,5px); } }
  .gs-skott { position:absolute; left:22%; top:38%; font-size:34px; z-index:2; animation:gs-flyg .45s cubic-bezier(.5,0,.9,.6) forwards; filter:drop-shadow(0 0 8px #fff); }
  @keyframes gs-flyg { 0% { transform:translateX(0) scale(.6) rotate(0); opacity:1; } 90% { opacity:1; } 100% { transform:translateX(52vw) scale(1.5) rotate(540deg); opacity:0; } }
  .gs-siffra { position:absolute; right:14%; top:30%; z-index:3; font-size:30px; font-weight:900; color:#ffeb3b; text-shadow:0 2px 0 #e65100, 0 0 10px #ff6d00; opacity:0;
    animation:gs-siffra 1.1s ease-out .4s forwards; }
  .gs-siffra.stor { font-size:44px; }
  @keyframes gs-siffra { 0% { opacity:0; transform:translateY(10px) scale(.5); } 20% { opacity:1; transform:translateY(-10px) scale(1.3); } 100% { opacity:0; transform:translateY(-60px) scale(1); } }
  .gs-figur.skjuter { animation:gs-rekyl .4s; }
  @keyframes gs-rekyl { 30% { transform:translateX(14px) scale(1.08); } }
  .gs-figur.mon.traff { animation:gs-skaka .4s .4s, gs-vit .4s .4s; }
  @keyframes gs-vit { 30% { filter:brightness(3) saturate(0); } }
  .gs-figur.mon.anfall { animation:gs-anfall .6s; }
  @keyframes gs-anfall { 40% { transform:translateX(-46vw) scale(1.25) rotate(-10deg); } }
  .gs-figur.traffad { animation:gs-traffad .6s .3s; }
  @keyframes gs-traffad { 0% { filter:brightness(3) saturate(0); transform:translateX(-12px); } 30% { transform:translateX(8px); filter:none; } 50% { filter:brightness(2) hue-rotate(-40deg); transform:translateX(-6px); } 100% { transform:none; filter:none; } }
  .gs-blixt { position:absolute; inset:0; background:#ff1744; opacity:0; animation:gs-blixt .5s .25s; pointer-events:none; }
  @keyframes gs-blixt { 30% { opacity:.35; } }
  .gs-kombo { text-align:center; font-weight:700; color:#ff6d00; margin:6px 0; min-height:20px; }
  .gs-fraga { font-size:26px; font-weight:700; text-align:center; margin:10px 0 12px; }
  .gs-facit { text-align:center; margin-bottom:8px; color:#c62828; }
  .tl-ledare { display:flex; gap:12px; align-items:center; padding:12px 14px; border-radius:14px; background:linear-gradient(135deg,#fff8e1,#ffe082); color:#4e342e; margin-bottom:10px; }
  .tl-ledare.tom { justify-content:center; }
  .tl-krona { font-size:34px; }
  .tl-staplar { display:flex; flex-direction:column; gap:8px; margin-bottom:6px; }
  .tl-rad { padding:6px 8px; border-radius:10px; }
  .tl-rad.jag { background:var(--secondary-background-color, rgba(0,0,0,.04)); }
  .tl-namn { margin-bottom:4px; }
  .tl-bar { position:relative; height:22px; background:var(--divider-color, #e0e0e0); border-radius:11px; overflow:hidden; }
  .tl-bar div { height:100%; background:linear-gradient(90deg,#ffb300,#ff7043); border-radius:11px; }
  .tl-bar span { position:absolute; right:8px; top:2px; font-weight:700; font-size:13px; }
  .tl-tabell-wrap { overflow-x:auto; }
  .tl-tabell { width:100%; border-collapse:collapse; font-size:14px; }
  .tl-tabell th, .tl-tabell td { padding:6px 8px; text-align:center; border-bottom:1px solid var(--divider-color, #e0e0e0); }
  .tl-tabell td:first-child { text-align:left; white-space:nowrap; }
  .tl-tabell th.jag, .tl-tabell td.jag { background:var(--secondary-background-color, rgba(0,0,0,.04)); }
  .tl-tabell td.basta { font-weight:700; color:#e65100; }
  .tl-grupp td { font-weight:700; text-align:left !important; padding-top:12px; border-bottom:2px solid var(--divider-color, #e0e0e0); }
  .tl-info { margin-top:8px; }
  .glod-guld .kropp { filter:drop-shadow(0 0 6px #ffd700) drop-shadow(0 0 16px #ffb300) saturate(1.3); }
  .glod-ljus .kropp { filter:drop-shadow(0 0 10px #ffd54f) drop-shadow(0 0 22px #ffb300); }
  .djur-figur.eff { position:relative; }
  a.knapp-lank { display:block; text-align:center; text-decoration:none; }
  .widget-steg { line-height:1.6; padding-left:20px; } .widget-steg li { margin-bottom:6px; }
  .djur-knappar { display:flex; gap:6px; flex-wrap:wrap; }
  .titel-bricka { font-size:11px; background:#ffd54f; color:#3e2723; border-radius:8px; padding:1px 6px; white-space:nowrap; }
  .pass-kort { display:block; width:100%; text-align:left; border:none; cursor:pointer; border-radius:16px; padding:12px 16px; margin-bottom:12px; color:#fff;
               background:linear-gradient(135deg,#3949ab,#8e24aa); }
  .pass-kort .progress { background:rgba(255,255,255,.3); margin:6px 0; } .pass-kort .progress div { background:#ffd54f; }
  .pass-xp { text-align:center; margin:10px 0; font-size:16px; }
  .pass-lista { display:flex; flex-direction:column; gap:6px; }
  .pass-rad { display:grid; grid-template-columns:34px 34px 1fr auto; align-items:center; gap:8px; background:var(--card-background-color); border-radius:12px; padding:8px 10px; opacity:.6; }
  .pass-rad.nadd { opacity:1; } .pass-rad.special { border:2px solid #ab47bc; } .pass-rad.final { border:3px solid #ffd54f; background:linear-gradient(135deg,rgba(255,213,79,.25),rgba(171,71,188,.25)); }
  .pass-niva { font-weight:800; text-align:center; } .pass-ikon { font-size:24px; text-align:center; }
  .djur-val button.vald { outline:3px solid #4fc98a; }
  .boss-kort { display:flex; gap:12px; align-items:center; border-radius:16px; padding:12px 16px; margin-bottom:12px; color:#fff; background:linear-gradient(135deg,#263238,#b71c1c); }
  .boss-kort.vunnen { background:linear-gradient(135deg,#1b5e20,#43a047); }
  .boss-figur { font-size:54px; animation:vicka 2.4s ease-in-out infinite; }
  .boss-kort .muted { color:rgba(255,255,255,.75); }
  .boss-hp { background:rgba(255,255,255,.25); margin:6px 0; } .boss-hp div { background:#ff5252; }
  .boss-kort { position:relative; overflow:hidden; background:linear-gradient(135deg,#263238,var(--varld,#b71c1c)); }
  .boss-kort.varldsboss { background:linear-gradient(135deg,#1a0000,#b71c1c 60%,#ff6f00); box-shadow:0 0 0 3px #ffd54f inset; }
  .karta-knapp { margin-top:8px; background:rgba(255,255,255,.2); color:#fff; border:none; }
  .van-lista { list-style:none; padding:0; margin:0; } .van-vantar { padding-left:18px; } .van-vantar li { margin:6px 0; }
  .van-rad { display:flex; align-items:center; gap:10px; padding:8px; border-radius:12px; margin-bottom:6px; background:var(--card-background-color,#fff); box-shadow:0 1px 3px rgba(0,0,0,.12); }
  .van-rad.jag { outline:2px solid #ffd54f; }
  .van-plats { font-weight:800; width:22px; text-align:center; } .van-djur { width:40px; height:40px; } .van-djur svg { width:100%; height:100%; }
  .van-namn { flex:1; } .van-niva { text-align:right; font-weight:700; }
  .karta-topp { text-align:center; font-weight:600; margin-bottom:8px; }
  .karta { border-radius:16px; overflow:hidden; background:linear-gradient(#e8f5e9,#fff8e1); padding-bottom:8px; }
  .karta-varld { color:#fff; font-weight:700; text-align:center; padding:6px; }
  .karta-rad { position:relative; height:76px; background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--farg) 14%,transparent),transparent); }
  .karta-rad::before { content:""; position:absolute; left:calc(var(--x) - 3px); top:-30px; width:6px; height:110px; background:repeating-linear-gradient(#bcaaa4 0 8px,transparent 8px 14px); z-index:0; }
  .karta-nod { position:absolute; left:var(--x); top:50%; transform:translate(-50%,-50%); width:54px; height:54px; border-radius:50%; display:flex; align-items:center; justify-content:center; background:#fff; border:4px solid var(--farg); box-shadow:0 3px 0 rgba(0,0,0,.2); z-index:1; }
  .karta-nod.boss { width:66px; height:66px; border-color:#ffd54f; background:#fff3e0; }
  .karta-nod.last { background:#eceff1; border-color:#b0bec5; }
  .karta-nod.klar { background:color-mix(in srgb,var(--farg) 25%,#fff); }
  .karta-nod.nu { animation:nodPuls 1.4s ease-in-out infinite; box-shadow:0 0 0 6px rgba(255,213,79,.6); }
  .nod-ikon { font-size:26px; } .karta-nod.last .nod-ikon { font-size:18px; opacity:.6; }
  .nod-nr { position:absolute; bottom:-8px; background:var(--farg); color:#fff; font-size:11px; font-weight:700; border-radius:8px; padding:0 6px; }
  .nod-stj { position:absolute; top:-12px; font-size:11px; white-space:nowrap; }
  .nod-djur { position:absolute; right:-46px; top:-14px; width:44px; height:44px; } .nod-djur svg, .nod-syskon svg { width:100%; height:100%; }
  .nod-syskon { position:absolute; left:-50px; top:-10px; width:40px; height:40px; text-align:center; } .nod-syskon b { display:block; font-size:9px; margin-top:-4px; }
  @keyframes nodPuls { 0%,100% { transform:translate(-50%,-50%) scale(1); } 50% { transform:translate(-50%,-50%) scale(1.08); } }
  .attack-rad { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-top:8px; }
  .attack-rad .energi { font-weight:700; background:rgba(255,235,59,.25); border-radius:12px; padding:4px 10px; }
  .attack-knapp { display:flex; flex-direction:column; align-items:center; min-width:52px; padding:4px 6px; border-radius:12px; border:2px solid rgba(255,255,255,.4); background:rgba(255,255,255,.15); color:#fff; cursor:pointer; line-height:1.1; }
  .attack-knapp .ai { font-size:22px; } .attack-knapp small { font-size:10px; opacity:.85; }
  .attack-knapp.svag { border-color:#ffeb3b; box-shadow:0 0 8px #ffeb3b; }
  .attack-knapp:disabled { opacity:.4; cursor:default; }
  .attack-sak.svag { outline:2px solid #fbc02d; }
  .sak-kort.svag { outline:2px solid #fbc02d; }
  .grupp-kort { border-left:4px solid var(--primary-color); padding:4px 0 4px 10px; margin:8px 0; }
  .sk-rad { padding:8px 0; border-bottom:1px solid var(--divider-color); }
  .badge { background:#e53935; color:#fff; border-radius:10px; padding:1px 7px; font-size:12px; }
  .stund { display:flex; flex-direction:column; gap:6px; }
  .stund.klar { outline:2px solid #fbc02d; }
  .stund-rad { display:grid; grid-template-columns:minmax(70px,auto) 1fr auto; gap:8px; align-items:center; }
  .duell-ord { font-size:28px; font-weight:800; text-align:center; margin:10px 0; }
  .duell-fraga input { width:100%; font-size:20px; padding:10px; box-sizing:border-box; margin-bottom:8px; }
  .duell-senast { text-align:center; font-weight:800; font-size:18px; animation:lsTraff .4s; }
  .duell-senast.ratt { color:#2e7d32; } .duell-senast.fel { color:#c62828; }
  .lag-folk { display:flex; gap:10px; flex-wrap:wrap; margin:8px 0; }
  .lag-pers { flex:1 1 120px; display:flex; flex-direction:column; align-items:center; gap:2px; background:rgba(127,127,127,.08); border-radius:12px; padding:8px; text-align:center; }
  .lag-djur, .ls-djur { width:64px; height:64px; position:relative; font-size:44px; }
  .lag-djur svg, .ls-djur svg { width:100%; height:100%; }
  .lagboss { display:flex; gap:12px; align-items:center; }
  .lagboss-figur { font-size:56px; }
  .lagboss.klar { outline:2px solid #fbc02d; }
  .lag-bidrag { display:flex; gap:10px; flex-wrap:wrap; font-size:13px; margin-top:4px; }
  .lag-marken { display:flex; flex-wrap:wrap; gap:8px; font-size:20px; }
  .ls-plan { background:linear-gradient(#311b92,#4a148c 55%,#1a237e); color:#fff; border-radius:16px; padding:10px; display:flex; flex-direction:column; gap:6px; }
  .ls-rad { display:flex; justify-content:center; gap:10px; }
  .ls-pers { display:flex; flex-direction:column; align-items:center; gap:2px; padding:6px; border-radius:12px; min-width:92px; background:rgba(255,255,255,.08); transition:opacity .3s; }
  .ls-pers[data-ls-mal] { cursor:pointer; }
  .ls-pers.mal { outline:2px solid #ffeb3b; }
  .ls-pers.ute { opacity:.4; }
  .ls-pers.traff .ls-djur { animation:lsTraff .5s ease-out 2; }
  @keyframes lsTraff { 0%,100% { transform:none; filter:none; } 30% { transform:translateX(-6px); filter:brightness(2) saturate(0); } 60% { transform:translateX(6px); } }
  .ls-skold { position:absolute; right:-8px; bottom:-4px; font-size:22px; }
  .ls-liv { width:80px; height:8px; }
  .ls-liv div { background:linear-gradient(90deg,#00c853,#b2ff59); }
  .ls-vs { text-align:center; font-weight:900; font-size:20px; color:#ffeb3b; }
  .ls-logg { list-style:none; padding:8px; margin:8px 0; font-size:13px; background:rgba(127,127,127,.1); border-radius:10px; }
  .ls-logg li.de { color:#e57373; }
  .ls-slut { font-size:22px; font-weight:800; text-align:center; margin:10px 0; }
  .ls-slut.vinst { color:#f9a825; animation:lsTraff .6s; }
  .sak-kort.vald { outline:3px solid #42a5f5; box-shadow:0 0 10px rgba(66,165,245,.5); }
  .liv-rad { display:flex; align-items:center; gap:8px; margin-top:8px; font-size:13px; }
  .liv-rad .djur-liv { flex:1; height:10px; margin:0; } .liv-rad .djur-liv div { background:linear-gradient(90deg,#00c853,#69f0ae); }
  .liv-rad .djur-liv.lag div { background:linear-gradient(90deg,#d50000,#ff8a80); }
  .ko-text { margin-top:6px; font-weight:700; }
  .strid-knapp { margin-top:8px; }
  .djur-niva { margin-top:6px; }
  .niva-upp { margin-top:8px; padding:6px 10px; border-radius:10px; background:linear-gradient(90deg,#ffd54f,#ffb300); color:#3e2723; font-weight:800; animation:nivaUpp 1s ease-out; }
  @keyframes nivaUpp { 0% { transform:scale(.6); opacity:0; } 60% { transform:scale(1.08); opacity:1; } 100% { transform:none; } }
  .arena-jag { display:flex; gap:12px; align-items:center; }
  .arena-djur { width:90px; height:90px; flex:none; } .arena-djur svg { width:100%; height:100%; }
  .arena-lista li { display:flex; align-items:center; gap:10px; }
  .arena-lista li > span:nth-child(2) { flex:1; }
  .dryck-knapp { background:rgba(255,255,255,.18); color:#fff; border:1px solid rgba(255,255,255,.45); }
  .repris-rad { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-top:8px; }
  .repris-knapp { background:rgba(0,0,0,.25); color:#fff; border:1px solid rgba(255,255,255,.4); }
  .repris-knapp.ny { border-color:#ffeb3b; box-shadow:0 0 8px #ffeb3b; }
  .attack-anim { position:absolute; inset:0; pointer-events:none; z-index:2; }
  .anim-djur { position:absolute; left:58%; bottom:6px; width:64px; height:64px; animation:djurAnfall 1.8s ease-in-out forwards; }
  .anim-djur svg { width:100%; height:100%; }
  .anim-skott { position:absolute; left:60%; top:40%; font-size:36px; opacity:0; animation:skott 1.8s ease-in forwards; }
  .anim-skada { position:absolute; left:14px; top:4px; font-size:30px; font-weight:900; color:#ffeb3b; text-shadow:0 2px 4px #000; opacity:0; animation:skadaUpp 1.8s ease-out forwards; }
  .anim-skada small { display:block; font-size:12px; }
  .anim-skada.svag { color:#ff9100; font-size:36px; }
  .boss-figur.traff { animation:bossTraff 1.8s ease-in-out; }
  @keyframes djurAnfall { 0% { transform:translateX(140px); opacity:0; } 20% { transform:translateX(0); opacity:1; } 35% { transform:translateX(-24px) scale(1.15); } 50%,80% { transform:translateX(0); opacity:1; } 100% { opacity:0; } }
  @keyframes skott { 0%,30% { left:60%; transform:scale(.6); opacity:0; } 35% { opacity:1; } 60% { left:24px; transform:scale(1.5); opacity:1; } 61%,100% { left:24px; opacity:0; } }
  @keyframes skadaUpp { 0%,55% { opacity:0; transform:translateY(20px) scale(.6); } 65% { opacity:1; transform:translateY(0) scale(1.3); } 90% { opacity:1; transform:translateY(-8px) scale(1); } 100% { opacity:0; transform:translateY(-16px); } }
  @keyframes bossTraff { 0%,55% { transform:none; filter:none; } 60% { transform:translateX(-8px) rotate(-8deg); filter:brightness(2.5); } 68% { transform:translateX(8px) rotate(8deg); } 76% { transform:translateX(-5px); filter:none; } 85%,100% { transform:none; } }
  .rum-scen { position:relative; height:240px; border-radius:18px; overflow:hidden; margin-bottom:10px; box-shadow:inset 0 0 0 3px rgba(0,0,0,.08); }
  .rum-golv { position:absolute; left:0; right:0; bottom:0; height:34%; border-top:4px solid rgba(0,0,0,.12); }
  .rum-sak { position:absolute; line-height:1; }
  .rum-fonster { top:18px; left:22px; font-size:46px; background:rgba(255,255,255,.6); border:5px solid #8d6e63; border-radius:6px; padding:4px; } .rum-fonster.tomt { opacity:.5; }
  .rum-tavla { top:22px; right:26px; font-size:40px; } .rum-lampa { top:12px; left:48%; font-size:36px; }
  .rum-sang { bottom:14%; right:16px; font-size:70px; } .rum-vaxt { bottom:16%; left:14px; font-size:52px; } .rum-leksak { bottom:6%; left:30%; font-size:34px; }
  .rum-djur { position:absolute; bottom:4%; left:50%; transform:translateX(-30%); }
  .rum-djur .djur-scen { background:transparent !important; box-shadow:none; width:120px !important; height:120px !important; }
  .variant-anim { animation:variantRegnbage 4s linear infinite; } @keyframes variantRegnbage { to { filter:hue-rotate(360deg) saturate(2); } }
  .paket-kort { display:flex; gap:12px; align-items:center; background:linear-gradient(135deg,#7e57c2,#ec407a); color:#fff; border-radius:16px; padding:12px; margin:8px 0; }
  .paket-kort.sasongs { background:linear-gradient(135deg,#ff6f00,#d81b60); }
  .paket-kort.kopt { opacity:.6; }
  .paket-kort .primary { background:#ffd54f; color:#3e2723; margin-top:6px; }
  .paket-djur { position:relative; width:96px; height:96px; flex:none; background:rgba(255,255,255,.18); border-radius:14px; }
  .paket-djur .exkl { position:absolute; bottom:-6px; left:50%; transform:translateX(-50%); white-space:nowrap; background:#ffd54f; color:#3e2723; font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px; }
  .paket-ikon { font-size:56px; width:96px; text-align:center; }
  .paket-info { flex:1; display:flex; flex-direction:column; gap:4px; }
  .paket-saker { font-size:26px; letter-spacing:4px; } .paket-saker sup { font-size:10px; color:#ffd54f; }
  .djur-scen.glod-sol .kropp { filter:drop-shadow(0 0 10px #ffeb3b) drop-shadow(0 0 24px #ff9800); }
  .djur-scen.glod-karlek .kropp { animation:karlek 1.5s ease-in-out infinite; } @keyframes karlek { 50% { filter:drop-shadow(0 0 14px #ff4081); } }
  .djur-scen.glod-legend .kropp { animation:legend 2.5s linear infinite; } @keyframes legend { 0% { filter:drop-shadow(0 0 8px #ffd700); } 50% { filter:drop-shadow(0 0 20px #fff176) drop-shadow(0 0 30px #ffb300); } 100% { filter:drop-shadow(0 0 8px #ffd700); } }
  .sasong { background:linear-gradient(135deg,rgba(255,152,0,.15),rgba(233,30,99,.15)); border-radius:14px; padding:4px 10px 10px; margin:10px 0; }
  .butik-knapp { align-self:flex-start; margin-top:4px; }
  .butik-saldo { text-align:center; margin:10px 0; font-size:16px; }
  .sak-rutnat { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:8px; }
  .sak-kort { background:var(--card-background-color); border-radius:12px; padding:10px 6px; text-align:center; display:flex; flex-direction:column; align-items:center; gap:4px;
              border:2px solid transparent; box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .sak-kort.pa { border-color:#4fc98a; } .sak-kort.last { opacity:.55; }
  .sak-ikon { font-size:34px; }
  .utmaning-kort { background:var(--card-background-color); border-radius:16px; padding:12px 16px; margin-bottom:12px; border:2px solid transparent;
                   box-shadow:var(--ha-card-box-shadow, 0 1px 2px rgba(0,0,0,.12)); }
  .utmaning-kort.klar { border-color:#4fc98a; }
  .utm-rad { padding:4px 0; } .utm-rad.ok { opacity:.6; text-decoration:line-through; }
  .skydd { font-size:14px; margin-left:4px; }
  .rekord-knapp { background:linear-gradient(135deg,#ff9800,#f44336); color:#fff; border:none; }
  .rekord-knapp .small { color:rgba(255,255,255,.85); } .rekord-siffra { font-weight:700; font-size:18px; }
  .rekord-intro { text-align:center; padding:10px 0; }
  .rekord-topp { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:16px; }
  .rek-tid { font-size:40px; font-weight:800; min-width:60px; } .rek-tid.bradskande { color:#f44336; animation:puls .5s infinite; }
  .rek-poang { font-size:28px; font-weight:700; color:#ff9800; }
  .rek-fraga { font-size:30px; font-weight:700; text-align:center; padding:26px 10px; border-radius:16px; background:var(--card-background-color); margin-bottom:14px; transition:background .15s; }
  .rek-fraga.ratt-flash { background:#4fc98a; color:#fff; } .rek-fraga.fel-flash { background:#f44336; color:#fff; }
  .rek-alt { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .rek-alt button { font-size:18px; padding:18px 8px; border-radius:14px; border:none; background:var(--secondary-background-color); color:var(--primary-text-color); cursor:pointer; min-height:70px; }
  .rek-alt button.ratt { background:#4fc98a; color:#fff; }
  .insp-ruta { background:var(--secondary-background-color); border-radius:12px; padding:12px; margin:8px 0; display:flex; flex-direction:column; gap:8px; }
  .insp-rad { display:flex; align-items:center; gap:8px; font-size:16px; }
  .insp-prick { width:14px; height:14px; border-radius:50%; background:#db4437; animation:puls 1s ease-in-out infinite; }
  @keyframes puls { 50% { opacity:.3; } }
  .zoom-knappar { position:fixed; bottom:calc(20px + env(safe-area-inset-bottom)); right:16px; display:flex; gap:10px; }
  .zoom-knappar button { width:52px; height:52px; border-radius:50%; border:none; background:rgba(255,255,255,.2); color:#fff; font-size:28px; cursor:pointer; }
  .zoom-tips { position:fixed; bottom:calc(32px + env(safe-area-inset-bottom)); left:16px; color:rgba(255,255,255,.6); font-size:13px; pointer-events:none; }
  .viewer .close { position:fixed; top:calc(10px + env(safe-area-inset-top)); right:12px; color:#fff; font-size:28px; background:rgba(255,255,255,.2); border:none; border-radius:50%; width:48px; height:48px; z-index:1; }
  @keyframes s { to { transform:rotate(360deg); } }
`;

// Elementnamnet följer versionen (?v=1.6.0 -> skolan-panel-1-6-0), så en ny version aldrig krockar med en gammal i minnet.
const TAG = `skolan-panel-${(new URL(import.meta.url).searchParams.get("v") || "0").replace(/\./g, "-")}`;
if (!customElements.get(TAG)) customElements.define(TAG, SkolanPanel);
// Gamla namnet, för den som laddar sidan innan Home Assistant har startats om.
if (!customElements.get("skolan-panel")) customElements.define("skolan-panel", class extends SkolanPanel {});
