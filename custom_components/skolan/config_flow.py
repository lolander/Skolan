"""Inställningsguide för Skolan: barn, föräldrar, telefoner och AI."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

DOMAIN = "skolan"


async def _anvandare(hass) -> dict[str, str]:
    """Riktiga användare (inte systemanvändare): id -> namn."""
    return {u.id: u.name or u.id for u in await hass.auth.async_get_users() if not u.system_generated and u.is_active}


def _notistjanster(hass) -> list[str]:
    return sorted(s for s in hass.services.async_services().get("notify", {}) if s.startswith("mobile_app_"))


def _val(alternativ: dict[str, str] | list[str], flera: bool = False) -> selector.SelectSelector:
    opts = [selector.SelectOptionDict(value=k, label=v) for k, v in alternativ.items()] if isinstance(alternativ, dict) \
        else [selector.SelectOptionDict(value=k, label=k) for k in alternativ]
    return selector.SelectSelector(selector.SelectSelectorConfig(options=opts, multiple=flera, mode=selector.SelectSelectorMode.DROPDOWN))


class SkolanFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {"barn": [], "foraldrar": [], "foralder_notify": {}}

    async def async_step_user(self, user_input: dict | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            self._data["ai_task_entity"] = user_input.get("ai_task_entity")
            return await self.async_step_barn()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Optional("ai_task_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task")),
        }))

    async def async_step_barn(self, user_input: dict | None = None):
        anv = await _anvandare(self.hass)
        fel = {}
        if user_input is not None:
            bid = slugify(user_input["namn"])
            if not bid or any(b["id"] == bid for b in self._data["barn"]):
                fel["namn"] = "namn_finns"
            elif any(b["user_id"] == user_input["anvandare"] for b in self._data["barn"]):
                fel["anvandare"] = "anvandare_finns"
            else:
                barn = {"id": bid, "namn": user_input["namn"].strip(), "user_id": user_input["anvandare"]}
                if user_input.get("notify"):
                    barn["notify"] = user_input["notify"]
                if user_input.get("klocka"):
                    barn["klocka"] = user_input["klocka"].strip()
                self._data["barn"].append(barn)
                if user_input.get("fler"):
                    return await self.async_step_barn()
                return await self.async_step_foraldrar()
        return self.async_show_form(step_id="barn", errors=fel, description_placeholders={"antal": str(len(self._data["barn"]))},
                                    data_schema=vol.Schema({
            vol.Required("namn"): str,
            vol.Required("anvandare"): _val(anv),
            vol.Optional("notify"): _val(_notistjanster(self.hass)),
            vol.Optional("klocka"): str,
            vol.Optional("fler", default=False): bool,
        }))

    async def async_step_foraldrar(self, user_input: dict | None = None):
        barn_id = {b["user_id"] for b in self._data["barn"]}
        anv = {k: v for k, v in (await _anvandare(self.hass)).items() if k not in barn_id}
        if user_input is not None:
            self._data["foraldrar"] = user_input["foraldrar"]
            return await self.async_step_notiser()
        return self.async_show_form(step_id="foraldrar", data_schema=vol.Schema({
            vol.Required("foraldrar"): _val(anv, flera=True),
        }))

    async def async_step_notiser(self, user_input: dict | None = None):
        anv = await _anvandare(self.hass)
        tjanster = _notistjanster(self.hass)
        if user_input is not None:
            self._data["foralder_notify"] = {uid: user_input[uid] for uid in self._data["foraldrar"] if user_input.get(uid)}
            return self.async_create_entry(title="Skolan", data=self._data)
        schema = {vol.Optional(uid, description={"suggested_value": None}): _val(tjanster) for uid in self._data["foraldrar"]}
        return self.async_show_form(step_id="notiser", data_schema=vol.Schema(schema),
                                    description_placeholders={"namn": ", ".join(anv.get(u, u) for u in self._data["foraldrar"])})

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return SkolanAlternativ()


class SkolanAlternativ(config_entries.OptionsFlow):
    """Lägg till ett barn eller byt AI-tjänst i efterhand (kräver omstart)."""

    async def async_step_init(self, user_input: dict | None = None):
        return self.async_show_menu(step_id="init", menu_options=["nytt_barn", "ai"])

    async def async_step_ai(self, user_input: dict | None = None):
        d = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, "ai_task_entity": user_input.get("ai_task_entity")})
        return self.async_show_form(step_id="ai", data_schema=vol.Schema({
            vol.Optional("ai_task_entity", description={"suggested_value": d.get("ai_task_entity")}):
                selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task")),
        }))

    async def async_step_nytt_barn(self, user_input: dict | None = None):
        d = {**self.config_entry.data, **self.config_entry.options}
        barn = list(d.get("barn", []))
        fel = {}
        if user_input is not None:
            bid = slugify(user_input["namn"])
            if not bid or any(b["id"] == bid for b in barn):
                fel["namn"] = "namn_finns"
            else:
                nytt = {"id": bid, "namn": user_input["namn"].strip(), "user_id": user_input["anvandare"]}
                if user_input.get("notify"):
                    nytt["notify"] = user_input["notify"]
                return self.async_create_entry(data={**self.config_entry.options, "barn": barn + [nytt]})
        return self.async_show_form(step_id="nytt_barn", errors=fel, data_schema=vol.Schema({
            vol.Required("namn"): str,
            vol.Required("anvandare"): _val(await _anvandare(self.hass)),
            vol.Optional("notify"): _val(_notistjanster(self.hass)),
        }))
