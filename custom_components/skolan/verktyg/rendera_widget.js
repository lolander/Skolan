// Kör: node rendera_widget.js i en tom mapp, sen rsvg-convert -w 300 -h 300 svg/X.svg -o /config/www/skolan_djur/X.png för varje fil.
// Ritar alla husdjur i alla humör som SVG + ankarpunkter för hatt/kompis (för widgeten)
const fs = require("fs");
const src = fs.readFileSync("/config/custom_components/skolan/www/panel.js", "utf8");
const a = src.indexOf("const DJUR_UTSEENDE"), b = src.indexOf("const DJUR_HUMOR");
eval(src.slice(a, b).replace("const DJUR_UTSEENDE", "globalThis.DJUR_UTSEENDE").replace("const PA_OGONEN", "globalThis.PA_OGONEN").replace("function ritaDjur", "globalThis.ritaDjur=function"));
const slug = (art) => [...art].filter((c) => c !== "️").map((c) => c.codePointAt(0).toString(16)).join("-");
const STEG = 3, s = 0.72 + STEG * 0.06;
const T = (x, y) => [100 + (x - 100) * s, 185 + (y - 185) * s];
// OBS: widgeten flyttar hattar 7 enheter högre än appen (ankare hatt y - 7), se nedan
const ankare = {};
fs.mkdirSync("svg", { recursive: true });
for (const art of Object.keys(DJUR_UTSEENDE)) {
  const u = DJUR_UTSEENDE[art];
  for (const h of ["glad", "nojd", "hungrig", "ledsen"]) fs.writeFileSync(`svg/${slug(art)}_${h}.svg`, ritaDjur(art, h, STEG, {}));
  let hatt, ogon;
  if (u.form) { const [cx, cy, r] = u.ansikte; hatt = [...T(cx + 4, u.topp + 6), 50 * s]; hatt[1] -= 7; ogon = [...T(cx, cy + 14), (r + 6) * s]; }
  else { hatt = [...T(104, 98 - 44 + 16), 50 * s]; hatt[1] -= 7; ogon = [...T(100, 98 + 14), 46 * s]; }
  ankare[slug(art)] = { hatt: hatt.map((v) => Math.round(v)), ogon: ogon.map((v) => Math.round(v)) };
}
for (const h of ["glad", "nojd", "hungrig", "ledsen"]) fs.writeFileSync(`svg/agg_${h}.svg`, ritaDjur("🐶", h, 0, {}));
fs.writeFileSync("/config/www/skolan_djur/ankare.json", JSON.stringify({ ankare, kompis: [162, 178, 38], ogon_saker: [...PA_OGONEN] }));
console.log(Object.keys(ankare).length);
