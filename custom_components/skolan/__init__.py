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
import os
import hashlib
import random
import re
import smtplib
import time
import secrets
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import voluptuous as vol
import aiohttp
from aiohttp import web

from homeassistant.components import panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import ai_lev, backup, omsorg, boende, dagens, extra, hjarngympa, intressen, larare, packa, fraga, meriter, penna, plugg, schemavy, skola, skriv, skrivkrav, tillsammans, utveckling, vanner

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
        "ai_inst": await hass.async_add_executor_job(_load_fil, base / AI_FIL),  # Läxspelets egen AI-koppling (t.ex. Mistral)
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
    for view in (StateView, ActionView, GlosstridView, LarView, FragaView, HjalpView, PlanView, HandstilView, SkrivView, PennaView, BackupView, HemkopplingView, HemView, FjarrView, BoendeView, SyskonView, PackaView, ExtraView, HjarnView, IntresseView, UtvecklingView, LarareView, SamtalView, KlockaView, PlanKalenderView, UploadView, FileView, GlosorReadView, GlosorStavningView, EbokView, UtskriftView, ForhorView, UppdragView, VeckobrevView, LektionView, SchemaSidaView, KalenderView, UttalView, InspelningView, WidgetView, WidgetBildView, WidgetBildHamtaView, WidgetNyckelView, WidgetInstallView, ExempelView, VannerView, VanPublikView, VanForfraganView, VanAdressView, VanAdressbokView, TillsammansView, VanTillsammansView, SkolaView, KlassView, ForalderInfoView, AiView):
        hass.http.register_view(view())

    async def _starta_grind(_event: Event | None = None) -> None:
        """Ingen Nabu Casa: starta Läxspelets gratistunnel, som bara släpper fram de publika länkarna."""
        if getattr(hass, "konto", None) is not None:  # Windowsappen har en egen tunnel
            return
        if _bas_url_egen(hass) and not conf.get("egen_tunnel"):
            return
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        from .grind import Grind
        g = Grind(base / ".cloudflared", hass.http.server_port or 8123, async_get_clientsession(hass))
        hass.data[DOMAIN]["grind"] = g
        try:
            await g.starta()
        except OSError as err:
            _LOGGER.warning("Läxspelets tunnel kunde inte starta: %s", err)

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
                for tjanst in _foralder_tjanster(hass, data):
                    await _notis(
                        hass, tjanst, f"⚠️ {b['namn']} har inte gjort förhöret",
                        f"{f['namn']}: {n} påminnelser utan att det blivit gjort. Dags att prata med {b['namn']}?",
                        f"/skolan?barn={b['id']}&forhor={f['id']}",
                    )

    async_track_time_change(hass, _tjata, minute=5, second=0)

    senast_klocka: dict[str, str] = {}

    async def _topplista_sensor() -> None:
        """Veckans topplista som sensor (för t.ex. en knapp på hemmets skärmar)."""

        def _rakna() -> list[dict]:
            ut = []
            for b in hass.data[DOMAIN]["conf"]["barn"]:
                d = _load(_dir(hass, b["id"]))
                v, s = meriter.veckoresultat(d), meriter.sammanfattning(d)
                djur = s.get("djur") or {}
                ut.append({
                    "namn": b["namn"], "poang": v["poang"], "andel": v["andel"], "klara": v["klara"], "antal": v["antal"],
                    "forbattring": v["forbattring"], "bonus": v["bonus"], "stjarnor_veckan": s["veckan"],
                    "svit": s["streak"], "gjort_idag": s["streak_idag"], "niva": s["niva"]["niva"], "niva_namn": s["niva"]["namn"],
                    "titel": meriter.titel(d), "karta_niva": meriter.karta_kort(d)["niva"],
                    "husdjur": (djur.get("art") or "") + " " + (djur.get("namn") or ""), "_nyckel": meriter.topp_nyckel(v),
                })
            return sorted(ut, key=lambda x: x["_nyckel"], reverse=True)

        try:
            lista = await hass.async_add_executor_job(_rakna)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Skolan: topplista: %s", err)
            return
        if not lista:
            return
        etta = lista[0]
        lika = len(lista) > 1 and lista[1]["_nyckel"] == etta["_nyckel"]
        for i, x in enumerate(lista):
            x["plats"] = i + 1
            x.pop("_nyckel")
        state = "Ingen än" if etta["poang"] == 0 else ("Lika" if lika else etta["namn"])
        hass.states.async_set("sensor.skolan_topplista", state, {
            "friendly_name": "Läxspelet topplista", "icon": "mdi:trophy",
            "ledare": None if state in ("Ingen än", "Lika") else etta["namn"],
            "poang": etta["poang"], "lista": lista, "vecka": dt_util.now().isocalendar()[1],
        })

    async def _klockor(_now=None) -> None:
        """Svit, stjärnor, dagens utmaning och husdjuret som sensorer, och till barnets Awtrix-klocka."""
        await _topplista_sensor()
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

    async def _lapp_utkast(_now=None) -> None:
        """Fredag 15.00: skriv ett utkast till veckans lapp till läraren om barnet har tyckt något var svårt."""
        if dt_util.now().weekday() != 4:
            return
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            try:
                mapp = _dir(hass, b["id"])
                data = await hass.async_add_executor_job(_load, mapp)
                f = await hass.async_add_executor_job(larare.fakta, data, larare.LAPP_DAGAR)
                s = await hass.async_add_executor_job(skola.las, mapp)
                if not larare.har_svart(f) or larare.lapp_status(s).get("aktuell"):
                    continue
                ai = _parse_json(await _ai_text(hass, larare.LAPP_PROMPT.format(namn=b["namn"], alder=intressen.alder(data) or "", fakta=larare.fakta_text(f)),
                                                "Läxspelet lapp till läraren"))
                if not str(ai.get("text") or "").strip():
                    continue
                async with hass.data[DOMAIN]["locks"][b["id"]]:
                    s = await hass.async_add_executor_job(skola.las, mapp)
                    larare.lapp_satt(s, ai["text"])
                    await hass.async_add_executor_job(skola.spara, mapp, s)
                for tj in _foralder_tjanster(hass, data):
                    await _notis(hass, tj, f"✉️ Lapp till {b['namn']}s lärare", f"Ett utkast om det {b['namn']} tyckte var svårt den här veckan är klart. Läs, ändra och skicka om du vill.",
                                 f"/skolan?barn={b['id']}")
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Veckans lapp: %s", err)

    async_track_time_change(hass, _lapp_utkast, hour=15, minute=0, second=0)

    async def _utveckling_notis(_now=None) -> None:
        """Första dagen i månaden: visa barnet hur mycket det har utvecklats."""
        if dt_util.now().day != 1:
            return
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            text = utveckling.notis_text(data)
            if text:
                await _notis(hass, b.get("notify"), "📈 Så mycket bättre du har blivit!", text, f"/skolan?barn={b['id']}")

    async_track_time_change(hass, _utveckling_notis, hour=17, minute=30, second=0)

    async_track_time_change(hass, _hogtid_notis, hour=15, minute=30, second=0)

    async def _skolinfo_notis(_now=None) -> None:
        """Kl. 18.30: påminn barnet och föräldrarna om det som händer i skolan imorgon (t.ex. utflykt, ta med matsäck)."""
        conf = hass.data[DOMAIN]["conf"]
        for b in conf["barn"]:
            data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            imorgon = [x for x in meriter.skolinfo(data) if x["dagar"] == 1 and (not x.get("kalender") or x.get("ny_start"))]
            if not imorgon:
                continue
            dag = imorgon[0]["datum"]
            nar = f"Imorgon, {VECKODAGAR_SV[date.fromisoformat(dag).weekday()]} {int(dag[8:])}/{int(dag[5:7])}"
            rader = nar + ":\n" + "\n".join(f"📌 {'Kl. ' + x['tid'] + ': ' if x.get('tid') else ''}{x['text']}" for x in imorgon)
            await _notis(hass, b.get("notify"), "🎒 Imorgon i skolan", rader, "/skolan")
            for tjanst in _foralder_tjanster(hass, data, dt_util.now().date() + timedelta(days=1)):
                await _notis(hass, tjanst, f"🎒 {b['namn']} imorgon", rader, f"/skolan?barn={b['id']}")

    async_track_time_change(hass, _skolinfo_notis, hour=18, minute=30, second=0)

    async def _overlamning(now=None) -> None:
        """Bytesdag (växelvis boende): sammanfattning till hemmet som tar emot barnet, påminnelse om saker till hemmet som lämnar."""
        now = now or dt_util.now()
        conf = hass.data[DOMAIN]["conf"]
        skickat = hass.data[DOMAIN].setdefault("overlamning_skickad", set())
        for b in conf["barn"]:
            fj = await hass.async_add_executor_job(_load_fil, _dir(hass, b["id"]) / "fjarr.json")
            if fj.get("token"):  # barnets konto finns i det andra hemmet: hämta därifrån, notiser till föräldrarna här
                try:
                    data = (await _fjarr_state(hass, b["id"]))["data"]
                except Exception:  # noqa: BLE001
                    continue
                vi = lambda h: bool(h and h.get("annat_system"))  # noqa: E731  (sett från hem-systemet är vi "det andra")
                mottagare = list(conf.get("foralder_notify", {}).values())
            else:
                data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
                vi = lambda h: bool(h and not h.get("annat_system"))  # noqa: E731
                mottagare = None
            if not boende.aktiv(data):
                continue
            idag = now.date()
            bt = (data.get("boende") or {}).get("bytestid", "17:00")
            h, m = (int(x) for x in bt.split(":"))
            nyckel = f"{b['id']}:{idag.isoformat()}"
            if nyckel in skickat or (now.hour, now.minute // 15) != (h - 2 if h >= 2 else 0, (m // 15)):
                continue  # skickas två timmar före bytet
            uppdr = [f"{u['namn']} ({u.get('amne_namn')}, {u['datum'][5:]})" for u in data.get("uppdrag", [])
                     if not u.get("klart") and u.get("datum") and idag.isoformat() <= u["datum"] <= (idag + timedelta(days=7)).isoformat()]
            info = [x["text"] for x in meriter.skolinfo(data) if x.get("dagar") is not None and 0 <= x["dagar"] <= 3]
            o = boende.overlamning(data, idag, uppdr, info)
            if not o:
                continue
            skickat.add(nyckel)
            fn = conf.get("foralder_notify", {})
            if vi(o["till"]):
                for tj in mottagare if mottagare is not None else [fn[u] for u in o["till"].get("foraldrar", []) if fn.get(u)] or list(fn.values()):
                    await _notis(hass, tj, f"🔄 {b['namn']} kommer till er idag kl. {bt}", o["text"], f"/skolan?barn={b['id']}")
            if vi(o["fran"]):
                saker = [x["namn"] for x in data.get("saker", []) if x.get("hem") == o["fran"]["id"]]
                text = (f"Glöm inte att packa: {', '.join(saker)}." if saker else "Allt verkar redan vara på plats.") + " Läxor och prov finns i Läxspelet."
                for tj in mottagare if mottagare is not None else [fn[u] for u in o["fran"].get("foraldrar", []) if fn.get(u)] or list(fn.values()):
                    await _notis(hass, tj, f"🔄 {b['namn']} flyttar till {o['till']['namn']} kl. {bt}", text, f"/skolan?barn={b['id']}")

    async_track_time_change(hass, _overlamning, minute=[0, 15, 30, 45], second=5)

    async def _fjarr_skolinfo(_now=None) -> None:
        """Kl. 18.30 för barn vars konto finns i det andra hemmet: notis till föräldrarna här när barnet är här imorgon."""
        conf = hass.data[DOMAIN]["conf"]
        imorgon_d = dt_util.now().date() + timedelta(days=1)
        for b in conf["barn"]:
            fj = await hass.async_add_executor_job(_load_fil, _dir(hass, b["id"]) / "fjarr.json")
            if not fj.get("token"):
                continue
            try:
                data = (await _fjarr_state(hass, b["id"]))["data"]
            except Exception:  # noqa: BLE001
                continue
            h = boende.hem_for(data, imorgon_d)
            if boende.aktiv(data) and not (h and h.get("annat_system")):
                continue  # barnet är i hem-systemets hem imorgon: de får notisen därifrån
            imorgon = [x for x in meriter.skolinfo(data) if x["dagar"] == 1 and (not x.get("kalender") or x.get("ny_start"))]
            if not imorgon:
                continue
            rader = "\n".join(f"📌 {'Kl. ' + x['tid'] + ': ' if x.get('tid') else ''}{x['text']}" for x in imorgon)
            for tj in conf.get("foralder_notify", {}).values():
                await _notis(hass, tj, f"🎒 {b['namn']} imorgon", rader, f"/skolan?barn={b['id']}")

    async_track_time_change(hass, _fjarr_skolinfo, hour=18, minute=30, second=20)

    async def _kalendrar(_now=None) -> None:
        try:
            await _kal_uppdatera(hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Skolkalendrarna: %s", err)

    async def _kal_start(_event=None) -> None:
        await _kal_migrera(hass)
        await _kalendrar()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _kal_start)
    async_track_time_change(hass, _kalendrar, minute=[7, 37], second=0)

    async def _van_adresser(_now=None) -> None:
        """Gratistunneln byter adress vid omstart: säg till vännerna, och leta reda på vänner vi inte når."""
        if not vanner.pa():
            return
        await _vanner_adress_koll(hass)

    async_track_time_change(hass, _van_adresser, minute=list(range(1, 60, 3)), second=30)

    async def _auto_backup(_now=None) -> None:
        """Kl. 03:15: automatisk backup (om föräldern har slagit på den)."""
        inst = await hass.async_add_executor_job(_backup_inst_las, hass)
        if inst.get("auto"):
            await _backup_kor(hass, inst)

    async_track_time_change(hass, _auto_backup, hour=3, minute=15, second=0)

    async def _klockor_laxor(_now=None) -> None:
        """Var 10:e minut: visa läxor, packning och husdjuret på barnens Awtrix-klockor (MQTT), om föräldern har slagit på det."""
        if not hass.services.has_service("mqtt", "publish"):
            return
        inst = await hass.async_add_executor_job(_load_fil, hass.data[DOMAIN]["base"] / "klockor.json")
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            k = inst.get(b["id"]) or {}
            if not k.get("pa") or not k.get("prefix"):
                continue
            try:
                data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
                text, farg = _klocka_text(data)
                await hass.services.async_call("mqtt", "publish", {"topic": f"{k['prefix']}/custom/laxspelet",
                                                                   "payload": json.dumps({"text": text, "color": farg, "duration": 8, "lifetime": 1200, "scrollSpeed": 80})})
            except Exception as err:  # noqa: BLE001
                _LOGGER.info("Läxspelet: klockan för %s: %s", b["id"], err)

    async_track_time_change(hass, _klockor_laxor, minute=list(range(2, 60, 10)), second=0)

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

    async def _svit_notis(now) -> None:
        """16.30 och 19.15: streaken är i fara (inget gjort idag) eller kan räddas genom att jobba ikapp."""
        sista = now.hour >= 19
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            if not b.get("notify"):
                continue
            try:
                data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
                m = meriter.sammanfattning(data)
            except Exception:  # noqa: BLE001
                continue
            ik, n = m.get("ikapp"), m["streak"]
            if ik:
                titel = f"🩹 Rädda din svit på {ik['svit']} dagar!" if not sista else f"⏰ Sista chansen: rädda din svit på {ik['svit']} dagar!"
                text = (f"Du missade igår, men du kan jobba ikapp idag. Tjäna {ik['mal']} ⭐ med läxor och övningar"
                        f" (du har {ik['p']}), så räknas igår också. Imorgon är det för sent!")
            elif m.get("skydd_raddar"):
                titel = f"🛡️ Din svit på {m['skydd_raddar']} dagar kan räddas!"
                text = "Du har ett svitskydd. Gör något i Läxspelet idag så räddar det sviten."
            elif n >= 2 and not m["streak_idag"]:
                titel = f"🔥 Din svit på {n} dagar väntar!" if not sista else f"⏰ Din svit på {n} dagar försvinner ikväll!"
                text = f"Gör något litet i Läxspelet idag så får du +{min(m['streak_max'], n + 1)} ⭐ och sviten fortsätter."
            else:
                continue
            try:
                tips = fraga.svit_forslag(data)
                tips = [t for t in tips if not t.startswith("För att jobba ikapp")][:2]
                if tips:
                    text += "\n" + "\n".join(f"👉 {t}" for t in tips)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Skolan: svitförslag: %s", err)
            idag = dt_util.now().date().isoformat()
            if any(x.get("dag") == idag for x in (data.get("skrivkrav") or {}).get("vantar") or []):
                text += ("\n✍️ Det du redan gjort idag räknas inte förrän du gjort en skrivövning"
                         " (Skrivverkstaden eller ett Pennuppdrag). Skriv något så räknas allt!")
            await _notis(hass, b["notify"], titel, text, f"/skolan?barn={b['id']}")

    async_track_time_change(hass, _svit_notis, hour=16, minute=30, second=0)
    async_track_time_change(hass, _svit_notis, hour=19, minute=15, second=0)
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
        hass.async_create_task(_starta_grind())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _ateruppta)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _starta_grind)

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
    bara = request.get("skolan_bara_barn")
    if bara:  # anrop från barnets andra hem: bara det kopplade barnet
        return bara
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


KRYMP_MAX = 2000  # längsta sida i pixlar: boktext går fortfarande lätt att läsa (också för AI:n)
KRYMP_KVALITET = 72


def _krymp_bild(f: Path) -> int:
    """Gör ett stort foto (JPEG) mindre: max 2000 px och lagom kvalitet. Bilden roteras rätt. Returnerar sparade byte."""
    try:
        if f.suffix.lower() not in (".jpg", ".jpeg") or f.stat().st_size < 450_000:
            return 0
        from PIL import Image, ImageOps

        fore = f.stat().st_size
        with Image.open(f) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail((KRYMP_MAX, KRYMP_MAX))
            tmp = f.with_name(f".krymp-{f.name}")
            im.save(tmp, "JPEG", quality=KRYMP_KVALITET, optimize=True, progressive=True)
        if tmp.stat().st_size < fore * 0.85:
            tmp.replace(f)
            return fore - f.stat().st_size
        tmp.unlink(missing_ok=True)
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("Läxspelet: kunde inte krympa %s: %s", f.name, err)
    return 0


def _krymp_mapp(mapp: Path) -> dict:
    """Krymp alla stora foton i en mapp (befintliga böcker m.m.)."""
    fore = sum(x.stat().st_size for x in mapp.glob("*") if x.is_file())
    n = sum(1 for f in sorted(mapp.glob("*")) if f.is_file() and _krymp_bild(f))
    efter = sum(x.stat().st_size for x in mapp.glob("*") if x.is_file())
    return {"bilder": n, "fore_mb": round(fore / 1e6, 1), "efter_mb": round(efter / 1e6, 1)}


_MAPP_ANNAN: "contextvars.ContextVar[tuple[str, Path] | None]" = __import__("contextvars").ContextVar("skolan_mapp", default=None)


def _dir(hass: HomeAssistant, barn: str) -> Path:
    o = _MAPP_ANNAN.get()
    if o and o[0] == barn:  # läser barnets konto ur en molnbackup (det andra hemmet svarar inte)
        return o[1]
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


def _klocka_text(data: dict) -> tuple[str, str]:
    """Det viktigaste just nu, kort nog för en pixelklocka."""
    nu = dt_util.now()
    d = meriter._m(data).get("djur") or {}
    rader = plugg.dagens_lista(data)["rader"]
    if rader and 13 <= nu.hour < 21:
        return f"{len(rader)} sak{'er' if len(rader) > 1 else ''} att plugga", "#FFA726"
    pl = packa.status(data)
    if pl["rader"] and nu.hour >= 18 and len(pl["bockat"]) < len(pl["rader"]):
        return "Packa vaskan!", "#29B6F6"
    dj = meriter.djur(data) or {}
    if dj.get("humor") in ("hungrig", "ledsen"):
        return f"{d.get('namn', 'Husdjuret')} ar hungrig!", "#EF5350"
    return f"{d.get('namn', '')} {meriter.sammanfattning(data).get('saldo', 0)} stj".strip(), "#66BB6A"


def _foralder_tjanster(hass: HomeAssistant, data: dict, dag: date | None = None) -> list[str]:
    """Notistjänster för föräldrarna som har barnet en viss dag (växelvis boende). Alla annars."""
    conf = hass.data[DOMAIN]["conf"]
    fn = conf.get("foralder_notify", {})
    vilka = boende.foraldrar_for(data, dag or dt_util.now().date(), list(conf.get("foraldrar", [])))
    return [fn[u] for u in vilka if fn.get(u)]


async def _foralder_namn(hass: HomeAssistant) -> dict[str, str]:
    ut = {}
    for uid in hass.data[DOMAIN]["conf"].get("foraldrar", []):
        try:
            u = await hass.auth.async_get_user(uid)
            ut[uid] = u.name if u else uid
        except Exception:  # noqa: BLE001  (Windows)
            p = getattr(hass, "konto", None) and hass.konto.person(uid)
            ut[uid] = (p or {}).get("namn", uid)
    return ut


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


