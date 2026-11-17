"""Skolan: en sida där varje barn har egna mappar med ämnen, läxböcker och glosor.

Varje barn ser bara sin egen mapp (avgörs av inloggad användare på servern).
Bara föräldrarna i "foraldrar" kan välja och se alla barn. Filerna sparas i
/config/skolan/<barn>/ som inte går att nå via webben eller mediabläddraren.
Glosor kan läsas in från ett foto med AI-uppgiften (Gemini). Bilden ligger då
några sekunder i /media/skolan_tmp under ett slumpat namn och raderas direkt.
"""

from __future__ import annotations

import asyncio
import base64
import html
import io
import json
import logging
import math
import mimetypes
import random
import re
import smtplib
import time
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import voluptuous as vol
from aiohttp import web

from homeassistant.components import panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import dagens, fraga, meriter, schemavy, skola, tillsammans, vanner

_LOGGER = logging.getLogger(__name__)

DOMAIN = "skolan"
TMP_SUBDIR = "skolan_tmp"
STATIC_URL = "/skolan_static"
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text("utf-8"))["version"]  # alltid samma som manifestet
MAX_BYTES = 20 * 1024 * 1024
MAX_NAME = 40
# Delar ett ämne kan ha. Föräldern eller barnet väljer när ämnet skapas och kan ändra sedan.
# Formler och begrepp sparas som listor bland glosorna (med "typ") så att de kan övas och förhöras på samma sätt.
DELAR = ("bocker", "glosor", "formler", "begrepp", "uppgifter", "anteckningar")
LISTTYPER = ("glosor", "formler", "begrepp")


def _delar(a: dict) -> list[str]:
    if isinstance(a.get("delar"), list):
        return [d for d in DELAR if d in a["delar"]]
    return ["bocker", "glosor"]  # ämnen från före delarna


def _sla_pa_del(a: dict, del_: str) -> None:
    """Något läggs in i en del som är avslagen (t.ex. via Lägg in läxa): slå på den så att det syns."""
    if del_ not in _delar(a):
        a["delar"] = [d for d in DELAR if d in _delar(a) + [del_]]


def _rensa_delar(x) -> list[str]:
    valda = [d for d in DELAR if isinstance(x, list) and d in x]
    if not valda:
        raise ValueError("Välj minst en del till ämnet.")
    return valda


FARGER = ["#4f8ef7", "#f7a14f", "#4fc98a", "#e05f8a", "#9b6cf0", "#2bb5c4", "#d4b02a", "#e0603a"]

BARN_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.slug,
        vol.Required("namn"): cv.string,
        vol.Required("user_id"): cv.string,
        vol.Optional("notify"): cv.string,  # t.ex. mobile_app_annas_iphone
        vol.Optional("klocka"): cv.string,  # MQTT-prefix för barnets Awtrix-klocka (valfritt)
    }
)
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional("ai_task_entity"): cv.entity_id,
                vol.Required("barn"): vol.All(cv.ensure_list, [BARN_SCHEMA]),
                # Användar-id för de föräldrar som får se alla barns mappar.
                vol.Required("foraldrar"): vol.All(cv.ensure_list, [cv.string]),
                # Notistjänst per förälder (user_id -> notify-tjänst), för förhör på distans.
                vol.Optional("foralder_notify", default={}): {cv.string: cv.string},
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Skolan kan ställas in i YAML (gamla sättet) eller via Inställningar → Integrationer."""
    if DOMAIN in config:
        return await _starta(hass, config[DOMAIN])
    return True


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    if hass.data.get(DOMAIN):
        _LOGGER.warning("Skolan är redan inställd i YAML. Ta bort skolan: från configuration.yaml för att använda guiden.")
        return False
    d = {**entry.data, **entry.options}
    conf = {
        "ai_task_entity": d.get("ai_task_entity") or None,
        "barn": d.get("barn", []),
        "foraldrar": d.get("foraldrar", []),
        "foralder_notify": d.get("foralder_notify", {}),
    }
    entry.async_on_unload(entry.add_update_listener(_alternativ_andrade))
    return await _starta(hass, conf)


async def _alternativ_andrade(hass: HomeAssistant, entry) -> None:
    """Webbadresser kan inte avregistreras, så ändringar kräver en omstart."""
    from homeassistant.helpers import issue_registry as ir

    ir.async_create_issue(hass, DOMAIN, "omstart", is_fixable=False, severity=ir.IssueSeverity.WARNING,
                          translation_key="omstart")


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    return False  # kräver omstart


async def _starta(hass: HomeAssistant, conf: dict) -> bool:
    base = Path(hass.config.path("skolan"))
    tmp = Path(hass.config.media_dirs.get("local", "/media")) / TMP_SUBDIR

    def _mk():
        for b in conf["barn"]:
            (base / b["id"] / "filer").mkdir(parents=True, exist_ok=True)
        tmp.mkdir(parents=True, exist_ok=True)
        for old in tmp.iterdir():  # rester efter en avbruten AI-läsning
            old.unlink(missing_ok=True)

    await hass.async_add_executor_job(_mk)
    hass.data[DOMAIN] = {
        "conf": conf,
        "base": base,
        "tmp": tmp,
        "locks": {b["id"]: asyncio.Lock() for b in conf["barn"]},
        "jobb": {},  # (barn, bok) -> status för pågående e-boksbygge
        "live": {},  # "barn/uppdrag" -> pågående medhörning
        "foralder_namn": {},  # user_id -> namn, fylls när föräldern skickar förhör
    }

    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)]
    )
    for view in (StateView, ActionView, GlosstridView, LarView, FragaView, UploadView, FileView, GlosorReadView, EbokView, UtskriftView, ForhorView, UppdragView, VeckobrevView, LektionView, SchemaSidaView, UttalView, InspelningView, WidgetView, WidgetNyckelView, WidgetInstallView, ExempelView, VannerView, VanPublikView, VanForfraganView, TillsammansView, VanTillsammansView, SkolaView, KlassView):
        hass.http.register_view(view())

    async def _ateruppta(_event: Event | None = None) -> None:
        """Fortsätt e-böcker som höll på när Home Assistant startades om."""
        pagaende = await hass.async_add_executor_job(_load_fil, base / "pagaende_ebocker.json")
        for j in pagaende.get("jobb", []):
            if j.get("barn") in hass.data[DOMAIN]["locks"]:
                _LOGGER.info("Fortsätter e-bok %s för %s efter omstart", j.get("bok"), j.get("barn"))
                _starta_ebok(hass, j["barn"], j.get("amne"), j.get("bok"), False)
        for b in conf["barn"]:
            hass.async_create_background_task(_rakna_ord(hass, b["id"]), f"skolan_ord_{b['id']}")

    async def _dagens_peppning(b: dict, data: dict) -> None:
        """17:00: vem leder veckan + vad barnet kan göra nu för att få meriter."""

        def _alla() -> list[tuple[str, int, tuple]]:
            ut = []
            for x in conf["barn"]:
                v = meriter.veckoresultat(data if x["id"] == b["id"] else _load(base / x["id"]))
                ut.append((x["namn"], v["poang"], meriter.topp_nyckel(v)))
            return ut

        alla = sorted(await hass.async_add_executor_job(_alla), key=lambda x: x[2], reverse=True)
        mina, min_nyckel = next((p, k) for n, p, k in alla if n == b["namn"])
        andra = [(n, p, k) for n, p, k in alla if n != b["namn"]]
        basta_andra = andra[0] if andra else None
        if alla[0][1] == 0:
            titel, rad1 = "🏆 Veckans topplista", "Ingen har några veckopoäng än. Bli först!"
        elif basta_andra and basta_andra[2] == min_nyckel:
            titel, rad1 = "🏆 Det är jämnt!", f"Du och {basta_andra[0]} har {mina} veckopoäng var. Ta ledningen!"
        elif basta_andra and basta_andra[1] == mina:
            leder = min_nyckel > basta_andra[2]
            titel = f"🥇 Du leder veckan med {mina} poäng!" if leder else f"🏆 {basta_andra[0]} leder veckan med {mina} poäng"
            rad1 = f"Ni har lika många poäng, men {'du' if leder else basta_andra[0]} har gjort mer den här veckan." + ("" if leder else " Gör en läxa eller öva så går du om!")
        elif not basta_andra or mina > basta_andra[1]:
            titel = f"🥇 Du leder veckan med {mina} poäng!"
            rad1 = f"{basta_andra[0]} har {basta_andra[1]}. Håll ledningen!" if basta_andra else "Bra jobbat!"
        else:
            titel = f"🏆 {basta_andra[0]} leder veckan med {basta_andra[1]} poäng"
            rad1 = f"Du har {mina}. Gör dina läxor i tid och slå förra veckan så går du om!"
        tips = meriter.forslag(data)[:2]
        await _notis(hass, b["notify"], titel, rad1 + "\n" + "\n".join(f"👉 {t}" for t in tips))

    async def _paminn(now) -> None:
        """17:15: påminn om läxor som brukar komma idag. 17:00: topplista + tips."""
        idag = now.date()
        for b in conf["barn"]:
            if not b.get("notify"):
                continue
            data = await hass.async_add_executor_job(_load, base / b["id"])
            nycklar = set(data.get("meriter", {}).get("nycklar", []))
            if now.hour == 17 and now.minute == 15:
                for u in data.get("uppdrag", []):
                    d = next((x for x in u.get("dagar", []) if x["datum"] == idag.isoformat()), None)
                    if u.get("typ") == "hogl" and d and d.get("status") not in ("ok", "vantar"):
                        await _notis(
                            hass, b["notify"], "🗣️ Dags att läsa högt!",
                            f"{u['namn']}: läs för mamma eller pappa och tryck på knappen i Läxspelet. +{meriter.P_HOGL_DAG} ⭐",
                            f"/skolan?uppdrag={u['id']}",
                        )
                for s in data.get("schema", []):
                    if int(s["kommer"]) == idag.weekday() and f"lagt_in:{s['id']}:{idag.isoformat()}" not in nycklar:
                        await _notis(
                            hass, b["notify"], f"📥 Har du fått {s['namn']}?",
                            f"Lägg in den i Läxspelet idag eller imorgon så får du {meriter.P_I_TID} meriter! ⏰",
                        )
            else:
                await _dagens_peppning(b, data)

    async_track_time_change(hass, _paminn, hour=17, minute=[0, 15], second=0)

    async def _tjata(now) -> None:
        """Påminn automatiskt om förhör som inte är gjorda (varannan timme, inte under skoltid eller kvällstid)."""
        start = 10 if now.weekday() >= 5 else 15
        if not start <= now.hour <= 20:
            return
        nu_iso = now.isoformat(timespec="minutes")
        idag = now.date().isoformat()
        for b in conf["barn"]:
            if not b.get("notify"):
                continue
            path = _dir(hass, b["id"])
            skicka, larm = [], []
            async with hass.data[DOMAIN]["locks"][b["id"]]:
                data = await hass.async_add_executor_job(_load, path)
                for f in data.get("forhor", []):
                    if f.get("status") == "klart":
                        continue
                    if (now - dt_util.parse_datetime(f["skapad"])).total_seconds() < 3600:
                        continue
                    pam = f.setdefault("paminnelser", [])
                    if pam and (now - dt_util.parse_datetime(pam[-1]["tid"])).total_seconds() < 2 * 3600 - 120:
                        continue
                    pam.append({"tid": nu_iso, "av": "Automatisk"})
                    del pam[:-30]
                    n = len(pam)
                    skicka.append((
                        f"🔔 Påminnelse{f' ({n})' if n > 1 else ''}: förhör väntar!",
                        f"Gör förhöret {f['namn']} ({len(f['fragor'])} ord) nu! Du slipper fler påminnelser när det är klart."
                        if f["status"] == "skickat" else f"Gör klart förhöret {f['namn']}! Du har svarat på {len(f['svar'])} av {len(f['fragor'])}.",
                        f"/skolan?barn={b['id']}&forhor={f['id']}",
                    ))
                    auto_idag = sum(1 for x in pam if x.get("av") == "Automatisk" and x["tid"][:10] == idag)
                    if auto_idag == 3:
                        larm.append((f, n))
                if skicka:
                    await hass.async_add_executor_job(_save, path, data)
            for titel, text, url in skicka:
                await _notis(hass, b["notify"], titel, text, url)
            for f, n in larm:
                for tjanst in conf.get("foralder_notify", {}).values():
                    await _notis(
                        hass, tjanst, f"⚠️ {b['namn']} har inte gjort förhöret",
                        f"{f['namn']}: {n} påminnelser utan att det blivit gjort. Dags att prata med {b['namn']}?",
                        f"/skolan?barn={b['id']}&forhor={f['id']}",
                    )

    async_track_time_change(hass, _tjata, minute=5, second=0)

    senast_klocka: dict[str, str] = {}

    async def _klockor(_now=None) -> None:
        """Svit, stjärnor, dagens utmaning och husdjuret som sensorer, och till barnets Awtrix-klocka."""
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            try:
                data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
                m = meriter.sammanfattning(data)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Skolan: klocka %s: %s", b["id"], err)
                continue
            utm = m["utmaning"]
            klara = sum(1 for x in utm if x["klar"])
            djur = m["djur"] or {}
            hass.states.async_set(f"sensor.skolan_{b['id']}_svit", m["streak"], {
                "friendly_name": f"Läxspelet {b['namn']} svit", "icon": "mdi:fire", "unit_of_measurement": "dagar",
                "idag": m["streak_idag"], "svitskydd": m["skydd"], "stjarnor": m["saldo"],
                "utmaning": f"{klara}/{len(utm)}" if utm else None,
                "husdjur": djur.get("namn"), "husdjur_humor": djur.get("humor"),
                "senast_i_appen": hass.data[DOMAIN].get("senast", {}).get(b["id"]),
            })
            if djur:
                humor_text = {"glad": "är mätt och glad! 😄", "nojd": "väntar på dagens mat 🙂",
                              "hungrig": "är hungrig! 😟", "ledsen": "saknar dig… 😢"}[djur["humor"]]
                figur = "🥚" if djur["steg"] == 0 else djur["art"]
                status = f"{figur} {djur['namn']} " + ("väntar på att kläckas" if djur["steg"] == 0 else humor_text)
            else:
                figur, status = "🥚", "Välj ditt husdjur i Läxspelet!"
            hass.states.async_set(f"sensor.skolan_{b['id']}_husdjur", status[:250], {
                "friendly_name": f"{b['namn']}s husdjur", "icon": "mdi:paw",
                "figur": figur, "namn": djur.get("namn"), "humor": djur.get("humor"),
                "storlek": djur.get("steg_namn"), "kvar_till_nasta": (djur["nasta"] - djur["intjanat"]) if djur.get("nasta") else None,
                "svit": m["streak"], "gjort_idag": m["streak_idag"], "stjarnor": m["saldo"],
                "utmaning": f"{klara}/{len(utm)}" if utm else None,
            })
            prefix = b.get("klocka")
            if not prefix or not hass.services.has_service("mqtt", "publish"):
                continue
            text = [{"t": str(m["streak"]), "c": "FF8C00" if m["streak_idag"] else "777777"}, {"t": " DGR ", "c": "AAAAAA"},
                    {"t": str(m["saldo"]), "c": "FFD700"}]
            app = {"text": text, "duration": 8}
            if utm:
                app.update({"progress": round(klara * 100 / len(utm)), "progressC": "00C853", "progressBC": "333333"})
            if djur and djur.get("humor") in ("hungrig", "ledsen") and dt_util.now().hour >= 14:
                app = {"text": f"{djur['namn'].upper()} ÄR HUNGRIG!", "color": "FF5252", "duration": 10, "scrollSpeed": 80}
            payload = json.dumps(app, ensure_ascii=False)
            if senast_klocka.get(prefix) == payload:
                continue
            try:
                await hass.services.async_call("mqtt", "publish", {"topic": f"{prefix}/custom/skolan", "payload": payload, "retain": True})
                senast_klocka[prefix] = payload
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Skolan: kunde inte skicka till klockan %s: %s", prefix, err)

    async def _hogtid_notis(_now=None) -> None:
        """Säg till barnen när säsongssakerna för en högtid kommer till husdjursbutiken."""
        idag = dt_util.now().date().isoformat()
        for h in meriter.aktiva_hogtider():
            if h["start"] != idag:
                continue
            for b in hass.data[DOMAIN]["conf"]["barn"]:
                await _notis(hass, b.get("notify"), f"{h['ikon']} {h['namn']} i husdjursbutiken!",
                             f"Nya {h['namn'].lower()}saker till ditt husdjur finns nu, bara fram till högtiden. Köp för dina stjärnor!", "/skolan")

    async_track_time_change(hass, _hogtid_notis, hour=15, minute=30, second=0)

    async def _hungrig_notis(_now=None) -> None:
        """Kl. 16: säg till om husdjuret är hungrigt eller ledset (en gång per dag)."""
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            try:
                data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            except Exception:  # noqa: BLE001
                continue
            d = meriter.djur(data) or {}
            if not d or d["humor"] not in ("hungrig", "ledsen"):
                continue
            namn = d["namn"]
            if d["humor"] == "hungrig":
                titel, text = f"😟 {namn} är hungrig!", f"{namn} har inte fått mat på två dagar. Öva lite i Läxspelet så blir {namn} glad igen!"
            else:
                titel, text = f"😢 {namn} saknar dig…", f"{namn} är ledsen. Kom tillbaka till Läxspelet och gör något litet, så blir {namn} glad!"
            await _notis(hass, b.get("notify"), titel, text, "/skolan")

    async_track_time_change(hass, _hungrig_notis, hour=16, minute=0, second=0)
    async def _vanner_synk(_now=None) -> None:
        """Skicka barnens kort till vänservern och hämta vänner (bara när vänner är påslaget)."""
        if not vanner.pa():
            return
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            try:
                await _vanner_synka_barn(hass, b)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Vänsynk %s: %s", b["id"], err)

    async_track_time_change(hass, _vanner_synk, minute=list(range(3, 60, 15)), second=0)
    async_track_time_change(hass, _klockor, second=20)  # varje minut

    async def _skola_mejl(_now=None) -> None:
        """18:00: veckorapport till läraren de dagar föräldern har valt."""
        if not skola.PA:
            return
        idag = dt_util.now().date()
        for b in conf["barn"]:
            try:
                mapp = _dir(hass, b["id"])
                s = await hass.async_add_executor_job(skola.las, mapp)
                if not skola.aktiv(s, "mejl") or idag.weekday() not in s["foralder"]["mejl_dagar"] or s["mejl_skickat"] == idag.isoformat():
                    continue
                data = await hass.async_add_executor_job(_load, mapp)
                namn = s["foralder"].get("namn") or b["namn"]
                r = skola.rapport(data, namn)
                await hass.async_add_executor_job(skola.skicka_mejl, hass.data[DOMAIN]["base"], s["foralder"]["mejl_till"],
                                                  f"Läxspelet: rapport om {namn}", skola.rapport_text(r))
                s["mejl_skickat"] = idag.isoformat()
                await hass.async_add_executor_job(skola.spara, mapp, s)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Rapportmejl för %s gick inte att skicka: %s", b["id"], err)

    async_track_time_change(hass, _skola_mejl, hour=18, minute=0, second=0)
    hass.async_create_task(_klockor())

    async def _notis_knapp(event: Event) -> None:
        """Godkänn/Neka direkt i notisen på en förälders telefon."""
        action = str(event.data.get("action") or "")
        if not action.startswith(("SKOLAN_OK__", "SKOLAN_NEJ__")):
            return
        if event.context.user_id not in conf["foraldrar"]:
            _LOGGER.warning("Skolan: godkännande från fel användare ignorerades")
            return
        try:
            _, barn, uid, datum = action.split("__")
            if barn not in hass.data[DOMAIN]["locks"]:
                return
            await _godkann(hass, barn, uid, None if datum == "-" else datum, action.startswith("SKOLAN_OK__"))
        except ValueError as err:
            _LOGGER.warning("Skolan: kunde inte godkänna %s: %s", action, err)

    hass.bus.async_listen("mobile_app_notification_action", _notis_knapp)

    if hass.is_running:
        hass.async_create_task(_ateruppta())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _ateruppta)

    # Ny fil = ny adress och nytt elementnamn, så ingen webbläsare visar en gammal app ur cachen.
    panel_v = f"{VERSION}-{int((Path(__file__).parent / 'www' / 'panel.js').stat().st_mtime)}"
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path="skolan",
        webcomponent_name=f"skolan-panel-{panel_v.replace('.', '-')}",  # nytt namn per version = appen laddar alltid den nya
        sidebar_title="Läxspelet",
        sidebar_icon="mdi:school",
        module_url=f"{STATIC_URL}/panel.js?v={panel_v}",
        require_admin=False,
        config={},
    )
    return True


# ---------- hjälpare ----------


def _barn_for(hass: HomeAssistant, request: web.Request, wanted: str | None) -> str:
    """Vilket barns mapp får användaren röra? Barn: bara sin egen. Förälder: valfri. Andra: ingen."""
    user = request["hass_user"]
    barn = hass.data[DOMAIN]["conf"]["barn"]
    own = next((b["id"] for b in barn if b["user_id"] == user.id), None)
    if own:
        hass.data[DOMAIN].setdefault("senast", {})[own] = dt_util.now().isoformat(timespec="seconds")
        if wanted and wanted != own:
            raise web.HTTPForbidden
        return own
    if user.id in hass.data[DOMAIN]["conf"]["foraldrar"]:
        ids = [b["id"] for b in barn]
        if wanted in ids:
            return wanted
        return ids[0]
    raise web.HTTPForbidden


def _dir(hass: HomeAssistant, barn: str) -> Path:
    return hass.data[DOMAIN]["base"] / barn


def _load(path: Path) -> dict:
    f = path / "data.json"
    if f.exists():
        try:
            return json.loads(f.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            _LOGGER.exception("Kunde inte läsa %s", f)
    return {"amnen": []}


def _save(path: Path, data: dict) -> None:
    tmp = path / "data.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(path / "data.json")


def _vanner_kort(hass: HomeAssistant, barn: str, v: dict) -> dict | None:
    data = _load(_dir(hass, barn))
    return vanner.kort(v, {**meriter.karta_kort(data), "lag": meriter.lag_kort(data)}, meriter.titel(data))


async def _vanner_foraldrar(hass: HomeAssistant, titel: str, text: str) -> None:
    for tjanst in hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values():
        await _notis(hass, tjanst, titel, text, "/skolan")


def _vlock(hass: HomeAssistant, barn: str) -> asyncio.Lock:
    return hass.data[DOMAIN].setdefault("vlocks", {}).setdefault(barn, asyncio.Lock())


async def _vanner_synka_barn(hass: HomeAssistant, b: dict) -> dict:
    """Hämta alla vänners kort direkt från deras Home Assistant."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    mapp = _dir(hass, b["id"])
    session = async_get_clientsession(hass)
    v = await hass.async_add_executor_job(vanner.las, mapp)
    resultat = {}
    for x in list(v["vanner"]):
        try:
            resultat[x["kod"]] = await vanner.hamta_kort(session, x["kod"])
        except ValueError:
            resultat[x["kod"]] = None
    async with _vlock(hass, b["id"]):
        v = await hass.async_add_executor_job(vanner.las, mapp)
        for kod, k in resultat.items():
            vanner.uppdatera_van(v, kod, k)
        v["synkad"] = dt_util.now().isoformat(timespec="minutes")
        await hass.async_add_executor_job(vanner.spara, mapp, v)
    return v


async def _barn_for_vannyckel(hass: HomeAssistant, nyckel: str) -> tuple[dict, dict] | None:
    import hmac
    hitta = None
    for b in hass.data[DOMAIN]["conf"]["barn"]:
        v = await hass.async_add_executor_job(vanner.las, _dir(hass, b["id"]))
        if v["nyckel"] and hmac.compare_digest(v["nyckel"], nyckel):
            hitta = (b, v)
    return hitta


