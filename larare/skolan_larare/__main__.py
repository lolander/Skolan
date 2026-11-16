"""Startar Läxspelet Lärare. I Windows syns en ikon vid klockan.

python -m skolan_larare [--utan-ikon] [--port 8770] [--tyst]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import webbrowser

from skolan_larare import server


def _oppna(port: int) -> None:
    webbrowser.open(f"http://localhost:{port}/")


def _ikon(port: int) -> None:
    import pystray
    from PIL import Image

    meny = pystray.Menu(
        pystray.MenuItem("Öppna Läxspelet Lärare", lambda: _oppna(port), default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Avsluta", lambda ikon, _i=None: ikon.stop()),
    )
    pystray.Icon("SkolanLarare", Image.open(server.WEBB / "ikon-64.png"), "Läxspelet Lärare", meny).run()


def main() -> None:
    p = argparse.ArgumentParser(prog="skolan_larare")
    p.add_argument("--utan-ikon", action="store_true")
    p.add_argument("--port", type=int, default=server.STD_PORT)
    p.add_argument("--tyst", action="store_true", help="öppna inte webbläsaren vid start")
    a = p.parse_args()
    if server.port_upptagen(a.port):
        _oppna(a.port)
        return
    server.logga(server.datamapp())
    nar_klar = None if a.tyst else (lambda: _oppna(a.port))
    if a.utan_ikon:
        asyncio.run(server.huvud(a.port, nar_klar))
        return
    t = threading.Thread(target=lambda: asyncio.run(server.huvud(a.port, nar_klar)), daemon=True)
    t.start()
    try:
        _ikon(a.port)
    except Exception:  # noqa: BLE001
        t.join()
    sys.exit(0)


if __name__ == "__main__":
    main()