async def _vanner_adress_koll(hass: HomeAssistant) -> None:
    """Meddela vännerna vår nya vänlänk (signerat). Vänner vi inte har nått på ett tag: fråga gemensamma vänner."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    bas = _bas_url(hass)
    if not bas.startswith("https://"):
        return
    for b in hass.data[DOMAIN]["conf"]["barn"]:
        mapp = _dir(hass, b["id"])
        v = await hass.async_add_executor_job(vanner.las, mapp)
        egen = vanner.egen_kod(bas, v)
        if not egen or not v["vanner"]:
            continue
        andrat = False
        for x in v["vanner"]:
            if not x.get("hemlighet"):
                continue
            if x.get("meddelad") != egen:  # ny adress hos oss: säg till
                try:
                    async with session.post(f"{x['kod']}/adress", json=vanner.adress_paket(v, x, egen), timeout=vanner.TIMEOUT, allow_redirects=False) as r:
                        if r.status == 200:
                            x["meddelad"], andrat = egen, True
                except Exception:  # noqa: BLE001
                    pass
            if x.get("fel", 0) >= 3 and time.time() - x.get("letad", 0) > 3600:  # når inte vännen: fråga gemensamma vänner
                x["letad"], andrat = time.time(), True
                for via in [y for y in v["vanner"] if y is not x and y.get("hemlighet") and not y.get("fel")][:10]:
                    try:
                        async with session.post(f"{via['kod']}/adressbok", json=vanner.adressbok_fraga(v, via, x["kod"]), timeout=vanner.TIMEOUT,
                                                allow_redirects=False) as r:
                            ny = (await r.json()).get("kod") if r.status == 200 else None
                        ny = vanner.normal_kod(ny) if ny else None
                        if ny and vanner.samma(ny, x["kod"]) and ny != x["kod"]:
                            x["kod"], x["fel"] = ny, 0
                            _LOGGER.info("Vänner: hittade %s via %s", x.get("smeknamn"), via.get("smeknamn"))
                            break
                    except Exception:  # noqa: BLE001
                        continue
        if andrat:
            async with _vlock(hass, b["id"]):
                v2 = await hass.async_add_executor_job(vanner.las, mapp)
                for x in v2["vanner"]:  # bara fälten vi ändrade
                    y = next((z for z in v["vanner"] if vanner.samma(z["kod"], x["kod"]) or z.get("hemlighet") == x.get("hemlighet") and z.get("hemlighet")), None)
                    if y:
                        x.update({k: y[k] for k in ("kod", "fel", "meddelad", "letad") if k in y})
                await hass.async_add_executor_job(vanner.spara, mapp, v2)


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


class VanAdressView(HomeAssistantView):
    """En vän har fått ny adress (gratistunneln byter vid omstart). Signerat med vänskapens hemlighet."""

    url = "/api/skolan/van/{nyckel}/adress"
    name = "api:skolan:van:adress"
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
                ok = vanner.ta_emot_adress(v, body)
                if ok:
                    await hass.async_add_executor_job(vanner.spara, _dir(hass, b["id"]), v)
        except (ValueError, AttributeError, TypeError):
            return self.json({"ok": False}, status_code=400)
        return self.json({"ok": ok}, status_code=200 if ok else 403)


class VanAdressbokView(HomeAssistantView):
    """En vän frågar om en gemensam väns senaste adress (bara vänner får svar, och bara om vänner till båda)."""

    url = "/api/skolan/van/{nyckel}/adressbok"
    name = "api:skolan:van:adressbok"
    requires_auth = False

    async def post(self, request: web.Request, nyckel: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        hitta = await _barn_for_vannyckel(hass, nyckel) if vanner.pa() else None
        if not hitta:
            raise web.HTTPNotFound
        try:
            kod = vanner.adressbok_svar(hitta[1], json.loads(await request.content.read(2048)))
        except (ValueError, AttributeError, TypeError):
            kod = None
        return self.json({"kod": kod}, status_code=200 if kod else 404)


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
                rad = vanner.ta_emot_forfragan(v, body.get("kod"), body.get("smeknamn"), body.get("hemlighet") or "")
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
                        h = vanner.ny_hemlighet()
                        vanner.lagg_in_van(v, kod, await vanner.hamta_kort(session, kod), h)
                        await vanner.skicka_forfragan(session, kod, egen, v["smeknamn"], h)
                    else:
                        vanner.onska(v, kod, egen)
                        meddela = (f"🤝 {b['namn']} vill lägga till en vän", "Godkänn eller neka under Vänner i Läxspelet.")
                elif op in ("svar_utgaende", "svar_inkommande"):
                    kod = vanner.normal_kod(kod)
                    if body.get("ja"):
                        if not egen:
                            raise ValueError("Er Home Assistant går inte att nå utifrån, så vänner fungerar inte.")
                        vanner._kolla_ny(v, kod, egen)
                        # vänskapens hemlighet: den som lägger till skapar den, den andra får den med förfrågan
                        h = vanner.ny_hemlighet() if op == "svar_utgaende" else vanner.inkommande_hemlighet(v, kod)
                        vanner.lagg_in_van(v, kod, await vanner.hamta_kort(session, kod), h)
                        if op == "svar_utgaende":
                            await vanner.skicka_forfragan(session, kod, egen, v["smeknamn"], h)
                    else:
                        lista = "utgaende" if op == "svar_utgaende" else "inkommande"
                        v[lista] = [x for x in v[lista] if not vanner.samma(x["kod"], kod)]
                elif op == "ta_bort":
                    vanner.ta_bort(v, vanner.normal_kod(kod))
                elif op == "flagga":  # 🚩 barnet säger till en vuxen: något känns fel med en vän (eller allmänt)
                    van = next((x for x in v["vanner"] if kod and vanner.samma(x["kod"], kod)), None)
                    vad = re.sub(r"\s+", " ", str(body.get("text") or "")).strip()[:300]
                    v.setdefault("flaggor", []).append({"tid": dt_util.now().isoformat(timespec="minutes"), "kod": van["kod"] if van else "",
                                                        "smeknamn": van["smeknamn"] if van else "", "text": vad})
                    v["flaggor"] = v["flaggor"][-50:]
                    meddela = (f"🚩 {b['namn']} vill prata med dig",
                               (f"Det gäller vännen \"{van['smeknamn']}\". " if van else "") + (f"{b['namn']} skrev: \"{vad}\". " if vad else "")
                               + "Prata med barnet. Under Vänner kan du ta bort vännen. Är något allvarligt: kontakta polisen (114 14, vid fara 112).")
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
        k = next((y for y in v["vanner"] if vanner.samma(y["kod"], x.get("kod"))), None)
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
        if not request.get("skolan_bara_barn"):  # barnets konto finns i ett annat hem: panelen hämtar därifrån
            fj = await hass.async_add_executor_job(_load_fil, _dir(hass, barn) / "fjarr.json")
            if fj.get("token"):
                return self.json({"fjarr": {"barn": barn, "hem": fj.get("hem") or "andra hemmet"},
                                  "alla_barn": [{"id": b["id"], "namn": b["namn"]} for b in conf["barn"]] if parent else [], "barn": barn, "kan_valja": parent})
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
                "laxfraga": meriter.laxfraga(data) if not parent else None, "veckokoll": meriter.veckokoll(data), "hjalp": meriter.hjalp_status(data), "handstil": meriter.handstil_status(data), "skriv": skriv.status(data, fraga.alder(data)), "penna": penna.status(data), "studieprofil": plugg.profil(data, fraga.alder(data)), "onskemal": plugg.onskemal(data) if parent else None, "husdjur_stats": meriter.husdjur_stats(data) if parent else None, "riktlinjer": plugg.riktlinjer(data) if parent else None,
                "boende": boende.status(data, await _foralder_namn(hass) if parent else {}),
                "packlista": packa.status(data), "lattlast": bool(data.get("lattlast")), "mående": extra.mående_status(data, parent),
                "matte": {"rekord": (data.get("matte") or {}).get("rekord", {})}, "hjarn": hjarngympa.status(data, barn), "intressen": intressen.status(data), "skrivkrav": skrivkrav.status(data), "lasflyt": (data.get("lasflyt") or [])[-30:], "syskonlista": [{"id": b["id"], "namn": b["namn"]} for b in conf["barn"] if b["id"] != barn] if not request.get("skolan_bara_barn") else [], "alla_djur": (meriter.DJUR + meriter.PAKET_DJUR) if parent else None, "svaga": plugg.svaga_status(data), "svaga_idag": plugg.svaga_idag(data), "dagens_lista": plugg.dagens_lista(data), "material": meriter.material_fraga(data) if not parent else None,
                "lektioner": data.get("lektioner", []), "skolinfo": meriter.skolinfo(data),
                "kalender": {"antal": len(data.get("skolkalender", []))} if data.get("skolkalender") else None,
                "lag": lag_st, "lagstrid": meriter.lagstrid_status(data), "lag_marken": meriter.LAG_MARKEN,
                "skola": await _skola_status(hass, barn, parent) if skola.PA else None,
                "amnes_larare": skola.amnes_larare(await hass.async_add_executor_job(skola.las, _dir(hass, barn)), data),
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
                "har_ai": bool(_ai_entitet(hass)) and getattr(hass, "ai", True) is not None if parent else None,  # Windowsappen: hass.ai är None utan vald AI
                **(_foralder_kvittens((await hass.async_add_executor_job(_load_fil, hass.data[DOMAIN]["base"] / "foralder_info.json")).get(user.id)) if parent
                   else {"foralder_info": None}),
                "user_id": user.id,
                "alla_barn": [{"id": b["id"], "namn": b["namn"]} for b in conf["barn"] if not request.get("skolan_bara_barn") or b["id"] == barn] if parent else [],
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
        entity = _ai_entitet(hass)
        if not entity:
            return self.json_message("Ingen AI finns i Home Assistant.", 503)
        instr = LAR_PROMPT.format(djur=d.get("namn") or "Husdjuret", art=d.get("art") or "🐾", vad=vad, term=term, facit=facit, historik=hist,
                                  sista="Det här är sista rundan: om förklaringen fortfarande inte stämmer, berätta snällt vad det betyder. " if runda >= LAR_RUNDOR else "")
        try:
            resp = await _ai_anrop(hass,"ai_task", "generate_data", {"task_name": "Läxspelet lär husdjuret", "entity_id": entity, "instructions": instr},
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


async def _omsorg(hass: HomeAssistant, barn: str, niva: str | None, text: str, kalla: str, data: dict | None = None) -> dict | None:
    """Barnet har skrivit något oroande: hjälp att visa för barnet, och (utom vid våld) en notis till föräldrarna, högst en per nivå och dag."""
    if niva not in omsorg.HJALP:
        return None
    hjalp = dict(omsorg.HJALP[niva])
    namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
    n = omsorg.notis(niva, namn, text, kalla)
    _LOGGER.warning("Läxspelet: omsorg (%s) för %s via %s", niva, namn, kalla)
    if n:
        idag = dt_util.now().date().isoformat()
        sett = hass.data[DOMAIN].setdefault("omsorg_notis", {})
        if sett.get((barn, niva)) != idag:
            sett[(barn, niva)] = idag
            tjanster = _foralder_tjanster(hass, data) if data is not None else list(hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values())
            for tj in tjanster:
                await _notis(hass, tj, *n, f"/skolan?barn={barn}")
        hjalp["hem_meddelad"] = True
    return hjalp


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
    "Frågar barnet varför hen inte fick stjärnor, poäng eller svit: titta i SENASTE STJÄRNORNA, PLUGGDAGAR, VÄNTAR, SKRIVKRAVET, FOTON och GÅTAN och förklara ärligt och vänligt "
    "vad som hände och vad hen kan göra nu (t.ex. 'det väntar på att mamma eller pappa godkänner', 'du behövde 5 rätt men fick 3'). Gissa inte: syns det inte i läget, säg att du inte ser det och föreslå att fråga mamma eller pappa. "
    "Säg aldrig att appen har fel om du inte ser det i läget. "
    "Om du inte vet: säg det ärligt och föreslå 'ℹ️ Så funkar det'. Om frågan inte handlar om spelet eller plugg, svara kort och snällt och styr tillbaka. "
    + plugg.TRYGG_REGEL.replace("{", "{{").replace("}", "}}") + " "
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
        lage = fraga.lage(data) + "\n" + fraga.forklaring(data)
        historik = [x for x in (body.get("historik") or []) if isinstance(x, dict)][-8:]
        hist = "\n".join(f"{'Barnet' if x.get('vem') == 'barn' else 'Du'}: {str(x.get('text') or '')[:400]}" for x in historik)
        hist += f"\nBarnet: {text}"
        entity = _ai_entitet(hass)
        if not entity:
            return self.json_message("Ingen AI finns i Home Assistant.", 503)
        namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
        instr = FRAGA_PROMPT.format(djur=d.get("namn") or "Husdjuret", art=d.get("art") or "🐾", namn=namn, guide=fraga.SPELGUIDE, lage=lage, historik=hist) + intressen.prompt_rad(data)
        instr += "\n" + omsorg.AI_REGEL
        oro = omsorg.bedom(text)  # fast skyddsnät, oberoende av AI:n
        if oro in omsorg.FAST_SVAR:  # akut, hot, våld och farliga frågor skickas aldrig till AI:n
            return self.json({"svar": omsorg.FAST_SVAR[oro], "hjalp": await _omsorg(hass, barn, oro, text, "till husdjuret", data)})
        try:
            resp = await _ai_anrop(hass,"ai_task", "generate_data", {"task_name": "Läxspelet fråga husdjuret", "entity_id": entity, "instructions": instr},
                                                  blocking=True, return_response=True)
            raw = (resp or {}).get("data")
            x = _parse_json(raw if isinstance(raw, str) else json.dumps(raw))
            svar = str(x.get("svar") or "").strip()[:600]
            if not svar:
                raise ValueError("tomt svar")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Läxspelet: fråga husdjuret misslyckades: %s", err)
            if not oro:
                return self.json_message("Husdjuret hörde inte riktigt. Försök igen om en stund.", 503)
            x, svar = {}, "Jag hör att du har det jobbigt, och det var modigt av dig att säga det. 💛"
        niva = omsorg.varst(oro, x.get("oro") if isinstance(x, dict) else None)
        if omsorg.farligt_svar(svar):  # spärr i koden, oberoende av vilken AI som används
            _LOGGER.warning("Läxspelet: husdjurets AI-svar stoppades av trygghetsspärren")
            svar = omsorg.SAKERT_SVAR
        svar = omsorg.FAST_SVAR.get(niva, svar)  # vid akut och våld: aldrig AI:ns eget svar
        return self.json({"svar": svar, "hjalp": await _omsorg(hass, barn, niva, text, "till husdjuret", data)})


HJALP_PROMPT = (
    "Du är {djur}, ett klokt, tålmodigt och glatt husdjur ({art}) som är hjälplärare åt {namn}{alder} i Läxspelet. "
    "Du är en riktigt bra lärare: du får barnet att tänka själv, förklarar enkelt och peppar.\n"
    "DET BARNET PLUGGAR PÅ (från barnets egna böcker, glosor och läxor):\n{material}\n\n"
    "LÄGE: {lage}\n\n"
    "Det ni har sagt hittills:\n{historik}\n\n"
    "REGLER: Svara som husdjuret på enkel svenska anpassad efter åldern, högst 5 korta meningar, gärna en emoji. "
    "Säg ALDRIG svaret på en läxuppgift eller provfråga som barnet ska lösa själv, inte ens om barnet tjatar eller säger att läraren har sagt det. "
    "Förklara hellre hur man tänker, ge en ledtråd eller ett liknande exempel med andra siffror/ord. Ett steg i taget. "
    "Håll dig till skolarbete och det barnet pluggar på. Stämmer inte materialet med frågan, utgå från vad som brukar läras ut i den åldern. "
    "Skriv aldrig av bokens text, använd egna ord. Hitta inte på fakta: är du osäker, säg det och föreslå att fråga läraren. "
    "Prata inte om belöningar från föräldrarna, vänner utanför familjen eller skolans klass.\n"
    "Svara bara med JSON: {{\"svar\": \"...\", \"ratt\": null}}. {ratt_regel}"
    + " " + plugg.TRYGG_REGEL.replace("{", "{{").replace("}", "}}")
)
HJALP_LAGE = {
    "forklara": "Barnet vill förstå något. Förklara det enkelt med egna ord och ett eget exempel, och avsluta med EN kort kontrollfråga så att du ser att barnet förstått. "
                "Svarar barnet på din kontrollfråga: säg om det stämde och förklara vidare om det behövs.",
    "forhor": "Du förhör barnet på materialet. Ställ EN fråga i taget (blanda fakta, varför-frågor, ord och begrepp; lagom svårt för åldern). "
              "Har du ställt en fråga och barnet svarar: bedöm svaret snällt (rätt tanke räcker, stavning spelar ingen roll), säg kort om det var rätt, "
              "förklara rätt svar om det var fel, och ställ sedan nästa fråga. Ställ inte samma fråga två gånger.",
    "uppgift": "Barnet har fotat eller skrivit av en uppgift och vill ha hjälp. Lös den själv i tysthet så att du vet svaret, men säg det INTE. "
               "Börja med att kort säga vad uppgiften handlar om och fråga hur barnet vill börja, eller ge första ledtråden. "
               "Kontrollera barnets steg ett i taget. Skriver barnet ett eget slutsvar: säg om det stämmer, och berömm i så fall.",
}
HJALP_LAGE["las"] = ("Barnet har läst läxans sidor. Prata om boken som en nyfiken kompis: ställ EN öppen fråga i taget (vem, vad, varför, hur kändes det, vad tror du händer sen). "
                     "Bedöm om svaret visar att barnet förstått det som står i sammanfattningarna (egna tankar om varför/vad som händer sen är alltid rätt om de är rimliga). "
                     "Säg kort vad du tycker och ställ nästa fråga.")
HJALP_LAGE["skriv"] = ("Barnet visar en egen text (foto eller inskriven) och vill ha tips. Skriv INTE om texten och skriv inga egna meningar åt barnet. "
                       "Säg först 2 saker som är bra. Ge sedan högst 3 konkreta tips (t.ex. 'kolla stavningen på ordet i rad 2', 'börja ett nytt stycke när ni kommer hem', 'berätta mer om hur det kändes'). "
                       "Peka ut ord som är felstavade men låt barnet rätta själv. Anpassa till åldern och till uppgiften om den står i materialet.")
HJALP_PER_DAG = 80  # AI-frågor per barn och dag


class HjalpView(HomeAssistantView):
    """Plugga med husdjuret: en hjälplärare som utgår från barnets eget material och aldrig säger svaret."""

    url = "/api/skolan/hjalp"
    name = "api:skolan:hjalp"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        bilder: list[Path] = []
        if request.content_type.startswith("multipart/"):
            form = await request.post()
            try:
                body = json.loads(str(form.get("json") or "{}"))
                if form.getall("file", []):
                    bilder = await _ta_emot_filer(hass, form, "hjalp")
            except ValueError as err:
                return self.json_message(str(err), 400)
        else:
            body = await request.json()
        try:
            return await self._svara(hass, request, body if isinstance(body, dict) else {}, bilder)
        finally:
            if bilder:
                await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in bilder])

    async def _svara(self, hass: HomeAssistant, request: web.Request, body: dict, bilder: list[Path]) -> web.Response:
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        lage = body.get("lage") if body.get("lage") in HJALP_LAGE else "forklara"
        text = re.sub(r"\s+", " ", str(body.get("text") or "")).strip()[:3000 if lage == "skriv" else 600]
        if not text and not bilder:
            return self.json_message("Skriv något först.", 400)
        idag = dt_util.now().date().isoformat()
        rakna = hass.data[DOMAIN].setdefault("hjalp_rakna", {})
        if rakna.get("dag") != idag:
            rakna.clear()
            rakna["dag"] = idag
        if rakna.get(barn, 0) >= HJALP_PER_DAG:
            return self.json_message("Husdjuret har pluggat så mycket idag att det somnat. Fortsätt i morgon! 😴", 429)
        rakna[barn] = rakna.get(barn, 0) + 1
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)
        try:
            a = _find(data.get("amnen", []), body.get("amne"))
        except ValueError:
            return self.json_message("Välj ett ämne.", 400)
        u = next((x for x in data.get("uppdrag", []) if x.get("id") == body.get("uppdrag") and x.get("amne") == a["id"]), None)

        def _ebocker() -> dict:
            return {b["id"]: _load_fil(path / "filer" / _ebok_fil(b["id"])).get("cache", {}) for b in a.get("bocker", []) if b.get("sidor")}

        material = fraga.studiematerial(data, a, u, await hass.async_add_executor_job(_ebocker))
        d = meriter._m(data).get("djur") or {}
        historik = [x for x in (body.get("historik") or []) if isinstance(x, dict)][-12:]
        hist = "\n".join(f"{'Barnet' if x.get('vem') == 'barn' else 'Du'}: {str(x.get('text') or '')[:600]}" for x in historik)
        hist += f"\nBarnet: {text or '(skickade en bild på uppgiften)'}" + (" [bild bifogad]" if bilder else "")
        ar = fraga.alder(data)
        namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
        instr = HJALP_PROMPT.format(
            djur=d.get("namn") or "Husdjuret", art=d.get("art") or "🐾", namn=namn, alder=f" ({ar} år)" if ar else "",
            material=material, historik=hist,
            lage=HJALP_LAGE[lage] + (" Bilden är uppgiften barnet behöver hjälp med." if bilder else "")
            + (" Det finns nästan inget material i ämnet: tipsa EN gång (inte varje svar) om att fota boksidorna eller lägga in glosor i ämnet, så kan du hjälpa ännu bättre." if len(material) < 250 and not historik else ""),
            ratt_regel=(("Barnet har läsa-lätt-läge: skriv extra korta och enkla meningar och svåra ord förklarade. " if data.get("lattlast") else "") + "ratt = true om barnets SENASTE meddelande var ett rätt svar på din senaste förhörsfråga, false om det var fel, "
                        "null om det inte var ett svar (t.ex. första gången, eller om barnet bad om en ny fråga)." "Om ratt är false: lägg också till \"fraga\" (din fråga, kort) och \"facit\" (rätt svar, kort) i JSON." if lage in ("forhor", "las") else "ratt ska alltid vara null.")) + plugg.larare_block(data, a["id"])
        instr += intressen.prompt_rad(data) + "\n" + omsorg.AI_REGEL
        oro = omsorg.bedom(text)  # fast skyddsnät, oberoende av AI:n
        if oro in omsorg.FAST_SVAR:  # akut, hot, våld och farliga frågor skickas aldrig till AI:n
            return self.json({"svar": omsorg.FAST_SVAR[oro], "ratt": None,
                              "hjalp": None if foralder else await _omsorg(hass, barn, oro, text, "till hjälpläraren", data)})
        try:
            if bilder:
                raw = await _ai_las(hass, bilder, instr, "Läxspelet hjälpläraren")
            else:
                raw = await _ai_text(hass, instr, "Läxspelet hjälpläraren")
            x = _parse_json(raw)
            svar = str(x.get("svar") or "").strip()[:1200]
            if not svar:
                raise ValueError("tomt svar")
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Läxspelet: hjälpläraren misslyckades: %s", err)
            if not oro:
                return self.json_message("Husdjuret hörde inte riktigt. Försök igen om en stund.", 503)
            x, svar = {}, "Jag hör att du har det jobbigt, och det var modigt av dig att säga det. Läxan kan vänta. 💛"
        niva = omsorg.varst(oro, x.get("oro") if isinstance(x, dict) else None)
        if omsorg.farligt_svar(svar):  # spärr i koden, oberoende av vilken AI som används
            _LOGGER.warning("Läxspelet: hjälplärarens AI-svar stoppades av trygghetsspärren")
            svar = omsorg.SAKERT_SVAR
        svar = omsorg.FAST_SVAR.get(niva, svar)  # vid akut och våld: aldrig AI:ns eget svar
        ratt = x.get("ratt") if lage in ("forhor", "las") and len(historik) >= 1 and not niva else None
        ratt = {"true": True, "false": False}.get(ratt.lower()) if isinstance(ratt, str) else ratt
        ut = {"svar": svar, "ratt": ratt if isinstance(ratt, bool) else None}
        if niva and not foralder:
            ut["hjalp"] = await _omsorg(hass, barn, niva, text, "till hjälpläraren", data)
        if ut["ratt"] is not None and not foralder:
            async with hass.data[DOMAIN]["locks"][barn]:
                data = await hass.async_add_executor_job(_load, path)
                if ut["ratt"]:
                    uu = next((y for y in data.get("uppdrag", []) if u and y.get("id") == u["id"]), None)
                    ut["poang"] = meriter.hjalp_ratt(data, uu)
                else:  # fel svar: tillbaka som svag punkt om några dagar
                    plugg.svag_ny(data, a["id"], u["id"] if u else None, x.get("fraga"), x.get("facit"), "forhor")
                    ut["poang"] = meriter.hjalp_status(data)
                await hass.async_add_executor_job(_save, path, data)
        else:
            ut["poang"] = meriter.hjalp_status(data)
        return self.json(ut)


OMRADEN_PROMPT = (
    "Du hjälper {namn}{alder} att förbereda sig för ett prov.\nProv: {prov}. Provtyp: {typ}.\nVad som ska ingå (enligt läraren eller barnet): {omfattning}\n"
    "Material i ämnet:\n{material}\n{bild}"
    "Dela upp det provet handlar om i 3–8 områden med korta namn (t.ex. 'Bråk: förlänga och förkorta', 'Fotosyntesen', 'Verb i presens'), i den ordning de brukar läras ut. "
    "info = en kort mening om vad området innehåller. Ta bara med sådant som hör till provet. Skriv inte av bokens text. "
    'Svara ENDAST med JSON: {{"omraden": [{{"namn": "...", "info": "..."}}], "omfattning": "..."}}. '
    "omfattning = om en bild är bifogad: kort vad som står där om provet (mål, kapitel, sidor, datum), annars tom text."
)
PLAN_PROMPT = (
    "Du är en skicklig och varm studiecoach. Gör en PERSONLIG pluggplan för {namn}{alder} inför ett prov.\n"
    "Prov: {prov}, datum {datum} (idag är {idag}). Provtyp: {typ}. Barnets mål: {mal}.\n"
    "Vad som ska ingå: {omfattning}\n"
    "Områden och hur säker barnet känner sig: {omraden}\n"
    "Så pluggar barnet bäst: {profil}\n"
    "Pluggdagar (använd BARA dessa datum): {dagar}. Ungefär {min} min per dag.\n"
    "Annat barnet har samma period: {andra}\n"
    "Material i ämnet:\n{material}\n\n"
    "TIDIGARE PLANER OCH RESULTAT (lär av dem):\n{historik}\n\n"
    "FÖRÄLDRARNAS ÖNSKEMÅL (förslag, inte order: väg in dem, men barnets bästa och barnets egna svar går först): {foralder}\n\n"
    "Se över tidigare planer: vilka typer av delar gör barnet och vilka hoppas över, hur mycket hinns faktiskt med, vad gav bra provresultat? "
    "Förbättra den nya planen utifrån det (t.ex. kortare pass om barnet ofta missar, mer av det som fungerar, mer övning i det som gick dåligt).\n"
    "REGLER: Lägg mest tid på det barnet inte kan eller är osäkert på, mindre på det barnet redan kan. Först förstå/läsa, sedan öva, sedan repetera. "
    "Låt områden komma tillbaka efter några dagar (spridd repetition). Sista pluggdagen: ett övningsprov (typ ovningsprov) och lätt repetition, inget nytt. "
    "Anpassa delarna efter hur barnet lär sig bäst och efter målet (högre mål = lite mer och svårare övning). 1–3 delar per dag, sammanlagt ungefär {min} min, mindre de dagar barnet har annat. "
    "Färre pluggdagar än områden: slå ihop. Gör 'vad' mycket konkret (t.ex. 'Läs s. 34–37 och skriv 3 viktiga saker', 'Be husdjuret förhöra dig på fotosyntesen', 'Förklara för mamma eller pappa hur ...'). "
    "Typer: las, forhor (husdjuret förhör i appen), ovningsprov (i appen), repetera (svaga punkter i appen), uppgifter, glosor, sammanfatta, forklara. "
    "Glosförhör: mest glosor och forhor. Muntligt: mycket forklara. Inlämning: bygg arbetet steg för steg (planera, skriva, förbättra) i stället för övningsprov. Skriv inte av bokens text.\n"
    'Svara ENDAST med JSON: {{"delar": [{{"dag": "ÅÅÅÅ-MM-DD", "titel": "kort", "vad": "konkret instruktion", "min": 15, "typ": "las", "omrade": "områdets namn exakt"}}], "tips": "en kort peppande mening till barnet", '
    '"tankar": "till FÖRÄLDRARNA, 2–5 meningar: dina tankar om barnets studietaktik utifrån tidigare planer, resultat och profil, vad du ändrat i den här planen och varför, hur du vägt in föräldrarnas önskemål (och var du gjort annorlunda och varför), och hur föräldrarna kan stötta"}}'
)
OVNINGSPROV_PROMPT = (
    "Gör ett övningsprov för {namn}{alder} inför provet \"{prov}\" ({typ}).\nOmråden och hur säker barnet är: {omraden}\nMaterial:\n{material}\n\n"
    "{antal} frågor, som på ett riktigt prov och lagom svåra för åldern. Fler frågor om områden barnet är osäkert på. "
    "Blanda korta frågor (svar med några ord eller en mening) och några flervalsfrågor (3–4 alternativ, facit exakt likadant som ett av alternativen). "
    "I matte: räkneuppgifter med ett tydligt svar. Bygg på materialet, men skriv inte av bokens text. "
    'Svara ENDAST med JSON: {{"fragor": [{{"fraga": "...", "facit": "kort rätt svar", "alternativ": [], "omrade": "områdets namn exakt"}}]}}'
)
RATTA_PROMPT = (
    "Rätta ett övningsprov för ett barn{alder}. För varje fråga: ratt = true om svaret visar rätt kunskap "
    "(stavning och ordval spelar ingen roll, rätt kärna räcker), annars false. kommentar = en kort, snäll förklaring till barnet: "
    "vid fel varför och vad som är rätt, vid rätt ett kort beröm eller tillägg.\n{fragor}\n"
    'Svara ENDAST med JSON: {{"bedomning": [{{"ratt": true, "kommentar": "..."}}]}} med lika många objekt som frågor, i samma ordning.'
)
RAPPORT_PROMPT = (
    "Skriv en kort veckorapport från Läxspelet till föräldrarna om {namn}{alder}. Var varm, ärlig och konkret. Överdriv inte och hitta inte på något som inte står i underlaget.\n"
    "UNDERLAG:\n{underlag}\n\n"
    'Svara ENDAST med JSON: {{"sammanfattning": "2–3 meningar", "bra": ["vad som gått bra"], "svart": ["vad som verkar svårt eller behöver mer övning"], '
    '"kommande": ["viktigt nästa vecka"], "tips": ["1–3 sätt föräldrarna kan hjälpa"], '
    '"middagsfragor": ["3 nyfikna frågor om innehållet barnet pluggat på, som man kan ställa vid middagen (inte förhör)"], '
    '"studietaktik": "3–6 meningar: dina tankar om barnets studietaktik (hur och när barnet pluggar, vad som fungerar och inte, mönster i planer och resultat) och konkreta förbättringar"}}. Tomma listor om underlaget saknas.'
)


COACH_PROMPT = (
    "Du är en klok, varm och kunnig studiecoach i Läxspelet. Du pratar med en förälder till {namn}{alder}. "
    "Föräldern vill förstå och påverka barnets studietaktik. Du ger råd och förklarar, men barnets bästa går först: säg ifrån snällt om något verkar för hårt eller kan ta bort lusten.\n"
    "STUDIEPROFIL (barnets egna svar): {profil}\nFÖRÄLDRARNAS ÖNSKEMÅL NU: {onskemal}\n"
    "PLANER OCH PROV:\n{historik}\n\nSENASTE VECKAN:\n{vecka}\n\n"
    "Det ni har sagt hittills:\n{samtal}\n\n"
    "REGLER: Svara på svenska, konkret och kort (högst 6 meningar eller en kort lista). Hitta inte på något om barnet som inte står ovan; säg om du inte vet. "
    "Om föräldern vill ändra hur planerna ska göras (t.ex. mer/mindre strikt, mer läsning, kortare pass): föreslå nya önskemål i onskemal, annars null. "
    "strikthet är mild, lagom eller strang; text är föräldrarnas önskemål i en kort mening eller två (ta med det som redan gäller om det fortfarande stämmer).\n"
    'Svara ENDAST med JSON: {{"svar": "...", "onskemal": null}} eller {{"svar": "...", "onskemal": {{"strikthet": "lagom", "text": "..."}}}}'
)


HANDSTIL_PROMPT = (
    "Du är en snäll och kunnig lärare i handstil för ett barn{alder} i en svensk skola. Bilden visar barnets handstil{vad}. "
    "Bedöm bara handstilen, inte stavning eller innehåll: bokstävernas form (t.ex. rund a, o, d, g), att de sitter på linjen, "
    "rätt höjd (små bokstäver lika höga, långa bokstäver som l, h, k, d, b högre, g, j, p, y går ner under linjen), jämna mellanrum mellan bokstäver och ord, och hur lätt det är att läsa. "
    "Var uppmuntrande och konkret, anpassat till åldern. Om bilden inte visar handstil: poang 0 och säg det vänligt i bra.\n"
    'Svara ENDAST med JSON: {{"poang": 0-100, "bra": ["1–2 saker som är bra"], "tips": ["1–3 konkreta tips, t.ex. \'stäng ringen i a\'"], '
    '"ova": ["högst 4 bokstäver som behöver övas, som enskilda tecken"], "pepp": "en kort peppande mening"}}'
)


SKRIV_TEMAN = ["en rolig dag i skolan", "ett äventyr i skogen", "ett husdjur som kan prata", "en resa till månen", "en snöig vinterdag", "ett hemligt rum",
               "en fotbollsmatch", "en dag på stranden", "en robot som blir kompis", "ett mystiskt paket", "en drake som är rädd för mörker", "en utflykt med klassen"]
TECKEN_PROMPT = (
    "Skriv en kort, rolig text på svenska som ett barn{alder} ska öva skiljetecken på. Tema: {tema}.\n"
    "Nivå: {niva_namn}. {niva_info}\n"
    "Regler: 4–7 meningar, ord som passar åldern. Texten ska vara helt korrekt med rätt stora bokstäver. "
    "Använd BARA dessa tecken: {tecken} (varje tecken minst en gång om det går){repliker}. Inga citattecken, parenteser, siffror eller förkortningar. "
    "Gärna några namn (stor bokstav).\n"
    'Svara ENDAST med JSON: {{"text": "..."}}'
)
STYCKEN_PROMPT = (
    "Skriv en kort text på svenska för ett barn{alder} som ska öva på styckeindelning. Tema: {tema}. "
    "3–4 stycken med 2–4 meningar var. Varje nytt stycke ska börja av ett tydligt skäl: ny tid, ny plats, nytt delämne eller att någon ny börjar prata. "
    'Svara ENDAST med JSON: {{"rubrik": "...", "stycken": [["mening 1", "mening 2"], ["..."]], "varfor": ["kort förklaring till barnet varför stycke 2 börjar där", "... stycke 3", "..."]}}'
)
FRITT_UPPGIFT_PROMPT = (
    "Hitta på EN rolig skrivuppgift på svenska för ett barn{alder}. Den ska gå att skriva på 10–20 minuter. "
    "Barnet behöver mest öva på: {fokus}. Välj en uppgift där det kommer till nytta (t.ex. en berättelse med repliker för talstreck, en text i flera delar för stycken). "
    'Svara ENDAST med JSON: {{"uppgift": "själva uppgiften i 1–2 meningar", "tips": ["2–3 korta tips om hur man gör, särskilt om {fokus}"]}}'
)
FRITT_BEDOM_PROMPT = (
    "Du är en snäll och skicklig svensklärare. Ett barn{alder} har skrivit en text. Uppgiften var: {uppgift}\n"
    "BARNETS TEXT:\n\"\"\"{text}\"\"\"\n{forra}"
    "Ge feedback på SKRIVANDET så att barnet blir tryggt och bra på att uttrycka sig. Bedöm 0–100: tecken (punkt, frågetecken, utropstecken, komma, talstreck), "
    "stor (stor bokstav i början av meningar och på namn), mellanrum (mellanslag efter tecken och mellan ord), stycken (nytt stycke vid ny tid, plats eller händelse), "
    "struktur (början, mitten och slut), ordval (beskrivande och varierade ord), meningar (variation i längd och hur de börjar). "
    "Säg 2 saker som är bra. Ge 2–3 konkreta tips och citera kort det ställe det gäller. Skriv INTE om texten och skriv inga nya meningar åt barnet; barnet ska rätta själv. "
    "Stavning nämns bara kort om samma fel återkommer. Anpassa till åldern och var uppmuntrande.\n"
    'Svara ENDAST med JSON: {{"poang": 0-100, "omraden": {{"tecken": 0, "stor": 0, "mellanrum": 0, "stycken": 0, "struktur": 0, "ordval": 0, "meningar": 0}}, '
    '"bra": ["..."], "tips": [{{"tips": "...", "citat": "kort citat ur texten"}}], "battre": "vad som blivit bättre sedan förra versionen, annars tom", "pepp": "en kort peppande mening"}}'
)


class SkrivView(HomeAssistantView):
    """Skrivverkstad: teckenövning, styckeövning och fritt skrivande med AI-feedback."""

    url = "/api/skolan/skriv"
    name = "api:skolan:skriv"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        path = _dir(hass, barn)
        lock = hass.data[DOMAIN]["locks"][barn]
        data = await hass.async_add_executor_job(_load, path)
        ar = fraga.alder(data)
        alder = f" ({ar} år)" if ar else ""
        op = body.get("op")
        d = meriter._m(data).get("djur") or {}
        tema = random.choice(SKRIV_TEMAN + ([f"husdjuret {d['namn']} {d['art']}"] if d.get("namn") else []))

        async def ai(prompt: str, uppgift: str) -> dict:
            try:
                x = _parse_json(await _ai_text(hass, prompt, uppgift))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Läxspelet: skrivverkstad: %s", err)
                raise web.HTTPServiceUnavailable(text=json.dumps({"message": "AI:n svarar inte just nu. Försök igen om en stund."}), content_type="application/json") from err
            if not isinstance(x, dict):
                raise web.HTTPServiceUnavailable(text=json.dumps({"message": "AI:n svarade konstigt. Försök igen."}), content_type="application/json")
            return x

        async def spara(fn):
            async with lock:
                dd = await hass.async_add_executor_job(_load, path)
                ut = fn(dd)
                await hass.async_add_executor_job(_save, path, dd)
                return ut

        try:
            if op == "tecken_ny":
                n = skriv.niva(data, ar)
                nv = skriv.NIVAER[n]
                x = await ai(TECKEN_PROMPT.format(alder=alder, tema=tema, niva_namn=nv["namn"], niva_info=nv["info"], tecken=" ".join(nv["tecken"]),
                                                  repliker=" och talstreck (–) först i repliker" if n >= 4 else ""), "Läxspelet skrivövning")
                text = re.sub(r"\s+", " ", str(x.get("text") or "")).strip()[:900]
                if len(text.split()) < 8:
                    return self.json_message("AI:n skrev för kort text. Försök igen.", 503)
                ov = {**skriv.ovning_tecken(text, n), "id": skriv.ny_id(), "typ": "tecken", "niva": n}
                await spara(lambda dd: skriv._s(dd).__setitem__("aktiv", ov))
                return self.json({"id": ov["id"], "typ": "tecken", "visa": ov["visa"], "niva": n, "niva_namn": nv["namn"], "niva_info": nv["info"]})
            if op == "stycken_ny":
                x = await ai(STYCKEN_PROMPT.format(alder=alder, tema=tema), "Läxspelet styckeövning")
                st = [[re.sub(r"\s+", " ", str(m)).strip()[:300] for m in s_ if str(m).strip()] for s_ in (x.get("stycken") or []) if isinstance(s_, list)]
                st = [s_ for s_ in st if s_][:5]
                if len(st) < 2:
                    return self.json_message("AI:n kunde inte göra någon text. Försök igen.", 503)
                meningar, starter = [], []
                for s_ in st:
                    if meningar:
                        starter.append(len(meningar))
                    meningar += s_
                ov = {"id": skriv.ny_id(), "typ": "stycken", "rubrik": str(x.get("rubrik") or "")[:80], "meningar": meningar, "starter": starter,
                      "varfor": [str(v)[:200] for v in (x.get("varfor") or [])][:5]}
                await spara(lambda dd: skriv._s(dd).__setitem__("aktiv", ov))
                return self.json({"id": ov["id"], "typ": "stycken", "rubrik": ov["rubrik"], "meningar": meningar})
            if op == "ratta":
                ov = skriv._s(data).get("aktiv") or {}
                if ov.get("id") != body.get("id"):
                    return self.json_message("Övningen är för gammal. Gör en ny!", 400)
                if ov["typ"] == "tecken":
                    res = skriv.ratta_tecken(ov, str(body.get("svar") or "")[:3000])
                else:
                    res = {**skriv.ratta_stycken(ov, body.get("val") or []), "meningar": ov["meningar"], "varfor": ov.get("varfor", [])}

                def _r(dd):
                    skriv._s(dd).pop("aktiv", None)
                    if foralder:
                        return 0
                    return skriv.spara_resultat(dd, ov["typ"], res["poang"], res["omraden"], ar, ov.get("rubrik") or ov.get("text", "")[:40])
                res["p"] = await spara(_r)
                return self.json(res)
            if op == "fritt_uppgift":
                st = skriv.status(data, ar)["omraden"]
                svagast = sorted(st.items(), key=lambda kv: kv[1]["snitt"])[:1]
                fokus = svagast[0][1]["namn"].lower() if svagast else "punkt och stor bokstav"
                x = await ai(FRITT_UPPGIFT_PROMPT.format(alder=alder, fokus=fokus) + intressen.prompt_rad(data), "Läxspelet skrivuppgift")
                return self.json({"uppgift": str(x.get("uppgift") or "")[:300], "tips": [str(t)[:200] for t in (x.get("tips") or [])][:3], "fokus": fokus})
            if op == "fritt_bedom":
                text = str(body.get("text") or "").strip()[:4000]
                if len(text.split()) < 15:
                    return self.json_message("Skriv lite mer först, minst ett par meningar.", 400)
                forra = str(body.get("forra") or "").strip()[:4000]
                x = await ai(FRITT_BEDOM_PROMPT.format(alder=alder, uppgift=str(body.get("uppgift") or "fritt skrivande")[:300], text=text,
                                                       forra=f"FÖRRA VERSIONEN (jämför och säg vad som blivit bättre):\n\"\"\"{forra}\"\"\"\n" if forra else "")
                             + plugg.larare_block(data, plugg.amne_svenska(data)), "Läxspelet skrivfeedback")
                omr = {k: max(0, min(100, int(v))) for k, v in (x.get("omraden") or {}).items() if k in skriv.OMRADEN and str(v).lstrip("-").isdigit()}
                poang = max(0, min(100, int(x.get("poang") or 0))) if str(x.get("poang") or "0").isdigit() else round(sum(omr.values()) / max(1, len(omr)))
                tips = [{"tips": str(t.get("tips") or "")[:240], "citat": str(t.get("citat") or "")[:160]} for t in (x.get("tips") or []) if isinstance(t, dict)][:3]
                ut = {"poang": poang, "omraden": omr, "bra": [str(b)[:200] for b in (x.get("bra") or [])][:2], "tips": tips,
                      "battre": str(x.get("battre") or "")[:300], "pepp": str(x.get("pepp") or "")[:200], "p": 0}
                forra_p = body.get("forra_poang")
                typ = "forbattrad" if forra and isinstance(forra_p, int) and poang > forra_p else "fritt"
                if not foralder:
                    ut["p"] = await spara(lambda dd: skriv.spara_resultat(dd, typ if typ == "forbattrad" else "fritt", poang, omr, ar, text[:40]))
                return self.json(ut)
        except web.HTTPException as err:
            if err.content_type == "application/json":
                return web.json_response(json.loads(err.text), status=err.status)
            raise
        return self.json_message("Okänd åtgärd.", 400)


PENNA_UPPDRAG_PROMPT = (
    "Hitta på TRE olika skrivuppdrag på svenska som ett barn{alder} ska skriva FÖR HAND med penna på papper. "
    "Barnet tycker att skriva är tråkigt, så uppdragen MÅSTE kännas roliga, lockande och lätta att komma igång med: busiga, fantasifulla, "
    "om barnet självt, dess intressen eller husdjuret i spelet, gärna med en twist (t.ex. 'Du vaknar och är 5 cm lång. Vad gör du först?'). Aldrig skoligt eller som ett prov. "
    "Längd: {info} (ungefär {mal} ord). Typerna ska vara olika, t.ex.: {typer}. Barnet ska kunna skriva direkt utan att leta fakta.{djur}\n"
    'Svara ENDAST med JSON: {{"val": [{{"uppgift": "uppdraget i 1–2 meningar, riktat till barnet", "ikon": "en emoji", "tips": ["1 kort tips för att komma igång"]}}, {{...}}, {{...}}]}}'
)
PENNA_BEDOM_PROMPT = (
    "Bilden ska visa ett barns{alder} text skriven FÖR HAND på papper till uppdraget: \"{uppgift}\" (ungefär {mal} ord).\n"
    "1) handskrivet: true bara om texten är skriven för hand med penna eller blyerts på papper. false om det är en skärm, tryckt text, en bok eller ingen text. "
    "2) text: skriv av barnets text så exakt det går, med barnets egen stavning och egna tecken. "
    "3) ord: antal ord i texten. 4) passar: 0–100, hur väl texten svarar på uppdraget. "
    "5) handstil: 0–100, hur lätt det är att läsa. 6) tecken: 0–100, punkt och stor bokstav. "
    "7) bra: 1–2 saker som är bra (om innehållet eller skrivandet). 8) tips: 1 litet konkret tips till nästa gång. 9) pepp: en kort peppande mening. "
    "10) djur: vad husdjuret {djur} säger när det har läst texten: max 2 meningar, glatt och nyfiket, nämn något KONKRET ur texten (en detalj, en rolig idé), gärna en fråga eller ett skämt. "
    "Var snäll och uppmuntrande, anpassat till åldern. Barnet tycker att skriva är jobbigt, så lyft det som är bra.\n"
    'Svara ENDAST med JSON: {{"handskrivet": true, "text": "...", "ord": 0, "passar": 0, "handstil": 0, "tecken": 0, "bra": ["..."], "tips": ["..."], "pepp": "...", "djur": "..."}}'
)


class PennaView(HomeAssistantView):
    """Pennuppdrag: barnet skriver för hand, fotar papperet och AI:n läser och bedömer."""

    url = "/api/skolan/penna"
    name = "api:skolan:penna"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        bilder: list[Path] = []
        if request.content_type.startswith("multipart/"):
            form = await request.post()
            try:
                body = json.loads(str(form.get("json") or "{}"))
                bilder = await _ta_emot_filer(hass, form, "penna")
            except ValueError as err:
                return self.json_message(str(err), 400)
        else:
            body = await request.json()
        try:
            return await self._op(hass, request, body if isinstance(body, dict) else {}, bilder)
        finally:
            if bilder:
                await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in bilder])

    async def _op(self, hass: HomeAssistant, request: web.Request, body: dict, bilder: list[Path]) -> web.Response:
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        path = _dir(hass, barn)
        lock = hass.data[DOMAIN]["locks"][barn]
        data = await hass.async_add_executor_job(_load, path)
        ar = fraga.alder(data)
        alder = f" ({ar} år)" if ar else ""
        op = body.get("op")
        if op in ("godkann", "underkann"):
            if not foralder:
                raise web.HTTPForbidden
            async with lock:
                data = await hass.async_add_executor_job(_load, path)
                try:
                    x = penna.foralder_andra(data, str(body.get("id")), op == "godkann")
                except ValueError as err:
                    return self.json_message(str(err), 400)
                await hass.async_add_executor_job(_save, path, data)
            return self.json(x)
        if foralder:
            return self.json_message("Pennuppdragen gör barnet själv. Ni kan se och underkänna inlämningarna.", 403)
        if op == "nytt":
            st = penna.status(data)
            if st["val"] and not body.get("byt"):
                return self.json({"val": st["val"]})
            d = meriter._m(data).get("djur") or {}
            info = penna.STEG[st["steg"]]
            typer = random.sample(penna.TYPER, 3)
            try:
                x = _parse_json(await _ai_text(hass, PENNA_UPPDRAG_PROMPT.format(
                    alder=alder, info=info["info"], mal=info["mal"], typer="; ".join(typer),
                    djur=f" Barnets husdjur i spelet heter {d['namn']} och är en {d['art']}." if d.get("namn") else "") + intressen.prompt_rad(data), "Läxspelet pennuppdrag"))
                val = [{"uppgift": str(v.get("uppgift") or "").strip()[:300], "ikon": str(v.get("ikon") or "🖊️")[:4],
                        "tips": [str(t)[:160] for t in (v.get("tips") or [])][:1], "typ": typer[i] if i < 3 else ""}
                       for i, v in enumerate(x.get("val") or []) if isinstance(v, dict) and str(v.get("uppgift") or "").strip()][:3]
                if not val:
                    raise ValueError("tomt")
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Läxspelet: pennuppdrag: %s", err)
                return self.json_message("AI:n kunde inte hitta på uppdrag just nu. Försök igen om en stund.", 503)
            async with lock:
                data = await hass.async_add_executor_job(_load, path)
                try:
                    val = penna.satt_val(data, val, bool(body.get("byt")))
                except ValueError as err:
                    return self.json_message(str(err), 400)
                await hass.async_add_executor_job(_save, path, data)
            return self.json({"val": val})
        if op == "valj":
            st = penna.status(data)
            egen = re.sub(r"\s+", " ", str(body.get("egen") or "")).strip()[:120]
            if egen:
                v = {"uppgift": f"Skriv om något du själv har valt: {egen}", "tips": ["Börja med det roligaste!"], "typ": "eget ämne"}
            else:
                try:
                    v = (st["val"] or [])[int(body.get("i"))]
                except (TypeError, ValueError, IndexError):
                    return self.json_message("Välj ett av uppdragen.", 400)
            async with lock:
                data = await hass.async_add_executor_job(_load, path)
                akt = penna.satt_aktiv(data, v["uppgift"], v.get("tips", []), v.get("typ", ""), False)
                await hass.async_add_executor_job(_save, path, data)
            return self.json(akt)
        if op == "lamna":
            akt = penna.status(data)["aktiv"]
            if not akt:
                return self.json_message("Hämta ett pennuppdrag först.", 400)
            if not bilder:
                return self.json_message("Fota papperet först.", 400)
            innehall = await hass.async_add_executor_job(bilder[0].read_bytes)
            hash_ = hashlib.sha256(innehall).hexdigest()
            if penna.dubblett(data, hash_, ""):
                return self.json_message("Det här fotot har redan lämnats in. Skriv en ny text!", 400)
            try:
                x = _parse_json(await _ai_las(hass, bilder[:1], PENNA_BEDOM_PROMPT.format(alder=alder, uppgift=akt["uppgift"], mal=penna.STEG[akt["steg"]]["mal"],
                                                                                  djur=f"{(meriter._m(data).get('djur') or {}).get('namn', '')} ({(meriter._m(data).get('djur') or {}).get('art', '🐾')})".strip()),
                                              "Läxspelet pennuppdrag bedöm"))
                if not isinstance(x, dict):
                    raise ValueError("konstigt svar")
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Läxspelet: pennuppdrag bedöm: %s", err)
                return self.json_message("AI:n kunde inte läsa fotot just nu. Försök igen om en stund.", 503)
            tal = lambda k: max(0, min(100, int(x.get(k) or 0))) if str(x.get(k) or "0").lstrip("-").isdigit() else 0  # noqa: E731
            bed = {"handskrivet": x.get("handskrivet") is True or str(x.get("handskrivet")).lower() == "true", "text": str(x.get("text") or "")[:3000],
                   "ord": tal("ord") if "ord" in x else 0, "passar": tal("passar"), "handstil": tal("handstil"), "tecken": tal("tecken"),
                   "bra": [str(b)[:200] for b in (x.get("bra") or [])][:2], "tips": [str(t)[:200] for t in (x.get("tips") or [])][:2], "pepp": str(x.get("pepp") or "")[:200],
                   "djur": str(x.get("djur") or "")[:300]}
            bed["ord"] = int(x.get("ord") or 0) if str(x.get("ord") or "").isdigit() else len(bed["text"].split())
            skal = penna.dubblett(data, hash_, bed["text"])
            if skal:
                return self.json_message(skal, 400)
            fil = f"penna_{hash_[:12]}{bilder[0].suffix.lower() or '.jpg'}"
            async with lock:
                data = await hass.async_add_executor_job(_load, path)
                await hass.async_add_executor_job(shutil.copyfile, bilder[0], path / "filer" / fil)
                await hass.async_add_executor_job(_krymp_bild, path / "filer" / fil)
                ut = penna.lamna_in(data, bed, fil, hash_)
                await hass.async_add_executor_job(_save, path, data)
            return self.json(ut)
        return self.json_message("Okänd åtgärd.", 400)


class HandstilView(HomeAssistantView):
    """Handstil: AI bedömer en bild (ritad i appen eller ett foto av papper)."""

    url = "/api/skolan/handstil"
    name = "api:skolan:handstil"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        form = await request.post()
        try:
            body = json.loads(str(form.get("json") or "{}"))
            bilder = await _ta_emot_filer(hass, form, "handstil")
        except ValueError as err:
            return self.json_message(str(err), 400)
        try:
            barn = _barn_for(hass, request, body.get("barn"))
            foralder = _ar_foralder(hass, request)
            path = _dir(hass, barn)
            data = await hass.async_add_executor_job(_load, path)
            ar = fraga.alder(data)
            text = re.sub(r"\s+", " ", str(body.get("text") or "")).strip()[:120]
            typ = "foto" if body.get("typ") == "foto" else "skriv"
            prompt = HANDSTIL_PROMPT.format(alder=f" ({ar} år)" if ar else "", vad=f". Barnet skulle skriva: \"{text}\"" if text else "")
            try:
                x = _parse_json(await _ai_las(hass, bilder[:1], prompt, "Läxspelet handstil"))
                poang = max(0, min(100, int(x.get("poang") or 0)))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Läxspelet: handstil misslyckades: %s", err)
                return self.json_message("AI:n kunde inte titta på bilden just nu. Försök igen om en stund.", 503)
            lista = lambda k, n: [str(v)[:160] for v in (x.get(k) or []) if str(v).strip()][:n]  # noqa: E731
            ut = {"poang": poang, "bra": lista("bra", 2), "tips": lista("tips", 3), "ova": [str(v)[:2] for v in (x.get("ova") or [])][:4],
                  "pepp": str(x.get("pepp") or "")[:200], "p": 0}
            if not foralder and poang > 0:
                async with hass.data[DOMAIN]["locks"][barn]:
                    data = await hass.async_add_executor_job(_load, path)
                    ut["p"] = meriter.handstil_klar(data, typ, poang, text or "(foto)", {"ova": ut["ova"], "tips": ut["tips"][:2]})
                    await hass.async_add_executor_job(_save, path, data)
            return self.json(ut)
        finally:
            await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in bilder])


# ---------- barnets två hem: ett hem-system har kontot, det andra kopplas dit ----------
def _hem_fil(hass: HomeAssistant) -> Path:
    return hass.data[DOMAIN]["base"] / "hemlankar.json"


def _hem_extern_url(hass: HomeAssistant) -> str | None:
    try:
        from homeassistant.helpers.network import get_url

        return get_url(hass, allow_internal=False, allow_ip=False, prefer_cloud=True)
    except Exception:  # noqa: BLE001  (Windows: tunneladressen)
        return getattr(hass.config, "external_url", None) or os.environ.get("SKOLAN_EXTERN_URL") or None


def _hem_lank(url: str, token: str, barn_namn: str) -> str:
    import base64

    return "LXS1." + base64.urlsafe_b64encode(json.dumps({"u": url, "t": token, "n": barn_namn}, ensure_ascii=False).encode()).decode().rstrip("=")


def _hem_las_lank(text: str) -> dict:
    import base64

    m = re.search(r"LXS1\.([A-Za-z0-9_\-]+)", text or "")
    if not m:
        raise ValueError("Det där ser inte ut som en länk från Läxspelet. Den börjar med LXS1.")
    b = m.group(1)
    d = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
    if not re.fullmatch(r"https?://[^\s]+", str(d.get("u") or "")) or len(str(d.get("t") or "")) < 30:
        raise ValueError("Länken är ofullständig.")
    return d


def _adressbok_amne(token: str) -> tuple[str, bytes]:
    h = hashlib.sha256(("adr:" + token).encode()).hexdigest()
    return "lxs-" + h[:32], hashlib.sha256(("nyckel:" + token).encode()).digest()


async def _adressbok_skicka(hass: HomeAssistant) -> None:
    """Hem-systemet berättar sin nuvarande adress (krypterat) så att det andra hemmet hittar hit om adressen byts."""
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    url = _hem_extern_url(hass)
    lankar = (await hass.async_add_executor_job(_load_fil, _hem_fil(hass))).get("lankar", {})
    if not url or not lankar:
        return
    session = async_get_clientsession(hass)
    for token in lankar:
        amne, nyckel = _adressbok_amne(token)
        nonce = os.urandom(12)
        ct = AESGCM(nyckel).encrypt(nonce, json.dumps({"u": url, "tid": int(time.time())}).encode(), None)
        try:
            async with session.post(f"https://ntfy.sh/{amne}", data=base64.b64encode(nonce + ct), timeout=20):
                pass
        except Exception as err:  # noqa: BLE001
            _LOGGER.info("Läxspelet: adressboken svarade inte: %s", err)


async def _adressbok_hamta(hass: HomeAssistant, token: str) -> str | None:
    import base64

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    amne, nyckel = _adressbok_amne(token)
    try:
        async with async_get_clientsession(hass).get(f"https://ntfy.sh/{amne}/json?poll=1&since=12h", timeout=20) as r:
            rader = (await r.text()).strip().splitlines()
        for rad in reversed(rader):
            x = json.loads(rad)
            if x.get("event") == "message":
                b = base64.b64decode(x["message"])
                return json.loads(AESGCM(nyckel).decrypt(b[:12], b[12:], None))["u"]
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("Läxspelet: kunde inte läsa adressboken: %s", err)
    return None


class HemkopplingView(HomeAssistantView):
    """Föräldrar: koppla ett barn mellan två hem (länk från hem-systemet, klistras in i det andra)."""

    url = "/api/skolan/hemkoppling"
    name = "api:skolan:hemkoppling"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden

        def _las():
            lankar = _load_fil(_hem_fil(hass)).get("lankar", {})
            ut = []
            for b in hass.data[DOMAIN]["conf"]["barn"]:
                fj = _load_fil(_dir(hass, b["id"]) / "fjarr.json")
                ut.append({"id": b["id"], "namn": b["namn"],
                           "lankar": [{"token": t[:8], "namn": l.get("namn"), "skapad": l.get("skapad"), "senast": l.get("senast")} for t, l in lankar.items() if l["barn"] == b["id"]],
                           "fjarr": {"hem": fj.get("hem"), "url": fj.get("url"), "kopplad": fj.get("kopplad"), "senast": fj.get("senast"),
                                     "moln": {"typ": fj["moln"]["typ"], "mapp": fj["moln"].get("mapp"), "url": fj["moln"].get("url"), "anv": fj["moln"].get("anv"),
                                              "kopia": fj.get("moln_kopia")} if fj.get("moln") else None} if fj.get("token") else None})
            return ut
        return self.json({"barn": await hass.async_add_executor_job(_las), "extern": _hem_extern_url(hass)})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden
        body = await request.json()
        op = body.get("op")
        conf = hass.data[DOMAIN]["conf"]
        b = next((x for x in conf["barn"] if x["id"] == body.get("barn")), None)
        try:
            if op == "skapa":
                if not b:
                    raise ValueError("Välj ett barn.")
                url = _hem_extern_url(hass)
                if not url:
                    raise ValueError("Det här Läxspelet saknar en adress utanför hemmet. I Windows: slå på Fjärråtkomst under ⚙️ Inställningar. "
                                     "I Home Assistant: Nabu Casa eller en egen extern adress behövs.")
                token = secrets.token_urlsafe(32)

                def _s():
                    d = _load_fil(_hem_fil(hass))
                    d.setdefault("lankar", {})[token] = {"barn": b["id"], "namn": plugg._txt(body.get("namn"), 40) or "Andra hemmet",
                                                         "skapad": dt_util.now().isoformat(timespec="minutes")}
                    _save_fil(_hem_fil(hass), d)
                await hass.async_add_executor_job(_s)
                hass.async_create_task(_adressbok_skicka(hass))
                return self.json({"lank": _hem_lank(url, token, b["namn"])})
            if op == "ta_bort_lank":
                def _t():
                    d = _load_fil(_hem_fil(hass))
                    d["lankar"] = {t: l for t, l in d.get("lankar", {}).items() if not (t.startswith(str(body.get("token") or "-")) and l["barn"] == body.get("barn"))}
                    _save_fil(_hem_fil(hass), d)
                await hass.async_add_executor_job(_t)
                return self.json({})
            if op == "koppla":
                if not b:
                    raise ValueError("Välj vilket barn här som länken gäller.")
                d = _hem_las_lank(str(body.get("lank") or ""))
                from homeassistant.helpers.aiohttp_client import async_get_clientsession

                try:  # prova att länken fungerar
                    async with async_get_clientsession(hass).get(f"{d['u'].rstrip('/')}/api/skolan/hem/{d['t']}/state", headers={"X-Lxs-Roll": "foralder"}, timeout=30) as r:
                        if r.status != 200:
                            raise ValueError(f"Det andra hemmets Läxspelet svarade {r.status}. Be dem skapa en ny länk.")
                        st = await r.json()
                except ValueError:
                    raise
                except Exception as err:  # noqa: BLE001
                    raise ValueError("Får ingen kontakt med det andra hemmets Läxspelet. Är den datorn igång och har fjärråtkomst?") from err
                info = {"url": d["u"], "token": d["t"], "hem": plugg._txt(body.get("hem"), 40) or f"{st.get('namn') or d.get('n')}s andra hem",
                        "kopplad": dt_util.now().isoformat(timespec="minutes"), "hem_barn": st.get("barn")}
                await hass.async_add_executor_job(_save_fil, _dir(hass, b["id"]) / "fjarr.json", info)
                return self.json({"ok": True})
            if op == "moln":  # det andra hemmet: var hem-systemets backuper finns, om det inte svarar
                if not b:
                    raise ValueError("Välj barn.")
                fil = _dir(hass, b["id"]) / "fjarr.json"
                k = await hass.async_add_executor_job(_load_fil, fil)
                if not k.get("token"):
                    raise ValueError("Barnet är inte kopplat till ett annat hem.")
                typ = body.get("typ")
                if typ == "av":
                    k.pop("moln", None)
                else:
                    gammal = k.get("moln") or {}
                    m = {"typ": "webdav" if typ == "webdav" else "mapp", "mapp": str(body.get("mapp") or "").strip()[:300],
                         "url": str(body.get("url") or "").strip()[:300], "anv": str(body.get("anv") or "").strip()[:200],
                         "losen": str(body.get("losen") or "") or gammal.get("losen", ""), "backup_losen": str(body.get("backup_losen") or "") or gammal.get("backup_losen", "")}
                    if not m["backup_losen"]:
                        raise ValueError("Skriv lösenordet som backuperna är krypterade med.")
                    if m["typ"] == "mapp" and not m["mapp"]:
                        raise ValueError("Skriv vilken mapp backuperna finns i.")
                    if m["typ"] == "webdav" and not m["url"].startswith("https://"):
                        raise ValueError("Molnadressen ska börja med https://")
                    k["moln"] = m
                await hass.async_add_executor_job(_save_fil, fil, k)
                if typ != "av":
                    try:
                        await _moln_kopia(hass, b["id"], tvinga=True)
                    except Exception as err:  # noqa: BLE001
                        return self.json_message(f"Sparat, men backupen gick inte att läsa: {err}", 400)
                return self.json({"ok": True})
            if op == "koppla_bort":
                if b:
                    await hass.async_add_executor_job(lambda: (_dir(hass, b["id"]) / "fjarr.json").unlink(missing_ok=True))
                return self.json({})
        except ValueError as err:
            return self.json_message(str(err), 400)
        return self.json_message("Okänd åtgärd.", 400)


class HemView(HomeAssistantView):
    """Hem-systemet: tar emot anrop från barnets andra hem. Hemlig länk per barn, bara det barnet och bara barn-/läxfunktioner."""

    url = "/api/skolan/hem/{token}/{rest:.*}"
    name = "api:skolan:hem"
    requires_auth = False

    async def _hantera(self, request: web.Request, token: str, rest: str) -> web.StreamResponse:
        import hmac
        from types import SimpleNamespace

        hass: HomeAssistant = request.app["hass"]
        lankar = (await hass.async_add_executor_job(_load_fil, _hem_fil(hass))).get("lankar", {})
        l = next((x for t, x in lankar.items() if hmac.compare_digest(t, token)), None)
        if not l:
            raise web.HTTPNotFound
        cls = next((c for c in HEM_VYER if c.url == f"/api/skolan/{rest}"), None)
        fn = getattr(cls(), request.method.lower(), None) if cls else None
        if not fn:
            raise web.HTTPNotFound
        conf = hass.data[DOMAIN]["conf"]
        barn = next((b for b in conf["barn"] if b["id"] == l["barn"]), None)
        if not barn:
            raise web.HTTPNotFound
        foralder = request.headers.get("X-Lxs-Roll") == "foralder"
        uid = (conf["foraldrar"][0] if conf["foraldrar"] else "") if foralder else barn["user_id"]
        ny = request.clone(rel_url=request.rel_url.with_path(f"/api/skolan/{rest}"))
        ny["hass_user"] = SimpleNamespace(id=uid, name=l.get("namn") or "Andra hemmet", is_admin=False)
        ny["skolan_bara_barn"] = barn["id"]
        ny["ha_authenticated"] = True
        if (l.get("senast") or "")[:13] != dt_util.now().isoformat()[:13]:
            def _s():
                d = _load_fil(_hem_fil(hass))
                if token in d.get("lankar", {}):
                    d["lankar"][token]["senast"] = dt_util.now().isoformat(timespec="minutes")
                    _save_fil(_hem_fil(hass), d)
            await hass.async_add_executor_job(_s)
        return await fn(ny)

    async def get(self, request: web.Request, token: str, rest: str) -> web.StreamResponse:
        return await self._hantera(request, token, rest)

    async def post(self, request: web.Request, token: str, rest: str) -> web.StreamResponse:
        return await self._hantera(request, token, rest)


async def _fjarr_state(hass: HomeAssistant, barn: str) -> dict:
    """Barnets state från hem-systemet (för notiser i det andra hemmet)."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    k = await hass.async_add_executor_job(_load_fil, _dir(hass, barn) / "fjarr.json")
    async with async_get_clientsession(hass).get(f"{k['url'].rstrip('/')}/api/skolan/hem/{k['token']}/state", headers={"X-Lxs-Roll": "foralder"}, timeout=60) as r:
        if r.status != 200:
            raise RuntimeError(f"svarade {r.status}")
        return await r.json()


