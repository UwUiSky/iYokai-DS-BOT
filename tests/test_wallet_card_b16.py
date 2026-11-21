"""
tests/test_wallet_card_b16.py
=============================
Portafoglio come immagine (ECO-017), #125 B16. Funzioni coperte: catalogo #125
"""

import io

from PIL import Image

from core.wallet_card import ALTEZZA, LARGHEZZA, render_wallet_card


def test_il_portafoglio_e_un_png_della_misura_giusta_anche_con_dati_strani():
    png = render_wallet_card("Kitsune", 12_345, 2_000_000, 3, "coin")
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG" and img.size == (LARGHEZZA, ALTEZZA)
    for nome in ("", "x" * 500, "👻👻", "@everyone"):
        assert Image.open(io.BytesIO(render_wallet_card(nome, 0, 0, None, "gemme"))).size == (LARGHEZZA, ALTEZZA)
    assert render_wallet_card("a", -5, -9, 1, "c", b"non e' un'immagine")  # immagine rovinata: non ferma il disegno
    moneta = io.BytesIO()
    Image.new("RGBA", (50, 50), (255, 0, 0, 255)).save(moneta, format="PNG")
    assert Image.open(io.BytesIO(render_wallet_card("a", 1, 1, 1, "c", moneta.getvalue()))).size == (LARGHEZZA, ALTEZZA)
