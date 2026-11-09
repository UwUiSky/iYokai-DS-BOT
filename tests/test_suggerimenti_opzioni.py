"""
tests/test_suggerimenti_opzioni.py
==================================
Catalogo #128 B7 (D69): suggerimenti anonimi (autore visibile solo agli admin, col registro), colore a soglia di
voti, canale unico, esito come messaggio nuovo.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands as ext

import cogs.utility.suggestions as sg
from core import suggestion_logic as L
from core.repositories.suggestion_repo import Suggestion, SuggestionRepository
from core.repositories.suggestions_config_repo import OpzioniSuggerimenti, SuggestionsConfigRepository
from tests.support.discord_fakes import fake_guild, fake_interaction
from tests.support.percorsi import comando_nel_gruppo
from datetime import datetime, timezone


def _s(**kw):
    base = dict(id=3, guild_id=1, channel_id=2, message_id=9, user_id=77, suggestion_text="idea", status="pending",
                decided_by=None, decided_at=None, created_at=datetime.now(timezone.utc))
    base.update(kw)
    return Suggestion(**base)


def test_colore_a_soglia_solo_per_i_suggerimenti_aperti():
    assert L.colore_attuale("pending", 10, 10, "#FFD700", 111) == 0xFFD700
    assert L.colore_attuale("pending", 9, 10, "#FFD700", 111) == 111
    assert L.colore_attuale("approved", 50, 10, "#FFD700", 222) == 222  # deciso: vale il colore dello stato
    assert L.colore_attuale("pending", 50, 0, "#FFD700", 111) == 111  # soglia 0 = spento
    assert L.colore_attuale("pending", 50, 10, None, 111) == 111


def test_canale_unico():
    assert L.fuori_dal_canale_unico(5, 6) and not L.fuori_dal_canale_unico(6, 6) and not L.fuori_dal_canale_unico(5, None)


def test_embed_anonimo_non_mostra_l_autore():
    campo = next(f for f in sg._build_embed(_s(anonimo=True)).fields if f.name == "Proposto da")
    assert campo.value == "Anonimo" and "77" not in campo.value
    assert "<@77>" in next(f for f in sg._build_embed(_s()).fields if f.name == "Proposto da").value


@pytest.mark.asyncio
async def test_repo_opzioni_parziali_e_cache(clean_db):
    r = SuggestionsConfigRepository(pool_provider=lambda: clean_db)
    assert await r.get(1) == OpzioniSuggerimenti()
    await r.imposta(1, soglia=5, colore="#FFD700")
    await r.imposta(1, esito="nuovo", solo_canale_id=44)
    o = await r.get(1)
    assert (o.soglia, o.colore, o.esito, o.solo_canale_id, o.anonimi) == (5, "#FFD700", "nuovo", 44, False)
    await r.togli_canale(1, 99)  # un altro canale: non cambia
    assert (await r.get(1)).solo_canale_id == 44
    await r.togli_canale(1, 44)
    assert (await r.get(1)).solo_canale_id is None
    with pytest.raises(ValueError):
        await r.imposta(1, id=3)
    with pytest.raises(Exception):
        await r.imposta(1, colore="rosso")  # lo rifiuta anche il database


@pytest.mark.asyncio
async def test_repo_suggerimento_anonimo_e_ricerca_per_messaggio(clean_db):
    r = SuggestionRepository(pool_provider=lambda: clean_db)
    sid = await r.create_suggestion(1, 2, 77, "idea", anonimo=True)
    await r.set_message_id(sid, 555)
    s = await r.per_messaggio(555)
    assert s.id == sid and s.anonimo is True
    assert (await r.per_messaggio(1)) is None
    assert (await r.get_suggestion(await r.create_suggestion(1, 2, 78, "altra"))).anonimo is False


def _cog(monkeypatch, opzioni):
    c = sg.SuggestionsCog(MagicMock())
    monkeypatch.setattr(sg.suggestions_config_repo, "get", AsyncMock(return_value=opzioni))
    monkeypatch.setattr(sg.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    return c


@pytest.mark.asyncio
async def test_suggest_fuori_dal_canale_unico_e_rifiutato(monkeypatch):
    c = _cog(monkeypatch, OpzioniSuggerimenti(solo_canale_id=500))
    crea = AsyncMock()
    monkeypatch.setattr(sg.suggestion_repo, "create_suggestion", crea)
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=2))
    canale = MagicMock(spec=discord.TextChannel)
    server = fake_guild()
    server.get_channel = lambda _i: canale
    it = fake_interaction(guild=server)
    it.channel_id = 400
    await c.suggest.callback(c, it, "idea")
    crea.assert_not_called()
    assert "<#500>" in it.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_suggest_anonimo_salva_il_segno(monkeypatch):
    c = _cog(monkeypatch, OpzioniSuggerimenti(anonimi=True))
    monkeypatch.setattr(sg.db, "get_guild_setting", AsyncMock(return_value=2))
    canale = MagicMock(spec=discord.TextChannel)
    canale.id = 2
    canale.send = AsyncMock(return_value=MagicMock(id=8, add_reaction=AsyncMock()))
    server = fake_guild()
    server.get_channel = lambda _i: canale
    crea = AsyncMock(return_value=3)
    monkeypatch.setattr(sg.suggestion_repo, "create_suggestion", crea)
    monkeypatch.setattr(sg.suggestion_repo, "get_suggestion", AsyncMock(return_value=_s(anonimo=True)))
    monkeypatch.setattr(sg.suggestion_repo, "set_message_id", AsyncMock())
    it = fake_interaction(guild=server)
    it.channel_id = 2
    await c.suggest.callback(c, it, "idea")
    assert crea.await_args.kwargs["anonimo"] is True
    vista = canale.send.await_args.kwargs["view"]
    assert any("chi:" in (getattr(b.item, "custom_id", "") if hasattr(b, "item") else getattr(b, "custom_id", "")) for b in vista.children)


@pytest.mark.asyncio
async def test_chi_l_ha_scritto_solo_admin_e_va_nel_registro(monkeypatch):
    b = sg.BottoneChiScrisse(3)
    it = fake_interaction()
    monkeypatch.setattr(sg, "puo_usare", AsyncMock(return_value=False))
    await b.callback(it)
    assert "admin" in it.response.send_message.await_args.args[0]
    monkeypatch.setattr(sg, "puo_usare", AsyncMock(return_value=True))
    monkeypatch.setattr(sg.suggestion_repo, "get_suggestion", AsyncMock(return_value=_s(guild_id=it.guild.id)))
    dest = MagicMock()
    monkeypatch.setattr(sg.router, "destinazione", AsyncMock(return_value=dest))
    invia = AsyncMock()
    monkeypatch.setattr(sg.router, "invia_a", invia)
    it2 = fake_interaction(guild=it.guild)
    await b.callback(it2)
    assert it2.response.send_message.await_args.kwargs["ephemeral"] is True
    invia.assert_awaited_once()


@pytest.mark.asyncio
async def test_esito_nuovo_lascia_il_messaggio_e_ne_scrive_un_altro(monkeypatch):
    c = _cog(monkeypatch, OpzioniSuggerimenti(esito="nuovo"))
    monkeypatch.setattr(sg.suggestion_repo, "get_suggestion", AsyncMock(return_value=_s()))
    monkeypatch.setattr(sg.suggestion_repo, "set_status", AsyncMock(return_value=True))
    monkeypatch.setattr(c, "_avvisa_autore", AsyncMock())
    monkeypatch.setattr(c, "_copia_nei_decisi", AsyncMock())
    staff = MagicMock(spec=discord.Member)
    staff.guild_permissions = discord.Permissions(manage_guild=True)
    staff.id = 5
    it = fake_interaction(user=staff)
    it.message = MagicMock(reply=AsyncMock())
    it.response.edit_message = AsyncMock()
    await c._handle_decision(it, 3, "approved", None)
    assert "embed" not in it.response.edit_message.await_args.kwargs  # l'originale non cambia
    it.message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_colore_a_soglia_modifica_il_messaggio(monkeypatch):
    c = _cog(monkeypatch, OpzioniSuggerimenti(soglia=2, colore="#FFD700"))
    monkeypatch.setattr(sg.suggestion_repo, "per_messaggio", AsyncMock(return_value=_s()))
    msg = MagicMock()
    msg.reactions = [MagicMock(emoji="👍", count=3, me=True)]  # 2 persone + il bot
    msg.embeds = [discord.Embed(color=0x5865F2)]
    msg.edit = AsyncMock()
    canale = MagicMock(fetch_message=AsyncMock(return_value=msg))
    server = MagicMock(get_channel=lambda _i: canale)
    c.bot.get_guild.return_value = server
    p = MagicMock(guild_id=1, message_id=9, emoji="👍")
    await c._aggiorna_colore(p)
    assert msg.edit.await_args.kwargs["embed"].color.value == 0xFFD700
    msg.edit.reset_mock()
    msg.reactions = [MagicMock(emoji="👍", count=2, me=True)]  # solo 1 persona: sotto soglia
    msg.embeds = [discord.Embed(color=0x5865F2)]
    await c._aggiorna_colore(p)
    msg.edit.assert_not_called()  # il colore è già quello giusto
    p.emoji = "👎"
    await c._aggiorna_colore(p)  # altre reazioni: nessuna chiamata
    assert msg.edit.await_count == 0


@pytest.mark.asyncio
async def test_albero_canale_suggerimenti_opzioni(monkeypatch):
    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    monkeypatch.setattr(sg.suggestion_repo, "list_pending", AsyncMock(return_value=[]))
    await sg.setup(bot)
    o = comando_nel_gruppo("admin-bot", "config canale-suggerimenti").to_dict(bot.tree)["options"]
    assert [x["name"] for x in o] == ["channel", "decisi", "anonimi", "soglia", "colore", "esito", "solo_da"]
    obbl = [x.get("required", False) for x in o]
    assert obbl == sorted(obbl, reverse=True)
    assert next(x for x in o if x["name"] == "colore")["max_length"] == 7


@pytest.mark.asyncio
async def test_indice_sul_messaggio_dei_suggerimenti(clean_db):
    riga = await clean_db.fetchval("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_suggestions_message'")
    assert riga == 1