class BoendeView(HomeAssistantView):
    """Växelvis boende: schema (föräldrar) och var sakerna finns (alla)."""

    url = "/api/skolan/boende"
    name = "api:skolan:boende"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        op = body.get("op")
        path = _dir(hass, barn)
        alla = list(hass.data[DOMAIN]["conf"].get("foraldrar", []))
        if op in ("spara", "undantag", "undantag_bort") and not foralder:
            raise web.HTTPForbidden
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                if op == "spara":
                    boende.spara(data, body, alla)
                elif op == "undantag":
                    boende.undantag(data, str(body.get("fran") or ""), str(body.get("till") or ""), str(body.get("hem") or ""))
                elif op == "undantag_bort":
                    boende.undantag(data, "", "", "", bort=str(body.get("id") or ""))
                elif op in ("sak_ny", "sak_flytta", "sak_bort"):
                    boende.sak(data, op, body)
                else:
                    raise ValueError("Okänd åtgärd.")
            except ValueError as err:
                return self.json_message(str(err), 400)
            await hass.async_add_executor_job(_save, path, data)
        return self.json({"boende": boende.status(data, await _foralder_namn(hass) if foralder else {})})


async def _moln_kopia(hass: HomeAssistant, barn: str, tvinga: bool = False) -> Path:
    """Hämta barnets konto ur hem-systemets senaste molnbackup (högst var 3:e timme). Returnerar mappen."""
    import aiohttp
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    base = hass.data[DOMAIN]["base"]
    fil = _dir(hass, barn) / "fjarr.json"
    k = await hass.async_add_executor_job(_load_fil, fil)
    m = k.get("moln") or {}
    mal = base / ".moln" / barn
    if not tvinga and (k.get("moln_kopia") or {}).get("hamtad", "") > (dt_util.now() - timedelta(hours=3)).isoformat() and mal.is_dir():
        return mal
    tmp = base / ".moln-tmp"
    await hass.async_add_executor_job(lambda: tmp.mkdir(parents=True, exist_ok=True))
    if m.get("typ") == "webdav":
        session = async_get_clientsession(hass)
        auth = aiohttp.BasicAuth(m.get("anv", ""), m.get("losen", ""))
        url = m["url"].rstrip("/")
        async with session.request("PROPFIND", url + "/", auth=auth, headers={"Depth": "1"}, timeout=aiohttp.ClientTimeout(total=60)) as r:
            if r.status >= 400:
                raise RuntimeError(f"molnet svarade {r.status}")
            namn = sorted(set(re.findall(r"(laxspelet-[^<>/\"]+?\.(?:zip|laxspelet))", await r.text())))
        if not namn:
            raise RuntimeError("hittade ingen backup i molnet")
        senaste = tmp / Path(namn[-1]).name
        async with session.get(f"{url}/{namn[-1]}", auth=auth, timeout=aiohttp.ClientTimeout(total=1800)) as r:
            if r.status != 200:
                raise RuntimeError(f"molnet svarade {r.status}")
            with senaste.open("wb") as f:
                async for bit in r.content.iter_chunked(1 << 20):
                    await hass.async_add_executor_job(f.write, bit)
    else:
        def _hitta():
            filer = sorted([f for f in Path(m.get("mapp", "")).glob("laxspelet-*") if f.suffix in (".zip", ".laxspelet")], key=lambda f: f.stat().st_mtime)
            if not filer:
                raise RuntimeError("hittade ingen backup i mappen")
            return filer[-1]
        senaste = await hass.async_add_executor_job(_hitta)

    def _packa_upp():
        manifest, zipf = backup.oppna(senaste, m.get("backup_losen") or None, tmp)
        ids = [x["id"] for x in manifest["barn"]]
        hem_barn = k.get("hem_barn") if k.get("hem_barn") in ids else (ids[0] if len(ids) == 1 else None)
        if not hem_barn:
            raise RuntimeError("backupen innehåller inte barnet")
        shutil.rmtree(mal, ignore_errors=True)
        backup.aterstall(zipf, base / ".moln", {hem_barn: barn}, False)
        for f in tmp.glob("*"):
            f.unlink(missing_ok=True)
        return manifest.get("skapad")
    skapad = await hass.async_add_executor_job(_packa_upp)
    kk = await hass.async_add_executor_job(_load_fil, fil)
    kk["moln_kopia"] = {"hamtad": dt_util.now().isoformat(timespec="minutes"), "skapad": skapad}
    await hass.async_add_executor_job(_save_fil, fil, kk)
    return mal


