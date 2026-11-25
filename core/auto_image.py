"""
core/auto_image.py
==================
Lavoro con Pillow sulle foto delle auto (FUN-017): ridurre la copia ricodificata che si conserva e affiancare le foto
di due auto in gara. Si chiama sempre con `run_image_task`, mai nel ciclo principale. Le foto in ingresso sono solo
copie PNG già rifatte dalla sandbox (D74).
Funzioni coperte: FUN-017
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.auto_logic import LATO_FOTO
from core.safe_image import apri_in_sandbox

LARGHEZZA_CELLA = 480
ALTEZZA_CELLA = 360
MARGINE = 12
SFONDO = (7, 7, 11)
VUOTO = (42, 41, 40)
VINCITORE = (194, 74, 58)


def riduci_foto(png: bytes, lato: int = LATO_FOTO) -> bytes:
    """Copia PNG con il lato più lungo al massimo `lato`, senza metadati. Solleva se l'immagine non si legge."""
    img = apri_in_sandbox(png, formati=("PNG",))
    img.thumbnail((lato, lato))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    fuori = io.BytesIO()
    img.save(fuori, format="PNG", optimize=True)
    return fuori.getvalue()


def affianca(foto_a: bytes | None, foto_b: bytes | None, vincitore: int = 0) -> bytes:
    """Le due foto (o un riquadro vuoto) una accanto all'altra; il vincitore ha il bordo cinabro."""
    larghezza = MARGINE * 3 + LARGHEZZA_CELLA * 2
    tela = Image.new("RGB", (larghezza, ALTEZZA_CELLA + MARGINE * 2), SFONDO)
    pennello = ImageDraw.Draw(tela)
    for n, dati in enumerate((foto_a, foto_b), 1):
        x0 = MARGINE + (n - 1) * (LARGHEZZA_CELLA + MARGINE)
        cella = (x0, MARGINE, x0 + LARGHEZZA_CELLA, MARGINE + ALTEZZA_CELLA)
        pennello.rectangle(cella, fill=VUOTO)
        if dati:
            img = apri_in_sandbox(dati, formati=("PNG",))
            img.thumbnail((LARGHEZZA_CELLA, ALTEZZA_CELLA))
            if img.mode == "RGBA":
                tela.paste(img, (x0 + (LARGHEZZA_CELLA - img.width) // 2, MARGINE + (ALTEZZA_CELLA - img.height) // 2), img)
            else:
                tela.paste(img.convert("RGB"), (x0 + (LARGHEZZA_CELLA - img.width) // 2, MARGINE + (ALTEZZA_CELLA - img.height) // 2))
        if vincitore == n:
            pennello.rectangle(cella, outline=VINCITORE, width=5)
    fuori = io.BytesIO()
    tela.save(fuori, format="PNG")
    return fuori.getvalue()
