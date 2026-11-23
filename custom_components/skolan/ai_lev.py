"""Läxspelets egen AI-koppling: används av Windowsappen och (valfritt) i Home Assistant i stället för ai_task.

Familjen väljer själv leverantör: Mistral, Anthropic Claude, OpenAI, Google Gemini, andra molntjänster med
OpenAI-kompatibelt API, eller en lokal AI på datorn (Ollama, LM Studio). Allt går genom generate_data(),
som har samma form som Home Assistants ai_task.generate_data: {"data": text}.

EN fil: custom_components/skolan/ai_lev.py. fristaende/skolan_app/ai.py är en exakt kopia (Windowsappen),
så ändra här och kopiera dit. Inga Home Assistant-importer här.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import struct
import zlib
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)
MAX_BILAGA = 20 * 1024 * 1024

# typ: gemini | anthropic | openai (OpenAI-kompatibelt chat/completions)
# bild: kan läsa bilder (med rätt modell), pdf: kan läsa PDF direkt
LEVERANTORER: dict[str, dict] = {
    "mistral": {"namn": "Mistral AI", "grupp": "moln", "typ": "openai", "url": "https://api.mistral.ai/v1",
                "modell": "mistral-small-latest", "nyckel": True, "bild": True, "pdf": True, "ocr": True, "rek": True,
                "info": "Rekommenderas. Europeiskt företag (Frankrike), så texter och foton stannar inom EU. Gratisplan finns. PDF läses av med Mistrals OCR."},
    "anthropic": {"namn": "Anthropic Claude", "grupp": "moln", "typ": "anthropic", "url": "https://api.anthropic.com/v1",
                  "modell": "claude-haiku-5-5", "nyckel": True, "bild": True, "pdf": True, "rek": True,
                  "info": "Rekommenderas. Mycket bra på svenska och på att förklara. Anthropic tillåter appar som barn använder, med skyddsåtgärder och tydlig AI-märkning (det gör Läxspelet)."},
    "openai": {"namn": "OpenAI (ChatGPT)", "grupp": "moln", "typ": "openai", "url": "https://api.openai.com/v1",
               "modell": "", "nyckel": True, "bild": True, "pdf": True,
               "info": "Företaget bakom ChatGPT. Välj en modell som kan läsa bilder."},

    "gemini": {"namn": "Google Gemini", "grupp": "moln", "typ": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta",
               "modell": "gemini-flash-latest", "nyckel": True, "bild": True, "pdf": True,
               "info": "Bra på foton och PDF.",
               "varning": "Googles villkor för Gemini API kräver att användaren är 18 år och tillåter inte appar som barn använder. Inom EU får sådana appar bara använda den betalda nivån. Välj hellre en annan tjänst."},
    "openrouter": {"namn": "OpenRouter (hundratals modeller)", "grupp": "moln", "typ": "openai", "url": "https://openrouter.ai/api/v1",
                   "modell": "", "nyckel": True, "bild": True, "pdf": False,
                   "info": "En nyckel till modeller från många företag."},
    "groq": {"namn": "Groq", "grupp": "moln", "typ": "openai", "url": "https://api.groq.com/openai/v1",
             "modell": "", "nyckel": True, "bild": True, "pdf": False,
             "info": "Mycket snabb. Bara vissa modeller kan läsa bilder."},
    "xai": {"namn": "xAI Grok", "grupp": "moln", "typ": "openai", "url": "https://api.x.ai/v1",
            "modell": "", "nyckel": True, "bild": True, "pdf": False, "info": "Grok från xAI."},
    "together": {"namn": "Together AI", "grupp": "moln", "typ": "openai", "url": "https://api.together.xyz/v1",
                 "modell": "", "nyckel": True, "bild": True, "pdf": False, "info": "Öppna modeller i molnet."},
    "ollama": {"namn": "Ollama (lokalt på datorn)", "grupp": "lokal", "typ": "openai", "url": "http://localhost:11434/v1",
               "modell": "", "nyckel": False, "bild": True, "pdf": False, "lokal": True,
               "info": "Ingenting lämnar hemmet. Installera Ollama och kör t.ex. 'ollama pull gemma3:12b' (kan läsa bilder). "
                       "Kräver en dator med bra grafikkort (helst 12–16 GB grafikminne), annars blir det långsamt. Sämre på svenska och foton än de stora."},
    "lmstudio": {"namn": "LM Studio (lokalt på datorn)", "grupp": "lokal", "typ": "openai", "url": "http://localhost:1234/v1",
                 "modell": "", "nyckel": False, "bild": True, "pdf": False, "lokal": True,
                 "info": "Ingenting lämnar hemmet. Installera LM Studio, ladda ner en modell som kan läsa bilder (t.ex. Gemma 3) och starta servern under Developer."},
    "egen": {"namn": "Annan (OpenAI-kompatibel adress)", "grupp": "egen", "typ": "openai", "url": "",
             "modell": "", "nyckel": False, "bild": True, "pdf": False,
             "info": "För andra tjänster eller servrar med OpenAI-kompatibelt API (t.ex. vLLM, LocalAI, Jan, Azure via proxy). Fyll i adressen som slutar på /v1."},
}


# Hjälp till familjerna: var man skaffar nyckeln, vad det kostar och om ett vanligt abonnemang räcker (det gör det aldrig för API:t).
HJALP = {
    "gemini": {"lank": "https://aistudio.google.com/apikey", "lank_text": "Skapa nyckel i Google AI Studio",
               "kostnad": "betala", "kostnad_text": "Inom EU kräver Googles villkor den betalda nivån för appar som barn använder: lägg till betalning i AI Studio.",
               "abonnemang": "Ett Gemini- eller Google One-abonnemang ingår inte.",
               "data": "Med betald nivå använder Google inte texterna för att förbättra sina tjänster.",
               "barn": "Googles villkor: användaren måste vara 18 år, och API:t får inte användas i appar som barn använder."},
    "anthropic": {"lank": "https://console.anthropic.com/settings/keys", "lank_text": "Skapa nyckel hos Anthropic",
                  "kostnad": "betala", "kostnad_text": "Ni sätter in en summa i förväg (t.ex. 5 dollar) som dras av lite i taget. Ingen månadsavgift.",
                  "abonnemang": "Claude Pro eller Max ingår inte. API:t betalas separat, även om ni redan har ett abonnemang.",
                  "data": "Anthropic tränar inte sina modeller på det ni skickar via API:t.",
                  "barn": "Anthropic tillåter appar som barn använder, med skyddsåtgärder och tydlig AI-märkning. Läxspelet märker AI-svaren och föräldern styr vad barnet gör."},
    "openai": {"lank": "https://platform.openai.com/api-keys", "lank_text": "Skapa nyckel hos OpenAI",
               "kostnad": "betala", "kostnad_text": "Ni sätter in en summa i förväg som dras av lite i taget. Ingen månadsavgift.",
               "abonnemang": "ChatGPT Plus eller Pro ingår inte. API:t har en egen betalning, även om ni redan har ChatGPT.",
               "data": "OpenAI använder inte det ni skickar via API:t för att förbättra tjänsten (om ni inte själva väljer det).",
               "barn": "OpenAI kräver att en förälder har gett sitt samtycke när barn använder tjänsten. Det gör du när du kopplar in den här."},
    "mistral": {"lank": "https://console.mistral.ai/api-keys", "lank_text": "Skapa nyckel hos Mistral",
                "kostnad": "gratis", "kostnad_text": "Gratis plan (Experiment) när man har verifierat sitt mobilnummer. Den har gränser per minut och månad. Det finns också en betalplan.",
                "abonnemang": "Le Chat Pro ingår inte.",
                "data": "På gratisplanen får Mistral använda texterna för att träna sina modeller, om ni inte stänger av det: Admin → Privacy i Mistrals konsol (gör det!).",
                "barn": "Mistral kräver att en förälder har gett sitt samtycke när barn använder tjänsten. Det gör du när du kopplar in den här."},
    "openrouter": {"lank": "https://openrouter.ai/keys", "lank_text": "Skapa nyckel hos OpenRouter",
                   "kostnad": "betala", "kostnad_text": "Ni sätter in en summa i förväg. Vissa modeller är gratis (märkta ”free”) men har låga gränser.",
                   "abonnemang": "Inga abonnemang från andra AI-företag ingår."},
    "groq": {"lank": "https://console.groq.com/keys", "lank_text": "Skapa nyckel hos Groq",
             "kostnad": "gratis", "kostnad_text": "Gratis med en gräns per dag, inget betalkort behövs.",
             "abonnemang": "Inget abonnemang behövs."},
    "xai": {"lank": "https://console.x.ai", "lank_text": "Skapa nyckel hos xAI",
            "kostnad": "betala", "kostnad_text": "Ni sätter in en summa i förväg som dras av lite i taget.",
            "abonnemang": "X Premium eller SuperGrok ingår inte."},
    "together": {"lank": "https://api.together.ai/settings/api-keys", "lank_text": "Skapa nyckel hos Together",
                 "kostnad": "betala", "kostnad_text": "Ni sätter in en summa i förväg som dras av lite i taget.", "abonnemang": "Inget abonnemang behövs."},
    "ollama": {"lank": "https://ollama.com/download", "lank_text": "Ladda ner Ollama",
               "kostnad": "lokal", "kostnad_text": "Helt gratis och ingen nyckel. Men datorn behöver ett bra grafikkort, annars blir det långsamt.",
               "abonnemang": "Inget konto eller abonnemang behövs."},
    "lmstudio": {"lank": "https://lmstudio.ai", "lank_text": "Ladda ner LM Studio",
                 "kostnad": "lokal", "kostnad_text": "Helt gratis och ingen nyckel. Men datorn behöver ett bra grafikkort, annars blir det långsamt.",
                 "abonnemang": "Inget konto eller abonnemang behövs."},
    "egen": {"kostnad": "egen", "kostnad_text": "Beror på tjänsten ni kopplar in.", "abonnemang": ""},
}


def _test_png() -> bytes:
    """En liten röd bild för att testa att modellen kan läsa bilder."""
    w = h = 16
    rader = b"".join(b"\x00" + b"\xdd\x22\x22" * w for _ in range(h))

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rader)) + chunk(b"IEND", b"")


class AI:
    def __init__(self, inst: dict, session_fn=None) -> None:
        self.lev = inst.get("leverantor") if inst.get("leverantor") in LEVERANTORER else "gemini"
        self.info = LEVERANTORER[self.lev]
        self.nyckel = str(inst.get("nyckel") or "").strip()
        self.modell = str(inst.get("modell") or self.info["modell"]).strip()
        self.url = str(inst.get("url") or self.info["url"]).strip().rstrip("/")
        self._session_fn = session_fn

    @property
    def beskrivning(self) -> str:
        return f"{self.info['namn']}{' · ' + self.modell if self.modell else ''}"

    def _session(self) -> ClientSession:
        return self._session_fn()

    def _timeout(self) -> ClientTimeout:
        return ClientTimeout(total=600 if self.info.get("lokal") or self.lev == "egen" else 180)

    async def _post(self, url: str, body: dict, headers: dict) -> dict:
        for forsok in range(3):
            try:
                async with self._session().post(url, json=body, headers=headers, timeout=self._timeout()) as r:
                    svar = await r.json(content_type=None)
                    status = r.status
            except (ClientError, asyncio.TimeoutError) as err:
                if self.info.get("lokal"):
                    raise RuntimeError(f"Får ingen kontakt med {self.info['namn']} på {self.url}. Är programmet igång?") from err
                if forsok < 2:
                    await asyncio.sleep(5 * (forsok + 1))
                    continue
                raise RuntimeError(f"{self.info['namn']} svarar inte ({err}).") from err
            if status in (429, 500, 502, 503, 529) and forsok < 2:
                await asyncio.sleep(5 * (forsok + 1))
                continue
            if status >= 400:
                fel = (svar or {}).get("error") if isinstance(svar, dict) else None
                fel = (fel.get("message") if isinstance(fel, dict) else fel) or f"HTTP {status}"
                raise RuntimeError(f"{self.info['namn']}: {fel}")
            return svar or {}
        raise RuntimeError(f"{self.info['namn']} svarar inte just nu.")

    async def fraga(self, instruktion: str, bilagor: list[tuple[str, bytes]] | None = None) -> str:
        if not self.modell:
            raise RuntimeError("Ingen AI-modell är vald. En förälder kan välja under Inställningar.")
        if self.info["nyckel"] and not self.nyckel:
            raise RuntimeError("AI-nyckel saknas. En förälder kan lägga in den under Inställningar.")
        bilagor = bilagor or []
        if self.info.get("ocr") and any(m == "application/pdf" for m, _ in bilagor):
            instruktion, bilagor = await self._ocr(instruktion, bilagor)
        if any(m == "application/pdf" for m, _ in bilagor) and not self.info["pdf"]:
            raise RuntimeError(f"{self.info['namn']} kan inte läsa PDF. Fota sidorna i stället, eller byt till Gemini, Claude eller OpenAI.")
        if bilagor and not self.info["bild"]:
            raise RuntimeError(f"{self.info['namn']} kan inte läsa bilder. Byt AI under Inställningar.")
        b64 = lambda d: base64.b64encode(d).decode()  # noqa: E731
        typ = self.info["typ"]
        if typ == "gemini":
            delar: list[dict] = [{"text": instruktion}] + [{"inline_data": {"mime_type": m, "data": b64(d)}} for m, d in bilagor]
            svar = await self._post(f"{self.url}/models/{self.modell}:generateContent", {"contents": [{"role": "user", "parts": delar}]},
                                    {"x-goog-api-key": self.nyckel})
            kandidat = (svar.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (kandidat.get("content") or {}).get("parts", []))
            if not text:
                raise RuntimeError(f"Gemini gav inget svar ({kandidat.get('finishReason') or 'okänt skäl'}).")
            return text
        if typ == "anthropic":
            innehall: list[dict] = []
            for m, d in bilagor:
                kalla = {"type": "base64", "media_type": m, "data": b64(d)}
                innehall.append({"type": "document" if m == "application/pdf" else "image", "source": kalla})
            innehall.append({"type": "text", "text": instruktion})
            svar = await self._post(f"{self.url}/messages", {"model": self.modell, "max_tokens": 8192, "messages": [{"role": "user", "content": innehall}]},
                                    {"x-api-key": self.nyckel, "anthropic-version": "2023-06-01"})
            text = "".join(b.get("text", "") for b in svar.get("content") or [] if b.get("type") == "text")
            if not text:
                raise RuntimeError(f"Claude gav inget svar ({svar.get('stop_reason') or 'okänt skäl'}).")
            return text
        # OpenAI-kompatibelt
        innehall = [{"type": "text", "text": instruktion}]
        for m, d in bilagor:
            if m == "application/pdf":
                innehall.append({"type": "file", "file": {"filename": "dokument.pdf", "file_data": f"data:{m};base64,{b64(d)}"}})
            else:
                innehall.append({"type": "image_url", "image_url": {"url": f"data:{m};base64,{b64(d)}"}})
        headers = {"Authorization": f"Bearer {self.nyckel}"} if self.nyckel else {}
        if self.lev == "openrouter":
            headers |= {"X-Title": "Läxspelet"}
        svar = await self._post(f"{self.url}/chat/completions",
                                {"model": self.modell, "messages": [{"role": "user", "content": innehall if bilagor else instruktion}]}, headers)
        val = (svar.get("choices") or [{}])[0]
        text = (val.get("message") or {}).get("content") or ""
        if isinstance(text, list):
            text = "".join(x.get("text", "") for x in text if isinstance(x, dict))
        if not text:
            raise RuntimeError(f"{self.info['namn']} gav inget svar ({val.get('finish_reason') or 'okänt skäl'}).")
        return text

    async def _ocr(self, instruktion: str, bilagor: list[tuple[str, bytes]]) -> tuple[str, list[tuple[str, bytes]]]:
        """Mistral: chatten läser inte PDF, så PDF-filer läses först av med Mistrals OCR och skickas som text."""
        texter, kvar = [], []
        for m, d in bilagor:
            if m != "application/pdf":
                kvar.append((m, d))
                continue
            svar = await self._post(f"{self.url}/ocr", {"model": "mistral-ocr-latest", "document": {
                "type": "document_url", "document_url": "data:application/pdf;base64," + base64.b64encode(d).decode()}},
                {"Authorization": f"Bearer {self.nyckel}"})
            sidor = [str(s.get("markdown") or "") for s in svar.get("pages") or []]
            if not any(x.strip() for x in sidor):
                raise RuntimeError("Mistral kunde inte läsa PDF-filen. Fota sidorna i stället.")
            texter.append("\n\n".join(f"[Sida {i + 1}]\n{x}" for i, x in enumerate(sidor)))
        if texter:
            instruktion += "\n\nTexten i den bifogade PDF-filen (avläst ord för ord):\n\n" + "\n\n---\n\n".join(texter)
        return instruktion, kvar

    async def modeller(self) -> list[str]:
        """Modeller som leverantören erbjuder (för listan i inställningarna)."""
        typ = self.info["typ"]
        try:
            if typ == "gemini":
                url, headers = f"{self.url}/models?pageSize=200", {"x-goog-api-key": self.nyckel}
            elif typ == "anthropic":
                url, headers = f"{self.url}/models?limit=100", {"x-api-key": self.nyckel, "anthropic-version": "2023-06-01"}
            else:
                url, headers = f"{self.url}/models", ({"Authorization": f"Bearer {self.nyckel}"} if self.nyckel else {})
            async with self._session().get(url, headers=headers, timeout=ClientTimeout(total=30)) as r:
                svar = await r.json(content_type=None)
                if r.status >= 400:
                    fel = (svar or {}).get("error") if isinstance(svar, dict) else None
                    raise RuntimeError((fel.get("message") if isinstance(fel, dict) else fel) or f"HTTP {r.status}")
        except (ClientError, asyncio.TimeoutError) as err:
            raise RuntimeError(f"Får ingen kontakt med {self.info['namn']} ({self.url}).") from err
        if typ == "gemini":
            ut = [m["name"].split("/", 1)[-1] for m in svar.get("models") or [] if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        else:
            ut = [m.get("id") for m in svar.get("data") or svar.get("models") or [] if isinstance(m, dict) and m.get("id")]
        return sorted(set(ut))

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

    async def testa(self) -> dict:
        """Testa text och bilder. Kastar fel om text inte fungerar; bildfel blir en varning."""
        svar = await self.fraga("Svara bara med ordet: ok")
        if not svar.strip():
            raise RuntimeError("Tomt svar")
        if not self.info["bild"]:
            return {"bild": False, "varning": "Den här AI:n kan inte läsa bilder, så foton av glosor, veckobrev, schema och böcker fungerar inte."}
        try:
            await self.fraga("Vilken färg har bilden? Svara med ett ord.", [("image/png", _test_png())])
        except Exception as err:  # noqa: BLE001
            return {"bild": False, "varning": f"Texten fungerar, men modellen kunde inte läsa en bild ({err}). Välj en modell som kan läsa bilder om ni vill fota glosor och veckobrev."}
        return {"bild": True}


def fran_inst(inst: dict, session_fn) -> AI | None:
    """AI enligt inställningarna. Gamla installationer hade bara inst["gemini"]."""
    ai = inst.get("ai")
    if not ai and (inst.get("gemini") or {}).get("nyckel"):
        ai = {"leverantor": "gemini", "nyckel": inst["gemini"]["nyckel"], "modell": inst["gemini"].get("modell", "")}
    if not ai:
        return None
    if ai.get("leverantor") not in LEVERANTORER:  # t.ex. DeepSeek, som har tagits bort (data till Kina): ingen AI tills föräldern väljer en ny
        _LOGGER.warning("AI-tjänsten %s finns inte längre i Läxspelet. Välj en ny under Inställningar.", ai.get("leverantor"))
        return None
    return AI(ai, session_fn)


def publik_lista() -> list[dict]:
    return [{"id": k, **{x: v[x] for x in ("namn", "grupp", "url", "modell", "nyckel", "bild", "pdf", "info")}, "rek": bool(v.get("rek")), "lokal": bool(v.get("lokal")),
             "varning": v.get("varning", ""), "barn": "Läs tjänstens villkor om barn innan ni väljer den." if v.get("grupp") == "moln" else "",
             **HJALP.get(k, {})} for k, v in LEVERANTORER.items()]