class FjarrView(HomeAssistantView):
    """Det andra hemmet: skickar barnets anrop vidare till hem-systemet (och visar en sparad kopia om det inte svarar)."""

    url = "/api/skolan/fjarr/{rest:.*}"
    name = "api:skolan:fjarr"

    async def _vidare(self, request: web.Request, rest: str) -> web.StreamResponse:
        import aiohttp
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        fil = _dir(hass, barn) / "fjarr.json"
        k = await hass.async_add_executor_job(_load_fil, fil)
        if not k.get("token") or not re.fullmatch(r"[a-z_]+", rest):
            raise web.HTTPNotFound
        params = [(a, b) for a, b in request.query.items() if a not in ("barn", "authSig")]
        data = await request.read()
        headers = {"X-Lxs-Roll": "foralder" if _ar_foralder(hass, request) else "barn"}
        if data and request.headers.get("Content-Type"):
            headers["Content-Type"] = request.headers["Content-Type"]
        session = async_get_clientsession(hass)
        for forsok in (0, 1):
            try:
                async with session.request(request.method, f"{k['url'].rstrip('/')}/api/skolan/hem/{k['token']}/{rest}", params=params,
                                           data=data or None, headers=headers, timeout=aiohttp.ClientTimeout(total=180)) as r:
                    innehall = await r.read()
                    typ = r.headers.get("Content-Type", "application/octet-stream")
                    if r.status == 404 and rest == "state":
                        return self.json_message("Kopplingen till det andra hemmet är borttagen där. Be dem skapa en ny länk.", 410)
                    if rest == "state" and r.status == 200 and request.method == "GET" and not params:
                        def _cache():
                            kk = _load_fil(fil)
                            kk["cache"] = json.loads(innehall)
                            kk["senast"] = dt_util.now().isoformat(timespec="minutes")
                            _save_fil(fil, kk)
                        await hass.async_add_executor_job(_cache)
                    return web.Response(body=innehall, status=r.status, headers={"Content-Type": typ, "Cache-Control": r.headers.get("Cache-Control", "no-store")})
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if forsok == 0:
                    ny = await _adressbok_hamta(hass, k["token"])
                    if ny and ny != k["url"]:
                        k["url"] = ny
                        await hass.async_add_executor_job(_save_fil, fil, {**await hass.async_add_executor_job(_load_fil, fil), "url": ny})
                        continue
                break
        if k.get("moln") and request.method == "GET" and rest in ("state", "fil", "ebok"):
            try:  # läs ur hem-systemets senaste molnbackup
                mapp = await _moln_kopia(hass, barn)
                kk = await hass.async_add_executor_job(_load_fil, fil)
                ny = request.clone(rel_url=request.rel_url.with_path(f"/api/skolan/{rest}"))
                ny["skolan_bara_barn"] = barn
                tok = _MAPP_ANNAN.set((barn, mapp))
                try:
                    vy = {"state": StateView, "fil": FileView, "ebok": EbokView}[rest]()
                    svar = await vy.get(ny)
                finally:
                    _MAPP_ANNAN.reset(tok)
                if rest == "state" and svar.status == 200:
                    return self.json({**json.loads(svar.body), "offline": f"molnbackupen {(kk.get('moln_kopia') or {}).get('skapad') or ''}".strip()})
                return svar
            except Exception as err:  # noqa: BLE001
                _LOGGER.info("Läxspelet: molnkopian gick inte att läsa: %s", err)
        if rest == "state" and request.method == "GET" and k.get("cache"):
            return self.json({**k["cache"], "offline": k.get("senast") or True})
        return self.json_message("Det andra hemmets Läxspelet svarar inte just nu (datorn kan vara avstängd). Försök igen senare.", 503)

    async def get(self, request: web.Request, rest: str) -> web.StreamResponse:
        return await self._vidare(request, rest)

    async def post(self, request: web.Request, rest: str) -> web.StreamResponse:
        return await self._vidare(request, rest)


# ---------- backup och flytt ----------
def _backup_inst_fil(hass: HomeAssistant) -> Path:
    return hass.data[DOMAIN]["base"] / "backup.json"


def _backup_std_mapp() -> str:
    if os.name == "nt":
        od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
        return str(Path(od or Path.home() / "Documents") / "Läxspelet backup")
    return "/share/laxspelet-backup"


def _backup_inst_las(hass: HomeAssistant) -> dict:
    d = _load_fil(_backup_inst_fil(hass))
    d.setdefault("auto", False)
    d.setdefault("mal", "mapp")
    d.setdefault("mapp", _backup_std_mapp())
    d.setdefault("behall", 7)
    d.setdefault("webdav", {})
    return d


def _backup_publik(d: dict) -> dict:
    w = d.get("webdav") or {}
    return {"auto": d["auto"], "mal": d["mal"], "mapp": d["mapp"], "behall": d["behall"], "har_losen": bool(d.get("losen")),
            "webdav": {"url": w.get("url", ""), "anv": w.get("anv", ""), "har_losen": bool(w.get("losen"))}, "senast": d.get("senast"),
            "windows": os.name == "nt", "std_mapp": _backup_std_mapp()}


async def _webdav_skicka(hass: HomeAssistant, fil: Path, w: dict, behall: int) -> None:
    import aiohttp
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    url = w["url"].rstrip("/")
    auth = aiohttp.BasicAuth(w.get("anv", ""), w.get("losen", ""))
    async with session.request("MKCOL", url + "/", auth=auth) as r:
        if r.status not in (201, 405, 301, 302):
            if r.status in (401, 403):
                raise RuntimeError("Molnet sa nej till inloggningen. Kolla användarnamn och lösenord (ofta ett särskilt app-lösenord).")

    async def bitar():
        with fil.open("rb") as f:
            while True:
                b = await hass.async_add_executor_job(f.read, 1 << 20)
                if not b:
                    break
                yield b
    async with session.put(f"{url}/{fil.name}", data=bitar(), auth=auth, headers={"Content-Length": str(fil.stat().st_size)},
                           timeout=aiohttp.ClientTimeout(total=3600)) as r:
        if r.status not in (200, 201, 204):
            raise RuntimeError(f"Molnet svarade {r.status} när backupen skickades.")
    try:  # rensa gamla backuper i molnet
        async with session.request("PROPFIND", url + "/", auth=auth, headers={"Depth": "1"}) as r:
            text = await r.text()
        namn = sorted(set(re.findall(r"(laxspelet-[^<>/\"]+?\.(?:zip|laxspelet))", text)))
        for gammal in namn[:-max(1, behall)]:
            async with session.delete(f"{url}/{gammal}", auth=auth):
                pass
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("Läxspelet: kunde inte rensa gamla backuper i molnet: %s", err)


async def _backup_kor(hass: HomeAssistant, inst: dict) -> dict:
    """Gör en backup av hela familjen och skicka den dit föräldern valt."""
    base = hass.data[DOMAIN]["base"]
    barn = [{"id": b["id"], "namn": b["namn"]} for b in hass.data[DOMAIN]["conf"]["barn"]]
    try:
        if not inst.get("losen"):
            raise RuntimeError("Välj ett lösenord för backuperna först.")
        if inst["mal"] == "webdav":
            if not (inst.get("webdav") or {}).get("url"):
                raise RuntimeError("Fyll i adressen till molnet (WebDAV).")
            fil = await hass.async_add_executor_job(backup.skapa, base, barn, base / ".backup-ut", inst["losen"], VERSION, "auto")
            try:
                await _webdav_skicka(hass, fil, inst["webdav"], inst["behall"])
            finally:
                await hass.async_add_executor_job(fil.unlink, True)
            var = "molnet"
        else:
            mapp = Path(inst["mapp"])
            fil = await hass.async_add_executor_job(backup.skapa, base, barn, mapp, inst["losen"], VERSION, "auto")
            await hass.async_add_executor_job(backup.rensa, mapp, inst["behall"])
            var = str(mapp)
        res = {"tid": dt_util.now().isoformat(timespec="minutes"), "ok": True, "text": f"Backup sparad i {var}: {fil.name} ({round(fil.stat().st_size / 1e6, 1) if fil.exists() else '–'} MB)."}
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Läxspelet: backup misslyckades: %s", err)
        res = {"tid": dt_util.now().isoformat(timespec="minutes"), "ok": False, "text": f"Backupen misslyckades: {err}"}
        for tjanst in hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values():
            await _notis(hass, tjanst, "💾 Läxspelets backup misslyckades", res["text"][:200], "/skolan")

    def _spara():
        d = _backup_inst_las(hass)
        d["senast"] = res
        _save_fil(_backup_inst_fil(hass), d)
    await hass.async_add_executor_job(_spara)
    return res


