"""
tests/test_anti_raid_avviso_133.py
==================================
Issue #133, anti-raid:
- un solo avviso nel canale degli allarmi per episodio, aggiornato a
  ogni ingresso (non un messaggio per ogni ingresso);
- un ruolo "Quarantined" già esistente viene adottato e allineato:
  i canali ricevono i permessi di quarantena (una volta sola).
"""

from datetime import timedelta
from unittest.mock import AsyncMock

import discord

import cogs.security.anti_raid as modulo
from core.repositories.security_repo import security_repo
from tests.support.discord_fakes import fake_role, fake_text_channel
from tests.test_anti_raid_f1 import (  # noqa: F401  (fixture condivise)
    GUILD_ID,
    _azione,
    _canali_di_ogni_tipo,
    _interazione,
    _raid,
    cog,
    db_finto,
    orologio,
    server,
)


async def _canale_allarmi(cog, server):
    canale = fake_text_channel(channel_id=4000, name="allarmi")
    messaggio = AsyncMock(spec=discord.Message)
    canale.send.return_value = messaggio
    server.get_channel.side_effect = lambda cid: canale if cid == 4000 else None
    await cog.alert_channel.callback(cog, _interazione(), canale)
    return canale, messaggio


async def test_un_solo_avviso_aggiornato_a_ogni_ingresso(cog, server):
    await _azione(cog, "quarantine")
    canale, messaggio = await _canale_allarmi(cog, server)

    await _raid(cog, server, quanti=8)  # 6 ingressi oltre la soglia

    canale.send.assert_awaited_once()
    assert messaggio.edit.await_count == 5
    ultimo = messaggio.edit.await_args.kwargs["embed"]
    assert "6" in ultimo.title or "6" in ultimo.description
    assert "Persona107" in ultimo.description  # l'ultimo arrivato
    assert len(ultimo.description) <= 4096


async def test_avviso_con_tanti_ingressi_resta_nei_limiti_dell_embed(cog, server):
    await _azione(cog, "quarantine")
    canale, messaggio = await _canale_allarmi(cog, server)

    await _raid(cog, server, quanti=300)

    ultimo = messaggio.edit.await_args.kwargs["embed"]
    assert len(ultimo.description) <= 4096
    assert len(ultimo.title) <= 256
    assert "298" in ultimo.title or "298" in ultimo.description


async def test_dopo_la_fine_dell_episodio_nasce_un_avviso_nuovo(cog, server, orologio):
    await _azione(cog, "quarantine")
    canale, messaggio = await _canale_allarmi(cog, server)
    await _raid(cog, server, quanti=4)

    orologio(seconds=modulo.DURATA_BLOCCO_SECONDI + 60)
    await _raid(cog, server, quanti=3, primo_id=300)

    assert canale.send.await_count == 2


async def test_avviso_cancellato_ne_manda_uno_nuovo(cog, server):
    await _azione(cog, "quarantine")
    canale, messaggio = await _canale_allarmi(cog, server)
    risposta = AsyncMock()
    risposta.status = 404
    risposta.reason = "Not Found"
    messaggio.edit.side_effect = discord.NotFound(risposta, "sparito")

    await _raid(cog, server, quanti=5)

    assert canale.send.await_count >= 2


async def test_ruolo_quarantined_esistente_viene_adottato_e_allineato(cog, server):
    await _azione(cog, "quarantine")
    esistente = fake_role(role_id=7777, name="Quarantined")
    server.roles = [esistente]
    server.channels = _canali_di_ogni_tipo()

    await _raid(cog, server)

    server.create_role.assert_not_awaited()
    for canale in server.channels:
        canale.set_permissions.assert_awaited_once()
        assert canale.set_permissions.call_args.args[0] is esistente
    assert (await security_repo.get_settings(GUILD_ID)).quarantine_role_id == 7777


async def test_ruolo_salvato_con_canali_vecchi_viene_allineato_una_volta(cog, server):
    await _azione(cog, "quarantine")
    esistente = fake_role(role_id=7777, name="Quarantined")
    server.get_role.side_effect = lambda rid: esistente if rid == 7777 else None
    impostazioni = await security_repo.get_settings(GUILD_ID)
    await security_repo.save_settings(modulo._replace(impostazioni, quarantine_role_id=7777))
    canali = _canali_di_ogni_tipo()
    # Il primo canale ha già tutti i permessi di quarantena: non si tocca.
    gia_a_posto = canali[0]
    gia_a_posto.overwrites_for.return_value = discord.PermissionOverwrite(
        **modulo.PERMESSI_QUARANTENA
    )
    server.channels = canali

    await _raid(cog, server, quanti=6)

    gia_a_posto.set_permissions.assert_not_awaited()
    for canale in canali[1:]:
        canale.set_permissions.assert_awaited_once()  # una volta, non a ogni ingresso
