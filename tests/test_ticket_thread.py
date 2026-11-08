"""
tests/test_ticket_thread.py
===========================
#156 (D66, T5): ticket come thread privati (TKT-031) con avviso e bottone «Entra» (TKT-032).
Regole pure, opzioni nel database e cog con Discord finto.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.tickets.tickets as modulo
from core import ticket_opzioni_logic as opz
from core import ticket_thread_logic as tl
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import fake_interaction, fake_member, fake_text_channel

GUILD = 100


# ====================================================================
# Regole pure
# ====================================================================
def test_nome_del_thread_sta_in_100_caratteri_e_non_e_vuoto():
    assert tl.nome_thread("a" * 150) == "a" * 100
    assert tl.nome_thread("   ") == "ticket"


def test_tetto_dei_thread_attivi():
    assert not tl.tetto_raggiunto(999) and tl.tetto_raggiunto(1000)


def test_permessi_del_bot_nel_canale_padre():
    ok = SimpleNamespace(view_channel=True, create_private_threads=True, send_messages_in_threads=True, manage_threads=True)
    assert tl.permessi_mancanti(ok) == []
    manca = SimpleNamespace(view_channel=True, create_private_threads=False, send_messages_in_threads=True, manage_threads=False)
    assert tl.permessi_mancanti(manca) == ["Creare thread privati", "Gestire i thread"]


def test_chi_entra_subito_senza_doppioni_e_con_tetto():
    assert tl.chi_aggiungere(1, [2, 1, 3, 2]) == [1, 2, 3]
    assert len(tl.chi_aggiungere(1, list(range(2, 50)))) == 11


# ====================================================================
# Opzioni nel database
# ====================================================================
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    ticket_opzioni_repo._cache.clear()
    yield


async def test_le_opzioni_dei_thread_si_salvano_e_si_leggono():
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 900, "Supporto")
    assert (await ticket_opzioni_repo.opzioni(p.id)).tipo == "canale"
    o = await ticket_opzioni_repo.imposta(p.id, tipo="thread", canale_padre_id=500, canale_avvisi_id=501)
    assert (o.tipo, o.canale_padre_id, o.canale_avvisi_id) == ("thread", 500, 501)
    assert "thread privati in <#500>" in dict(opz.riassunto(o))["Canale"]
    with pytest.raises(Exception):
        await ticket_opzioni_repo.imposta(p.id, tipo="forum")


async def test_il_flag_e_thread_si_scrive_sul_ticket():
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 900, "Supporto")
    await ticket_repo.create_ticket(GUILD, 20, 5001, panel_id=p.id, ticket_number=1)
    assert not (await ticket_repo.get_ticket_by_channel(5001)).e_thread
    assert await ticket_repo.set_e_thread(5001, True)
    assert (await ticket_repo.get_ticket_by_channel(5001)).e_thread


# ====================================================================
# Cog con Discord finto
# ====================================================================
def _padre(permessi_ok=True):
    padre = create_autospec(discord.TextChannel, instance=True)
    padre.id = 500
    perm = SimpleNamespace(view_channel=True, create_private_threads=permessi_ok, send_messages_in_threads=True, manage_threads=True)
    padre.permissions_for.return_value = perm
    padre.mention = "<#500>"
    thread = create_autospec(discord.Thread, instance=True)
    thread.id = 7001
    thread.mention = "<#7001>"
    padre.create_thread = AsyncMock(return_value=thread)
    return padre, thread


def _guild(padre, n_thread=0):
    return SimpleNamespace(id=GUILD, me=object(), threads=[object()] * n_thread,
                           get_channel=lambda i: padre if i == padre.id else None)


OPZ = opz.Opzioni(tipo="thread", canale_padre_id=500)


async def test_il_thread_nasce_privato_non_invitabile_e_con_archivio_lungo():
    padre, thread = _padre()
    creato, errore = await modulo._crea_thread_privato(_guild(padre), OPZ, "ticket-0001", "motivo")
    assert creato is thread and errore is None
    k = padre.create_thread.await_args.kwargs
    assert k["type"] == discord.ChannelType.private_thread and k["invitable"] is False
    assert k["auto_archive_duration"] == 10080 and k["name"] == "ticket-0001"


async def test_thread_non_si_crea_con_tetto_permessi_o_padre_mancanti():
    padre, _ = _padre()
    assert await modulo._crea_thread_privato(_guild(padre, 1000), OPZ, "n", "m") == (None, "tickets_thread_troppi")
    padre, _ = _padre(permessi_ok=False)
    assert await modulo._crea_thread_privato(_guild(padre), OPZ, "n", "m") == (None, "tickets_thread_permessi")
    padre.create_thread.assert_not_awaited()
    assert await modulo._crea_thread_privato(_guild(padre), opz.Opzioni(tipo="thread", canale_padre_id=999), "n", "m") == (
        None, "tickets_thread_padre_mancante")


async def test_entrano_utente_e_reperibili_e_un_errore_non_ferma_gli_altri():
    _, thread = _padre()
    thread.add_user = AsyncMock(side_effect=[discord.HTTPException(MagicMock(status=403), "no"), None])
    await modulo._entrano_nel_thread(thread, [20, 30])
    assert thread.add_user.await_count == 2


async def test_avviso_allo_staff_ha_il_bottone_entra_nel_canale_avvisi():
    padre, thread = _padre()
    avvisi = fake_text_channel(501, "avvisi")
    avvisi.send = AsyncMock()
    guild = SimpleNamespace(id=GUILD, get_channel=lambda i: {500: padre, 501: avvisi}.get(i))
    utente = SimpleNamespace(mention="<@20>")
    await modulo._avviso_thread_allo_staff(guild, thread, opz.Opzioni(tipo="thread", canale_padre_id=500, canale_avvisi_id=501), utente, 1)
    k = avvisi.send.await_args.kwargs
    bottone = k["view"].children[0]
    assert bottone.item.custom_id == "tkt:ent:7001" and len(bottone.item.label) <= 45
    assert "<#7001>" in k["embed"].description


async def test_bottone_entra_solo_per_lo_staff(monkeypatch):
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 900, "Supporto")
    await ticket_repo.create_ticket(GUILD, 20, 7001, panel_id=p.id, ticket_number=1)
    _, thread = _padre()
    thread.add_user = AsyncMock()
    i = fake_interaction()
    i.guild = SimpleNamespace(id=GUILD, get_thread=lambda t: thread, fetch_channel=AsyncMock(return_value=thread))
    bottone = modulo.BottoneEntra(7001)
    monkeypatch.setattr(modulo, "_is_ticket_staff", AsyncMock(return_value=False))
    await bottone.callback(i)
    thread.add_user.assert_not_awaited()
    monkeypatch.setattr(modulo, "_is_ticket_staff", AsyncMock(return_value=True))
    await bottone.callback(i)
    thread.add_user.assert_awaited_once_with(i.user)
    assert "<#7001>" in i.followup.send.await_args.args[0]


def test_il_bottone_entra_si_riconosce_dal_custom_id():
    assert modulo.BottoneEntra.__discord_ui_compiled_template__.match("tkt:ent:7001")
    assert len("tkt:ent:" + "9" * 20) <= 100


async def test_chiusura_in_due_passi_toglie_l_utente_dal_thread_e_riapri_lo_rimette():
    _, thread = _padre()
    thread.__class__ = discord.Thread
    thread.remove_user = AsyncMock()
    ticket = SimpleNamespace(user_id=20, panel_id=None)
    cog = modulo.TicketsCog.__new__(modulo.TicketsCog)
    assert await cog._nascondi_ai_non_staff(SimpleNamespace(id=GUILD), thread, ticket, opz.Opzioni()) == 0
    thread.remove_user.assert_awaited_once()
    assert thread.remove_user.await_args.args[0].id == 20


async def test_thread_archiviato_da_discord_si_riapre_se_il_ticket_e_aperto():
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 900, "Supporto")
    await ticket_repo.create_ticket(GUILD, 20, 7001, panel_id=p.id, ticket_number=1)
    await ticket_repo.set_e_thread(7001, True)
    prima, dopo = MagicMock(archived=False), MagicMock(archived=True, locked=False, id=7001)
    dopo.edit = AsyncMock()
    cog = modulo.TicketsCog.__new__(modulo.TicketsCog)
    await cog.on_thread_update(prima, dopo)
    dopo.edit.assert_awaited_once()
    dopo.edit.reset_mock()
    await ticket_repo.close_ticket_of_deleted_channel(7001)  # ticket chiuso: il thread resta archiviato
    await cog.on_thread_update(prima, dopo)
    dopo.edit.assert_not_awaited()


async def test_thread_cancellato_a_mano_chiude_il_ticket():
    """Discord non manda on_guild_channel_delete per i thread: prima il ticket restava aperto per sempre."""
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 900, "Supporto")
    await ticket_repo.create_ticket(GUILD, 20, 7001, panel_id=p.id, ticket_number=1)
    cog = modulo.TicketsCog.__new__(modulo.TicketsCog)
    cog._attivita_scritta = {}
    await cog.on_raw_thread_delete(SimpleNamespace(thread_id=7001, guild_id=GUILD))
    assert (await ticket_repo.get_ticket_by_channel(7001)).status == "closed"


async def test_chiusura_di_massa_e_uscita_dell_utente_trovano_i_thread():
    """`guild.get_channel` non vede i thread: prima la chiusura di massa li segnava «cancellati» senza chiuderli."""
    p = await ticket_form_repo.crea_pannello(GUILD, "Supporto", 900, "Supporto")
    await ticket_repo.create_ticket(GUILD, 20, 7001, panel_id=p.id, ticket_number=1)
    thread = create_autospec(discord.Thread, instance=True)
    thread.id = 7001
    interaction = fake_interaction()
    interaction.guild.id = GUILD
    interaction.guild.get_channel = MagicMock(return_value=None)
    interaction.guild.get_channel_or_thread = MagicMock(side_effect={7001: thread}.get)
    cog = modulo.TicketsCog.__new__(modulo.TicketsCog)
    cog._chiudi_da_sistema = AsyncMock(return_value=True)
    await modulo.TicketsCog.chiudi_tutti.callback(cog, interaction, None)
    assert cog._chiudi_da_sistema.await_args.args[1] is thread
    cog._chiudi_da_sistema.reset_mock()
    membro = SimpleNamespace(id=20, guild=interaction.guild)
    await cog.on_member_remove(membro)
    assert cog._chiudi_da_sistema.await_args.args[1] is thread