class BackupView(HomeAssistantView):
    """Föräldrar: ladda ner backup, återställ/flytta från en backup, automatisk backup till mapp eller moln."""

    url = "/api/skolan/backup"
    name = "api:skolan:backup"

    def _kraver(self, hass, request) -> None:
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden

    async def get(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        self._kraver(hass, request)
        namn = Path(request.query.get("hamta") or "").name
        f = hass.data[DOMAIN]["base"] / ".backup-ut" / namn
        if namn:
            if not await hass.async_add_executor_job(f.is_file):
                raise web.HTTPNotFound
            return web.FileResponse(f, headers={"Content-Disposition": f'attachment; filename="{namn}"', "Cache-Control": "no-store"})
        inst = await hass.async_add_executor_job(_backup_inst_las, hass)

        def _storlek():
            ut = []
            for b in hass.data[DOMAIN]["conf"]["barn"]:
                m = hass.data[DOMAIN]["base"] / b["id"] / "filer"
                filer = [x for x in m.glob("*") if x.is_file()] if m.is_dir() else []
                stora = sum(1 for x in filer if x.suffix.lower() in (".jpg", ".jpeg") and x.stat().st_size >= 450_000)
                ut.append({"id": b["id"], "namn": b["namn"], "mb": round(sum(x.stat().st_size for x in filer) / 1e6, 1), "stora": stora})
            return ut
        return self.json({"inst": _backup_publik(inst), "barn": [{"id": b["id"], "namn": b["namn"]} for b in hass.data[DOMAIN]["conf"]["barn"]],
                          "storlek": await hass.async_add_executor_job(_storlek)})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        self._kraver(hass, request)
        base = hass.data[DOMAIN]["base"]
        tmp = base / ".backup-in"
        q = request.query
        if q.get("op") == "del":  # uppladdning i bitar (stora backuper)
            uid = re.sub(r"[^a-f0-9]", "", q.get("id", ""))[:32]
            if len(uid) < 16:
                raise web.HTTPBadRequest
            bit = await request.read()
            n = int(q.get("n") or 0)

            def _skriv():
                tmp.mkdir(parents=True, exist_ok=True)
                for gammal in tmp.glob("*"):
                    if gammal.stat().st_mtime < time.time() - 86400:
                        gammal.unlink(missing_ok=True)
                with (tmp / uid).open("wb" if n == 0 else "ab") as f:
                    f.write(bit)
            await hass.async_add_executor_job(_skriv)
            return self.json({"ok": True})
        body = await request.json()
        op = body.get("op")
        try:
            if op == "skapa":
                ids = [b for b in hass.data[DOMAIN]["conf"]["barn"] if body.get("barn") in (None, "alla", b["id"])]
                losen = str(body.get("losen") or "") or None
                ut = base / ".backup-ut"

                def _gor():
                    if ut.exists():
                        for g in ut.glob("laxspelet-*"):
                            g.unlink(missing_ok=True)
                    return backup.skapa(base, [{"id": b["id"], "namn": b["namn"]} for b in ids], ut, losen, VERSION, "manuell")
                fil = await hass.async_add_executor_job(_gor)
                return self.json({"fil": fil.name, "mb": round(fil.stat().st_size / 1e6, 1)})
            if op == "las":
                uid = re.sub(r"[^a-f0-9]", "", str(body.get("id") or ""))[:32]
                fil = tmp / uid
                if not uid or not await hass.async_add_executor_job(fil.is_file):
                    raise ValueError("Filen kom inte fram. Försök igen.")
                try:
                    m, zipf = await hass.async_add_executor_job(backup.oppna, fil, str(body.get("losen") or "") or None, tmp)
                except PermissionError as err:
                    return self.json({"krypterad": True, "message": str(err)})
                hass.data[DOMAIN]["backup_zip"] = {"id": uid, "zip": zipf}
                return self.json({"manifest": m, "lokala": [{"id": b["id"], "namn": b["namn"]} for b in hass.data[DOMAIN]["conf"]["barn"]]})
            if op == "aterstall":
                b = hass.data[DOMAIN].get("backup_zip") or {}
                if b.get("id") != body.get("id") or not b.get("zip"):
                    raise ValueError("Läs in backupfilen igen.")
                lokala = {x["id"] for x in hass.data[DOMAIN]["conf"]["barn"]}
                karta = {str(k): str(v) for k, v in (body.get("karta") or {}).items() if v in lokala}
                if not karta:
                    raise ValueError("Välj vilket barn i det här systemet som varje barn i backupen ska bli.")
                if len(set(karta.values())) != len(karta):
                    raise ValueError("Två barn i backupen kan inte bli samma barn här.")
                locks = [hass.data[DOMAIN]["locks"][v] for v in karta.values()]
                for lk in locks:
                    await lk.acquire()
                try:
                    klara = await hass.async_add_executor_job(backup.aterstall, b["zip"], base, karta, bool(body.get("gemensamt")))
                finally:
                    for lk in locks:
                        lk.release()

                def _stada():
                    for f in tmp.glob("*"):
                        f.unlink(missing_ok=True)
                await hass.async_add_executor_job(_stada)
                hass.data[DOMAIN].pop("backup_zip", None)
                return self.json({"klara": klara})
            if op == "installningar":
                def _inst():
                    d = _backup_inst_las(hass)
                    d["auto"] = bool(body.get("auto"))
                    d["mal"] = "webdav" if body.get("mal") == "webdav" else "mapp"
                    if str(body.get("mapp") or "").strip():
                        d["mapp"] = str(body["mapp"]).strip()[:300]
                    d["behall"] = max(1, min(60, int(body.get("behall") or 7)))
                    if body.get("losen"):
                        if len(str(body["losen"])) < 6:
                            raise ValueError("Lösenordet behöver minst 6 tecken.")
                        d["losen"] = str(body["losen"])[:200]
                    w = d.setdefault("webdav", {})
                    if "webdav_url" in body:
                        u = str(body.get("webdav_url") or "").strip()[:300]
                        if u and not u.startswith("https://"):
                            raise ValueError("Molnadressen ska börja med https://")
                        w["url"] = u
                    if "webdav_anv" in body:
                        w["anv"] = str(body.get("webdav_anv") or "").strip()[:200]
                    if body.get("webdav_losen"):
                        w["losen"] = str(body["webdav_losen"])[:300]
                    if d["auto"] and not d.get("losen"):
                        raise ValueError("Välj ett lösenord för backuperna först.")
                    _save_fil(_backup_inst_fil(hass), d)
                    return d
                return self.json({"inst": _backup_publik(await hass.async_add_executor_job(_inst))})
            if op == "krymp":
                if (await hass.async_add_executor_job(_load_fil, base / "pagaende_ebocker.json")).get("jobb"):
                    raise ValueError("En e-bok håller på att göras just nu. Försök igen om en stund.")
                res = {}
                for b in hass.data[DOMAIN]["conf"]["barn"]:
                    async with hass.data[DOMAIN]["locks"][b["id"]]:
                        res[b["namn"]] = await hass.async_add_executor_job(_krymp_mapp, base / b["id"] / "filer")
                return self.json({"res": res})
            if op == "nu":
                inst = await hass.async_add_executor_job(_backup_inst_las, hass)
                res = await _backup_kor(hass, inst)
                return self.json({"res": res, "inst": _backup_publik(await hass.async_add_executor_job(_backup_inst_las, hass))})
        except ValueError as err:
            return self.json_message(str(err), 400)
        return self.json_message("Okänd åtgärd.", 400)


PROVANALYS_PROMPT = (
    "Bilderna visar ett RÄTTAT prov för ett barn{alder} i {amne} (\"{prov}\"). Läs lärarens rättning: bockar, kryss, poäng, betyg och kommentarer. "
    "Skriv inte av hela provet. Områden barnet pluggade på: {omraden}.\n"
    'Svara ENDAST med JSON: {{"poang": tal eller null, "max": tal eller null, "betyg": "A–F" eller null, '
    '"omraden": [{{"namn": "område (använd gärna samma namn som ovan)", "ratt": antal rätt, "fel": antal fel}}], '
    '"fel": [{{"fraga": "kort sammanfattning av frågan barnet missade", "ratt_svar": "kort rätt svar", "omrade": "område"}}], '
    '"bra": ["1–2 saker som gick bra"], "ova": ["2–3 saker att öva mer på"], '
    '"sammanfattning": "2 peppande meningar till barnet om hur det gick och vad som är nästa steg"}}. '
    "Hittar du inget prov på bilderna: tom omraden och sammanfattning som säger det."
)
P_PROVANALYS = 5


class PlanView(HomeAssistantView):
    """Pluggplan inför prov, övningsprov, svaga punkter, studieprofil och veckorapport."""

    url = "/api/skolan/plan"
    name = "api:skolan:plan"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        bilder: list[Path] = []
        try:
            if request.content_type.startswith("multipart/"):
                form = await request.post()
                body = json.loads(str(form.get("json") or "{}"))
                if form.getall("file", []):
                    bilder = await _ta_emot_filer(hass, form, "plan")
            else:
                body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Fel format.")
            return self.json(await self._op(hass, request, body, bilder))
        except ValueError as err:
            return self.json_message(str(err), 400)
        except RuntimeError as err:
            _LOGGER.warning("Läxspelet: pluggplan: %s", err)
            return self.json_message(str(err), 503)
        finally:
            if bilder:
                await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in bilder])

    async def _ai(self, hass: HomeAssistant, prompt: str, uppgift: str, bilder: list[Path] | None = None) -> dict:
        try:
            raw = await (_ai_las(hass, bilder, prompt, uppgift) if bilder else _ai_text(hass, prompt, uppgift))
            x = _parse_json(raw)
        except Exception as err:  # noqa: BLE001
            raise RuntimeError(f"AI:n svarade inte ({err}). Försök igen om en stund.") from err
        if not isinstance(x, dict):
            raise RuntimeError("AI:n svarade konstigt. Försök igen.")
        return x

    async def _op(self, hass: HomeAssistant, request: web.Request, body: dict, bilder: list[Path]) -> dict:
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        op = body.get("op")
        path = _dir(hass, barn)
        lock = hass.data[DOMAIN]["locks"][barn]
        namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
        data = await hass.async_add_executor_job(_load, path)
        ar = fraga.alder(data)
        alder = f" ({ar} år)" if ar else ""

        async def spara(fn):
            async with lock:
                d = await hass.async_add_executor_job(_load, path)
                ut = fn(d)
                await hass.async_add_executor_job(_save, path, d)
                return ut

        def prov(d: dict) -> dict:
            u = next((x for x in d.get("uppdrag", []) if x.get("id") == body.get("uppdrag")), None)
            if not u or u.get("typ") != "prov":
                raise ValueError("Provet finns inte.")
            return u

        async def material(u: dict) -> str:
            a = next((x for x in data.get("amnen", []) if x["id"] == u.get("amne")), None)
            if not a:
                return "(inget material)"
            eb = await hass.async_add_executor_job(lambda: {b["id"]: _load_fil(path / "filer" / _ebok_fil(b["id"])).get("cache", {}) for b in a.get("bocker", []) if b.get("sidor")})
            return fraga.studiematerial(data, a, u, eb, 6000)

        if op == "profil":
            return {"profil": await spara(lambda d: plugg.profil_spara(d, body))}
        if op == "kalenderlank":  # föräldrar: hemlig prenumerationslänk till familjens kalender
            if not foralder:
                raise web.HTTPForbidden

            def _k(d):
                if body.get("ny") or not d.get("kal_nyckel"):
                    d["kal_nyckel"] = secrets.token_urlsafe(24)
                return d["kal_nyckel"]
            nyckel = await spara(_k)
            bas = _hem_extern_url(hass) or (getattr(hass.config, "internal_url", None) or "")
            return {"url": f"{bas.rstrip('/')}/api/skolan/plankalender/{nyckel}.ics" if bas else f"/api/skolan/plankalender/{nyckel}.ics", "extern": bool(_hem_extern_url(hass))}
        if op == "svag_svar":
            return await spara(lambda d: plugg.svag_svar(d, str(body.get("id")), bool(body.get("kunde"))))
        if op == "onskemal":
            if not foralder:
                raise web.HTTPForbidden
            return {"onskemal": await spara(lambda d: plugg.onskemal_spara(d, body, request["hass_user"].name))}
        if op in ("riktlinje_ny", "riktlinje_bort"):
            if not foralder:
                raise web.HTTPForbidden
            if op == "riktlinje_bort":
                await spara(lambda d: plugg.riktlinje_bort(d, str(body.get("id"))))
                return {}
            a = next((x for x in data.get("amnen", []) if x["id"] == body.get("amne")), None)
            return {"riktlinje": await spara(lambda d: plugg.riktlinje_ny(d, a["id"] if a else "", a["namn"] if a else "Alla ämnen",
                                                                            body.get("text"), "foralder", request["hass_user"].name))}
        if op == "coach":
            if not foralder:
                raise web.HTTPForbidden
            text = plugg._txt(body.get("text"), 800)
            if not text:
                raise ValueError("Skriv något först.")
            hist = [x for x in body.get("historik") or [] if isinstance(x, dict)][-12:]
            samtal = "\n".join(f"{'Föräldern' if x.get('vem') == 'jag' else 'Du'}: {plugg._txt(x.get('text'), 800)}" for x in hist) + f"\nFöräldern: {text}"
            x = await self._ai(hass, COACH_PROMPT.format(namn=namn, alder=alder, profil=plugg.profil_text(plugg.profil(data, ar)), onskemal=plugg.onskemal_text(data),
                                                         historik=plugg.plan_historik(data), vecka=plugg.vecko_underlag(data, namn), samtal=samtal)
                                 + plugg.larare_block(data) + ("\nOm föräldern vill något som går emot lärarens riktlinjer: säg det vänligt och föreslå att de pratar med läraren." if plugg.riktlinjer(data) else ""),
                                 "Läxspelet studiecoach")
            o = x.get("onskemal") if isinstance(x.get("onskemal"), dict) else None
            if o:
                o = {"strikthet": o.get("strikthet") if o.get("strikthet") in plugg.STRIKTHET else plugg.onskemal(data)["strikthet"], "text": plugg._txt(o.get("text"), 800)}
            return {"svar": str(x.get("svar") or "").strip()[:2000] or "Jag förstod inte riktigt, kan du säga det på ett annat sätt?", "onskemal": o}
        if op == "rapport":
            if not foralder:
                raise web.HTTPForbidden
            vecka = dt_util.now().strftime("%G-%V")
            gammal = data.get("veckorapport") or {}
            if gammal.get("vecka") == vecka and not body.get("ny"):
                return gammal
            x = await self._ai(hass, RAPPORT_PROMPT.format(namn=namn, alder=alder, underlag=plugg.vecko_underlag(data, namn) + "\nPLUGGPLANER OCH PROV:\n" + plugg.plan_historik(data) + "\nSTUDIEPROFIL: " + plugg.profil_text(plugg.profil(data, ar)) + "\nFÖRÄLDRARNAS ÖNSKEMÅL: " + plugg.onskemal_text(data)), "Läxspelet veckorapport")
            rap = {k: ([str(v)[:300] for v in x.get(k) or []][:6] if k not in ("sammanfattning", "studietaktik") else str(x.get(k) or "")[:1500])
                   for k in ("sammanfattning", "bra", "svart", "kommande", "tips", "middagsfragor", "studietaktik")}
            ut = {"vecka": vecka, "skapad": dt_util.now().isoformat(timespec="minutes"), "rapport": rap}
            await spara(lambda d: d.__setitem__("veckorapport", ut))
            return ut

        u = prov(data)
        if op == "provanalys":  # fota det rättade provet: AI:n läser rättningen, felen blir svaga punkter
            if not bilder:
                raise ValueError("Fota provet först.")
            a = next((x for x in data.get("amnen", []) if x["id"] == u.get("amne")), {})
            x = await self._ai(hass, PROVANALYS_PROMPT.format(alder=alder, amne=a.get("namn") or u.get("amne_namn") or "", prov=u["namn"],
                                                              omraden=", ".join(o["namn"] for o in (u.get("plan") or {}).get("omraden", [])) or "okänt"),
                               "Läxspelet provanalys", bilder[:6])
            tal = lambda v: float(v) if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d+(\.\d+)?", v)) else None  # noqa: E731
            an = {"tid": dt_util.now().isoformat(timespec="minutes"), "av": "förälder" if foralder else "barnet",
                  "poang": tal(x.get("poang")), "max": tal(x.get("max")), "betyg": str(x.get("betyg") or "").upper()[:1] if str(x.get("betyg") or "").upper()[:1] in meriter.PROV_BETYG else None,
                  "omraden": [{"namn": plugg._txt(o.get("namn"), 60), "ratt": int(tal(o.get("ratt")) or 0), "fel": int(tal(o.get("fel")) or 0)}
                              for o in (x.get("omraden") or []) if isinstance(o, dict) and o.get("namn")][:10],
                  "fel": [{"fraga": plugg._txt(f.get("fraga"), 200), "ratt_svar": plugg._txt(f.get("ratt_svar"), 200), "omrade": plugg._txt(f.get("omrade"), 60)}
                          for f in (x.get("fel") or []) if isinstance(f, dict) and f.get("fraga")][:20],
                  "bra": [plugg._txt(b_, 200) for b_ in (x.get("bra") or [])][:2], "ova": [plugg._txt(b_, 200) for b_ in (x.get("ova") or [])][:3],
                  "sammanfattning": plugg._txt(x.get("sammanfattning"), 400)}

            def _s(d):
                uu = prov(d)
                uu["provanalys"] = an
                for f in an["fel"]:
                    plugg.svag_ny(d, uu["amne"], uu["id"], f["fraga"], f["ratt_svar"], "prov")
                omr = {o["namn"].lower(): o for o in (uu.get("plan") or {}).get("omraden", [])}
                for o in an["omraden"]:
                    if o["namn"].lower() in omr and o["ratt"] + o["fel"]:
                        andel = o["ratt"] / (o["ratt"] + o["fel"])
                        omr[o["namn"].lower()]["kan"] = 2 if andel >= 0.8 else 1 if andel >= 0.5 else 0
                p_ = 0
                if foralder and not uu.get("resultat") and (an["betyg"] or (an["poang"] is not None and an["max"])):
                    res = {"kommentar": "Läst av AI från foto", "av": request["hass_user"].name, "tid": an["tid"]}
                    res.update({"betyg": an["betyg"]} if an["betyg"] and not an["max"] else {"poang": an["poang"], "max": an["max"]})
                    meriter.prov_resultat(d, uu, res)
                elif not foralder and meriter.ge(d, P_PROVANALYS, f"📸 Lärde sig av provet {uu['namn'][:40]}", f"provanalys:{uu['id']}", "📸"):
                    p_ = P_PROVANALYS
                return p_
            p_ = await spara(_s)
            return {"analys": an, "p": p_}
        if op == "omraden":
            typ = plugg.PROVTYPER.get(body.get("provtyp"), "Skriftligt prov")
            x = await self._ai(hass, OMRADEN_PROMPT.format(
                namn=namn, alder=alder, prov=u["namn"], typ=typ, omfattning=plugg._txt(body.get("omfattning"), 1500) or u.get("kapitel") or "(okänt)",
                material=await material(u), bild="Bilden är lärarens information om provet (t.ex. mål eller planering).\n" if bilder else ""),
                "Läxspelet provområden", bilder)
            return {"omraden": plugg.omraden_spara({}, [o for o in x.get("omraden") or [] if isinstance(o, dict)]), "omfattning": plugg._txt(x.get("omfattning"), 1500)}
        if op == "plan_skapa":
            inst = {"provtyp": body.get("provtyp") if body.get("provtyp") in plugg.PROVTYPER else "skriftligt",
                    "mal": body.get("mal") if body.get("mal") in plugg.MAL else "bra",
                    "omfattning": plugg._txt(body.get("omfattning"), 1500),
                    "uteslut": [str(x)[:10] for x in body.get("uteslut") or []][:30]}
            prof = await spara(lambda d: plugg.profil_spara(d, body))
            omraden = plugg.omraden_spara(u, body.get("omraden") or [])
            dagar = plugg.plan_dagar(u, prof["dagar"], inst["uteslut"])
            if not dagar:
                raise ValueError("Provet har redan varit, eller så finns det inga dagar kvar att plugga.")
            andra = [f"{x['datum']}: {x['namn']} ({x.get('amne_namn')})" for x in data.get("uppdrag", [])
                     if x["id"] != u["id"] and not x.get("klart") and x.get("datum") and dagar[0] <= x["datum"] <= u["datum"]]
            x = await self._ai(hass, PLAN_PROMPT.format(
                namn=namn, alder=alder, prov=u["namn"], datum=u["datum"], idag=dt_util.now().date().isoformat(), typ=plugg.PROVTYPER[inst["provtyp"]],
                mal=plugg.MAL[inst["mal"]], omfattning=inst["omfattning"] or u.get("kapitel") or "(okänt)",
                omraden="; ".join(f"{o['namn']}: {plugg.KAN[o['kan']]}" for o in omraden) or "(inga angivna)",
                profil=plugg.profil_text(prof), dagar=", ".join(f"{d} ({meriter.VECKODAGAR[date.fromisoformat(d).weekday()]})" for d in dagar),
                min=prof["min_dag"], andra="; ".join(andra) or "inget", material=await material(u),
                historik=plugg.plan_historik(data, u["id"]), foralder=plugg.onskemal_text(data)) + plugg.larare_block(data, u.get("amne")), "Läxspelet pluggplan")
            inst["tips"] = plugg._txt(x.get("tips"), 200)
            inst["tankar"] = plugg._txt(x.get("tankar"), 1200)

            def _s(d):
                uu = prov(d)
                plan = plugg.plan_spara(uu, inst, omraden, x.get("delar") or [], dagar)
                if not plan["delar"]:
                    raise ValueError("AI:n kunde inte göra någon plan. Försök igen.")
                return plugg.plan_lage(uu)
            return {"plan": await spara(_s)}
        if op == "plan_bort":
            await spara(lambda d: prov(d).pop("plan", None))
            return {}
        if op == "del_klar":
            return await spara(lambda d: plugg.del_klar(d, prov(d), str(body.get("del")), bool(body.get("klar"))))
        if op == "ovningsprov_skapa":
            omraden = (u.get("plan") or {}).get("omraden", [])
            x = await self._ai(hass, OVNINGSPROV_PROMPT.format(
                namn=namn, alder=alder, prov=u["namn"], typ=plugg.PROVTYPER.get((u.get("plan") or {}).get("inst", {}).get("provtyp"), "skriftligt prov"),
                omraden="; ".join(f"{o['namn']}: {plugg.KAN[o['kan']]}" for o in omraden) or "(inga angivna)",
                material=await material(u), antal=6 if (ar or 12) < 11 else 8) + plugg.larare_block(data, u.get("amne")), "Läxspelet övningsprov")
            op_ = await spara(lambda d: plugg.ovningsprov_spara(prov(d), x.get("fragor") or [], omraden))
            return {"prov": plugg.ovningsprov_ut(op_, foralder)}
        if op == "ovningsprov_ratta":
            o = next((y for y in (u.get("plan") or {}).get("ovningsprov", []) if y["id"] == body.get("prov")), None)
            if not o:
                raise ValueError("Övningsprovet finns inte.")
            if o.get("resultat"):
                raise ValueError("Det här övningsprovet är redan rättat.")
            svar = [plugg._txt(v, 300) for v in body.get("svar") or []]
            oppna = [(i, q) for i, q in enumerate(o["fragor"]) if not q["alternativ"] and i < len(svar) and svar[i]]
            bed = [{} for _ in o["fragor"]]
            if oppna:
                x = await self._ai(hass, RATTA_PROMPT.format(alder=alder, fragor="\n".join(
                    f"{n + 1}. Fråga: {q['fraga']} | Facit: {q['facit']} | Barnets svar: {svar[i]}" for n, (i, q) in enumerate(oppna))), "Läxspelet rätta övningsprov")
                for n, (i, _q) in enumerate(oppna):
                    b = (x.get("bedomning") or [])[n:n + 1]
                    bed[i] = b[0] if b and isinstance(b[0], dict) else {}

            def _r(d):
                uu = prov(d)
                oo = next(y for y in uu["plan"]["ovningsprov"] if y["id"] == o["id"])
                return {**plugg.ovningsprov_ratta(d, uu, oo, svar, bed, uu["amne"]), "facit": [q["facit"] for q in oo["fragor"]], "omraden": uu["plan"].get("omraden", [])}
            if foralder:  # föräldern provar: rättas men ger inga meriter och sparas inte
                res = []
                for i, q in enumerate(o["fragor"]):
                    s_ = svar[i] if i < len(svar) else ""
                    ratt = s_ == q["facit"] if q["alternativ"] else bool(bed[i].get("ratt")) if s_ else False
                    res.append({"svar": s_, "ratt": ratt, "kommentar": plugg._txt(bed[i].get("kommentar"), 300)})
                return {"resultat": res, "ratt": sum(r["ratt"] for r in res), "av": len(res), "p": 0, "facit": [q["facit"] for q in o["fragor"]], "prov_lage": True}
            return await spara(_r)
        raise ValueError("Okänd åtgärd.")


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
            van = next((x for x in v["vanner"] if vanner.samma(x["kod"], body.get("van"))), None)
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
        if op == "gata_svar":  # en gissning som inte står i facit: låt AI:n bedöma om den ändå är rätt (t.ex. tvättsvamp/svamp)
            fraga_ai = dagens.gata_ai_fraga(await hass.async_add_executor_job(_load, path))
            if fraga_ai:
                try:
                    body["_gata_ai"] = _parse_json(await _ai_text(hass, fraga_ai, "Läxspelet gåta"))
                except Exception as err:  # noqa: BLE001
                    _LOGGER.info("Gåtan: AI kunde inte bedöma svaret: %s", err)
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
    "djur_ater",
    "schema_spara", "bonus", "los_in", "butik_lagg_till", "butik_ta_bort",
    "manuell_uppdrag", "manuell_schema", "manuell_forhor", "manuell_ovning", "manuell_plugg", "angra_ovning",
    "hejarop_ny", "hejarop_bort", "fodelsedag_satt", "lektioner_spara", "skolinfo_bort",
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
    if op == "djur_ater":  # föräldern låter barnet ångra att det släppte ett husdjur
        meriter.djur_ater(data, str(body.get("hid") or ""))
        return []
    if op in ("gata_gissa", "gata_svar"):  # dagens gåta (bara barnet själv)
        if not body.get("_barn"):
            raise ValueError("Det är barnet som gissar.")
        if op == "gata_gissa":
            dagens.gissa(data, str(body.get("svar") or ""))
        else:
            dagens.visa_svar(data, body.get("_gata_ai") if isinstance(body.get("_gata_ai"), dict) else None)
        return []
    if op in ("djur", "djur_kop", "djur_pa", "djur_paket", "pass_hamta", "rum_stall", "vaning_kop", "vaning_djur", "mata", "djur_slapp", "attack_kop", "attack_upp", "uppsattning", "attack", "dryck_kop", "dryck", "energi_kop", "skold_kop", "skold_pa", "traning_kop", "lagstrid_start", "lagstrid_drag", "lagstrid_ge_upp", "arena_start", "arena_drag", "arena_byt", "arena_ge_upp", "revansch_start", "provboss_start"):  # husdjuret: välj, köp saker, ta på (bara barnet själv)
        if not body.get("_barn"):
            raise ValueError("Det är barnet som bestämmer över sitt husdjur.")
        if op == "djur":
            meriter.djur_valj(data, str(body.get("art") or ""), str(body.get("namn") or ""), str(body.get("id") or "") or None)
        elif op == "djur_kop":
            meriter.djur_kop(data, str(body.get("sak") or ""), body.get("vaning"))
        elif op == "djur_paket":
            meriter.kop_paket(data, str(body.get("paket") or ""))
        elif op == "pass_hamta":
            meriter.hamta_pass(data, int(body.get("niva") or 0))
        elif op == "rum_stall":
            meriter.rum_stall(data, str(body.get("plats") or ""), body.get("sak") or None, body.get("vaning"))
        elif op == "mata":
            meriter.mata(data, str(body.get("hid") or ""))
        elif op == "djur_slapp":
            meriter.djur_slapp(data, str(body.get("hid") or ""))
        elif op == "vaning_kop":
            meriter.vaning_kop(data)
        elif op == "vaning_djur":
            meriter.vaning_djur(data, body.get("vaning"), body.get("hid") or None)
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
                meriter.arena_start(data, jag_namn, mot_id, mot_namn, mot_data, lag=body.get("lag"))
            else:
                raise ValueError("Välj en motståndare.")
        elif op == "revansch_start":
            meriter.revansch_start(data, str(body.get("varld") or ""), lag=body.get("lag"))
        elif op == "provboss_start":
            meriter.provboss_start(data, str(body.get("id") or ""))
        elif op == "arena_drag":
            meriter.arena_drag(data, str(body.get("drag") or ""))
        elif op == "arena_byt":
            meriter.arena_byt(data, str(body.get("hid") or ""))
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
    if op == "handstil_klar":  # spårövning (bara barnet själv; föräldrar kan prova utan att det sparas)
        if body.get("_barn"):
            meriter.handstil_klar(data, "spara", int(body.get("poang") or 0), str(body.get("text") or ""))
        return []
    if op == "skolinfo_bort":
        i = str(body.get("id") or "")
        if i.startswith("kal:"):  # händelse från skolkalendern: göm den
            data["kalender_dolda"] = (data.get("kalender_dolda", []) + [i[4:]])[-200:]
        data["skolinfo"] = [x for x in data.get("skolinfo", []) if x.get("id") != i]
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
        elif (g := _sla_ihop_glosor({"glosor": [x for x in a["glosor"] if x.get("typ", "glosor") == typ]}, namn, forhor or None, par)):
            # samma glosor en gång till: nya ord lades till i den gamla listan, ingen kopia.
            # Barnet får ändå stjärnor, men den minsta mängden om någon annan lade in dem först.
            if body.get("_barn"):
                meriter.lagt_in(data, a["id"], "glosor", g, minsta=g.get("av") != "barn")
        else:
            ny_g = {"id": _new_id(), "namn": namn, "sprak": sprak, "par": par, "forhor": forhor or None, "skapad": dt_util.now().date().isoformat(), "typ": typ,
                    "av": "barn" if body.get("_barn") else "foralder"}
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
            await hass.async_add_executor_job(_krymp_bild, path / "filer" / name)  # mobilfoton är stora: krymp utan att texten blir svårläst
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
        entity = _ai_entitet(hass)
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
            resp = await _ai_anrop(hass,
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


def _bas_url_egen(hass: HomeAssistant) -> str:
    """Familjens egen adress utifrån (Nabu Casa eller en inställd https-adress), om den finns."""
    try:
        from homeassistant.components import cloud
        if cloud.async_active_subscription(hass) and cloud.async_remote_ui_url(hass):
            return cloud.async_remote_ui_url(hass)
    except Exception:  # noqa: BLE001
        pass
    u = hass.config.external_url or ""
    return u if u.startswith("https://") else ""


def _bas_url(hass: HomeAssistant) -> str:
    """Adressen som fungerar även utanför hemmet: Nabu Casa/egen adress, annars Läxspelets gratistunnel (grind.py)."""
    egen = _bas_url_egen(hass)
    if egen:
        return egen
    g = (hass.data.get(DOMAIN) or {}).get("grind")
    if g and g.adress:
        return g.adress
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


class WidgetBildView(HomeAssistantView):
    """Appen sparar husdjursbilden (ritad i appen, alla fyra humören) som widgeten visar."""

    url = "/api/skolan/widgetbild"
    name = "api:skolan:widgetbild"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        mapp = _dir(hass, barn) / "widget"
        sig = str(body.get("sig", ""))[:500]
        info_fil = mapp / "info.json"
        info = await hass.async_add_executor_job(lambda: _load_fil(info_fil) if info_fil.exists() else {})
        bilder = body.get("bilder")
        if not bilder:
            return self.json({"behov": info.get("sig") != sig})
        filer = {}
        for h in WIDGET_HUMOR:
            b = str(bilder.get(h, ""))
            if not b.startswith("data:image/png;base64,") or len(b) > 1_500_000:
                return self.json({"message": "Fel bild"}, status_code=400)
            png = base64.b64decode(b.split(",", 1)[1])
            if not png.startswith(b"\x89PNG"):
                return self.json({"message": "Fel bild"}, status_code=400)
            filer[h] = png

        def spara():
            mapp.mkdir(parents=True, exist_ok=True)
            for h, png in filer.items():
                (mapp / f"{h}.png").write_bytes(png)
            _save_fil(info_fil, {"sig": sig, "art": str(body.get("art", "")), "agg": bool(body.get("agg")),
                                 "v": hashlib.sha1(sig.encode()).hexdigest()[:10]})
        await hass.async_add_executor_job(spara)
        return self.json({"ok": True})


class WidgetBildHamtaView(HomeAssistantView):
    """Husdjursbilden för widgeten (ingen inloggning, samma hemliga nyckel som widgeten)."""

    url = "/api/skolan/widget/{nyckel}/bild/{humor}.png"
    name = "api:skolan:widget:bild"
    requires_auth = False

    async def get(self, request: web.Request, nyckel: str, humor: str) -> web.Response:
        import hmac
        hass: HomeAssistant = request.app["hass"]
        if humor not in WIDGET_HUMOR:
            raise web.HTTPNotFound
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            n = await hass.async_add_executor_job(_widget_nyckel, hass, b["id"])
            if n and hmac.compare_digest(n, nyckel):
                f = _dir(hass, b["id"]) / "widget" / f"{humor}.png"
                if await hass.async_add_executor_job(f.exists):
                    return web.Response(body=await hass.async_add_executor_job(f.read_bytes), content_type="image/png",
                                        headers={"Cache-Control": "max-age=86400"})
        raise web.HTTPNotFound


WIDGET_HUMOR = ("glad", "nojd", "hungrig", "ledsen")


def _widget_egen(hass: HomeAssistant, barn: str) -> dict:
    f = _dir(hass, barn) / "widget" / "info.json"
    return _load_fil(f) if f.exists() else {}


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
        egen = await hass.async_add_executor_job(_widget_egen, hass, barn["id"])
        # appens egen bild gäller bara om den är ritad för samma husdjur (och ägg/kläckt stämmer)
        if not (d and egen.get("art") == d.get("art") and egen.get("agg") == agg):
            egen = {}
        humor_text = {"glad": "är mätt och glad!", "nojd": "väntar på dagens mat", "hungrig": "är hungrig!", "ledsen": "saknar dig…"}[humor]
        return self.json({
            "namn": d.get("namn") or "Välj ett husdjur",
            "text": ("väntar på att kläckas" if agg else humor_text) if d else "Öppna Läxspelet och välj ditt husdjur!",
            "humor": humor,
            "bild": f"/api/skolan/widget/{nyckel}/bild/{humor}.png?v={egen['v']}" if egen
            else f"{STATIC_URL}/djur/{'agg' if agg or not d else slug}_{humor}.png",
            "hatt": None if egen else hatt["ikon"] if hatt else ("👑" if d.get("steg", 0) >= 5 else None),
            "hatt_pos": a.get("ogon" if hatt and hatt["id"] in ank.get("ogon_saker", []) else "hatt"),
            "kompis": (sak(pa.get("kompis")) or {}).get("ikon") if not agg and not egen else None,
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


STAV_PROMPT = (
    "Du kontrollerar stavningen i en glosläxa som ett skolbarn har skrivit in eller fotat. Språk: {sprak}.\n"
    "Ordpar (rad: kolumn 1 | kolumn 2):\n{rader}\n\n"
    "Hitta ord som nästan säkert är FELSTAVADE (stavfel, saknade/extra bokstäver, fel accent, ihopskrivning). "
    "Ändra INTE: artiklar som finns med eller saknas, brittisk/amerikansk stavning, versaler, synonymer, ordval eller översättningar du tycker är sämre. "
    "Är du osäker: ta inte med ordet. Svara ENDAST med giltig JSON utan markdown: "
    '{{"forslag": [{{"rad": radnummer, "kol": 1 eller 2, "fran": exakt texten i fältet, "till": hela fältet rättstavat, "varfor": max 6 ord på svenska}}]}} '
    'och {{"forslag": []}} om allt ser rätt ut.'
)
STAV_MAX = 120


def _ar_json(t: str) -> bool:
    try:
        json.loads(t)
        return True
    except ValueError:
        return False


class GlosorStavningView(HomeAssistantView):
    """Kollar stavningen i glosor innan de sparas. Föreslår bara, barnet eller föräldern väljer Byt eller Behåll."""

    url = "/api/skolan/glosor_stavning"
    name = "api:skolan:glosor_stavning"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        if not isinstance(body, dict):
            raise web.HTTPBadRequest
        _barn_for(hass, request, body.get("barn"))
        par = [[str(x or "")[:120] for x in (p or [])[:2]] + [""] * (2 - len((p or [])[:2])) for p in (body.get("par") or [])[:STAV_MAX] if isinstance(p, list)]
        sprak = [str(x or "")[:30] for x in (body.get("sprak") or [])[:2]]
        if not any(a.strip() or b.strip() for a, b in par):
            return self.json({"forslag": []})
        entity = _ai_entitet(hass)
        if not entity:
            return self.json({"forslag": [], "ingen_ai": True})
        rader = "\n".join(f"{i + 1}: {a} | {b}" for i, (a, b) in enumerate(par))
        instr = STAV_PROMPT.format(sprak=" / ".join(x for x in sprak if x) or "okänt", rader=rader)
        try:
            resp = await _ai_anrop(hass, "ai_task", "generate_data", {"task_name": "Läxspelet stavningskoll", "entity_id": entity, "instructions": instr},
                                   blocking=True, return_response=True)
            raw = (resp or {}).get("data")
            raw = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Läxspelet: stavningskollen misslyckades: %s", err)
            return self.json({"forslag": [], "fel": True})
        try:
            x = _parse_json(raw)
        except (ValueError, json.JSONDecodeError):  # avklippt svar: ta de förslag som hann bli hela
            x = {"forslag": [json.loads(m) for m in re.findall(r'\{[^{}]*"rad"[^{}]*\}', raw) if _ar_json(m)]}
        ut, sett = [], set()
        for f in (x.get("forslag") or [])[:40] if isinstance(x, dict) else []:
            try:
                i, k = int(f.get("rad")) - 1, int(f.get("kol")) - 1
            except (TypeError, ValueError, AttributeError):
                continue
            if not (0 <= i < len(par) and k in (0, 1)) or (i, k) in sett:
                continue
            fore, till = par[i][k], str(f.get("till") or "").strip()[:120]
            if not till or till == fore.strip() or not fore.strip():
                continue
            sett.add((i, k))
            ut.append({"i": i, "k": k, "fran": fore, "till": till, "varfor": str(f.get("varfor") or "")[:60]})
        return self.json({"forslag": ut})


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
        entity = _ai_entitet(hass)
        if not entity:
            return self.json_message("Ingen AI-uppgift finns i Home Assistant.", 500)
        try:
            resp = await _ai_anrop(hass,
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


async def _ai_las(hass: HomeAssistant, src: Path | list[Path], prompt: str, task_name: str) -> str:
    """Kopiera filen (eller filerna, t.ex. flera skärmdumpar av samma brev) till tillfälliga mediafiler,
    låt AI:n läsa dem i samma fråga och radera kopiorna."""
    conf = hass.data[DOMAIN]["conf"]
    entity = _ai_entitet(hass)
    if not entity:
        raise RuntimeError("Ingen AI-uppgift finns i Home Assistant.")
    kallor = src if isinstance(src, list) else [src]
    bilagor, tmps = [], []
    for k in kallor:
        name = f"{uuid.uuid4().hex}{k.suffix.lower()}"
        tmp = hass.data[DOMAIN]["tmp"] / name
        await hass.async_add_executor_job(shutil.copyfile, k, tmp)
        tmps.append(tmp)
        bilagor.append({"media_content_id": f"media-source://media_source/local/{TMP_SUBDIR}/{name}",
                        "media_content_type": mimetypes.guess_type(k.name)[0] or "image/jpeg"})
    if len(kallor) > 1:
        prompt = f"Du får {len(kallor)} bilder/filer som hör ihop (t.ex. flera skärmdumpar eller sidor av samma dokument). Läs dem tillsammans som ETT dokument. " + prompt
    try:
        resp = await _ai_anrop(hass,
            "ai_task",
            "generate_data",
            {"task_name": task_name, "entity_id": entity, "instructions": prompt, "attachments": bilagor},
            blocking=True,
            return_response=True,
        )
    finally:
        await hass.async_add_executor_job(lambda: [t.unlink(missing_ok=True) for t in tmps])
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
    if not foralder:  # övningsprov: facit först när provet är inlämnat
        data["uppdrag"] = [
            {**{k: v for k, v in u.items() if k != "plan_historik"}, "plan": {**u["plan"], "inst": {k: v for k, v in (u["plan"].get("inst") or {}).items() if k != "tankar"},
                                    "ovningsprov": [x if x.get("resultat") else plugg.ovningsprov_ut(x, False) for x in u["plan"].get("ovningsprov", [])]}}
            if u.get("plan") else u
            for u in data.get("uppdrag", [])
        ]
    data.pop("veckorapport", None)
    if not foralder:
        data.pop("foralder_onskemal", None)
        data.pop("larar_riktlinjer", None)
    if "meriter" in data:
        data["meriter"] = {k: v for k, v in data["meriter"].items() if k != "nycklar"}
    data.pop("kalender", None)  # gamla länken per barn: aldrig till webbläsaren
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
        syskon_klart: list[tuple] = []

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
                            if f.get("syskon"):  # ett syskon skickade förhöret: belöna och berätta hur det gick
                                syskon_klart.append((f["syskon"], f["namn"], ratt, len(f["fragor"]), f["bedomning"] == "godkant"))
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
        for syskon, namn, ratt, av, godk in syskon_klart:
            await _syskon_belona(hass, syskon, barn_conf["namn"], namn, ratt, av, godk)
        return self.json({"data": _ut(data, foralder)})


P_SYSKON = 5  # ⭐ till syskonet som förhörde
SYSKON_MAX = 3  # belönade syskonförhör per dag


async def _syskon_belona(hass: HomeAssistant, syskon: str, namn: str, lista: str, ratt: int, av: int, godk: bool) -> None:
    sb = next((b for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == syskon), None)
    if not sb:
        return
    p = 0
    async with hass.data[DOMAIN]["locks"][syskon]:
        data = await hass.async_add_executor_job(_load, _dir(hass, syskon))
        idag = dt_util.now().date().isoformat()
        for n in range(1, SYSKON_MAX + 1):
            poang = P_SYSKON + (3 if godk else 0)
            if meriter.ge(data, poang, f"🤝 Förhörde {namn} på {lista[:30]}", f"syskon:{idag}:{n}", "🤝"):
                p = poang
                meriter.aktiv(data, idag)
                break
        await hass.async_add_executor_job(_save, _dir(hass, syskon), data)
    await _notis(hass, sb.get("notify"), f"🤝 {namn} har gjort ditt förhör", f"{ratt} av {av} rätt på {lista}." + (f" Du får +{p} ⭐ för att du hjälpte till!" if p else ""), "/skolan")


class LarareView(HomeAssistantView):
    """Till läraren (bara föräldrar): veckans lapp, underlag till utvecklingssamtalet och text om AI:n."""

    url = "/api/skolan/larare"
    name = "api:skolan:larare"

    @staticmethod
    def _svar(s: dict, namn: str) -> dict:
        lar = skola.huvudlarare(s)
        return {"lapp": larare.lapp_status(s), "om_ai": larare.OM_AI.format(namn=namn), "mejl": s["foralder"].get("mejl_till", ""),
                "larare": lar.get("namn") or "", "kopplad": bool(lar.get("id")), "pa": skola.PA,
                "kan": {f: skola.aktiv(s, f) for f in ("lapp", "samtal")},
                "mottagare": {f: [{"id": x["id"], "namn": x.get("namn") or "Läraren", "amne": x.get("amne") or "", "roll": x.get("roll") or "mentor"}
                                  for x in (s.get("lararna") or {}).values() if skola.aktiv(s, f, x["id"])] for f in ("lapp", "samtal")},
                "skickat": [{"typ": x["typ"], "tid": x["tid"]} for x in s.get("utgaende", [])][-10:][::-1],
                "samtal_ai": bool(s.get("samtal_ai"))}

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            return self.json_message("Bara för föräldrar.", 403)
        barn = _barn_for(hass, request, request.query.get("barn"))
        s = await hass.async_add_executor_job(skola.las, _dir(hass, barn))
        namn = next(b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn)
        return self.json(self._svar(s, namn))

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            return self.json_message("Bara för föräldrar.", 403)
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        op = body.get("op")
        mapp = _dir(hass, barn)
        namn = next(b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn)
        data = await hass.async_add_executor_job(_load, mapp)
        ai = None
        try:
            if op == "lapp_ny":
                f = larare.fakta(data, larare.LAPP_DAGAR)
                ai = _parse_json(await _ai_text(hass, larare.LAPP_PROMPT.format(namn=namn, alder=intressen.alder(data) or "", fakta=larare.fakta_text(f)),
                                                "Läxspelet lapp till läraren"))
                if not str(ai.get("text") or "").strip():
                    raise ValueError("AI:n skrev ingen lapp. Försök igen.")
            elif op == "samtal_ai":
                f = larare.fakta(data, larare.SAMTAL_DAGAR)
                ai = _parse_json(await _ai_text(hass, larare.SAMTAL_PROMPT.format(namn=namn, alder=intressen.alder(data) or "", fakta=larare.fakta_text(f)),
                                                "Läxspelet underlag utvecklingssamtal"))
        except ValueError as err:
            return self.json_message(str(err), 400)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Till läraren: AI misslyckades: %s", err)
            return self.json_message("AI:n svarade inte. Försök igen om en stund.", 503)
        async with hass.data[DOMAIN]["locks"][barn]:
            s = await hass.async_add_executor_job(skola.las, mapp)
            try:
                if op == "lapp_ny":
                    larare.lapp_satt(s, ai["text"])
                elif op == "lapp_spara":
                    larare.lapp_satt(s, body.get("text"), (s.get("lapp") or {}).get("status") or "utkast")
                elif op == "lapp_klar":  # föräldern har skickat lappen själv (kopierat eller mejlat)
                    larare.lapp_satt(s, body.get("text") or (s.get("lapp") or {}).get("text"), "skickad")
                elif op == "lapp_skicka":  # via lärarappen
                    if not skola.aktiv(s, "lapp"):
                        raise ValueError("Lappar är inte påslagna hos både dig och läraren.")
                    lp = larare.lapp_satt(s, body.get("text") or (s.get("lapp") or {}).get("text"), "skickad")
                    if not lp["text"]:
                        raise ValueError("Lappen är tom.")
                    larare.skicka(s, "lapp", {"namn": s["foralder"].get("namn") or namn, "text": lp["text"]}, body.get("till"))
                elif op == "samtal_ai":
                    s["samtal_ai"] = {k: [str(x)[:300] for x in (ai.get(k) or [])][:4] for k in ("styrkor", "svart", "fragor")}
                elif op == "samtal_utan_ai":
                    s.pop("samtal_ai", None)
                elif op == "samtal_skicka":
                    if not skola.aktiv(s, "samtal"):
                        raise ValueError("Underlaget är inte påslaget hos både dig och läraren.")
                    f = larare.fakta(data, larare.SAMTAL_DAGAR)
                    larare.skicka(s, "samtal", larare.samtal_till_larare(s["foralder"].get("namn") or namn, f, s.get("samtal_ai")), body.get("till"))
                elif op == "mejl":
                    s["foralder"]["mejl_till"] = str(body.get("mejl") or "").strip()[:200]
                else:
                    raise ValueError("Okänd åtgärd.")
            except ValueError as err:
                return self.json_message(str(err), 400)
            await hass.async_add_executor_job(skola.spara, mapp, s)
        return self.json(self._svar(s, namn))


class SamtalView(HomeAssistantView):
    """Underlaget till utvecklingssamtalet som utskriftsvänlig sida (signerad länk, bara föräldrar)."""

    url = "/api/skolan/samtal"
    name = "api:skolan:samtal"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden
        barn = _barn_for(hass, request, request.query.get("barn"))
        mapp = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, mapp)
        s = await hass.async_add_executor_job(skola.las, mapp)
        namn = next(b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn)
        f = await hass.async_add_executor_job(larare.fakta, data, larare.SAMTAL_DAGAR)
        return web.Response(text=larare.samtal_sida(namn, f, s.get("samtal_ai")), content_type="text/html", headers={"Cache-Control": "no-store"})


class IntresseView(HomeAssistantView):
    """Det jag gillar: barnets intressen, Lästal och Läs om det du gillar (AI-skrivet på barnets nivå)."""

    url = "/api/skolan/intressen"
    name = "api:skolan:intressen"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        return self.json({"status": intressen.status(data), "lastal": intressen.lastal_publik(data), "las": intressen.las_publik(data)})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        op = body.get("op")
        path = _dir(hass, barn)
        if op not in ("satt", "lastal_ny", "lastal_svar", "las_ny", "las_svar"):
            return self.json_message("Okänd åtgärd.", 400)
        if op != "satt" and _ar_foralder(hass, request):
            return self.json_message("Det här gör barnet själv.", 400)
        ai = None
        if op in ("lastal_ny", "las_ny"):  # AI:n skriver utanför låset (tar några sekunder)
            data = await hass.async_add_executor_job(_load, path)
            try:
                if intressen.status(data)["kvar"] <= 0:
                    raise ValueError("Nu har AI:n skrivit många uppgifter idag. Kom tillbaka i morgon! 😴")
                amne = intressen.valj_amne(data, body.get("amne"))
            except ValueError as err:
                return self.json_message(str(err), 400)
            prompt = intressen.lastal_prompt(data, amne) if op == "lastal_ny" else intressen.las_prompt(data, amne)
            try:
                ai = _parse_json(await _ai_text(hass, prompt, "Läxspelet " + ("lästal" if op == "lastal_ny" else "läs om det du gillar")))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Intressen: AI misslyckades: %s", err)
                return self.json_message("AI:n svarade inte. Försök igen om en stund.", 503)
        bedomning = None
        skrivsvar = " ".join(str(body.get("skrivsvar") or "").split())
        if op == "las_svar":  # skrivsvaret rättas av AI:n (utanför låset)
            data = await hass.async_add_executor_job(_load, path)
            prompt = intressen.skriv_bedom_prompt(data, skrivsvar)
            if prompt:
                if len(skrivsvar.split()) < 6:
                    return self.json({"res": {"skriv": {"svar": skrivsvar, "ok": False, "bra": "",
                                                        "tips": "Skriv lite mer! Svara med hela meningar, med stor bokstav först och punkt sist."}, "om": True},
                                      "status": intressen.status(data)})
                try:
                    bedomning = _parse_json(await _ai_text(hass, prompt, "Läxspelet rätta skrivsvar"))
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Intressen: AI-rättning misslyckades: %s", err)
                    return self.json_message("AI:n kunde inte rätta just nu. Försök igen om en stund.", 503)
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                if op == "satt":
                    intressen.satt(data, body.get("lista"))
                    ut = {}
                elif op == "lastal_ny":
                    intressen.rakna_ai(data)
                    ut = {"lastal": intressen.lastal_spara(data, amne, ai)}
                elif op == "las_ny":
                    intressen.rakna_ai(data)
                    ut = {"las": intressen.las_spara(data, amne, ai)}
                elif op == "lastal_svar":
                    ut = {"res": intressen.lastal_svar(data, body.get("svar") or [])}
                else:
                    ut = {"res": intressen.las_svar(data, body.get("svar") or [], skrivsvar, bedomning)}
            except ValueError as err:
                return self.json_message(str(err), 400)
            await hass.async_add_executor_job(_save, path, data)
        ut["status"] = intressen.status(data)
        return self.json(ut)


class UtvecklingView(HomeAssistantView):
    """Min utveckling: förr jämfört med nu."""

    url = "/api/skolan/utveckling"
    name = "api:skolan:utveckling"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        data = await hass.async_add_executor_job(_load, _dir(hass, barn))
        return self.json(utveckling.matt(data))


class HjarnView(HomeAssistantView):
    """Hjärngympa: syskontävlingen (bara poängen i hjärngympan, inget annat från syskonens mappar)."""

    url = "/api/skolan/hjarngympa"
    name = "api:skolan:hjarngympa"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        jag = _barn_for(hass, request, request.query.get("barn"))
        barnen = []
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            if request.get("skolan_bara_barn") and b["id"] != jag:
                continue
            barnen.append((b, await hass.async_add_executor_job(_load, _dir(hass, b["id"]))))
        return self.json(hjarngympa.tavling(barnen))


class ExtraView(HomeAssistantView):
    """Mattemonster, läsflyt, läsa-lätt-läge och "Hur känns skolan?"."""

    url = "/api/skolan/extra"
    name = "api:skolan:extra"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        barn = _barn_for(hass, request, request.query.get("barn"))
        path = _dir(hass, barn)
        data = await hass.async_add_executor_job(_load, path)

        def _sidor():  # böcker med fotade sidor och ordräkning (från e-boken)
            ut = []
            for a in data.get("amnen", []):
                for b in a.get("bocker", []):
                    cache = _load_fil(path / "filer" / _ebok_fil(b["id"])).get("cache", {})
                    sidor = [{"nyckel": f"{f}#{i}", "fil": f, "sidnr": s_.get("sidnummer"), "ord": int(s_.get("ord") or 0)}
                             for f in b.get("sidor", []) for i, s_ in enumerate(cache.get(f, {}).get("sidor", [])) if int(s_.get("ord") or 0) >= 20]
                    if sidor:
                        ut.append({"id": b["id"], "namn": b["namn"], "amne": a["namn"], "sidor": sidor})
            return ut
        return self.json({"bocker": await hass.async_add_executor_job(_sidor)})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        ljud = None
        if request.content_type.startswith("multipart/"):
            form = await request.post()
            body = json.loads(str(form.get("json") or "{}"))
            ljud = form.get("file") if hasattr(form.get("file"), "file") else None
        else:
            body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        op = body.get("op")
        path = _dir(hass, barn)
        larm = False
        maende_oro = None
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, path)
            try:
                if op == "lattlast":
                    data["lattlast"] = bool(body.get("pa"))
                    ut = {"lattlast": data["lattlast"]}
                elif foralder:
                    raise ValueError("Det här gör barnet själv.")
                elif op == "hjarn":
                    ut = hjarngympa.resultat(data, barn, str(body.get("spel") or ""), int(body.get("raw") or 0), bool(body.get("daglig")))
                elif op == "matte":
                    ut = extra.matte_rekord(data, str(body.get("typ") or ""), int(body.get("niva") or 1), int(body.get("poang") or 0))
                elif op == "mående":
                    ut = extra.mående_svar(data, str(body.get("kansla") or ""), body.get("vad") or [], str(body.get("text") or ""))
                    larm = ut["larm"]
                    maende_oro = omsorg.bedom(str(body.get("text") or ""))
                elif op == "lasflyt":
                    nyckel = str(body.get("nyckel") or "")
                    fil, _, idx = nyckel.partition("#")
                    cache = (await hass.async_add_executor_job(_load_fil, path / "filer" / _ebok_fil(str(body.get("bok") or "")))).get("cache", {})
                    try:
                        sida = cache.get(Path(fil).name, {}).get("sidor", [])[int(idx)]
                    except (ValueError, IndexError) as err:
                        raise ValueError("Sidan finns inte.") from err
                    ljudfil = None
                    if ljud is not None:
                        innehall = await hass.async_add_executor_job(ljud.file.read)
                        if 0 < len(innehall) < 15 * 1024 * 1024:
                            ljudfil = f"lasflyt_{dt_util.now().strftime('%Y%m%d-%H%M%S')}_{_new_id()}{'.webm' if 'webm' in (ljud.content_type or '') else '.m4a'}"
                            await hass.async_add_executor_job((path / "filer" / ljudfil).write_bytes, innehall)
                    ut = extra.lasflyt_spara(data, str(body.get("bok") or ""), str(sida.get("sidnummer") or ""), int(sida.get("ord") or 0),
                                             int(body.get("sek") or 0), ljudfil)
                    for gammal in extra.lasflyt_gamla_filer(data):
                        await hass.async_add_executor_job((path / "filer" / gammal).unlink, True)
                else:
                    raise ValueError("Okänd åtgärd.")
            except ValueError as err:
                return self.json_message(str(err), 400)
            await hass.async_add_executor_job(_save, path, data)
        if maende_oro:
            ut["hjalp"] = await _omsorg(hass, barn, maende_oro, str(body.get("text") or ""), "i \"Hur känns skolan?\"", data)
        if larm:
            namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
            for tj in _foralder_tjanster(hass, data):
                await _notis(hass, tj, f"💛 {namn} verkar ha det jobbigt", f"{namn} har svarat ledsen, stressad eller arg de senaste tre gångerna på ”Hur känns skolan?”. Kanske värt en pratstund?", f"/skolan?barn={barn}")
        return self.json(ut)


class KlockaView(HomeAssistantView):
    """Föräldrar: barnets Awtrix-klocka (MQTT-prefix, på/av, test)."""

    url = "/api/skolan/klocka"
    name = "api:skolan:klocka"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        fil = hass.data[DOMAIN]["base"] / "klockor.json"
        inst = await hass.async_add_executor_job(_load_fil, fil)
        k = inst.setdefault(barn, {"prefix": f"{barn}s_klocka", "pa": False})
        if body.get("op") == "spara":
            k["prefix"] = re.sub(r"[^A-Za-z0-9_/\-]", "", str(body.get("prefix") or ""))[:60] or k["prefix"]
            k["pa"] = bool(body.get("pa"))
            await hass.async_add_executor_job(_save_fil, fil, inst)
        mqtt = hass.services.has_service("mqtt", "publish")
        if body.get("op") == "testa" and mqtt:
            data = await hass.async_add_executor_job(_load, _dir(hass, barn))
            text, farg = _klocka_text(data)
            await hass.services.async_call("mqtt", "publish", {"topic": f"{k['prefix']}/notify", "payload": json.dumps({"text": "Läxspelet: " + text, "color": farg, "duration": 10})})
        return self.json({"klocka": k, "mqtt": mqtt})


def _ics_text(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")[:200]


class PlanKalenderView(HomeAssistantView):
    """Kalenderprenumeration (.ics) med pluggplan, prov, läxor och byten. Hemlig länk per barn, bara för föräldrar."""

    url = "/api/skolan/plankalender/{nyckel}"
    name = "api:skolan:plankalender"
    requires_auth = False

    async def get(self, request: web.Request, nyckel: str) -> web.Response:
        import hmac

        hass: HomeAssistant = request.app["hass"]
        nyckel = nyckel.removesuffix(".ics")
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            if data.get("kal_nyckel") and hmac.compare_digest(data["kal_nyckel"], nyckel):
                break
        else:
            raise web.HTTPNotFound
        namn = b["namn"]
        rader = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Laxspelet//SV", "CALSCALE:GREGORIAN", f"X-WR-CALNAME:Läxspelet – {namn}", "X-PUBLISHED-TTL:PT3H"]
        stamp = dt_util.utcnow().strftime("%Y%m%dT%H%M%SZ")

        def ev(uid: str, dag: str, titel: str, besk: str = "") -> None:
            d = dag.replace("-", "")
            nasta = (date.fromisoformat(dag) + timedelta(days=1)).strftime("%Y%m%d")
            rader.extend(["BEGIN:VEVENT", f"UID:{uid}@laxspelet", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{nasta}",
                          f"SUMMARY:{_ics_text(titel)}"] + ([f"DESCRIPTION:{_ics_text(besk)}"] if besk else []) + ["TRANSP:TRANSPARENT", "END:VEVENT"])
        fran = (dt_util.now().date() - timedelta(days=14)).isoformat()
        for u in data.get("uppdrag", []):
            if not u.get("datum") or u["datum"] < fran:
                continue
            if u.get("typ") == "prov":
                ev(f"prov-{u['id']}", u["datum"], f"📝 {namn}: {u['namn']}", u.get("amne_namn") or "")
                for d_ in (u.get("plan") or {}).get("delar", []):
                    ev(f"plan-{d_['id']}", d_["dag"], f"{'✅' if d_.get('klar') else '📚'} {namn}: {d_['titel']} ({d_['min']} min)", d_.get("vad") or "")
            elif not u.get("klart"):
                ev(f"laxa-{u['id']}", u["datum"], f"📖 {namn}: {u['namn']}", u.get("amne_namn") or "")
        if boende.aktiv(data):
            idag = dt_util.now().date()
            for i in range(0, 90):
                d_ = idag + timedelta(days=i)
                if boende.bytesdag(data, d_):
                    ev(f"byte-{b['id']}-{d_.isoformat()}", d_.isoformat(), f"🔄 {namn} till {boende.hem_for(data, d_)['namn']} kl. {(data.get('boende') or {}).get('bytestid', '')}")
        rader.append("END:VCALENDAR")
        return web.Response(body="\r\n".join(rader).encode("utf-8"), headers={"Content-Type": "text/calendar; charset=utf-8", "Cache-Control": "no-store"})


class SyskonView(HomeAssistantView):
    """Storasyskon-uppdrag: ett barn skickar ett glosförhör till sitt syskon och får ⭐ när det är gjort."""

    url = "/api/skolan/syskon"
    name = "api:skolan:syskon"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        jag = _barn_for(hass, request, request.query.get("barn"))
        ut = []
        for b in hass.data[DOMAIN]["conf"]["barn"]:
            if b["id"] == jag:
                continue
            data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
            listor = [{"amne": a["id"], "amne_namn": a["namn"], "id": g["id"], "namn": g["namn"], "antal": len(g.get("par", []))}
                      for a in data.get("amnen", []) for g in a.get("glosor", []) if g.get("par")]
            skickade = [{"namn": f["namn"], "status": f["status"], "ratt": sum(1 for x in f.get("svar", []) if x.get("ratt")), "av": len(f["fragor"]),
                         "skapad": f["skapad"]} for f in data.get("forhor", []) if f.get("syskon") == jag][-8:]
            ut.append({"id": b["id"], "namn": b["namn"], "listor": listor[-30:], "skickade": skickade[::-1]})
        return self.json({"syskon": ut})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        jag = _barn_for(hass, request, body.get("barn"))
        conf = hass.data[DOMAIN]["conf"]
        till = next((b for b in conf["barn"] if b["id"] == body.get("syskon") and b["id"] != jag), None)
        if not till:
            return self.json_message("Välj ett syskon.", 400)
        jag_namn = next(b["namn"] for b in conf["barn"] if b["id"] == jag)
        async with hass.data[DOMAIN]["locks"][till["id"]]:
            data = await hass.async_add_executor_job(_load, _dir(hass, till["id"]))
            try:
                a = _find(data.get("amnen", []), body.get("amne"))
                g = _find(a["glosor"], body.get("glosor"))
            except ValueError:
                return self.json_message("Listan finns inte.", 400)
            lista = data.setdefault("forhor", [])
            if sum(1 for f in lista if f.get("syskon") == jag and f["status"] != "klart") >= 3:
                return self.json_message(f"{till['namn']} har redan tre förhör från dig att göra.", 400)
            riktning = int(body.get("riktning") or 0)
            lista.append({"id": _new_id(), "amne": a["id"], "glosor": g["id"], "namn": g["namn"], "amne_namn": a["namn"],
                          "meddelande": str(body.get("meddelande") or "").strip()[:200], "av_id": request["hass_user"].id, "av_namn": jag_namn,
                          "syskon": jag, "skapad": dt_util.now().isoformat(timespec="minutes"), "status": "skickat",
                          "fragor": _fragor(g, riktning), "svar": [], "riktning": riktning})
            del lista[:-300]
            await hass.async_add_executor_job(_save, _dir(hass, till["id"]), data)
        await _notis(hass, till.get("notify"), f"📋 Förhör från {jag_namn}", f"{g['namn']} ({a['namn']}). Öppna Läxspelet för att börja.", "/skolan")
        return self.json({"ok": True})


class PackaView(HomeAssistantView):
    """Packlistan: bocka av, och fasta saker per veckodag."""

    url = "/api/skolan/packa"
    name = "api:skolan:packa"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        body = await request.json()
        barn = _barn_for(hass, request, body.get("barn"))
        foralder = _ar_foralder(hass, request)
        p = 0
        async with hass.data[DOMAIN]["locks"][barn]:
            data = await hass.async_add_executor_job(_load, _dir(hass, barn))
            if body.get("op") == "bocka":
                p = packa.bocka(data, str(body.get("dag") or "")[:10], str(body.get("id") or ""), bool(body.get("pa")), not foralder)
            elif body.get("op") in ("fast_ny", "fast_bort"):
                packa.fast(data, int(body.get("veckodag") or 0), str(body.get("text") or ""), body.get("op") == "fast_bort")
            else:
                return self.json_message("Okänd åtgärd.", 400)
            await hass.async_add_executor_job(_save, _dir(hass, barn), data)
        return self.json({"packlista": packa.status(data), "p": p})


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
                    elif typ == "las" and not body.get("papper"):
                        raise ValueError("Välj en bok, eller välj att boken inte finns i appen.")
                    papper = typ == "las" and not bok_id  # boken finns inte i appen: barnet läser i den riktiga boken
                    if papper and not str(body.get("kapitel") or "").strip():
                        raise ValueError("Skriv vad som ska läsas, t.ex. \"SO-boken s. 40–52\".")
                    glosor = [g["id"] for g in a["glosor"] if g["id"] in (body.get("glosor") or [])]
                    if not sidor and not glosor and not papper:
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
                        **({"papper": True} if papper else {}),
                    }
                    fanns = _sla_ihop_uppdrag(data, lista, u)
                    if fanns:  # samma prov/läxa fanns redan på samma dag: informationen läggs till, ingen kopia
                        u = fanns
                    else:
                        _framsteg(data, u)
                        lista.append(u)
                    del lista[:-200]
                    if not foralder:  # fanns den redan från läraren, veckobrevet eller en förälder: minsta belöningen
                        meriter.registrerat(data, u, minsta=bool(fanns) and fanns.get("av_id") != user.id)
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
                    elif op == "pluggat_prov":  # barnet pluggade till provet utanför appen, en förälder godkänner
                        if foralder:
                            raise ValueError("Bara barnet kan säga att det har pluggat.")
                        idag = dt_util.now().date().isoformat()
                        if u["typ"] != "prov" or u.get("klart") or (u.get("datum") or "") <= idag:
                            raise ValueError("Det går bara före provdagen.")
                        if idag in u.get("studiedagar", []):
                            raise ValueError("Idag räknas redan som pluggdag för provet. 👍")
                        vantar = u.setdefault("pluggat_vantar", [])
                        if idag in vantar:
                            raise ValueError("Mamma eller pappa har redan fått frågan om idag.")
                        vantar.append(idag)
                        u.setdefault("pluggat_vad", {})[idag] = re.sub(r"\s+", " ", str(body.get("vad") or "")).strip()[:120]
                        for k in [k for k in u["pluggat_vad"] if k not in vantar]:
                            u["pluggat_vad"].pop(k, None)
                        be_om = (u, idag)
                    elif op in ("skriv_klar", "las_klar"):
                        if (u["typ"] != "skriv" and not (u["typ"] == "las" and u.get("papper"))) or u.get("klart"):
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
            entity = _ai_entitet(hass)
            n = 3 if len(u["sidor"]) < 15 else 4
            for forsok in range(3):
                try:
                    resp = await _ai_anrop(hass,
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
    "Du läser ett veckobrev eller ett meddelande från skolan (t.ex. en skärmdump från InfoMentor, Unikum, SchoolSoft, ett mejl eller sms) "
    "om läxor för ett barn i Sverige. Ta fram läxorna. Svara ENDAST med giltig JSON utan markdown, på formen "
    '{"kapitel": kapitelnummer som heltal eller null, "kapitel_namn": kapitlets namn om det står, annars null, '
    '"las_dagar": [veckodagar 0=måndag..4=fredag då läsläxan ska läsas], '
    '"hoglasning": true om läsningen görs högt/för en vuxen, annars false, '
    '"skriv_dag": veckodag 0–6 då uppgifterna i läxboken/skrivläxan ska lämnas in, eller null, '
    '"ord": [veckans ord/glosor exakt som de står], '
    '"diktamen_dag": veckodag 0–6 för diktamen/förhör på orden, eller null, '
    '"uppgifter": [{"typ": "las" om det är något att läsa, annars "gora" (räkna, svara på frågor, göra uppgifter, lämna in), "amne": ämne eller "", '
    '"vad": konkret och kort, t.ex. "Läs s. 40–52 i SO-boken" eller "Gör uppgift 3–5 på s. 12", "datum": "YYYY-MM-DD" då det ska vara klart}] '
    '(läxor med eget ämne eller datum, t.ex. från ett meddelande, som inte är veckans läsläxa/läxbok/ord ovan), '
    '"prov": [{"amne": ämne, "namn": kort namn t.ex. "Matteprov kapitel 3", "datum": "YYYY-MM-DD", "omfattning": vad provet handlar om/vad man ska plugga eller ""}], '
    '"handelser": [{"datum": "YYYY-MM-DD" eller "", "tid": "HH:MM" eller "", "text": kort beskrivning t.ex. "Utflykt till Skansen", "ta_med": vad man ska ta med eller ""}], '
    '"kom_ihag": [korta saker att komma ihåg som inte hör till en viss dag, t.ex. "Ta med matlåda och bestick vid skolmat"], '
    '"regler": [korta regler/instruktioner om läxorna, med egna ord], "note": kort kommentar eller ""}. '
    '"Varje vardag" betyder [0,1,2,3,4]. Räkna ut datum utifrån dagens datum (brev skrivna på helgen gäller veckan som kommer). '
    "Ta med ALLA prov, förhör, utflykter, idrottsdagar, lediga dagar, föräldramöten och annat viktigt, även om det inte finns några läxor. "
    'Hitta inte på något som inte står i brevet.'
)


def _vb_prompt() -> str:
    idag = dt_util.now().date()
    return f"Idag är det {VECKODAGAR_SV[idag.weekday()]} {idag.isoformat()}. " + VECKOBREV_PROMPT


VECKODAGAR_SV = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]

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
    a_ord = (_amne_match(amnen, str(ai["ord_amne"])) if ai.get("ord_amne") else None) or _hitta_amne(amnen, "ord", "glos")
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
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ai.get("forhor_datum") or "")):  # läraren gav ett datum (läxa utanför veckobrevet)
        diktamen = ai["forhor_datum"]
    g_finns = next((g for g in (a_ord or {}).get("glosor", []) if diktamen and g.get("forhor") == diktamen), None)
    titel = f"Kapitel {knr}" if knr else (knamn or "Veckans läsläxa")
    def iso(v):
        v = str(v or "")[:10]
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else ""

    uppgifter = []
    for x in (ai.get("uppgifter") or [])[:10]:
        if not isinstance(x, dict) or not str(x.get("vad") or "").strip():
            continue
        a = _amne_match(amnen, str(x.get("amne") or "")) if x.get("amne") else None
        uppgifter.append({"typ": "las" if x.get("typ") == "las" else "gora", "vad": str(x["vad"]).strip()[:200], "amne": (a or {}).get("id"),
                          "amne_namn": str(x.get("amne") or "")[:MAX_NAME], "datum": iso(x.get("datum")),
                          **({"extra": True, "frivillig": bool(x.get("frivillig")), "post": str(x.get("post") or "")[:40]} if x.get("extra") else {})})
    prov = []
    for x in (ai.get("prov") or [])[:6]:
        if not isinstance(x, dict) or not iso(x.get("datum")):
            continue
        a = _amne_match(amnen, str(x.get("amne") or "")) if x.get("amne") else None
        prov.append({"namn": str(x.get("namn") or f"{x.get('amne') or ''}-prov").strip()[:MAX_NAME], "amne": (a or {}).get("id"),
                     "amne_namn": str(x.get("amne") or "")[:MAX_NAME], "datum": iso(x["datum"]), "omfattning": str(x.get("omfattning") or "")[:200]})
    info = []
    for x in (ai.get("handelser") or [])[:12]:
        if isinstance(x, dict) and str(x.get("text") or "").strip():
            text = str(x["text"]).strip().rstrip(".")[:120] + "." + (f" Ta med: {str(x['ta_med']).strip().rstrip('.')[:80]}." if str(x.get("ta_med") or "").strip() else "")
            info.append({"text": text, "datum": iso(x.get("datum")), "tid": str(x.get("tid") or "")[:5] if re.fullmatch(r"\d{1,2}:\d{2}", str(x.get("tid") or "")) else ""})
    for x in (ai.get("kom_ihag") or [])[:10]:
        if str(x).strip():
            info.append({"text": str(x).strip()[:160], "datum": "", "tid": ""})
    return {
        "mandag": mandag.isoformat(),
        "prov": prov, "info": info, "uppgifter": uppgifter,
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
            "namn": str(ai.get("ord_namn") or "")[:MAX_NAME] or (g_finns or {}).get("namn") or f"Veckans ord v.{(mandag.isocalendar()[1])}",
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
                   "info": str(x.get("info") or "").strip()[:80], "ej": bool(x.get("ej"))})
    data["lektioner"] = sorted(ut, key=lambda x: (x["dag"], x["start"]))


