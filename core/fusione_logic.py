"""
core/fusione_logic.py
=====================
`/immagini fusione` (#131, D70, B11, FUN-057): due Pokémon, il nome fuso e le loro immagini ufficiali affiancate.
Nessuna fusione disegnata: le fusioni dei fan sono opere senza licenza (D18). Le schede vengono da PokéAPI (cache
comune), le immagini da raw.githubusercontent.com, aperte con `safe_open_image` e composte da Pillow in `run_image_task`.
Funzioni coperte: SPEC §16 (FUN-057)
Dipende da: core/schede_giochi_logic.py, core/safe_http.py, core/safe_image.py
"""

from __future__ import annotations

import io
import re
from urllib.parse import urlparse

from PIL import Image, ImageDraw

LATO = 320
MARGINE = 24
MAX_BYTE_IMMAGINE = 2 * 1024 * 1024
DOMINIO_IMMAGINI = "githubusercontent.com"
VOCALI = "aeiouyàèéìòù"


def _pulito(titolo: str) -> str:
    """Dal titolo di una scheda («#25 Pikachu») al solo nome."""
    return re.sub(r"^#\d+\s*", "", titolo or "").strip()


def nome_fuso(a: str, b: str) -> str:
    """Prima parte di A (fino a una vocale vicino alla metà) + seconda parte di B (da una vocale vicino alla metà)."""
    a, b = _pulito(a), _pulito(b)
    if len(a) < 2 or len(b) < 2:
        return (a + b)[:60]
    # La vocale più vicina alla metà che lascia almeno 2 lettere ad A e 3 a B.
    in_a = [i for i in range(1, len(a) - 1) if a[i].casefold() in VOCALI]
    in_b = [i for i in range(1, len(b) - 2) if b[i].casefold() in VOCALI]
    fine_a = min(in_a, key=lambda i: abs(i - len(a) // 2)) if in_a else len(a) // 2
    inizio_b = min(in_b, key=lambda i: abs(i - len(b) // 2)) if in_b else len(b) // 2
    fuso = a[: fine_a + 1] + b[inizio_b:].lstrip(" -")
    return fuso[:60].strip().capitalize()


def indirizzo_ammesso(url: object) -> bool:
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    return p.scheme == "https" and bool(p.hostname) and (p.hostname == DOMINIO_IMMAGINI or p.hostname.endswith("." + DOMINIO_IMMAGINI))


def componi(png_a: bytes, png_b: bytes) -> bytes:
    """Le due immagini affiancate con un «+» in mezzo, su fondo trasparente (lavoro di Pillow: da `run_image_task`)."""
    from core.safe_image import safe_open_image

    tela = Image.new("RGBA", (LATO * 2 + MARGINE * 3, LATO + MARGINE * 2), (0, 0, 0, 0))
    for i, dati in enumerate((png_a, png_b)):
        img = safe_open_image(dati).convert("RGBA")
        img.thumbnail((LATO, LATO))
        x = MARGINE + i * (LATO + MARGINE) + (LATO - img.width) // 2
        tela.alpha_composite(img, (x, MARGINE + (LATO - img.height) // 2))
    d = ImageDraw.Draw(tela)
    cx, cy, r = tela.width // 2, tela.height // 2, 8
    d.rectangle((cx - r, cy - 2, cx + r, cy + 2), fill=(255, 255, 255, 230))
    d.rectangle((cx - 2, cy - r, cx + 2, cy + r), fill=(255, 255, 255, 230))
    fuori = io.BytesIO()
    tela.save(fuori, format="PNG")
    return fuori.getvalue()


async def fondi(nome_a: str, nome_b: str, lingua: str, cache, scarica=None, componi_in=None) -> tuple[str, bytes] | None:
    """(nome fuso, PNG) oppure None se un Pokémon non si trova o un'immagine non arriva."""
    from core import schede_giochi_logic as sl

    schede = [await sl.cerca("pokemon", n, lingua, cache) for n in (nome_a, nome_b)]
    if not all(schede) or not all(indirizzo_ammesso(s.get("miniatura")) for s in schede):
        return None
    if scarica is None:
        from core.safe_http import safe_richiesta_byte

        async def scarica(url: str):
            return await safe_richiesta_byte(url, max_bytes=MAX_BYTE_IMMAGINE)

    immagini = [await scarica(s["miniatura"]) for s in schede]
    if not all(immagini):
        return None
    if componi_in is None:
        from core.safe_image import run_image_task

        componi_in = lambda x, y: run_image_task(componi, x, y)  # noqa: E731
    try:
        png = await componi_in(immagini[0][0], immagini[1][0])
    except Exception:  # immagine non valida o troppo grande: nessun dettaglio all'utente
        return None
    return nome_fuso(schede[0]["titolo"], schede[1]["titolo"]), png
