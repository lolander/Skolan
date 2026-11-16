# PyInstaller: bygger dist/Skolan/Skolan.exe. Körs från mappen fristaende:  pyinstaller --noconfirm windows/skolan.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROT = Path(SPECPATH).parent  # fristaende/
INTEGRATION = ROT.parent / "custom_components"


def mapp(src, dst):
    """Alla filer i en mapp (utom __pycache__) som datafiler."""
    ut = []
    for f in Path(src).rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts:
            ut.append((str(f), str(Path(dst) / f.relative_to(src).parent)))
    return ut


a = Analysis(
    [str(ROT / "start.py")],
    pathex=[str(ROT)],
    datas=mapp(ROT / "ha_shim", "ha_shim") + mapp(INTEGRATION / "skolan", "custom_components/skolan")
    + mapp(ROT / "skolan_app" / "webb", "skolan_app/webb"),
    hiddenimports=collect_submodules("voluptuous") + collect_submodules("aiohttp") + collect_submodules("pystray")
    + ["pywebpush", "py_vapid", "http_ece", "qrcode.image.svg", "tzdata", "PIL.ImageOps"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Skolan", console=False,
          icon=str(ROT / "windows" / "skolan.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="Skolan")
