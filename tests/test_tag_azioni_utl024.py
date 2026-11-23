"""
tests/test_tag_azioni_utl024.py
===============================
UTL-024 (D121): le azioni sicure di un tag (fino a 3), salvate nel database e fatte partire con i permessi di chi usa il
tag, dopo la risposta. Database vero per l'archivio, Discord finto.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.utility.custom_commands import CustomCommandsCog
from core import azioni_sicure as az
from core.repositories.custom_command_repo import custom_command_repo
from tests.test_azioni_sicure_utl024_111 import G, _scena

NOME = "benvenuto-giochi"


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await custom_command_repo.create_tag(G, NOME, response="ciao", use_embed=False, role_id=None, role_action="nessuna",
                                         cooldown_seconds=0, ping_ruoli=False, created_by=5)
    yield


async def test_si_salvano_al_massimo_3_azioni_e_si_tolgono_per_numero():
    for i in range(3):
        assert await custom_command_repo.aggiungi_azione(G, NOME, {"tipo": "dai_ruolo", "ruolo_id": 10 + i}, az.MAX_AZIONI_TAG)
    assert not await custom_command_repo.aggiungi_azione(G, NOME, {"tipo": "dai_ruolo", "ruolo_id": 99}, az.MAX_AZIONI_TAG)
    assert [a["ruolo_id"] for a in await custom_command_repo.azioni_di(G, NOME)] == [10, 11, 12]
    assert await custom_command_repo.togli_azione(G, NOME, 2)
    assert [a["ruolo_id"] for a in await custom_command_repo.azioni_di(G, NOME)] == [10, 12]
    assert not await custom_command_repo.togli_azione(G, NOME, 5)
    assert not await custom_command_repo.aggiungi_azione(G, "non-esiste", {"tipo": "reazione", "emoji": "👍"}, 3)


async def test_togliendo_il_tag_spariscono_le_azioni(clean_db):
    await custom_command_repo.aggiungi_azione(G, NOME, {"tipo": "reazione", "emoji": "👍"}, 3)
    await custom_command_repo.delete_tag(G, NOME)
    assert await clean_db.fetchval("SELECT count(*) FROM tag_azioni") == 0


async def test_chi_usa_il_tag_riceve_le_azioni_con_i_suoi_permessi():
    guild, canale, esec, utente = _scena()
    await custom_command_repo.aggiungi_azione(G, NOME, {"tipo": "dai_ruolo", "ruolo_id": 10}, 3)
    await custom_command_repo.aggiungi_azione(G, NOME, {"tipo": "dai_ruolo", "ruolo_id": 12}, 3)  # admin: rifiutato
    await custom_command_repo.aggiungi_azione(G, NOME, {"tipo": "messaggio", "canale_id": 77, "testo": "ciao"}, 3)
    cog = CustomCommandsCog(MagicMock())
    tag = await custom_command_repo.get_tag(G, NOME)
    note = await cog._azioni_extra(tag, guild, utente, None)
    assert utente.add_roles.await_count == 1  # solo quello sicuro
    canale.send.assert_awaited_once()
    assert len(note) == 1  # l'azione rifiutata si dice, le altre vanno lo stesso


async def test_un_tipo_non_ammesso_salvato_a_mano_non_esegue(clean_db):
    guild, canale, esec, utente = _scena()
    await clean_db.execute("INSERT INTO tag_azioni VALUES ($1, $2, 1, '{\"tipo\": \"ban\", \"utente_id\": 6}')", G, NOME)
    cog = CustomCommandsCog(MagicMock())
    tag = await custom_command_repo.get_tag(G, NOME)
    note = await cog._azioni_extra(tag, guild, utente, None)
    assert len(note) == 1
