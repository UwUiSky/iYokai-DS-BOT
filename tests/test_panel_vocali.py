"""
tests/test_panel_vocali.py
==========================
Pagina dei vocali temporanei nel pannello web (VOC-020): stesse regole di `/admin-vocali opzioni`, stesso repository.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import web_panel_vocali
from core.config_schema import ImpostazioneNonValida
from core.repositories.voice_temp_repo import voice_temp_repo
from tests.support.discord_fakes import fake_guild
from tests.test_panel_accesso import ADMIN, GUILD, LETTORE, ambiente, _come, _imposta  # noqa: F401
from tests.test_web_panel_server import _csrf

CANALE_TESTO = 9100
CAMPI = {
    "nome": "Stanza {numero}", "bloccati": "1", "registro": str(CANALE_TESTO), "cap": "12", "clona": "0",
    "titolo": "Il mio <b>pannello</b>", "testo": "Ciao", "colore": "5865F2",
}


@pytest.fixture
async def vocali(ambiente):
    canale = SimpleNamespace(id=CANALE_TESTO, name="registro", position=1, send=MagicMock())
    ambiente.guild.text_channels = [canale]
    ambiente.guild.get_channel = MagicMock(side_effect=lambda cid: canale if cid == CANALE_TESTO else None)
    await voice_temp_repo.set_config(GUILD, 111, 222)
    return ambiente


@pytest.mark.asyncio
async def test_salva_dal_pannello_come_il_comando(vocali):
    client = await _come(vocali, ADMIN)
    try:
        csrf = await _csrf(client, f"/server/{GUILD}/vocali")
        r = await client.post(f"/server/{GUILD}/vocali", data={"csrf": csrf, **CAMPI}, allow_redirects=False)
        assert r.status == 302 and "esito=salvato" in r.headers["Location"]
        c = await voice_temp_repo.get_config(GUILD)
        assert (c.nome_modello, c.nasce_bloccato, c.canale_registro_id, c.category_cap, c.pannello_colore) == (
            "Stanza {numero}", True, CANALE_TESTO, 12, 0x5865F2,
        )
        assert c.generator_channel_id == 111 and c.category_id == 222  # impianto intatto
        pagina = await (await client.get(f"/server/{GUILD}/vocali")).text()
        assert "&lt;b&gt;pannello&lt;/b&gt;" in pagina and "<b>pannello</b>" not in pagina
        di_nuovo = await client.post(f"/server/{GUILD}/vocali", data={"csrf": csrf, **CAMPI}, allow_redirects=False)
        assert "esito=invariato" in di_nuovo.headers["Location"]
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("campo,valore", [
    ("nome", "{utente.__class__}"), ("nome", "{numero:>999999}"), ("cap", "51"), ("cap", "0"), ("cap", "x"),
    ("colore", "ZZZZZZ"), ("registro", "424242"), ("registro", "12abc"), ("bloccati", "forse"), ("titolo", "a" * 257),
])
async def test_valori_storti_non_scrivono_niente(vocali, campo, valore):
    with pytest.raises(ImpostazioneNonValida):
        await web_panel_vocali.applica(vocali.guild, {**CAMPI, campo: valore}, ADMIN)
    c = await voice_temp_repo.get_config(GUILD)
    assert c.nome_modello is None and c.category_cap is None


@pytest.mark.asyncio
async def test_senza_impianto_non_si_salva(ambiente):
    with pytest.raises(ImpostazioneNonValida):
        await web_panel_vocali.applica(ambiente.guild, CAMPI, ADMIN)


@pytest.mark.asyncio
async def test_il_lettore_vede_la_pagina_ma_non_salva(vocali):
    await _imposta(vocali, "lettura", [7001])
    client = await _come(vocali, LETTORE)
    try:
        assert (await client.get(f"/server/{GUILD}/vocali")).status == 200
        csrf = await _csrf(client, f"/server/{GUILD}/vocali")
        r = await client.post(f"/server/{GUILD}/vocali", data={"csrf": csrf, **CAMPI}, allow_redirects=False)
        assert r.status == 403
        assert (await voice_temp_repo.get_config(GUILD)).nome_modello is None
    finally:
        await client.close()
