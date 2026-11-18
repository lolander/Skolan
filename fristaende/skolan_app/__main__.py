"""Startar Skolan. I Windows syns en ikon vid klockan: Öppna Läxspelet, Koppla mobilen, Avsluta.

python -m skolan_app [--utan-ikon] [--port 8765]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import webbrowser


def _certifikat() -> None:
    """https ska fungera i den packade Windowsappen: använd Windows egna certifikat (även antivirus/företagsproxy),
    och certifis lista som reserv. Annars blir det CERTIFICATE_VERIFY_FAILED mot GitHub och AI-tjänsterna."""
    try:
        import truststore

        truststore.inject_into_ssl()
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:  # noqa: BLE001
        pass


_certifikat()

from skolan_app import server  # noqa: E402


def _oppna(port: int, vag: str = "/skolan") -> None:
    webbrowser.open(f"http://localhost:{port}{vag}")


def _ikon(port: int, styr: dict) -> None:
    import pystray
    from PIL import Image

    bild = Image.open(server.WEBB / "bilder" / "ikon-64.png")

    def avsluta(ikon, _item=None):
        if os.name == "nt":  # varna: mobilerna och det andra hemmet tappar kontakten
            try:
                import ctypes

                svar = ctypes.windll.user32.MessageBoxW(
                    0, "Om du avslutar Läxspelet kan barnens mobiler (och ett kopplat hem) inte nå det förrän det startas igen.\n\n"
                    "Att stänga webbläsaren räcker för att bara stänga fönstret. Läxspelet fortsätter då i bakgrunden.\n\n"
                    "Vill du ändå avsluta Läxspelet helt?", "Avsluta Läxspelet?", 0x4 | 0x30 | 0x100 | 0x40000)
                if svar != 6:  # 6 = Ja; Nej är förvalt
                    return
            except Exception:  # noqa: BLE001
                pass
        app, loop = styr.get("app"), styr.get("loop")
        if app and loop:
            app.avsluta = True
            loop.call_soon_threadsafe(app.omstart.set)
        ikon.stop()

    meny = pystray.Menu(
        pystray.MenuItem("Öppna Läxspelet", lambda: _oppna(port), default=True),
        pystray.MenuItem("Koppla en mobil", lambda: _oppna(port, "/app/koppla")),
        pystray.MenuItem("Inställningar", lambda: _oppna(port, "/app/installning")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Avsluta Läxspelet", avsluta),
    )
    pystray.Icon("Skolan", bild, "Läxspelet", meny).run()


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
    from skolan_app.paket import STORE, sekunder_sedan_start

    tyst = a.tyst or (STORE and sekunder_sedan_start() < 300)  # Store-appens autostart skickar inga flaggor
    nar_klar = None if tyst else (lambda: _oppna(a.port))
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
