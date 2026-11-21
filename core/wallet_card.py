"""
core/wallet_card.py
===================
L'immagine del portafoglio (ECO-017): nome, contanti, banca, posizione e moneta del server su una scheda scura.
Disegno con Pillow: va chiamato da `run_image_task` (fuori dal ciclo principale); niente immagini di altri utenti.
Funzioni coperte: ECO-017
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from core.rank_card_image import _compatto, carica_font, senza_quadrati, taglia_al_largo

LARGHEZZA, ALTEZZA = 720, 260
FONDO = (7, 7, 11)  # void
PANNELLO = (42, 41, 40)  # ash
TESTO = (200, 196, 188)  # pale-ink
SECONDARIO = (138, 134, 128)  # mist
ACCENTO = (194, 74, 58)  # cinnabar


def render_wallet_card(nome: str, contanti: int, banca: int, posizione: int | None, moneta: str, moneta_png: bytes | None = None) -> bytes:
    """PNG 720x260 del portafoglio. `moneta_png` è l'immagine già preparata della moneta del server (facoltativa)."""
    tela = Image.new("RGB", (LARGHEZZA, ALTEZZA), FONDO)
    d = ImageDraw.Draw(tela)
    d.rounded_rectangle((16, 16, LARGHEZZA - 16, ALTEZZA - 16), radius=18, fill=PANNELLO)
    d.rectangle((16, 16, 22, ALTEZZA - 16), fill=ACCENTO)
    f_grande, f_medio, f_piccolo = carica_font(44), carica_font(28), carica_font(20)
    pulito = senza_quadrati(nome, f_medio)
    moneta_pulita = senza_quadrati(moneta, f_piccolo)
    d.text((48, 34), taglia_al_largo(d, pulito, f_medio, 470), font=f_medio, fill=TESTO)
    d.text((48, 86), f"{_compatto(max(0, contanti))}", font=f_grande, fill=TESTO)
    d.text((48, 140), f"{moneta_pulita} in contanti", font=f_piccolo, fill=SECONDARIO)
    d.text((48, 172), f"Banca: {_compatto(max(0, banca))}", font=f_medio, fill=TESTO)
    if posizione:
        d.text((48, 214), f"#{posizione} in classifica", font=f_piccolo, fill=SECONDARIO)
    if moneta_png:
        try:
            m = Image.open(io.BytesIO(moneta_png)).convert("RGBA").resize((120, 120))
            tela.paste(m, (LARGHEZZA - 160, 60), m)
        except Exception:  # un'immagine rovinata non ferma il portafoglio
            pass
    else:
        d.ellipse((LARGHEZZA - 160, 60, LARGHEZZA - 40, 180), outline=ACCENTO, width=6)
    uscita = io.BytesIO()
    tela.save(uscita, format="PNG")
    return uscita.getvalue()
