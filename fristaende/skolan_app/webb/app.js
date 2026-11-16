// Skolan fristående: inloggning, första start, inställningar, mobilkoppling och laddning av Skolans panel.
const rot = document.getElementById("rot");
const FARGER = ["#4f8ef7", "#f7a14f", "#4fc98a", "#e05f8a", "#9b6cf0", "#2bb5c4", "#d4b02a", "#e0603a"];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const $ = (s) => rot.querySelector(s);

let token = "";
try { token = localStorage.getItem("skolan_token") || ""; } catch (e) { /* privat läge */ }
const sparaToken = (t) => { token = t; try { t ? localStorage.setItem("skolan_token", t) : localStorage.removeItem("skolan_token"); } catch (e) { /* ok */ } };

async function api(url, body, metod) {
  const r = await fetch(url, {
    method: metod || (body === undefined ? "GET" : "POST"),
    headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.message || (r.status === 403 ? "Bara en förälder kan göra det." : r.statusText));
  return d;
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

async function start() {
  let info;
  try { info = await api("/app/start"); } catch (e) { return visaFel("Kan inte nå Läxspelet på datorn. Är den igång?"); }
  const vag = location.pathname;
  if (!info.installerad) return info.fran_datorn ? forstaStart() : visaFel("Läxspelet är inte inställd än. Starta den på familjens dator först.");
  if (vag === "/app/koppla" && info.adresser) return koppla(info);
  if (!info.anvandare) return valjPerson(info);
  if (vag === "/app/installning") return info.anvandare.is_admin ? installning(info) : (location.href = "/skolan");
  if (vag === "/app/koppla") return info.anvandare.is_admin ? koppla(info) : (location.href = "/skolan");
  return visaSkolan(info);
}

function visaFel(text) {
  rot.innerHTML = `<div class="mitt"><h1>📚 Läxspelet</h1><div class="kort">${esc(text)}</div><button class="primar" onclick="location.reload()">Försök igen</button></div>`;
}

// ---------- inloggning ----------
function valjPerson(info) {
  rot.innerHTML = `<div class="mitt"><h1>📚 Vem är du?</h1><div class="personer">${info.personer.map((p, i) =>
    `<button class="person" data-id="${esc(p.id)}"><span class="ava" style="background:${FARGER[i % FARGER.length]}">${esc(p.namn[0] || "?")}</span>${esc(p.namn)}</button>`).join("")}</div></div>`;
  rot.querySelectorAll("[data-id]").forEach((b) => b.addEventListener("click", () => pin(info, info.personer.find((p) => p.id === b.dataset.id))));
}

function pin(info, person) {
  let kod = "";
  rot.innerHTML = `<div class="mitt center"><h1>Hej ${esc(person.namn)}!</h1><p class="liten">Skriv din PIN-kod</p>
    <div class="pin" id="pin"></div><div class="fel" id="fel"></div>
    <div class="knappsats">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => `<button data-n="${n}">${n}</button>`).join("")}
      <button data-n="bak">⌫</button><button data-n="0">0</button><button data-n="ok" class="primar">OK</button></div>
    <button id="tillbaka">← Tillbaka</button></div>`;
  const visa = () => { $("#pin").textContent = "●".repeat(kod.length); };
  const skicka = async () => {
    try {
      const d = await api("/app/login", { id: person.id, pin: kod });
      sparaToken(d.token);
      location.reload();
    } catch (e) { kod = ""; visa(); $("#fel").textContent = e.message; }
  };
  rot.querySelectorAll("[data-n]").forEach((b) => b.addEventListener("click", () => {
    const n = b.dataset.n;
    if (n === "bak") kod = kod.slice(0, -1);
    else if (n === "ok") return skicka();
    else if (kod.length < 8) kod += n;
    visa();
  }));
  document.onkeydown = (e) => {
    if (/^\d$/.test(e.key) && kod.length < 8) { kod += e.key; visa(); }
    else if (e.key === "Backspace") { kod = kod.slice(0, -1); visa(); }
    else if (e.key === "Enter") skicka();
  };
  $("#tillbaka").addEventListener("click", () => { document.onkeydown = null; valjPerson(info); });
}

async function loggaUt() {
  try { await api("/app/logout", {}); } catch (e) { /* ok */ }
  sparaToken("");
  location.href = "/skolan";
}

// ---------- första start ----------
function forstaStart() {
  const personer = [];
  const rita = (fel = "") => {
    rot.innerHTML = `<div class="mitt"><h1>📚 Välkommen till Läxspelet!</h1>
      <div class="kort"><p>Lägg till familjen. Varje person får en egen PIN-kod (4–8 siffror) som används för att logga in.</p>
        <ul class="lista">${personer.map((p, i) => `<li>${p.roll === "foralder" ? "👩‍👧" : "🧒"} <b>${esc(p.namn)}</b> (${p.roll === "foralder" ? "förälder" : "barn"}) <button data-bort="${i}">✕</button></li>`).join("") || "<li class='liten'>Ingen än</li>"}</ul>
        <div class="rad"><input id="namn" placeholder="Namn" maxlength="30"><select id="roll"><option value="barn">Barn</option><option value="foralder">Förälder</option></select></div>
        <div class="rad"><input id="pin1" placeholder="PIN-kod" inputmode="numeric" maxlength="8"><button id="lagg">Lägg till</button></div>
      </div>
      <div class="kort"><h2 style="margin-top:0">🤖 AI-nyckel (rekommenderas)</h2>
        <p class="liten">Läxspelet använder Googles AI Gemini för att läsa glosor från foton, göra förhör och e-böcker. Nyckeln är gratis:
        gå till <b>aistudio.google.com/apikey</b>, logga in med ett Google-konto och tryck "Create API key". Du kan lägga in den senare också.</p>
        <input id="gemini" placeholder="Klistra in nyckeln (valfritt)"></div>
      <div class="fel">${esc(fel)}</div>
      <button class="primar" id="klar">Klart, starta Läxspelet</button></div>`;
    $("#lagg").addEventListener("click", () => {
      const namn = $("#namn").value.trim(), p = $("#pin1").value.trim();
      if (!namn) return rita("Skriv ett namn.");
      if (!/^\d{4,8}$/.test(p)) return rita("PIN-koden ska vara 4–8 siffror.");
      personer.push({ namn, roll: $("#roll").value, pin: p });
      rita();
    });
    rot.querySelectorAll("[data-bort]").forEach((b) => b.addEventListener("click", () => { personer.splice(+b.dataset.bort, 1); rita(); }));
    $("#klar").addEventListener("click", async () => {
      try {
        await api("/app/installera", { personer, gemini: $("#gemini").value.trim() });
        rot.innerHTML = `<div class="mitt"><h1>🎉 Klart!</h1><p>Läxspelet startar…</p></div>`;
        setTimeout(() => location.reload(), 2500);
      } catch (e) { rita(e.message); }
    });
  };
  rita();
}

// ---------- koppla mobilen ----------
function koppla(info) {
  const a = info.adresser || {};
  const qr = (u) => `<img class="qr" src="/app/qr.svg?text=${encodeURIComponent(u)}" alt="QR-kod">`;
  rot.innerHTML = `<div class="mitt"><h1>📱 Koppla en mobil</h1>
    <div class="kort"><h2 style="margin-top:0">🏠 Hemma (samma wifi)</h2>
      ${a.lokala?.length ? `${qr(a.lokala[0])}<p class="center"><code>${esc(a.lokala[0])}</code></p>` : "<p>Hittar ingen adress i nätverket.</p>"}
      <p class="liten">Skanna med mobilens kamera. Lägg sedan till Läxspelet på hemskärmen: iPhone: Dela → Lägg till på hemskärmen. Android: ⋮ → Installera app.</p></div>
    <div class="kort"><h2 style="margin-top:0">🌍 Överallt + notiser</h2>
      ${a.fjarr ? `${qr(a.fjarr)}<p class="center"><code>${esc(a.fjarr)}</code></p>
        <p class="liten">Den här adressen fungerar även utanför hemmet och behövs för notiser på iPhone. Den byts när datorn startas om, skanna då igen.</p>`
        : `<p class="liten">Fjärråtkomst är ${a.fjarr_status === "av" ? "avstängd" : esc(a.fjarr_status)}. En förälder kan slå på den under <a href="/app/installning">Inställningar</a>.</p>`}
    </div><a href="/skolan">← Till Läxspelet</a></div>`;
}

// ---------- inställningar (föräldrar) ----------
async function installning(info) {
  let s, up;
  const ladda = async (meddelande = "", fel = "") => {
    try { s = await api("/app/installningar"); up = await api("/app/uppdatering"); } catch (e) { return visaFel(e.message); }
    rot.innerHTML = `<div class="mitt"><h1>⚙️ Inställningar</h1>
      <div class="kort"><h2 style="margin-top:0">👨‍👩‍👧 Familjen</h2><ul class="lista">${s.personer.map((p) =>
        `<li>${p.roll === "foralder" ? "👩‍👧" : "🧒"} <b>${esc(p.namn)}</b> ${p.notiser ? "🔔" : ""}
          <button data-pin="${esc(p.id)}">Byt PIN</button> <button data-bort="${esc(p.id)}">Ta bort</button></li>`).join("")}</ul>
        <div class="rad"><input id="namn" placeholder="Namn" maxlength="30"><select id="roll"><option value="barn">Barn</option><option value="foralder">Förälder</option></select></div>
        <div class="rad"><input id="pin1" placeholder="PIN-kod" inputmode="numeric" maxlength="8"><button id="lagg">Lägg till</button></div>
        <p class="liten">Att lägga till eller ta bort någon startar om Läxspelet (några sekunder).</p></div>
      <div class="kort"><h2 style="margin-top:0">🤖 AI-nyckel</h2><p>${s.ai ? "✅ Inlagd" : "❌ Saknas: glosor från foton, förhör och e-böcker fungerar inte."}</p>
        <div class="rad"><input id="nyckel" placeholder="Ny Gemini-nyckel från aistudio.google.com/apikey"><button id="spara-ai">Spara</button></div></div>
      <div class="kort"><h2 style="margin-top:0">🌍 Fjärråtkomst</h2>
        <p class="liten">Gör Läxspelet nåbar utanför hemmet med en gratis, krypterad Cloudflare-tunnel. Behövs för notiser på iPhone och för vänner.</p>
        <p>Status: <b>${esc(s.fjarr_status)}</b>${s.fjarr_adress ? `<br><code>${esc(s.fjarr_adress)}</code>` : ""}</p>
        <button id="fjarr" class="${s.fjarr ? "" : "primar"}">${s.fjarr ? "Stäng av" : "Slå på"}</button></div>
      <div class="kort"><h2 style="margin-top:0">🆕 Uppdateringar</h2>
        <p>Du har version <b>${esc(up.version)}</b>. ${up.ny ? `<b>Version ${esc(up.senaste)} finns!</b>` : up.senaste ? "Det är den senaste ✅" : ""}</p>
        ${up.steg === "laddar" ? `<p>⏳ Laddar ner uppdateringen…</p>` : up.steg === "installerar" ? `<p>⏳ Installerar. Svara <b>Ja</b> om Windows frågar. Läxspelet startar om av sig själv.</p>` : ""}
        ${up.ny && !up.steg ? (up.kan_installera ? `<button id="upp-nu" class="primar">⬇️ Uppdatera nu</button> ` : "") + `<a href="${esc(up.sida)}" target="_blank" rel="noopener">Ladda ner från GitHub</a>` : ""}
        <div class="rad" style="margin-top:10px"><label><input type="radio" name="upp-lage" value="manuell" ${up.lage === "manuell" ? "checked" : ""}> <b>Manuell</b>: jag väljer själv när</label></div>
        <div class="rad"><label><input type="radio" name="upp-lage" value="automatisk" ${up.lage === "automatisk" ? "checked" : ""}> <b>Automatisk</b>: installera när ingen har använt Läxspelet på 15 minuter</label></div>
        <p class="liten">Appen kollar efter nya versioner var 6:e timme. Windows frågar alltid om lov på datorn innan en uppdatering installeras. Läxor och inställningar finns kvar.</p>
        <button id="upp-kolla">🔍 Sök efter uppdatering</button>${up.kollad ? ` <span class="liten">Senast kollat ${new Date(up.kollad * 1000).toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" })}</span>` : ""}
        ${up.fel ? `<p class="fel">${esc(up.fel)}</p>` : ""}</div>
      <div class="kort"><h2 style="margin-top:0">🔔 Notiser på den här enheten</h2><button id="notiser">Slå på notiser</button> <button id="testa">Skicka test</button></div>
      <div class="ok">${esc(meddelande)}</div><div class="fel">${esc(fel)}</div>
      <p><a href="/app/koppla">📱 Koppla en mobil</a> · <a href="/skolan">← Till Läxspelet</a></p></div>`;
    const andra = async (body, ok) => {
      try {
        const d = await api("/app/installningar", body);
        if (d.omstart) { rot.innerHTML = `<div class="mitt"><p>Startar om Läxspelet…</p></div>`; return setTimeout(() => location.reload(), 4000); }
        ladda(ok);
      } catch (e) { ladda("", e.message); }
    };
    $("#lagg").addEventListener("click", () => andra({ op: "lagg_till", namn: $("#namn").value, roll: $("#roll").value, pin: $("#pin1").value }, "Tillagd."));
    rot.querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", () => {
      const p = prompt("Ny PIN-kod (4–8 siffror):");
      if (p) andra({ op: "byt_pin", id: b.dataset.pin, pin: p }, "PIN-koden är bytt.");
    }));
    rot.querySelectorAll("[data-bort]").forEach((b) => b.addEventListener("click", () => {
      if (confirm("Ta bort personen? Barnets läxor sparas på datorn men syns inte längre.")) andra({ op: "ta_bort", id: b.dataset.bort });
    }));
    $("#spara-ai").addEventListener("click", () => andra({ op: "ai", nyckel: $("#nyckel").value }, "AI-nyckeln fungerar! ✅"));
    $("#fjarr").addEventListener("click", () => andra({ op: "fjarr", pa: !s.fjarr }, s.fjarr ? "Avstängd." : "Startar… det tar en halv minut. Ladda om sidan sedan."));
    const upp = async (body, ok) => {
      try { await api("/app/uppdatering", body); ladda(ok); } catch (e) { ladda("", e.message); }
    };
    $("#upp-kolla").addEventListener("click", () => upp({ op: "kolla" }, "Klart."));
    $("#upp-nu")?.addEventListener("click", () => {
      if (confirm(`Uppdatera till version ${up.senaste}? Läxspelet stängs en kort stund. Svara Ja om Windows frågar.`)) {
        upp({ op: "installera" }, "Uppdateringen har startat.");
        setTimeout(() => ladda(), 3000);
      }
    });
    rot.querySelectorAll("input[name=upp-lage]").forEach((r) => r.addEventListener("change", () =>
      upp({ op: "lage", lage: r.value }, r.value === "automatisk" ? "Automatiska uppdateringar är på." : "Du uppdaterar själv.")));
    $("#notiser").addEventListener("click", async () => { try { await slaPaNotiser(); ladda("Notiser påslagna! 🔔"); } catch (e) { ladda("", e.message); } });
    $("#testa").addEventListener("click", async () => { try { await api("/app/push/test", {}); ladda("Testnotis skickad."); } catch (e) { ladda("", e.message); } });
  };
  ladda();
}

// ---------- notiser ----------
const b64 = (s) => { const p = "=".repeat((4 - (s.length % 4)) % 4); const r = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(r, (c) => c.charCodeAt(0)); };

async function slaPaNotiser() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error(/iPhone|iPad/.test(navigator.userAgent)
      ? "På iPhone: lägg först till Läxspelet på hemskärmen (via fjärradressen med https) och öppna den därifrån."
      : "Den här webbläsaren kan inte ta emot notiser.");
  }
  if (location.protocol !== "https:" && location.hostname !== "localhost") throw new Error("Notiser kräver fjärradressen (https). Slå på fjärråtkomst och öppna Läxspelet via den.");
  if ((await Notification.requestPermission()) !== "granted") throw new Error("Notiser är inte tillåtna.");
  const reg = await navigator.serviceWorker.ready;
  const { nyckel } = await api("/app/push/nyckel");
  const sub = (await reg.pushManager.getSubscription()) || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(nyckel) }));
  await api("/app/push/prenumerera", sub.toJSON());
}

// ---------- Skolans panel ----------
async function visaSkolan(info) {
  if (!info.panel) return visaFel("Läxspelet startar fortfarande. Försök igen om en stund.");
  await import(info.panel.modul);
  const el = document.createElement(info.panel.komponent);
  const u = info.anvandare;
  el.hass = {
    user: { id: u.id, name: u.name, is_admin: u.is_admin },
    language: "sv",
    fetchWithAuth: (url, opt = {}) => fetch(url, { ...opt, credentials: "same-origin", headers: { ...(opt.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) } }),
    callWS: async (m) => {
      if (m.type === "auth/sign_path") return api("/app/signera", { path: m.path });
      throw new Error("Stöds inte i fristående läge");
    },
    themes: { darkMode: matchMedia("(prefers-color-scheme: dark)").matches },
  };
  el.narrow = false;
  rot.innerHTML = "";
  rot.appendChild(el);
  const v = document.createElement("div");
  v.className = "verktyg";
  const nyVer = u.is_admin && info.uppdatering?.ny && info.uppdatering.lage === "manuell";
  v.innerHTML = `${nyVer ? `<button title="Ny version" onclick="location.href='/app/installning'">🆕 ${esc(info.uppdatering.senaste)}</button>` : ""}
    ${u.is_admin ? `<button title="Inställningar" onclick="location.href='/app/installning'">⚙️</button>` : ""}
    ${"PushManager" in window && Notification.permission !== "granted" ? `<button id="v-notis" title="Slå på notiser">🔔</button>` : ""}
    <button id="v-ut" title="Byt person">👤 ${esc(u.name)}</button>`;
  document.body.appendChild(v);
  v.querySelector("#v-ut").addEventListener("click", () => { if (confirm(`Logga ut ${u.name}?`)) loggaUt(); });
  v.querySelector("#v-notis")?.addEventListener("click", async (e) => {
    try { await slaPaNotiser(); e.target.remove(); alert("Notiser påslagna! 🔔"); } catch (err) { alert(err.message); }
  });
}

start();
