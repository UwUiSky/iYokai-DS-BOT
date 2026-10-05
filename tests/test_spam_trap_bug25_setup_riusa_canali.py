"""
tests/test_spam_trap_bug25_setup_riusa_canali.py
====================================================
BUG-25: rilanciare `/spamtrap-setup` senza indicare i canali (es. solo
`staff_role_add:`) su un server già configurato deve riusare i canali
salvati, non crearne di nuovi abbandonando quelli vecchi. Si crea solo
quello che manca davvero.

Database vero (clean_db); la prima configurazione la scrive il comando
stesso, non il test.
"""

from unittest.mock import create_autospec

import pytest
from discord.ext import commands

from cogs.security.spam_trap import SETTING_STAFF_ROLES, SpamTrapCog
from core.database import db
from core.repositories.spam_trap_repo import spam_trap_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_role,
    fake_text_channel,
)

ID_SERVER = 100


@pytest.fixture(autouse=True)
def _ambiente_pulito(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    spam_trap_repo._config_cache.clear()
    yield
    spam_trap_repo._config_cache.clear()


class _ServerConCanali:
    """
    Guild finta (autospec) che ricorda i canali creati: quelli che
    `create_text_channel` restituisce diventano visibili a `get_channel`,
    come su Discord.
    """

    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER, "Alpha")
        self.canali: dict[int, object] = {}
        self._prossimo_id = 7000
        self.guild.create_text_channel.side_effect = self._crea
        self.guild.get_channel.side_effect = self.canali.get
        self.guild.invites.return_value = []

    async def _crea(self, name, **kwargs):
        self._prossimo_id += 1
        canale = fake_text_channel(self._prossimo_id, name)
        self.canali[canale.id] = canale
        return canale

    @property
    def canali_creati(self) -> int:
        return self.guild.create_text_channel.await_count


async def _lancia_setup(cog: SpamTrapCog, server: _ServerConCanali, **opzioni) -> None:
    interazione = fake_interaction(guild=server.guild)
    await cog.spamtrap_setup.callback(cog, interazione, **opzioni)


@pytest.fixture
def cog() -> SpamTrapCog:
    return SpamTrapCog(create_autospec(commands.Bot, instance=True))


@pytest.mark.asyncio
async def test_aggiungere_un_ruolo_staff_non_ricrea_i_canali(cog):
    server = _ServerConCanali()
    await _lancia_setup(cog, server)
    prima = await spam_trap_repo.get_config(ID_SERVER)
    assert server.canali_creati == 2

    await _lancia_setup(cog, server, staff_role_add=fake_role(555, "Staff"))

    dopo = await spam_trap_repo.get_config(ID_SERVER)
    assert server.canali_creati == 2, "non deve creare altri canali"
    assert (dopo.trap_channel_id, dopo.log_channel_id) == (
        prima.trap_channel_id,
        prima.log_channel_id,
    )
    assert await db.get_guild_setting(ID_SERVER, SETTING_STAFF_ROLES) == [555]


@pytest.mark.asyncio
async def test_i_canali_riusati_non_ricevono_di_nuovo_l_embed(cog):
    server = _ServerConCanali()
    await _lancia_setup(cog, server)
    config = await spam_trap_repo.get_config(ID_SERVER)
    trappola = server.canali[config.trap_channel_id]
    log = server.canali[config.log_channel_id]

    await _lancia_setup(cog, server, staff_role_add=fake_role(555, "Staff"))

    assert trappola.send.await_count == 1
    assert log.send.await_count == 1


@pytest.mark.asyncio
async def test_se_la_trappola_e_stata_eliminata_si_ricrea_solo_quella(cog):
    server = _ServerConCanali()
    await _lancia_setup(cog, server)
    prima = await spam_trap_repo.get_config(ID_SERVER)
    del server.canali[prima.trap_channel_id]

    await _lancia_setup(cog, server)

    dopo = await spam_trap_repo.get_config(ID_SERVER)
    assert server.canali_creati == 3
    assert dopo.log_channel_id == prima.log_channel_id
    assert dopo.trap_channel_id != prima.trap_channel_id
    assert dopo.trap_channel_id in server.canali


@pytest.mark.asyncio
async def test_un_canale_passato_a_mano_sostituisce_quello_salvato(cog):
    server = _ServerConCanali()
    await _lancia_setup(cog, server)
    prima = await spam_trap_repo.get_config(ID_SERVER)
    nuovo_log = fake_text_channel(9001, "log-staff")

    await _lancia_setup(cog, server, log_channel=nuovo_log)

    dopo = await spam_trap_repo.get_config(ID_SERVER)
    assert server.canali_creati == 2
    assert dopo.trap_channel_id == prima.trap_channel_id
    assert dopo.log_channel_id == 9001


# ====================================================================
# M 3.13 (LIM-36): il server non può avere altri canali
# ====================================================================
def _troppi_canali():
    import discord
    from unittest.mock import MagicMock

    risposta = MagicMock()
    risposta.status = 400
    risposta.reason = "Bad Request"
    return discord.HTTPException(
        risposta, {"code": 30013, "message": "Maximum number of guild channels reached (500)"}
    )


@pytest.mark.asyncio
async def test_server_a_500_canali_messaggio_chiaro_e_niente_salvato(cog):
    server = _ServerConCanali()
    server.guild.create_text_channel.side_effect = _troppi_canali()
    interazione = fake_interaction(guild=server.guild)

    await cog.spamtrap_setup.callback(cog, interazione)

    interazione.followup.send.assert_awaited_once()
    testo = interazione.followup.send.call_args.args[0]
    assert "500" in testo
    assert "trap_channel" in testo  # dice come uscirne: indicare canali esistenti
    assert len(testo) <= 2000
    config = await spam_trap_repo.get_config(ID_SERVER)
    assert (config.trap_channel_id, config.log_channel_id) == (None, None)


@pytest.mark.asyncio
async def test_se_fallisce_il_secondo_canale_il_primo_non_resta_orfano(cog):
    server = _ServerConCanali()
    crea_davvero = server.guild.create_text_channel.side_effect
    chiamate = []

    async def _solo_il_primo(name, **kwargs):
        chiamate.append(name)
        if len(chiamate) == 2:
            raise _troppi_canali()
        return await crea_davvero(name, **kwargs)

    server.guild.create_text_channel.side_effect = _solo_il_primo
    interazione = fake_interaction(guild=server.guild)

    await cog.spamtrap_setup.callback(cog, interazione)

    (trappola,) = server.canali.values()
    trappola.delete.assert_awaited_once()
    trappola.send.assert_not_awaited()
    assert "500" in interazione.followup.send.call_args.args[0]
    config = await spam_trap_repo.get_config(ID_SERVER)
    assert (config.trap_channel_id, config.log_channel_id) == (None, None)


@pytest.mark.asyncio
async def test_setup_legge_subito_gli_inviti_del_server(cog):
    # M 3.17: gli inviti non si scaricano più per tutti i server
    # all'avvio. Chi configura lo spam-trap li ha pronti da subito,
    # così già il primo ingresso può essere attribuito.
    server = _ServerConCanali()

    await _lancia_setup(cog, server)

    server.guild.invites.assert_awaited_once()
