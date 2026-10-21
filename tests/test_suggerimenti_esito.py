"""
tests/test_suggerimenti_esito.py
================================
Catalogo #128: stati "in valutazione" e "realizzato" (UTL-135), motivo
dello staff (UTL-136), DM a chi propone (UTL-137), canale dei decisi
(UTL-138). Archivio su PostgreSQL vero, cog con oggetti finti.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.suggestions as sg
from cogs.utility.suggestions import MotivoModal, SuggestionsCog
from core.repositories.suggestion_repo import SuggestionRepository
from core.suggestion_logic import APPROVED, CONSIDERING, IMPLEMENTED, REJECTED, can_decide, e_finale
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel


def _staff(user_id=10):
    return fake_member(user_id=user_id, guild_permissions=discord.Permissions(manage_guild=True))


@pytest.fixture
def repo(clean_db, monkeypatch):
    r = SuggestionRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(sg, "suggestion_repo", r)
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=None))
    return r


def test_stati_aperti_e_finali():
    assert can_decide(CONSIDERING) and not can_decide(IMPLEMENTED)
    assert e_finale(APPROVED) and e_finale(IMPLEMENTED) and not e_finale(CONSIDERING)


@pytest.mark.asyncio
async def test_in_valutazione_poi_realizzato_con_motivo(repo):
    sid = await repo.create_suggestion(1, 2, 3, "idea")
    ora = datetime.now(timezone.utc)
    assert await repo.set_status(sid, CONSIDERING, decided_by=10, decided_at=ora, motivo="ci pensiamo")
    assert [s.id for s in await repo.list_pending(1)] == [sid]  # resta aperto: i bottoni tornano all'avvio
    assert await repo.set_status(sid, IMPLEMENTED, decided_by=11, decided_at=ora, motivo="fatto!")
    s = await repo.get_suggestion(sid)
    assert s.status == IMPLEMENTED and s.decision_reason == "fatto!"
    assert await repo.set_status(sid, REJECTED, decided_by=12, decided_at=ora) is False


@pytest.mark.asyncio
async def test_bottone_apre_la_finestra_del_motivo_solo_per_lo_staff():
    cog = SuggestionsCog(bot=MagicMock())
    vista = cog._build_decision_view(5)
    assert len(vista.children) == 4
    approva = vista.children[0]
    it = fake_interaction(user=_staff())
    await approva.callback(it)
    finestra = it.response.send_modal.await_args.args[0]
    assert isinstance(finestra, MotivoModal) and finestra.stato == APPROVED
    membro = fake_interaction(user=fake_member(20))
    await approva.callback(membro)
    membro.response.send_modal.assert_not_awaited()


@pytest.mark.asyncio
async def test_decisione_finale_avvisa_autore_e_copia_nei_decisi(repo, monkeypatch):
    sid = await repo.create_suggestion(1, 2, 3, "idea")
    server = fake_guild(guild_id=1)
    autore = fake_member(3)
    decisi = fake_text_channel(77)
    decisi.send = AsyncMock()
    server.get_member = MagicMock(return_value=autore)
    server.get_channel = MagicMock(return_value=decisi)
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=77))
    cog = SuggestionsCog(bot=MagicMock())
    it = fake_interaction(guild=server, user=_staff())
    await cog._handle_decision(it, sid, REJECTED, "fuori tema")
    embed = it.response.edit_message.await_args.kwargs["embed"]
    assert {f.name: f.value for f in embed.fields}["Motivo"] == "fuori tema"
    assert it.response.edit_message.await_args.kwargs["view"].children == []
    assert "fuori tema" in autore.send.await_args.args[0]
    decisi.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_in_valutazione_lascia_i_bottoni_e_non_copia(repo, monkeypatch):
    sid = await repo.create_suggestion(1, 2, 3, "idea")
    server = fake_guild(guild_id=1)
    server.get_member = MagicMock(return_value=None)
    cog = SuggestionsCog(bot=MagicMock())
    it = fake_interaction(guild=server, user=_staff())
    await cog._handle_decision(it, sid, CONSIDERING)
    assert len(it.response.edit_message.await_args.kwargs["view"].children) == 4
    sg.db.get_guild_setting.assert_not_awaited()