class VanPublikView(HomeAssistantView):
    """Barnets vänkort för andra familjers Home Assistant. Ingen inloggning, hemlig nyckel i länken."""

    url = "/api/skolan/van/{nyckel}"
    name = "api:skolan:van"
    requires_auth = False

    async def get(self, request: web.Request, nyckel: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        hitta = await _barn_for_vannyckel(hass, nyckel) if vanner.pa() else None
        if not hitta:
            raise web.HTTPNotFound
        b, v = hitta
        k = await hass.async_add_executor_job(_vanner_kort, hass, b["id"], v)
        if not k:
            raise web.HTTPNotFound
        for typ in ("stund", "duell"):  # en vän vill se hur vårt barn ligger till i en pluggstund/duell
            if request.query.get(typ):
                sid = request.query[typ][:20]
                t = await hass.async_add_executor_job(tillsammans.las, hass.data[DOMAIN]["base"])
                x = next((y for y in t["stunder" if typ == "stund" else "dueller"] if y["id"] == sid), None)
                if not x:
                    raise web.HTTPNotFound
                ref = f"barn:{b['id']}"
                if typ == "stund":
                    data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
                    tillsammans.stund_uppdatera(x, {ref: data}, {})
                    return self.json(tillsammans.stund_publik(x, ref))
                return self.json(tillsammans.duell_publik(x, ref))
        if request.query.get("arena"):  # en vän vill strida: husdjurets stridsvärden + versioner
            data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            return self.json({"v": 1, "arena_ver": meriter.ARENA_VER, "skolan": VERSION, "kampe": meriter.arena_kampe(data)})
        if request.query.get("json"):
            return self.json(k)
        lank = html.escape(str(request.url.with_query(None)))
        sida = f"""<!doctype html><html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bli vän i Läxspelet</title><style>body{{font-family:system-ui;background:#fff8e1;margin:0;padding:24px;text-align:center}}
.kort{{background:#fff;border-radius:20px;padding:24px;max-width:360px;margin:auto;box-shadow:0 4px 16px rgba(0,0,0,.12)}}
.djur{{font-size:72px}}button{{font-size:18px;padding:12px 20px;border-radius:12px;border:0;background:#43a047;color:#fff;margin-top:16px}}
textarea{{width:100%;font-size:12px;margin-top:12px;height:70px}}</style></head><body><div class="kort">
<div class="djur">{html.escape(k['art'] or '🙂')}</div><h2>{html.escape(k['smeknamn'])} vill bli din vän i Läxspelet!</h2>
<p>🗺️ Nivå {k['niva']} · ⭐ {k['stjarnor']}</p>
<p>Kopiera länken och klistra in den under <b>🤝 Vänner</b> i Läxspelet.</p>
<button onclick="navigator.clipboard.writeText(document.getElementById('l').value).then(()=>this.textContent='✅ Kopierad!')">📋 Kopiera vänlänken</button>
<textarea id="l" readonly>{lank}</textarea></div></body></html>"""
        return web.Response(text=sida, content_type="text/html")


class VanForfraganView(HomeAssistantView):
    """En annan familjs Home Assistant säger att deras barn har lagt till vårt barn."""

    url = "/api/skolan/van/{nyckel}/forfragan"
    name = "api:skolan:van:forfragan"
    requires_auth = False

    async def post(self, request: web.Request, nyckel: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        hitta = await _barn_for_vannyckel(hass, nyckel) if vanner.pa() else None
        if not hitta:
            raise web.HTTPNotFound
        b, _ = hitta
        try:
            body = json.loads(await request.content.read(2048))
            async with _vlock(hass, b["id"]):
                v = await hass.async_add_executor_job(vanner.las, _dir(hass, b["id"]))
                rad = vanner.ta_emot_forfragan(v, body.get("kod"), body.get("smeknamn"))
                if rad:
                    await hass.async_add_executor_job(vanner.spara, _dir(hass, b["id"]), v)
        except (ValueError, AttributeError):
            return self.json({"ok": False}, status_code=400)
        if rad:
            await _vanner_foraldrar(hass, f"🤝 Vänförfrågan till {b['namn']}",
                                    f"{rad['smeknamn'] or 'Någon'} har lagt till {b['namn']} som vän i Läxspelet. Godkänn eller neka under Vänner.")
        return self.json({"ok": True})


class VannerView(HomeAssistantView):
    """Appens vänsida. Dolt (pa: false) tills vänner slås på."""

    url = "/api/skolan/vanner"
    name = "api:skolan:vanner"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        if not vanner.pa():
            return self.json({"pa": False})
        async with _vlock(hass, barn):
            v = await hass.async_add_executor_job(vanner.las, _dir(hass, barn))
            if vanner.se_till_nyckel(v):
                await hass.async_add_executor_job(vanner.spara, _dir(hass, barn), v)
        return self.json(vanner.publik(v, _ar_foralder(hass, request), _bas_url(hass)))

    async def post(self, request: web.Request) -> web.Response:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        hass: HomeAssistant = request.app["hass"]
        if not vanner.pa():
            raise web.HTTPNotFound
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        op = str(body.get("op") or "")
        b = next(x for x in hass.data[DOMAIN]["conf"]["barn"] if x["id"] == barn)
        if op in ("godkann_smeknamn", "svar_utgaende", "svar_inkommande") and not foralder:
            raise web.HTTPForbidden
        mapp = _dir(hass, barn)
        bas = _bas_url(hass)
        session = async_get_clientsession(hass)
        meddela = None
        try:
            if op == "synka":
                v = await _vanner_synka_barn(hass, b)
                return self.json(vanner.publik(v, foralder, bas))
            async with _vlock(hass, barn):
                v = await hass.async_add_executor_job(vanner.las, mapp)
                vanner.se_till_nyckel(v)
                egen = vanner.egen_kod(bas, v)
                kod = str(body.get("kod") or "")
                if op == "smeknamn":
                    vanner.satt_smeknamn(v, body.get("namn"), foralder)
                    if not foralder:
                        meddela = (f"🤝 {b['namn']} vill heta \"{v['smeknamn']}\"", "Godkänn smeknamnet under Vänner innan det visas för kompisar.")
                elif op == "godkann_smeknamn":
                    vanner.godkann_smeknamn(v)
                elif op == "lagg_till":
                    if not (v["smeknamn_ok"] and egen):
                        raise ValueError("Välj ett smeknamn och låt en förälder godkänna det först.")
                    if foralder:  # föräldern lägger till direkt
                        kod = vanner.normal_kod(kod)
                        vanner._kolla_ny(v, kod, egen)
                        vanner.lagg_in_van(v, kod, await vanner.hamta_kort(session, kod))
                        await vanner.skicka_forfragan(session, kod, egen, v["smeknamn"])
                    else:
                        vanner.onska(v, kod, egen)
                        meddela = (f"🤝 {b['namn']} vill lägga till en vän", "Godkänn eller neka under Vänner i Läxspelet.")
                elif op in ("svar_utgaende", "svar_inkommande"):
                    kod = vanner.normal_kod(kod)
                    if body.get("ja"):
                        if not egen:
                            raise ValueError("Er Home Assistant går inte att nå utifrån, så vänner fungerar inte.")
                        vanner._kolla_ny(v, kod, egen)
                        vanner.lagg_in_van(v, kod, await vanner.hamta_kort(session, kod))
                        if op == "svar_utgaende":
                            await vanner.skicka_forfragan(session, kod, egen, v["smeknamn"])
                    else:
                        lista = "utgaende" if op == "svar_utgaende" else "inkommande"
                        v[lista] = [x for x in v[lista] if x["kod"] != kod]
                elif op == "ta_bort":
                    vanner.ta_bort(v, vanner.normal_kod(kod))
                else:
                    raise ValueError("Okänd åtgärd.")
                await hass.async_add_executor_job(vanner.spara, mapp, v)
        except ValueError as err:
            return self.json_message(str(err), 400)
        if meddela:
            await _vanner_foraldrar(hass, *meddela)
        return self.json(vanner.publik(v, foralder, bas))


def _load_fil(f: Path) -> dict:
    try:
        return json.loads(f.read_text("utf-8")) if f.exists() else {}
    except (OSError, json.JSONDecodeError):
        _LOGGER.exception("Kunde inte läsa %s", f)
        return {}


def _save_fil(f: Path, data: dict) -> None:
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    tmp.replace(f)


def _name(val) -> str:
    s = re.sub(r"\s+", " ", str(val or "")).strip()[:MAX_NAME]
    if not s:
        raise ValueError("Namnet får inte vara tomt.")
    return s


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _find(items: list, item_id: str) -> dict:
    for it in items:
        if it.get("id") == item_id:
            return it
    raise ValueError("Hittades inte (har någon tagit bort den?).")


def _clean_pairs(par) -> list[list[str]]:
    out = []
    for p in par or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            a, b = str(p[0] or "").strip()[:120], str(p[1] or "").strip()[:120]
            if a or b:
                out.append([a, b])
    return out[:300]


def _parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("inget JSON-objekt i svaret")
    return json.loads(t[start : end + 1], strict=False)


def _mime(field) -> str:
    mime = (field.content_type or "").lower()
    if not mime or mime == "application/octet-stream":
        mime = mimetypes.guess_type(field.filename or "")[0] or ""
    return mime


def _ok_file(mime: str) -> bool:
    return mime.startswith("image/") or mime == "application/pdf"


# ---------- vyer ----------


def _lag_fil(hass: HomeAssistant) -> Path:
    return hass.data[DOMAIN]["base"] / "lag.json"


def _lag_las(hass: HomeAssistant, barn: str, data: dict) -> tuple[dict | None, list]:
    """Barnets lag och lagmedlemmarnas data [(id, namn, data)]. Sätter dagens lagbonus i allas data (bara i minnet
    för de andra; barnets egen data sparas av den som anropar)."""
    lagen = _load_fil(_lag_fil(hass)).get("lag", [])
    lag = next((x for x in lagen if barn in x.get("medlemmar", [])), None)
    if not lag:
        meriter.lag_satt(data, None, 0)
        return None, []
    namn = {b["id"]: b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"]}
    medl = [(b, namn[b], data if b == barn else _load(_dir(hass, b))) for b in lag["medlemmar"] if b in namn]
    st = meriter.lag_status(lag, medl, _lag_vanner(hass, lag))
    for _b, _n, d in medl:
        meriter.lag_satt(d, lag, st["bonus"])
    return lag, medl


def _lag_van_val(hass: HomeAssistant) -> list[dict]:
    return [{"kod": x["kod"], "smeknamn": x["smeknamn"], "barn": b["id"], "barn_namn": b["namn"]}
            for b in hass.data[DOMAIN]["conf"]["barn"] for x in vanner.las(_dir(hass, b["id"]))["vanner"]]


def _lag_vanner(hass: HomeAssistant, lag: dict) -> list[dict]:
    """Vänner i andra hem som är med i laget (deras senast hämtade kort). Tomt när vänner är avstängda."""
    if not vanner.pa():
        return []
    ut = []
    for x in lag.get("vanner", []):
        v = vanner.las(_dir(hass, x.get("barn", "")))
        k = next((y for y in v["vanner"] if y["kod"] == x.get("kod")), None)
        if k:
            ut.append({"kod": k["kod"], "barn": x["barn"], **k})
    return ut


def _lag_andra(hass: HomeAssistant, body: dict) -> list:
    f = _lag_fil(hass)
    allt = _load_fil(f)
    lagen = allt.setdefault("lag", [])
    barn = {b["id"] for b in hass.data[DOMAIN]["conf"]["barn"]}
    if body.get("op") == "lag_ta_bort":
        allt["lag"] = [x for x in lagen if x["id"] != body.get("id")]
    else:
        medl = [b for b in dict.fromkeys(body.get("medlemmar") or []) if b in barn]
        if len(medl) < 2:
            raise ValueError("Ett lag behöver minst två barn.")
        lag = next((x for x in lagen if x["id"] == body.get("id")), None) if body.get("id") else None
        if not lag:
            lag = {"id": _new_id()}
            lagen.append(lag)
        for x in lagen:  # ett barn kan bara vara med i ett lag
            if x is not lag:
                x["medlemmar"] = [b for b in x.get("medlemmar", []) if b not in medl]
        vanlista = []
        if vanner.pa():  # vänner i andra hem: måste vara vän med något av barnen i laget
            for x in (body.get("vanner") or [])[: meriter.LAG_MAX]:
                if isinstance(x, dict) and x.get("barn") in medl and any(
                        y["kod"] == x.get("kod") for y in vanner.las(_dir(hass, x["barn"]))["vanner"]):
                    vanlista.append({"kod": x["kod"], "barn": x["barn"]})
        lag["vanner"] = vanlista[: max(0, meriter.LAG_MAX - len(medl))]
        lag.update({"namn": _name(body.get("namn") or "Laget"), "marke": body.get("marke") if body.get("marke") in meriter.LAG_MARKEN else "🏳️",
                    "medlemmar": medl[: meriter.LAG_MAX]})
        allt["lag"] = [x for x in lagen if len(x.get("medlemmar", [])) >= 2]
    _save_fil(f, allt)
    return allt["lag"]


class StateView(HomeAssistantView):
    url = "/api/skolan/state"
    name = "api:skolan:state"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        conf = hass.data[DOMAIN]["conf"]
        user = request["hass_user"]
        parent = user.id in conf["foraldrar"]
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        lag, medl = await hass.async_add_executor_job(_lag_las, hass, barn, data)
        lag_st = meriter.lag_status(lag, medl) if lag else None
        if lag_st and lag_st["boss"]["klar"] and f"lagboss:{lag_st['boss']['vecka']}" not in meriter._m(data)["nycklar"]:
            async with hass.data[DOMAIN]["locks"][barn]:  # lagbossen besegrad: belöning till barnet en gång
                d2 = await hass.async_add_executor_job(_load, _dir(hass, barn))
                if meriter.lagboss_belona(d2, lag_st):
                    meriter.lag_satt(d2, lag, lag_st["bonus"])
                    await hass.async_add_executor_job(_save, _dir(hass, barn), d2)
                data = d2
                meriter.lag_satt(data, lag, lag_st["bonus"])

        def _topp() -> list[dict]:
            ut = []
            for b in conf["barn"]:
                d = data if b["id"] == barn else _load(_dir(hass, b["id"]))
                ut.append({"id": b["id"], "namn": b["namn"], **meriter.sammanfattning(d), "vecka": meriter.veckoresultat(d),
                           "titel": meriter.titel(d), "karta": meriter.karta_kort(d), "jamfor": meriter.jamfor(d)})
            return sorted(ut, key=lambda x: meriter.topp_nyckel(x["vecka"]), reverse=True)

        topplista = await hass.async_add_executor_job(_topp)

        def _syskon() -> dict | None:
            alla = [(b["id"], b["namn"], data if b["id"] == barn else _load(_dir(hass, b["id"]))) for b in conf["barn"]]
            return meriter.syskon_uppdrag(alla)

        syskon_st = await hass.async_add_executor_job(_syskon)
        if not parent and syskon_st and syskon_st["klar"] and f"syskon:{syskon_st['vecka']}" not in meriter._m(data)["nycklar"]:
            async with hass.data[DOMAIN]["locks"][barn]:  # uppdraget klart: belöning till barnet en gång
                d2 = await hass.async_add_executor_job(_load, _dir(hass, barn))
                if meriter.syskon_belona(d2, syskon_st):
                    await hass.async_add_executor_job(_save, _dir(hass, barn), d2)
                data = d2
        idag = dt_util.now().date()
        butik = await hass.async_add_executor_job(_load_fil, hass.data[DOMAIN]["base"] / "butik.json") if parent else None
        return self.json(
            {
                "meriter": {
                    **meriter.sammanfattning(data),
                    "vantande": meriter.vantande(data),
                    "schema_status": meriter.schema_status(data) if parent else [],
                },
                "topplista": topplista,
                "dagens": dagens.dagens(data, next((b["namn"] for b in conf["barn"] if b["id"] == barn), "")),
                "handelse": meriter.vecko_handelse(), "rekord": dagens.rekord(data), "prat": dagens.prat(data), "syskon": syskon_st, "kort": meriter.kort_status(data),
                "fodelsedag": dagens.fodelsedag_idag(data), "jul": dagens.julkalender(data),
                "djurbrev": dagens.husdjurets_brev(data, next((b["namn"] for b in conf["barn"] if b["id"] == barn), "")) if parent else None,
                "djurlista": meriter.DJUR,
                "djurbutik": meriter.butik_lista(),
                "pass": meriter.pass_status(data),
                "karta": meriter.karta_status(data), "arena": meriter.arena_status(data), "revansch": {"bossar": meriter.revansch_lista(data), "kort_kvar": meriter.revansch_kort_kvar(data), "energi": meriter.REVANSCH_ENERGI},
                "kistor": meriter.kista_status(data), "provbossar": meriter.provboss_lista(data),
                "laxfraga": meriter.laxfraga(data) if not parent else None, "veckokoll": meriter.veckokoll(data), "material": meriter.material_fraga(data) if not parent else None,
                "lektioner": data.get("lektioner", []),
                "lag": lag_st, "lagstrid": meriter.lagstrid_status(data), "lag_marken": meriter.LAG_MARKEN,
                "skola": await _skola_status(hass, barn, parent) if skola.PA else None,
                "lag_lista": (await hass.async_add_executor_job(_load_fil, _lag_fil(hass))).get("lag", []) if parent else None,
                "barn_lista": [{"id": b["id"], "namn": b["namn"]} for b in conf["barn"]] if parent else None,
                "lag_van_val": await hass.async_add_executor_job(_lag_van_val, hass) if parent and vanner.pa() else None,
                "rum_platser": meriter.RUM_PLATSER,
                "varianter": meriter.VARIANTER,
                "titel": meriter.titel(data),
                "paket": meriter.paket_lista(data),
                "hogtider": meriter.aktiva_hogtider(),
                "nasta_hogtid": meriter.nasta_hogtid(),
                "djur_steg": [n for _g, n in meriter.DJUR_STEG],
                "nytt_djur_pris": meriter.P_NYTT_DJUR,
                "djur_element": meriter.DJUR_ELEMENT, "element_dalig": meriter.ELEMENT_DALIG, "typer": meriter.TYPER,
                "medaljlista": [
                    {"id": m[0], "ikon": m[1], "namn": m[2], "beskrivning": m[3]} for m in meriter.MEDALJER
                ],
                "poang": {
                    "i_tid": meriter.P_I_TID, "ovning": meriter.P_OVNING, "tidigt": meriter.P_TIDIGT,
                    "forhor_ratt": meriter.P_FORHOR_RATT, "forhor_alla": meriter.P_FORHOR_ALLA, "medalj": meriter.P_MEDALJ,
                },
                "butik": (butik or {"beloningar": []}) if parent else None,
                "barn": barn,
                "namn": next(b["namn"] for b in conf["barn"] if b["id"] == barn),
                "kan_valja": parent,
                "user_id": user.id,
                "alla_barn": [{"id": b["id"], "namn": b["namn"]} for b in conf["barn"]] if parent else [],
                "data": _ut(data, parent),
            }
        )


LAR_PROMPT = (
    "Du är {djur}, ett gulligt och nyfiket husdjur ({art}) som bor i ett läxspel. Ditt barn är 10–13 år och ska förklara "
    "{vad} \"{term}\" för dig, så att du lär dig. Rätt betydelse: \"{facit}\".\n"
    "Det ni har sagt hittills:\n{historik}\n"
    "Bedöm barnets SENASTE förklaring: visar den att barnet förstår? Den behöver inte vara ordagrann, egna ord och exempel är bra. "
    "betyg: 0 = fel eller inget, 1 = delvis, 2 = bra, 3 = jättebra med eget exempel.\n"
    "Svara som husdjuret på enkel svenska, högst 2 korta meningar, glatt och uppmuntrande, gärna med en emoji. "
    "Om betyg är 0 eller 1: ställ EN nyfiken följdfråga som leder barnet rätt, utan att säga svaret. "
    "Om betyg är 2 eller 3: berätta med egna ord vad du har lärt dig och tacka, och ställ INGEN fråga. "
    "{sista}"
    "Svara bara med JSON: {{\"svar\": \"...\", \"betyg\": 0, \"klar\": false}}. klar = true när betyg är 2 eller 3."
)
LAR_RUNDOR = 3
LAR_PER_DAG = 30  # AI-frågor per barn och dag


class LarView(HomeAssistantView):
    """Lär husdjuret: barnet förklarar ett begrepp med egna ord, AI:n svarar som husdjuret."""

    url = "/api/skolan/lar"
    name = "api:skolan:lar"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)
        try:
            a = _find(data.get("amnen", []), body.get("amne"))
            g = _find(a["glosor"], body.get("glosor"))
            par = g["par"][int(body.get("i"))]
        except (ValueError, TypeError, IndexError, KeyError):
            return self.json_message("Ordet finns inte.", 400)
        text = re.sub(r"\s+", " ", str(body.get("text") or "")).strip()[:400]
        if not text:
            return self.json_message("Skriv din förklaring först.", 400)
        historik = [x for x in (body.get("historik") or []) if isinstance(x, dict)][-6:]
        runda = sum(1 for x in historik if x.get("vem") == "barn") + 1
        idag = dt_util.now().date().isoformat()
        rakna = hass.data[DOMAIN].setdefault("lar_rakna", {})
        if rakna.get("dag") != idag:
            rakna.clear()
            rakna["dag"] = idag
        if rakna.get(barn, 0) >= LAR_PER_DAG:
            return self.json_message("Husdjuret är trött efter allt lärande idag. Fortsätt i morgon! 😴", 429)
        rakna[barn] = rakna.get(barn, 0) + 1
        d = meriter._m(data).get("djur") or {}
        typ = g.get("typ") or "glosor"
        term, facit = (par[0], par[1])
        vad = {"begrepp": "begreppet", "formler": "formeln"}.get(typ, "ordet")
        hist = "\n".join(f"{'Barnet' if x.get('vem') == 'barn' else 'Du'}: {str(x.get('text') or '')[:400]}" for x in historik)
        hist += f"\nBarnet: {text}"
        entity = hass.data[DOMAIN]["conf"].get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
        if not entity:
            return self.json_message("Ingen AI finns i Home Assistant.", 503)
        instr = LAR_PROMPT.format(djur=d.get("namn") or "Husdjuret", art=d.get("art") or "🐾", vad=vad, term=term, facit=facit, historik=hist,
                                  sista="Det här är sista rundan: om förklaringen fortfarande inte stämmer, berätta snällt vad det betyder. " if runda >= LAR_RUNDOR else "")
        try:
            resp = await hass.services.async_call("ai_task", "generate_data", {"task_name": "Läxspelet lär husdjuret", "entity_id": entity, "instructions": instr},
                                                  blocking=True, return_response=True)
            raw = (resp or {}).get("data")
            x = _parse_json(raw if isinstance(raw, str) else json.dumps(raw))
            svar = str(x.get("svar") or "").strip()[:400]
            betyg = max(0, min(3, int(x.get("betyg") or 0)))
            if not svar:
                raise ValueError("tomt svar")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Läxspelet: lär husdjuret misslyckades: %s", err)
            return self.json_message("Husdjuret hörde inte riktigt. Försök igen om en stund.", 503)
        klar = betyg >= 2 or runda >= LAR_RUNDOR
        p = 0
        if klar and betyg >= 2 and not foralder:
            async with hass.data[DOMAIN]["locks"][barn]:
                data = await hass.async_add_executor_job(_load, path)
                p = meriter.lar_djuret(data, g, term, betyg)
                await hass.async_add_executor_job(_save, path, data)
        return self.json({"svar": svar, "betyg": betyg, "klar": klar, "p": p, "facit": facit if klar and betyg < 2 else None})


FRAGA_PROMPT = (
    "Du är {djur}, ett gulligt, klokt och lite busigt husdjur ({art}) som bor i Läxspelet. Du pratar med ditt barn, {namn}, som är 10–13 år. "
    "Barnet undrar något om spelet eller vill ha tips om strategi.\n"
    "FAKTA OM SPELET (lita bara på detta, hitta inte på regler, siffror eller saker som inte står här):\n{guide}\n\n"
    "BARNETS LÄGE JUST NU:\n{lage}\n\n"
    "Det ni har sagt hittills:\n{historik}\n\n"
    "REGLER: Svara som husdjuret på enkel svenska, glatt och peppigt, högst 4 korta meningar, gärna en emoji. "
    "Svara bara på det barnet frågar, lägg inte till tips om annat. Ge konkreta råd utifrån läget (t.ex. vilken attack som är bäst mot monstret just nu, vad som ger mest ⭐). "
    "Kolla alltid energin: föreslå aldrig att använda en attack nu om det är för lite ⚡, säg i så fall hur man får mer ⚡. "
    "Det bästa rådet är nästan alltid att plugga, för plugg ger ⭐, ⚡, ❤️ och skada på en gång. "
    "Kompisarna i butiken har en hemlig effekt och vissa passar extra bra med vissa husdjur: avslöja ALDRIG vilken effekt, siffror eller vilka som passar ihop, "
    "var bara retsam och hemlighetsfull (t.ex. 'det är en hemlighet… men välj med hjärtat 😏'). "
    "Prata inte om belöningar från föräldrarna, vänner utanför familjen eller skolans klass. "
    "Om barnet frågar om något skolämne, en läxa, matte, glosor eller fakta: säg ALDRIG svaret, inte ens om det är lätt. Ge bara en liten ledtråd eller ett sätt att tänka, och peppa barnet att räkna/tänka själv. "
    "Om du inte vet: säg det ärligt och föreslå 'ℹ️ Så funkar det'. Om frågan inte handlar om spelet eller plugg, svara kort och snällt och styr tillbaka. "
    "Svara bara med JSON: {{\"svar\": \"...\"}}"
)
FRAGA_PER_DAG = 40  # AI-frågor per barn och dag


class FragaView(HomeAssistantView):
    """Fråga husdjuret: barnet frågar om spelet och strategier, AI:n svarar som husdjuret."""

    url = "/api/skolan/fraga"
    name = "api:skolan:fraga"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        barn = _barn_for(hass, request, body.get("barn"))
        text = re.sub(r"\s+", " ", str(body.get("text") or "")).strip()[:300]
        if not text:
            return self.json_message("Skriv din fråga först.", 400)
        idag = dt_util.now().date().isoformat()
        rakna = hass.data[DOMAIN].setdefault("fraga_rakna", {})
        if rakna.get("dag") != idag:
            rakna.clear()
            rakna["dag"] = idag
        if rakna.get(barn, 0) >= FRAGA_PER_DAG:
            return self.json_message("Husdjuret har pratat så mycket idag att det somnat. Fråga igen i morgon! 😴", 429)
        rakna[barn] = rakna.get(barn, 0) + 1
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        d = meriter._m(data).get("djur") or {}
        lage = fraga.lage(data)
        historik = [x for x in (body.get("historik") or []) if isinstance(x, dict)][-8:]
        hist = "\n".join(f"{'Barnet' if x.get('vem') == 'barn' else 'Du'}: {str(x.get('text') or '')[:400]}" for x in historik)
        hist += f"\nBarnet: {text}"
        entity = hass.data[DOMAIN]["conf"].get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
        if not entity:
            return self.json_message("Ingen AI finns i Home Assistant.", 503)
        namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
        instr = FRAGA_PROMPT.format(djur=d.get("namn") or "Husdjuret", art=d.get("art") or "🐾", namn=namn, guide=fraga.SPELGUIDE, lage=lage, historik=hist)
        try:
            resp = await hass.services.async_call("ai_task", "generate_data", {"task_name": "Läxspelet fråga husdjuret", "entity_id": entity, "instructions": instr},
                                                  blocking=True, return_response=True)
            raw = (resp or {}).get("data")
            x = _parse_json(raw if isinstance(raw, str) else json.dumps(raw))
            svar = str(x.get("svar") or "").strip()[:600]
            if not svar:
                raise ValueError("tomt svar")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Läxspelet: fråga husdjuret misslyckades: %s", err)
            return self.json_message("Husdjuret hörde inte riktigt. Försök igen om en stund.", 503)
        return self.json({"svar": svar})


class GlosstridView(HomeAssistantView):
    """Glosstrid: ett svar i taget. Servern rättar, så att bara riktiga rätt svar gör skada."""

    url = "/api/skolan/glosstrid"
    name = "api:skolan:glosstrid"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        path = _dir(hass, barn)
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                a = _find(data.get("amnen", []), body.get("amne"))
                g = _find(a["glosor"], body.get("glosor"))
                i, r = int(body.get("i")), 1 if body.get("r") else 0
                par = g["par"][i]
            except (ValueError, TypeError, IndexError, KeyError):
                return self.json_message("Ordet finns inte.", 400)
            facit = par[1 - r]
            ratt = _ratt_svar(str(body.get("svar") or ""), facit, g.get("typ") == "formler" and r == 0)
            if foralder:  # föräldrar kan prova, men det påverkar inte barnets karta
                return self.json({"ratt": ratt, "facit": facit, "prov": True})
            ut = meriter.glosstrid_svar(data, ratt)
            await hass.async_add_executor_job(_save, path, data)
        return self.json({**ut, "facit": facit})


class ActionView(HomeAssistantView):
    url = "/api/skolan/action"
    name = "api:skolan:action"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        body = {k: v for k, v in body.items() if not str(k).startswith("_")}  # _-fält sätts bara av servern
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        body["_barn"] = not foralder  # meriter bara när barnet själv gör något
        body["_av"] = request["hass_user"].name if foralder else ""
        op = str(body.get("op") or "")
        if op in FORALDER_OPS and not foralder:
            raise web.HTTPForbidden
        path = _dir(hass, barn)
        if op == "arena_start" and body.get("van"):  # vän i ett annat hem
            from homeassistant.helpers.aiohttp_client import async_get_clientsession

            if not vanner.pa():
                raise web.HTTPForbidden
            v = await hass.async_add_executor_job(vanner.las, _dir(hass, barn))
            van = next((x for x in v["vanner"] if x["kod"] == body.get("van")), None)
            if not van:
                return self.json_message("Den vännen finns inte.", 400)
            try:
                k = await vanner.hamta_kampe(async_get_clientsession(hass), van["kod"], van["smeknamn"])
                de, _okanda = meriter.rensa_kampe(k, van["smeknamn"])
            except ValueError as err:
                return self.json_message(str(err), 400)
            jag = next(b for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn)
            body["_van"] = ("van:" + van["kod"].rsplit("/", 1)[-1][:12], van["smeknamn"], de, jag["namn"])
        elif op == "lagstrid_start" and vanner.pa():  # vänner i laget hämtas från sina hem
            from homeassistant.helpers.aiohttp_client import async_get_clientsession

            lag_nu = next((x for x in (await hass.async_add_executor_job(_load_fil, _lag_fil(hass))).get("lag", [])
                           if barn in x.get("medlemmar", [])), None)
            vk = []
            for x in (lag_nu or {}).get("vanner", []):
                try:
                    k = await vanner.hamta_kampe(async_get_clientsession(hass), x["kod"], "Vännen")
                    vk.append(meriter.rensa_kampe(k, "van")[0])
                except ValueError:
                    pass  # vännen går inte att nå: laget strider utan hen
            body["_vankampar"] = vk
        elif op == "arena_start":  # motståndarens data läses bara, ändras aldrig
            conf = hass.data[DOMAIN]["conf"]
            mot = next((b for b in conf["barn"] if b["id"] == body.get("mot") and b["id"] != barn), None)
            if not mot:
                return self.json_message("Den motståndaren finns inte.", 400)
            jag = next(b for b in conf["barn"] if b["id"] == barn)
            body["_mot"] = (mot["id"], mot["namn"], await hass.async_add_executor_job(_load, _dir(hass, mot["id"])), jag["namn"])
        if op in ("lag_spara", "lag_ta_bort"):
            if not foralder:
                raise web.HTTPForbidden
            try:
                lagen = await hass.async_add_executor_job(_lag_andra, hass, body)
            except ValueError as err:
                return self.json_message(str(err), 400)
            return self.json({"lag_lista": lagen})
        if op.startswith("butik_"):
            f = hass.data[DOMAIN]["base"] / "butik.json"
            butik = await hass.async_add_executor_job(_load_fil, f)
            lista = butik.setdefault("beloningar", [])
            try:
                if op == "butik_lagg_till":
                    lista.append({"id": _new_id(), "namn": _name(body.get("namn")), "kostnad": max(1, int(body.get("kostnad") or 0))})
                elif op == "butik_ta_bort":
                    lista.remove(_find(lista, body.get("id")))
            except (ValueError, TypeError) as err:
                return self.json_message(str(err), 400)
            await hass.async_add_executor_job(_save_fil, f, butik)
            return self.json({"butik": butik})
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            body["_lag"] = await hass.async_add_executor_job(_lag_las, hass, barn, data)
            try:
                if op == "los_in":
                    butik = await hass.async_add_executor_job(_load_fil, hass.data[DOMAIN]["base"] / "butik.json")
                    bel = _find(butik.get("beloningar", []), body.get("beloning"))
                    saldo = meriter.sammanfattning(data)["saldo"]
                    if saldo < bel["kostnad"]:
                        raise ValueError(f"För lite meriter ({saldo} av {bel['kostnad']}).")
                    meriter.ge(data, -bel["kostnad"], f"Löste in: {bel['namn']}", None, "🎁")
                    remove_files = []
                else:
                    remove_files = _apply(data, body)
            except ValueError as err:
                return self.json_message(str(err), 400)
            await hass.async_add_executor_job(_save, path, data)

            def _rm():
                for f in remove_files:
                    (path / "filer" / Path(f).name).unlink(missing_ok=True)

            if remove_files:
                await hass.async_add_executor_job(_rm)
        if op == "bok_lon_be":
            b = _find(_find(data["amnen"], body.get("amne"))["bocker"], body.get("bok"))
            await _be_om_godkannande(hass, barn, {"typ": "bok", "id": f"bok-{b['id']}", "namn": b["namn"], "sidor": b["foto_vantar"]["sidor"], "pris": meriter.foto_pris(b)}, None)
        return self.json({"data": _ut(data, _ar_foralder(hass, request))})


OMSLAG = {"fram": "framsida", "bak": "baksida"}


def _bok_filer(b: dict) -> list[str]:
    """Alla filer som hör till en bok: sidor + omslag."""
    return list(b.get("sidor", [])) + [b[k] for k in OMSLAG.values() if b.get(k)] + [_ebok_fil(b["id"])]


def _ebok_fil(bok_id: str) -> str:
    return f"ebok_{bok_id}.json"


FORALDER_OPS = {
    "schema_spara", "bonus", "los_in", "butik_lagg_till", "butik_ta_bort",
    "manuell_uppdrag", "manuell_schema", "manuell_forhor", "manuell_ovning", "manuell_plugg", "angra_ovning",
    "hejarop_ny", "hejarop_bort", "fodelsedag_satt", "lektioner_spara",
}


def _bakat_datum(v) -> str:
    """Datum för något som gjordes utanför appen: idag eller upp till 7 dagar bakåt."""
    d = str(v or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise ValueError("Ogiltigt datum.")
    dagar = (dt_util.now().date() - date.fromisoformat(d)).days
    if not 0 <= dagar <= 7:
        raise ValueError("Välj en dag den senaste veckan.")
    return d


def _apply(data: dict, body: dict) -> list[str]:
    """Utför en ändring i barnets data. Returnerar filer som ska raderas."""
    op = body.get("op")
    amnen = data.setdefault("amnen", [])
    if op in ("ova_tips", "ova_forsok"):
        if body.get("_barn"):  # föräldrar som provar övningen betalar inget
            meriter.kop_tips(data, "forsok" if op == "ova_forsok" else "tips")
        return []
    if op == "hejarop_ny":
        dagens.hejarop_ny(data, body.get("text"), int(body.get("boost") or 0), str(body.get("nar") or "nu"), body.get("varde"), body.get("_av") or "")
        return []
    if op == "hejarop_bort":
        data["hejarop"] = [h for h in data.get("hejarop", []) if h["id"] != body.get("id")]
        return []
    if op == "hejarop_las":
        if body.get("_barn"):
            dagens.hejarop_las(data, str(body.get("id") or ""))
        return []
    if op in ("fokus_start", "fokus_klar", "fokus_avbryt"):
        if not body.get("_barn"):
            raise ValueError("Fokusläget är för barnet.")
        if op == "fokus_start":
            dagens.fokus_start(data, int(body.get("min") or 0))
        elif op == "fokus_klar":
            dagens.fokus_klar(data)
        else:
            dagens.fokus_avbryt(data)
        return []
    if op == "fodelsedag_satt":
        f = str(body.get("datum") or "")
        if f and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", f):
            raise ValueError("Välj ett datum.")
        data["fodelsedag"] = f
        return []
    if op in ("fodelsedag_hamta", "lucka"):
        if not body.get("_barn"):
            raise ValueError("Det är barnet som öppnar.")
        if op == "fodelsedag_hamta":
            dagens.fodelsedag_hamta(data)
        else:
            dagens.oppna_lucka(data, int(body.get("dag") or 0))
        return []
    if op == "kort_sett":
        if body.get("_barn"):
            meriter.kort_sett(data)
        return []
    if op in ("kista_oppna", "laxfraga_svar"):  # bara barnet själv
        if not body.get("_barn"):
            raise ValueError("Det är barnet som gör det här.")
        if op == "kista_oppna":
            meriter.kista_oppna(data, str(body.get("id") or ""))
        elif body.get("material"):
            meriter.material_vanta(data, str(body.get("material")))
        else:
            meriter.laxfraga_svar(data, bool(body.get("ja")))
        return []
    if op == "lektioner_spara":
        _lektioner_spara(data, body)
        return []
    if op in ("gata_gissa", "gata_svar"):  # dagens gåta (bara barnet själv)
        if not body.get("_barn"):
            raise ValueError("Det är barnet som gissar.")
        if op == "gata_gissa":
            dagens.gissa(data, str(body.get("svar") or ""))
        else:
            dagens.visa_svar(data)
        return []
    if op in ("djur", "djur_kop", "djur_pa", "djur_paket", "pass_hamta", "rum_stall", "attack_kop", "attack_upp", "uppsattning", "attack", "dryck_kop", "dryck", "energi_kop", "skold_kop", "skold_pa", "traning_kop", "lagstrid_start", "lagstrid_drag", "lagstrid_ge_upp", "arena_start", "arena_drag", "arena_ge_upp", "revansch_start", "provboss_start"):  # husdjuret: välj, köp saker, ta på (bara barnet själv)
        if not body.get("_barn"):
            raise ValueError("Det är barnet som bestämmer över sitt husdjur.")
        if op == "djur":
            meriter.djur_valj(data, str(body.get("art") or ""), str(body.get("namn") or ""), str(body.get("id") or "") or None)
        elif op == "djur_kop":
            meriter.djur_kop(data, str(body.get("sak") or ""))
        elif op == "djur_paket":
            meriter.kop_paket(data, str(body.get("paket") or ""))
        elif op == "pass_hamta":
            meriter.hamta_pass(data, int(body.get("niva") or 0))
        elif op == "rum_stall":
            meriter.rum_stall(data, str(body.get("plats") or ""), body.get("sak") or None)
        elif op == "attack_kop":
            meriter.attack_kop(data, str(body.get("attack") or ""))
        elif op == "uppsattning":
            meriter.uppsattning_vaxla(data, str(body.get("attack") or ""))
        elif op == "attack_upp":
            meriter.attack_uppgradera(data, str(body.get("attack") or ""))
        elif op == "attack":
            meriter.attack(data, str(body.get("attack") or ""))
        elif op == "dryck_kop":
            meriter.dryck_kop(data, str(body.get("dryck") or ""))
        elif op == "energi_kop":
            meriter.energi_kop(data, int(body.get("n") or 1))
        elif op == "skold_kop":
            meriter.skold_kop(data, str(body.get("skold") or ""))
        elif op == "traning_kop":
            meriter.traning_kop(data)
        elif op == "skold_pa":
            meriter.skold_pa(data, str(body.get("skold") or "") or None)
        elif op == "dryck":
            meriter.dryck(data, str(body.get("dryck") or ""))
        elif op == "arena_start":
            if "_van" in body:
                mot_id, mot_namn, de, jag_namn = body["_van"]
                meriter.arena_start(data, jag_namn, mot_id, mot_namn, de=de)
            elif "_mot" in body:
                mot_id, mot_namn, mot_data, jag_namn = body["_mot"]
                meriter.arena_start(data, jag_namn, mot_id, mot_namn, mot_data)
            else:
                raise ValueError("Välj en motståndare.")
        elif op == "revansch_start":
            meriter.revansch_start(data, str(body.get("varld") or ""))
        elif op == "provboss_start":
            meriter.provboss_start(data, str(body.get("id") or ""))
        elif op == "arena_drag":
            meriter.arena_drag(data, str(body.get("drag") or ""))
        elif op == "lagstrid_start":
            lag, medl = body.get("_lag") or (None, [])
            if not lag:
                raise ValueError("Du är inte med i något lag än. Be en förälder skapa ett lag.")
            jag = next(x for x in medl if x[2] is data)
            andra = [x for x in medl if x[2] is not data and (x[2].get("meriter") or {}).get("djur")]
            kampar = ([meriter._kampe(data, jag[1])] + [meriter._kampe(d, n) for _i, n, d in andra]
                      + list(body.get("_vankampar") or []))[: meriter.LAG_MAX]
            meriter.lagstrid_start(data, jag[1], f"{lag['marke']} {lag['namn']}", kampar)
        elif op == "lagstrid_drag":
            meriter.lagstrid_drag(data, str(body.get("drag") or ""), int(body.get("mal") or 0))
        elif op == "lagstrid_ge_upp":
            meriter.lagstrid_ge_upp(data)
        elif op == "arena_ge_upp":
            meriter.arena_ge_upp(data)
        else:
            meriter.djur_pa(data, str(body.get("typ") or ""), body.get("sak") or None)
        return []
    if op == "schema_spara":
        ny = []
        for x in (body.get("schema") or [])[:30]:
            if not isinstance(x, dict):
                continue
            _find(amnen, x.get("amne"))  # ämnet måste finnas
            ny.append(
                {
                    "id": x.get("id") or _new_id(),
                    # från vilken dag läxan finns i schemat (tidigare veckor räknas inte)
                    "fran": next((o.get("fran") for o in data.get("schema", []) if o["id"] == x.get("id") and o.get("fran")), None)
                    or dt_util.now().date().isoformat(),
                    "namn": _name(x.get("namn")),
                    "amne": x["amne"],
                    "typ": "bok" if x.get("typ") == "bok" else "glosor",
                    "kommer": int(x.get("kommer")) % 7,
                    "forhor": (int(x["forhor"]) % 7) if x.get("forhor") not in (None, "") else None,
                }
            )
        data["schema"] = ny
        return []
    # Läxor gjorda i boken (utanför appen) som en förälder registrerar.
    if op == "manuell_uppdrag":
        u = _find(data.get("uppdrag", []), body.get("id"))
        if u.get("klart"):
            raise ValueError("Den är redan klar.")
        if u.get("typ") == "hogl":
            raise ValueError("Bocka av högläsningen dag för dag.")
        datum = str(body.get("datum") or dt_util.now().date().isoformat())[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
            raise ValueError("Ogiltigt datum.")
        u["klart"] = f"{datum}T12:00"
        u["manuell"] = True
        meriter.uppdrag_klart(data, u)
        return []
    if op == "manuell_plugg":
        u = _find(data.get("uppdrag", []), body.get("id"))
        if u.get("typ") != "prov":
            raise ValueError("Bara för prov.")
        dag = _bakat_datum(body.get("datum"))
        if dag >= u["datum"]:
            raise ValueError("Pluggdagen måste vara före provet.")
        meriter.prov_studiedag(data, u, dag)
        return []
    if op == "manuell_schema":
        meriter.manuell_schema(data, str(body.get("schema")), str(body.get("ankomst"))[:10], bool(body.get("i_tid")))
        return []
    if op == "manuell_forhor":
        a = _find(amnen, body.get("amne"))
        g = _find(a["glosor"], body.get("glosor"))
        av = max(1, min(500, int(body.get("av") or len(g["par"]))))
        ratt = max(0, min(av, int(body.get("ratt") or 0)))
        nu = dt_util.now().isoformat(timespec="minutes")
        f = {
            "id": _new_id(), "amne": a["id"], "glosor": g["id"], "namn": g["namn"], "amne_namn": a["namn"],
            "meddelande": "Muntligt förhör (registrerat av förälder)", "av_id": "", "av_namn": str(body.get("av_namn") or "Förälder"),
            "skapad": nu, "klart": nu, "status": "klart", "manuell": True,
            "fragor": [{"fraga": "", "facit": "", "fran": "", "till": ""} for _ in range(av)],
            "svar": [{"svar": "", "ratt": i < ratt} for i in range(av)],
        }
        data.setdefault("forhor", []).append(f)
        meriter.forhor_klart(data, f)
        return []
    if op == "bonus":
        p = int(body.get("poang") or 0)
        if not p or abs(p) > 1000:
            raise ValueError("Ogiltigt antal meriter.")
        meriter.ge(data, p, str(body.get("orsak") or "Bonus från förälder")[:80], None, "🎉" if p > 0 else "➖")
        return []
    if op == "add_amne":
        namn = _name(body.get("namn"))
        if any(a["namn"].lower() == namn.lower() for a in amnen):
            raise ValueError("Det ämnet finns redan.")
        delar = _rensa_delar(body.get("delar")) if body.get("delar") is not None else ["bocker", "glosor"]
        amnen.append({"id": _new_id(), "namn": namn, "farg": FARGER[len(amnen) % len(FARGER)], "bocker": [], "glosor": [], "delar": delar})
        return []
    if op == "amne_andra":
        a = _find(amnen, body.get("amne"))
        namn = _name(body.get("namn"))
        if any(x is not a and x["namn"].lower() == namn.lower() for x in amnen):
            raise ValueError("Det ämnet finns redan.")
        a["namn"] = namn
        a["delar"] = _rensa_delar(body.get("delar"))  # en del som tas bort göms bara, innehållet sparas
        return []
    if op == "rename_amne":
        _find(amnen, body.get("amne"))["namn"] = _name(body.get("namn"))
        return []
    if op == "del_amne":
        a = _find(amnen, body.get("amne"))
        amnen.remove(a)
        return [s for b in a.get("bocker", []) for s in _bok_filer(b)]
    a = _find(amnen, body.get("amne")) if body.get("amne") else None
    if a is None:
        raise ValueError("Okänd ändring.")
    if op == "add_bok":
        namn = _name(body.get("namn"))
        a["bocker"].append({"id": _new_id(), "namn": namn, "sidor": []})
        return []
    if op == "rename_bok":
        _find(a["bocker"], body.get("bok"))["namn"] = _name(body.get("namn"))
        return []
    if op == "del_bok":
        b = _find(a["bocker"], body.get("bok"))
        a["bocker"].remove(b)
        return _bok_filer(b)
    if op == "del_omslag":
        b = _find(a["bocker"], body.get("bok"))
        key = OMSLAG.get(body.get("sida"))
        if not key:
            raise ValueError("Okänd omslagssida.")
        old = b.pop(key, None)
        return [old] if old else []
    if op == "del_sida":
        b = _find(a["bocker"], body.get("bok"))
        fil = body.get("fil")
        if fil in b["sidor"]:
            b["sidor"].remove(fil)
            return [fil]
        return []
    if op == "bok_lon_be":  # barnet har fotat klart och ber om lön
        if not body.get("_barn"):
            raise ValueError("Det är barnet som ber om lön för sina foton.")
        b = _find(a["bocker"], body.get("bok"))
        n = len(meriter.foto_obetalda(b))
        if b.get("foto_vantar"):
            raise ValueError("Du har redan frågat. Vänta på mamma eller pappa.")
        if n < meriter.FOTO_MIN_SIDOR:
            raise ValueError(f"Fota minst {meriter.FOTO_MIN_SIDOR} nya sidor först (du har {n}).")
        if not meriter.foto_pris(b, n):
            raise ValueError("Den här boken har redan gett all lön som går.")
        b["foto_vantar"] = {"tid": dt_util.now().isoformat(timespec="minutes"), "sidor": n}
        return []
    if op == "move_sida":
        b = _find(a["bocker"], body.get("bok"))
        fil, steg = body.get("fil"), int(body.get("steg") or 0)
        if fil in b["sidor"]:
            i = b["sidor"].index(fil)
            j = max(0, min(len(b["sidor"]) - 1, i + steg))
            b["sidor"].insert(j, b["sidor"].pop(i))
        return []
    if op == "uppgift_ny":
        text = str(body.get("text") or "").strip()[:200]
        if not text:
            raise ValueError("Skriv vad uppgiften är.")
        datum = str(body.get("datum") or "").strip()
        if datum and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
            raise ValueError("Ogiltigt datum.")
        u = a.setdefault("uppgifter", [])
        if len(u) >= 200:
            raise ValueError("Ta bort några gamla uppgifter först.")
        u.append({"id": _new_id(), "text": text, "datum": datum or None, "klar": None, "skapad": dt_util.now().date().isoformat()})
        _sla_pa_del(a, "uppgifter")
        return []
    if op == "uppgift_klar":
        u = _find(a.get("uppgifter", []), body.get("uppgift"))
        u["klar"] = dt_util.now().date().isoformat() if body.get("klar") else None
        return []
    if op == "uppgift_bort":
        a["uppgifter"].remove(_find(a.get("uppgifter", []), body.get("uppgift")))
        return []
    if op == "anteckning_spara":
        hade = meriter.har_material(a)
        a["anteckningar"] = str(body.get("text") or "")[:10000]
        if body.get("_barn") and not hade and len(a["anteckningar"].strip()) >= 40:
            meriter.material_ny(data, a)
        return []
    if op == "save_glosor":
        namn = _name(body.get("namn"))
        typ = body.get("typ") if body.get("typ") in LISTTYPER else "glosor"
        sprak = [str(s or "").strip()[:30] for s in (body.get("sprak") or ["", ""])][:2]
        while len(sprak) < 2:
            sprak.append("")
        par = _clean_pairs(body.get("par"))
        if not par:
            raise ValueError("Glosorna är tomma.")
        forhor = str(body.get("forhor") or "").strip()
        if forhor and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", forhor):
            raise ValueError("Ogiltigt datum för förhöret.")
        if body.get("glosor"):
            g = _find(a["glosor"], body.get("glosor"))
            g.update({"namn": namn, "sprak": sprak, "par": par, "forhor": forhor or None, "typ": typ})
        else:
            ny_g = {"id": _new_id(), "namn": namn, "sprak": sprak, "par": par, "forhor": forhor or None, "skapad": dt_util.now().date().isoformat(), "typ": typ}
            hade = meriter.har_material(a)
            a["glosor"].append(ny_g)
            if body.get("_barn") and not hade:
                meriter.material_ny(data, a)
            _sla_pa_del(a, typ)
            if body.get("_barn"):
                meriter.lagt_in(data, a["id"], "glosor", ny_g)
        return []
    if op == "manuell_ovning":
        g = _find(a["glosor"], body.get("glosor"))
        dag = _bakat_datum(body.get("datum"))
        if dag in g.get("ovat_dagar", []):
            raise ValueError("Den dagen är redan registrerad.")
        meriter.ovat(data, g, 0, 0, dag)
        if dag in g.get("papper_vantar", []):
            g["papper_vantar"].remove(dag)
        return []
    if op == "angra_ovning":
        g = _find(a["glosor"], body.get("glosor"))
        meriter.angra_ovning(data, g, str(body.get("datum") or "")[:10])
        return []
    if op == "del_glosor":
        a["glosor"].remove(_find(a["glosor"], body.get("glosor")))
        return []
    if op == "rekord":  # Glosrekord: så många rätt som möjligt på 60 sekunder
        g = _find(a["glosor"], body.get("glosor"))
        if body.get("_barn"):
            meriter.rekord(data, g, int(body.get("poang") or 0))
        return []
    if op == "ova_resultat":
        g = _find(a["glosor"], body.get("glosor"))
        g.setdefault("resultat", []).append(
            {"datum": dt_util.now().isoformat(timespec="minutes"), "ratt": int(body.get("ratt") or 0), "av": int(body.get("av") or 0)}
        )
        g["resultat"] = g["resultat"][-20:]
        av = int(body.get("av") or 0)
        if body.get("_barn"):
            meriter.ovat(data, g, int(body.get("ratt") or 0), av, hela=av >= len(g["par"]))
        # Svåra ord: fel på första försöket ger +2, rätt ger -1 (0–6). 2 eller mer = svårt ord.
        svara = g.setdefault("svara", {})
        for x in (body.get("ord") or [])[:200]:
            if not isinstance(x, dict):
                continue
            nyckel = str(x.get("o") or "").strip().lower()[:80]
            if not nyckel:
                continue
            poang = max(0, min(6, svara.get(nyckel, 0) + (-1 if x.get("r") else 2)))
            if poang:
                svara[nyckel] = poang
            else:
                svara.pop(nyckel, None)
        return []
    raise ValueError("Okänd ändring.")


class UploadView(HomeAssistantView):
    """Lägg till sidor (foton/PDF) i en bok."""

    url = "/api/skolan/upload"
    name = "api:skolan:upload"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        form = await request.post()
        barn = _barn_for(hass, request, form.get("barn"))
        path = _dir(hass, barn)
        omslag = form.get("omslag")
        if omslag and omslag not in OMSLAG:
            return self.json_message("Okänd omslagssida.", 400)
        saved: list[str] = []
        for field in form.getall("file", []):
            if omslag and saved:
                break
            if not hasattr(field, "file"):
                continue
            mime = _mime(field)
            if omslag and not mime.startswith("image/"):
                return self.json_message("Omslaget måste vara ett foto.", 400)
            if not _ok_file(mime):
                return self.json_message(f"{field.filename}: bara bilder och PDF:er.", 400)
            content = await hass.async_add_executor_job(field.file.read)
            if len(content) > MAX_BYTES:
                return self.json_message(f"{field.filename}: för stor (max 20 MB).", 400)
            ext = (Path(field.filename or "").suffix or mimetypes.guess_extension(mime) or "").lower()[:6]
            name = f"{dt_util.now().strftime('%Y%m%d-%H%M%S')}_{_new_id()}{ext}"
            await hass.async_add_executor_job((path / "filer" / name).write_bytes, content)
            saved.append(name)
        if not saved:
            return self.json_message("Ingen fil skickades.", 400)
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                a = _find(data.get("amnen", []), form.get("amne"))
                b = _find(a["bocker"], form.get("bok"))
            except ValueError as err:
                for n in saved:
                    await hass.async_add_executor_job((path / "filer" / n).unlink, True)
                return self.json_message(str(err), 400)
            old = None
            if omslag:
                old = b.get(OMSLAG[omslag])
                b[OMSLAG[omslag]] = saved[0]
            else:
                hade = meriter.har_material(a)
                b["sidor"].extend(saved)
                if not _ar_foralder(hass, request) and not hade:
                    meriter.material_ny(data, a)
                if not _ar_foralder(hass, request):
                    b.setdefault("barn_sidor", []).extend(saved)  # barnets egna foton kan ge lön (efter godkännande)
                    meriter.lagt_in(data, a["id"], "bok")
            await hass.async_add_executor_job(_save, path, data)
            if old:
                await hass.async_add_executor_job((path / "filer" / Path(old).name).unlink, True)
        return self.json({"data": _ut(data, _ar_foralder(hass, request)), "saved": saved})


class FileView(HomeAssistantView):
    """Hämta en sida. Bara från det egna barnets mapp."""

    url = "/api/skolan/fil"
    name = "api:skolan:fil"

    async def get(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        fil = Path(request.query.get("fil") or "").name
        f = _dir(hass, barn) / "filer" / fil
        if not fil or not await hass.async_add_executor_job(f.is_file):
            raise web.HTTPNotFound
        cache = "no-store" if fil.startswith("live_") else "private, max-age=86400"
        return web.FileResponse(f, headers={"Cache-Control": cache})


class UttalView(HomeAssistantView):
    """Uppläsning av ett ord med Home Assistant Clouds röst (tydligare än telefonens)."""

    url = "/api/skolan/uttal"
    name = "api:skolan:uttal"

    async def get(self, request: web.Request) -> web.StreamResponse:
        import hashlib
        from homeassistant.components import tts

        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))  # bara inloggade Skolan-användare
        text = (request.query.get("text") or "").strip()[:200]
        sprak = (request.query.get("sprak") or "en-GB").strip()[:10]
        dikt = False
        if request.query.get("forhor"):  # diktamen i ett förhör: ordet hämtas här, barnet ser det aldrig
            data = await hass.async_add_executor_job(_load, _dir(hass, barn))
            try:
                f = _find(data.get("forhor", []), request.query.get("forhor"))
                q = f["fragor"][int(request.query.get("i", -1))]
            except (ValueError, IndexError, TypeError) as err:
                raise web.HTTPNotFound from err
            if not q.get("dikt"):
                raise web.HTTPBadRequest
            text, dikt = str(q["fraga"]).strip()[:200], True
        if not text or not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", sprak):
            raise web.HTTPBadRequest
        mapp = Path(hass.config.path("skolan", "uttal"))
        f = mapp / (hashlib.sha1(f"{sprak}|{text}".encode()).hexdigest() + ".mp3")
        if not await hass.async_add_executor_job(f.is_file):
            try:
                mid = tts.generate_media_source_id(hass, text, "tts.home_assistant_cloud", sprak, None, False)
                _ext, ljud = await tts.async_get_media_source_audio(hass, mid)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Uppläsning misslyckades: %s", err)
                if dikt:  # ingen molnröst (t.ex. Windowsappen): telefonens egen röst får läsa
                    return self.json({"text": text}, status_code=503)
                raise web.HTTPServiceUnavailable from err

            def _spara() -> None:
                mapp.mkdir(parents=True, exist_ok=True)
                f.write_bytes(ljud)

            await hass.async_add_executor_job(_spara)
        return web.FileResponse(f, headers={"Cache-Control": "private, max-age=604800", "Content-Type": "audio/mpeg"})


EXEMPEL_PROMPT = (
    "Du hjälper ett barn i grundskolan (10–13 år) att förstå hur ett ord används.\n"
    "Ord: \"{ord}\" ({sprak}). {betydelse}\n"
    "Skriv EN kort, naturlig och vardaglig mening på {sprak} där ordet används i sin vanliga betydelse. "
    "Meningen ska vara lätt att förstå, högst 15 ord, och ordet ska finnas med (gärna i samma form). "
    "{variant}\n"
    "Svara bara med JSON: {{\"mening\": \"...\", \"svenska\": \"...\", \"forklaring\": \"...\"}}\n"
    "svenska = meningen översatt till svenska ({svenska_regel}).\n"
    "forklaring = vad ordet betyder, förklarat enkelt på svenska med högst 12 ord."
)
EXEMPEL_PER_DAG = 80  # nya meningar per barn och dag
SVENSKA = ("", "svenska", "sv", "swedish")


def _exempel_nyckel(p: list) -> str:
    return f"{str(p[0]).strip()}|{str(p[1] if len(p) > 1 else '').strip()}"[:250]


def _exempel_ord(g: dict, p: list) -> tuple[str, str, str]:
    """(ordet meningen ska innehålla, dess språk, betydelsen). Det främmande språket går före svenskan."""
    sp = [str(x or "").strip() for x in (g.get("sprak") or [])] + ["", ""]
    a, b = str(p[0]).strip(), str(p[1] if len(p) > 1 else "").strip()
    if g.get("typ") == "begrepp":
        return a, "svenska", b
    if sp[0].lower() in SVENSKA and sp[1].lower() not in SVENSKA and b:
        return b, sp[1], a
    return a, sp[0] or "svenska", "" if b.lower() == a.lower() else b


class ExempelView(HomeAssistantView):
    """En exempelmening från AI:n som visar hur ett glosord används. Sparas på glosan."""

    url = "/api/skolan/exempel"
    name = "api:skolan:exempel"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)
        try:
            g = _find(_find(data.get("amnen", []), body.get("amne"))["glosor"], body.get("glosor"))
            par = g["par"][int(body.get("i", -1))]
        except (ValueError, IndexError, TypeError):
            return self.json_message("Ordet finns inte längre.", 404)
        if g.get("typ") == "formler":
            return self.json_message("Exempelmeningar finns bara för ord och begrepp.", 400)
        nyckel = _exempel_nyckel(par)
        gammal = (g.get("exempel") or {}).get(nyckel)
        if gammal and not body.get("ny"):
            return self.json({"nyckel": nyckel, "exempel": gammal})
        ord_, sprak, betydelse = _exempel_ord(g, par)
        if not ord_:
            return self.json_message("Ordet är tomt.", 400)
        rakna = hass.data[DOMAIN].setdefault("exempel_idag", {})
        dag = dt_util.now().date().isoformat()
        if rakna.get("dag") != dag:
            rakna.clear()
            rakna["dag"] = dag
        if rakna.get(barn, 0) >= EXEMPEL_PER_DAG:
            return self.json_message("Nu har AI:n gjort många meningar idag. Försök igen imorgon!", 429)
        conf = hass.data[DOMAIN]["conf"]
        entity = conf.get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
        if not entity:
            return self.json_message("Ingen AI-uppgift finns i Home Assistant.", 500)
        svensk = sprak.lower() in SVENSKA
        instr = EXEMPEL_PROMPT.format(
            ord=ord_[:80], sprak=sprak[:30] or "svenska",
            betydelse=f'Det betyder "{betydelse[:150]}".' if betydelse else "",
            variant=f"Skriv en annan mening än den här: \"{gammal['mening'][:200]}\"" if gammal else "",
            svenska_regel="tom sträng, meningen är redan på svenska" if svensk else "kort och naturlig svenska",
        )
        rakna[barn] = rakna.get(barn, 0) + 1
        try:
            resp = await hass.services.async_call(
                "ai_task", "generate_data", {"task_name": "Läxspelet exempelmening", "entity_id": entity, "instructions": instr},
                blocking=True, return_response=True,
            )
            raw = (resp or {}).get("data")
            x = _parse_json(raw if isinstance(raw, str) else json.dumps(raw))
            ex = {"mening": str(x.get("mening") or "").strip()[:300], "svenska": "" if svensk else str(x.get("svenska") or "").strip()[:300],
                  "forklaring": str(x.get("forklaring") or "").strip()[:200], "ord": ord_[:80]}
            if not ex["mening"]:
                raise ValueError("tomt svar")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Läxspelet: kunde inte göra exempelmening: %s", err)
            return self.json_message("AI:n kunde inte göra en mening just nu. Försök igen om en stund.", 503)
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                g = _find(_find(data.get("amnen", []), body.get("amne"))["glosor"], body.get("glosor"))
            except ValueError:
                return self.json({"nyckel": nyckel, "exempel": ex})
            nu = {_exempel_nyckel(q) for q in g.get("par", [])}
            g["exempel"] = {k: v for k, v in (g.get("exempel") or {}).items() if k in nu}  # glömmer ord som tagits bort
            g["exempel"][nyckel] = ex
            await hass.async_add_executor_job(_save, path, data)
        return self.json({"nyckel": nyckel, "exempel": ex})


class InspelningView(HomeAssistantView):
    """Barnet spelar in sin högläsning. Föräldrarna lyssnar och godkänner."""

    url = "/api/skolan/inspelning"
    name = "api:skolan:inspelning"

    async def get(self, request: web.Request) -> web.Response:
        """Medhörning: pågår inläsningen just nu, och hur lång är den?"""
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        x = hass.data[DOMAIN]["live"].get(f"{barn}/{request.query.get('id')}")
        if not x:
            return self.json({"aktiv": False})
        nu = dt_util.now().timestamp()
        return self.json({"aktiv": nu - x["senast"] < 20, "fil": x["fil"], "sek": int(nu - x["start"])})

    async def _live(self, hass: HomeAssistant, request: web.Request, form, barn: str, steg: str) -> web.Response:
        path = _dir(hass, barn)
        nyckel = f"{barn}/{form.get('id')}"
        live = hass.data[DOMAIN]["live"]
        nu = dt_util.now().timestamp()
        if steg == "start":
            idag = dt_util.now().date().isoformat()
            async with hass.data[DOMAIN]["locks"][barn]:
                data = await hass.async_add_executor_job(_load, path)
                try:
                    u = _find(data.get("uppdrag", []), form.get("id"))
                    d = next((x for x in u.get("dagar", []) if x["datum"] == idag), None) if u["typ"] == "hogl" else None
                    if not d or d.get("status") in ("ok", "vantar"):
                        raise ValueError("Ingen högläsning att spela in idag.")
                except ValueError as err:
                    return self.json_message(str(err), 400)
            gammal = live.pop(nyckel, None)
            if gammal:
                await hass.async_add_executor_job((path / "filer" / gammal["fil"]).unlink, True)
            ext = ".webm" if "webm" in str(form.get("typ") or "") else ".m4a"
            fil = f"live_{idag}_{_new_id()}{ext}"
            await hass.async_add_executor_job((path / "filer" / fil).write_bytes, b"")
            senast_notis = (gammal or {}).get("notis", 0)
            live[nyckel] = {"fil": fil, "start": nu, "senast": nu, "notis": senast_notis, "storlek": 0}
            if nu - senast_notis > 600:  # inte flera notiser om barnet börjar om
                live[nyckel]["notis"] = nu
                conf = hass.data[DOMAIN]["conf"]
                namn = next(b["namn"] for b in conf["barn"] if b["id"] == barn)
                for tjanst in conf.get("foralder_notify", {}).values():
                    await _notis(hass, tjanst, f"🔴 {namn} läser högt just nu",
                                 f"{u['namn']}{': ' + u['kapitel'] if u.get('kapitel') else ''}. Tryck för att lyssna med.",
                                 f"/skolan?barn={barn}&uppdrag={u['id']}")
            return self.json({"fil": fil})
        x = live.get(nyckel)
        field = form.get("file")
        if not x or not hasattr(field, "file"):
            return self.json({"ok": False})
        bitar = await hass.async_add_executor_job(field.file.read)
        if x["storlek"] + len(bitar) > 40 * 1024 * 1024:
            return self.json({"ok": False})

        def _lagg_till() -> None:
            with open(path / "filer" / x["fil"], "ab") as f:
                f.write(bitar)

        await hass.async_add_executor_job(_lagg_till)
        x["storlek"] += len(bitar)
        x["senast"] = nu
        return self.json({"ok": True})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        form = await request.post()
        barn = _barn_for(hass, request, form.get("barn"))
        if _ar_foralder(hass, request):
            return self.json_message("Bara barnet spelar in sin högläsning.", 400)
        steg = str(form.get("steg") or "klar")
        if steg in ("start", "del"):
            return await self._live(hass, request, form, barn, steg)
        field = form.get("file")
        if not hasattr(field, "file"):
            return self.json_message("Ingen inspelning skickades.", 400)
        mime = _mime(field)
        if not mime.startswith(("audio/", "video/mp4", "video/webm")):
            return self.json_message("Det där är ingen ljudfil.", 400)
        content = await hass.async_add_executor_job(field.file.read)
        if len(content) > 40 * 1024 * 1024:
            return self.json_message("Inspelningen är för lång.", 400)
        if len(content) < 2000:
            return self.json_message("Inspelningen blev tom. Försök igen.", 400)
        ext = ".m4a" if "mp4" in mime or "m4a" in mime or "aac" in mime else ".webm" if "webm" in mime else ".ogg" if "ogg" in mime else ".m4a"
        path = _dir(hass, barn)
        idag = dt_util.now().date().isoformat()
        namn = f"insp_{idag}_{_new_id()}{ext}"
        live_x = hass.data[DOMAIN]["live"].pop(f"{barn}/{form.get('id')}", None)
        live_fil = None  # medhörningsfilen tas bort nu när hela inspelningen kommit

        def _skriv_och_stada() -> None:
            (path / "filer" / namn).write_bytes(content)
            grans = (dt_util.now().date() - timedelta(days=30)).isoformat()
            for f in (path / "filer").glob("insp_*"):  # inspelningar sparas i 30 dagar
                if f.name[5:15] < grans:
                    f.unlink(missing_ok=True)
            for f in (path / "filer").glob("live_*"):  # medhörningsfiler behövs inte efteråt
                if f.name != (live_fil or ""):
                    f.unlink(missing_ok=True)

        await hass.async_add_executor_job(_skriv_och_stada)
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                u = _find(data.get("uppdrag", []), form.get("id"))
                if u["typ"] != "hogl":
                    raise ValueError("Det här är ingen högläsning.")
                d = next((x for x in u.get("dagar", []) if x["datum"] == idag), None)
                if not d:
                    raise ValueError("Idag är ingen läsdag.")
                if d.get("status") in ("ok", "vantar"):
                    raise ValueError("Dagens högläsning är redan skickad.")
            except ValueError as err:
                await hass.async_add_executor_job((path / "filer" / namn).unlink, True)
                return self.json_message(str(err), 400)
            gammal = d.get("inspelning")
            d["inspelning"] = namn
            d["insp_sek"] = max(0, min(7200, int(form.get("sek") or 0)))
            d["status"] = "vantar"
            d["tid"] = dt_util.now().isoformat(timespec="minutes")
            meriter.kolla_utmaning(data)
            await hass.async_add_executor_job(_save, path, data)
            if gammal:
                await hass.async_add_executor_job((path / "filer" / Path(gammal).name).unlink, True)
        await _be_om_godkannande(hass, barn, u, idag)
        return self.json({"data": _ut(data, False)})


def _widget_nyckel(hass: HomeAssistant, barn: str, skapa: bool = False) -> str | None:
    import secrets
    f = _dir(hass, barn) / "widget.json"
    x = _load_fil(f) if f.exists() else {}
    if not x.get("nyckel") and skapa:
        x["nyckel"] = secrets.token_urlsafe(24)
        _save_fil(f, x)
    return x.get("nyckel")


def _bas_url(hass: HomeAssistant) -> str:
    """Adressen som fungerar även utanför hemmet (Nabu Casa) om den finns."""
    try:
        from homeassistant.components import cloud
        if cloud.async_active_subscription(hass) and cloud.async_remote_ui_url(hass):
            return cloud.async_remote_ui_url(hass)
    except Exception:  # noqa: BLE001
        pass
    return hass.config.external_url or hass.config.internal_url or ""


def _widget_kod(hass: HomeAssistant, nyckel: str) -> str:
    mall = (Path(__file__).parent / "verktyg" / "widget_mall.js").read_text("utf-8")
    return mall.replace("__BAS__", _bas_url(hass).rstrip("/")).replace("__NYCKEL__", nyckel)


class WidgetInstallView(HomeAssistantView):
    """Laddar ner widgetskriptet som en .scriptable-fil: öppnas direkt i appen Scriptable."""

    url = "/api/skolan/widget/{nyckel}/Husdjur.scriptable"
    name = "api:skolan:widget:installera"
    requires_auth = False

    async def get(self, request: web.Request, nyckel: str) -> web.Response:
        import hmac
        hass: HomeAssistant = request.app["hass"]
        ok = False
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            n = await hass.async_add_executor_job(_widget_nyckel, hass, b["id"])
            ok = ok or bool(n and hmac.compare_digest(n, nyckel))
        if not ok:
            raise web.HTTPNotFound
        kod = await hass.async_add_executor_job(_widget_kod, hass, nyckel)
        fil = {"always_run_in_app": False, "icon": {"color": "green", "glyph": "paw"}, "name": "Husdjur",
               "script": kod, "share_sheet_inputs": []}
        return web.Response(body=json.dumps(fil, ensure_ascii=False).encode(), headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="Husdjur.scriptable"', "Cache-Control": "no-store"})


class WidgetNyckelView(HomeAssistantView):
    """Barnets hemliga widgetlänk (skapas första gången)."""

    url = "/api/skolan/widgetnyckel"
    name = "api:skolan:widgetnyckel"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        nyckel = await hass.async_add_executor_job(_widget_nyckel, hass, barn, True)
        bas = _bas_url(hass).rstrip("/")
        return self.json({"nyckel": nyckel, "bas": bas, "kod": await hass.async_add_executor_job(_widget_kod, hass, nyckel),
                          "installera": f"{bas}/api/skolan/widget/{nyckel}/Husdjur.scriptable"})


class WidgetView(HomeAssistantView):
    """Husdjurets status för hemskärmswidgeten. Ingen inloggning, men en hemlig nyckel per barn
    och bara husdjurets status och lektionsschemat (inga läxor eller annat)."""

    url = "/api/skolan/widget/{nyckel}"
    name = "api:skolan:widget"
    requires_auth = False

    async def get(self, request: web.Request, nyckel: str) -> web.Response:
        import hmac
        hass: HomeAssistant = request.app["hass"]
        barn = None
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            n = await hass.async_add_executor_job(_widget_nyckel, hass, b["id"])
            if n and hmac.compare_digest(n, nyckel):
                barn = b
        if not barn:
            raise web.HTTPNotFound
        data = await hass.async_add_executor_job(_load, _dir(hass, barn["id"]))
        m = meriter.sammanfattning(data)
        d = m.get("djur") or {}
        utm = m["utmaning"]
        sak = lambda i: meriter._sak(i) if i else None  # noqa: E731
        pa = d.get("pa", {})
        agg = d.get("steg", 0) == 0
        slug = "-".join(f"{ord(c):x}" for c in d.get("art", "") if c != "\ufe0f")
        humor = d.get("humor", "nojd")
        bg = sak(pa.get("bakgrund"))
        farger = re.findall(r"#[0-9a-fA-F]{6}", (bg or {}).get("bg", "")) or {
            "glad": ["#e8f5e9", "#a5d6a7"], "nojd": ["#e3f2fd", "#90caf9"], "hungrig": ["#fff8e1", "#ffcc80"], "ledsen": ["#eceff1", "#b0bec5"]}[humor]
        ank = await hass.async_add_executor_job(_load_fil, Path(__file__).parent / "www" / "djur" / "ankare.json")
        hatt = sak(pa.get("hatt")) if not agg else None
        a = ank.get("ankare", {}).get(slug, {})
        humor_text = {"glad": "är mätt och glad!", "nojd": "väntar på dagens mat", "hungrig": "är hungrig!", "ledsen": "saknar dig…"}[humor]
        return self.json({
            "namn": d.get("namn") or "Välj ett husdjur",
            "text": ("väntar på att kläckas" if agg else humor_text) if d else "Öppna Läxspelet och välj ditt husdjur!",
            "humor": humor,
            "bild": f"{STATIC_URL}/djur/{'agg' if agg or not d else slug}_{humor}.png",
            "hatt": hatt["ikon"] if hatt else ("👑" if d.get("steg", 0) >= 5 else None),
            "hatt_pos": a.get("ogon" if hatt and hatt["id"] in ank.get("ogon_saker", []) else "hatt"),
            "kompis": (sak(pa.get("kompis")) or {}).get("ikon") if not agg else None,
            "kompis_pos": ank.get("kompis"),
            "bg": farger[:1] + farger[-1:],
            "fg": (bg or {}).get("fg", "#263238"),
            "svit": m["streak"], "idag": m["streak_idag"], "stjarnor": m["saldo"],
            "utmaning": f"{sum(1 for x in utm if x['klar'])}/{len(utm)}" if utm else None,
            "schema": meriter.lektion_nu(data),
        }, headers={"Cache-Control": "no-store"})


GLOS_PROMPT = (
    "Du läser ett foto eller en PDF av en glosläxa (ordlista) för ett skolbarn i Sverige. "
    "Hitta alla ordpar: ett ord/uttryck på ett språk och dess översättning. "
    "Svara ENDAST med giltig JSON utan markdown, på formen "
    '{"sprak": [språk för första kolumnen, språk för andra kolumnen], "par": [[ord, översättning], ...], '
    '"namn": kort förslag på namn för läxan (t.ex. "Kapitel 3" eller "Vecka 12") eller null, "note": kort kommentar eller ""}. '
    "Språknamn på svenska (t.ex. \"Engelska\", \"Svenska\", \"Spanska\", \"Tyska\", \"Franska\"). "
    "Lägg det främmande språket först och svenska sist om båda finns. "
    "Behåll stavningen exakt som i bilden, inklusive artiklar (t.ex. \"el perro\", \"to run\"). "
    "Hitta inte på ord som inte står där. Är bilden oläslig: tom lista och förklara i note."
)


class GlosorReadView(HomeAssistantView):
    """Läs glosor från ett foto med AI-uppgiften. Sparar inget, barnet granskar först."""

    url = "/api/skolan/glosor_las"
    name = "api:skolan:glosor_las"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        form = await request.post()
        barn = _barn_for(hass, request, form.get("barn"))
        field = form.get("file")
        if field is None or not hasattr(field, "file"):
            return self.json_message("Ingen fil skickades.", 400)
        mime = _mime(field)
        if not _ok_file(mime):
            return self.json_message("Bara bilder och PDF:er.", 400)
        content = await hass.async_add_executor_job(field.file.read)
        if len(content) > MAX_BYTES:
            return self.json_message("Filen är för stor (max 20 MB).", 400)
        ext = (Path(field.filename or "").suffix or mimetypes.guess_extension(mime) or "").lower()[:6]
        name = f"{uuid.uuid4().hex}{ext}"
        tmp = hass.data[DOMAIN]["tmp"] / name
        await hass.async_add_executor_job(tmp.write_bytes, content)

        conf = hass.data[DOMAIN]["conf"]
        entity = conf.get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
        if not entity:
            return self.json_message("Ingen AI-uppgift finns i Home Assistant.", 500)
        try:
            resp = await hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": "Läs glosor",
                    "entity_id": entity,
                    "instructions": GLOS_PROMPT,
                    "attachments": [
                        {
                            "media_content_id": f"media-source://media_source/local/{TMP_SUBDIR}/{name}",
                            "media_content_type": mime,
                        }
                    ],
                },
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Glosläsning misslyckades: %s", err)
            return self.json_message(f"AI:n kunde inte läsa bilden: {err}", 502)
        finally:
            await hass.async_add_executor_job(lambda: tmp.unlink(missing_ok=True))

        text = (resp or {}).get("data")
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        try:
            parsed = _parse_json(text)
        except (ValueError, json.JSONDecodeError):
            return self.json({"sprak": ["", ""], "par": [], "note": "AI:n svarade inte i rätt format. Försök igen."})
        sprak = [str(s or "") for s in (parsed.get("sprak") or ["", ""])][:2]
        while len(sprak) < 2:
            sprak.append("")
        return self.json(
            {
                "sprak": sprak,
                "par": _clean_pairs(parsed.get("par")),
                "namn": parsed.get("namn") or "",
                "note": parsed.get("note") or "",
            }
        )


# ---------- e-bok ----------

EBOK_PROMPT = (
    "Du får ett foto eller en PDF med en eller flera sidor ur skolboken \"{titel}\" i ämnet {amne}. "
    "Skriv INTE av bokens text (den är upphovsrättsskyddad). Ta bara fram strukturen och en kort sammanfattning med egna ord. "
    "Senaste kapitel före den här sidan: {kapitel}. "
    "Svara ENDAST med giltig JSON utan markdown, på formen "
    '{{"sidor": [{{"sidnummer": tryckt sidnummer som text eller null, '
    '"kapitel": kapitelrubriken om ett nytt kapitel BÖRJAR på sidan, annars null (inte sidhuvuden som upprepas), '
    '"rubriker": [mindre rubriker/avsnitt som börjar på sidan], '
    '"sammanfattning": 1–3 meningar på svenska med egna ord om vad sidan handlar om, skrivet för ett barn, '
    '"ord": ungefär hur många ord som finns att läsa på sidan (heltal; räkna brödtext, rubriker och bildtexter, inte sidnummer eller sidhuvud; 0 om sidan bara har bilder), '
    '"innehallsforteckning": true om sidan är bokens innehållsförteckning, annars false}}]}}. '
    "Ett objekt per boksida i läsordning (ett uppslag = två sidor, en PDF kan ha många sidor). Hitta inte på."
)


async def _ai_las(hass: HomeAssistant, src: Path, prompt: str, task_name: str) -> str:
    """Kopiera filen till en tillfällig mediafil, låt AI:n läsa den och radera kopian."""
    conf = hass.data[DOMAIN]["conf"]
    entity = conf.get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
    if not entity:
        raise RuntimeError("Ingen AI-uppgift finns i Home Assistant.")
    mime = mimetypes.guess_type(src.name)[0] or "image/jpeg"
    name = f"{uuid.uuid4().hex}{src.suffix.lower()}"
    tmp = hass.data[DOMAIN]["tmp"] / name
    await hass.async_add_executor_job(shutil.copyfile, src, tmp)
    try:
        resp = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "task_name": task_name,
                "entity_id": entity,
                "instructions": prompt,
                "attachments": [
                    {"media_content_id": f"media-source://media_source/local/{TMP_SUBDIR}/{name}", "media_content_type": mime}
                ],
            },
            blocking=True,
            return_response=True,
        )
    finally:
        await hass.async_add_executor_job(lambda: tmp.unlink(missing_ok=True))
    text = (resp or {}).get("data")
    return text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)


