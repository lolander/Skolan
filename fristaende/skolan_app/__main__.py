"""Startar Skolan. I Windows syns en ikon vid klockan: Öppna Skolan, Koppla mobilen, Avsluta.

python -m skolan_app [--utan-ikon] [--port 8765]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import webbrowser

from skolan_app import server


def _oppna(port: int, vag: str = "/skolan") -> None:
    webbrowser.open(f"http://localhost:{port}{vag}")


def _ikon(port: int, styr: dict) -> None:
    import pystray
    from PIL import Image

    bild = Image.open(server.WEBB / "bilder" / "ikon-64.png")

    def avsluta(ikon, _item=None):
        app, loop = styr.get("app"), styr.get("loop")
        if app and loop:
            app.avsluta = True
            loop.call_soon_threadsafe(app.omstart.set)
        ikon.stop()

    meny = pystray.Menu(
        pystray.MenuItem("Öppna Skolan", lambda: _oppna(port), default=True),
        pystray.MenuItem("Koppla en mobil", lambda: _oppna(port, "/app/koppla")),
        pystray.MenuItem("Inställningar", lambda: _oppna(port, "/app/installning")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Avsluta Skolan", avsluta),
    )
    pystray.Icon("Skolan", bild, "Skolan", meny).run()


def main() -> None:
    p = argparse.ArgumentParser(prog="skolan")
    p.add_argument("--utan-ikon", action="store_true", help="ingen ikon vid klockan (t.ex. på en server)")
    p.add_argument("--port", type=int, default=server.STD_PORT)
    p.add_argument("--tyst", action="store_true", help="öppna inte webbläsaren vid start")
    a = p.parse_args()

    if server.port_upptagen(a.port):  # Skolan körs redan: visa den bara
        _oppna(a.port)
        return
    server.logga(server.datamapp())
    nar_klar = None if a.tyst else (lambda: _oppna(a.port))
    styr: dict = {}
    if a.utan_ikon:
        asyncio.run(server.huvud(a.port, nar_klar, styr))
        return
    t = threading.Thread(target=lambda: asyncio.run(server.huvud(a.port, nar_klar, styr)), daemon=True)
    t.start()
    try:
        _ikon(a.port, styr)
    except Exception:  # noqa: BLE001  ingen ikon möjlig (t.ex. inget skrivbord): kör ändå
        t.join()
    sys.exit(0)


if __name__ == "__main__":
    main()
