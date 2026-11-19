"""Windows: brandväggen (en gång) och den gamla installationen under Program Files.
Samma kod som i Läxspelet Lärare (larare/skolan_larare/windows.py), med appens egna namn.

Appen installeras per användare (ingen administratör behövs för uppdateringar). Det enda som kräver
administratör är brandväggsregeln som låter familjens mobiler ansluta hemma. Den skapas en gång, första gången
appen startar, och pekar på programmets sökväg (som är samma efter varje uppdatering). Samtidigt tas en
gammal installation under Program Files bort (versioner före 1.95.0).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

REGEL = "Laxspelet"
GAMMAL_REGEL = "Skolan"
GAMMAL_APPID = "{6E3F2B1A-5C4D-4E8F-9A7B-1C2D3E4F5A6B}_is1"
_INGET_FONSTER = 0x08000000  # CREATE_NO_WINDOW


def ar_windows() -> bool:
    return os.name == "nt"


def exe() -> str:
    from .paket import STORE

    return sys.executable if getattr(sys, "frozen", False) and not STORE else ""


def _netsh(*args: str) -> str:
    try:
        return subprocess.run(["netsh", "advfirewall", "firewall", *args], capture_output=True, text=True, timeout=20,
                              creationflags=_INGET_FONSTER).stdout
    except Exception as err:  # noqa: BLE001
        _LOGGER.info("netsh: %s", err)
        return ""


def brandvagg_ok() -> bool:
    """Finns regeln för just den här programfilen? (Läsa regler kräver inte administratör.)"""
    if not ar_windows() or not exe():
        return True
    ut = _netsh("show", "rule", f"name={REGEL}", "verbose")
    return exe().lower() in ut.lower()


def gammal_mapp() -> Path | None:
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        p = os.environ.get(var)
        if p and (Path(p) / "Skolan" / "Skolan.exe").is_file():
            return Path(p) / "Skolan"
    return None


def status() -> dict:
    if not ar_windows():
        return {"windows": False, "brandvagg": True, "gammal": False}
    return {"windows": True, "brandvagg": brandvagg_ok(), "gammal": gammal_mapp() is not None}


def forbered() -> bool:
    """Öppna brandväggen och städa bort den gamla installationen. Windows frågar om lov en gång.

    Returnerar True om frågan visades (inget behövdes annars)."""
    if not ar_windows() or not exe():
        return False
    gammal = gammal_mapp()
    if brandvagg_ok() and not gammal:
        return False
    rader = ["@echo off", "chcp 65001 >nul",
             f'netsh advfirewall firewall delete rule name="{GAMMAL_REGEL}" >nul 2>&1',
             f'netsh advfirewall firewall delete rule name="{REGEL}" >nul 2>&1',
             f'netsh advfirewall firewall add rule name="{REGEL}" dir=in action=allow program="{exe()}" enable=yes profile=private']
    if gammal:  # gamla versionen (Program Files): ta bort filer, genvägar och raden i "Appar"
        rader += [f'rmdir /s /q "{gammal}"',
                  f'reg delete "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GAMMAL_APPID}" /f >nul 2>&1',
                  f'reg delete "HKLM\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GAMMAL_APPID}" /f >nul 2>&1',
                  'del /q "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\Läxspelet\\*.lnk" >nul 2>&1',
                  'rmdir /q "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\Läxspelet" >nul 2>&1',
                  'del /q "%Public%\\Desktop\\Läxspelet.lnk" >nul 2>&1']
    skript = Path(tempfile.gettempdir()) / "laxspelet_forbered.cmd"
    skript.write_text("\r\n".join(rader) + "\r\n", encoding="utf-8")
    try:
        import ctypes
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c "{skript}"', None, 0)  # type: ignore[attr-defined]
        _LOGGER.info("Brandväggen/gamla installationen: ShellExecute %s", r)
        return r > 32
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Kunde inte be Windows om lov: %s", err)
        return False