TOC_PROMPT = (
    "Det här är innehållsförteckningen i skolboken \"{titel}\". "
    "Lista bokens kapitel och avsnitt med det sidnummer där de börjar. "
    'Svara ENDAST med giltig JSON: {{"kapitel": [{{"titel": kapitlets namn (med ev. nummer), "sida": startsida som heltal}}]}}. '
    "I läsordning. Ta bara med det som står i förteckningen."
)


def _ar_toc(sida: dict) -> bool:
    if sida.get("toc"):
        return True
    txt = " ".join([sida.get("kapitel") or "", *(sida.get("rubriker") or [])]).lower()
    return "innehåll" in txt or "innehållsförteckning" in (sida.get("sammanfattning") or "").lower()


def _sidnr_int(v) -> int | None:
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def _txt(v, n: int) -> str | None:
    v = str(v).strip() if v not in (None, "") and not isinstance(v, (dict, list)) else ""
    return v[:n] or None


def _senaste_kapitel(cache: dict, filer: list[str]) -> str:
    kap = None
    for f in filer:
        for sida in cache.get(f, {}).get("sidor", []):
            if sida.get("kapitel"):
                kap = sida["kapitel"]
    return f"\"{kap}\"" if kap else "ingen ännu"


def _starta_ebok(hass: HomeAssistant, barn: str, amne: str, bok: str, gor_om: bool) -> dict:
    jobb = hass.data[DOMAIN]["jobb"]
    jobb[(barn, bok)] = {"kor": True, "klar": 0, "av": 0}
    hass.async_create_background_task(_bygg_ebok(hass, barn, amne, bok, gor_om), f"skolan_ebok_{bok}")
    return jobb[(barn, bok)]


