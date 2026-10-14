"""
core/rank_card_image.py
=======================
Disegna la rank card: avatar, nome, livello, barra dell'XP, posizione in
classifica e coin, con colore e tema a scelta di chi la guarda. Lavoro di
Pillow: va chiamato fuori dal ciclo principale (core.safe_image.run_image_task);
l'avatar si apre con safe_open_image (limite di pixel).
Funzioni coperte: SPEC §22.8 (NF-12)
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from core.leveling_logic import colore_valido
from core.safe_image import safe_open_image

LARGHEZZA = 800
ALTEZZA = 240
COLORE_DI_BASE = "#5865F2"
LATO_AVATAR = 140
# Testo oltre questa lunghezza non serve a nessuno: il disegno lo taglia
# comunque in base alla larghezza, ma non lavora su stringhe enormi.
MAX_CARATTERI_NOME = 64

_FONT_CANDIDATI = (
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@dataclass(frozen=True)
class Tema:
    sfondo: tuple[int, int, int]
    pannello: tuple[int, int, int]
    testo: tuple[int, int, int]
    testo_secondario: tuple[int, int, int]
    barra_vuota: tuple[int, int, int]


TEMI = {
    "scuro": Tema((24, 25, 28), (35, 37, 42), (245, 245, 245), (160, 164, 172), (64, 67, 74)),
    "chiaro": Tema((236, 238, 242), (255, 255, 255), (30, 32, 36), (100, 104, 112), (205, 208, 214)),
    "notte": Tema((8, 12, 32), (16, 24, 56), (235, 240, 255), (140, 155, 205), (40, 52, 96)),
}
TEMA_DI_BASE = "scuro"


@dataclass(frozen=True)
class DatiRankCard:
    nome: str
    livello: int
    xp_nel_livello: int
    xp_richiesti: int  # 0 = nessun livello successivo: la barra è piena
    xp_totale: int
    posizione: int | None
    coin: int
    colore: str = COLORE_DI_BASE
    tema: str = TEMA_DI_BASE


def _rgb(colore: str) -> tuple[int, int, int]:
    esadecimale = colore_valido(colore) or COLORE_DI_BASE
    return tuple(int(esadecimale[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def carica_font(dimensione: int) -> ImageFont.ImageFont:
    for candidato in _FONT_CANDIDATI:
        try:
            return ImageFont.truetype(candidato, dimensione)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=dimensione)
    except TypeError:  # Pillow prima della 10.1: font fisso
        return ImageFont.load_default()


def senza_quadrati(testo: str, font) -> str:
    """
    Toglie dal testo i caratteri che il font non sa disegnare (emoji, scritture
    rare): al loro posto Pillow disegnerebbe quadrati vuoti. Se non resta
    niente, "Utente".
    """
    def firma(carattere: str) -> bytes:
        tela = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(tela).text((10, 10), carattere, font=font, fill=255)
        return tela.tobytes()

    try:
        vuoto = firma("\uffff")  # il "quadrato" che il font disegna per ciò che non conosce
        giusti = [c for c in testo if c.isspace() or c == "…" or firma(c) != vuoto]
    except Exception:  # font o Pillow che non disegnano così: si lascia il testo com'è
        return testo
    pulito = " ".join("".join(giusti).split())
    return pulito or "Utente"


def _compatto(numero: int) -> str:
    """1500 -> 1.5k, 2_300_000 -> 2.3M: i numeri enormi restano in poco spazio."""
    for soglia, suffisso in ((10**9, "G"), (10**6, "M"), (10**3, "k")):
        if numero >= soglia:
            return f"{numero / soglia:.1f}".rstrip("0").rstrip(".") + suffisso
    return str(numero)


def taglia_al_largo(draw: ImageDraw.ImageDraw, testo: str, font, larghezza_max: int) -> str:
    """Il testo accorciato con «…» finché sta nella larghezza."""
    if draw.textlength(testo, font=font) <= larghezza_max:
        return testo
    while testo and draw.textlength(testo + "…", font=font) > larghezza_max:
        testo = testo[:-1]
    return testo + "…"


def _avatar_tondo(avatar_bytes: bytes | None, colore_vuoto) -> Image.Image:
    """L'avatar ritagliato a cerchio; se manca o non è apribile, un cerchio pieno."""
    quadrato = Image.new("RGB", (LATO_AVATAR, LATO_AVATAR), colore_vuoto)
    if avatar_bytes:
        try:
            originale = safe_open_image(avatar_bytes)
            quadrato = originale.convert("RGB").resize((LATO_AVATAR, LATO_AVATAR))
        except Exception:  # file rotto, formato strano o troppo grande: si usa il cerchio pieno
            pass
    maschera = Image.new("L", (LATO_AVATAR * 4, LATO_AVATAR * 4), 0)
    ImageDraw.Draw(maschera).ellipse((0, 0, LATO_AVATAR * 4 - 1, LATO_AVATAR * 4 - 1), fill=255)
    maschera = maschera.resize((LATO_AVATAR, LATO_AVATAR), Image.LANCZOS)
    tondo = Image.new("RGBA", (LATO_AVATAR, LATO_AVATAR), (0, 0, 0, 0))
    tondo.paste(quadrato, (0, 0), maschera)
    return tondo


