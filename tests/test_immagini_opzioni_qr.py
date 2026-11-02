"""
tests/test_immagini_opzioni_qr.py
=================================
Impostazioni del filtro immagini (D16) e giudizio sui QR (D62).
"""

import pytest

from core import immagini_opzioni as op
from core import immagini_qr_logic as qr


class Archivio:
    def __init__(self, **valori):
        self.valori = valori

    async def get_guild_setting(self, guild_id, chiave, default=None):
        return self.valori.get(chiave, default)


@pytest.mark.asyncio
async def test_valori_di_base():
    o = await op.leggi(1, Archivio())
    assert o == op.OpzioniImmagini(attivo=False, azione="cancella", timeout_minuti=10, canale_log_id=None)


@pytest.mark.asyncio
async def test_valori_sporchi_tornano_ai_valori_di_base():
    o = await op.leggi(
        1,
        Archivio(immagini_filtro_attivo="si", immagini_azione="ban", immagini_timeout_minuti=10**9, immagini_canale_log_id=True),
    )
    assert o == op.OpzioniImmagini()


@pytest.mark.asyncio
async def test_valori_validi_si_leggono():
    o = await op.leggi(
        1, Archivio(immagini_filtro_attivo=True, immagini_azione="timeout", immagini_timeout_minuti=30, immagini_canale_log_id=555)
    )
    assert (o.attivo, o.azione, o.timeout_minuti, o.canale_log_id) == (True, "timeout", 30, 555)


@pytest.mark.asyncio
async def test_imposta_rifiuta_i_valori_fuori_limite(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    for kw in ({"azione": "ban"}, {"timeout_minuti": 0}, {"timeout_minuti": 40321}, {"canale_log_id": -5}):
        with pytest.raises(ValueError):
            await op.imposta(1, 2, **kw)
    await op.imposta(777000801, 2, attivo=True, azione="avvisa", timeout_minuti=5, canale_log_id=99)
    database_module.db._settings_cache.clear()
    assert await op.leggi(777000801) == op.OpzioniImmagini(True, "avvisa", 5, 99)
    await op.imposta(777000801, 2, togli_canale=True)
    database_module.db._settings_cache.clear()
    assert (await op.leggi(777000801)).canale_log_id is None


@pytest.mark.parametrize(
    "testo,atteso",
    [
        ("https://discord.com/ra/AbC123-xyz", qr.QR_LOGIN),
        ("https://discordapp.com/ra/abc", qr.QR_LOGIN),
        ("https://discord-nitro.gift/claim", qr.QR_PHISHING),
        ("https://bit.ly/3abcdE", qr.QR_ACCORCIATORE),
        ("https://sito-qualunque.example/free-nitro/ritira", qr.QR_TRUFFA),
        ("https://sito-qualunque.example/nitro-gratis", qr.QR_TRUFFA),
        ("https://sito-qualunque.example/seed phrase", qr.QR_TRUFFA),
        ("https://discord.com/channels/1/2", None),
        ("https://www.youtube.com/watch?v=abc", None),
        ("WIFI:T:WPA;S:casa;P:segreta;;", None),
        ("ciao", None),
        ("", None),
    ],
)
def test_giudizio_sui_qr(testo, atteso):
    assert qr.giudica_qr(testo) == atteso


def test_frasi_di_piu_lingue_caricate():
    frasi = qr.frasi_truffa()
    assert "free nitro" in frasi and "nitro gratis" in frasi


def test_lista_di_qr_ferma_al_primo_motivo():
    assert qr.giudica_qr_lista(["ciao", "https://bit.ly/x", "https://discord.com/ra/a"]) == qr.QR_ACCORCIATORE
    assert qr.giudica_qr_lista([]) is None
