"""AI via Googles Gemini (ersätter Home Assistants ai_task). Familjen lägger in en egen, gratis API-nyckel."""
from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent"
STD_MODELL = "gemini-flash-latest"
MAX_BILAGA = 20 * 1024 * 1024


class Gemini:
    def __init__(self, nyckel: str, modell: str = "", session_fn=None) -> None:
        self.nyckel = nyckel.strip()
        self.modell = (modell or STD_MODELL).strip()
        self._session_fn = session_fn

    def _session(self) -> ClientSession:
        return self._session_fn()

    async def fraga(self, instruktion: str, bilagor: list[tuple[str, bytes]] | None = None) -> str:
        delar: list[dict] = [{"text": instruktion}]
        for mime, data in bilagor or []:
            delar.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
        body = {"contents": [{"role": "user", "parts": delar}]}
        for forsok in range(3):
            async with self._session().post(URL.format(modell=self.modell), json=body,
                                            headers={"x-goog-api-key": self.nyckel},
                                            timeout=ClientTimeout(total=180)) as r:
                svar = await r.json(content_type=None)
            if r.status in (429, 500, 503) and forsok < 2:
                await asyncio.sleep(5 * (forsok + 1))
                continue
            if r.status >= 400:
                fel = ((svar or {}).get("error") or {}).get("message") or f"HTTP {r.status}"
                raise RuntimeError(f"Gemini: {fel}")
            kandidat = ((svar or {}).get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (kandidat.get("content") or {}).get("parts", []))
            if not text:
                raise RuntimeError(f"Gemini gav inget svar ({kandidat.get('finishReason') or 'okänt skäl'}).")
            return text
        raise RuntimeError("Gemini svarar inte just nu.")

    async def generate_data(self, data: dict, media_mapp: str) -> dict:
        """Samma form som Home Assistants ai_task.generate_data: {"data": text}."""
        bilagor = []
        for a in data.get("attachments") or []:
            mid = str(a.get("media_content_id") or "")
            delvag = mid.split("media-source://media_source/local/", 1)[-1]
            f = (Path(media_mapp) / delvag).resolve()
            if Path(media_mapp).resolve() not in f.parents or not f.is_file():
                raise RuntimeError("Bilagan hittades inte.")
            if f.stat().st_size > MAX_BILAGA:
                raise RuntimeError("Bilagan är för stor.")
            mime = a.get("media_content_type") or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            bilagor.append((mime, await asyncio.get_running_loop().run_in_executor(None, f.read_bytes)))
        return {"data": await self.fraga(str(data.get("instructions") or ""), bilagor)}

    async def testa(self) -> None:
        svar = await self.fraga("Svara bara med ordet: ok")
        if not svar.strip():
            raise RuntimeError("Tomt svar")