async def _markera_pagaende(hass: HomeAssistant, barn: str, amne: str, bok: str, pa: bool) -> None:
    """Kom ihåg pågående e-böcker på disk, så de kan fortsätta efter en omstart."""
    f = hass.data[DOMAIN]["base"] / "pagaende_ebocker.json"
    async with hass.data[DOMAIN].setdefault("pagaende_lock", asyncio.Lock()):
        d = await hass.async_add_executor_job(_load_fil, f)
        lista = [j for j in d.get("jobb", []) if not (j.get("barn") == barn and j.get("bok") == bok)]
        if pa:
            lista.append({"barn": barn, "amne": amne, "bok": bok})
        await hass.async_add_executor_job(_save_fil, f, {"jobb": lista})


async def _bygg_ebok(hass: HomeAssistant, barn: str, amne_id: str, bok_id: str, gor_om: bool) -> None:
    jobb = hass.data[DOMAIN]["jobb"]
    key = (barn, bok_id)
    path = _dir(hass, barn)
    ebok_path = path / "filer" / _ebok_fil(bok_id)
    st = jobb[key]
    await _markera_pagaende(hass, barn, amne_id, bok_id, True)
    klart = False
    try:
        data = await hass.async_add_executor_job(_load, path)
        a = _find(data.get("amnen", []), amne_id)
        b = _find(a["bocker"], bok_id)
        filer = list(b.get("sidor", []))
        ebok = {} if gor_om else await hass.async_add_executor_job(_load_fil, ebok_path)
        cache = ebok.setdefault("cache", {})
        att_gora = [f for f in filer if f not in cache or cache[f].get("fel")]
        st.update(av=len(att_gora), klar=0)
        for f in att_gora:
            prompt = EBOK_PROMPT.format(
                titel=b["namn"], amne=a["namn"], kapitel=_senaste_kapitel(cache, filer[: filer.index(f)])
            )
            try:
                for forsok in range(3):  # Google svarar ibland 503 "high demand"
                    try:
                        text = await _ai_las(hass, path / "filer" / f, prompt, "Skolan e-bok")
                        break
                    except Exception:  # noqa: BLE001
                        if forsok == 2:
                            raise
                        await asyncio.sleep(20 * (forsok + 1))
                try:
                    parsed = _parse_json(text)
                    sidor = [
                        {
                            "sidnr": _txt(x.get("sidnummer"), 12),
                            "kapitel": _txt(x.get("kapitel"), 120),
                            "rubriker": [r for r in (_txt(r, 120) for r in (x.get("rubriker") or [])[:10]) if r],
                            "sammanfattning": _txt(x.get("sammanfattning"), 600),
                            "toc": x.get("innehallsforteckning") is True,
                            "ord": _ord_int(x.get("ord")),
                        }
                        for x in parsed.get("sidor") or []
                        if isinstance(x, dict)
                    ]
                except (ValueError, json.JSONDecodeError, AttributeError, TypeError):
                    sidor = []
                cache[f] = {"sidor": sidor} if sidor else {"sidor": [], "fel": "AI:n kunde inte läsa sidan."}
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("E-bok: kunde inte läsa %s: %s", f, err)
                cache[f] = {"sidor": [], "fel": str(err)[:200]}
                await asyncio.sleep(10)  # ge AI-tjänsten en paus om den är överbelastad
            await hass.async_add_executor_job(_save_fil, ebok_path, ebok)
            st["klar"] += 1

        # Innehållsförteckning -> kapitel med startsidor (mer pålitligt än att gissa sida för sida).
        toc_cache = ebok.setdefault("toc_cache", {})
        toc_filer = [f for f in filer if any(_ar_toc(x) for x in cache.get(f, {}).get("sidor", []))]
        for f in toc_filer:
            if f in toc_cache:
                continue
            st["steg"] = "kapitel"
            try:
                parsed = _parse_json(
                    await _ai_las(hass, path / "filer" / f, TOC_PROMPT.format(titel=b["namn"]), "Skolan innehåll")
                )
                toc_cache[f] = [
                    {"titel": _txt(k.get("titel"), 120), "sida": _sidnr_int(k.get("sida"))}
                    for k in parsed.get("kapitel") or []
                    if isinstance(k, dict) and _txt(k.get("titel"), 120) and _sidnr_int(k.get("sida")) is not None
                ]
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("E-bok: kunde inte läsa innehållsförteckningen %s: %s", f, err)
            await hass.async_add_executor_job(_save_fil, ebok_path, ebok)
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                b = _find(_find(data.get("amnen", []), amne_id)["bocker"], bok_id)
            except ValueError:
                await hass.async_add_executor_job(lambda: ebok_path.unlink(missing_ok=True))
                klart = True
                return
            b["ebok"] = {
                "filer": [f for f in cache if not cache[f].get("fel")],
                "toc": bool([k for f in filer for k in toc_cache.get(f, [])]),
                "toc_kollad": True,
                "datum": dt_util.now().isoformat(timespec="minutes"),
            }
            await hass.async_add_executor_job(_save, path, data)
        klart = True
    except asyncio.CancelledError:
        raise  # Home Assistant stängs av: låt markeringen ligga kvar så bygget fortsätter efter omstart
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("E-bok misslyckades")
        st["fel"] = str(err)[:200]
        klart = True  # boken/ämnet finns inte längre eller annat bestående fel
    finally:
        st["kor"] = False
        if klart:
            await _markera_pagaende(hass, barn, amne_id, bok_id, False)


