"""
tests/test_moderation_ordine_azione.py
======================================
Kick, ban, tempban e softban (M 1.3, M 1.4):
- chiamano `defer()` prima di parlare con Discord (LIM-25);
- fanno prima l'azione, poi il caso, il log e il DM (LIM-8): se
  l'azione fallisce non resta nessun caso e non parte nessun DM;
- gestiscono ogni `discord.HTTPException`, non solo `Forbidden`.

Database vero (clean_db) e repository veri; di Discord solo i finti
fedeli di tests/support/discord_fakes.py.
"""

from unittest.mock import MagicMock

import discord
import pytest

import core.scheduler as modulo_scheduler
from cogs.moderation._shared import MODULE_ACTIONS, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.softban_mute import ModerationSoftbanMuteCog
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)

ID_SERVER = 100
ID_MODERATORE = 10
ID_BERSAGLIO = 20
ID_CANALE_LOG = 7001


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_ACTIONS, True)
    await db.set_guild_setting(ID_SERVER, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    yield
    database_module.db._modules_cache.clear()


def _errore_http(stato: int = 400) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=stato, reason="Bad Request"), "Invalid Form Body")


class Scena:
    """Server, moderatore, bersaglio e interazione, con il registro delle chiamate."""

    def __init__(self) -> None:
        self.chiamate: list[str] = []
        self.server = fake_guild(ID_SERVER, owner_id=1)
        self.server.me.top_role = fake_role(role_id=3, position=50)
        self.server.me.id = 999
        self.canale_log = fake_text_channel(ID_CANALE_LOG, "mod-log")
        self.server.get_channel.return_value = self.canale_log

        self.moderatore = fake_member(ID_MODERATORE, roles=[fake_role(role_id=1, position=40)])
        self.moderatore.guild = self.server
        self.bersaglio = fake_member(ID_BERSAGLIO, roles=[fake_role(role_id=2, position=5)])
        self.bersaglio.guild = self.server
        self.server.get_member.return_value = self.moderatore

        self.interazione = fake_interaction(guild=self.server, user=self.moderatore)

        self._registra(self.interazione.response.defer, "defer")
        self._registra(self.interazione.followup.send, "followup")
        self._registra(self.bersaglio.ban, "ban")
        self._registra(self.bersaglio.kick, "kick")
        self._registra(self.bersaglio.send, "dm")
        self._registra(self.server.unban, "unban")
        self._registra(self.canale_log.send, "log")

    def _registra(self, finto, nome: str) -> None:
        async def _annota(*args, **kwargs):
            self.chiamate.append(nome)

        finto.side_effect = _annota

    def fallisce(self, finto, nome: str, errore: Exception) -> None:
        async def _annota_e_fallisce(*args, **kwargs):
            self.chiamate.append(nome)
            raise errore

        finto.side_effect = _annota_e_fallisce


async def _esegui(nome: str, scena: Scena) -> None:
    if nome == "softban":
        cog = ModerationSoftbanMuteCog(bot=None)
        await cog.softban.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
        return
    cog = ModerationActionsCog(bot=None)
    if nome == "kick":
        await cog.kick.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    elif nome == "ban":
        await cog.ban.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    elif nome == "tempban":
        await cog.tempban.callback(cog, scena.interazione, scena.bersaglio, "7d", "Spam ripetuto")


def _azione(nome: str) -> str:
    return "kick" if nome == "kick" else "ban"


COMANDI = ("kick", "ban", "tempban", "softban")


@pytest.mark.parametrize("nome", COMANDI)
async def test_defer_prima_di_ogni_chiamata_a_discord(nome):
    scena = Scena()

    await _esegui(nome, scena)

    assert scena.chiamate[0] == "defer"
    scena.interazione.response.send_message.assert_not_awaited()
    # La risposta finale passa da followup, con l'embed del caso.
    embed = scena.interazione.followup.send.call_args.kwargs["embed"]
    assert any(campo.name == "Caso" for campo in embed.fields)


@pytest.mark.parametrize("nome", COMANDI)
async def test_ordine_azione_caso_log_dm(nome):
    scena = Scena()

    await _esegui(nome, scena)

    ordine = [c for c in scena.chiamate if c in (_azione(nome), "log", "dm")]
    assert ordine == [_azione(nome), "log", "dm"]
    casi = await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO)
    assert [c.action_type for c in casi] == [nome]


@pytest.mark.parametrize("nome", COMANDI)
@pytest.mark.parametrize(
    "errore",
    [
        discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Missing Permissions"),
        _errore_http(400),
    ],
    ids=["forbidden", "http_400"],
)
async def test_azione_fallita_nessun_caso_nessun_dm_nessun_log(nome, errore):
    scena = Scena()
    finto = scena.bersaglio.kick if nome == "kick" else scena.bersaglio.ban
    scena.fallisce(finto, _azione(nome), errore)

    await _esegui(nome, scena)

    assert await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO) == []
    assert "dm" not in scena.chiamate
    assert "log" not in scena.chiamate
    assert "unban" not in scena.chiamate
    # Il moderatore riceve comunque una risposta chiara.
    risposta = scena.interazione.followup.send.call_args
    assert "Non sono riuscito" in risposta.args[0]


async def test_tempban_fallito_non_pianifica_lo_sblocco(monkeypatch):
    pianificate = []

    async def _pianifica(**kwargs):
        pianificate.append(kwargs)

    monkeypatch.setattr(modulo_scheduler.scheduler, "schedule", _pianifica)
    scena = Scena()
    scena.fallisce(scena.bersaglio.ban, "ban", _errore_http(400))

    await _esegui("tempban", scena)

    assert pianificate == []


async def test_tempban_riuscito_pianifica_lo_sblocco_con_il_numero_del_caso():
    scena = Scena()

    await _esegui("tempban", scena)

    casi = await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO)
    righe = await db.pool.fetch(
        "SELECT payload FROM scheduled_actions WHERE guild_id = $1 AND user_id = $2",
        ID_SERVER,
        ID_BERSAGLIO,
    )
    assert len(righe) == 1
    assert str(casi[0].case_number) in str(righe[0]["payload"])


async def test_softban_dm_non_recapitato_lo_dice_al_moderatore():
    scena = Scena()
    scena.fallisce(
        scena.bersaglio.send,
        "dm",
        discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Cannot send messages to this user"),
    )

    await _esegui("softban", scena)

    embed = scena.interazione.followup.send.call_args.kwargs["embed"]
    assert "Non è stato possibile notificare" in embed.footer.text
    assert scena.chiamate.index("ban") < scena.chiamate.index("unban")


@pytest.mark.parametrize("nome", ("timeout", "mute-role"))
async def test_timeout_e_mute_errore_http_gestito_senza_caso(nome):
    scena = Scena()
    if nome == "timeout":
        scena.bersaglio.timeout.side_effect = _errore_http(400)
        cog = ModerationActionsCog(bot=None)
        await cog.timeout.callback(cog, scena.interazione, scena.bersaglio, "10m", "Spam ripetuto")
        risposta = scena.interazione.response.send_message.call_args
    else:
        scena.server.get_role.return_value = fake_role(role_id=88, name="Muted")
        await db.set_guild_setting(ID_SERVER, "mute_role_id", 88)
        scena.bersaglio.add_roles.side_effect = _errore_http(400)
        cog = ModerationSoftbanMuteCog(bot=None)
        await cog.mute_role.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
        risposta = scena.interazione.followup.send.call_args

    assert "Non sono riuscito" in risposta.args[0]
    assert await moderation_repo.list_cases_for_user(ID_SERVER, ID_BERSAGLIO) == []
    assert "dm" not in scena.chiamate
