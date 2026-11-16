"""Webbnotiser till telefoner och datorer (ersätter Home Assistant-appens notiser).

Skolan skickar notiser till tjänsten "push_<person-id>". Varje person kan ha flera enheter.
iPhone kräver att Skolan är tillagd på hemskärmen och nås via https (fjärråtkomst påslagen).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
PREFIX = "push_"


def tjanst(pid: str) -> str:
    return f"{PREFIX}{pid}"


class Push:
    def __init__(self, mapp: Path, kontakt: str = "mailto:skolan@example.invalid") -> None:
        self.mapp = mapp
        self.kontakt = kontakt
        self.nyckelfil = mapp / "vapid.pem"
        self.fil = mapp / "push.json"
        self.prenumerationer: dict[str, list[dict]] = self._las()
        self.publik_nyckel = self._nycklar()

    def _las(self) -> dict:
        try:
            return json.loads(self.fil.read_text("utf-8")) if self.fil.exists() else {}
        except (OSError, ValueError):
            return {}

    def _spara(self) -> None:
        tmp = self.fil.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.prenumerationer), "utf-8")
        tmp.replace(self.fil)

    def _nycklar(self) -> str:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid

        if not self.nyckelfil.exists():
            v = Vapid()
            v.generate_keys()
            v.save_key(str(self.nyckelfil))
        v = Vapid.from_file(str(self.nyckelfil))
        pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        return base64.urlsafe_b64encode(pub).decode().rstrip("=")

    def prenumerera(self, pid: str, sub: dict) -> None:
        if not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://"):
            raise ValueError("Ogiltig prenumeration.")
        lista = [x for x in self.prenumerationer.get(pid, []) if x.get("endpoint") != sub["endpoint"]]
        lista.append({"endpoint": sub["endpoint"], "keys": sub.get("keys", {})})
        self.prenumerationer[pid] = lista[-5:]
        self._spara()

    def avsluta(self, pid: str, endpoint: str) -> None:
        self.prenumerationer[pid] = [x for x in self.prenumerationer.get(pid, []) if x.get("endpoint") != endpoint]
        self._spara()

    def har(self, pid: str) -> bool:
        return bool(self.prenumerationer.get(pid))

    async def skicka(self, service: str, data: dict) -> None:
        if not service.startswith(PREFIX):
            return
        if data.get("message") == "clear_notification":
            return
        pid = service[len(PREFIX):]
        extra = data.get("data") or {}
        payload = json.dumps({"title": data.get("title") or "Skolan", "body": data.get("message") or "",
                              "url": extra.get("url") or "/skolan", "image": extra.get("image"),
                              "tag": extra.get("tag")}, ensure_ascii=False)
        await asyncio.get_running_loop().run_in_executor(None, self._skicka_alla, pid, payload)

    def _skicka_alla(self, pid: str, payload: str) -> None:
        from pywebpush import WebPushException, webpush

        borta = []
        for sub in list(self.prenumerationer.get(pid, [])):
            try:
                webpush(sub, payload, vapid_private_key=str(self.nyckelfil), vapid_claims={"sub": self.kontakt}, ttl=3600)
            except WebPushException as err:
                kod = getattr(err.response, "status_code", 0)
                if kod in (404, 410):
                    borta.append(sub["endpoint"])
                else:
                    _LOGGER.warning("Notisen kom inte fram: %s", err)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Notisen kom inte fram: %s", err)
        for e in borta:
            self.avsluta(pid, e)
