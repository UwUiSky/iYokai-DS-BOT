"""
core/welcome_image.py
=====================
Disegna l'immagine di benvenuto (NF-11, SPEC §22.7): avatar, nome e numero del
membro su un modello pronto o su uno sfondo caricato dall'admin. Funzioni
sincrone con Pillow: chi le chiama le esegue con `run_image_task`
(core/safe_image.py), fuori dal ciclo principale.
Funzioni coperte: SPEC §22 (NF-11)
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageOps

from core.leveling_logic import colore_valido
from core.rank_card_image import carica_font, senza_quadrati, taglia_al_largo
from core.safe_image import safe_open_image

LARGHEZZA = 1024
ALTEZZA = 400
LATO_AVATAR = 200
MAX_SFONDO_BYTE = 3 * 1024 * 1024  # come ProBot: sfondo sotto 3 MB
MAX_TITOLO = 40
MAX_NOME = 32
FORME = ("tondo", "quadrato")
COLORE_TESTO_DI_BASE = "#FFFFFF"

# modello: (colore in alto a sinistra, colore in basso a destra)
MODELLI: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "scuro": ((24, 25, 28), (58, 62, 74)),
    "chiaro": ((236, 238, 242), (190, 200, 220)),
    "viola": ((60, 24, 110), (150, 70, 190)),
    "tramonto": ((200, 70, 60), (250, 170, 70)),
}
MODELLO_DI_BASE = "scuro"


@dataclass(frozen=True)
class DatiBenvenuto:
    nome: str
    numero: int
    titolo: str = "Benvenuto"
    modello: str = MODELLO_DI_BASE
    forma: str = "tondo"
    colore_testo: str = COLORE_TESTO_DI_BASE


def prepara_sfondo(image_bytes: bytes) -> bytes:
    """
    Dallo sfondo caricato all'immagine da salvare: aperto con le regole di safe_image
    (16 megapixel, 2048 px; solleva ImmagineTroppoGrande o UnidentifiedImageError),
    ritagliato alla misura del benvenuto e ricompresso in JPEG.
    """
    img = safe_open_image(image_bytes).convert("RGB")
    img = ImageOps.fit(img, (LARGHEZZA, ALTEZZA), method=Image.LANCZOS)
    for qualita in (88, 75, 60):
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=qualita)
        if buffer.tell() <= MAX_SFONDO_BYTE:
            return buffer.getvalue()
    raise ValueError("Lo sfondo resta troppo pesante anche ricompresso.")


def _sfumatura(modello: str) -> Image.Image:
    inizio, fine = MODELLI.get(modello, MODELLI[MODELLO_DI_BASE])
    # Un gradiente diagonale: si disegna piccolo e si ingrandisce, costa poco.
    piccolo = Image.new("RGB", (64, 25))
    px = piccolo.load()
    for x in range(64):
        for y in range(25):
            t = (x / 63 + y / 24) / 2
            px[x, y] = tuple(int(inizio[i] + (fine[i] - inizio[i]) * t) for i in range(3))
    return piccolo.resize((LARGHEZZA, ALTEZZA), Image.BILINEAR)


def _sfondo(modello: str, sfondo_bytes: bytes | None) -> Image.Image:
    if sfondo_bytes:
        try:
            img = ImageOps.fit(safe_open_image(sfondo_bytes).convert("RGB"), (LARGHEZZA, ALTEZZA), method=Image.LANCZOS)
            # Un velo scuro: il testo si legge su qualunque sfondo.
            velo = Image.new("RGB", img.size, (0, 0, 0))
            return Image.blend(img, velo, 0.35)
        except Exception:  # sfondo rotto: si usa il modello
            pass
    return _sfumatura(modello)


def _avatar(avatar_bytes: bytes | None, forma: str) -> Image.Image:
    quadrato = Image.new("RGB", (LATO_AVATAR, LATO_AVATAR), (90, 94, 104))
    if avatar_bytes:
        try:
            quadrato = ImageOps.fit(
                safe_open_image(avatar_bytes).convert("RGB"), (LATO_AVATAR, LATO_AVATAR), method=Image.LANCZOS
            )
        except Exception:  # avatar rotto: resta il riquadro grigio
            pass
    maschera = Image.new("L", (LATO_AVATAR * 4, LATO_AVATAR * 4), 0)
    d = ImageDraw.Draw(maschera)
    if forma == "quadrato":
        d.rounded_rectangle((0, 0, LATO_AVATAR * 4 - 1, LATO_AVATAR * 4 - 1), radius=40, fill=255)
    else:
        d.ellipse((0, 0, LATO_AVATAR * 4 - 1, LATO_AVATAR * 4 - 1), fill=255)
    maschera = maschera.resize((LATO_AVATAR, LATO_AVATAR), Image.LANCZOS)
    finale = Image.new("RGBA", (LATO_AVATAR, LATO_AVATAR), (0, 0, 0, 0))
    finale.paste(quadrato, (0, 0), maschera)
    return finale


def render_welcome_image(dati: DatiBenvenuto, avatar_bytes: bytes | None, sfondo_bytes: bytes | None) -> bytes:
    """L'immagine di benvenuto come PNG di LARGHEZZA x ALTEZZA. Non solleva per avatar, sfondo o testi strani."""
    colore = colore_valido(dati.colore_testo) or COLORE_TESTO_DI_BASE
    rgb = tuple(int(colore[i : i + 2], 16) for i in (1, 3, 5))
    immagine = _sfondo(dati.modello, sfondo_bytes)
    draw = ImageDraw.Draw(immagine)

    avatar = _avatar(avatar_bytes, dati.forma)
    y_avatar = (ALTEZZA - LATO_AVATAR) // 2
    immagine.paste(avatar, (60, y_avatar), avatar)
    forma_riga = (56, y_avatar - 4, 60 + LATO_AVATAR + 3, y_avatar + LATO_AVATAR + 3)
    if dati.forma == "quadrato":
        draw.rounded_rectangle(forma_riga, radius=44, outline=rgb, width=4)
    else:
        draw.ellipse(forma_riga, outline=rgb, width=4)

    x = 60 + LATO_AVATAR + 50
    larghezza = LARGHEZZA - x - 50
    f_titolo, f_nome, f_numero = carica_font(44), carica_font(56), carica_font(30)
    titolo = taglia_al_largo(draw, senza_quadrati(dati.titolo[:MAX_TITOLO], f_titolo), f_titolo, larghezza)
    nome = taglia_al_largo(draw, senza_quadrati(dati.nome[:MAX_NOME], f_nome), f_nome, larghezza)
    numero = f"Membro n. {dati.numero:,}".replace(",", ".")
    draw.text((x, 100), titolo, font=f_titolo, fill=rgb)
    draw.text((x, 170), nome, font=f_nome, fill=rgb)
    draw.text((x, 260), numero, font=f_numero, fill=rgb)

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()
