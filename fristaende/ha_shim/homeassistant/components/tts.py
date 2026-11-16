"""Ingen molnröst i Windowsappen: Skolan faller då tillbaka på webbläsarens egen uppläsning."""


def generate_media_source_id(*_a, **_kw):
    raise RuntimeError("Ingen TTS i fristående läge")


async def async_get_media_source_audio(*_a, **_kw):
    raise RuntimeError("Ingen TTS i fristående läge")
