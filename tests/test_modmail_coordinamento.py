# ruff: noqa: F811
"""
tests/test_modmail_coordinamento.py
===================================
ModMail: un solo gestore per DM (Spam Trap vs ModMail), nessun messaggio perso,
blacklist, controlli rifatti nel menu, transcript e eliminazione.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.modmail_repo import modmail_repo
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel
from tests.test_modmail import (  # noqa: F401, F811
    ID_ALTRO_SERVER,
    ID_CATEGORIA,
    ID_SERVER,
    ID_UTENTE,
    Scena,
    _ambiente,
    scena,
)


def _testi(canale):
    return [
        c.kwargs["embed"].description
        for c in canale.send.await_args_list
        if c.kwargs.get("embed") and c.kwargs["embed"].description
    ]


async def _due_server(scena):
    await scena.configura()
    altro = Scena._server(ID_ALTRO_SERVER, "Server due")
    altro.get_member.side_effect = lambda uid: scena.utente
    altro.get_channel.side_effect = scena.guild.get_channel.side_effect
    await _imposta_altra_categoria()
    scena.bot.guilds = [scena.guild, altro]


async def _imposta_altra_categoria():
    await modmail_repo.imposta_categoria(ID_ALTRO_SERVER, ID_CATEGORIA)


# ---------- un solo gestore per DM
async def test_chi_ha_un_ban_dello_spam_trap_non_apre_un_modmail_e_l_appello_non_arriva_allo_staff_di_un_altro_server(scena):
    await scena.configura()
    caso = SimpleNamespace(guild_id=555, case_number=7, user_id=ID_UTENTE, created_at=datetime.now(timezone.utc))
    scena.bot.get_guild = lambda gid: fake_guild(555) if gid == 555 else None
    m = scena.dm("Mi hanno bannato per errore, sono Mario Rossi, mario@example.com")
    with patch.object(
        modulo_moderation(), "get_active_cases_for_user_across_guilds", AsyncMock(return_value=[caso])
    ):
        await scena.cog.on_message(m)
    assert scena.canali == []
    m.channel.send.assert_not_awaited()  # nessuna seconda risposta: risponde solo l'altro cog
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None


def modulo_moderation():
    import cogs.tickets.modmail as modulo

    return modulo.moderation_repo


async def test_senza_ban_il_dm_va_al_modmail(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm("ciao"))
    assert len(scena.canali) == 1


async def test_ban_in_un_server_che_il_bot_non_vede_non_blocca_il_modmail(scena):
    await scena.configura()
    caso = SimpleNamespace(guild_id=555)
    scena.bot.get_guild = lambda gid: None
    with patch.object(modulo_moderation(), "get_active_cases_for_user_across_guilds", AsyncMock(return_value=[caso])):
        await scena.cog.on_message(scena.dm("ciao"))
    assert len(scena.canali) == 1


# ---------- blacklist
async def test_utente_in_blacklist_non_apre_il_modmail(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await blacklist_repo.add_user(ID_UTENTE, "abuso", 1)
    try:
        await scena.cog.on_message(scena.dm("spam"))
        assert scena.canali == [] and await modmail_repo.aperta_dell_utente(ID_UTENTE) is None
    finally:
        await blacklist_repo.remove_user(ID_UTENTE)


# ---------- messaggi non persi
async def test_due_dm_insieme_arrivano_tutti_e_due_in_ordine(scena, clean_db):
    await apri_connessioni(clean_db, 4)
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    a, b = scena.dm("PRIMO"), scena.dm("SECONDO")
    await asyncio.gather(scena.cog.on_message(a), scena.cog.on_message(b))
    assert len(scena.canali) == 1
    testi = [t for t in _testi(scena.canali[0]) if t in ("PRIMO", "SECONDO")]
    assert testi == ["PRIMO", "SECONDO"]


async def test_secondo_menu_non_perde_il_messaggio_ma_avvisa(scena):
    await _due_server(scena)
    scena.bot.get_guild = lambda gid: None
    m1, m2 = scena.dm("domanda uno"), scena.dm("domanda due")
    await scena.cog.on_message(m1)
    await scena.cog.on_message(m2)
    assert m1.channel.send.await_args.kwargs.get("view") is not None
    assert "domanda" in m2.channel.send.await_args.args[0]  # avviso, non silenzio e non secondo menu
    assert "view" not in m2.channel.send.await_args.kwargs


async def test_scelta_dal_menu_dopo_un_blocco_non_apre(scena):
    await _due_server(scena)
    scena.bot.get_guild = lambda gid: None
    m = scena.dm("ciao")
    await scena.cog.on_message(m)
    v = m.channel.send.await_args.kwargs["view"]
    await modmail_repo.blocca(ID_SERVER, ID_UTENTE, 30)
    i = fake_interaction(user=scena.utente)
    i.data = {"values": [str(ID_SERVER)]}
    await v._scelto(i)
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None
    assert scena.canali == []


async def test_scelta_dal_menu_con_conversazione_gia_aperta_inoltra_al_thread_esistente(scena):
    await _due_server(scena)
    scena.bot.get_guild = lambda gid: None
    m = scena.dm("domanda uno")
    await scena.cog.on_message(m)
    v = m.channel.send.await_args.kwargs["view"]
    # intanto una conversazione si apre da un'altra strada
    canale = fake_text_channel(3000, "modmail-x")
    scena.canali.append(canale)
    await modmail_repo.crea(ID_SERVER, ID_UTENTE, 3000)
    i = fake_interaction(user=scena.utente)
    i.data = {"values": [str(ID_SERVER)]}
    await v._scelto(i)
    assert "domanda uno" in _testi(canale)


async def test_canale_cancellato_a_mano_il_messaggio_riparte_da_capo(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm("primo"))
    vecchio = scena.canali[0]
    scena.bot.get_channel = lambda cid: None  # il canale non c'è più
    scena.bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404, reason="x"), "x"))
    scena.cog._limitatore = MagicMock(consenti=MagicMock(return_value=True))
    await scena.cog.on_message(scena.dm("secondo"))
    assert len(scena.canali) == 2 and "secondo" in _testi(scena.canali[1])
    nuovo = await modmail_repo.aperta_dell_utente(ID_UTENTE)
    assert nuovo.channel_id == scena.canali[1].id != vecchio.id


# ---------- transcript ed eliminazione
async def test_l_eliminazione_aspetta_il_transcript(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm())
    canale = scena.canali[0]
    fermo = asyncio.Event()

    async def lenta(**kw):
        yield SimpleNamespace(created_at=datetime.now(timezone.utc), author="x", content="m0", embeds=[], attachments=[])
        await fermo.wait()

    canale.history = lenta
    canale.delete = AsyncMock()
    scena.bot.fetch_channel = AsyncMock(return_value=canale)
    thread = await modmail_repo.aperta_del_canale(canale.id)
    chiusura = asyncio.create_task(scena.cog._chiudi(scena.guild, canale, thread, 30, "fine", avvisa_utente=False))
    await asyncio.sleep(0.2)
    await scena.cog.handle_modmail_delete_channel(ID_SERVER, ID_UTENTE, {"channel_id": canale.id, "reason": "x"})
    assert canale.delete.await_count == 0  # rimandato dallo scheduler
    fermo.set()
    await chiusura


async def test_il_transcript_distingue_utente_e_staff(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm("la mia email"))
    canale = scena.canali[0]
    bot = SimpleNamespace(bot=True, __str__=lambda s: "Yokai Bot#0001")

    def msg(autore, testo):
        e = SimpleNamespace(description=testo, author=SimpleNamespace(name=autore))
        return SimpleNamespace(
            created_at=datetime.now(timezone.utc), author=bot, content="", embeds=[e], attachments=[]
        )

    async def h(**kw):
        yield msg("Mario Rossi", "la mia email")
        yield msg("Giulia → utente", "ok")

    canale.history = h
    thread = await modmail_repo.aperta_del_canale(canale.id)
    assert await scena.cog._transcript_al_log(scena.guild, canale, thread) is True
    testo = scena.log.send.await_args.kwargs["file"].fp.read().decode()
    assert "Mario Rossi" in testo and "Giulia" in testo and "Yokai Bot" not in testo


async def test_senza_canale_log_il_comando_lo_dice(scena):
    from cogs.tickets import modmail as modulo

    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm())
    canale = scena.canali[0]
    async def h(**kw):
        return
        yield
    canale.history = h
    with patch.object(modulo.router, "destinazione", AsyncMock(return_value=None)):
        i = scena.staff(canale)
        await scena.cog.dm_chiudi.callback(scena.cog, i)
    assert "transcript non è stato salvato" in i.followup.send.call_args.args[0]


# ====================================================================
# Giro del capo: scadenza dei menu, conferma del primo DM, chiusura sicura
# ====================================================================
import pytest  # noqa: E402


async def _primo_dm_con_menu(scena):
    await _due_server(scena)
    scena.bot.get_guild = lambda gid: None
    scena.cog._limitatore = MagicMock(consenti=MagicMock(return_value=True))
    m = scena.dm("uno")
    await scena.cog.on_message(m)
    return m, m.channel.send.await_args.kwargs["view"]


async def test_menu_scaduto_non_blocca_piu_l_utente(scena):
    m, vista = await _primo_dm_con_menu(scena)
    assert ID_UTENTE in scena.cog._menu_aperti
    await vista.on_timeout()
    assert ID_UTENTE not in scena.cog._menu_aperti
    m2 = scena.dm("riprovo")
    await scena.cog.on_message(m2)
    assert isinstance(m2.channel.send.await_args.kwargs.get("view"), modulo_view())  # il menu torna


def modulo_view():
    import cogs.tickets.modmail as modulo

    return modulo.SceltaServerView


async def test_se_la_scelta_dal_menu_solleva_l_utente_non_resta_bloccato(scena):
    m, vista = await _primo_dm_con_menu(scena)
    i = fake_interaction(user=scena.utente)
    i.data = {"values": [str(ID_SERVER)]}
    i.response.edit_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500, reason="x"), "x"))
    with pytest.raises(discord.HTTPException):
        await vista._scelto(i)
    assert ID_UTENTE not in scena.cog._menu_aperti


async def test_con_un_solo_server_il_primo_dm_chiede_conferma_e_non_crea_nulla(scena):
    import cogs.tickets.modmail as modulo

    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    scena.auto_conferma = False
    m = scena.dm("ciao")
    await scena.cog.on_message(m)
    assert "Server uno" in m.channel.send.await_args.args[0]
    vista = m.channel.send.await_args.kwargs["view"]
    assert isinstance(vista, modulo.ConfermaInvioView)
    assert scena.canali == [] and await modmail_repo.aperta_dell_utente(ID_UTENTE) is None
    await vista.invia.callback(fake_interaction(user=scena.utente))
    assert len(scena.canali) == 1 and "ciao" in _testi(scena.canali[0])


async def test_annulla_non_invia_nulla_e_libera_l_utente(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    scena.auto_conferma = False
    m = scena.dm("ciao")
    await scena.cog.on_message(m)
    vista = m.channel.send.await_args.kwargs["view"]
    await vista.annulla.callback(fake_interaction(user=scena.utente))
    assert scena.canali == [] and ID_UTENTE not in scena.cog._menu_aperti


async def test_conferma_scaduta_libera_l_utente_e_un_altro_non_puo_premere(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    scena.auto_conferma = False
    m = scena.dm("ciao")
    await scena.cog.on_message(m)
    vista = m.channel.send.await_args.kwargs["view"]
    intruso = fake_interaction(user=SimpleNamespace(id=999))
    await vista.invia.callback(intruso)
    assert scena.canali == []
    await vista.on_timeout()
    assert ID_UTENTE not in scena.cog._menu_aperti


async def test_dopo_la_conferma_i_dm_successivi_non_chiedono_piu_nulla(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    scena.cog._limitatore = MagicMock(consenti=MagicMock(return_value=True))
    await scena.cog.on_message(scena.dm("uno"))
    m2 = scena.dm("due")
    await scena.cog.on_message(m2)
    assert len(scena.canali) == 1 and "due" in _testi(scena.canali[0])


async def test_scelta_dal_menu_ricontrolla_appello_e_blacklist(scena):
    m, vista = await _primo_dm_con_menu(scena)
    await blacklist_repo.add_user(ID_UTENTE, "abuso", 1)
    try:
        i = fake_interaction(user=scena.utente)
        i.data = {"values": [str(ID_SERVER)]}
        await vista._scelto(i)
        assert scena.canali == []
    finally:
        await blacklist_repo.remove_user(ID_UTENTE)


async def test_scelta_dal_menu_con_appello_aperto_non_apre(scena):
    from unittest.mock import patch

    m, vista = await _primo_dm_con_menu(scena)
    caso = SimpleNamespace(guild_id=555)
    scena.bot.get_guild = lambda gid: fake_guild(555) if gid == 555 else None
    with patch.object(modulo_moderation(), "get_active_cases_for_user_across_guilds", AsyncMock(return_value=[caso])):
        i = fake_interaction(user=scena.utente)
        i.data = {"values": [str(ID_SERVER)]}
        await vista._scelto(i)
    assert scena.canali == []


async def test_chiusura_doppia_ne_vince_una_sola(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm())
    canale = scena.canali[0]

    async def vuota(**kw):
        return
        yield

    canale.history = vuota
    thread = await modmail_repo.aperta_del_canale(canale.id)
    assert await scena.cog._chiudi(scena.guild, canale, thread, 30, "a", avvisa_utente=False) is True
    assert await scena.cog._chiudi(scena.guild, canale, thread, 30, "b", avvisa_utente=False) is False
    assert scena.log.send.await_count == 1


async def test_se_lo_scheduler_fallisce_la_conversazione_si_riapre(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm())
    canale = scena.canali[0]
    thread = await modmail_repo.aperta_del_canale(canale.id)
    scena.scheduler.schedule = AsyncMock(side_effect=RuntimeError("db giù"))
    with pytest.raises(RuntimeError):
        await scena.cog._chiudi(scena.guild, canale, thread, 30, "fine", avvisa_utente=False)
    riaperta = await modmail_repo.aperta_del_canale(canale.id)
    assert riaperta is not None and riaperta.close_reason is None


async def test_canale_doppio_viene_eliminato(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    # una conversazione si apre "da un'altra strada" mentre il canale nasce
    originale = scena.categoria.create_text_channel.side_effect

    async def crea_e_apri_altrove(name, **kw):
        c = await originale(name, **kw)
        await modmail_repo.crea(ID_SERVER, ID_UTENTE, 4000)
        return c

    scena.categoria.create_text_channel.side_effect = crea_e_apri_altrove
    altro = fake_text_channel(4000, "gia-aperto")
    scena.canali.append(altro)
    await scena.cog.on_message(scena.dm("ciao"))
    nuovo = [c for c in scena.canali if c.id != 4000][0]
    nuovo.delete.assert_awaited_once()
    assert "ciao" in _testi(altro)


async def test_rispondi_fa_defer_per_primo(scena):
    await scena.configura()
    scena.bot.get_guild = lambda gid: None
    await scena.cog.on_message(scena.dm())
    i = scena.staff(scena.canali[0])
    ordine = []
    i.response.defer = AsyncMock(side_effect=lambda *a, **k: ordine.append("defer"))
    scena.utente.send = AsyncMock(side_effect=lambda *a, **k: ordine.append("dm"))
    await scena.cog.rispondi.callback(scena.cog, i, "ciao", False)
    assert ordine == ["defer", "dm"]


async def test_oblio_di_due_utenti_con_conversazione_aperta(clean_db):
    from core.forget_user_service import dimentica_utente

    await modmail_repo.crea(ID_SERVER, 71, 7001)
    await modmail_repo.crea(ID_SERVER, 72, 7002)
    await dimentica_utente(clean_db, 71)
    await dimentica_utente(clean_db, 72)
    assert await clean_db.fetchval("SELECT count(*) FROM modmail_threads WHERE user_id = 0") == 2