MAX_FOTON = 6


async def _ta_emot_filer(hass: HomeAssistant, form, prefix: str) -> list[Path]:
    """Spara alla uppladdade filer (fältet "file", en eller flera) tillfälligt. Kastar ValueError vid fel."""
    falt = [f for f in form.getall("file", []) if hasattr(f, "file")][:MAX_FOTON]
    if not falt:
        raise ValueError("Ingen bild skickades.")
    ut = []
    try:
        for field in falt:
            mime = _mime(field)
            if not _ok_file(mime):
                raise ValueError("Bara bilder och PDF:er.")
            content = await hass.async_add_executor_job(field.file.read)
            if len(content) > MAX_BYTES:
                raise ValueError("En fil är för stor (max 20 MB).")
            ext = (Path(field.filename or "").suffix or mimetypes.guess_extension(mime) or ".jpg").lower()[:6]
            src = hass.data[DOMAIN]["base"] / f".{prefix}_{uuid.uuid4().hex}{ext}"
            await hass.async_add_executor_job(src.write_bytes, content)
            ut.append(src)
    except ValueError:
        await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in ut])
        raise
    return ut


def _kal_url(url: str) -> str:
    u = re.sub(r"^webcals?://", "https://", str(url or "").strip(), flags=re.I)
    if u and not re.fullmatch(r"https?://[^\s]{4,500}", u):
        raise ValueError("Klistra in hela länken till kalendern (börjar med https:// eller webcal://).")
    return u


