"""Värden: det lilla av Home Assistant som Skolans integration behöver, fast fristående.

Skolans kod (custom_components/skolan) körs oförändrad. Här finns:
- hass.data, hass.config, executor-jobb och bakgrundsuppgifter
- tidsstyrda jobb (async_track_time_change)
- tjänster: ai_task.generate_data (Gemini), notify.* (webbnotiser), mqtt finns inte
- http: vyer och statiska filer i en aiohttp-app, med inloggning via konto.py
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from aiohttp import ClientSession, web

from homeassistant.core import Event, State
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)
METODER = ("get", "post", "put", "delete", "patch")


@dataclass
class Anvandare:
    id: str
    name: str
    is_admin: bool = False


class _Config:
    def __init__(self, mapp: Path) -> None:
        self.config_dir = str(mapp)
        self.media_dirs = {"local": str(mapp / "media")}
        self.internal_url = ""
        self.external_url = ""

    def path(self, *delar: str) -> str:
        return str(Path(self.config_dir, *delar))


class _Bus:
    def __init__(self) -> None:
        self._lyss: dict[str, list[tuple[Callable, bool]]] = {}

    def async_listen(self, typ: str, cb: Callable) -> Callable:
        self._lyss.setdefault(typ, []).append((cb, False))
        return lambda: None

    def async_listen_once(self, typ: str, cb: Callable) -> Callable:
        self._lyss.setdefault(typ, []).append((cb, True))
        return lambda: None

    async def fire(self, typ: str, data: dict | None = None) -> None:
        lista = self._lyss.get(typ, [])
        self._lyss[typ] = [x for x in lista if not x[1]]
        for cb, _ in lista:
            r = cb(Event(typ, data or {}))
            if asyncio.iscoroutine(r):
                await r


class _States:
    def __init__(self, varden: "Varden") -> None:
        self._v = varden
        self._s: dict[str, State] = {}

    def async_all(self, domain: str | None = None) -> list[State]:
        ut = list(self._s.values())
        if domain == "ai_task" and self._v.ai:
            ut.append(State("ai_task.gemini", "idle"))
        return [s for s in ut if domain is None or s.entity_id.startswith(domain + ".")]

    def async_set(self, entity_id: str, state: Any, attributes: dict | None = None) -> None:
        self._s[entity_id] = State(entity_id, str(state), attributes or {})

    def get(self, entity_id: str) -> State | None:
        return self._s.get(entity_id)


class _Services:
    def __init__(self, varden: "Varden") -> None:
        self._v = varden

    def has_service(self, domain: str, service: str) -> bool:
        return domain in ("ai_task", "notify")

    async def async_call(self, domain: str, service: str, data: dict | None = None, blocking: bool = False,
                         return_response: bool = False, **_kw) -> Any:
        data = data or {}
        if domain == "ai_task" and service == "generate_data":
            if not self._v.ai:
                raise RuntimeError("Ingen AI-nyckel är inlagd. En förälder kan lägga in den under Inställningar.")
            return await self._v.ai.generate_data(data, self._v.config.media_dirs["local"])
        if domain == "notify":
            if self._v.push:
                await self._v.push.skicka(service, data)
            return None
        _LOGGER.debug("Tjänsten %s.%s finns inte i fristående läge", domain, service)
        return None


class _Http:
    def __init__(self, varden: "Varden") -> None:
        self._v = varden

    def register_view(self, view) -> None:
        app = self._v.app
        for metod in METODER:
            fn = getattr(view, metod, None)
            if not fn:
                continue
            for url in [view.url, *getattr(view, "extra_urls", [])]:
                app.router.add_route(metod.upper(), url, self._v.konto.skydda(fn, view.requires_auth))

    async def async_register_static_paths(self, lista) -> None:
        for s in lista:
            self._v.app.router.add_static(s.url_path, s.path)


class Varden:
    """Ersätter `hass` för Skolans integration."""

    def __init__(self, mapp: Path, app: web.Application, konto, ai=None, push=None) -> None:
        self.data: dict[str, Any] = {}
        self.config = _Config(mapp)
        self.bus = _Bus()
        self.states = _States(self)
        self.services = _Services(self)
        self.http = _Http(self)
        self.app = app
        self.konto = konto
        self.ai = ai
        self.push = push
        self.is_running = False
        self.panel: dict = {}
        self._tider: list[tuple[Callable, set | None, set | None, set | None]] = []
        self._session: ClientSession | None = None
        self._uppgifter: set[asyncio.Task] = set()
        app["hass"] = self

    # ---------- uppgifter ----------
    async def async_add_executor_job(self, fn: Callable, *args):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *args)

    def async_create_task(self, coro, name: str | None = None) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro, name=name)
        self._uppgifter.add(t)
        t.add_done_callback(self._klar)
        return t

    def async_create_background_task(self, coro, name: str | None = None, **_kw) -> asyncio.Task:
        return self.async_create_task(coro, name)

    def _klar(self, t: asyncio.Task) -> None:
        self._uppgifter.discard(t)
        if not t.cancelled() and t.exception():
            _LOGGER.error("Bakgrundsjobb misslyckades", exc_info=t.exception())

    def http_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession()
        return self._session

    # ---------- klockan ----------
    def lagg_till_tid(self, action: Callable, h, m, s) -> Callable:
        rad = (action, h, m, s)
        self._tider.append(rad)
        return lambda: self._tider.remove(rad) if rad in self._tider else None

    async def _ticka(self) -> None:
        senast = None
        while True:
            nu = dt_util.now().replace(microsecond=0)
            if nu != senast:
                senast = nu
                for action, h, m, s in list(self._tider):
                    # som i Home Assistant: det som inte anges matchar alla värden
                    if (s is None or nu.second in s) and (m is None or nu.minute in m) and (h is None or nu.hour in h):
                        r = action(nu)
                        if asyncio.iscoroutine(r):
                            self.async_create_task(r)
            await asyncio.sleep(1.02 - dt_util.now().microsecond / 1e6)

    async def starta(self) -> None:
        self.is_running = True
        self.async_create_task(self._ticka(), "klocka")
        await self.bus.fire("homeassistant_started")

    async def stoppa(self) -> None:
        for t in list(self._uppgifter):
            t.cancel()
        if self._session:
            await self._session.close()