class EbokView(HomeAssistantView):
    """Gör om bokens foton till en e-bok (i bakgrunden) och hämta den."""

    url = "/api/skolan/ebok"
    name = "api:skolan:ebok"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        q = request.query
        barn = _barn_for(hass, request, q.get("barn"))
        st = dict(hass.data[DOMAIN]["jobb"].get((barn, q.get("bok")), {}))
        if q.get("bara_status"):
            return self.json({"jobb": st})
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)
        try:
            b = _find(_find(data.get("amnen", []), q.get("amne"))["bocker"], q.get("bok"))
        except ValueError as err:
            return self.json_message(str(err), 404)
        ebok = await hass.async_add_executor_job(_load_fil, path / "filer" / _ebok_fil(b["id"]))
        cache = ebok.get("cache", {})
        sidor = []
        for f in b.get("sidor", []):
            for i, sida in enumerate(cache.get(f, {}).get("sidor", [])):
                sidor.append({"fil": f, "del": i, **sida})
        fel = [f for f in b.get("sidor", []) if cache.get(f, {}).get("fel")]
        toc = [k for f in b.get("sidor", []) for k in ebok.get("toc_cache", {}).get(f, [])]
        return self.json({"jobb": st, "sidor": sidor, "fel": fel, "toc": toc})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        bok = body.get("bok")
        jobb = hass.data[DOMAIN]["jobb"]
        if jobb.get((barn, bok), {}).get("kor"):
            return self.json({"jobb": jobb[(barn, bok)]})
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        try:
            b = _find(_find(data.get("amnen", []), body.get("amne"))["bocker"], bok)
        except ValueError as err:
            return self.json_message(str(err), 404)
        if not b.get("sidor"):
            return self.json_message("Boken har inga sidor än.", 400)
        return self.json({"jobb": _starta_ebok(hass, barn, body.get("amne"), bok, bool(body.get("gor_om")))})


# ---------- utskrift ----------

MAX_UTSKRIFT = 60


def _valda(spec: str, n: int) -> list[int]:
    """'1-3, 5' -> [0, 1, 2, 4]. Tomt = alla."""
    spec = (spec or "").replace(" ", "")
    if not spec:
        return list(range(n))
    out: list[int] = []
    for part in spec.split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        try:
            lo, hi = int(a), int(b or a)
        except ValueError:
            continue
        for i in range(min(lo, hi), max(lo, hi) + 1):
            if 1 <= i <= n and i - 1 not in out:
                out.append(i - 1)
    return out


def _bild_data(f: Path) -> str:
    """Förminska fotot (om Pillow finns) och gör en data-URL."""
    raw = f.read_bytes()
    mime = mimetypes.guess_type(f.name)[0] or "image/jpeg"
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1700, 1700))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            raw, mime = buf.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001
        pass
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


class UtskriftView(HomeAssistantView):
    """En utskriftsvänlig sida med bokens foton, en per A4. Öppnas via en signerad länk."""

    url = "/api/skolan/utskrift"
    name = "api:skolan:utskrift"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        q = request.query
        barn = _barn_for(hass, request, q.get("barn"))
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)
        try:
            b = _find(_find(data.get("amnen", []), q.get("amne"))["bocker"], q.get("bok"))
        except ValueError:
            raise web.HTTPNotFound from None
        filer = []
        if q.get("fram") == "1" and b.get("framsida"):
            filer.append(b["framsida"])
        if q.get("sidor") != "ingen":
            filer += [b["sidor"][i] for i in _valda(q.get("sidor", ""), len(b["sidor"]))]
        if q.get("bak") == "1" and b.get("baksida"):
            filer.append(b["baksida"])
        if not filer:
            raise web.HTTPBadRequest(text="Inga sidor valda.")
        bilder = [f for f in filer if not f.lower().endswith(".pdf")][:MAX_UTSKRIFT]

        def _bygg() -> str:
            return "".join(
                f'<div class="sida"><img src="{_bild_data(path / "filer" / Path(f).name)}"></div>' for f in bilder
            )

        sidor_html = await hass.async_add_executor_job(_bygg)
        titel = html.escape(b["namn"])
        skippade = len(filer) - len(bilder)
        info = f"<p class='info'>{skippade} sidor (PDF eller fler än {MAX_UTSKRIFT}) kom inte med.</p>" if skippade else ""
        body = f"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{titel}</title>