async def _kalender_ladda(hass: HomeAssistant, url: str) -> list[dict]:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    try:
        async with async_get_clientsession(hass).get(_kal_url(url), timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                raise ValueError(f"Kalendern svarade {r.status}.")
            text = await r.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ValueError("Kunde inte hämta kalendern.") from err
    if "BEGIN:VCALENDAR" not in text[:2000]:
        raise ValueError("Länken ger ingen kalender (iCal).")
    return await hass.async_add_executor_job(meriter.ics_las, text)


# ---------- skolkalendrar: flera källor, var och en kan gälla flera barn ----------
KAL_TYPER = ("ics", "ha", "webb", "fil", "foto")
KAL_OM = {"ics": 3 * 3600, "ha": 3 * 3600, "webb": 24 * 3600}  # hur ofta källan hämtas igen (fil och foto: aldrig)
KAL_PROMPT = (
    "Du läser en skolkalender, läsårsplanering eller terminsplan för en svensk skola. Idag är det {idag}. "
    "Ta fram alla händelser: lov, utvecklingsdagar/studiedagar, lediga dagar, terminsstart och -avslutning, utflykter, "
    "föräldramöten, utvecklingssamtal, friluftsdagar, prov och annat viktigt. Räkna ut rätt år utifrån dagens datum. "
    'Svara ENDAST med giltig JSON: {{"handelser": [{{"start": "YYYY-MM-DD", "slut": "YYYY-MM-DD" (samma som start om det är en dag), '
    '"tid": "HH:MM" eller "", "text": kort beskrivning, "info": mer information eller ""}}]}}. Hitta inte på något som inte står där.'
)


def _kal_fil(hass: HomeAssistant) -> Path:
    return hass.data[DOMAIN]["base"] / "kalendrar.json"


# ---------- AI: Home Assistants ai_task eller Läxspelets egen koppling ----------
# Föräldern kan koppla in en AI direkt i Läxspelet (t.ex. Mistral, som Home Assistant saknar). Den används först när
# föräldern har testat den och tryckt på "Använd"; annars används Home Assistants AI-uppgift som förut.
AI_FIL = "ai.json"  # {leverantor, nyckel, modell, url, aktiv}. Nyckeln visas aldrig i appen.
AI_DIREKT = "skolan.direkt"


def _ai_direkt(hass: HomeAssistant, inst: dict | None = None) -> ai_lev.AI | None:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    d = inst if inst is not None else (hass.data[DOMAIN].get("ai_inst") or {})
    if (inst is None and not d.get("aktiv")) or d.get("leverantor") not in ai_lev.LEVERANTORER:
        return None
    return ai_lev.AI(d, lambda: async_get_clientsession(hass))


def _ai_entitet(hass: HomeAssistant) -> str | None:
    if _ai_direkt(hass):
        return AI_DIREKT
    return hass.data[DOMAIN]["conf"].get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)


async def _ai_anrop(hass: HomeAssistant, domain: str, service: str, data: dict, blocking: bool = True, return_response: bool = True) -> dict:
    """Som hass.services.async_call("ai_task", "generate_data", ...), men går till Läxspelets egen AI när den är vald.

    Varje AI-anrop får barnets trygghetsregel (aldrig hjälpa till att skada, aldrig be om personuppgifter eller träffar)."""
    if isinstance(data.get("instructions"), str) and "BARNETS TRYGGHET" not in data["instructions"]:
        data = {**data, "instructions": data["instructions"] + "\n\n" + plugg.TRYGG_REGEL}
    ai = _ai_direkt(hass)
    if ai:
        return await ai.generate_data(data, str(hass.data[DOMAIN]["tmp"].parent))
    return await hass.services.async_call(domain, service, {**data, "entity_id": data.get("entity_id") if data.get("entity_id") != AI_DIREKT else None},
                                          blocking=blocking, return_response=return_response)


class AiView(HomeAssistantView):
    """Föräldern kopplar in Läxspelets egen AI (t.ex. Mistral), testar den och väljer när den ska användas."""

    url = "/api/skolan/ai"
    name = "api:skolan:ai"

    def _foralder(self, request: web.Request) -> HomeAssistant:
        hass: HomeAssistant = request.app["hass"]
        if request["hass_user"].id not in hass.data[DOMAIN]["conf"]["foraldrar"]:
            raise web.HTTPForbidden
        return hass

    def _status(self, hass: HomeAssistant) -> dict:
        d = hass.data[DOMAIN].get("ai_inst") or {}
        ent = hass.data[DOMAIN]["conf"].get("ai_task_entity") or next((s.entity_id for s in hass.states.async_all("ai_task")), None)
        st = hass.states.get(ent) if ent else None
        ai = _ai_direkt(hass, d) if d.get("leverantor") else None
        return {"anvander": "direkt" if d.get("aktiv") and ai else "ha" if ent else "ingen",
                "ha": {"entitet": ent, "namn": (st.attributes.get("friendly_name") if st else None) or ent} if ent else None,
                "direkt": {"leverantor": d.get("leverantor"), "modell": ai.modell if ai else "", "beskrivning": ai.beskrivning if ai else "",
                           "har_nyckel": bool(d.get("nyckel")), "testad": d.get("testad"), "aktiv": bool(d.get("aktiv"))} if d.get("leverantor") else None,
                "leverantorer": ai_lev.publik_lista()}

    async def get(self, request: web.Request) -> web.Response:
        return self.json(self._status(self._foralder(request)))

    async def post(self, request: web.Request) -> web.Response:
        hass = self._foralder(request)
        body = await request.json()
        op = body.get("op")
        fil = hass.data[DOMAIN]["base"] / AI_FIL
        gammal = dict(hass.data[DOMAIN].get("ai_inst") or {})
        try:
            if op in ("spara", "modeller"):
                lev = body.get("leverantor")
                if lev not in ai_lev.LEVERANTORER:
                    raise ValueError("Välj en AI-tjänst.")
                nyckel = str(body.get("nyckel") or "").strip() or (gammal.get("nyckel", "") if gammal.get("leverantor") == lev else "")
                url = str(body.get("url") or "").strip()
                if url and not url.startswith(("http://", "https://")):
                    raise ValueError("Adressen ska börja med http:// eller https://")
                ny = {"leverantor": lev, "nyckel": nyckel, "modell": str(body.get("modell") or "").strip()[:120], "url": url[:300]}
                test = _ai_direkt(hass, ny)
                if op == "modeller":
                    try:
                        return self.json({"modeller": await test.modeller()})
                    except Exception as err:  # noqa: BLE001
                        raise ValueError(f"Kunde inte hämta modeller: {err}") from err
                try:
                    res = await test.testa()
                except Exception as err:  # noqa: BLE001
                    raise ValueError(f"AI:n fungerade inte: {err}") from err
                ny.update({"aktiv": bool(gammal.get("aktiv")) and gammal.get("leverantor") == lev, "testad": dt_util.now().isoformat(timespec="minutes")})
                hass.data[DOMAIN]["ai_inst"] = ny
                await hass.async_add_executor_job(_save_fil, fil, ny)
                return self.json({**self._status(hass), "varning": res.get("varning")})
            if op == "anvand":  # byt mellan Home Assistants AI och Läxspelets egen
                pa = bool(body.get("pa"))
                if pa and not (gammal.get("leverantor") and gammal.get("testad")):
                    raise ValueError("Testa och spara AI:n först.")
                gammal["aktiv"] = pa
                hass.data[DOMAIN]["ai_inst"] = gammal
                await hass.async_add_executor_job(_save_fil, fil, gammal)
            elif op == "ta_bort":
                hass.data[DOMAIN]["ai_inst"] = {}
                await hass.async_add_executor_job(lambda: fil.unlink(missing_ok=True))
            else:
                raise ValueError("Okänd åtgärd.")
        except ValueError as err:
            return self.json_message(str(err), 400)
        return self.json(self._status(hass))


async def _ai_text(hass: HomeAssistant, prompt: str, task_name: str) -> str:
    entity = _ai_entitet(hass)
    if not entity:
        raise RuntimeError("Ingen AI-uppgift finns i Home Assistant.")
    resp = await _ai_anrop(hass,"ai_task", "generate_data", {"task_name": task_name, "entity_id": entity, "instructions": prompt},
                                          blocking=True, return_response=True)
    text = (resp or {}).get("data")
    return text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)


def _kal_ai_svar(text: str) -> list[dict]:
    ai = _parse_json(text)
    ut = []
    for x in (ai.get("handelser") if isinstance(ai, dict) else None) or []:
        if isinstance(x, dict):
            h = meriter.kal_handelse(x.get("start"), x.get("slut"), x.get("text"), x.get("tid") or "", x.get("info") or "")
            if h:
                ut.append(h)
    return ut


async def _kal_ha(hass: HomeAssistant, entity: str) -> list[dict]:
    """Händelser från en kalender som redan finns i Home Assistant (Google, CalDAV, Outlook …)."""
    if not entity.startswith("calendar.") or not hass.states.get(entity):
        raise ValueError("Kalendern finns inte i Home Assistant.")
    nu = dt_util.now()
    resp = await hass.services.async_call("calendar", "get_events", {"entity_id": entity, "start_date_time": (nu - timedelta(days=7)).isoformat(),
                                          "end_date_time": (nu + timedelta(days=200)).isoformat()}, blocking=True, return_response=True)
    ut = []
    for e in (resp or {}).get(entity, {}).get("events", []):
        st, sl = str(e.get("start") or ""), str(e.get("end") or "")
        if len(st) == 10:  # heldag: slutdatum är dagen efter
            slut = (date.fromisoformat(sl[:10]) - timedelta(days=1)).isoformat() if len(sl) >= 10 else st
            h = meriter.kal_handelse(st, slut, e.get("summary"), "", e.get("description") or "", e.get("location") or "")
        else:
            a = dt_util.as_local(datetime.fromisoformat(st))
            b = dt_util.as_local(datetime.fromisoformat(sl)) if sl else a
            h = meriter.kal_handelse(a.date().isoformat(), b.date().isoformat(), e.get("summary"), a.strftime("%H:%M"), e.get("description") or "",
                                     e.get("location") or "", "", b.strftime("%H:%M"))
        if h:
            ut.append(h)
    return ut


