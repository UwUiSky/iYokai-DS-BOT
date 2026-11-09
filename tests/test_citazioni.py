"""
tests/test_citazioni.py
=======================
D69 B16 (UTL-206, 207, 222, 229): citazioni del server (tetto 500, elimina solo le proprie, import/export JSON),
conteggio dei comandi usati e registro dei comandi dello staff. Archivio su PostgreSQL vero.
"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.utility.citazioni as modulo
from core.citazioni_logic import (
    MAX_PER_SERVER, ImportCitazioniErrato, e_comando_staff, leggi_importazione, pulisci_testo, righe_in_json, riga_citazione,
)
from core.log_eventi_logic import INTERRUTTORI, interruttore_di
from core.repositories.citazioni_repo import CitazioniRepository, ComandiUsoRepository, TroppeCitazioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 7


def test_testo_pulito_e_tagliato():
    assert pulisci_testo("  ciao  \n") == "ciao"
    assert len(pulisci_testo("x" * 5000)) == 1000


def test_comandi_dello_staff():
    assert e_comando_staff("admin-moduli citazioni azione") and e_comando_staff("mod-ban utente")
    assert not e_comando_staff("fun citazioni caso") and not e_comando_staff("utility ping")


def test_menu_eventi_dei_log_resta_entro_25():
    assert len(INTERRUTTORI) <= 25 and interruttore_di("staff_command") == "comandi_staff"


def test_import_export_andata_e_ritorno_e_righe_sbagliate():
    righe = [{"testo": "uno", "autore_id": 5, "link": None}, {"testo": "due", "autore_id": None, "link": None}]
    assert leggi_importazione(righe_in_json(righe), 10) == righe
    assert len(leggi_importazione(righe_in_json(righe), 1)) == 1
    sporco = b'{"citazioni": [1, {"testo": 3}, {"testo": "ok", "autore_id": "x", "link": "http://evil"}]}'
    assert leggi_importazione(sporco, 10) == [{"testo": "ok", "autore_id": None, "link": None}]
    for brutto in (b"non json", b"[]", b"\xff\xfe", b"x" * (1024 * 1024 + 1)):
        with pytest.raises(ImportCitazioniErrato):
            leggi_importazione(brutto, 10)


def test_riga_ha_numero_e_autore():
    assert riga_citazione({"id": 3, "testo": "ciao", "autore_id": 9}) == "“ciao” — <@9> (#3)"


@pytest.fixture
def repo(clean_db):
    return CitazioniRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_tetto_e_cancellazione_solo_delle_proprie(repo):
    numero = await repo.aggiungi(G, "ciao a tutti", 1, 2, None)
    assert await repo.elimina(G, numero, 99) is False  # non l'ha salvata lui
    assert await repo.elimina(G + 1, numero, 2) is False  # altro server
    assert await repo.elimina(G, numero, 2) is True
    assert await repo.importa(G, [{"testo": f"c{i}", "autore_id": None, "link": None} for i in range(MAX_PER_SERVER + 5)], 2) == MAX_PER_SERVER
    with pytest.raises(TroppeCitazioni):
        await repo.aggiungi(G, "una di troppo", None, 2, None)
    assert await repo.elimina_tutte(G) == MAX_PER_SERVER and await repo.conta(G) == 0


@pytest.mark.asyncio
async def test_cerca_non_usa_i_jolly(repo):
    await repo.aggiungi(G, "100% sicuro", None, 1, None)
    await repo.aggiungi(G, "altra cosa", None, 1, None)
    assert len(await repo.cerca(G, "%")) == 1 and len(await repo.cerca(G, "_")) == 0
    assert (await repo.a_caso(G + 5)) is None


@pytest.mark.asyncio
async def test_comandi_piu_usati_per_giorno(clean_db):
    r = ComandiUsoRepository(pool_provider=lambda: clean_db)
    oggi = date.today()
    for _ in range(3):
        await r.registra(G, "fun citazioni caso", oggi)
    await r.registra(G, "utility ping", oggi)
    await r.registra(G, "utility ping", oggi - timedelta(days=30))
    assert await r.piu_usati(G, oggi - timedelta(days=7)) == [("fun citazioni caso", 3), ("utility ping", 1)]
    assert (await r.piu_usati(G, oggi - timedelta(days=60)))[1] == ("utility ping", 2)
    assert await r.piu_usati(G + 1, oggi) == []


@pytest.mark.asyncio
async def test_registro_staff_scrive_solo_se_il_comando_e_dello_staff_e_l_evento_e_acceso():
    cog = modulo.CitazioniCog(MagicMock())
    guild = fake_guild(G)
    inter = fake_interaction(guild=guild, user=fake_member(5))
    inter.is_guild_integration = MagicMock(return_value=True)
    inter.channel_id = 3
    comando = MagicMock(spec=discord.app_commands.Command)
    comando.qualified_name = "admin-moduli citazioni azione"
    with patch.object(modulo, "comandi_uso_repo") as uso, patch.object(modulo, "log_eventi_repo") as ev, \
            patch.object(modulo.router, "destinazione", AsyncMock(return_value="dest")), \
            patch.object(modulo.router, "invia_a", AsyncMock()) as invia, \
            patch.object(modulo, "lingua_risposta", AsyncMock(return_value="it")):
        uso.registra = AsyncMock()
        ev.evento_acceso = AsyncMock(return_value=True)
        await cog.on_app_command_completion(inter, comando)
        uso.registra.assert_awaited_once()
        invia.assert_awaited_once()
        comando.qualified_name = "fun citazioni caso"
        await cog.on_app_command_completion(inter, comando)
        assert invia.await_count == 1 and uso.registra.await_count == 2
        ev.evento_acceso = AsyncMock(return_value=False)
        comando.qualified_name = "mod-ban utente"
        await cog.on_app_command_completion(inter, comando)
        assert invia.await_count == 1


@pytest.mark.asyncio
async def test_presenti_con_codice_esclude_chi_e_uscito(clean_db):
    from core.repositories.invite_stats_repo import InviteStatsRepository
    r = InviteStatsRepository(pool_provider=lambda: clean_db)
    await clean_db.execute(
        "INSERT INTO invite_joins (guild_id, user_id, inviter_id, code, kind) VALUES (1,10,5,'abc','invite'),(1,11,5,'abc','invite'),(1,12,5,'xyz','invite')")
    await clean_db.execute("UPDATE invite_joins SET left_at = now() WHERE user_id = 11")
    assert await r.presenti_con_codice(1, "abc") == [10] and await r.presenti_con_codice(2, "abc") == []
