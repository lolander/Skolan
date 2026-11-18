"""Bygger Microsoft Store-paketet (MSIX) av dist/Skolan.  python windows/msix_bygg.py <dist/Skolan> <version> <ut-mapp>

Identiteten kommer från Partner Center och läggs som GitHub-variabler: STORE_NAMN, STORE_PUBLISHER, STORE_PUBLISHER_NAMN.
Utan dem byggs ett provpaket (kan inte skickas till Store, men visar att bygget fungerar). Store signerar paketet själv.
"""
import glob
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image

HAR = Path(__file__).parent


def ikon(storlek: tuple[int, int], ut: Path) -> None:
    ico = Image.open(HAR / "skolan.ico")
    basta = max(ico.info.get("sizes") or [ico.size])
    ico.size = basta
    bild = ico.convert("RGBA")
    sida = int(min(storlek) * 0.84)
    bild = bild.resize((sida, sida), Image.LANCZOS)
    duk = Image.new("RGBA", storlek, (0, 0, 0, 0))
    duk.paste(bild, ((storlek[0] - sida) // 2, (storlek[1] - sida) // 2), bild)
    duk.save(ut)


def main() -> None:
    dist, version, ut = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    delar = (version.split(".") + ["0", "0", "0"])[:3]
    msix_ver = ".".join(delar) + ".0"  # Store kräver att sista siffran är 0
    stage = ut / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(dist, stage)
    # Tunnelprogrammet packas med (Store-appar får inte ladda ner program)
    urllib.request.urlretrieve("https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe", stage / "cloudflared.exe")
    (stage / "Assets").mkdir(exist_ok=True)
    for namn, st in {"Square44x44Logo": (44, 44), "Square150x150Logo": (150, 150), "Wide310x150Logo": (310, 150), "StoreLogo": (50, 50)}.items():
        ikon(st, stage / "Assets" / f"{namn}.png")
    manifest = (HAR / "msix" / "AppxManifest.xml").read_text("utf-8")
    for k, v in {"{NAMN}": os.environ.get("STORE_NAMN") or "Laxspelet.Prov", "{PUBLISHER}": os.environ.get("STORE_PUBLISHER") or "CN=Laxspelet Prov",
                 "{PUBLISHER_NAMN}": os.environ.get("STORE_PUBLISHER_NAMN") or "Läxspelet", "{VERSION}": msix_ver}.items():
        manifest = manifest.replace(k, v.replace("&", "&amp;"))
    (stage / "AppxManifest.xml").write_text(manifest, "utf-8")
    makeappx = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe"))[-1]
    paket = ut / f"Laxspelet-{msix_ver}.msix"
    subprocess.run([makeappx, "pack", "/o", "/d", str(stage), "/p", str(paket)], check=True)
    print("Byggt:", paket, "(prov)" if not os.environ.get("STORE_NAMN") else "")


if __name__ == "__main__":
    main()
