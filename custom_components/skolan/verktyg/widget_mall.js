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
  if (d.utmaning) rad(v, `🎯 Utmaning ${d.utmaning}`, 13);
} else {
  const h = w.addStack(); h.addSpacer();
  h.addImage(dc.getImage()).imageSize = new Size(110, 110);
  h.addSpacer();
  const n = rad(w, `${d.namn} · 🔥${d.svit}`, 13, true); n.centerAlignText();
}
w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);
Script.setWidget(w);
if (!config.runsInWidget) await w.presentMedium();
Script.complete();
