"""
tests/test_global_ban_revisione_117.py
======================================
Difetti trovati da cacciatore e revisore nel ban globale:
- un unban fallito non chiude la riga (si ritenta); uno riuscito si;
- un appello accolto mentre la propagazione e' a meta' la ferma: nessun ban dopo la revoca;
- se un'altra sorgente ha ancora bannato l'utente lì, il suo ban resta;
- lo staff (admin/mod, bot, ruolo staff) del server di arrivo non viene bannato;
- la pulizia del registro e' una volta per giro e il registro ha gli indici;
- `/modban unban` toglie anche i ban propagati.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

import cogs.security.global_ban as modulo
from core.repositories.global_ban_repo import global_ban_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.test_global_ban_117 import USER, _bot, _server, ambiente  # noqa: F401  (fixture condivise)


def _http(status=500):
    risposta = MagicMock(status=status, reason="x")
    return discord.HTTPException(risposta, "boom")


# ---------------------------------------------------------------- revoca
async def test_un_unban_fallito_resta_da_ritentare(ambiente):
    a, b, c = _server(1), _server(2), _server(3)
    ambiente.update({1, 2, 3})
    bot = _bot(a, b, c)
    await modulo.propagate_ban(bot, a, USER, "x")
    b.unban.side_effect = _http()

    tolti = await modulo.revoca_ban_propagati(bot, 1, USER)

    assert tolti == 1  # solo C
    assert await global_ban_repo.active_propagations(1, USER) == [2]  # B resta aperto
    b.unban.side_effect = None
    assert await modulo.revoca_ban_propagati(bot, 1, USER) == 1
    assert await global_ban_repo.active_propagations(1, USER) == []


async def test_ban_dello_staff_di_quel_server_o_gia_sbannato_chiude_la_riga(ambiente):
    a, b, c = _server(1), _server(2, ban_reason="Spam: deciso dallo staff"), _server(3)
    ambiente.update({1, 2, 3})
    bot = _bot(a, b, c)
    await modulo.propagate_ban(bot, a, USER, "x")
    c.fetch_ban.side_effect = discord.NotFound(MagicMock(status=404, reason="x"), "no")

    assert await modulo.revoca_ban_propagati(bot, 1, USER) == 0

    b.unban.assert_not_awaited()
    assert await global_ban_repo.active_propagations(1, USER) == []


async def test_revoked_at_esclude_il_ban_dal_conteggio_della_rete(ambiente, clean_db):
    a, b = _server(1), _server(2)
    ambiente.update({1, 2})
    bot = _bot(a, b)
    await modulo.propagate_ban(bot, a, USER, "x")
    assert (await global_ban_repo.network_summary(USER))[0] == 1
    await modulo.revoca_ban_propagati(bot, 1, USER)
    assert (await global_ban_repo.network_summary(USER))[0] == 0
    assert await clean_db.fetchval("SELECT revoked_at FROM global_ban_log") is not None


async def test_se_un_altro_server_lo_ha_ancora_bannato_lì_il_ban_resta(ambiente):
    a, b, c = _server(1), _server(2), _server(3)
    ambiente.update({1, 2, 3})
    bot = _bot(a, b, c)
    await modulo.propagate_ban(bot, a, USER, "x")  # B e C
    await modulo.propagate_ban(bot, c, USER, "x")  # da C: A e B

    tolti = await modulo.revoca_ban_propagati(bot, 1, USER)  # appello solo in A

    b.unban.assert_not_awaited()  # C lo ha ancora bannato su B
    assert tolti == 1  # solo su C, dove nessun altro lo aveva propagato
    assert await global_ban_repo.active_propagations(1, USER) == []
    assert 2 in await global_ban_repo.active_propagations(3, USER)
    # Quando poi decide C, il ban su B salta.
    await modulo.revoca_ban_propagati(bot, 3, USER)
    b.unban.assert_awaited_once()


async def test_appello_accolto_a_meta_propagazione_ferma_i_ban_successivi(ambiente):
    a = _server(1)
    destinazioni = [_server(i) for i in (2, 3, 4)]
    ambiente.update({1, 2, 3, 4})
    bot = _bot(a, *destinazioni)
    cancello = asyncio.Event()
    avviato = asyncio.Event()

    async def lento(*_a, **_k):
        avviato.set()
        await cancello.wait()

    destinazioni[1].ban.side_effect = lento  # il server 3 e' lento

    propagazione = asyncio.create_task(modulo.propagate_ban(bot, a, USER, "x"))
    await avviato.wait()
    revoca = asyncio.create_task(modulo.revoca_ban_propagati(bot, 1, USER))
    await asyncio.sleep(0.05)
    assert not revoca.done()  # aspetta il ban in volo, non lo scavalca
    cancello.set()

    propagati = await propagazione
    tolti = await revoca

    assert propagati == [2, 3]
    destinazioni[2].ban.assert_not_awaited()  # nessun ban dopo la revoca
    assert tolti == 2
    assert destinazioni[0].unban.await_count == destinazioni[1].unban.await_count == 1
    assert await global_ban_repo.active_propagations(1, USER) == []


# ---------------------------------------------------------------- staff
async def test_lo_staff_del_server_di_arrivo_non_viene_bannato(ambiente):
    a, admin_qui, normale = _server(1), _server(2), _server(3)
    ambiente.update({1, 2, 3})
    modulo.db.get_guild_setting = AsyncMock(return_value=[])
    admin_qui.get_member.return_value = fake_member(
        user_id=USER, guild_permissions=discord.Permissions(administrator=True)
    )
    normale.get_member.return_value = fake_member(user_id=USER, guild_permissions=discord.Permissions.none())
    for presente in (admin_qui, normale):
        presente.get_member.return_value.top_role = fake_role(role_id=1, position=1)
        presente.me.top_role = fake_role(role_id=9, position=50)

    propagati = await modulo.propagate_ban(_bot(a, admin_qui, normale), a, USER, "x")

    assert propagati == [3]
    admin_qui.ban.assert_not_awaited()


async def test_un_bot_o_un_ruolo_staff_configurato_non_viene_bannato(ambiente):
    a, con_bot, con_ruolo = _server(1), _server(2), _server(3)
    ambiente.update({1, 2, 3})
    staff = fake_role(role_id=77, position=1)
    modulo.db.get_guild_setting = AsyncMock(side_effect=lambda gid, *_a, **_k: [77] if gid == 3 else [])
    con_bot.get_member.return_value = fake_member(user_id=USER, bot=True)
    con_ruolo.get_member.return_value = fake_member(user_id=USER, roles=[staff])
    for s in (con_bot, con_ruolo):
        s.get_member.return_value.top_role = fake_role(role_id=1, position=1)
        s.me.top_role = fake_role(role_id=9, position=50)

    assert await modulo.propagate_ban(_bot(a, con_bot, con_ruolo), a, USER, "x") == []


# ---------------------------------------------------------------- registro
async def test_la_pulizia_del_registro_e_una_per_giro(ambiente, monkeypatch):
    a = _server(1)
    altri = [_server(i) for i in (2, 3, 4)]
    ambiente.update({1, 2, 3, 4})
    pulizia = AsyncMock()
    monkeypatch.setattr(global_ban_repo, "purge_old", pulizia)

    await modulo.propagate_ban(_bot(a, *altri), a, USER, "x")

    pulizia.assert_awaited_once()


async def test_il_registro_ha_gli_indici_per_utente_e_sorgente(clean_db):
    righe = await clean_db.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'global_ban_log'")
    nomi = {r["indexname"] for r in righe}
    assert {"idx_global_ban_log_attivi_utente", "idx_global_ban_log_attivi_sorgente", "idx_global_ban_log_creazione"} <= nomi


async def test_propagazione_annullata_non_lascia_un_ban_senza_riga(ambiente):
    a, b = _server(1), _server(2)
    ambiente.update({1, 2})
    attesa = asyncio.Event()

    async def lento(*_a, **_k):
        await attesa.wait()

    b.ban.side_effect = lento
    compito = asyncio.create_task(modulo.propagate_ban(_bot(a, b), a, USER, "x"))
    await asyncio.sleep(0.05)
    compito.cancel()
    attesa.set()
    await asyncio.gather(compito, return_exceptions=True)
    await asyncio.sleep(0.05)

    b.ban.assert_awaited_once()
    assert await global_ban_repo.active_propagations(1, USER) == [2]  # il ban e la sua riga vanno insieme


# ---------------------------------------------------------------- /modban unban
async def test_modban_unban_toglie_anche_i_ban_propagati(monkeypatch):
    import cogs.moderation.actions as actions

    ordine = []
    monkeypatch.setattr(actions, "ensure_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(actions, "validate_reason", AsyncMock(return_value=True))
    monkeypatch.setattr(actions, "post_to_mod_log", AsyncMock())
    repo = MagicMock()
    repo.get_latest_active_case = AsyncMock(return_value=None)
    repo.get_tempban_state = AsyncMock(return_value=None)
    repo.cancel_tempban_jobs = AsyncMock()
    repo.close_open_appeals = AsyncMock()
    repo.revoke_active_cases_for_user = AsyncMock()
    monkeypatch.setattr(actions, "moderation_repo", repo)

    async def revoca(client, guild_id, user_id):
        ordine.append("revoca")
        return 2

    monkeypatch.setattr(actions, "revoca_ban_propagati", revoca)
    server = fake_guild(guild_id=1)
    server.unban = AsyncMock()
    interazione = fake_interaction(guild=server)
    interazione.response.send_message.side_effect = lambda *a, **k: ordine.append("risposta")
    interazione.followup.send.side_effect = lambda *a, **k: ordine.append("avviso")
    cog = actions.ModerationActionsCog(bot=None)

    await cog.unban.callback(cog, interazione, "4242", "appello accolto")

    # Prima si risponde (3 secondi), poi si tolgono i ban dagli altri server.
    assert ordine == ["risposta", "revoca", "avviso"]
