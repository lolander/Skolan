"""Hur appen är installerad: från Microsoft Store (MSIX) eller med Skolan-Setup.exe."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Appar från Microsoft Store ligger under C:\\Program Files\\WindowsApps. Där sköter Store uppdateringarna.
STORE = os.name == "nt" and "\\windowsapps\\" in sys.executable.lower()
MAPP = Path(sys.executable).parent


def sekunder_sedan_start() -> float:
    """Hur länge Windows har varit igång (för att se om appen startades av autostart)."""
    if os.name != "nt":
        return 1e9
    try:
        import ctypes

        return ctypes.windll.kernel32.GetTickCount64() / 1000
    except Exception:  # noqa: BLE001
        return 1e9
