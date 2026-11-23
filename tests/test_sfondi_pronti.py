"""
tests/test_sfondi_pronti.py
===========================
Sfondi pronti della rank card (LIV-053): generati dal codice, nessun file esterno.
Funzioni coperte: LIV-053
"""

import io

import pytest
from PIL import Image

from core.rank_card_image import LATO_SFONDO, MAX_BYTE_SFONDO
from core.sfondi_pronti import SFONDI_PRONTI, disegna_sfondo_pronto


# LIV-053
def test_ci_sono_da_cinque_a_dieci_sfondi_con_nome_e_id_validi():
    assert 5 <= len(SFONDI_PRONTI) <= 10
    for id_sfondo, nome in SFONDI_PRONTI.items():
        assert id_sfondo.isidentifier() and 0 < len(nome) <= 25  # il nome è una scelta di Discord (max 100), corto per la lista


# LIV-053
@pytest.mark.parametrize("id_sfondo", sorted(SFONDI_PRONTI))
def test_ogni_sfondo_e_un_jpeg_della_misura_giusta_e_leggero(id_sfondo):
    dati = disegna_sfondo_pronto(id_sfondo)
    assert len(dati) <= MAX_BYTE_SFONDO
    immagine = Image.open(io.BytesIO(dati))
    assert immagine.format == "JPEG" and immagine.size == LATO_SFONDO


# LIV-053
def test_uno_sfondo_sconosciuto_e_rifiutato():
    with pytest.raises(KeyError):
        disegna_sfondo_pronto("inventato")
