"""
tests/test_moderation_caso_note_warn.py
=======================================
Case system esteso: storico per tipo, motivo e eliminazione dei casi,
classifica staff, note (togli, cambia, svuota), warn (togli, azzera,
classifica). Database vero.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation._shared import MODULE_CASE_SYSTEM, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.case_system import ModerationCaseSystemCog
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G = 100


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, 7001)
    yield
    database_module.db._modules_cache.clear()


def _inter(gestione=False):
    server = fake_guild(G)
    canale_log = fake_text_channel(7001)
    canale_log.send = AsyncMock()
    server.get_channel.return_value = canale_log
    permessi = discord.Permissions(manage_guild=gestione)
    mod = fake_member(10, guild_permissions=permessi)
    return fake_interaction(guild=server, user=mod), canale_log


def _testo(inter):
    chiamata = inter.response.send_message.call_args
    return chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")


async def _casi():
    await moderation_repo.create_case(G, 1, 10, "warn", "uno")
    await moderation_repo.create_case(G, 1, 10, "ban", "due")
    await moderation_repo.create_case(G, 1, 11, "warn", "tre")
    await moderation_repo.create_case(G, 2, 10, "warn", "quattro")


async def test_storico_filtrato_per_tipo():
    await _casi()
    inter, _ = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    membro = fake_member(1)
    membro.display_avatar = MagicMock(url="https://x/y.png")
    scelta = MagicMock(value="warn")

    await cog.history.callback(cog, inter, membro, scelta)

    descr = inter.response.send_message.call_args.kwargs["embed"].description
    assert "warn" in descr and "ban" not in descr.replace("banner", "")


async def test_motivo_cambiato_e_loggato():
    await _casi()
    inter, log = _inter()
    cog = ModerationCaseSystemCog(bot=None)

    await cog.case_reason.callback(cog, inter, 1, "Motivo nuovo valido")

    assert (await moderation_repo.get_case(G, 1)).reason == "Motivo nuovo valido"
    log.send.assert_awaited()
    await cog.case_reason.callback(cog, inter, 99, "Motivo nuovo valido")
    assert "Nessun caso" in _testo(inter)


async def test_elimina_caso_solo_con_gestione():
    await _casi()
    inter, _ = _inter(gestione=False)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.case_delete.callback(cog, inter, 1)
    assert await moderation_repo.get_case(G, 1) is not None
    assert "Gestire il server" in _testo(inter)

    inter, _ = _inter(gestione=True)
    await cog.case_delete.callback(cog, inter, 1)
    assert await moderation_repo.get_case(G, 1) is None


async def test_classifica_staff_e_casi_del_moderatore():
    await _casi()
    assert await moderation_repo.moderator_ranking(G) == [(10, 3), (11, 1)]
    assert [c.case_number for c in await moderation_repo.list_cases_by_moderator(G, 10, action_type="warn")] == [4, 1]


async def test_note_togli_modifica_svuota():
    n1 = await moderation_repo.add_note(G, 1, 10, "prima")
    n2 = await moderation_repo.add_note(G, 1, 10, "seconda")
    cog = ModerationCaseSystemCog(bot=None)
    inter, _ = _inter()

    await cog.note_edit.callback(cog, inter, n1, "cambiata")
    assert [n.note for n in await moderation_repo.list_notes_for_user(G, 1)] == ["seconda", "cambiata"]
    await cog.note_remove.callback(cog, inter, n2)
    assert len(await moderation_repo.list_notes_for_user(G, 1)) == 1
    # Una nota di un altro server non si tocca.
    assert await moderation_repo.delete_note(999, n1) is False

    senza, _ = _inter(gestione=False)
    await cog.note_clear.callback(cog, senza, fake_member(1))
    assert len(await moderation_repo.list_notes_for_user(G, 1)) == 1
    con, _ = _inter(gestione=True)
    await cog.note_clear.callback(cog, con, fake_member(1))
    assert await moderation_repo.list_notes_for_user(G, 1) == []


async def test_elenco_note_mostra_il_numero():
    n = await moderation_repo.add_note(G, 1, 10, "ciao")
    inter, _ = _inter()
    membro = fake_member(1)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.note_list.callback(cog, inter, membro)
    assert f"#{n}" in inter.response.send_message.call_args.kwargs["embed"].description


async def test_warn_togli_azzera_classifica():
    await _casi()
    cog = ModerationCaseSystemCog(bot=None)
    inter, _ = _inter()

    await cog.warn_remove.callback(cog, inter, 2)  # e' un ban
    assert "non è un warn" in _testo(inter)
    await cog.warn_remove.callback(cog, inter, 1)
    assert (await moderation_repo.get_case(G, 1)).active is False
    assert await moderation_repo.warn_ranking(G) == [(1, 1), (2, 1)]

    senza, _ = _inter()
    await cog.warn_reset.callback(cog, senza, fake_member(1))
    assert (await moderation_repo.get_case(G, 3)).active is True
    con, _ = _inter(gestione=True)
    await cog.warn_reset.callback(cog, con, fake_member(1))
    assert (await moderation_repo.get_case(G, 3)).active is False


def test_numeri_di_caso_e_nota_hanno_il_tetto_del_database():
    """Oltre 2^31-1 Postgres darebbe DataError: il limite sta nel comando."""
    import typing

    cog = ModerationCaseSystemCog
    visti = 0
    for nome in dir(cog):
        comando = getattr(cog, nome)
        if not hasattr(comando, "callback"):
            continue
        for parametro, tipo in typing.get_type_hints(comando.callback).items():
            if parametro in ("case_number", "nota_id"):
                visti += 1
                assert tipo.max_value == 2**31 - 1 and tipo.min_value == 1, (nome, parametro)
    assert visti >= 6


async def test_le_query_del_repo_non_toccano_un_altro_server():
    """Ogni query filtra per server: stesso numero in un altro server = niente."""
    ALTRO = 999
    numero = await moderation_repo.create_case(G, 1, 10, "warn", "uno")
    nota = await moderation_repo.add_note(G, 1, 10, "nota")

    assert not await moderation_repo.update_case_reason(ALTRO, numero, "cambiato")
    assert not await moderation_repo.delete_case(ALTRO, numero)
    assert not await moderation_repo.update_note(ALTRO, nota, "cambiata")
    assert not await moderation_repo.delete_note(ALTRO, nota)
    assert await moderation_repo.delete_notes_for_user(ALTRO, 1) == 0
    assert await moderation_repo.list_cases_by_moderator(ALTRO, 10) == []
    assert await moderation_repo.moderator_ranking(ALTRO) == []

    caso = await moderation_repo.get_case(G, numero)
    assert caso is not None and caso.reason == "uno"
    assert len(await moderation_repo.list_notes_for_user(G, 1)) == 1


# ------------------------------------------------------- caso registrato a mano
async def test_caso_registrato_a_mano_entra_nello_storico_senza_agire():
    inter, canale_log = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    utente = MagicMock(id=555)
    scelta = MagicMock(value="ban")
    scelta.name = "Ban"

    await cog.case_register.callback(cog, inter, utente, scelta, "ban dato da un altro bot")

    [caso] = await moderation_repo.list_cases_for_user(G, 555)
    assert (caso.action_type, caso.moderator_id, caso.active) == ("ban", 10, True)
    assert "registrato a mano" in inter.response.send_message.call_args.kwargs["embed"].title
    canale_log.send.assert_awaited_once()


async def test_caso_a_nome_di_un_altro_serve_gestire_il_server():
    inter, _ = _inter(gestione=False)
    cog = ModerationCaseSystemCog(bot=None)
    scelta = MagicMock(value="kick")
    await cog.case_register.callback(cog, inter, MagicMock(id=555), scelta, "kick fuori bot", fake_member(77))
    assert await moderation_repo.list_cases_for_user(G, 555) == []
    assert "Gestire il server" in _testo(inter)

    inter, _ = _inter(gestione=True)
    await cog.case_register.callback(cog, inter, MagicMock(id=555), scelta, "kick fuori bot", fake_member(77))
    [caso] = await moderation_repo.list_cases_for_user(G, 555)
    assert caso.moderator_id == 77
