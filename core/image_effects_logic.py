"""
core/image_effects_logic.py
===========================
Effetti sull'avatar o su un'immagine (FUN-058..061): arcobaleno, lapide
R.I.P., manifesto "Ricercato", "triggered" (GIF che trema). Pillow è
sincrono: il cog li esegue con core.safe_image.run_image_task. Ogni
funzione restituisce None se l'immagine non è apribile. Funzioni coperte:
SPEC §16.2.
"""

from __future__ import annotations

import io
import colorsys

from PIL import Image, ImageDraw, ImageFont

from core.image_manipulation import _encode_png, _load_image

LATO = 512
MAX_NOME = 40


def _quadrata(img: Image.Image, lato: int = LATO) -> Image.Image:
    return img.resize((lato, lato))


def _testo_centrato(draw: ImageDraw.ImageDraw, xy, testo: str, dim: int, fill) -> None:
    draw.text(xy, testo, font=ImageFont.load_default(size=dim), fill=fill, anchor="mm")


def effetto_arcobaleno(image_bytes: bytes) -> bytes | None:
    img = _load_image(image_bytes)
    if img is None:
        return None
    img = _quadrata(img)
    banda = Image.new("RGB", img.size)
    px = banda.load()
    for x in range(img.width):
        for y in range(img.height):
            r, g, b = colorsys.hsv_to_rgb(((x + y) / (2 * img.width)) % 1.0, 0.9, 1.0)
            px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    return _encode_png(Image.blend(img, banda, 0.4))


def effetto_rip(image_bytes: bytes, nome: str = "") -> bytes | None:
    img = _load_image(image_bytes)
    if img is None:
        return None
    nome = (nome or "").strip()[:MAX_NOME]
    tela = Image.new("RGB", (LATO, LATO + 128), (40, 44, 52))
    d = ImageDraw.Draw(tela)
    d.rounded_rectangle((60, 40, LATO - 60, LATO + 128), radius=190, fill=(150, 150, 155))
    tela.paste(_quadrata(img, 256).convert("L").convert("RGB"), (128, 120))
    _testo_centrato(d, (LATO // 2, 85), "R.I.P.", 56, (30, 30, 35))
    _testo_centrato(d, (LATO // 2, 440), nome, 36, (30, 30, 35))
    return _encode_png(tela)


def effetto_ricercato(image_bytes: bytes, nome: str = "") -> bytes | None:
    img = _load_image(image_bytes)
    if img is None:
        return None
    nome = (nome or "").strip()[:MAX_NOME]
    tela = Image.new("RGB", (LATO, LATO + 160), (222, 196, 150))
    d = ImageDraw.Draw(tela)
    d.rectangle((12, 12, LATO - 12, LATO + 148), outline=(90, 60, 30), width=6)
    _testo_centrato(d, (LATO // 2, 70), "RICERCATO", 80, (70, 40, 20))
    tela.paste(_quadrata(img, 340), ((LATO - 340) // 2, 130))
    _testo_centrato(d, (LATO // 2, 520), nome, 44, (70, 40, 20))
    _testo_centrato(d, (LATO // 2, 590), "per essere troppo simpatico", 28, (70, 40, 20))
    return _encode_png(tela)


def effetto_triggered(image_bytes: bytes) -> bytes | None:
    """GIF di 6 fotogrammi: l'immagine trema sotto una banda rossa."""
    img = _load_image(image_bytes)
    if img is None:
        return None
    base = _quadrata(img, 256)
    spostamenti = ((-6, -4), (5, 3), (-4, 6), (6, -5), (-5, 4), (4, -6))
    fotogrammi = []
    for dx, dy in spostamenti:
        tela = Image.new("RGB", (256, 256), (255, 0, 0))
        tela.paste(base, (dx, dy))
        d = ImageDraw.Draw(tela, "RGBA")
        d.rectangle((0, 210, 256, 256), fill=(220, 0, 0, 200))
        _testo_centrato(d, (128, 233), "TRIGGERED", 30, (255, 255, 255))
        fotogrammi.append(tela)
    buf = io.BytesIO()
    fotogrammi[0].save(buf, format="GIF", save_all=True, append_images=fotogrammi[1:], duration=60, loop=0)
    return buf.getvalue()
