"""
core/immagini_worker.py
=======================
Processo figlio della sandbox (D62): analizza UN'immagine della quarantena e scrive l'esito su
stdout (lunghezza + JSON, poi lunghezza + PNG ricodificato). Parte con `python3 -I -B`, con i
limiti di memoria, tempo e file messi da `core/immagini_sandbox.py`. Non parla con Discord né col
database. Qualunque errore del decoder finisce in un esito «errore»: chi legge lo tratta da sospetto.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import io
import json
import os
import re
import struct
import sys
from pathlib import Path

from PIL import Image

RADICE = str(Path(__file__).resolve().parent.parent)
if RADICE not in sys.path:  # con -I la cartella non c'e' di suo
    sys.path.insert(0, RADICE)

MAX_FOTOGRAMMI = 200
MAX_ICC = 1024 * 1024
MAX_EXIF = 256 * 1024
MAX_TESTO = 1024 * 1024
LATO_ANALISI = 1024
MAX_QR = 5
MAX_TESTO_QR = 2000
NOME = re.compile(r"^[0-9a-f]{32}$")


def _scrivi(esito: dict, png: bytes = b"") -> None:
    corpo = json.dumps(esito, separators=(",", ":")).encode()
    out = sys.stdout.buffer
    out.write(struct.pack(">I", len(corpo)) + corpo + struct.pack(">I", len(png)) + png)
    out.flush()


def _fotogrammi(img) -> int:
    """Quanti fotogrammi ha, contati fino a MAX_FOTOGRAMMI + 1."""
    n = 1
    try:
        while n <= MAX_FOTOGRAMMI:
            img.seek(n)
            n += 1
    except EOFError:
        pass
    finally:
        img.seek(0)
    return n


def _metadati(img) -> list[str]:
    motivi = []
    info = img.info
    if len(info.get("icc_profile") or b"") > MAX_ICC:
        motivi.append("icc_enorme")
    if len(info.get("exif") or b"") > MAX_EXIF:
        motivi.append("exif_enorme")
    testo = sum(len(v) for v in info.values() if isinstance(v, (str, bytes)) and v is not info.get("icc_profile") and v is not info.get("exif"))
    if testo > MAX_TESTO:
        motivi.append("testo_enorme")
    return motivi


def _qr(img) -> list[str]:
    """I testi dei QR trovati (solo formato QR, al massimo 5, ognuno al massimo 2000 caratteri)."""
    try:
        import zxingcpp
    except ImportError:
        return []
    trovati = zxingcpp.read_barcodes(img.convert("RGB"), formats=zxingcpp.BarcodeFormat.QRCode)
    return [t.text[:MAX_TESTO_QR] for t in trovati[:MAX_QR] if t.text]


def _png_pulito(img) -> bytes:
    """PNG nuovo ricostruito dai soli pixel: spariscono metadati, profili e dati nascosti."""
    modo = "RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB"
    pixel = img.convert(modo)
    pulita = Image.frombytes(modo, pixel.size, pixel.tobytes())
    buf = io.BytesIO()
    pulita.save(buf, "PNG", compress_level=3)
    return buf.getvalue()


def _contenuto(img) -> tuple[dict, bytes]:
    from core.immagini_impronte import dhash

    img.seek(0)
    img = img.copy() if getattr(img, "is_animated", False) else img
    return {"dhash": f"{dhash(img):016x}", "qr": _qr(img)}, _png_pulito(img)


def analizza(percorso: Path) -> tuple[dict, bytes]:
    from core.safe_image import FORMATI_AMMESSI, ImmagineTroppoGrande, safe_open_image

    try:
        dati = percorso.read_bytes()
        anteprima = Image.open(io.BytesIO(dati), formats=FORMATI_AMMESSI)
        formato = anteprima.format
        larghezza, altezza = anteprima.size
        motivi = _metadati(anteprima)
        fotogrammi = _fotogrammi(anteprima)
        anteprima.close()
        if fotogrammi > MAX_FOTOGRAMMI:
            motivi.append("troppi_fotogrammi")
        img = safe_open_image(dati, max_side=LATO_ANALISI)
    except (ImmagineTroppoGrande, Image.DecompressionBombError):
        return {"esito": "errore", "motivo": "troppo_grande"}, b""
    except Exception as errore:  # decoder: qualunque cosa e' sospetta
        return {"esito": "errore", "motivo": "decodifica", "dettaglio": type(errore).__name__}, b""
    try:
        extra, png = _contenuto(img)
    except Exception as errore:
        return {"esito": "errore", "motivo": "elaborazione", "dettaglio": type(errore).__name__}, b""
    info = {
        **extra,
        "esito": "ok",
        "formato": formato,
        "larghezza": larghezza,
        "altezza": altezza,
        "fotogrammi": fotogrammi,
        "motivi": motivi,
    }
    return info, png


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not NOME.fullmatch(argv[1]):
        _scrivi({"esito": "errore", "motivo": "nome"})
        return 2
    base = Path(os.environ.get("IYOKAI_QUARANTENA_DIR") or "/var/lib/iyokai/quarantena")
    info, png = analizza(base / argv[1])
    _scrivi(info, png)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