<style>
@page {{ size: A4; margin: 8mm; }}
body {{ margin:0; font-family: sans-serif; background:#eee; }}
.bar {{ position:sticky; top:0; background:#fff; padding:12px; display:flex; gap:10px; align-items:center; box-shadow:0 1px 4px #0003; }}
.bar button {{ font-size:18px; padding:10px 18px; border-radius:10px; border:none; background:#03a9f4; color:#fff; }}
.sida {{ background:#fff; margin:12px auto; max-width:800px; text-align:center; }}
.sida img {{ max-width:100%; max-height:95vh; }}
.info {{ padding:0 12px; color:#a00; }}
@media print {{
  .bar, .info {{ display:none; }} body {{ background:#fff; }}
  .sida {{ margin:0; max-width:none; height:281mm; display:flex; align-items:center; justify-content:center; break-after:page; }}
  .sida:last-child {{ break-after:auto; }}
  .sida img {{ max-width:100%; max-height:281mm; object-fit:contain; }}
}}
</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ Skriv ut</button><span>{titel} · {len(bilder)} sidor</span></div>
{info}{sidor_html}
<script>window.addEventListener("load", () => setTimeout(() => window.print(), 400));</script>
</body></html>"""
        return web.Response(text=body, content_type="text/html", headers={"Cache-Control": "no-store"})


# ---------- förhör på distans ----------
# En förälder skickar ett förhör på ett glosset. Barnet svarar ett ord i taget utan hjälp,
# svaren rättas på servern, och föräldern får en notis med resultatet.


def _norm(s: str) -> str:
    s = re.sub(r"[.,!?;:\"'()¿¡]", "", str(s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _formel(s: str) -> str:
    """Formler jämförs utan mellanslag och gångertecken: "F = m · a" = "F=ma"."""
    s = str(s or "").lower().translate(str.maketrans({"²": "^2", "³": "^3", "−": "-", "÷": "/", ",": "."}))
    return re.sub(r"[\s·×*⋅]", "", s).rstrip(".")


def _ratt_svar(svar: str, facit: str, formel: bool = False) -> bool:
    if formel:
        return bool(_formel(svar)) and _formel(svar) in [_formel(x) for x in re.split(r";| eller ", facit or "")]
    alt = [_norm(x) for x in re.split(r"[/,;]| eller ", facit or "") if _norm(x)]
    return _norm(svar) in alt or _norm(svar) == _norm(facit)


def _ar_foralder(hass: HomeAssistant, request: web.Request) -> bool:
    return request["hass_user"].id in hass.data[DOMAIN]["conf"]["foraldrar"]


def _djur_bild(data: dict) -> tuple[str | None, dict]:
    """Bilden på barnets husdjur med rätt humör (för notiser och widget)."""
    d = meriter.djur(data) or {}
    if not d:
        return None, d
    slug = "-".join(f"{ord(c):x}" for c in d["art"] if c != "\ufe0f")
    return f"{STATIC_URL}/djur/{'agg' if d['steg'] == 0 else slug}_{d['humor']}.png", d


async def _notis(hass: HomeAssistant, tjanst: str | None, titel: str, text: str, url: str = "/skolan") -> None:
    if not tjanst:
        return
    extra: dict = {}
    b = next((x for x in hass.data[DOMAIN]["conf"]["barn"] if x.get("notify") == tjanst), None)
    if b:  # notiser till barnen får en bild på husdjuret med rätt min
        try:
            data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            bild, d = _djur_bild(data)
            if bild:
                extra["image"] = bild
                if d["steg"] and d["humor"] in ("hungrig", "ledsen") and d["namn"] not in text:
                    text += f"\n{'😟' if d['humor'] == 'hungrig' else '😢'} {d['namn']} är {'hungrig' if d['humor'] == 'hungrig' else 'ledsen'}, mata hen genom att göra något i Läxspelet!"
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Skolan: ingen husdjursbild: %s", err)
    try:
        await hass.services.async_call(
            "notify", tjanst, {"title": titel, "message": text, "data": {"url": url, "clickAction": url, **extra}}
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Skolan: kunde inte skicka notis via %s: %s", tjanst, err)


def _ut(data: dict, foralder: bool) -> dict:
    """Det som skickas till webbläsaren: inget facit till barnet under förhör, inga interna nycklar."""
    data = dict(data)
    data["forhor"] = [_publik_forhor(x, foralder) for x in data.get("forhor", [])]
    if not foralder:
        data["uppdrag"] = [
            {**u, "fragor": [{k: v for k, v in q.items() if k != "ratt"} for q in u.get("fragor", [])]}
            if u.get("fragor") and not u.get("klart")
            else u
            for u in data.get("uppdrag", [])
        ]
    if "meriter" in data:
        data["meriter"] = {k: v for k, v in data["meriter"].items() if k != "nycklar"}
    if not foralder:  # hejarop som inte har kommit fram än är en överraskning
        data["hejarop"] = dagens.hejarop_synliga(data)
    return data


def _publik_forhor(f: dict, foralder: bool) -> dict:
    """Barnet ser inte facit förrän förhöret är inlämnat."""
    if foralder or f.get("status") == "klart":
        return f
    # Diktamen: ordet läses upp från servern och skickas aldrig till barnets skärm.
    return {**f, "fragor": [{k: ("" if k == "fraga" and q.get("dikt") else v) for k, v in q.items() if k != "facit"} for q in f["fragor"]]}


GODKANT_GRANS = 0.8  # minst 80 % rätt för godkänt (föräldern kan ändra beslutet)


def _forslag(f: dict) -> str:
    n = len(f["fragor"])
    ratt = sum(1 for x in f["svar"] if x["ratt"])
    return "godkant" if n and ratt >= math.ceil(n * GODKANT_GRANS - 1e-9) else "ej_godkant"


def _stavord(g: dict) -> bool:
    """Samma språk på båda sidor (t.ex. svenska veckans ord): förhörs som diktamen."""
    if g.get("typ", "glosor") != "glosor":
        return False
    sp = [str(x or "").lower().strip() for x in g.get("sprak", [])] + ["", ""]
    par = g.get("par", [])
    return bool(sp[0] and sp[0] == sp[1]) or bool(par) and all(
        len(p) < 2 or not str(p[1]).strip() or str(p[0]).strip().lower() == str(p[1]).strip().lower() for p in par
    )


def _fragor(g: dict, riktning: int) -> list[dict]:
    if _stavord(g):
        sp = g["sprak"][0] or "Svenska"
        fragor = [{"fraga": p[0], "facit": p[0], "fran": sp, "till": sp, "dikt": True} for p in g["par"] if str(p[0]).strip()]
        random.shuffle(fragor)
        return fragor
    fragor = []
    for p in g["par"]:
        fran = riktning if riktning in (0, 1) else (0 if uuid.uuid4().int % 2 else 1)
        q = {"fraga": p[fran], "facit": p[1 - fran], "fran": g["sprak"][fran], "till": g["sprak"][1 - fran]}
        if g.get("typ") == "formler" and fran == 0:
            q["formel"] = True
        fragor.append(q)
    random.shuffle(fragor)
    return fragor


def _omprov(data: dict, f: dict) -> dict | None:
    """Ett nytt förhör på samma glosor när det förra inte blev godkänt."""
    if f.get("omprov_id") and any(x["id"] == f["omprov_id"] for x in data.get("forhor", [])):
        return None
    try:
        a = _find(data.get("amnen", []), f["amne"])
        g = _find(a["glosor"], f["glosor"])
    except ValueError:
        return None
    riktning = f.get("riktning")
    if riktning is None:
        fr = {q.get("fran") for q in f["fragor"]}
        riktning = 0 if fr == {g["sprak"][0]} else 1 if fr == {g["sprak"][1]} else 2
    ratt = sum(1 for x in f["svar"] if x["ratt"])
    ny = {
        "id": _new_id(), "amne": a["id"], "glosor": g["id"], "namn": g["namn"], "amne_namn": a["namn"],
        "meddelande": f"Nytt försök! Förra gången fick du {ratt} av {len(f['fragor'])} rätt. Du klarar det! 💪",
        "av_id": f.get("av_id", ""), "av_namn": f.get("av_namn", "Förälder"),
        "skapad": dt_util.now().isoformat(timespec="minutes"), "status": "skickat",
        "fragor": _fragor(g, riktning), "svar": [], "riktning": riktning, "omprov_av": f["id"],
    }
    data.setdefault("forhor", []).append(ny)
    f["omprov_id"] = ny["id"]
    return ny


class ForhorView(HomeAssistantView):
    url = "/api/skolan/forhor"
    name = "api:skolan:forhor"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        user = request["hass_user"]
        conf = hass.data[DOMAIN]["conf"]
        barn_conf = next(b for b in conf["barn"] if b["id"] == barn)
        path = _dir(hass, barn)
        op = body.get("op")
        notiser: list[tuple[str | None, str, str, str]] = []

        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            lista = data.setdefault("forhor", [])
            try:
                if op == "skapa":
                    if not foralder:
                        raise web.HTTPForbidden
                    a = _find(data.get("amnen", []), body.get("amne"))
                    g = _find(a["glosor"], body.get("glosor"))
                    riktning = int(body.get("riktning") or 0)
                    fragor = _fragor(g, riktning)
                    f = {
                        "id": _new_id(),
                        "amne": a["id"],
                        "glosor": g["id"],
                        "namn": g["namn"],
                        "amne_namn": a["namn"],
                        "meddelande": str(body.get("meddelande") or "").strip()[:200],
                        "av_id": user.id,
                        "av_namn": user.name,
                        "skapad": dt_util.now().isoformat(timespec="minutes"),
                        "status": "skickat",
                        "fragor": fragor,
                        "svar": [],
                        "riktning": riktning,
                    }
                    lista.append(f)
                    del lista[:-300]  # loggen sparar de 300 senaste
                    notiser.append(
                        (barn_conf.get("notify"), f"📋 Förhör från {user.name}", f"{g['namn']} ({a['namn']}), {len(fragor)} ord. Öppna Läxspelet för att börja.", "/skolan")
                    )
                else:
                    f = _find(lista, body.get("forhor"))
                    url = f"/skolan?barn={barn}&forhor={f['id']}"
                    if op == "starta":
                        if foralder:
                            raise web.HTTPForbidden
                        if f["status"] == "skickat":
                            f["status"] = "pagar"
                            f["startad"] = dt_util.now().isoformat(timespec="minutes")
                            notiser.append(
                                (
                                    conf["foralder_notify"].get(f["av_id"]),
                                    f"✏️ {barn_conf['namn']} har startat förhöret",
                                    f"{f['namn']}, {len(f['fragor'])} ord. Tryck här för att följa hur det går.",
                                    url,
                                )
                            )
                    elif op == "svara":
                        if foralder or f["status"] == "klart":
                            raise ValueError("Förhöret går inte att svara på.")
                        i = len(f["svar"])
                        if int(body.get("index", -1)) != i or i >= len(f["fragor"]):
                            raise ValueError("Fel fråga.")
                        svar = str(body.get("svar") or "").strip()[:100]
                        f["svar"].append({"svar": svar, "ratt": _ratt_svar(svar, f["fragor"][i]["facit"], bool(f["fragor"][i].get("formel")))})
                        f["senast"] = dt_util.now().isoformat(timespec="seconds")
                        if f["status"] == "skickat":
                            f["status"] = "pagar"
                            f["startad"] = dt_util.now().isoformat(timespec="minutes")
                        if len(f["svar"]) == len(f["fragor"]):
                            f["status"] = "klart"
                            f["klart"] = dt_util.now().isoformat(timespec="minutes")
                            ratt = sum(1 for x in f["svar"] if x["ratt"])
                            fel = [q["facit"] for q, x in zip(f["fragor"], f["svar"]) if not x["ratt"]]
                            text = f"{barn_conf['namn']} fick {ratt} av {len(f['fragor'])} rätt på {f['namn']}."
                            if fel:
                                text += " Fel på: " + ", ".join(fel[:8]) + ("…" if len(fel) > 8 else "")
                            f["forslag"] = f["bedomning"] = _forslag(f)
                            f["bedomd_av"] = ""
                            if f["bedomning"] == "godkant":
                                rubrik = "✅ Förhöret är godkänt"
                                text += " Tryck här om du vill ändra beslutet."
                            else:
                                rubrik = "❌ Förhöret är inte godkänt"
                                text += f" {barn_conf['namn']} har fått ett nytt förhör. Tryck här om du hellre vill godkänna."
                                _omprov(data, f)
                            notiser.append((conf["foralder_notify"].get(f["av_id"]), rubrik, text, url))
                            meriter.forhor_klart(data, f)
                            # Felstavade ord blir "svåra ord" att öva på.
                            try:
                                g = _find(_find(data.get("amnen", []), f["amne"])["glosor"], f["glosor"])
                                svara = g.setdefault("svara", {})
                                for q, x in zip(f["fragor"], f["svar"]):
                                    p = next((p for p in g["par"] if q["fraga"] in p and q["facit"] in p), None)
                                    if p:
                                        k = p[0].strip().lower()[:80]
                                        n = max(0, min(6, svara.get(k, 0) + (-1 if x["ratt"] else 2)))
                                        if n:
                                            svara[k] = n
                                        else:
                                            svara.pop(k, None)
                            except ValueError:
                                pass
                    elif op == "paminn":
                        if not foralder:
                            raise web.HTTPForbidden
                        if f["status"] == "klart":
                            raise ValueError("Förhöret är redan klart.")
                        f.setdefault("paminnelser", []).append({"tid": dt_util.now().isoformat(timespec="minutes"), "av": user.name})
                        f["paminnelser"] = f["paminnelser"][-30:]
                        n = len(f["paminnelser"])
                        notiser.append((
                            barn_conf.get("notify"),
                            f"🔔 Påminnelse{f' ({n})' if n > 1 else ''}: förhör väntar!",
                            f"{user.name} påminner: gör förhöret {f['namn']} ({len(f['fragor'])} ord) nu!"
                            if f["status"] == "skickat" else f"{user.name} påminner: gör klart förhöret {f['namn']}!",
                            url,
                        ))
                    elif op == "andra":
                        if not foralder:
                            raise web.HTTPForbidden
                        x = f["svar"][int(body.get("index"))]
                        x["ratt"] = not x["ratt"]
                        x["andrad"] = True
                        if f["status"] == "klart":
                            f["forslag"] = _forslag(f)
                    elif op == "bedom":
                        if not foralder:
                            raise web.HTTPForbidden
                        if f["status"] != "klart" or f.get("manuell"):
                            raise ValueError("Förhöret går inte att bedöma.")
                        beslut = body.get("bedomning")
                        if beslut not in ("godkant", "ej_godkant"):
                            raise ValueError("Okänt beslut.")
                        if beslut != f.get("bedomning"):
                            f["bedomning"] = beslut
                            f["bedomd_av"] = user.name
                            f["bedomd"] = dt_util.now().isoformat(timespec="minutes")
                            if beslut == "godkant":
                                om = next((x for x in lista if x["id"] == f.get("omprov_id")), None)
                                if om and om["status"] == "skickat":  # inte påbörjat: behövs inte längre
                                    lista.remove(om)
                                    f.pop("omprov_id", None)
                                notiser.append((barn_conf.get("notify"), "🎉 Förhöret är godkänt!", f"{user.name} har godkänt ditt förhör {f['namn']}. Bra jobbat!", url))
                            else:
                                ny = _omprov(data, f)
                                notiser.append((
                                    barn_conf.get("notify"), "📋 Nytt förhör",
                                    f"{user.name}: förhöret {f['namn']} blev inte godkänt. Gör ett nytt försök!",
                                    f"/skolan?barn={barn}&forhor={ny['id']}" if ny else url,
                                ))
                    elif op == "ta_bort":
                        if not foralder:
                            raise web.HTTPForbidden
                        lista.remove(f)
                    else:
                        raise ValueError("Okänd ändring.")
            except (ValueError, IndexError, TypeError) as err:
                return self.json_message(str(err) or "Fel.", 400)
            await hass.async_add_executor_job(_save, path, data)

        for tjanst, titel, text, url in notiser:
            await _notis(hass, tjanst, titel, text, url)
        return self.json({"data": _ut(data, foralder)})


# ---------- läsläxor och prov ----------
# Ett uppdrag = läs sidorna (tryckta sidnummer fran–till) i en bok före ett datum.
# E-boken mäter lästid per sida. När alla sidor är lästa (minst LAS_MIN_SEK var)
# ställer AI:n kontrollfrågor från sidornas sammanfattningar. Klarar barnet dem ges meriter.

LAS_MIN_SEK = 20  # längsta lästid som krävs för en sida (och för sidor där vi inte vet hur mycket text det är)
LAS_KORT_SEK = 6  # kortaste lästid, t.ex. en sida med bara en bild
LAS_ORD_PER_SEK = 2.5  # ungefär hur fort ett barn på mellanstadiet läser tyst

ORD_PROMPT = (
    "Du får ett foto eller en PDF med en eller flera sidor ur en skolbok. Skriv INTE av texten. "
    "Räkna bara ungefär hur många ord som finns att läsa på varje sida (brödtext, rubriker och bildtexter, inte sidnummer eller sidhuvud; 0 om sidan bara har bilder). "
    'Svara ENDAST med giltig JSON: {"sidor": [{"sidnummer": tryckt sidnummer som text eller null, "ord": heltal}]}, ett objekt per boksida i läsordning.'
)


def _ord_int(v) -> int | None:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 3000 else None


def _sid_sek(sida: dict) -> int:
    """Hur länge en sida måste vara öppen för att räknas som läst. Korta sidor går fortare."""
    ord_ = sida.get("ord")
    if ord_ is None:
        return LAS_MIN_SEK
    return max(LAS_KORT_SEK, min(LAS_MIN_SEK, math.ceil(ord_ / LAS_ORD_PER_SEK)))

FRAGE_PROMPT = (
    "Här är korta sammanfattningar av sidor som ett barn har läst i boken \"{bok}\" ({amne}). "
    "Gör {n} enkla kontrollfrågor på svenska som visar om barnet har läst och förstått, "
    "med 3 svarsalternativ var där exakt ett är rätt. Frågorna ska bara gå att svara på om man läst texten. "
    'Svara ENDAST med giltig JSON: {{"fragor": [{{"fraga": "...", "alternativ": ["...", "...", "..."], "ratt": index 0-2}}]}}.\n\n'
    "{text}"
)


def _sid_lista(path: Path, b: dict, fran: int, till: int) -> list[dict]:
    """E-bokens sidor (i bokens ordning) med tryckt sidnummer i intervallet."""
    ebok = _load_fil(path / "filer" / _ebok_fil(b["id"]))
    cache = ebok.get("cache", {})
    ut, senast = [], None
    for f in b.get("sidor", []):
        for i, sida in enumerate(cache.get(f, {}).get("sidor", [])):
            nr = _sidnr_int(sida.get("sidnr"))
            nr = nr if nr is not None else senast
            senast = nr
            if nr is not None and fran <= nr <= till:
                ut.append({"nyckel": f"{f}#{i}", "sidnr": sida.get("sidnr"), "sammanfattning": sida.get("sammanfattning"), "sek": _sid_sek(sida)})
    return ut


def _framsteg(data: dict, u: dict) -> None:
    las = data.get("lasning", {})
    lasta = sum(1 for x in u["sidor"] if las.get(u["bok"], {}).get(x["nyckel"], 0) >= x.get("sek", LAS_MIN_SEK)) if u.get("bok") else 0
    u["lasta"] = lasta
    u["allt_last"] = bool(u["sidor"]) and lasta == len(u["sidor"])


async def _rakna_ord(hass: HomeAssistant, barn: str) -> None:
    """Böcker inlästa innan AI:n räknade ord: räkna orden på sidorna i läxor som inte är klara, och korta lästiden."""
    korande = hass.data[DOMAIN].setdefault("ord_korande", set())
    if barn in korande:
        return
    korande.add(barn)
    try:
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)
        saknas: dict[str, set[str]] = {}
        for u in data.get("uppdrag", []):
            if u.get("klart") or not u.get("bok"):
                continue
            for x in u.get("sidor", []):
                if "sek" not in x:
                    saknas.setdefault(u["bok"], set()).add(x["nyckel"].rsplit("#", 1)[0])
        for bok_id, filer in saknas.items():
            ebok_path = path / "filer" / _ebok_fil(bok_id)
            for f in sorted(filer):
                ebok = await hass.async_add_executor_job(_load_fil, ebok_path)
                sidor = ebok.get("cache", {}).get(f, {}).get("sidor", [])
                if not sidor or all("ord" in s for s in sidor):
                    continue
                try:
                    svar = _parse_json(await _ai_las(hass, path / "filer" / f, ORD_PROMPT, "Skolan räkna ord")).get("sidor") or []
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("E-bok: kunde inte räkna ord i %s: %s", f, err)
                    await asyncio.sleep(10)
                    continue
                ebok = await hass.async_add_executor_job(_load_fil, ebok_path)
                sidor = ebok.get("cache", {}).get(f, {}).get("sidor", [])
                if len(svar) != len(sidor):
                    _LOGGER.info("E-bok: %s gav %s sidor i ordräkningen men har %s, hoppar över", f, len(svar), len(sidor))
                    for s in sidor:
                        s.setdefault("ord", None)
                else:
                    for s, x in zip(sidor, svar):
                        s["ord"] = _ord_int(x.get("ord")) if isinstance(x, dict) else None
                await hass.async_add_executor_job(_save_fil, ebok_path, ebok)
        if not saknas:
            return
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            for u in data.get("uppdrag", []):
                if u.get("klart") or u.get("bok") not in saknas:
                    continue
                ebok = await hass.async_add_executor_job(_load_fil, path / "filer" / _ebok_fil(u["bok"]))
                cache = ebok.get("cache", {})
                for x in u.get("sidor", []):
                    f, _, i = x["nyckel"].rpartition("#")
                    try:
                        x["sek"] = _sid_sek(cache[f]["sidor"][int(i)])
                    except (KeyError, IndexError, ValueError):
                        x["sek"] = LAS_MIN_SEK
                _framsteg(data, u)
            await hass.async_add_executor_job(_save, path, data)
        _LOGGER.info("E-bok: lästid per sida uppdaterad för %s", barn)
    finally:
        korande.discard(barn)


class UppdragView(HomeAssistantView):
    url = "/api/skolan/uppdrag"
    name = "api:skolan:uppdrag"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        user = request["hass_user"]
        conf = hass.data[DOMAIN]["conf"]
        barn_conf = next(b for b in conf["barn"] if b["id"] == barn)
        path = _dir(hass, barn)
        op = body.get("op")
        notiser = []
        ai_jobb = None
        be_om = None
        if op in ("veckoplan", "godkann") and not foralder:
            raise web.HTTPForbidden
        if op == "godkann":
            try:
                data = await _godkann(hass, barn, str(body.get("id")), body.get("datum"), bool(body.get("ok")))
            except ValueError as err:
                return self.json_message(str(err), 400)
            return self.json({"data": _ut(data, foralder)})
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            lista = data.setdefault("uppdrag", [])
            try:
                if op == "skapa":
                    typ = "prov" if body.get("typ") == "prov" else "las"
                    datum = str(body.get("datum") or "")
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
                        raise ValueError("Välj ett datum.")
                    a = _find(data.get("amnen", []), body.get("amne"))
                    sidor, bok_id = [], None
                    if body.get("bok"):
                        b = _find(a["bocker"], body.get("bok"))
                        bok_id = b["id"]
                        fran, till = int(body.get("fran")), int(body.get("till"))
                        if till < fran:
                            fran, till = till, fran
                        sidor = await hass.async_add_executor_job(_sid_lista, path, b, fran, till)
                        if not sidor:
                            raise ValueError("Hittade inga sidor med de sidnumren i e-boken. Har boken en e-bok?")
                    elif typ == "las":
                        raise ValueError("Välj en bok.")
                    glosor = [g["id"] for g in a["glosor"] if g["id"] in (body.get("glosor") or [])]
                    if not sidor and not glosor:
                        raise ValueError("Välj sidor eller glosor att plugga.")
                    u = {
                        "id": _new_id(),
                        "typ": typ,
                        "namn": _name(body.get("namn") or (f"{a['namn']}-prov" if typ == "prov" else "Läsläxa")),
                        "amne": a["id"],
                        "amne_namn": a["namn"],
                        "bok": bok_id,
                        "fran": body.get("fran"),
                        "till": body.get("till"),
                        "kapitel": str(body.get("kapitel") or "")[:200],
                        "sidor": sidor,
                        "glosor": glosor,
                        "datum": datum,
                        "skapad": dt_util.now().isoformat(timespec="minutes"),
                        "av_id": user.id,
                        "av_namn": user.name,
                    }
                    _framsteg(data, u)
                    lista.append(u)
                    del lista[:-200]
                    if not foralder:
                        meriter.registrerat(data, u)
                    for g_id in glosor:  # provdatum blir förhörsdatum på glosorna om de saknar ett
                        g = _find(a["glosor"], g_id)
                        if not g.get("forhor"):
                            g["forhor"] = datum
                elif op == "veckoplan":
                    await hass.async_add_executor_job(_veckoplan, path, data, body, user)
                elif op == "ova_papper":  # barnet har övat glosor på papper, en förälder godkänner
                    if foralder:
                        raise ValueError("Använd raden Övat på papper.")
                    g = _find(_find(data.get("amnen", []), body.get("amne"))["glosor"], body.get("glosor"))
                    dag = dt_util.now().date().isoformat()
                    vantar = g.setdefault("papper_vantar", [])
                    if dag in g.get("ovat_dagar", []) or dag in vantar:
                        raise ValueError("Idag är redan registrerad.")
                    vantar.append(dag)
                    be_om = ({"typ": "glosor", "id": f"glosor-{g['id']}", "namn": g["namn"]}, dag)
                else:
                    u = _find(lista, body.get("id"))
                    if op == "ta_bort":
                        if not foralder and u["av_id"] != user.id:
                            raise web.HTTPForbidden
                        lista.remove(u)
                        if not foralder:
                            meriter.kista_ta_bort(data, f"kista:{u['id']}")
                    elif op == "las_tid":
                        if foralder:
                            return self.json({"ok": True})  # föräldrars läsning räknas inte
                        nyckel = str(body.get("nyckel") or "")
                        if any(x["nyckel"] == nyckel for x in u["sidor"]):
                            bok = data.setdefault("lasning", {}).setdefault(u["bok"], {})
                            bok[nyckel] = min(1800, bok.get(nyckel, 0) + max(0, min(180, int(body.get("sek") or 0))))
                            _framsteg(data, u)
                            if u["typ"] == "prov" and not u.get("klart"):
                                meriter.prov_studiedag(data, u)
                    elif op == "prov_resultat":
                        if not foralder:
                            raise web.HTTPForbidden
                        if u["typ"] != "prov":
                            raise ValueError("Det här är inget prov.")
                        if body.get("rensa"):
                            meriter.prov_resultat(data, u, None)
                        else:
                            betyg = str(body.get("betyg") or "").strip().upper()
                            res = {"kommentar": str(body.get("kommentar") or "").strip()[:200],
                                   "av": user.name, "tid": dt_util.now().isoformat(timespec="minutes")}
                            if body.get("max") not in (None, ""):
                                mx, po = float(body.get("max")), float(body.get("poang") or 0)
                                if mx <= 0 or po < 0 or po > mx or mx > 10000:
                                    raise ValueError("Poängen måste vara mellan 0 och maxpoängen.")
                                res.update({"poang": po, "max": mx})
                                visa = f"{po:g} av {mx:g} poäng"
                            elif betyg in meriter.PROV_BETYG:
                                res["betyg"] = betyg
                                visa = f"betyg {betyg}"
                            else:
                                raise ValueError("Skriv in poäng och maxpoäng, eller välj ett betyg.")
                            ny = "resultat" not in u
                            diff = meriter.prov_resultat(data, u, res)
                            if ny or diff:
                                belon = f" Du får +{diff} ⭐!" if diff > 0 else ""
                                notiser.append((
                                    barn_conf.get("notify"), f"📝 Provresultat: {u['namn']}",
                                    f"{user.name} har lagt in ditt resultat: {visa}.{belon}",
                                ))
                    elif op == "hogl_klar":
                        if u["typ"] != "hogl":
                            raise ValueError("Det här är ingen högläsning.")
                        idag = dt_util.now().date().isoformat()
                        dag = str(body.get("datum") or idag) if foralder else idag
                        d = next((x for x in u.get("dagar", []) if x["datum"] == dag), None)
                        if not d:
                            raise ValueError("Idag är ingen läsdag." if not foralder else "Okänd dag.")
                        if foralder:  # förälder bockar av direkt
                            _godkann_i(data, u, dag, True)
                        elif d.get("status") not in ("ok", "vantar"):
                            d["status"] = "vantar"
                            d["tid"] = dt_util.now().isoformat(timespec="minutes")
                            be_om = (u, dag)
                            meriter.kolla_utmaning(data)
                    elif op == "skriv_klar":
                        if u["typ"] != "skriv" or u.get("klart"):
                            raise ValueError("Den är redan klar.")
                        if foralder:
                            _godkann_i(data, u, None, True)
                        elif not u.get("vantar"):
                            u["vantar"] = dt_util.now().isoformat(timespec="minutes")
                            be_om = (u, None)
                    elif op == "fragor":
                        if not u.get("allt_last"):
                            raise ValueError("Läs alla sidor först.")
                        if not u.get("fragor") and not u.get("klart"):
                            ai_jobb = u
                    elif op == "svara":
                        if foralder or u.get("klart") or not u.get("fragor"):
                            raise ValueError("Inga frågor att svara på.")
                        svar = body.get("svar") or []
                        ratt = sum(1 for q, x in zip(u["fragor"], svar) if q["ratt"] == x)
                        u.setdefault("forsok", []).append({"tid": dt_util.now().isoformat(timespec="minutes"), "ratt": ratt, "av": len(u["fragor"])})
                        if ratt * 3 >= len(u["fragor"]) * 2:
                            u["klart"] = dt_util.now().isoformat(timespec="minutes")
                            meriter.uppdrag_klart(data, u)
                            notiser.append(
                                (conf["foralder_notify"].get(u["av_id"]), f"📖 {barn_conf['namn']} är klar",
                                 f"{u['namn']}: alla sidor lästa och {ratt} av {len(u['fragor'])} rätt på kontrollfrågorna.")
                            )
                        else:
                            u["fragor"] = []  # nya frågor nästa gång
                    else:
                        raise ValueError("Okänd ändring.")
            except (ValueError, TypeError) as err:
                return self.json_message(str(err) or "Fel.", 400)
            await hass.async_add_executor_job(_save, path, data)

        if op != "las_tid" and any(not u.get("klart") and u.get("bok") and any("sek" not in x for x in u.get("sidor", [])) for u in data.get("uppdrag", [])):
            hass.async_create_background_task(_rakna_ord(hass, barn), f"skolan_ord_{barn}")

        if ai_jobb is not None:
            fragor = await self._gor_fragor(hass, data, ai_jobb)
            async with hass.data[DOMAIN]["locks"][barn]:
                data = await hass.async_add_executor_job(_load, path)
                u = _find(data.get("uppdrag", []), ai_jobb["id"])
                if fragor:
                    u["fragor"] = fragor
                else:  # AI:n gick inte att nå: lästiden får räcka
                    u["klart"] = dt_util.now().isoformat(timespec="minutes")
                    u["utan_fragor"] = True
                    meriter.uppdrag_klart(data, u)
                await hass.async_add_executor_job(_save, path, data)
        for n in notiser:
            await _notis(hass, *n)
        if be_om:
            await _be_om_godkannande(hass, barn, *be_om)
        return self.json({"data": _ut(data, foralder)})

    async def _gor_fragor(self, hass: HomeAssistant, data: dict, u: dict) -> list[dict]:
        text = "\n".join(f"Sida {x.get('sidnr') or '?'}: {x['sammanfattning']}" for x in u["sidor"] if x.get("sammanfattning"))
        if not text:
            return []
        try:
            b = _find(_find(data["amnen"], u["amne"])["bocker"], u["bok"])
            conf = hass.data[DOMAIN]["conf"]
            entity = conf.get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
            n = 3 if len(u["sidor"]) < 15 else 4
            for forsok in range(3):
                try:
                    resp = await hass.services.async_call(
                        "ai_task", "generate_data",
                        {"task_name": "Skolan kontrollfrågor", "entity_id": entity,
                         "instructions": FRAGE_PROMPT.format(bok=b["namn"], amne=u["amne_namn"], n=n, text=text[:12000])},
                        blocking=True, return_response=True,
                    )
                    break
                except Exception:  # noqa: BLE001
                    if forsok == 2:
                        raise
                    await asyncio.sleep(10)
            raw = (resp or {}).get("data")
            parsed = _parse_json(raw if isinstance(raw, str) else json.dumps(raw))
            ut = []
            for q in parsed.get("fragor") or []:
                alt = [str(x)[:150] for x in (q.get("alternativ") or [])][:4]
                r = int(q.get("ratt", -1))
                if q.get("fraga") and len(alt) >= 2 and 0 <= r < len(alt):
                    # blanda så att rätt svar inte alltid är på samma plats
                    ordning = list(range(len(alt)))
                    random.shuffle(ordning)
                    ut.append({"fraga": str(q["fraga"])[:200], "alternativ": [alt[i] for i in ordning], "ratt": ordning.index(r)})
            return ut[:5]
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Skolan: kunde inte göra kontrollfrågor: %s", err)
            return []


# ---------- veckobrev: högläsning, läxbok och veckans ord ----------

VECKOBREV_PROMPT = (
    "Du läser ett veckobrev från skolan om läxor för ett barn i Sverige. "
    "Ta fram veckans läxor. Svara ENDAST med giltig JSON utan markdown, på formen "
    '{"kapitel": kapitelnummer som heltal eller null, "kapitel_namn": kapitlets namn om det står, annars null, '
    '"las_dagar": [veckodagar 0=måndag..4=fredag då läsläxan ska läsas], '
    '"hoglasning": true om läsningen görs högt/för en vuxen, annars false, '
    '"skriv_dag": veckodag 0–6 då uppgifterna i läxboken/skrivläxan ska lämnas in, eller null, '
    '"ord": [veckans ord/glosor exakt som de står], '
    '"diktamen_dag": veckodag 0–6 för diktamen/förhör på orden, eller null, '
    '"regler": [korta regler/instruktioner ur brevet, med egna ord], "note": kort kommentar eller ""}. '
    '"Varje vardag" betyder [0,1,2,3,4]. Hitta inte på något som inte står i brevet.'
)

VECKODAG = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


def _kap_nr(namn: str) -> tuple[int | None, str]:
    m = re.match(r"^\s*(\d+)\s*[.:)]\s*(.*)$", namn or "")
    return (int(m.group(1)), m.group(2).strip()) if m else (None, (namn or "").strip())


def _kapitel_lista(path: Path, b: dict) -> list[dict]:
    """Kapitlen i en e-bok med sidintervall: [{nr, namn, fran, till, nyckel}]."""
    cache = _load_fil(path / "filer" / _ebok_fil(b["id"])).get("cache", {})
    kap, sista = [], 0
    for f in b.get("sidor", []):
        for i, sida in enumerate(cache.get(f, {}).get("sidor", [])):
            nr = _sidnr_int(sida.get("sidnr"))
            if nr is not None:
                sista = max(sista, nr)
            if not sida.get("kapitel") or nr is None:
                continue  # utan sidnummer (t.ex. bild på halv sida) går det inte att räkna sidor
            knr, namn = _kap_nr(str(sida["kapitel"]))
            if kap and ((knr is not None and kap[-1]["nr"] == knr) or kap[-1]["namn"].lower() == namn.lower()):
                continue
            kap.append({"nr": knr, "namn": namn, "fran": nr, "nyckel": f"{f}#{i}"})
    for k, nasta in zip(kap, kap[1:] + [None]):
        k["till"] = max(k["fran"], (nasta["fran"] - 1) if nasta else sista)
    return kap


def _liknar(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _hitta_amne(amnen: list, *ord_: str) -> dict | None:
    for o in ord_:
        a = next((x for x in amnen if o in x["namn"].lower()), None)
        if a:
            return a
    return None


def _forslag_veckobrev(path: Path, data: dict, ai: dict) -> dict:
    """Gör om AI:ns svar till ett förslag med ämnen, böcker, sidor och datum."""
    idag = dt_util.now().date()
    mandag = idag - timedelta(days=idag.weekday())
    if idag.weekday() >= 5:  # helg: brevet gäller veckan som kommer
        mandag += timedelta(days=7)

    def dag(n):
        try:
            return (mandag + timedelta(days=int(n) % 7)).isoformat()
        except (TypeError, ValueError):
            return None

    amnen = data.get("amnen", [])
    a_las = _hitta_amne(amnen, "läsläx", "läs")
    a_skriv = _hitta_amne(amnen, "skriv", "läxbok")
    a_ord = _hitta_amne(amnen, "ord", "glos")
    kapitel = {}
    for a in (a_las, a_skriv):
        for b in (a or {}).get("bocker", []):
            if b.get("ebok"):
                kapitel[b["id"]] = _kapitel_lista(path, b)
    knr = ai.get("kapitel")
    knr = int(knr) if isinstance(knr, (int, float)) or str(knr or "").isdigit() else None
    knamn = str(ai.get("kapitel_namn") or "")

    def valj(a):
        """Bästa bok och kapitel i ämnet: först på nummer, sedan på namn."""
        bast = (0.0, None, None)
        for b in (a or {}).get("bocker", []):
            for k in kapitel.get(b["id"], []):
                p = 1.0 if knr is not None and k["nr"] == knr else (_liknar(k["namn"], knamn) if knamn else 0)
                if p > bast[0]:
                    bast = (p, b, k)
        return bast

    p_skriv, b_skriv, k_skriv = valj(a_skriv)
    if k_skriv and not knamn:
        knamn = k_skriv["namn"]  # läxboken har kapitelnumren, läsboken bara namnen
    p_las, b_las, k_las = valj(a_las)
    if p_las < 0.6:
        b_las = b_las if p_las else next((b for b in (a_las or {}).get("bocker", []) if b.get("ebok")), None)
        k_las = None
    if p_skriv < 0.6:
        k_skriv = None
    las_dagar = sorted({int(x) for x in (ai.get("las_dagar") or []) if str(x).lstrip("-").isdigit() and 0 <= int(x) <= 6})
    ord_lista = [str(x).strip()[:170] for x in (ai.get("ord") or []) if str(x).strip()][:100]
    diktamen = dag(ai["diktamen_dag"]) if ai.get("diktamen_dag") is not None else None
    g_finns = next((g for g in (a_ord or {}).get("glosor", []) if diktamen and g.get("forhor") == diktamen), None)
    titel = f"Kapitel {knr}" if knr else (knamn or "Veckans läsläxa")
    return {
        "mandag": mandag.isoformat(),
        "regler": [str(x)[:200] for x in (ai.get("regler") or [])][:8],
        "note": str(ai.get("note") or "")[:300],
        "kapitel": {bid: [{k: v for k, v in x.items() if k != "nyckel"} for x in lista] for bid, lista in kapitel.items()},
        "las": {
            "amne": (a_las or {}).get("id"), "bok": (b_las or {}).get("id"),
            "namn": f"{titel}{' – högläsning' if ai.get('hoglasning') else ''}"[:MAX_NAME],
            "kapitel": (k_las or {}).get("namn") or knamn, "fran": (k_las or {}).get("fran"), "till": (k_las or {}).get("till"),
            "dagar": [dag(x) for x in las_dagar], "hogl": bool(ai.get("hoglasning", True)),
        } if las_dagar else None,
        "skriv": {
            "amne": (a_skriv or {}).get("id"), "bok": (b_skriv or {}).get("id"),
            "namn": f"Läxboken {titel.lower()}"[:MAX_NAME],
            "kapitel": (k_skriv or {}).get("namn") or knamn, "fran": (k_skriv or {}).get("fran"), "till": (k_skriv or {}).get("till"),
            "datum": dag(ai["skriv_dag"]),
        } if ai.get("skriv_dag") is not None else None,
        "ord": {
            "amne": (a_ord or {}).get("id"), "glosor": (g_finns or {}).get("id"),
            "befintliga": [p[0] for p in (g_finns or {}).get("par", [])],
            "namn": (g_finns or {}).get("namn") or f"Veckans ord v.{(mandag.isocalendar()[1])}",
            "ord": ord_lista, "forhor": diktamen, "sprak": ai.get("glosor_sprak"),
        } if ord_lista else None,
    }


LEKTION_PROMPT = (
    "Det här är ett foto av en elevs lektionsschema (skolschema för en vecka). Läs av alla lektioner måndag till fredag. "
    'Svara ENDAST med giltig JSON: {"lektioner": [{"dag": 0 för måndag, 1 tisdag, 2 onsdag, 3 torsdag, 4 fredag, '
    '"start": "HH:MM", "slut": "HH:MM", "amne": ämnets namn, "sal": sal/klassrum eller "", "larare": lärarens namn eller förkortning eller "", '
    '"info": annan kort text i rutan (t.ex. grupp, "jämn vecka", "ta med ombyte") eller ""}], "amnen": [varje skolämne i schemat en gång]}. '
    "Skriv ämnena med vanliga svenska namn och stor första bokstav, och skriv ut förkortningar "
    "(t.ex. Ma = Matte, Sv = Svenska, En = Engelska, Idh = Idrott, Tk = Teknik, Hkk = Hemkunskap, Mu = Musik, Sl = Slöjd, "
    "Bi = Biologi, Fy = Fysik, Ke = Kemi, Ge = Geografi, Hi = Historia, Re = Religion, Sh = Samhällskunskap, Mod = Moderna språk). "
    "Står ett språk (Spanska, Tyska, Franska) så använd det. "
    "Har en ruta två eller fler ämnen samtidigt (delad tid, t.ex. Spanska/Tyska eller Slöjd/Hemkunskap i olika grupper), "
    "lägg in VARJE ämne som en egen lektion med samma dag och tid, och skriv gruppen i info om den står. Ta INTE med rast, lunch, mentorstid, klassråd, fritids eller studietid. "
    'Saknas en tid, skriv "". Hittar du inget schema: {"lektioner": [], "amnen": []}.'
)


def _amne_match(amnen: list, namn: str) -> dict | None:
    """Hitta ett befintligt ämne som är samma som ett ämne från schemat (Matte = Matematik = matte)."""
    n = _norm(namn)
    lika = {"matematik": "matte", "idrott och hälsa": "idrott", "hemkunskap": "hkk", "samhällskunskap": "samhälle"}
    n = lika.get(n, n)
    for a in amnen:
        x = lika.get(_norm(a["namn"]), _norm(a["namn"]))
        if x == n or (len(n) >= 4 and len(x) >= 4 and (x.startswith(n) or n.startswith(x))) or _liknar(x, n) >= 0.85:
            return a
    return None


def _lektion_forslag(data: dict, ai: dict) -> dict:
    lektioner = []
    for x in ai.get("lektioner") or []:
        if not isinstance(x, dict):
            continue
        try:
            dag = int(x.get("dag"))
        except (TypeError, ValueError):
            continue
        namn = str(x.get("amne") or "").strip()[:MAX_NAME]
        if not 0 <= dag <= 4 or not namn:
            continue
        tid = lambda v: v if re.fullmatch(r"\d{1,2}[:.]\d{2}", str(v or "").strip()) else ""
        lektioner.append({"dag": dag, "start": tid(x.get("start")).replace(".", ":").zfill(5) if tid(x.get("start")) else "",
                          "slut": tid(x.get("slut")).replace(".", ":").zfill(5) if tid(x.get("slut")) else "", "namn": namn,
                          "sal": str(x.get("sal") or "").strip()[:20], "larare": str(x.get("larare") or "").strip()[:40], "info": str(x.get("info") or "").strip()[:80]})
    lektioner.sort(key=lambda x: (x["dag"], x["start"]))
    namn = list(dict.fromkeys([str(a).strip()[:MAX_NAME] for a in (ai.get("amnen") or []) if str(a).strip()] + [x["namn"] for x in lektioner]))
    amnen = data.get("amnen", [])
    ut = []
    for n in namn:
        if any(_norm(n) == _norm(y["namn"]) for y in ut):
            continue
        a = _amne_match(amnen, n)
        ut.append({"namn": n, "amne": a["id"] if a else None, "amne_namn": a["namn"] if a else None})
    return {"lektioner": lektioner, "amnen": ut}


def _lektioner_spara(data: dict, body: dict) -> None:
    amnen = data.setdefault("amnen", [])
    for n in (body.get("skapa") or [])[:20]:
        namn = _name(n)
        if not _amne_match(amnen, namn):
            amnen.append({"id": _new_id(), "namn": namn, "farg": FARGER[len(amnen) % len(FARGER)], "bocker": [], "glosor": [], "delar": ["bocker", "glosor"]})
    ut = []
    for x in (body.get("lektioner") or [])[:80]:
        if not isinstance(x, dict):
            continue
        dag = int(x.get("dag") or 0)
        namn = str(x.get("namn") or "").strip()[:MAX_NAME]
        if not 0 <= dag <= 4 or not namn:
            continue
        a = _amne_match(amnen, namn)
        tid = lambda v: str(v or "").strip().replace(".", ":").zfill(5)[:5] if re.fullmatch(r"\d{1,2}[:.]\d{2}", str(v or "").strip()) else ""
        ut.append({"dag": dag, "start": tid(x.get("start")), "slut": tid(x.get("slut")), "namn": a["namn"] if a else namn,
                   "amne": a["id"] if a else None, "sal": str(x.get("sal") or "").strip()[:20], "larare": str(x.get("larare") or "").strip()[:40],
                   "info": str(x.get("info") or "").strip()[:80]})
    data["lektioner"] = sorted(ut, key=lambda x: (x["dag"], x["start"]))


class SchemaSidaView(HomeAssistantView):
    """Den digitala kopian av schemat som egen sida: sök och skriv ut. Öppnas via en signerad länk."""

    url = "/api/skolan/schema_sida"
    name = "api:skolan:schema_sida"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        namn = next(b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn)
        farger = {a["namn"].lower(): a.get("farg") for a in data.get("amnen", [])}
        sida = schemavy.sida(f"{namn}s schema", data.get("lektioner", []), farger, hem=f"/skolan?barn={barn}")
        return web.Response(text=sida, content_type="text/html", headers={"Cache-Control": "no-store"})


class LektionView(HomeAssistantView):
    """Barnet (eller en förälder) fotar lektionsschemat. AI:n läser lektioner och ämnen. Inget sparas här."""

    url = "/api/skolan/lektionsschema"
    name = "api:skolan:lektionsschema"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):  # bara föräldrar (och läraren via inkorgen) ändrar schemat
            raise web.HTTPForbidden
        form = await request.post()
        barn = _barn_for(hass, request, form.get("barn"))
        field = form.get("file")
        if field is None or not hasattr(field, "file"):
            return self.json_message("Ingen bild skickades.", 400)
        mime = _mime(field)
        if not _ok_file(mime):
            return self.json_message("Bara bilder och PDF:er.", 400)
        content = await hass.async_add_executor_job(field.file.read)
        if len(content) > MAX_BYTES:
            return self.json_message("Filen är för stor (max 20 MB).", 400)
        ext = (Path(field.filename or "").suffix or mimetypes.guess_extension(mime) or ".jpg").lower()[:6]
        src = hass.data[DOMAIN]["base"] / f".schema_{uuid.uuid4().hex}{ext}"
        await hass.async_add_executor_job(src.write_bytes, content)
        try:
            for forsok in range(3):
                try:
                    text = await _ai_las(hass, src, LEKTION_PROMPT, "Läs lektionsschema")
                    break
                except Exception as err:  # noqa: BLE001
                    if forsok == 2:
                        _LOGGER.warning("Schemat kunde inte läsas: %s", err)
                        return self.json_message(f"AI:n kunde inte läsa schemat: {err}", 502)
                    await asyncio.sleep(5)
        finally:
            await hass.async_add_executor_job(lambda: src.unlink(missing_ok=True))
        try:
            ai = _parse_json(text)
        except (ValueError, json.JSONDecodeError):
            return self.json_message("AI:n svarade inte i rätt format. Försök igen.", 502)
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        forslag = _lektion_forslag(data, ai if isinstance(ai, dict) else {})
        if not forslag["lektioner"] and not forslag["amnen"]:
            return self.json_message("AI:n hittade inget schema på bilden. Fota hela schemat rakt framifrån.", 422)
        return self.json(forslag)


class VeckobrevView(HomeAssistantView):
    """Förälder fotar veckobrevet. AI:n läser det och servern gör ett förslag. Inget sparas här."""

    url = "/api/skolan/veckobrev"
    name = "api:skolan:veckobrev"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden
        form = await request.post()
        barn = _barn_for(hass, request, form.get("barn"))
        field = form.get("file")
        if field is None or not hasattr(field, "file"):
            return self.json_message("Ingen fil skickades.", 400)
        mime = _mime(field)
        if not _ok_file(mime):
            return self.json_message("Bara bilder och PDF:er.", 400)
        content = await hass.async_add_executor_job(field.file.read)
        if len(content) > MAX_BYTES:
            return self.json_message("Filen är för stor (max 20 MB).", 400)
        ext = (Path(field.filename or "").suffix or mimetypes.guess_extension(mime) or ".jpg").lower()[:6]
        src = hass.data[DOMAIN]["base"] / f".veckobrev_{uuid.uuid4().hex}{ext}"
        await hass.async_add_executor_job(src.write_bytes, content)
        try:
            for forsok in range(3):
                try:
                    text = await _ai_las(hass, src, VECKOBREV_PROMPT, "Läs veckobrev")
                    break
                except Exception as err:  # noqa: BLE001
                    if forsok == 2:
                        _LOGGER.warning("Veckobrev kunde inte läsas: %s", err)
                        return self.json_message(f"AI:n kunde inte läsa brevet: {err}", 502)
                    await asyncio.sleep(5)
        finally:
            await hass.async_add_executor_job(lambda: src.unlink(missing_ok=True))
        try:
            ai = _parse_json(text)
        except (ValueError, json.JSONDecodeError):
            return self.json_message("AI:n svarade inte i rätt format. Försök igen.", 502)
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        forslag = await hass.async_add_executor_job(_forslag_veckobrev, _dir(hass, barn), data, ai)
        return self.json(forslag)


def _veckoplan(path: Path, data: dict, body: dict, user) -> list[str]:
    """Spara veckobrevets läxor. Returnerar vad som skapades."""
    amnen = data.get("amnen", [])
    lista = data.setdefault("uppdrag", [])
    nu = dt_util.now().isoformat(timespec="minutes")
    skapat, hogl_id = [], None

    def datum(v):
        v = str(v or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("Ogiltigt datum.")
        return v

    def bok_sidor(x, a):
        if not x.get("bok"):
            return None, []
        b = _find(a["bocker"], x["bok"])
        try:
            fran, till = int(x.get("fran")), int(x.get("till"))
        except (TypeError, ValueError):
            return b["id"], []
        return b["id"], _sid_lista(path, b, min(fran, till), max(fran, till))

    las = body.get("las")
    if las:
        a = _find(amnen, las.get("amne"))
        dagar = sorted({datum(d) for d in (las.get("dagar") or [])})
        if not dagar:
            raise ValueError("Välj minst en dag för läsläxan.")
        bok_id, sidor = bok_sidor(las, a)
        u = {
            "id": _new_id(), "typ": "hogl" if las.get("hogl", True) else "las",
            "namn": _name(las.get("namn") or "Läsläxa"), "amne": a["id"], "amne_namn": a["namn"],
            "bok": bok_id, "fran": las.get("fran"), "till": las.get("till"), "kapitel": str(las.get("kapitel") or "")[:200],
            "sidor": sidor, "glosor": [], "datum": dagar[-1], "skapad": nu, "av_id": user.id, "av_namn": user.name,
        }
        if u["typ"] == "hogl":
            u["dagar"] = [{"datum": d, "status": None} for d in dagar]
        elif not sidor:
            raise ValueError("Läsläxan behöver sidor i e-boken (eller välj högläsning).")
        _framsteg(data, u)
        lista.append(u)
        hogl_id = u["id"]
        skapat.append(f"📖 {u['namn']}")
    skriv = body.get("skriv")
    if skriv:
        a = _find(amnen, skriv.get("amne"))
        bok_id, sidor = bok_sidor(skriv, a)
        u = {
            "id": _new_id(), "typ": "skriv", "namn": _name(skriv.get("namn") or "Läxboken"),
            "amne": a["id"], "amne_namn": a["namn"], "bok": bok_id, "fran": skriv.get("fran"), "till": skriv.get("till"),
            "kapitel": str(skriv.get("kapitel") or "")[:200], "sidor": sidor, "glosor": [], "datum": datum(skriv.get("datum")),
            "kopplad": hogl_id, "skapad": nu, "av_id": user.id, "av_namn": user.name,
        }
        _framsteg(data, u)
        lista.append(u)
        skapat.append(f"✍️ {u['namn']}")
    ord_ = body.get("ord")
    if ord_:
        a = _find(amnen, ord_.get("amne"))
        rader = [str(o).strip() for o in (ord_.get("ord") or []) if str(o).strip()][:100]
        sprak = ["Svenska", "Svenska"]
        if rader and all(" = " in x for x in rader):  # glosor med översättning (t.ex. från lärarens veckobrev)
            par = [[a_.strip()[:80], b_.strip()[:80]] for a_, b_ in (x.split(" = ", 1) for x in rader)]
            sp = ord_.get("sprak") if isinstance(ord_.get("sprak"), list) and len(ord_["sprak"]) == 2 else ["Svenska", "Engelska"]
            sprak = [str(sp[0])[:20] or "Svenska", str(sp[1])[:20] or "Engelska"]
        else:
            par = [[x[:80], ""] for x in rader]
        if not par:
            raise ValueError("Veckans ord är tomma.")
        forhor = datum(ord_["forhor"]) if ord_.get("forhor") else None
        if ord_.get("glosor"):
            g = _find(a["glosor"], ord_["glosor"])
            g.update({"par": par, "forhor": forhor or g.get("forhor"), "sprak": sprak})
        else:
            g = {"id": _new_id(), "namn": _name(ord_.get("namn") or "Veckans ord"), "sprak": sprak,
                 "par": par, "forhor": forhor, "skapad": dt_util.now().date().isoformat()}
            a["glosor"].append(g)
        skapat.append(f"📝 {g['namn']} ({len(par)} ord)")
    del lista[:-200]
    return skapat


def _godkann_glosor(data: dict, gid: str, datum: str | None, ok: bool) -> str | None:
    """Förälder godkänner eller nekar glosövning på papper en viss dag."""
    g = next((g for a in data.get("amnen", []) for g in a.get("glosor", []) if g["id"] == gid), None)
    if not g or datum not in g.get("papper_vantar", []):
        return None
    g["papper_vantar"].remove(datum)
    if not ok:
        return f"🙈 Övningen på papper ({g['namn']}) blev inte godkänd. Öva och visa mamma eller pappa."
    if datum not in g.get("ovat_dagar", []):
        meriter.ovat(data, g, 0, 0, datum)
    return f"👍 Övningen på papper ({g['namn']}) är godkänd!"


def _godkann_bok(data: dict, bok_id: str, ok: bool) -> str | None:
    """Förälder har kollat barnets bokfoton."""
    b = next((b for a in data.get("amnen", []) for b in a.get("bocker", []) if b["id"] == bok_id), None)
    if not b or not b.get("foto_vantar"):
        return None
    b.pop("foto_vantar")
    if ok:
        p = meriter.foto_lon(data, b)
        return f"📸 Fotona i {b['namn']} är godkända! +{p} ⭐"
    return f"📸 Fotona i {b['namn']} blev inte godkända än. Kolla att alla sidor är skarpa och i rätt ordning, och fråga igen."


def _godkann_i(data: dict, u: dict, datum: str | None, ok: bool) -> str | None:
    """Förälder godkänner eller nekar högläsning (en dag) eller läxboken. Returnerar notis till barnet."""
    if u["typ"] == "hogl":
        d = next((x for x in u.get("dagar", []) if x["datum"] == datum), None)
        if not d:
            raise ValueError("Okänd dag.")
        if d.get("status") == "ok":
            return None
        if ok:
            d["status"] = "ok"
            d["godkand"] = dt_util.now().isoformat(timespec="minutes")
            meriter.hogl_ok(data, u, d["datum"])
            return f"👍 Högläsningen ({VECKODAG[date.fromisoformat(d['datum']).weekday()]}) är godkänd! +{meriter.P_HOGL_DAG} ⭐"
        d["status"] = "nej"
        return "🙈 Högläsningen blev inte godkänd. Läs högt för mamma eller pappa och tryck igen."
    if u["typ"] == "skriv":
        if u.get("klart"):
            return None
        if ok:
            u["klart"] = u.pop("vantar", None) or dt_util.now().isoformat(timespec="minutes")
            meriter.uppdrag_klart(data, u)
            return f"👍 {u['namn']} är godkänd!"
        u.pop("vantar", None)
        return f"🙈 {u['namn']} blev inte godkänd än. Kolla uppgifterna igen."
    raise ValueError("Den här läxan godkänns inte så.")


async def _be_om_godkannande(hass: HomeAssistant, barn: str, u: dict, datum: str | None) -> None:
    conf = hass.data[DOMAIN]["conf"]
    namn = next(b["namn"] for b in conf["barn"] if b["id"] == barn)
    if u["typ"] == "glosor":
        titel = f"✍️ {namn} har övat på papper"
        text = f"{u['namn']} ({VECKODAG[date.fromisoformat(datum).weekday()]}). Har du sett det? Godkänn?"
    elif u["typ"] == "hogl":
        d = next((x for x in u.get("dagar", []) if x["datum"] == datum), {})
        titel = f"🗣️ {namn} har läst högt" + (" 🎙️" if d.get("inspelning") else "")
        text = f"{u['namn']}{': ' + u['kapitel'] if u.get('kapitel') else ''} ({VECKODAG[date.fromisoformat(datum).weekday()]}). " + (
            f"Tryck här för att lyssna på inspelningen ({d.get('insp_sek', 0) // 60} min). Godkänn?" if d.get("inspelning") else "Godkänn?")
    elif u["typ"] == "bok":
        titel = f"📸 {namn} har fotat en bok"
        text = f"{u['namn']}: {u['sidor']} nya sidor (+{u['pris']} ⭐). Kolla att sidorna är skarpa och i rätt ordning. Godkänn?"
    else:
        titel = f"✍️ {namn} har gjort läxboken"
        text = f"{u['namn']}. Har du kollat? Godkänn?"
    nyckel = f"{barn}__{u['id']}__{datum or '-'}"
    url = (f"/skolan?barn={barn}&glosor={u['id'][7:]}" if u["typ"] == "glosor"
           else f"/skolan?barn={barn}&bok={u['id'][4:]}" if u["typ"] == "bok" else f"/skolan?barn={barn}&uppdrag={u['id']}")
    for tjanst in conf.get("foralder_notify", {}).values():
        try:
            await hass.services.async_call("notify", tjanst, {
                "title": titel, "message": text,
                "data": {"url": url, "clickAction": url, "tag": f"skolan-{nyckel}", "actions": [
                    {"action": f"SKOLAN_OK__{nyckel}", "title": "👍 Godkänn"},
                    {"action": f"SKOLAN_NEJ__{nyckel}", "title": "Neka", "destructive": True},
                ]},
            })
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Skolan: kunde inte skicka notis via %s: %s", tjanst, err)


async def _godkann(hass: HomeAssistant, barn: str, uid: str, datum: str | None, ok: bool) -> dict:
    path = _dir(hass, barn)
    async with hass.data[DOMAIN]["locks"][barn]:
        data = await hass.async_add_executor_job(_load, path)
        if uid.startswith("glosor-"):
            svar = _godkann_glosor(data, uid[7:], datum, ok)
        elif uid.startswith("bok-"):
            svar = _godkann_bok(data, uid[4:], ok)
        else:
            svar = _godkann_i(data, _find(data.get("uppdrag", []), uid), datum, ok)
        await hass.async_add_executor_job(_save, path, data)
    if svar:
        b = next(x for x in hass.data[DOMAIN]["conf"]["barn"] if x["id"] == barn)
        await _notis(hass, b.get("notify"), "Läxspelet", svar, f"/skolan?glosor={uid[7:]}" if uid.startswith("glosor-") else f"/skolan?bok={uid[4:]}" if uid.startswith("bok-") else f"/skolan?uppdrag={uid}")
        for tjanst in hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values():  # ta bort frågan hos den andra föräldern
            try:
                await hass.services.async_call("notify", tjanst, {"message": "clear_notification", "data": {"tag": f"skolan-{barn}__{uid}__{datum or '-'}"}})
            except Exception:  # noqa: BLE001
                pass
    return data


# ---------- plugga tillsammans: pluggstund och glosduell ----------
def _tlock(hass: HomeAssistant) -> asyncio.Lock:
    return hass.data[DOMAIN].setdefault("tlock", asyncio.Lock())


def _kompisar(hass: HomeAssistant, barn: str) -> list[dict]:
    """Vem barnet kan bjuda in: syskon, och vänner när vänner är påslagna."""
    ut = [{"ref": f"barn:{b['id']}", "namn": b["namn"], "typ": "syskon"} for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] != barn]
    if vanner.pa():
        v = vanner.las(_dir(hass, barn))
        ut += [{"ref": f"van:{x['kod']}", "namn": x["smeknamn"], "typ": "van", "art": x.get("art")} for x in v["vanner"]]
    return ut


def _glos_listor(data: dict) -> list[dict]:
    return [{"amne": a["id"], "id": g["id"], "namn": g["namn"], "amne_namn": a["namn"], "antal": len(g.get("par", []))}
            for a in data.get("amnen", []) for g in a.get("glosor", []) if g.get("par") and not _stavord(g) and g.get("typ", "glosor") == "glosor"]


async def _van_framsteg(hass: HomeAssistant, kod: str, typ: str, sid: str) -> dict | None:
    """Hämta vännens framsteg i en stund/duell från vännens hem (kort cache)."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    if not vanner.pa():
        return None
    cache = hass.data[DOMAIN].setdefault("tcache", {})
    nyckel = (kod, typ, sid)
    nu = time.monotonic()
    if nyckel in cache and nu - cache[nyckel][0] < (3 if typ == "duell" else 60):
        return cache[nyckel][1]
    try:
        async with async_get_clientsession(hass).get(f"{kod}?json=1&{typ}={sid}", timeout=vanner.TIMEOUT, allow_redirects=False) as r:
            svar = json.loads(await r.content.read(2048)) if r.status == 200 else None
    except Exception:  # noqa: BLE001
        svar = None
    if not isinstance(svar, dict):
        svar = None
    cache[nyckel] = (nu, svar)
    return svar


async def _van_bjud(hass: HomeAssistant, barn: str, kod: str, body: dict) -> None:
    """Skicka en inbjudan till vännens hem."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    v = await hass.async_add_executor_job(vanner.las, _dir(hass, barn))
    egen = vanner.egen_kod(_bas_url(hass), v)
    if not egen or not v["smeknamn_ok"]:
        raise ValueError("Du behöver ett godkänt smeknamn och en vänlänk först.")
    try:
        async with async_get_clientsession(hass).post(f"{kod}/tillsammans", json={**body, "kod": egen, "smeknamn": v["smeknamn"]},
                                                      timeout=vanner.TIMEOUT, allow_redirects=False) as r:
            if r.status != 200:
                raise ValueError("Läxspelet hos kompisen svarade inte. Har de samma version?")
    except ValueError:
        raise
    except Exception as err:  # noqa: BLE001
        raise ValueError("Kunde inte nå Läxspelet hos kompisen just nu.") from err


async def _tillsammans_lage(hass: HomeAssistant, barn: str) -> dict:
    """Uppdatera barnets stunder och dueller (egna barns poäng, vänners framsteg), dela ut belöningar."""
    conf = hass.data[DOMAIN]["conf"]
    bas = hass.data[DOMAIN]["base"]
    jag = f"barn:{barn}"
    async with _tlock(hass):
        t = await hass.async_add_executor_job(tillsammans.las, bas)
    stunder = [s for s in t["stunder"] if any(d["ref"] == jag for d in s["deltagare"])]
    dueller = [x for x in t["dueller"] if any(d["ref"] == jag for d in x["deltagare"])]
    van_svar: dict[tuple, dict] = {}
    for typ, lista in (("stund", stunder), ("duell", dueller)):
        for x in lista:
            for d in x["deltagare"]:
                if d["ref"].startswith("van:"):
                    svar = await _van_framsteg(hass, d["ref"][4:], typ, x["id"])
                    if svar:
                        van_svar[(x["id"], d["ref"])] = svar
    lokala_id = {f"barn:{b['id']}": b["id"] for b in conf["barn"]}
    belona: list[tuple[str, str, dict]] = []
    async with _tlock(hass):
        t = await hass.async_add_executor_job(tillsammans.las, bas)
        for s in t["stunder"]:
            if not any(d["ref"] == jag for d in s["deltagare"]):
                continue
            lokala = {}
            for d in s["deltagare"]:
                if d["ref"] in lokala_id:
                    lokala[d["ref"]] = await hass.async_add_executor_job(_load, _dir(hass, lokala_id[d["ref"]]))
            tillsammans.stund_uppdatera(s, lokala, {d["ref"]: van_svar[(s["id"], d["ref"])] for d in s["deltagare"] if (s["id"], d["ref"]) in van_svar})
            if s["klar"]:
                belona += [("stund", d["ref"], s) for d in s["deltagare"] if d["ref"] in lokala_id and d["med"]]
        for x in t["dueller"]:
            if not any(d["ref"] == jag for d in x["deltagare"]):
                continue
            tillsammans.duell_uppdatera(x, {d["ref"]: van_svar[(x["id"], d["ref"])] for d in x["deltagare"] if (x["id"], d["ref"]) in van_svar})
            if tillsammans.duell_status(x)["slut"]:
                belona += [("duell", d["ref"], x) for d in x["deltagare"] if d["ref"] in lokala_id and d["med"]]
        await hass.async_add_executor_job(tillsammans.spara, bas, t)
    for typ, ref, x in belona:
        bid = lokala_id[ref]
        nyckel = f"{typ}:{x['id']}"
        async with hass.data[DOMAIN]["locks"][bid]:
            data = await hass.async_add_executor_job(_load, _dir(hass, bid))
            if nyckel in meriter._m(data)["nycklar"]:
                continue
            if tillsammans.stund_belona(data, x) if typ == "stund" else tillsammans.duell_belona(data, x, ref):
                await hass.async_add_executor_job(_save, _dir(hass, bid), data)
    idag = dt_util.now().date().isoformat()
    return {
        "jag": jag, "vanner_pa": vanner.pa(), "stund_mal": tillsammans.STUND_MAL, "stund_bonus": tillsammans.STUND_BONUS,
        "duell_delta": tillsammans.DUELL_DELTA, "duell_vinst": tillsammans.DUELL_VINST,
        "stunder": [s for s in t["stunder"] if s["dag"] == idag and any(d["ref"] == jag for d in s["deltagare"])],
        "dueller": [tillsammans.duell_for_barn(x, jag) for x in t["dueller"] if any(d["ref"] == jag for d in x["deltagare"])][-5:],
    }


class TillsammansView(HomeAssistantView):
    url = "/api/skolan/tillsammans"
    name = "api:skolan:tillsammans"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        lage = await _tillsammans_lage(hass, barn)
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        lage["kompisar"] = await hass.async_add_executor_job(_kompisar, hass, barn)
        lage["glosor"] = _glos_listor(data)
        return self.json(lage)

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        barn = _barn_for(hass, request, body.get("barn"))
        if _ar_foralder(hass, request):
            return self.json_message("Det är barnen som pluggar tillsammans 🙂", 400)
        conf = hass.data[DOMAIN]["conf"]
        jag_namn = next(b["namn"] for b in conf["barn"] if b["id"] == barn)
        jag = f"barn:{barn}"
        bas = hass.data[DOMAIN]["base"]
        op = str(body.get("op") or "")
        try:
            kompisar = {k["ref"]: k for k in await hass.async_add_executor_job(_kompisar, hass, barn)}
            if op == "stund_ny":
                gaster = [(r, kompisar[r]["namn"]) for r in dict.fromkeys(body.get("gaster") or []) if r in kompisar][:6]
                async with _tlock(hass):
                    t = await hass.async_add_executor_job(tillsammans.las, bas)
                    s = tillsammans.stund_ny(t, (jag, jag_namn), gaster)
                    await hass.async_add_executor_job(tillsammans.spara, bas, t)
                for r, _n in gaster:
                    if r.startswith("van:"):
                        try:
                            await _van_bjud(hass, barn, r[4:], {"typ": "stund", "id": s["id"], "start": s["start"]})
                        except ValueError:
                            pass  # kompisen kan fortfarande se oss när den hämtar; stunden gäller ändå
            elif op == "duell_ny":
                gast = body.get("gast")
                if gast not in kompisar:
                    raise ValueError("Välj vem du vill utmana.")
                data = await hass.async_add_executor_job(_load, _dir(hass, barn))
                a = _find(data.get("amnen", []), body.get("amne"))
                g = _find(a["glosor"], body.get("glosor"))
                if _stavord(g):
                    raise ValueError("Stavningsord går inte att duellera med än. Välj en glosa med översättning.")
                ord_ = _fragor(g, 0)[: tillsammans.DUELL_ORD]
                async with _tlock(hass):
                    t = await hass.async_add_executor_job(tillsammans.las, bas)
                    x = tillsammans.duell_ny(t, (jag, jag_namn), (gast, kompisar[gast]["namn"]), g["namn"], ord_)
                    await hass.async_add_executor_job(tillsammans.spara, bas, t)
                if gast.startswith("van:"):
                    await _van_bjud(hass, barn, gast[4:], {"typ": "duell", "id": x["id"], "start": x["start"], "namn": x["namn"], "ord": x["ord"]})
            elif op in ("stund_ga_med", "duell_ga_med", "duell_svara"):
                async with _tlock(hass):
                    t = await hass.async_add_executor_job(tillsammans.las, bas)
                    svar = None
                    if op == "stund_ga_med":
                        tillsammans.stund_ga_med(t, str(body.get("id")), jag)
                    elif op == "duell_ga_med":
                        tillsammans.duell_ga_med(t, str(body.get("id")), jag)
                    else:
                        svar = tillsammans.duell_svara(t, str(body.get("id")), jag, int(body.get("i", -1)), body.get("svar"), _ratt_svar)
                    await hass.async_add_executor_job(tillsammans.spara, bas, t)
                if op == "duell_svara":
                    hass.data[DOMAIN].get("tcache", {}).clear()
                    return self.json({"ratt": svar})
            else:
                raise ValueError("Okänd åtgärd.")
        except (ValueError, KeyError, TypeError) as err:
            return self.json_message(str(err) if isinstance(err, ValueError) else "Det gick inte.", 400)
        return self.json({"ok": True})


class VanTillsammansView(HomeAssistantView):
    """En vän i ett annat hem bjuder in vårt barn till en pluggstund eller glosduell."""

    url = "/api/skolan/van/{nyckel}/tillsammans"
    name = "api:skolan:van:tillsammans"
    requires_auth = False

    async def post(self, request: web.Request, nyckel: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        hitta = await _barn_for_vannyckel(hass, nyckel) if vanner.pa() else None
        if not hitta:
            raise web.HTTPNotFound
        b, v = hitta
        try:
            body = json.loads(await request.content.read(16384))
            kod = vanner.normal_kod(body.get("kod"))
            van = next((x for x in v["vanner"] if x["kod"] == kod), None)
            if not van:  # bara vänner som föräldrarna har godkänt får bjuda in
                return self.json({"ok": False}, status_code=403)
            sid = str(body.get("id") or "")[:20]
            start = str(body.get("start") or "")[:25]
            datetime.fromisoformat(start)
            if not re.fullmatch(r"[A-Za-z0-9_\-]{6,20}", sid):
                raise ValueError
            bas = hass.data[DOMAIN]["base"]
            async with _tlock(hass):
                t = await hass.async_add_executor_job(tillsammans.las, bas)
                if not any(x["id"] == sid for x in t["stunder"] + t["dueller"]):
                    van_ref, mig = (f"van:{kod}", van["smeknamn"]), (f"barn:{b['id']}", b["namn"])
                    if body.get("typ") == "stund":
                        tillsammans.stund_ny(t, van_ref, [mig], sid, start)
                    elif body.get("typ") == "duell":
                        ord_ = [o for o in (body.get("ord") or []) if isinstance(o, dict) and o.get("fraga") and o.get("facit")]
                        tillsammans.duell_ny(t, van_ref, mig, str(body.get("namn") or "Glosor"), ord_, sid, start)
                    else:
                        raise ValueError
                    await hass.async_add_executor_job(tillsammans.spara, bas, t)
        except (ValueError, TypeError, AttributeError):
            return self.json({"ok": False}, status_code=400)
        return self.json({"ok": True})


# ---------- skolan: läraren och klassen ----------
async def _skola_status(hass: HomeAssistant, barn: str, foralder: bool) -> dict:
    mapp = _dir(hass, barn)
    s = await hass.async_add_executor_job(skola.las, mapp)
    if skola.se_till_nyckel(s):
        await hass.async_add_executor_job(skola.spara, mapp, s)
    st = skola.status(s, _bas_url(hass), foralder)
    if not foralder:  # barnet ser klasslänken bara om föräldern har slagit på något
        if not any(s["foralder"].get(f) for f in skola.FUNKTIONER if f != "mejl"):
            st["lank"] = ""
    else:
        st["smtp"] = await hass.async_add_executor_job(skola.smtp_publik, hass.data[DOMAIN]["base"])
    return st


class SkolaView(HomeAssistantView):
    """Inställningar för skolan (förälder): vad som är på, lärarens e-post, inkorgen med veckobrev."""

    url = "/api/skolan/skola"
    name = "api:skolan:skola"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not skola.PA:
            raise web.HTTPNotFound
        barn = _barn_for(hass, request, request.query.get("barn"))
        return self.json(await _skola_status(hass, barn, _ar_foralder(hass, request)))

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not skola.PA:
            raise web.HTTPNotFound
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        barn = _barn_for(hass, request, body.get("barn"))
        mapp = _dir(hass, barn)
        foralder = _ar_foralder(hass, request)
        if body.get("op") == "grupp_klar" and not foralder:  # barnet bockar av gruppuppgiften
            try:
                async with _vlock(hass, f"skola:{barn}"):
                    s = await hass.async_add_executor_job(skola.las, mapp)
                    skola.grupp_klar(s, str(body.get("id") or ""))
                    await hass.async_add_executor_job(skola.spara, mapp, s)
            except ValueError as err:
                return self.json_message(str(err), 400)
            return self.json(await _skola_status(hass, barn, False))
        if not foralder:
            raise web.HTTPForbidden
        bas = hass.data[DOMAIN]["base"]
        op = str(body.get("op") or "")
        try:
            if op == "smtp":
                await hass.async_add_executor_job(skola.smtp_spara, bas, body)
            elif op == "mejl_test":
                s = await hass.async_add_executor_job(skola.las, mapp)
                till = str(body.get("till") or s["foralder"]["mejl_till"] or "").strip()
                if not till:
                    raise ValueError("Skriv en e-postadress.")
                data = await hass.async_add_executor_job(_load, mapp)
                namn = s["foralder"].get("namn") or next(b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn)
                text = "(TEST – så här ser rapporten ut)\n\n" + skola.rapport_text(skola.rapport(data, namn))
                try:
                    await hass.async_add_executor_job(skola.skicka_mejl, bas, till, f"Läxspelet: testrapport om {namn}", text)
                except (OSError, smtplib.SMTPException) as err:
                    raise ValueError(f"Mejlet gick inte iväg: {err}") from err
            elif op == "inkorg_forslag":
                s = await hass.async_add_executor_job(skola.las, mapp)
                b = next((x for x in s["inkorg"] if x["id"] == body.get("id")), None)
                if not b:
                    raise ValueError("Veckobrevet finns inte.")
                ai = b["ai"]
                if b.get("fil") and not b.get("fil_last"):  # läraren bifogade brevet: AI:n läser det och fyller i det läraren inte skrev
                    try:
                        las = _parse_json(await _ai_las(hass, mapp / "filer" / b["fil"]["namn"], VECKOBREV_PROMPT, "Läs veckobrev från läraren"))
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning("Lärarens veckobrev kunde inte läsas: %s", err)
                        raise ValueError("AI:n kunde inte läsa det bifogade brevet. Försök igen om en stund.") from err
                    if isinstance(las, dict):
                        ai = {**las, **{k: v for k, v in ai.items() if v not in (None, "", [], False)}}
                    async with _vlock(hass, f"skola:{barn}"):
                        s = await hass.async_add_executor_job(skola.las, mapp)
                        b = next((x for x in s["inkorg"] if x["id"] == body.get("id")), None)
                        if b:
                            b["ai"], b["fil_last"] = ai, True
                            await hass.async_add_executor_job(skola.spara, mapp, s)
                data = await hass.async_add_executor_job(_load, mapp)
                return self.json({"forslag": await hass.async_add_executor_job(_forslag_veckobrev, mapp, data, ai)})
            elif op == "inkorg_schema":  # läraren skickade klassens schema: AI:n läser det, föräldern granskar
                s = await hass.async_add_executor_job(skola.las, mapp)
                b = next((x for x in s["inkorg"] if x["id"] == body.get("id") and x.get("typ") == "schema" and x.get("fil")), None)
                if not b:
                    raise ValueError("Schemat finns inte.")
                try:
                    ai = _parse_json(await _ai_las(hass, mapp / "filer" / Path(b["fil"]["namn"]).name, LEKTION_PROMPT, "Läs schema från läraren"))
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Lärarens schema kunde inte läsas: %s", err)
                    raise ValueError("AI:n kunde inte läsa schemat. Försök igen om en stund.") from err
                data = await hass.async_add_executor_job(_load, mapp)
                forslag = _lektion_forslag(data, ai if isinstance(ai, dict) else {})
                if not forslag["lektioner"] and not forslag["amnen"]:
                    raise ValueError("AI:n hittade inget schema i filen.")
                return self.json({"forslag": forslag})
            elif op in ("inkorg_material", "inkorg_prov"):
                await _inkorg_spara(hass, barn, mapp, op, body)
            else:
                async with _vlock(hass, f"skola:{barn}"):
                    s = await hass.async_add_executor_job(skola.las, mapp)
                    if op == "installningar":
                        skola.satt_installningar(s, body)
                    elif op == "koppla_bort":
                        skola.koppla_bort(s)
                    elif op in ("inkorg_klar", "inkorg_avvisa"):
                        b = next((x for x in s["inkorg"] if x["id"] == body.get("id")), None)
                        if b:
                            b["status"] = "sparad" if op == "inkorg_klar" else "avvisad"
                            if b.get("fil") and (op == "inkorg_avvisa" or b.get("typ", "veckobrev") in ("veckobrev", "schema")):
                                await hass.async_add_executor_job((mapp / "filer" / Path(b["fil"]["namn"]).name).unlink, True)
                    else:
                        raise ValueError("Okänd åtgärd.")
                    await hass.async_add_executor_job(skola.spara, mapp, s)
        except ValueError as err:
            return self.json_message(str(err), 400)
        return self.json(await _skola_status(hass, barn, True))


async def _inkorg_spara(hass: HomeAssistant, barn: str, mapp: Path, op: str, body: dict) -> None:
    """Föräldern godkänner studiematerial eller ett provresultat från läraren och väljer ämne."""
    async with hass.data[DOMAIN]["locks"][barn]:
        async with _vlock(hass, f"skola:{barn}"):
            s = await hass.async_add_executor_job(skola.las, mapp)
            b = next((x for x in s["inkorg"] if x["id"] == body.get("id") and x["status"] == "ny"), None)
            if not b or b.get("typ") != ("material" if op == "inkorg_material" else "prov"):
                raise ValueError("Det finns inte längre i inkorgen.")
            data = await hass.async_add_executor_job(_load, mapp)
            amnen = data.setdefault("amnen", [])
            if body.get("nytt_amne"):
                namn = _name(body.get("nytt_amne"))
                a = next((x for x in amnen if x["namn"].lower() == namn.lower()), None)
                if not a:
                    a = {"id": _new_id(), "namn": namn, "farg": FARGER[len(amnen) % len(FARGER)], "bocker": [], "glosor": [], "delar": ["bocker"]}
                    amnen.append(a)
            else:
                a = _find(amnen, body.get("amne"))
            fil = (b.get("fil") or {}).get("namn")
            if fil:  # filen blir en bok i ämnet, så att den syns och kan läsas som de andra böckerna
                a.setdefault("bocker", []).append({"id": _new_id(), "namn": _name(("📝 " if op == "inkorg_prov" else "📎 ") + b["titel"]), "sidor": [fil]})
                _sla_pa_del(a, "bocker")
            if op == "inkorg_prov" and b.get("resultat"):
                lista = data.setdefault("uppdrag", [])
                u = next((x for x in lista if b.get("prov_id") and x.get("larar_prov") == b["prov_id"]), None) or \
                    next((x for x in lista if x.get("typ") == "prov" and x.get("amne") == a["id"] and not x.get("resultat")
                          and _liknar(x["namn"], b["titel"]) > 0.6), None)
                if not u:
                    u = {"id": _new_id(), "typ": "prov", "namn": _name(b["titel"]), "amne": a["id"], "amne_namn": a["namn"], "bok": None,
                         "fran": None, "till": None, "kapitel": "", "sidor": [], "glosor": [], "lasta": 0, "allt_last": False, "klart": dt_util.now().isoformat(timespec="minutes"),
                         "datum": b.get("datum") or dt_util.now().date().isoformat(), "skapad": dt_util.now().isoformat(timespec="minutes"),
                         "av_id": "larare", "av_namn": (s.get("larare") or {}).get("namn") or "Läraren"}
                    lista.append(u)
                    del lista[:-200]
                u["larar_prov"] = b.get("prov_id") or ""
                meriter.prov_resultat(data, u, {**b["resultat"], "av": (s.get("larare") or {}).get("namn") or "Läraren",
                                                "tid": dt_util.now().isoformat(timespec="minutes")})
            b["status"] = "sparad"
            await hass.async_add_executor_job(_save, mapp, data)
            await hass.async_add_executor_job(skola.spara, mapp, s)


class KlassView(HomeAssistantView):
    """Lärarappen synkar med en elev. Ingen inloggning, hemlig nyckel i klasslänken."""

    url = "/api/skolan/klass/{nyckel}"
    name = "api:skolan:klass"
    requires_auth = False

    async def post(self, request: web.Request, nyckel: str) -> web.Response:
        import hmac

        hass: HomeAssistant = request.app["hass"]
        if not skola.PA:
            raise web.HTTPNotFound
        hitta = None
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            s = await hass.async_add_executor_job(skola.las, _dir(hass, b["id"]))
            if s["nyckel"] and hmac.compare_digest(s["nyckel"], nyckel):
                hitta = b
        if not hitta:
            raise web.HTTPNotFound
        try:
            body = json.loads(await request.content.read(skola.MAX_FILER_PER_SYNK * 2))  # veckobrev, material och prov kan ha filer
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.json({"fel": "Fel format."}, status_code=400)
        mapp = _dir(hass, hitta["id"])
        async with hass.data[DOMAIN]["locks"][hitta["id"]]:
            async with _vlock(hass, f"skola:{hitta['id']}"):
                s = await hass.async_add_executor_job(skola.las, mapp)
                if not any(s["foralder"].get(f) for f in skola.FUNKTIONER if f != "mejl"):
                    return self.json({"fel": "Föräldern har inte slagit på något för läraren än."}, status_code=403)
                data = await hass.async_add_executor_job(_load, mapp)
                try:
                    svar = skola.ta_emot(s, data, hitta["namn"], body)
                except PermissionError as err:
                    return self.json({"fel": str(err)}, status_code=409)
                except ValueError as err:
                    return self.json({"fel": str(err)}, status_code=400)
                if skola.klassboss_belona(data, s):
                    await hass.async_add_executor_job(_save, mapp, data)
                for namn, innehall in svar.pop("_filer"):
                    await hass.async_add_executor_job((mapp / "filer" / namn).write_bytes, innehall)
                await hass.async_add_executor_job(skola.spara, mapp, s)
        svar["skolan"] = VERSION
        return self.json(svar)
