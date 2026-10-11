"""
tests/test_spam_trap_117.py
===========================
Difetti dello spam-trap trovati leggendo:
- piu' messaggi di fila nella trappola facevano ripartire tutta la
  sequenza (DM, ban, caso, propagazione) una volta per messaggio;
- trappola e log sullo stesso canale;
- il bot non avvisava se mancavano i permessi che servono davvero;
- il canale dei log creato dal bot poteva restare invisibile al bot;
- il transcript faceva una chiamata a Discord per ogni messaggio dell'utente
  prima di bannarlo;
- un appello accolto lasciava il ban negli altri server della rete;
- la pulizia dopo il ban si fermava su un errore del registro di controllo
  diverso da "permesso negato".
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.spam_trap as modulo
from core.repositories.spam_trap_repo import spam_trap_repo
from tests.support.discord_fakes import fake_interaction, fake_member
from tests.test_spam_trap_ban_e_appello import (  # noqa: F401  (fixture condivisa)
    GUILD_ID,
    UTENTE_ID,
    scenario,
)


async def test_cinque_messaggi_insieme_un_solo_ban(scenario):
    await asyncio.gather(*(scenario.scrive_nella_trappola() for _ in range(5)))
    assert scenario.server.ban.await_count == 1
    scenario.log.send.assert_awaited_once()


async def test_un_messaggio_subito_dopo_il_ban_non_rifa_niente(scenario):
    await scenario.scrive_nella_trappola()
    await scenario.scrive_nella_trappola()
    assert scenario.server.ban.await_count == 1


async def test_dopo_un_ban_fallito_si_puo_riprovare(scenario):
    scenario.server.ban.side_effect = discord.Forbidden(MagicMock(status=403), "no")
    await scenario.scrive_nella_trappola()
    scenario.server.ban.side_effect = None
    await scenario.scrive_nella_trappola()
    assert scenario.server.ban.await_count == 2


async def test_trappola_e_log_non_possono_essere_lo_stesso_canale(scenario):
    interazione = fake_interaction(guild=scenario.server)
    stesso = scenario.trappola
    prima = await spam_trap_repo.get_config(GUILD_ID)
    await scenario.cog.spamtrap_setup.callback(scenario.cog, interazione, stesso, stesso)
    assert "diversi" in interazione.response.send_message.call_args.args[0]
    assert await spam_trap_repo.get_config(GUILD_ID) == prima


async def test_il_setup_dice_cosa_manca_al_bot(scenario):
    interazione = fake_interaction(guild=scenario.server)
    await scenario.cog.spamtrap_setup.callback(scenario.cog, interazione)
    testo = interazione.followup.send.call_args.args[0]
    assert "Bannare membri" in testo  # il bot finto non ha permessi


async def test_il_canale_log_creato_dal_bot_e_visibile_al_bot(scenario):
    scenario.server.create_text_channel.reset_mock()
    await scenario.cog._create_log_channel(scenario.server)
    overwrites = scenario.server.create_text_channel.call_args.kwargs["overwrites"]
    assert overwrites[scenario.server.me].create_private_threads is True
    assert overwrites[scenario.server.default_role].view_channel is False


async def test_il_transcript_ha_un_tetto_di_messaggi_e_lo_dichiara(scenario):
    adesso = datetime.now(timezone.utc)
    for numero in range(modulo.MAX_MESSAGGI_TRANSCRIPT + 30):
        await spam_trap_repo.index_message(
            5000 + numero, GUILD_ID, scenario.trappola.id, UTENTE_ID, adesso
        )
    scenario.trappola.fetch_message.reset_mock()

    voci = await scenario.cog._gather_transcript_entries(scenario.server, scenario.utente)

    assert scenario.trappola.fetch_message.await_count == modulo.MAX_MESSAGGI_TRANSCRIPT
    assert len(voci) == modulo.MAX_MESSAGGI_TRANSCRIPT + 1
    assert "30 older message" in voci[0].content


async def test_appello_accolto_toglie_anche_i_ban_propagati(scenario, monkeypatch):
    revoca = AsyncMock(return_value=2)
    monkeypatch.setattr(modulo, "revoca_ban_propagati", revoca)
    scenario.bot.fetch_user = AsyncMock(return_value=MagicMock(send=AsyncMock()))
    vista = modulo.AppealActionsView(GUILD_ID, 1, UTENTE_ID)
    staff = fake_member(user_id=7, guild_permissions=discord.Permissions(ban_members=True))
    interazione = fake_interaction(guild=scenario.server, user=staff)
    interazione.client = scenario.bot
    interazione.edit_original_response = AsyncMock()

    await vista.unban(interazione)

    revoca.assert_awaited_once_with(scenario.bot, GUILD_ID, UTENTE_ID)
    scenario.server.unban.assert_awaited_once()


async def test_una_revoca_che_fallisce_non_blocca_lo_unban(scenario, monkeypatch):
    monkeypatch.setattr(modulo, "revoca_ban_propagati", AsyncMock(side_effect=RuntimeError("boom")))
    scenario.bot.fetch_user = AsyncMock(return_value=MagicMock(send=AsyncMock()))
    vista = modulo.AppealActionsView(GUILD_ID, 1, UTENTE_ID)
    staff = fake_member(user_id=7, guild_permissions=discord.Permissions(ban_members=True))
    interazione = fake_interaction(guild=scenario.server, user=staff)
    interazione.client = scenario.bot
    interazione.edit_original_response = AsyncMock()
    await vista.unban(interazione)
    assert "Unbanned" in interazione.edit_original_response.call_args.kwargs["content"]


async def test_pulizia_dopo_il_ban_regge_un_errore_del_registro(scenario):
    scenario.server.audit_logs.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    await scenario.cog._cleanup_user_artifacts(scenario.server, scenario.utente)  # non solleva


def _canale_con_permessi(**permessi):
    from tests.support.discord_fakes import fake_text_channel

    canale = fake_text_channel()
    canale.mention = "#canale"
    canale.permissions_for = MagicMock(return_value=discord.Permissions(**permessi))
    return canale


def _server_senza_bannare(*, ban: bool):
    from tests.support.discord_fakes import fake_guild

    server = fake_guild()
    server.me.guild_permissions = discord.Permissions(ban_members=ban)
    return server


def test_tutti_e_tre_gli_avvisi_dei_permessi_mancanti():
    trappola = _canale_con_permessi()
    log = _canale_con_permessi()

    avvisi = modulo._permessi_mancanti(_server_senza_bannare(ban=False), trappola, log)

    assert len(avvisi) == 3
    assert "Bannare membri" in avvisi[0]
    assert "non posso scrivere" in avvisi[1]
    assert "non vedo i messaggi" in avvisi[2]


def test_senza_thread_nel_log_l_avviso_e_quello_degli_appelli():
    trappola = _canale_con_permessi(view_channel=True, read_message_history=True)
    log = _canale_con_permessi(view_channel=True, send_messages=True, embed_links=True)

    avvisi = modulo._permessi_mancanti(_server_senza_bannare(ban=True), trappola, log)

    assert len(avvisi) == 1 and "thread" in avvisi[0] and "appelli" in avvisi[0]


def test_con_tutto_a_posto_nessun_avviso():
    tutto = dict(
        view_channel=True, send_messages=True, embed_links=True, read_message_history=True,
        create_private_threads=True, send_messages_in_threads=True,
    )
    assert modulo._permessi_mancanti(
        _server_senza_bannare(ban=True), _canale_con_permessi(**tutto), _canale_con_permessi(**tutto)
    ) == []


async def test_se_la_sequenza_salta_la_propagazione_non_resta_orfana(scenario, monkeypatch):
    creati = []
    crea_originale = asyncio.create_task

    def _crea(coro, **kw):
        task = crea_originale(coro, **kw)
        creati.append(task)
        return task

    async def propagazione_lenta(*_a, **_k):
        await asyncio.sleep(30)

    monkeypatch.setattr(modulo, "propagate_ban", propagazione_lenta)
    monkeypatch.setattr(modulo.asyncio, "create_task", _crea)
    monkeypatch.setattr(modulo.moderation_repo, "create_case", AsyncMock(side_effect=RuntimeError("db giu'")))

    with pytest.raises(RuntimeError):
        await scenario.cog._esegui_sequenza_ban(
            scenario.messaggio(scenario.trappola, 900_000, datetime.now(timezone.utc))
        )

    # Annullata, non attesa fino in fondo: senza il `cancel()` il test aspetterebbe i 30 secondi.
    assert creati and all(t.cancelled() for t in creati)
