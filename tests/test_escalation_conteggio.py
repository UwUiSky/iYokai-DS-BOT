"""
tests/test_escalation_conteggio.py
==================================
Conteggio delle infrazioni della scala di escalation (LIM-32).

Discord manda un evento `on_automod_action` per OGNI azione di una
regola: una regola con "blocca" e "avvisa" manda due eventi per lo
stesso messaggio. L'infrazione deve contare una volta sola. Due
messaggi diversi arrivati insieme devono contare due volte (conteggio
atomico nel database).

Database vero; evento e membro sono finti fedeli.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.automod.escalation as modulo_escalation
from core.database import Database
from core.repositories.escalation_repo import escalation_repo
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_member

GUILD_ID = 666
UTENTE_ID = 4242
REGOLA_ID = 9001


@pytest.fixture
async def cog(clean_db, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo_escalation, "db", db_finto)
    monkeypatch.setattr(escalation_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(moderation_repo, "_pool_provider", lambda: clean_db)

    bot = create_autospec(commands.Bot, instance=True)
    bot.user = fake_member(user_id=999, bot=True)
    cog = modulo_escalation.EscalationCog(bot)
    # La scala viene accesa con il suo comando, come farebbe un admin.
    await escalation_repo.set_enabled(GUILD_ID, True)
    return cog


def _evento(
    membro: MagicMock,
    tipo_azione: discord.AutoModRuleActionType,
    *,
    contenuto: str = "parola vietata",
    message_id: int | None = None,
) -> MagicMock:
    evento = create_autospec(discord.AutoModAction, instance=True)
    evento.guild_id = GUILD_ID
    evento.user_id = membro.id
    evento.member = membro
    evento.rule_id = REGOLA_ID
    evento.message_id = message_id
    evento.content = contenuto
    evento.matched_keyword = "vietata"
    evento.action = discord.AutoModRuleAction(type=tipo_azione, channel_id=123) if (
        tipo_azione is discord.AutoModRuleActionType.send_alert_message
    ) else discord.AutoModRuleAction(type=tipo_azione)
    return evento


async def _conteggio(pool) -> int:
    return await pool.fetchval(
        "SELECT violation_count FROM automod_violations WHERE guild_id = $1 AND user_id = $2",
        GUILD_ID,
        UTENTE_ID,
    )


async def _numero_casi(pool) -> int:
    return await pool.fetchval(
        "SELECT count(*) FROM moderation_cases WHERE guild_id = $1", GUILD_ID
    )


async def test_regola_con_due_azioni_conta_una_infrazione(cog, clean_db):
    membro = fake_member(user_id=UTENTE_ID)
    blocco = _evento(membro, discord.AutoModRuleActionType.block_message)
    avviso = _evento(membro, discord.AutoModRuleActionType.send_alert_message)

    await cog.on_automod_action(blocco)
    await cog.on_automod_action(avviso)

    assert await _conteggio(clean_db) == 1
    # Primo gradino della scala: un solo warn, nessun timeout.
    assert await _numero_casi(clean_db) == 1
    membro.timeout.assert_not_awaited()


async def test_due_azioni_arrivate_insieme_contano_una_infrazione(cog, clean_db):
    membro = fake_member(user_id=UTENTE_ID)
    blocco = _evento(membro, discord.AutoModRuleActionType.block_message)
    avviso = _evento(membro, discord.AutoModRuleActionType.send_alert_message)

    await asyncio.gather(cog.on_automod_action(blocco), cog.on_automod_action(avviso))

    assert await _conteggio(clean_db) == 1
    membro.timeout.assert_not_awaited()


async def test_messaggi_diversi_arrivati_insieme_contano_tutti(cog, clean_db):
    # Con "leggi, somma, scrivi" due eventi insieme leggevano lo stesso
    # numero e un'infrazione andava persa.
    membro = fake_member(user_id=UTENTE_ID)
    eventi = [
        _evento(membro, discord.AutoModRuleActionType.block_message, contenuto=f"vietata {numero}")
        for numero in range(8)
    ]

    await asyncio.gather(*(cog.on_automod_action(evento) for evento in eventi))

    assert await _conteggio(clean_db) == 8
    # Un caso per infrazione: nessun gradino applicato due volte o saltato.
    assert await _numero_casi(clean_db) == 8


async def test_stesso_testo_ripetuto_piu_tardi_conta_di_nuovo(cog, clean_db, monkeypatch):
    membro = fake_member(user_id=UTENTE_ID)
    adesso = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(modulo_escalation, "_adesso", lambda: adesso)
    await cog.on_automod_action(_evento(membro, discord.AutoModRuleActionType.block_message))

    dopo = adesso + timedelta(seconds=modulo_escalation.FINESTRA_STESSO_MESSAGGIO + 1)
    monkeypatch.setattr(modulo_escalation, "_adesso", lambda: dopo)
    await cog.on_automod_action(_evento(membro, discord.AutoModRuleActionType.block_message))

    assert await _conteggio(clean_db) == 2


async def test_dopo_la_buona_condotta_il_conteggio_riparte_da_uno(cog, clean_db, monkeypatch):
    membro = fake_member(user_id=UTENTE_ID)
    inizio = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(modulo_escalation, "_adesso", lambda: inizio)
    await cog.on_automod_action(
        _evento(membro, discord.AutoModRuleActionType.block_message, contenuto="uno")
    )
    await cog.on_automod_action(
        _evento(membro, discord.AutoModRuleActionType.block_message, contenuto="due")
    )
    assert await _conteggio(clean_db) == 2

    # La scala di default azzera dopo 30 giorni senza infrazioni.
    molto_dopo = inizio + timedelta(days=31)
    monkeypatch.setattr(modulo_escalation, "_adesso", lambda: molto_dopo)
    await cog.on_automod_action(
        _evento(membro, discord.AutoModRuleActionType.block_message, contenuto="tre")
    )

    assert await _conteggio(clean_db) == 1


# ====================================================================
# Prima l'azione su Discord, poi il caso (LIMITI, lista di controllo 10 e 11)
# ====================================================================
def _errore_http() -> discord.HTTPException:
    risposta = MagicMock()
    risposta.status = 500
    risposta.reason = "Internal Server Error"
    return discord.HTTPException(risposta, "errore finto di Discord")


@pytest.mark.parametrize("azione", ["kick", "ban", "timeout"])
async def test_azione_fallita_non_lascia_un_caso(cog, clean_db, azione):
    from discord import app_commands
    from tests.support.discord_fakes import fake_guild, fake_interaction

    interazione = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    await cog.set_step.callback(
        cog, interazione, 1, app_commands.Choice(name=azione, value=azione), 10
    )
    membro = fake_member(user_id=UTENTE_ID)
    getattr(membro, azione).side_effect = _errore_http()

    await cog.on_automod_action(_evento(membro, discord.AutoModRuleActionType.block_message))

    getattr(membro, azione).assert_awaited_once()
    assert await _numero_casi(clean_db) == 0


async def test_kick_riuscito_crea_il_caso_dopo_l_azione(cog, clean_db):
    from discord import app_commands
    from tests.support.discord_fakes import fake_guild, fake_interaction

    interazione = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    await cog.set_step.callback(
        cog, interazione, 1, app_commands.Choice(name="Kick", value="kick"), None
    )
    membro = fake_member(user_id=UTENTE_ID)
    casi_al_momento_del_kick = []

    async def _kick(**_kwargs):
        casi_al_momento_del_kick.append(await _numero_casi(clean_db))

    membro.kick.side_effect = _kick

    await cog.on_automod_action(_evento(membro, discord.AutoModRuleActionType.block_message))

    assert casi_al_momento_del_kick == [0]
    assert await _numero_casi(clean_db) == 1
    assert len(membro.kick.call_args.kwargs["reason"]) <= 512
