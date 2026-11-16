"""Startpunkt för Windowsappen (PyInstaller). Importerna nedan ser till att allt Skolan behöver packas med."""
# Används av custom_components/skolan och ha_shim, som laddas från filer och därför inte syns för PyInstaller.
import asyncio, base64, dataclasses, difflib, hashlib, hmac, html, io, ipaddress, json, logging, mimetypes, random, re, secrets, shutil, uuid, zoneinfo  # noqa: E401,F401
import urllib.parse  # noqa: F401
import voluptuous  # noqa: F401
from PIL import Image, ImageOps  # noqa: F401

from skolan_app.__main__ import main

if __name__ == "__main__":
    main()
