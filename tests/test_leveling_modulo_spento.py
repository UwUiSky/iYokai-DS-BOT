"""
tests/test_leveling_modulo_spento.py
====================================
M 9.7: con il modulo "leveling" spento su un server, OGNI comando di
economia, livelli, shop, cassa, giveaway e clan viene rifiutato prima
di fare qualunque cosa. Il test passa in rassegna tutti i comandi del
cog: un comando nuovo senza il controllo lo fa fallire. Database vero.
Funzioni coperte: SPEC §15
"""

import pytest
from discord import app_commands

from cogs.leveling.leveling import MODULE_LEVELING, LevelingCog
from core.repositories.leveling_repo import leveling_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD_ID = 100


def _tutti_i_comandi(cog: LevelingCog) -> list[app_commands.Command]:
    return [c for c in cog.walk_app_commands() if isinstance(c, app_commands.Command)]


def _nomi_dei_comandi() -> list[str]:
    cog = LevelingCog.__new__(LevelingCog)  # solo per leggere l'elenco dei comandi
    return sorted(c.qualified_name for c in _tutti_i_comandi(cog))


@pytest.fixture
async def cog(monkeypatch, clean_db):
    # Database collegato, ma nessun modulo attivato per GUILD_ID.
    await attiva_livelli(monkeypatch, clean_db)
    c = LevelingCog(bot=None)
    c.cog_unload()
    return c


async def _lancia(cog: LevelingCog, nome: str, interazione) -> None:
    comando = next(c for c in _tutti_i_comandi(cog) if c.qualified_name == nome)
    # Il controllo viene prima di tutto: gli argomenti non vengono nemmeno letti.
    argomenti = {parametro.name: None for parametro in comando.parameters}
    await comando.callback(cog, interazione, **argomenti)


def test_l_elenco_copre_tutte_le_famiglie_di_comandi():
    nomi = _nomi_dei_comandi()
    assert len(nomi) >= 35
    for atteso in ("daily", "shop buy", "cassa saldo", "assegna-lobby", "clan crea",
                   "clan tesoreria dona", "clan boost gilda", "giveaway", "level-roles add"):
        assert atteso in nomi


@pytest.mark.asyncio
@pytest.mark.parametrize("nome", _nomi_dei_comandi())
async def test_modulo_spento_comando_rifiutato(cog, clean_db, nome):
    interazione = fake_interaction(guild=fake_guild(GUILD_ID), user=fake_member(1))

    await _lancia(cog, nome, interazione)

    interazione.response.send_message.assert_awaited_once()
    chiamata = interazione.response.send_message.await_args
    assert "non è attivo" in chiamata.args[0]
    assert chiamata.kwargs["ephemeral"] is True
    interazione.response.defer.assert_not_awaited()
    interazione.followup.send.assert_not_awaited()
    # Nessuna scrittura: nemmeno una riga nelle tabelle dell'economia.
    for tabella in ("leveling_totals", "shop_items", "clans", "giveaways", "guild_chest"):
        assert await clean_db.fetchval(f"SELECT COUNT(*) FROM {tabella}") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("nome", _nomi_dei_comandi())
async def test_fuori_da_un_server_comando_rifiutato(cog, nome):
    interazione = fake_interaction(user=fake_member(1))
    interazione.guild = None

    await _lancia(cog, nome, interazione)

    interazione.response.send_message.assert_awaited_once()
    assert "solo dentro un server" in interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_modulo_acceso_il_comando_funziona(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD_ID)
    cog = LevelingCog(bot=None)
    cog.cog_unload()
    interazione = fake_interaction(guild=fake_guild(GUILD_ID), user=fake_member(1))

    await cog.daily.callback(cog, interazione)

    assert "Hai riscosso" in interazione.response.send_message.await_args.args[0]
    assert (await leveling_repo.get_totals(GUILD_ID, 1)).coins_total > 0


@pytest.mark.asyncio
async def test_modulo_spento_dopo_essere_stato_acceso(monkeypatch, clean_db):
    import core.database as database_module

    await attiva_livelli(monkeypatch, clean_db, GUILD_ID)
    await database_module.db.set_module_active_for_guild(GUILD_ID, MODULE_LEVELING, False)
    cog = LevelingCog(bot=None)
    cog.cog_unload()
    interazione = fake_interaction(guild=fake_guild(GUILD_ID), user=fake_member(1))

    await cog.daily.callback(cog, interazione)

    assert "non è attivo" in interazione.response.send_message.await_args.args[0]
    assert (await leveling_repo.get_totals(GUILD_ID, 1)).coins_total == 0
