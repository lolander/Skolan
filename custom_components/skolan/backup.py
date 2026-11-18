"""Backup, återställning och flytt mellan Läxspelet-system (Windows ↔ Home Assistant).

En backup är en zip-fil med en mapp per barn (data.json, filer/ m.m.) och familjens gemensamma filer.
Med lösenord krypteras hela filen med AES-GCM (nyckel från lösenordet med PBKDF2) i bitar, så att även
stora backuper (många fotade boksidor) går att hantera utan att allt hamnar i minnet.
Allt här är vanliga (blockerande) funktioner; anropa dem i en executor.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import time
import uuid
import zipfile
from pathlib import Path

MAGI = b"LXSP1"
ITER = 300_000
BIT = 4 * 1024 * 1024
GEMENSAMMA = ("kalendrar.json", "tillsammans.json")
OKOMPRIMERAT = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".mp3", ".m4a", ".ogg", ".webm", ".mp4"}


def _nyckel(losen: str, salt: bytes) -> bytes:
    import hashlib

    return hashlib.pbkdf2_hmac("sha256", losen.encode("utf-8"), salt, ITER, 32)


def kryptera(src: Path, dst: Path, losen: str) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    aes = AESGCM(_nyckel(losen, salt))
    with src.open("rb") as fi, dst.open("wb") as fo:
        fo.write(MAGI + salt)
        n = 0
        while True:
            bit = fi.read(BIT)
            nonce = os.urandom(12)
            ct = aes.encrypt(nonce, bit, struct.pack(">Q", n) + (b"S" if not bit else b""))
            fo.write(nonce + struct.pack(">I", len(ct)) + ct)
            n += 1
            if not bit:
                break


def ar_krypterad(fil: Path) -> bool:
    with fil.open("rb") as f:
        return f.read(len(MAGI)) == MAGI


def dekryptera(src: Path, dst: Path, losen: str) -> None:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with src.open("rb") as fi, dst.open("wb") as fo:
        if fi.read(len(MAGI)) != MAGI:
            raise ValueError("Filen är inte en krypterad Läxspelet-backup.")
        aes = AESGCM(_nyckel(losen, fi.read(16)))
        n = 0
        while True:
            huvud = fi.read(16)
            if len(huvud) < 16:
                raise ValueError("Backupfilen är trasig eller inte komplett.")
            nonce, langd = huvud[:12], struct.unpack(">I", huvud[12:])[0]
            ct = fi.read(langd)
            try:
                bit = aes.decrypt(nonce, ct, struct.pack(">Q", n) + (b"S" if langd == 16 else b""))
            except InvalidTag as err:
                raise ValueError("Fel lösenord (eller trasig fil).") from err
            if not bit:
                break
            fo.write(bit)
            n += 1


def skapa(base: Path, barn: list[dict], ut_mapp: Path, losen: str | None, version: str, kalla: str) -> Path:
    """Skapa en backup av de valda barnen (+ gemensamma filer om alla barn är med). Returnerar filen."""
    ut_mapp.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    namn = "familjen" if len(barn) != 1 else barn[0]["namn"].lower()
    zipf = ut_mapp / f".tmp-{uuid.uuid4().hex}.zip"
    manifest = {"typ": "laxspelet-backup", "version": version, "skapad": time.strftime("%Y-%m-%d %H:%M"), "kalla": kalla,
                "barn": [{"id": b["id"], "namn": b["namn"]} for b in barn]}
    with zipfile.ZipFile(zipf, "w", allowZip64=True) as z:
        z.writestr("laxspelet.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for b in barn:
            mapp = base / b["id"]
            if not mapp.is_dir():
                continue
            for f in mapp.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts and not f.name.startswith(".tmp"):
                    rel = f"barn/{b['id']}/{f.relative_to(mapp).as_posix()}"
                    z.write(f, rel, zipfile.ZIP_STORED if f.suffix.lower() in OKOMPRIMERAT else zipfile.ZIP_DEFLATED)
        if len(barn) > 1:
            for g in GEMENSAMMA:
                if (base / g).is_file():
                    z.write(base / g, f"gemensamt/{g}", zipfile.ZIP_DEFLATED)
    if losen:
        ut = ut_mapp / f"laxspelet-{namn}-{stamp}.laxspelet"
        kryptera(zipf, ut, losen)
        zipf.unlink()
    else:
        ut = ut_mapp / f"laxspelet-{namn}-{stamp}.zip"
        zipf.replace(ut)
    return ut


def oppna(fil: Path, losen: str | None, tmp_mapp: Path) -> tuple[dict, Path]:
    """Läs manifestet. Returnerar (manifest, zipfil att återställa från)."""
    zipf = fil
    if ar_krypterad(fil):
        if not losen:
            raise PermissionError("Backupen är krypterad. Skriv lösenordet.")
        zipf = tmp_mapp / f".tmp-{uuid.uuid4().hex}.zip"
        try:
            dekryptera(fil, zipf, losen)
        except ValueError:
            zipf.unlink(missing_ok=True)
            raise
    try:
        with zipfile.ZipFile(zipf) as z:
            m = json.loads(z.read("laxspelet.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as err:
        raise ValueError("Filen är inte en Läxspelet-backup.") from err
    if m.get("typ") != "laxspelet-backup":
        raise ValueError("Filen är inte en Läxspelet-backup.")
    return m, zipf


def _byt_id(v, karta: dict):
    if isinstance(v, str):
        return karta.get(v, v)
    if isinstance(v, list):
        return [_byt_id(x, karta) for x in v]
    if isinstance(v, dict):
        return {k: _byt_id(x, karta) for k, x in v.items()}
    return v


def aterstall(zipf: Path, base: Path, karta: dict[str, str], gemensamt: bool) -> list[str]:
    """Lägg in barnen från backupen. karta: backupens barn-id -> barn-id i det här systemet.
    Det som fanns innan sparas i <base>/.fore-aterstallning/<tid>/ så att inget försvinner."""
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    sakert = base / ".fore-aterstallning" / stamp
    klara = []
    with zipfile.ZipFile(zipf) as z:
        namn = z.namelist()
        for gammal, ny in karta.items():
            if not ny or "/" in ny or "/" in gammal or ny.startswith("."):
                continue
            prefix = f"barn/{gammal}/"
            filer = [n for n in namn if n.startswith(prefix) and not n.endswith("/")]
            if not filer:
                continue
            mal = base / ny
            if mal.exists():
                sakert.mkdir(parents=True, exist_ok=True)
                shutil.move(str(mal), str(sakert / ny))
            for n in filer:
                rel = Path(n[len(prefix):])
                if ".." in rel.parts:
                    continue
                dst = mal / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as fi, dst.open("wb") as fo:
                    shutil.copyfileobj(fi, fo, 1 << 20)
            klara.append(ny)
        if gemensamt:
            for g in GEMENSAMMA:
                if f"gemensamt/{g}" in namn:
                    if (base / g).exists():
                        sakert.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(base / g, sakert / g)
                    innehall = _byt_id(json.loads(z.read(f"gemensamt/{g}")), karta)
                    (base / g).write_text(json.dumps(innehall, ensure_ascii=False, indent=1), "utf-8")
    return klara


def rensa(mapp: Path, behall: int, monster: str = "laxspelet-*") -> None:
    """Behåll bara de senaste backuperna i en mapp."""
    filer = sorted([f for f in mapp.glob(monster) if f.is_file() and f.suffix in (".zip", ".laxspelet")], key=lambda f: f.stat().st_mtime)
    for f in filer[:-max(1, behall)]:
        f.unlink(missing_ok=True)
