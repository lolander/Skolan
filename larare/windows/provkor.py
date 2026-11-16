"""Provkör den byggda lärarappen i GitHub Actions: start, sidor, veckobrev, grupper, historik.

python provkor.py <sökväg till SkolanLarare.exe>
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
EXE = sys.argv[1]
PORT = 8771
BAS = f"http://127.0.0.1:{PORT}"


def anrop(vag, body=None):
    req = urllib.request.Request(BAS + vag, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


data = tempfile.mkdtemp()
proc = subprocess.Popen([EXE, "--utan-ikon", "--tyst", "--port", str(PORT)], env={**os.environ, "SKOLAN_LARARE_DATA": data})
try:
    for _ in range(60):
        try:
            lage = json.loads(anrop("/api/lage"))
            break
        except Exception:  # noqa: BLE001
            time.sleep(1)
    else:
        raise SystemExit("FEL: servern startade inte")
    print("✓ servern svarar, version", lage["version"])
    assert "Läxspelet L".encode() in anrop("/") and b"<svg" in anrop("/api/qr.svg") and b"Ansluter" in anrop("/elev")
    print("✓ sidorna och QR-koden")
    anrop("/api/andra", {"op": "installningar", "klass": "4B", "veckobrev": True, "grupper": True, "klasslag": True})
    l = json.loads(anrop("/api/andra", {"op": "veckobrev", "titel": "Test", "ai": {"ord": ["hund"]}}))
    assert l["veckobrev"] and l["boss"], l
    l = json.loads(anrop("/api/andra", {"op": "anteckning", "text": "Provkörning"}))
    assert any("Provkörning" in h["text"] for h in l["historik"])
    assert b"Provk" in anrop("/api/historik.csv")
    print("✓ veckobrev, klassboss och historik")
    try:
        anrop("/api/elev/koppla", {"lank": "https://192.168.1.2/api/skolan/klass/" + "x" * 30})
        raise SystemExit("FEL: lokal klasslänk godtogs")
    except urllib.error.HTTPError as err:
        assert err.code == 400
    print("✓ klasslänkar till lokala adresser stoppas")
    print("ALLT OK")
finally:
    proc.terminate()
