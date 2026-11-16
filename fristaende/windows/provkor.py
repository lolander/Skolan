"""Provkör den byggda appen i GitHub Actions (Windows): start, första start, inloggning, Skolan, fjärrtunnel.

python provkor.py <sökväg till Skolan.exe>
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

EXE = sys.argv[1]
PORT = 8799
BAS = f"http://127.0.0.1:{PORT}"


def anrop(vag, body=None, token="", bas=BAS):
    req = urllib.request.Request(bas + vag, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def vanta(villkor, sek=90, text=""):
    slut = time.time() + sek
    while time.time() < slut:
        try:
            if villkor():
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    raise SystemExit(f"FEL: tog för lång tid: {text}")


data = tempfile.mkdtemp()
proc = subprocess.Popen([EXE, "--utan-ikon", "--tyst", "--port", str(PORT)], env={**os.environ, "SKOLAN_DATA": data})
try:
    vanta(lambda: anrop("/app/start") is not None, text="servern startar")
    print("✓ servern svarar")
    anrop("/app/installera", {"personer": [{"namn": "Förälder", "roll": "foralder", "pin": "1234"},
                                            {"namn": "Barn", "roll": "barn", "pin": "1111"}]})
    vanta(lambda: anrop("/app/start")["panel"], text="Skolan efter första start")
    print("✓ första start")
    tb = anrop("/app/login", {"id": "barn", "pin": "1111"})["token"]
    tf = anrop("/app/login", {"id": "foralder", "pin": "1234"})["token"]
    anrop("/api/skolan/action", {"op": "djur", "art": "🐢", "namn": "Sköldis"}, tb)
    s = anrop("/api/skolan/state", token=tb)
    assert s["meriter"]["djur"]["namn"] == "Sköldis", s["meriter"]
    print("✓ Skolan fungerar, nivå", s["karta"]["niva"])
    with urllib.request.urlopen(BAS + "/skolan_static/panel.js?v=1") as r:
        assert b"customElements" in r.read()
    print("✓ panelen laddas")
    anrop("/app/installningar", {"op": "fjarr", "pa": True}, tf)
    adress = {}
    vanta(lambda: adress.update(a=anrop("/app/installningar", token=tf)["fjarr_adress"]) or adress["a"], 120, "fjärrtunneln")
    print("✓ fjärradress", adress["a"])
    vanta(lambda: anrop("/app/start", bas=adress["a"])["fran_datorn"] is False, 60, "nå appen via tunneln")
    print("✓ appen nås via tunneln och räknas inte som datorn själv")
    print("ALLT OK")
finally:
    proc.terminate()
    subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True)