def render_rank_card(dati: DatiRankCard, avatar_bytes: bytes | None) -> bytes:
    """La rank card come PNG di LARGHEZZA x ALTEZZA. Non solleva per avatar o numeri strani."""
    tema = TEMI.get(dati.tema, TEMI[TEMA_DI_BASE])
    accento = _rgb(dati.colore)

    immagine = Image.new("RGB", (LARGHEZZA, ALTEZZA), tema.sfondo)
    draw = ImageDraw.Draw(immagine)
    draw.rounded_rectangle((16, 16, LARGHEZZA - 17, ALTEZZA - 17), radius=24, fill=tema.pannello)

    avatar = _avatar_tondo(avatar_bytes, tema.barra_vuota)
    immagine.paste(avatar, (40, (ALTEZZA - LATO_AVATAR) // 2), avatar)
    draw.ellipse(
        (36, (ALTEZZA - LATO_AVATAR) // 2 - 4, 40 + LATO_AVATAR + 3, (ALTEZZA + LATO_AVATAR) // 2 + 3),
        outline=accento,
        width=4,
    )

    x_testo = 40 + LATO_AVATAR + 40
    x_fine = LARGHEZZA - 44

    # Livello e posizione a destra, in alto.
    f_grande, f_medio, f_piccolo = carica_font(40), carica_font(28), carica_font(22)
    livello = f"LIV {_compatto(dati.livello)}"
    draw.text((x_fine, 44), livello, font=f_grande, fill=accento, anchor="ra")
    larghezza_livello = draw.textlength(livello, font=f_grande)
    if dati.posizione is not None:
        posizione = f"#{_compatto(dati.posizione)}"
        draw.text(
            (x_fine - larghezza_livello - 24, 52), posizione, font=f_medio,
            fill=tema.testo_secondario, anchor="ra",
        )
        larghezza_livello += draw.textlength(posizione, font=f_medio) + 24

    # Nome a sinistra, nello spazio che resta.
    nome = taglia_al_largo(draw, senza_quadrati(dati.nome[:MAX_CARATTERI_NOME], f_grande), f_grande, int(x_fine - x_testo - larghezza_livello - 24))
    draw.text((x_testo, 44), nome, font=f_grande, fill=tema.testo)

    # Barra dell'XP.
    x0, y0, y1 = x_testo, 168, 198
    frazione = 1.0 if dati.xp_richiesti <= 0 else min(1.0, max(0.0, dati.xp_nel_livello / dati.xp_richiesti))
    draw.rounded_rectangle((x0, y0, x_fine, y1), radius=15, fill=tema.barra_vuota)
    larghezza_barra = int((x_fine - x0) * frazione)
    if larghezza_barra >= 30:
        draw.rounded_rectangle((x0, y0, x0 + larghezza_barra, y1), radius=15, fill=accento)
    elif larghezza_barra > 0:
        draw.ellipse((x0, y0, x0 + 30, y1), fill=accento)

    if dati.xp_richiesti > 0:
        riga = f"{_compatto(dati.xp_nel_livello)} / {_compatto(dati.xp_richiesti)} XP"
    else:
        riga = "Livello massimo"
    draw.text((x0, 128), riga, font=f_piccolo, fill=tema.testo_secondario)
    draw.text(
        (x_fine, 128), f"{_compatto(dati.xp_totale)} XP totali · {_compatto(dati.coin)} coin",
        font=f_piccolo, fill=tema.testo_secondario, anchor="ra",
    )

    buffer = io.BytesIO()
    immagine.save(buffer, format="PNG")
    return buffer.getvalue()