async def _kal_webb(hass: HomeAssistant, url: str) -> list[dict]:
    """Skolans webbsida med kalender: texten på sidan läses av AI:n."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    u = _kal_url(url)
    try:
        async with async_get_clientsession(hass).get(u, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                raise ValueError(f"Sidan svarade {r.status}.")
            sida = await r.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ValueError("Kunde inte hämta sidan.") from err
    if "BEGIN:VCALENDAR" in sida[:2000]:  # det var en kalenderlänk ändå
        return await hass.async_add_executor_job(meriter.ics_las, sida)
    text = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", sida)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()[:25000]
    if len(text) < 40:
        raise ValueError("Hittade ingen text på sidan.")
    idag = dt_util.now().date().isoformat()
    return _kal_ai_svar(await _ai_text(hass, KAL_PROMPT.format(idag=idag) + "\n\nSidans text:\n" + text, "Läs skolans kalender"))


async def _kal_hamta_kalla(hass: HomeAssistant, k: dict) -> list[dict]:
    if k["typ"] == "ics":
        return await _kalender_ladda(hass, k["url"])
    if k["typ"] == "ha":
        return await _kal_ha(hass, k["entity"])
    if k["typ"] == "webb":
        return await _kal_webb(hass, k["url"])
    return k.get("handelser", [])


async def _kal_fordela(hass: HomeAssistant) -> None:
    """Varje barn får händelserna från de källor som gäller just det barnet."""
    kal = await hass.async_add_executor_job(_load_fil, _kal_fil(hass))
    for b in hass.data[DOMAIN]["conf"]["barn"]:
        alla = []
        for k in kal.get("kallor", []):
            if b["id"] in k.get("barn", []):
                alla += [{**x, "kalla": k["namn"]} for x in k.get("handelser", [])]
        ny = meriter.kalender_samla(alla)
        path = _dir(hass, b["id"])
        async with hass.data[DOMAIN]["locks"][b["id"]]:
            data = await hass.async_add_executor_job(_load, path)
            gammal, hade = data.get("skolkalender", []), "kalender" in data
            meriter.kalender_spara(data, ny)
            data.pop("kalender", None)  # gamla inställningen per barn (före kalenderkällorna)
            if data.get("skolkalender") != gammal or hade:
                await hass.async_add_executor_job(_save, path, data)


async def _kal_uppdatera(hass: HomeAssistant, kid: str | None = None, tvinga: bool = False) -> None:
    """Hämta källorna som är för gamla (eller en viss källa) och fördela till barnen."""
    async with hass.data[DOMAIN].setdefault("kal_lock", asyncio.Lock()):
        kal = await hass.async_add_executor_job(_load_fil, _kal_fil(hass))
        nu = dt_util.now()
        andrat = False
        for k in kal.get("kallor", []):
            if kid and k["id"] != kid:
                continue
            om = KAL_OM.get(k["typ"])
            if not om:
                continue
            if not tvinga and k.get("hamtad"):
                senast = datetime.fromisoformat(k["hamtad"])
                if senast.tzinfo is None:
                    senast = senast.replace(tzinfo=nu.tzinfo)
                if (nu - senast).total_seconds() < om:
                    continue
            try:
                k["handelser"], k["fel"] = (await _kal_hamta_kalla(hass, k))[:300], ""
            except (ValueError, RuntimeError, json.JSONDecodeError) as err:
                k["fel"] = str(err) or "Kunde inte hämta."
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Skolkalender %s: %s", k.get("namn"), err)
                k["fel"] = "Kunde inte hämta."
            k["hamtad"] = nu.isoformat(timespec="minutes")
            andrat = True
        if andrat:
            await hass.async_add_executor_job(_save_fil, _kal_fil(hass), kal)
    await _kal_fordela(hass)


async def _kal_migrera(hass: HomeAssistant) -> None:
    """Länkar som sparades per barn (1.79) blir kalenderkällor."""
    kal = await hass.async_add_executor_job(_load_fil, _kal_fil(hass))
    kallor = kal.setdefault("kallor", [])
    for b in hass.data[DOMAIN]["conf"]["barn"]:
        data = await hass.async_add_executor_job(_load, _dir(hass, b["id"]))
        url = (data.get("kalender") or {}).get("url")
        if url and not any(k.get("url") == url for k in kallor):
            kallor.append({"id": _new_id(), "typ": "ics", "namn": f"Skolkalender {b['namn']}", "url": url, "barn": [b["id"]], "handelser": []})
    await hass.async_add_executor_job(_save_fil, _kal_fil(hass), kal)


class KalenderView(HomeAssistantView):
    """Föräldrar sätter upp skolkalendrar: länk, kalender i HA, webbsida, fil eller foto."""

    url = "/api/skolan/kalendrar"
    name = "api:skolan:kalendrar"

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden
        kal = await hass.async_add_executor_job(_load_fil, _kal_fil(hass))
        idag = dt_util.now().date().isoformat()
        return self.json({
            "kallor": [{**{k: v for k, v in x.items() if k != "handelser"}, "antal": len(x.get("handelser", [])),
                        "kommande": [h for h in x.get("handelser", []) if h["slut"] >= idag][:60]} for x in kal.get("kallor", [])],
            "ha": [{"id": st.entity_id, "namn": st.attributes.get("friendly_name") or st.entity_id} for st in hass.states.async_all("calendar")],
            "barn": [{"id": b["id"], "namn": b["namn"]} for b in hass.data[DOMAIN]["conf"]["barn"]],
        })

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not _ar_foralder(hass, request):
            raise web.HTTPForbidden
        alla_barn = {b["id"] for b in hass.data[DOMAIN]["conf"]["barn"]}
        multipart = (request.content_type or "").startswith("multipart/")
        if multipart:
            form = await request.post()
            body = {"op": "lagg_till", "typ": form.get("typ"), "namn": form.get("namn"), "barn": str(form.get("barn") or "").split(",")}
        else:
            body = await request.json()
        op = body.get("op")
        try:
            if op == "lagg_till":
                typ = body.get("typ")
                if typ not in KAL_TYPER:
                    raise ValueError("Okänd sorts kalender.")
                barn = [b for b in body.get("barn") or [] if b in alla_barn]
                if not barn:
                    raise ValueError("Välj minst ett barn.")
                k = {"id": _new_id(), "typ": typ, "namn": _name(body.get("namn") or "Skolkalender"), "barn": barn, "handelser": [],
                     "skapad": dt_util.now().isoformat(timespec="minutes")}
                if typ in ("ics", "webb"):
                    k["url"] = _kal_url(body.get("url"))
                    if not k["url"]:
                        raise ValueError("Klistra in länken.")
                elif typ == "ha":
                    k["entity"] = str(body.get("entity") or "")
                if typ in ("fil", "foto"):  # läses en gång nu
                    if not multipart:
                        raise ValueError("Välj en fil.")
                    src = await _ta_emot_filer(hass, form, "kalender")
                    try:
                        if typ == "fil":
                            text = await hass.async_add_executor_job(lambda: src[0].read_bytes().decode("utf-8", "replace"))
                            if "BEGIN:VCALENDAR" not in text[:2000]:
                                raise ValueError("Filen är ingen kalenderfil (.ics).")
                            k["handelser"] = await hass.async_add_executor_job(meriter.ics_las, text)
                        else:
                            idag = dt_util.now().date().isoformat()
                            k["handelser"] = _kal_ai_svar(await _ai_las(hass, src, KAL_PROMPT.format(idag=idag), "Läs skolans kalender"))
                    finally:
                        await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in src])
                    if not k["handelser"]:
                        raise ValueError("Hittade inga händelser.")
                    k["hamtad"] = dt_util.now().isoformat(timespec="minutes")
                else:
                    k["handelser"] = (await _kal_hamta_kalla(hass, k))[:300]
                    k["hamtad"] = dt_util.now().isoformat(timespec="minutes")
                async with hass.data[DOMAIN].setdefault("kal_lock", asyncio.Lock()):
                    kal = await hass.async_add_executor_job(_load_fil, _kal_fil(hass))
                    kal.setdefault("kallor", []).append(k)
                    await hass.async_add_executor_job(_save_fil, _kal_fil(hass), kal)
            elif op in ("barn", "namn", "ta_bort"):
                async with hass.data[DOMAIN].setdefault("kal_lock", asyncio.Lock()):
                    kal = await hass.async_add_executor_job(_load_fil, _kal_fil(hass))
                    k = _find(kal.get("kallor", []), body.get("id"))
                    if op == "barn":
                        k["barn"] = [b for b in body.get("barn") or [] if b in alla_barn]
                    elif op == "namn":
                        k["namn"] = _name(body.get("namn"))
                    else:
                        kal["kallor"].remove(k)
                    await hass.async_add_executor_job(_save_fil, _kal_fil(hass), kal)
            elif op == "uppdatera":
                await _kal_uppdatera(hass, str(body.get("id") or ""), tvinga=True)
            else:
                raise ValueError("Okänd åtgärd.")
        except (ValueError, RuntimeError) as err:
            return self.json_message(str(err), 400)
        except json.JSONDecodeError:
            return self.json_message("AI:n svarade inte i rätt format. Försök igen.", 502)
        await _kal_fordela(hass)
        return await self.get(request)


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
        try:
            src = await _ta_emot_filer(hass, form, "schema")
        except ValueError as err:
            return self.json_message(str(err), 400)
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
            await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in src])
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
        try:
            src = await _ta_emot_filer(hass, form, "veckobrev")
        except ValueError as err:
            return self.json_message(str(err), 400)
        try:
            for forsok in range(3):
                try:
                    text = await _ai_las(hass, src, _vb_prompt(), "Läs veckobrev")
                    break
                except Exception as err:  # noqa: BLE001
                    if forsok == 2:
                        _LOGGER.warning("Veckobrev kunde inte läsas: %s", err)
                        return self.json_message(f"AI:n kunde inte läsa brevet: {err}", 502)
                    await asyncio.sleep(5)
        finally:
            await hass.async_add_executor_job(lambda: [p.unlink(missing_ok=True) for p in src])
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
    larare, larar_id = None, None  # brevet kom från läraren (Lärarrummet): prov, läxor och glosor märks med det
    if body.get("inkorg"):
        try:
            b_in = next((x for x in skola.las(path)["inkorg"] if x.get("id") == body["inkorg"]), None)
            larare, larar_id = (b_in or {}).get("larare") or None, (b_in or {}).get("larar_id") or None
        except Exception:  # noqa: BLE001
            larare = None
    kalla_brev = "larare" if larare else "veckobrev"

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
        fanns = _sla_ihop_uppdrag(data, lista, u)
        if fanns:
            hogl_id = fanns["id"]
            skapat.append(f"🔁 {fanns['namn']} (fanns redan, informationen lades till)")
        else:
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
        fanns = _sla_ihop_uppdrag(data, lista, u)
        if fanns:
            skapat.append(f"🔁 {fanns['namn']} (fanns redan, informationen lades till)")
        else:
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
        elif (g := _sla_ihop_glosor(a, _name(ord_.get("namn") or "Veckans ord"), forhor, par)):
            pass  # samma glosor fanns redan: nya ord lades till
        else:
            g = {"id": _new_id(), "namn": _name(ord_.get("namn") or "Veckans ord"), "sprak": sprak,
                 "par": par, "forhor": forhor, "skapad": dt_util.now().date().isoformat(), "av": "larare" if larare else "veckobrev", **({"larare": larare} if larare else {})}
            a["glosor"].append(g)
        skapat.append(f"📝 {g['namn']} ({len(par)} ord)")
    for x in (body.get("uppgifter") or [])[:10]:  # läxor ur ett meddelande: läsa (utan bok i appen) eller göra
        d = datum(x.get("datum"))
        vad = str(x.get("vad") or "").strip()[:200]
        if not vad:
            continue
        a = _find(amnen, x["amne"]) if x.get("amne") else None
        if a is None:
            namn_a = str(x.get("amne_namn") or "").strip()
            a = _amne_match(amnen, namn_a) if namn_a else None
            if a is None and namn_a:
                a = {"id": _new_id(), "namn": _name(namn_a), "farg": FARGER[len(amnen) % len(FARGER)], "bocker": [], "glosor": [], "delar": ["bocker", "glosor"]}
                amnen.append(a)
        if a is None:
            raise ValueError("Välj ett ämne för läxan.")
        las_ = x.get("typ") == "las"
        u = {"id": _new_id(), "typ": "las" if las_ else "skriv", "namn": _name(vad), "amne": a["id"], "amne_namn": a["namn"],
             "bok": None, "fran": None, "till": None, "kapitel": vad, "sidor": [], "glosor": [], "datum": d,
             "skapad": nu, "av_id": user.id, "av_namn": user.name, "kalla": "larare" if larare else "meddelande", **({"larare": larare} if larare else {}),
             **({"papper": True} if las_ else {"uppgift": True})}
        if x.get("extra"):  # extrauppgift från läraren: läraren får veta när den är klar
            u.update({"namn": _name(f"🎯 {'Frivillig extrauppgift' if x.get('frivillig') else 'Extrauppgift'}: {vad}"), "extra": True,
                      "frivillig": bool(x.get("frivillig")), "larar_post": str(x.get("post") or "")[:40] or None, "larar_id": larar_id})
        fanns = _sla_ihop_uppdrag(data, lista, u)
        if fanns:
            skapat.append(f"🔁 {fanns['namn']} (fanns redan, informationen lades till)")
            continue
        _framsteg(data, u)
        lista.append(u)
        skapat.append(f"{'📖' if las_ else '✏️'} {u['namn']}")
    for x in (body.get("prov") or [])[:6]:  # prov ur brevet blir riktiga prov (med provboss)
        d = datum(x.get("datum"))
        if not d:
            continue
        a = _find(amnen, x["amne"]) if x.get("amne") else None
        if a is None and str(x.get("amne_namn") or "").strip():
            a = _amne_match(amnen, x["amne_namn"])
            if a is None:
                a = {"id": _new_id(), "namn": _name(x["amne_namn"]), "farg": FARGER[len(amnen) % len(FARGER)], "bocker": [], "glosor": [], "delar": ["bocker", "glosor"]}
                amnen.append(a)
        if a is None:
            raise ValueError("Välj ett ämne för provet.")
        u = {"id": _new_id(), "typ": "prov", "namn": _name(x.get("namn") or f"{a['namn']}-prov"), "amne": a["id"], "amne_namn": a["namn"],
             "bok": None, "fran": None, "till": None, "kapitel": str(x.get("omfattning") or "")[:200], "sidor": [], "glosor": [],
             "datum": d, "skapad": nu, "av_id": user.id, "av_namn": user.name, "kalla": kalla_brev, **({"larare": larare} if larare else {})}
        fanns = _sla_ihop_uppdrag(data, lista, u)
        if fanns:  # samma prov igen: slås ihop (pluggdagarna ligger kvar)
            skapat.append(f"🔁 {fanns['namn']} (fanns redan, informationen lades till)")
            continue
        _framsteg(data, u)
        lista.append(u)
        skapat.append(f"📝 {u['namn']}")
    info = [x for x in (body.get("info") or [])[:20] if isinstance(x, dict) and str(x.get("text") or "").strip()]
    if info:
        si = data.setdefault("skolinfo", [])
        mandag = str(body.get("mandag") or "")[:10]
        for x in info:
            if any(y.get("text") == str(x["text"]).strip()[:200] and y.get("datum") == (datum(x.get("datum")) if x.get("datum") else "") for y in si):
                continue  # samma sak från skolan finns redan
            si.append({"id": _new_id(), "text": str(x["text"]).strip()[:200], "datum": datum(x.get("datum")) if x.get("datum") else "",
                       "tid": str(x.get("tid") or "")[:5], "vecka": mandag, "skapad": nu})
        del si[:-80]
        skapat.append(f"📌 {len(info)} saker från skolan")
    del lista[:-200]
    return skapat


def _jamfor_namn(t: str) -> str:
    return re.sub(r"[^a-z0-9åäö]+", "", str(t or "").lower())


def _samma_uppdrag(lista: list, typ: str, namn: str, datum: str | None, amne: str | None = None) -> dict | None:
    """Ett uppdrag på samma ställe: samma typ och samma dag, och samma ämne eller samma namn
    (stora/små bokstäver, mellanslag och tecken spelar ingen roll)."""
    n = _jamfor_namn(namn)
    return next((u for u in lista if u.get("typ") == typ and u.get("datum") == datum and not u.get("klart")
                 and ((amne and u.get("amne") == amne) or _jamfor_namn(u.get("namn")) == n)), None)


def _med_text(gammal: str, ny: str, max_len: int = 300) -> str:
    """Lägg till ny information utan att upprepa det som redan står där."""
    gammal, ny = str(gammal or "").strip(), str(ny or "").strip()
    if not ny or _jamfor_namn(ny) in _jamfor_namn(gammal):
        return gammal[:max_len]
    if not gammal or _jamfor_namn(gammal) in _jamfor_namn(ny):
        return ny[:max_len]
    return f"{gammal} · {ny}"[:max_len]


def _sla_ihop_uppdrag(data: dict, lista: list, u: dict) -> dict | None:
    """Finns redan ett prov/en läxa på samma ställe slås det nya ihop med det gamla så att all information kommer med.
    Returnerar det gamla uppdraget (som nu är uppdaterat), eller None om det nya ska läggas till."""
    gammal = _samma_uppdrag(lista, u.get("typ"), u.get("namn"), u.get("datum"), u.get("amne"))
    if not gammal:
        return None
    nn, gn = _jamfor_namn(u.get("namn")), _jamfor_namn(gammal.get("namn"))
    if nn and nn not in gn and gn not in nn:  # helt annat namn: det nya namnet blir en del av infon
        gammal["kapitel"] = _med_text(gammal.get("kapitel"), u.get("namn"))
    gammal["kapitel"] = _med_text(gammal.get("kapitel"), u.get("kapitel"))
    if not any(a["id"] == gammal.get("amne") for a in data.get("amnen", [])) and u.get("amne"):
        gammal["amne"], gammal["amne_namn"] = u["amne"], u.get("amne_namn")
    if u.get("bok") and not gammal.get("bok"):
        gammal.update({k: u.get(k) for k in ("bok", "fran", "till")})
    if u.get("bok") == gammal.get("bok"):
        har = {x.get("nyckel") for x in gammal.get("sidor") or []}
        gammal["sidor"] = list(gammal.get("sidor") or []) + [x for x in u.get("sidor") or [] if x.get("nyckel") not in har]
    gammal["glosor"] = list(dict.fromkeys(list(gammal.get("glosor") or []) + list(u.get("glosor") or [])))
    if u.get("dagar"):  # högläsning: alla läsdagar från båda
        har = {d["datum"] for d in gammal.get("dagar") or []}
        gammal["dagar"] = sorted(list(gammal.get("dagar") or []) + [d for d in u["dagar"] if d["datum"] not in har], key=lambda d: d["datum"])
    for k in ("papper", "uppgift"):
        if u.get(k):
            gammal[k] = True
    for k in ("extra", "frivillig", "larar_post", "larar_id", "larare"):  # extrauppgift/lärare: läraren ska få veta när den är klar
        if u.get(k) and not gammal.get(k):
            gammal[k] = u[k]
    _framsteg(data, gammal)
    return gammal


def _sla_ihop_glosor(a: dict, namn: str, forhor: str | None, par: list) -> dict | None:
    """Samma glosor en gång till (samma namn, eller samma förhörsdag) i samma ämne: lägg till nya ord i den gamla listan."""
    n = _jamfor_namn(namn)
    g = next((g for g in a.get("glosor", []) if _jamfor_namn(g.get("namn")) == n or (forhor and g.get("forhor") == forhor)), None)
    if not g:
        return None
    har = {_jamfor_namn(p[0]) for p in g.get("par", [])}
    for p in par:
        if _jamfor_namn(p[0]) not in har:
            g.setdefault("par", []).append(p)
            har.add(_jamfor_namn(p[0]))
        else:  # samma ord: fyll i översättningen om den saknades
            for q in g["par"]:
                if _jamfor_namn(q[0]) == _jamfor_namn(p[0]) and not str(q[1]).strip() and str(p[1]).strip():
                    q[1] = p[1]
    if forhor and not g.get("forhor"):
        g["forhor"] = forhor
    if _jamfor_namn(namn) != _jamfor_namn(g.get("namn")) and namn:
        g["namn"] = _name(f"{g['namn']} + {namn}")
    return g


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
    if not b:
        return None
    if not b.get("foto_vantar") and not (ok and len(meriter.foto_obetalda(b)) >= meriter.FOTO_MIN_SIDOR):
        return None  # en förälder kan också godkänna utan att barnet har frågat
    b.pop("foto_vantar", None)
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
    if u["typ"] == "prov":  # pluggade till provet utanför appen
        vantar = u.get("pluggat_vantar") or []
        if datum not in vantar:
            return None
        vantar.remove(datum)
        (u.get("pluggat_vad") or {}).pop(datum, None)
        if not ok:
            return f"🙈 Pluggandet till {u['namn']} blev inte godkänt. Visa mamma eller pappa vad du har gjort."
        meriter.prov_studiedag(data, u, datum)  # räknas för den dagen: svitdag och pluggdag mot provbossen
        return f"👍 Pluggandet till {u['namn']} är godkänt! Dagen räknas för sviten 🔥 och mot provbossen."
    if u["typ"] == "skriv" or (u["typ"] == "las" and u.get("papper")):
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
    elif u["typ"] == "prov":
        vad = (u.get("pluggat_vad") or {}).get(datum or "") or ""
        titel = f"📚 {namn} har pluggat till provet"
        text = f"{u['namn']} ({VECKODAG[date.fromisoformat(datum).weekday()]}){': ' + vad if vad else ''}. Pluggat utanför appen. Har du sett det? Godkänn?"
    elif u["typ"] == "bok":
        titel = f"📸 {namn} har fotat en bok"
        text = f"{u['namn']}: {u['sidor']} nya sidor (+{u['pris']} ⭐). Kolla att sidorna är skarpa och i rätt ordning. Godkänn?"
    elif u["typ"] == "las":
        titel = f"📖 {namn} har läst läsläxan"
        text = f"{u['namn']}: {u.get('kapitel') or ''}. Har du kollat? Godkänn?"
    elif u.get("uppgift"):
        titel = f"✏️ {namn} har gjort läxan"
        text = f"{u.get('amne_namn') or ''}: {u.get('kapitel') or u['namn']}. Har du kollat? Godkänn?"
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
            van = next((x for x in v["vanner"] if vanner.samma(x["kod"], kod)), None)
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
                        # glosorna kommer från ett annat hem: inga kontaktvägar (telefon, mejl, länkar, andra appar) når barnet
                        ord_ = [o for o in (body.get("ord") or []) if isinstance(o, dict) and o.get("fraga") and o.get("facit")
                                and len(str(o.get("fraga"))) <= 40 and len(str(o.get("facit"))) <= 40
                                and not any(vanner.har_kontakt(o.get(f)) for f in ("fraga", "facit", "fran", "till"))]
                        tillsammans.duell_ny(t, van_ref, mig, vanner.ren(body.get("namn"), 60, "Glosor") or "Glosor", ord_, sid, start)
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
    if not foralder:  # barnet får klasslänken bara för att synka med lärare som en förälder redan har godkänt
        if not any(s["foralder"].get(f) for f in skola.FUNKTIONER if f != "mejl") or not skola.har_godkand_larare(s):
            st["lank"] = ""
    else:
        st["smtp"] = await hass.async_add_executor_job(skola.smtp_publik, hass.data[DOMAIN]["base"])
    return st


FORALDER_INFO_VER = "2"  # höj när introduktionen (det föräldern kvitterar) ändras, så att föräldrarna läser den igen


def _foralder_kvittens(v) -> dict:
    """Förälderns kvittens: {ver, tid, ai_samtycke}. Version 1 sparades bara som versionsnumret."""
    d = v if isinstance(v, dict) else {"ver": v}
    return {"foralder_info": d.get("ver") == FORALDER_INFO_VER, "foralder_info_tid": d.get("tid"), "ai_samtycke": d.get("ai_samtycke")}


class ForalderInfoView(HomeAssistantView):
    """Föräldern kvitterar "Till dig som förälder": Läxspelet är ett komplement och ersätter inte föräldern."""

    url = "/api/skolan/foralder_info"
    name = "api:skolan:foralder_info"

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        user = request["hass_user"]
        if user.id not in hass.data[DOMAIN]["conf"]["foraldrar"]:
            raise web.HTTPForbidden
        try:
            body = await request.json()
        except ValueError:
            body = {}
        fil = hass.data[DOMAIN]["base"] / "foralder_info.json"
        async with _vlock(hass, "foralder_info"):
            d = await hass.async_add_executor_job(_load_fil, fil)
            # Kvittensen sparas med datum och version. AI-samtycket är vårdnadshavarens samtycke som flera AI-tjänster kräver för barn.
            d[user.id] = {"ver": FORALDER_INFO_VER, "tid": dt_util.now().isoformat(timespec="minutes"), "namn": user.name,
                          "ai_samtycke": bool((body or {}).get("ai_samtycke"))}
            await hass.async_add_executor_job(_save_fil, fil, d)
        return self.json({"ok": True})


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
                        las = _parse_json(await _ai_las(hass, mapp / "filer" / b["fil"]["namn"], _vb_prompt(), "Läs veckobrev från läraren"))
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
            elif op == "anmal":  # 🚩 föräldern anmäler en misstanke om en lärare till rektorn (läraren spärras direkt)
                barn_namn = next((b["namn"] for b in hass.data[DOMAIN]["conf"]["barn"] if b["id"] == barn), "")
                async with _vlock(hass, f"skola:{barn}"):
                    s = await hass.async_add_executor_job(skola.las, mapp)
                    lid_anm = str(body.get("larare") or "")
                    anm_namn = (s["lararna"].get(lid_anm) or {}).get("namn") or ""
                    anm = skola.anmal(s, lid_anm, body.get("text"), body.get("kontakt"), barn_namn)
                    await hass.async_add_executor_job(skola.spara, mapp, s)
                await _riktlinjer_bort(hass, barn, mapp, [(lid_anm, anm_namn)])
                _LOGGER.warning("Skolan: en förälder har anmält en misstanke om en lärare för %s och kopplat bort läraren", barn_namn)
                return self.json({**await _skola_status(hass, barn, True), "anmalan": anm})
            elif op in ("inkorg_material", "inkorg_prov"):
                await _inkorg_spara(hass, barn, mapp, op, body)
            elif op == "inkorg_riktlinje":  # föräldern godkänner en riktlinje från läraren
                async with hass.data[DOMAIN]["locks"][barn]:
                    async with _vlock(hass, f"skola:{barn}"):
                        s = await hass.async_add_executor_job(skola.las, mapp)
                        b = next((x for x in s["inkorg"] if x["id"] == body.get("id") and x["status"] == "ny" and x.get("typ") == "riktlinje"), None)
                        if not b:
                            raise ValueError("Det finns inte längre i inkorgen.")
                        data = await hass.async_add_executor_job(_load, mapp)
                        a = next((x for x in data.get("amnen", []) if x["id"] == body.get("amne")), None)
                        plugg.riktlinje_ny(data, a["id"] if a else "", a["namn"] if a else "Alla ämnen", b["text"], "larare",
                                           b.get("larare") or skola.huvudlarare(s).get("namn") or "Läraren", b.get("larar_id") or "")
                        b["status"] = "sparad"
                        await hass.async_add_executor_job(_save, mapp, data)
                        await hass.async_add_executor_job(skola.spara, mapp, s)
            else:
                async with _vlock(hass, f"skola:{barn}"):
                    s = await hass.async_add_executor_job(skola.las, mapp)
                    if op == "installningar":
                        skola.satt_installningar(s, body)
                    elif op == "koppla_bort":
                        lid_bort = str(body.get("larare") or "") or None
                        bort_namn = [(x["id"], x.get("namn") or "") for x in s["lararna"].values() if not lid_bort or x["id"] == lid_bort]
                        skola.koppla_bort(s, lid_bort)
                    elif op == "larare_godkann":  # föräldern godkänner en ny lärare (inget delas förrän nu)
                        skola.godkann_larare(s, str(body.get("larare") or ""))
                    elif op in ("skolan_godkann", "skolan_neka"):  # föräldern godkänner skolan och rektorn (eller en ny rektor)
                        skola.skolan_beslut(s, op == "skolan_godkann")
                    elif op == "skolan_bort":
                        skola.skolan_bort(s)
                    elif op in ("inkorg_klar", "inkorg_avvisa"):
                        b = next((x for x in s["inkorg"] if x["id"] == body.get("id")), None)
                        if b:
                            b["status"] = "sparad" if op == "inkorg_klar" else "avvisad"
                            if b.get("fil") and (op == "inkorg_avvisa" or b.get("typ", "veckobrev") in ("veckobrev", "schema")):
                                await hass.async_add_executor_job((mapp / "filer" / Path(b["fil"]["namn"]).name).unlink, True)
                    else:
                        raise ValueError("Okänd åtgärd.")
                    await hass.async_add_executor_job(skola.spara, mapp, s)
                if op == "koppla_bort":  # efter skolans lås (samma låsordning som annan kod: barnets lås före skolans)
                    await _riktlinjer_bort(hass, barn, mapp, bort_namn)
        except ValueError as err:
            return self.json_message(str(err), 400)
        return self.json(await _skola_status(hass, barn, True))


async def _riktlinjer_bort(hass: HomeAssistant, barn: str, mapp: Path, lararna: list[tuple[str, str]]) -> None:
    """Bortkopplade eller anmälda lärares riktlinjer slutar genast styra AI:n."""
    if not lararna:
        return
    async with hass.data[DOMAIN]["locks"][barn]:
        data = await hass.async_add_executor_job(_load, mapp)
        if sum(plugg.riktlinjer_bort_for_larare(data, lid, namn) for lid, namn in lararna):
            await hass.async_add_executor_job(_save, mapp, data)


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
                         "av_id": "larare", "av_namn": b.get("larare") or skola.huvudlarare(s).get("namn") or "Läraren"}
                    lista.append(u)
                    del lista[:-200]
                u["larar_prov"] = b.get("prov_id") or ""
                meriter.prov_resultat(data, u, {**b["resultat"], "av": b.get("larare") or skola.huvudlarare(s).get("namn") or "Läraren",
                                                "tid": dt_util.now().isoformat(timespec="minutes")})
            b["status"] = "sparad"
            await hass.async_add_executor_job(_save, mapp, data)
            await hass.async_add_executor_job(skola.spara, mapp, s)


async def _skolkonto_kolla(hass: HomeAssistant, token, pub: str) -> dict:
    """Kontrollera lärarens skolkonto-intyg mot Microsofts/Googles publika nycklar (sparas en stund)."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from . import skolkonto

    if not token:
        return {"bort": True}
    if not isinstance(token, str):
        return {"fel": "Intyget har fel format."}
    cache = hass.data[DOMAIN].setdefault("skolkonto", {"nycklar": {}, "klara": {}})
    nyckel = hashlib.sha256(f"{pub}|{token}".encode()).hexdigest()
    if nyckel in cache["klara"]:
        return cache["klara"][nyckel]
    lev = skolkonto.leverantor(token)
    if not lev or not skolkonto.klient(lev):
        return {"fel": "Intyget kommer inte från Microsoft eller Google."}
    nu = time.time()
    hamtad, jwks = cache["nycklar"].get(lev, (0, {}))
    kid = skolkonto.nyckel_id(token)
    saknas = not any(k.get("kid") == kid for k in jwks.get("keys", []))
    if nu - hamtad > 6 * 3600 or (saknas and nu - hamtad > 600):
        try:
            async with async_get_clientsession(hass).get(skolkonto.NYCKLAR[lev], timeout=aiohttp.ClientTimeout(total=15)) as r:
                jwks = await r.json(content_type=None)
            cache["nycklar"][lev] = (nu, jwks)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            _LOGGER.warning("Kunde inte hämta %s nycklar för skolkonton: %s", lev, err)
            return {}  # ingen slutsats nu, försök vid nästa synk
    try:
        res = {"ok": skolkonto.kontrollera(token, jwks, pub, nu)}
    except ValueError as err:
        res = {"fel": str(err)}
    if len(cache["klara"]) > 500:
        cache["klara"].clear()
    cache["klara"][nyckel] = res
    return res


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
            raw = await request.content.read(skola.MAX_FILER_PER_SYNK * 2)  # veckobrev, material och prov kan ha filer
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.json({"fel": "Fel format."}, status_code=400)
        mapp = _dir(hass, hitta["id"])
        # Lärarrummet 0.13.0+ skickar alltid "konto" (intyget eller null). Äldre lärarappar säger inget.
        konto = await _skolkonto_kolla(hass, body.get("konto"), str(body.get("pub") or "")) if "konto" in body else None
        async with hass.data[DOMAIN]["locks"][hitta["id"]]:
            async with _vlock(hass, f"skola:{hitta['id']}"):
                s = await hass.async_add_executor_job(skola.las, mapp)
                if not any(s["foralder"].get(f) for f in skola.FUNKTIONER if f != "mejl"):
                    return self.json({"fel": "Föräldern har inte slagit på något för läraren än."}, status_code=403)
                data = await hass.async_add_executor_job(_load, mapp)
                try:
                    svar = skola.ta_emot(s, data, hitta["namn"], body, plugg.studieteknik(data, fraga.alder(data)),
                                         raw, request.headers.get("X-Laxspelet-Signatur", ""), konto)
                except PermissionError as err:
                    return self.json({"fel": str(err)}, status_code=409)
                except ValueError as err:
                    return self.json({"fel": str(err)}, status_code=400)
                vantar_godk = bool(svar.get("_vantar"))
                if vantar_godk:  # läraren väntar på förälderns godkännande: bara kopplingen sparas, inget delas eller tas emot
                    await hass.async_add_executor_job(skola.spara, mapp, s)
                    vantar = []
                    forslag = svar.get("_forslag")
                else:
                    if skola.klassboss_belona(data, s):
                        await hass.async_add_executor_job(_save, mapp, data)
                    for namn, innehall in svar.pop("_filer"):
                        await hass.async_add_executor_job((mapp / "filer" / namn).write_bytes, innehall)
                    await hass.async_add_executor_job(skola.spara, mapp, s)
                    vantar = [x for x in s["inkorg"] if x.get("status") == "ny"]
                    forslag = svar.pop("_forslag", None)
                flaggor = svar.pop("_flaggor", []) if not vantar_godk else []
                sk_f = (s.get("skolan") or {}).get("forslag") or {}
                lar_namn = (s["lararna"].get(str(body.get("larar_id") or "")[:40]) or {}).get("namn") or "En lärare"
        if forslag:  # skolan, en ny rektor eller en ny lärare: föräldern ska veta (och godkänna skola och rektor)
            rubrik, text = {
                "skola": (f"🏫 {sk_f.get('namn') or 'En skola'} vill kopplas till {hitta['namn']}",
                          f"Rektor: {sk_f.get('rektor_namn') or '?'} (via {lar_namn}). Lärarna får inget om {hitta['namn']} förrän du har godkänt skolan i Läxspelet → Föräldrar → Skolan."),
                "rektor": (f"🏫 Ny rektor på {sk_f.get('namn') or 'skolan'}",
                           f"{sk_f.get('rektor_namn') or '?'} har tagit över efter den rektor du godkände. Godkänn i Läxspelet → Föräldrar → Skolan."),
                "larare": (f"👩‍🏫 {lar_namn} vill bli lärare för {hitta['namn']}",
                           f"Inget delas och inget når {hitta['namn']} förrän du godkänner. Känner du inte igen läraren: tryck Neka i Läxspelet → Föräldrar → Skolan."),
            }.get(forslag, ("", ""))
            for tjanst in hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values():
                await _notis(hass, tjanst, rubrik, text, f"/skolan?barn={hitta['id']}")
        if flaggor:  # läraren skickade fritext till barnet med kontaktuppgifter eller olämpligt innehåll: stoppat, föräldern får veta
            _LOGGER.warning("Skolan: text från läraren %s till %s stoppades", lar_namn, hitta["namn"])
            for tjanst in hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values():
                await _notis(hass, tjanst, f"⚠️ Text från {lar_namn} stoppades",
                             f"Läraren skickade något till {hitta['namn']} som innehöll kontaktuppgifter, en länk eller olämpligt innehåll, och det visas inte: "
                             f"\"{flaggor[0][:200]}\". Tycker du att det är konstigt: Läxspelet → Föräldrar → Skolan → 🚩 Anmäl misstanke.",
                             f"/skolan?barn={hitta['id']}")
        if vantar_godk:
            return self.json({"fel": "Föräldern har inte godkänt dig som lärare än. Be föräldern godkänna dig i Läxspelet → Föräldrar → Skolan."},
                             status_code=409)
        if svar.get("nya_veckobrev"):  # något nytt från läraren väntar på förälderns godkännande
            typer = {"veckobrev": "veckobrev", "material": "studiematerial", "prov": "provresultat", "schema": "schema", "riktlinje": "riktlinje till AI:n"}
            vad = ", ".join(sorted({typer.get(x.get("typ", "veckobrev"), "meddelande") for x in vantar[-svar["nya_veckobrev"]:]}))
            for tjanst in hass.data[DOMAIN]["conf"].get("foralder_notify", {}).values():
                await _notis(hass, tjanst, f"📬 Nytt från läraren till {hitta['namn']}",
                             f"{svar['nya_veckobrev']} sak{'er' if svar['nya_veckobrev'] > 1 else ''} väntar på att du godkänner: {vad}. Öppna Läxspelet → Föräldrar → Skolan.",
                             f"/skolan?barn={hitta['id']}")
        svar["skolan"] = VERSION
        return self.json(svar)


# Det barnets andra hem får använda (barnets egna funktioner och föräldrarnas läxfunktioner för just det barnet).
HEM_VYER = [StateView, ActionView, GlosstridView, LarView, FragaView, HjalpView, PlanView, HandstilView, SkrivView, PennaView, UploadView,
            FileView, EbokView, UtskriftView, ForhorView, UppdragView, VeckobrevView, LektionView, SchemaSidaView, UttalView, ExempelView, InspelningView,
            BoendeView, PackaView, ExtraView]
