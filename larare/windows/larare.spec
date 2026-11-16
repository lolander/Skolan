# PyInstaller: bygger dist/SkolanLarare/SkolanLarare.exe. Körs från mappen larare:  pyinstaller --noconfirm windows/larare.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROT = Path(SPECPATH).parent  # larare/

a = Analysis(
    [str(ROT / "start.py")],
    pathex=[str(ROT)],
    datas=[(str(f), "skolan_larare/webb") for f in (ROT / "skolan_larare" / "webb").iterdir() if f.is_file()],
    hiddenimports=collect_submodules("aiohttp") + collect_submodules("pystray") + ["qrcode.image.svg"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SkolanLarare", console=False, icon=str(ROT / "windows" / "larare.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="SkolanLarare")
