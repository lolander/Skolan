// Skolan: mitt husdjur 🐾 (klistras in i appen Scriptable)
const BAS = "__BAS__";
const d = await new Request(BAS + "/api/skolan/widget/__NYCKEL__").loadJSON();
const bild = await new Request(BAS + d.bild).loadImage();
const S = 1.5; // bilden är 300 px, ritningen 200
const dc = new DrawContext();
dc.size = new Size(300, 300); dc.opaque = false; dc.respectScreenScale = true;
dc.drawImageInRect(bild, new Rect(0, 0, 300, 300));
const emoji = (text, pos) => {
  if (!text || !pos) return;
  const [x, y, f] = pos;
  dc.setFont(Font.systemFont(f * S)); dc.setTextAlignedCenter();
  dc.drawTextInRect(text, new Rect(x * S - f * S, y * S - f * S * 0.95, f * S * 2, f * S * 1.4));
};
emoji(d.hatt, d.hatt_pos);
emoji(d.kompis, d.kompis_pos);
const w = new ListWidget();
const g = new LinearGradient(); g.colors = d.bg.map((c) => new Color(c)); g.locations = [0, 1];
w.backgroundGradient = g; w.setPadding(6, 8, 6, 8); w.url = BAS + "/skolan";
const fg = new Color(d.fg);
const sc = d.schema; // lektionsschemat (om barnet har fotat det)
const rad = (st, text, size, bold) => { const t = st.addText(text); t.font = bold ? Font.boldSystemFont(size) : Font.systemFont(size); t.textColor = fg; t.lineLimit = 2; t.minimumScaleFactor = 0.7; return t; };
if (config.widgetFamily === "medium") {
  const h = w.addStack(); h.centerAlignContent();
  h.addImage(dc.getImage()).imageSize = new Size(130, 130);
  h.addSpacer(8);
  const v = h.addStack(); v.layoutVertically();
  rad(v, d.namn, 18, true);
  rad(v, d.text, 14);
  v.addSpacer(6);
  rad(v, `🔥 ${d.svit} dagar · ⭐ ${d.stjarnor}`, 13);
  if (d.utmaning && !sc) rad(v, `🎯 Utmaning ${d.utmaning}`, 13);
  if (sc) {
    if (sc.nu) rad(v, `📖 Nu: ${sc.nu.namn} till ${sc.nu.slut}`, 13);
    if (sc.nasta) rad(v, `📚 ${sc.nasta_dag ? sc.nasta_dag[0].toUpperCase() + sc.nasta_dag.slice(1) : "Nästa"}: ${sc.nasta.namn} ${sc.nasta.start}`, 13, true);
    if (sc.rast) rad(v, sc.rast.nu ? `🔔 ${sc.rast.lunch ? "Lunch" : "Rast"} nu till ${sc.rast.slut}` : `🔔 ${sc.rast.lunch ? "Lunch" : "Rast"} ${sc.rast.start}–${sc.rast.slut}`, 13);
  }
} else {
  const h = w.addStack(); h.addSpacer();
  h.addImage(dc.getImage()).imageSize = new Size(sc && sc.nasta ? 80 : 110, sc && sc.nasta ? 80 : 110);
  h.addSpacer();
  const n = rad(w, `${d.namn} · 🔥${d.svit}`, 13, true); n.centerAlignText();
  if (sc && sc.nasta) { const t = rad(w, `📚 ${sc.nasta.namn} ${sc.nasta.start}`, 12); t.centerAlignText(); }
  if (sc && sc.rast) { const t = rad(w, `🔔 ${sc.rast.nu ? "nu–" + sc.rast.slut : sc.rast.start}`, 12); t.centerAlignText(); }
}
// Uppdatera när nästa lektion börjar eller slutar (iOS bestämmer till slut själv hur ofta).
const byte = sc && sc.byte ? new Date(sc.byte) : null;
w.refreshAfterDate = byte && byte - Date.now() < 15 * 60 * 1000 ? byte : new Date(Date.now() + 15 * 60 * 1000);
Script.setWidget(w);
if (!config.runsInWidget) await w.presentMedium();
Script.complete();
