"""Skolan: lärarnas appar i ett gemensamt "kluster" på skolans nätverk. Ingen server och inget moln.

- En lärare skapar skolan och får en kod (giltig 7 dagar). Kollegor skriver koden i sin app.
- Apparna hittar varandra på nätverket (UDP-sändning på samma port som appen). Fungerar inte det
  (vissa skolnät stoppar sändningar) skriver läraren in en kollegas adress, t.ex. 10.0.4.17:8770.
- Medlemmarna synkar var 10:e minut, signerat med skolans hemliga nyckel (HMAC-SHA256).
- Det som delas: vem som är med (namn, ämne, roll, klass) och provkalendern (titel, ämne, datum, klass).
- Elevdata delas bara med elevens mentor: ämneslärarens provresultat för just den eleven, så att mentorn
  får hela bilden. Eleven känns igen på elev_id (samma för alla lärare, från familjens Läxspelet).
- Meddelanden mellan lärarna (till alla eller till en kollega).
- Anteckningar om en elev, skrivna av läraren själv: mentorn får alla, en ämneslärare bara de som gäller sitt
  ämne. De går bara till elevens egna lärare, aldrig till familjen. Det familjen har delat med en lärare
  (lappar, studieteknik, samtalsunderlag) skickas aldrig vidare till kollegor.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import socket
import time

from aiohttp import ClientSession, ClientTimeout

from . import behorighet as beh

_LOGGER = logging.getLogger(__name__)

SYNK_VAR = 600  # sekunder mellan synkarna med kollegorna
FYR_VAR = 60  # sekunder mellan "här är jag"-sändningarna på nätverket
KOD_GILTIG = 7 * 24 * 3600
MAX_SKEV = 900  # godta signerade meddelanden högst 15 minuter gamla
PROTO = b"LXS1"


def _t(x, n: int) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def amne_lika(a: str, b: str) -> bool:
    """Samma ämne? (Matte/Matematik, Spanska/Moderna språk …) Samma regler som i familjens Läxspelet."""
    syn = {"matematik": "matte", "ma": "matte", "sv": "svenska", "en": "engelska", "samhällskunskap": "so", "historia": "so",
           "geografi": "so", "religion": "so", "biologi": "no", "fysik": "no", "kemi": "no"}
    n = lambda x: syn.get(re.sub(r"[^a-zåäö ]", "", (x or "").lower()).strip(), re.sub(r"[^a-zåäö ]", "", (x or "").lower()).strip())  # noqa: E731
    a, b = n(a), n(b)
    sprak = {"spanska", "tyska", "franska", "italienska", "kinesiska", "arabiska", "ryska", "japanska"}
    if {a, b} & {"moderna språk", "språkval"} and ({a, b} & sprak):
        return True
    return bool(a and b) and (a == b or a in b or b in a)


def ny_kod() -> str:
    alfabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    k = "".join(secrets.choice(alfabet) for _ in range(8))
    return f"{k[:4]}-{k[4:]}"


def _kodnyckel(kod: str) -> str:
    return hashlib.sha256(("kod:" + re.sub(r"[^A-Z0-9]", "", kod.upper())).encode()).hexdigest()[:16]


def signera(hemlighet: str, kropp: bytes) -> str:
    return hmac.new(hemlighet.encode(), kropp, hashlib.sha256).hexdigest()


class Skola:
    def __init__(self, klass) -> None:
        self.k = klass  # Klass (server.py): d, spara(), logga(), port
        self.d.setdefault("skola", None)
        self._fel_forsok: dict[str, list[float]] = {}
        self._uppgift: asyncio.Task | None = None
        self._udp = None

    @property
    def d(self) -> dict:
        return self.k.d

    @property
    def s(self) -> dict | None:
        return self.d.get("skola")

    @property
    def lid(self) -> str:
        return self.d["larar_id"]

    def min_info(self) -> dict:
        from .server import lan_ip
        return {"namn": self.d.get("larare") or "Läraren", "amne": self.d.get("amne", ""), "roll": "mentor" if self.mentor_for() else "amne",
                "klass": self.d.get("klass", ""), "adress": f"{lan_ip()}:{self.k.port}", "pub": beh.publik_nyckel(self.d["nyckel"])}

    # ---------- skapa, gå med, lämna ----------
    def skapa(self, namn: str) -> dict:
        if self.s:
            raise ValueError("Du är redan med i en skola.")
        namn = _t(namn, 60)
        if not namn:
            raise ValueError("Skriv skolans namn.")
        self.d["skola"] = {"id": secrets.token_urlsafe(9), "namn": namn, "hemlighet": secrets.token_urlsafe(32),
                           "kod": ny_kod(), "kod_tid": time.time(), "medlemmar": {}, "prov": {}, "resultat": {}, "meddelanden": [], "anteckningar_in": {}}
        self.s["policy"] = beh.ny_policy(self.s["id"], self.lid, self.d.get("larare") or "Rektorn", beh.publik_nyckel(self.d["nyckel"]), self.d["nyckel"])
        self.k.logga("skola", f"Skolan {namn} skapades. Du är skolans rektor i appen och bestämmer lärarnas behörigheter.")
        self.k.rensa_otillatet()
        self.utfarda()
        self.k.spara()
        return self.s

    def ny_kod(self) -> str:
        if not self.s:
            raise ValueError("Du är inte med i någon skola.")
        self.s["kod"], self.s["kod_tid"] = ny_kod(), time.time()
        self.k.spara()
        return self.s["kod"]

    def lamna(self) -> None:
        if self.s:
            self.k.logga("skola", f"Lämnade skolan {self.s['namn']}.")
        self.d["skola"] = None
        self.k.rensa_otillatet()
        self.k.spara()

    def kod_ok(self, kod: str) -> bool:
        s = self.s
        return bool(s and s.get("kod") and time.time() - s.get("kod_tid", 0) < KOD_GILTIG
                    and hmac.compare_digest(_kodnyckel(s["kod"]), _kodnyckel(kod)))

    def ta_emot_medlem(self, ip: str, body: dict) -> dict:
        """En kollega vill gå med (POST /api/skola/ga_med). Kräver rätt kod. Max 10 fel per timme och adress."""
        f = [t for t in self._fel_forsok.get(ip, []) if time.time() - t < 3600]
        if len(f) >= 10:
            raise PermissionError("För många fel försök. Vänta en stund.")
        if not self.kod_ok(str(body.get("kod") or "")):
            self._fel_forsok[ip] = f + [time.time()]
            raise PermissionError("Fel kod, eller så har koden gått ut. Be kollegan om en ny.")
        lid = _t(body.get("larar_id"), 40)
        if not lid:
            raise ValueError("Saknar lärare.")
        self._spara_medlem(lid, body.get("info") or {}, ip)
        self.k.logga("skola", f"{_t((body.get('info') or {}).get('namn'), 60)} gick med i skolan.")
        self.utfarda()
        self.k.spara()
        svar = {"id": self.s["id"], "namn": self.s["namn"], "hemlighet": self.s["hemlighet"], "policy": self.s.get("policy"),
                "medlemmar": {**self.s["medlemmar"], self.lid: {**self.min_info(), "sedd": time.strftime("%Y-%m-%d %H:%M")}}}
        # skolans hemlighet skickas krypterad med koden kollegan skrev in, aldrig i klartext på nätverket
        return {"krypt": beh._b64(beh.krypt(beh.kodnyckel(str(body.get("kod") or "")), json.dumps(svar, ensure_ascii=False).encode()))}

    async def ga_med(self, session: ClientSession, kod: str, adress: str | None = None) -> None:
        """Gå med i en kollegas skola: hitta kollegan på nätverket (eller via adress) och skicka koden."""
        if self.s:
            raise ValueError("Du är redan med i en skola. Lämna den först.")
        kod = _t(kod, 20).upper()
        if not re.fullmatch(r"[A-Z0-9]{4}-?[A-Z0-9]{4}", kod):
            raise ValueError("Koden ser ut så här: ABCD-EF23.")
        adresser = [adress] if adress else await self._sok_kod(kod)
        if not adresser:
            raise ValueError("Hittade ingen kollega med den koden på nätverket. Skriv in kollegans adress (den står på kollegans Översikt).")
        senaste_fel = ""
        for a in adresser:
            if not re.fullmatch(r"[\w.\-]+:\d{2,5}", a or ""):
                continue
            try:
                async with session.post(f"http://{a}/api/skola/ga_med", json={"kod": kod, "larar_id": self.lid, "info": self.min_info()},
                                        timeout=ClientTimeout(total=15)) as r:
                    j = await r.json()
                    if r.status != 200:
                        senaste_fel = j.get("fel") or f"Kollegans app svarade {r.status}."
                        continue
                    if "krypt" not in j:
                        senaste_fel = "Kollegans app är för gammal. Be kollegan uppdatera lärarappen."
                        continue
                    j = json.loads(beh.dekrypt(beh.kodnyckel(kod), beh._ub64(j["krypt"])))
            except Exception as err:  # noqa: BLE001
                senaste_fel = f"Kunde inte nå {a}: {err}"
                continue
            self.d["skola"] = {"id": _t(j["id"], 40), "namn": _t(j["namn"], 60), "hemlighet": str(j["hemlighet"])[:100], "kod": "", "kod_tid": 0,
                               "medlemmar": {}, "prov": {}, "resultat": {}, "meddelanden": [], "anteckningar_in": {}}
            if isinstance(j.get("policy"), dict) and beh.godta_policy(None, j["policy"], self.s["id"]):
                self.s["policy"] = j["policy"]
            self.k.rensa_otillatet()
            for mlid, info in (j.get("medlemmar") or {}).items():
                if mlid != self.lid:
                    self._spara_medlem(_t(mlid, 40), info, None)
            self.k.logga("skola", f"Gick med i skolan {self.s['namn']}.")
            self.k.spara()
            asyncio.get_running_loop().create_task(self.synka_alla(session))
            return
        raise ValueError(senaste_fel or "Kunde inte gå med.")

    def _spara_medlem(self, lid: str, info: dict, ip: str | None) -> None:
        if lid == self.lid:
            return
        m = self.s["medlemmar"].setdefault(lid, {})
        adress = _t(info.get("adress"), 60)
        if ip and adress:  # lita på avsändarens ip, porten från meddelandet
            adress = f"{ip}:{adress.rsplit(':', 1)[-1]}"
        m.update({"namn": _t(info.get("namn"), 60) or m.get("namn") or "?", "amne": _t(info.get("amne"), 60), "roll": info.get("roll") if info.get("roll") in ("mentor", "amne") else "",
                  "klass": _t(info.get("klass"), 40), "sedd": time.strftime("%Y-%m-%d %H:%M")})
        if re.fullmatch(r"[\w.\-]+:\d{2,5}", adress or ""):
            m["adress"] = adress
        if re.fullmatch(r"[A-Za-z0-9_\-]{40,50}", str(info.get("pub") or "")):
            m["pub"] = info["pub"]

    # ---------- det som delas ----------
    def mina_prov(self) -> list[dict]:
        return [{"id": m["id"], "titel": _t(m.get("titel"), 80), "amne": _t(m.get("amne"), 40), "datum": _t(m.get("datum"), 10), "klass": self.d.get("klass", "")}
                for m in self.d.get("material", []) if m.get("typ") == "prov" and m.get("datum")][-60:]

    def till_mentor(self, mentor_lid: str) -> dict:
        """Mina provresultat för de elever där mentor_lid är mentor (bara dem)."""
        ut: dict[str, list] = {}
        if not (self.k.har("mentor") and self.k.har("prov")):
            return ut
        for e in self.d.get("elever", []):
            if not e.get("elev_id") or not any(x.get("id") == mentor_lid and x.get("roll") == "mentor" for x in e.get("lararna") or []):
                continue
            rader = []
            for m in self.d.get("material", []):
                r = (m.get("resultat") or {}).get(e["id"]) if m.get("typ") == "prov" else None
                if r:
                    rader.append({"titel": _t(m.get("titel"), 80), "amne": _t(m.get("amne"), 40), "datum": _t(m.get("datum"), 10), "max": m.get("max"),
                                  **{k: r[k] for k in ("poang", "betyg", "kommentar") if k in r}, "larare": self.d.get("larare") or ""})
            if rader:
                ut[e["elev_id"]] = rader[-30:]
        return ut

    # ---------- meddelanden och anteckningar ----------
    def skriv_meddelande(self, text: str, till: str | None) -> None:
        if not self.s:
            raise ValueError("Du är inte med i någon skola.")
        if not self.k.har("meddelanden"):
            raise ValueError("Rektorn har inte gett dig behörighet att skicka meddelanden.")
        text = str(text or "").strip()[:1000]
        if not text:
            raise ValueError("Skriv ett meddelande.")
        if till and till not in self.s["medlemmar"]:
            raise ValueError("Den kollegan finns inte i skolan.")
        self.s.setdefault("meddelanden", []).append({"id": secrets.token_urlsafe(8), "fran": self.lid, "namn": self.d.get("larare") or "Läraren",
                                                     "till": till or None, "text": text, "tid": time.strftime("%Y-%m-%d %H:%M"), "last": True})
        self.s["meddelanden"] = self.s["meddelanden"][-300:]
        self.k.spara()

    def last_meddelanden(self) -> None:
        for m in (self.s or {}).get("meddelanden", []):
            m["last"] = True
        self.k.spara()

    def skriv_anteckning(self, elev: dict, amne: str, text: str) -> None:
        """En anteckning om en elev: mentorn får den, och ämnesläraren i ämnet (om ämnet är satt)."""
        if not self.k.har("anteckningar"):
            raise ValueError("Rektorn har inte gett dig behörighet att skriva anteckningar om elever.")
        text = str(text or "").strip()[:1000]
        if not text:
            raise ValueError("Skriv en anteckning.")
        self.d.setdefault("anteckningar", []).append({"id": secrets.token_urlsafe(8), "elev": elev["id"], "elev_id": elev.get("elev_id") or "",
                                                       "elev_namn": elev.get("namn") or "", "amne": _t(amne, 40), "text": text,
                                                       "larare": self.d.get("larare") or "Läraren", "tid": time.strftime("%Y-%m-%d %H:%M")})
        self.d["anteckningar"] = self.d["anteckningar"][-1000:]
        self.k.spara()

    def _roll_hos_elev(self, e: dict, lid: str) -> tuple[str | None, str]:
        """Vilken roll har kollegan lid hos eleven e (enligt familjens lista)? (roll, ämne)"""
        x = next((y for y in e.get("lararna") or [] if y.get("id") == lid), None)
        if not x:
            return None, ""
        amne = x.get("amne") or (self.s["medlemmar"].get(lid) or {}).get("amne") or ""
        return x.get("roll") or None, amne

    def _anteckningar_till(self, lid: str) -> list[dict]:
        """Mina anteckningar som kollegan lid ska få: mentorn allt om sina elever, ämnesläraren sitt ämne."""
        ut = []
        if not (self.k.har("mentor") and self.k.har("anteckningar")):
            return ut
        elever = {e["id"]: e for e in self.d.get("elever", [])}
        for a in self.d.get("anteckningar", [])[-300:]:
            e = elever.get(a["elev"])
            if not e or not e.get("elev_id"):
                continue
            roll, amne = self._roll_hos_elev(e, lid)
            if roll == "mentor" or (roll == "amne" and a.get("amne") and any(amne_lika(a["amne"], x) for x in re.split(r"[,/]", amne))):
                ut.append({k: a[k] for k in ("id", "elev_id", "elev_namn", "amne", "text", "larare", "tid")})
        return ut

    def _paket(self, till: str | None) -> dict:
        mina = [m for m in self.s.get("meddelanden", []) if m.get("fran") == self.lid and (not m.get("till") or m.get("till") == till)][-100:]
        return {"v": 1, "skola": self.s["id"], "fran": self.lid, "tid": time.time(), "info": self.min_info(), "prov": self.mina_prov(),
                "medlemmar": {k: {x: v.get(x) for x in ("namn", "amne", "roll", "klass", "adress")} for k, v in self.s["medlemmar"].items()},
                "till_mentor": self.till_mentor(till) if till else {},
                "meddelanden": [{k: m[k] for k in ("id", "namn", "till", "text", "tid")} for m in mina],
                "anteckningar": self._anteckningar_till(till) if till else [], "policy": self.s.get("policy"),
                "intyg": list(self.s.get("intyg", {}).values()), "godk": list(self.s.get("godk", {}).values())}

    def _ta_emot_paket(self, p: dict, ip: str | None) -> None:
        lid = _t(p.get("fran"), 40)
        if not lid or lid == self.lid:
            return
        self._spara_medlem(lid, p.get("info") or {}, ip)
        ny = p.get("policy")
        if isinstance(ny, dict) and beh.godta_policy(self.s.get("policy"), ny, self.s["id"]):
            self.s["policy"] = ny
            self.k.logga("behorighet", f"Nytt beslut från rektorn ({ny.get('rektor_namn')}): {(ny.get('beslut') or [{}])[-1].get('text', '')}"[:500])
            self.k.rensa_otillatet()
        self.s["prov"][lid] = [{k: _t(x.get(k), 80) for k in ("id", "titel", "amne", "datum", "klass")} for x in (p.get("prov") or [])[:60] if isinstance(x, dict)]
        tm = (p.get("till_mentor") or {}) if self.k.har("mentor") else {}
        self.s["resultat"][lid] = {_t(eid, 30): [{k: (x.get(k) if k in ("poang", "max") and isinstance(x.get(k), (int, float)) else _t(x.get(k), 200))
                                                  for k in ("titel", "amne", "datum", "max", "poang", "betyg", "kommentar", "larare") if k in x}
                                                 for x in rader[:30] if isinstance(x, dict)]
                                   for eid, rader in list(tm.items())[:200] if isinstance(rader, list)}
        kanda = {m["id"] for m in self.s.setdefault("meddelanden", [])}
        for m in (p.get("meddelanden") or [])[:100]:
            if isinstance(m, dict) and _t(m.get("id"), 20) and m["id"] not in kanda and (not m.get("till") or m.get("till") == self.lid):
                self.s["meddelanden"].append({"id": _t(m["id"], 20), "fran": lid, "namn": _t(m.get("namn"), 60), "till": m.get("till") or None,
                                              "text": _t(m.get("text"), 1000), "tid": _t(m.get("tid"), 16), "last": False})
        self.s["meddelanden"] = sorted(self.s["meddelanden"], key=lambda m: m.get("tid", ""))[-300:]
        self.s.setdefault("anteckningar_in", {})[lid] = [] if not self.k.har("mentor") else [{k: _t(a.get(k), 1000 if k == "text" else 60) for k in ("id", "elev_id", "elev_namn", "amne", "text", "larare", "tid")}
                                                         for a in (p.get("anteckningar") or [])[:300] if isinstance(a, dict)]
        for mlid, info in (p.get("medlemmar") or {}).items():  # så hittar alla varandra
            if mlid not in self.s["medlemmar"] and mlid != self.lid and isinstance(info, dict):
                self._spara_medlem(_t(mlid, 40), info, None)
        self.ta_emot_intyg(p.get("intyg"), p.get("godk"))

    def _las(self, kropp: bytes) -> bytes:
        try:
            return beh.dekrypt(beh.skolnyckel(self.s["hemlighet"]), kropp)
        except Exception as err:  # noqa: BLE001
            raise PermissionError("Kunde inte läsa (kollegans app kanske är för gammal).") from err

    def _skriv(self, p: dict) -> bytes:
        return beh.krypt(beh.skolnyckel(self.s["hemlighet"]), json.dumps(p, ensure_ascii=False).encode())

    def verifiera(self, kropp: bytes, signatur: str) -> dict:
        """Signaturen gäller det krypterade innehållet. Allt mellan kollegor är krypterat med skolans nyckel."""
        if not self.s:
            raise PermissionError("Inte med i någon skola.")
        if not hmac.compare_digest(signera(self.s["hemlighet"], kropp), signatur or ""):
            raise PermissionError("Fel signatur.")
        p = json.loads(self._las(kropp))
        if p.get("skola") != self.s["id"] or abs(time.time() - float(p.get("tid") or 0)) > MAX_SKEV:
            raise PermissionError("Fel skola eller för gammalt.")
        return p

    def ta_emot_synk(self, kropp: bytes, signatur: str, ip: str) -> tuple[bytes, str]:
        """En kollega synkar med oss (POST /api/skola/synk). Svarar med vårt paket, signerat."""
        p = self.verifiera(kropp, signatur)
        self._ta_emot_paket(p, ip)
        self.k.spara()
        svar = self._skriv(self._paket(_t(p.get("fran"), 40)))
        return svar, signera(self.s["hemlighet"], svar)

    async def synka_alla(self, session: ClientSession) -> None:
        if not self.s:
            return
        self.utfarda()
        for lid, m in list(self.s["medlemmar"].items()):
            if not m.get("adress"):
                continue
            kropp = self._skriv(self._paket(lid))
            try:
                async with session.post(f"http://{m['adress']}/api/skola/synk", data=kropp, timeout=ClientTimeout(total=15),
                                        headers={"Content-Type": "application/octet-stream", "X-Laxspelet-Signatur": signera(self.s["hemlighet"], kropp)}) as r:
                    if r.status != 200:
                        m["fel"] = f"svarade {r.status}"
                        continue
                    svar = await r.read()
                    p = self.verifiera(svar, r.headers.get("X-Laxspelet-Signatur", ""))
                    self._ta_emot_paket(p, None)
                    m["fel"] = ""
            except Exception as err:  # noqa: BLE001
                m["fel"] = "nås inte just nu"
                _LOGGER.info("Skolan: kunde inte synka med %s: %s", m.get("namn"), err)
        self.k.spara()

    # ---------- rektorn ----------
    @property
    def policy(self) -> dict | None:
        return (self.s or {}).get("policy")

    def ar_rektor(self) -> bool:
        p = self.policy
        return bool(p and p.get("rektor") == self.lid and p.get("rektor_pub") == beh.publik_nyckel(self.d["nyckel"]))

    def _namn(self, lid: str) -> str:
        return self.d.get("larare") or "Du" if lid == self.lid else (self.s["medlemmar"].get(lid) or {}).get("namn") or "?"

    def bli_rektor(self) -> None:
        """Skolan har ingen rektor i appen än (skapad med en äldre version): den första som tar rollen blir rektor."""
        if not self.s:
            raise ValueError("Du är inte med i någon skola.")
        if self.policy:
            raise ValueError(f"Skolan har redan en rektor: {self.policy.get('rektor_namn')}.")
        self.s["policy"] = beh.ny_policy(self.s["id"], self.lid, self.d.get("larare") or "Rektorn", beh.publik_nyckel(self.d["nyckel"]), self.d["nyckel"])
        self.k.logga("behorighet", "Du blev skolans rektor i appen.")
        self.k.rensa_otillatet()
        self.utfarda()

    def _nytt_beslut(self, andra, text: str) -> None:
        if not self.ar_rektor():
            raise PermissionError("Bara skolans rektor kan ändra behörigheter.")
        p = json.loads(json.dumps(self.policy))
        andra(p)
        p["ver"] += 1
        p["tid"] = time.time()
        p.setdefault("beslut", []).append({"tid": time.strftime("%Y-%m-%d %H:%M"), "av": self.d.get("larare") or "Rektorn", "text": text[:600]})
        p["beslut"] = p["beslut"][-500:]
        self.s["policy"] = beh.signera_policy(p, self.d["nyckel"])
        self.k.logga("behorighet", text)
        self.k.rensa_otillatet()
        self.utfarda()

    def satt_ratt(self, vem: str, ratt: list, motivering: str) -> None:
        """vem = en lärares id, eller "standard" (alla lärare utan eget beslut)."""
        ratt = beh.rensa_ratt(ratt)
        motivering = _t(motivering, 300)
        if vem != "standard" and vem != self.lid and vem not in self.s["medlemmar"]:
            raise ValueError("Läraren finns inte i skolan.")
        if beh.niva_for(ratt) >= 1 and not motivering:
            raise ValueError("Skriv vad beslutet bygger på, t.ex. dataskyddsombudets bedömning eller ett diarienummer.")
        namn = "Alla lärare (standard)" if vem == "standard" else self._namn(vem)
        lista = ", ".join(beh.RATTIGHETER[k][1] for k in ratt) or "inget"
        text = f"{namn}: nivå {beh.niva_for(ratt)} ({lista})." + (f" Grund: {motivering}" if motivering else "")

        def andra(p):
            if vem == "standard":
                p["standard"] = ratt
            else:
                p.setdefault("larare", {})[vem] = ratt
        self._nytt_beslut(andra, text)

    def aterstall(self, vem: str, motivering: str) -> None:
        """Ta bort lärarens egna beslut, så att standarden gäller."""
        if vem not in (self.policy or {}).get("larare", {}):
            return
        self._nytt_beslut(lambda p: p["larare"].pop(vem, None), f"{self._namn(vem)}: följer standarden igen." + (f" Grund: {_t(motivering, 300)}" if motivering else ""))

    def overlat(self, vem: str) -> None:
        """Lämna över rektorsrollen till en kollega (signeras av nuvarande rektor)."""
        m = self.s["medlemmar"].get(vem)
        if not m or not m.get("pub"):
            raise ValueError("Kollegan måste ha synkat med en ny version av lärarappen först.")

        def andra(p):
            # den gamla rektorn signerar överlämningen, så att familjerna kan följa den (föräldern godkänner den nya rektorn)
            p["kedja"] = (p.get("kedja") or [])[-19:] + [beh.kedjelank(self.s["id"], p["rektor_pub"], m["pub"], m.get("namn") or "?", self.d["nyckel"])]
            p.update({"rektor": vem, "rektor_namn": m.get("namn") or "?", "rektor_pub": m["pub"]})
        self._nytt_beslut(andra, f"{self.d.get('larare') or 'Rektorn'} lämnade över rektorsrollen till {m.get('namn')}.")

    def satt_mentor(self, vem: str, klasser: str, motivering: str) -> None:
        """Rektorn bestämmer vem som är mentor för vilka klasser. Bara mentorn kan godkänna ämneslärare för klassen."""
        if vem != self.lid and vem not in self.s["medlemmar"]:
            raise ValueError("Läraren finns inte i skolan.")
        lista = sorted({_t(k, 20).upper() for k in re.split(r"[,;/]", klasser or "") if _t(k, 20)})[:10]
        text = f"{self._namn(vem)}: " + (f"mentor för {', '.join(lista)}." if lista else "inte mentor för någon klass.") + (f" Grund: {_t(motivering, 300)}" if motivering else "")

        def andra(p):
            mentorer = p.setdefault("mentorer", {})
            if lista:
                mentorer[vem] = lista
            else:
                mentorer.pop(vem, None)
        self._nytt_beslut(andra, text)

    def mentor_for(self, lid: str | None = None) -> list[str]:
        return list(((self.policy or {}).get("mentorer") or {}).get(lid or self.lid) or [])

    # ---------- intyg och godkännanden (till familjerna) ----------
    def utfarda(self) -> None:
        """Rektorns app: håll intygen aktuella för alla lärare (nya lärare, nya beslut, snart utgångna)."""
        if not self.s or not self.ar_rektor():
            return
        p = self.policy
        intyg = self.s.setdefault("intyg", {})
        lararna = {self.lid: (self.d.get("larare") or "Rektorn", beh.publik_nyckel(self.d["nyckel"]))}
        lararna.update({k: (m.get("namn") or "?", m["pub"]) for k, m in self.s["medlemmar"].items() if m.get("pub")})
        for lid, (namn, pub) in lararna.items():
            ny = beh.intyg(p, self.s["namn"], lid, namn, pub, self.d["nyckel"])
            gammal = intyg.get(lid)
            if (not gammal or time.time() - gammal.get("tid", 0) > beh.FORNYA
                    or any(gammal.get(k) != ny[k] for k in ("skola_namn", "rektor_namn", "rektor_pub", "namn", "pub", "ratt", "mentor"))):
                intyg[lid] = ny
        for lid in [k for k in intyg if k not in lararna]:
            intyg.pop(lid)
        self.godkann_alla()

    def godkann(self, lid: str, klass: str, amnen: str, elever: list | None) -> None:
        """Mentorn godkänner (eller tar bort, amnen tomt) en ämneslärare för sin klass."""
        klass = _t(klass, 20).upper()
        if klass not in self.mentor_for():
            raise PermissionError("Bara klassens mentor (utsedd av rektorn) kan godkänna ämneslärare.")
        if lid not in self.s["medlemmar"] or not self.s["medlemmar"][lid].get("pub"):
            raise ValueError("Kollegan måste ha synkat med en ny version av lärarappen först.")
        lista = [x for x in dict.fromkeys(_t(a, 40) for a in re.split(r"[,/]", amnen or "")) if x][:8]
        el = None if elever is None else [_t(x, 30) for x in elever if re.fullmatch(r"[0-9a-f]{20}", str(x))][:200]
        g = self.d.setdefault("godkanda", {})
        namn = self._namn(lid)
        if lista:
            g[f"{lid}|{klass}"] = {"lid": lid, "klass": klass, "amnen": lista, "elever": el}
            text = f"Godkände {namn} som ämneslärare i {', '.join(lista)} för {klass}" + (" (hela klassen)." if el is None else f" ({len(el)} elever).")
        else:
            g[f"{lid}|{klass}"] = {"lid": lid, "klass": klass, "amnen": [], "elever": None, "bort": True}
            text = f"Tog bort {namn} som ämneslärare för {klass}."
        self.k.logga("behorighet", text)
        self.godkann_alla(tvinga=f"{lid}|{klass}")

    def godkann_alla(self, tvinga: str | None = None) -> None:
        """Signera mina godkännanden (som mentor) och förnya dem i tid. Borttagna skickas som tomma, så att de gamla slutar gälla."""
        if not self.s:
            return
        godk = self.s.setdefault("godk", {})
        for nyckel, x in (self.d.get("godkanda") or {}).items():
            m = self.s["medlemmar"].get(x["lid"]) or {}
            if x["klass"] not in self.mentor_for() or not m.get("pub"):
                continue
            k = f"{self.lid}:{nyckel}"
            gammal = godk.get(k)
            if nyckel == tvinga or not gammal or time.time() - gammal.get("tid", 0) > beh.FORNYA or gammal.get("pub") != m["pub"] or gammal.get("namn") != m.get("namn"):
                godk[k] = beh.godkannande(self.s["id"], x["klass"], self.lid, x["lid"], m["pub"], m.get("namn") or "?", x["amnen"], x["elever"], self.d["nyckel"])
        for k in [k for k, g in godk.items() if time.time() - g.get("tid", 0) > beh.GILTIG]:
            godk.pop(k)

    def ta_emot_intyg(self, intyg, godk) -> None:
        """Intyg och godkännanden från kollegorna. Bara det som är signerat av rektorn (intyg) eller av en mentor
        som rektorn har utsett för klassen (godkännanden) sparas, och bara nyare än det vi har."""
        p = self.policy
        if not self.s or not p:
            return
        mina = self.s.setdefault("intyg", {})
        for lid in [k for k, c in mina.items() if c.get("rektor_pub") != p["rektor_pub"]]:
            mina.pop(lid)  # ny rektor: de gamla intygen gäller inte längre här
        for c in (intyg or [])[:200]:
            if (isinstance(c, dict) and c.get("typ") == "intyg" and c.get("skola") == self.s["id"] and c.get("rektor_pub") == p["rektor_pub"]
                    and beh.sig_ok(c, p["rektor_pub"]) and c.get("tid", 0) > (mina.get(c.get("lid")) or {}).get("tid", 0)):
                mina[c["lid"]] = c
        alla = self.s.setdefault("godk", {})
        for g in (godk or [])[:400]:
            if not isinstance(g, dict) or g.get("typ") != "amneslarare" or g.get("skola") != self.s["id"]:
                continue
            mi = mina.get(g.get("mentor")) or {}
            k = f"{g.get('mentor')}:{g.get('lid')}|{g.get('klass')}"
            if (g.get("klass") in (mi.get("mentor") or []) and beh.sig_ok(g, mi.get("pub") or "")
                    and g.get("tid", 0) > (alla.get(k) or {}).get("tid", 0) and time.time() - g.get("tid", 0) < beh.GILTIG):
                alla[k] = g

    def min_roll(self) -> dict:
        """Min roll enligt rektorns intyg och mentorernas godkännanden (det familjerna litar på)."""
        c = (self.s or {}).get("intyg", {}).get(self.lid)
        if not c or time.time() - c.get("tid", 0) > beh.GILTIG:
            return {"roll": None, "intyg": bool(c), "text": "Inget giltigt intyg från rektorn än." if self.s else "Du är inte med i någon skola."}
        if c.get("mentor"):
            return {"roll": "mentor", "klasser": c["mentor"], "intyg": True, "giltigt_till": c["tid"] + beh.GILTIG,
                    "text": f"Mentor för {', '.join(c['mentor'])} (beslut av rektorn {c.get('rektor_namn')})."}
        g = [x for x in self.mina_godk() if x.get("amnen")]
        if g:
            return {"roll": "amne", "intyg": True, "giltigt_till": c["tid"] + beh.GILTIG, "godk": [{k: x[k] for k in ("klass", "amnen")} | {
                "mentor": self._namn(x["mentor"]), "elever": None if x.get("elever") is None else len(x["elever"])} for x in g],
                "text": "Ämneslärare: " + "; ".join(f"{', '.join(x['amnen'])} i {x['klass']} (godkänd av {self._namn(x['mentor'])})" for x in g) + "."}
        return {"roll": None, "intyg": True, "giltigt_till": c["tid"] + beh.GILTIG,
                "text": "Ingen roll än: rektorn kan göra dig till mentor, eller en mentor godkänna dig som ämneslärare för sin klass."}

    def mina_godk(self) -> list[dict]:
        return [g for k, g in (self.s or {}).get("godk", {}).items() if g.get("lid") == self.lid and time.time() - g.get("tid", 0) < beh.GILTIG]

    def till_familjen(self) -> dict:
        """Det som följer med varje synk till familjerna: hela skolans intyg, godkännanden och rektorskedjan.
        Familjen sparar det senaste av varje sort, så att borttagna godkännanden och sänkta behörigheter slår igenom."""
        if not self.s or not self.policy:
            return {}
        nu = time.time()
        return {"intyg": [c for c in self.s.get("intyg", {}).values() if nu - c.get("tid", 0) < beh.GILTIG][:200],
                "godk": [g for g in self.s.get("godk", {}).values() if nu - g.get("tid", 0) < beh.GILTIG][:400],
                "kedja": (self.policy.get("kedja") or [])[-20:]}

    # ---------- det läraren ser ----------
    def publik(self) -> dict | None:
        s = self.s
        if not s:
            return None
        return {"id": s["id"], "namn": s["namn"], "kod": s.get("kod") if s.get("kod") and time.time() - s.get("kod_tid", 0) < KOD_GILTIG else "",
                "meddelanden": [{**m, "egen": m.get("fran") == self.lid, "till_namn": (s["medlemmar"].get(m.get("till") or "") or {}).get("namn") if m.get("till") else None}
                                for m in s.get("meddelanden", [])[-100:]][::-1],
                "olasta": sum(1 for m in s.get("meddelanden", []) if not m.get("last")),
                "medlemmar": [{"id": k, **{x: v.get(x) for x in ("namn", "amne", "roll", "klass", "sedd", "fel", "adress")}, "kan_bli_rektor": bool(v.get("pub")),
                               **({"ratt": beh.rensa_ratt((s.get("policy") or {}).get("larare", {}).get(k, (s.get("policy") or {}).get("standard"))),
                                   "eget": k in (s.get("policy") or {}).get("larare", {})} if s.get("policy") else {})}
                              for k, v in sorted(s["medlemmar"].items(), key=lambda kv: kv[1].get("namn", ""))],
                "min_roll": self.min_roll(),
                "mentorer": {k: v for k, v in ((s.get("policy") or {}).get("mentorer") or {}).items()},
                "godkanda": [{**x, "namn": self._namn(x["lid"])} for x in (self.d.get("godkanda") or {}).values() if x["klass"] in self.mentor_for() and not x.get("bort")],
                "rektor": {"namn": s["policy"].get("rektor_namn"), "jag": self.ar_rektor(), "standard": s["policy"].get("standard", []),
                           "mina_eget": self.lid in s["policy"].get("larare", {}),
                           "jag_ratt": beh.rensa_ratt(s["policy"].get("larare", {}).get(self.lid, s["policy"].get("standard"))),
                           "beslut": s["policy"].get("beslut", [])[-100:][::-1], "ver": s["policy"].get("ver")} if s.get("policy") else None}

    def provkalender(self) -> list[dict]:
        if not self.s:
            return []
        ut = [{**x, "larare": self.d.get("larare") or "Du", "egen": True} for x in self.mina_prov()]
        for lid, lista in self.s["prov"].items():
            namn = (self.s["medlemmar"].get(lid) or {}).get("namn") or "?"
            ut += [{**x, "larare": namn, "egen": False} for x in lista]
        return sorted(ut, key=lambda x: x.get("datum", ""))

    def anteckningar_for(self, e: dict) -> list[dict]:
        """Anteckningar om eleven som jag får se: mina egna och de kollegorna har skickat till mig."""
        egna = [{**a, "egen": True} for a in self.d.get("anteckningar", []) if a.get("elev") == e["id"]]
        andras = [{**a, "egen": False} for lista in ((self.s or {}).get("anteckningar_in") or {}).values() for a in lista
                  if e.get("elev_id") and a.get("elev_id") == e["elev_id"]]
        return sorted(egna + andras, key=lambda a: a.get("tid", ""), reverse=True)

    def fran_kollegor(self) -> dict:
        """Provresultat från ämneslärarna, per elev_id (bara för elever där jag är mentor)."""
        if not self.s:
            return {}
        ut: dict[str, list] = {}
        for lista in self.s["resultat"].values():
            for eid, rader in lista.items():
                ut.setdefault(eid, []).extend(rader)
        return ut

    # ---------- hitta varandra på nätverket ----------
    async def _sok_kod(self, kod: str) -> list[str]:
        """Fråga på nätverket vem som har den här koden. Svar: kollegornas adresser."""
        loop = asyncio.get_running_loop()
        svar: list[str] = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("", 0))
        try:
            fraga = PROTO + b"? " + _kodnyckel(kod).encode()
            for _ in range(3):
                for mal in ("255.255.255.255", "<broadcast>"):
                    try:
                        sock.sendto(fraga, (mal, self.k.port))
                    except OSError:
                        pass
                slut = time.time() + 1.5
                while time.time() < slut:
                    try:
                        data, (ip, _p) = await asyncio.wait_for(loop.sock_recvfrom(sock, 512), timeout=max(0.05, slut - time.time()))
                    except (asyncio.TimeoutError, OSError):
                        break
                    m = re.fullmatch(rb"LXS1! (\d{2,5})", data.strip())
                    if m and f"{ip}:{m.group(1).decode()}" not in svar:
                        svar.append(f"{ip}:{m.group(1).decode()}")
                if svar:
                    break
        finally:
            sock.close()
        return svar

    def _udp_in(self, data: bytes, addr: tuple) -> None:
        ip = addr[0]
        s = self.s
        if not s:
            return
        m = re.fullmatch(rb"LXS1\? ([0-9a-f]{16})", data.strip())
        if m and s.get("kod") and time.time() - s.get("kod_tid", 0) < KOD_GILTIG and hmac.compare_digest(m.group(1).decode(), _kodnyckel(s["kod"])):
            if self._udp:
                self._udp.sendto(PROTO + b"! " + str(self.k.port).encode(), addr)  # svaret till frågans port
            return
        m = re.fullmatch(rb"LXS1 ([\w\-]{6,40}) ([\w\-]{4,40}) (\d{2,5})", data.strip())
        if m and m.group(1).decode() == s["id"] and m.group(2).decode() != self.lid:
            lid = m.group(2).decode()
            if lid in s["medlemmar"]:  # en känd kollega har (kanske) bytt adress
                s["medlemmar"][lid]["adress"] = f"{ip}:{m.group(3).decode()}"

    async def starta(self, session_fn) -> None:
        loop = asyncio.get_running_loop()
        skola = self

        class Udp(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):  # noqa: N802
                try:
                    skola._udp_in(data, addr)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("UDP: %s", err)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", self.k.port))
            self._udp, _ = await loop.create_datagram_endpoint(Udp, sock=sock)
        except OSError as err:
            _LOGGER.warning("Skolan: kunde inte lyssna på nätverket (UDP %s): %s", self.k.port, err)
        self._uppgift = loop.create_task(self._slinga(session_fn))

    async def _slinga(self, session_fn) -> None:
        senast_synk = 0.0
        while True:
            try:
                if self.s:
                    if self._udp:
                        fyr = f"LXS1 {self.s['id']} {self.lid} {self.k.port}".encode()
                        for mal in ("255.255.255.255",):
                            try:
                                self._udp.sendto(fyr, (mal, self.k.port))
                            except OSError:
                                pass
                    if time.time() - senast_synk >= SYNK_VAR:
                        senast_synk = time.time()
                        await self.synka_alla(await session_fn())
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Skolan: %s", err)
            await asyncio.sleep(FYR_VAR)
