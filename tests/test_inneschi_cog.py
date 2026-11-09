"""B27: comandi /admin-automazioni inneschi, ascolto di reazioni e ruoli, giro dello scheduler."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.inneschi as modulo
from cogs.utility.inneschi import InneschiCog
from core import tag_inneschi_logic as L
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel


def riga(**kw):
    base = dict(id=5, guild_id=1, tag="dado", tipo="reazione", valore="👍", canale_id=None, escludi="", creato_da=9)
    base.update(kw)
    return base


@pytest.fixture
def cog(monkeypatch):
    bot = MagicMock()
    c = InneschiCog(bot)
    tag_cog = MagicMock()
    tag_cog.esegui_innesco = AsyncMock(return_value=None)
    bot.get_cog = MagicMock(return_value=tag_cog)
    repo = MagicMock()
    for nome in ("aggiungi", "elenco", "per_tipo", "prendi", "prendi_per_id", "togli", "togli_per_canale"):
        setattr(repo, nome, AsyncMock())
    repo.aggiungi.return_value = ("ok", 5)
    repo.per_tipo.return_value = []
    monkeypatch.setattr(modulo, "tag_inneschi_repo", repo)
    sched = MagicMock()
    sched.schedule = AsyncMock(return_value=1)
    monkeypatch.setattr(modulo, "scheduler", sched)
    ccr = MagicMock()
    ccr.get_tag = AsyncMock(return_value=SimpleNamespace(name="dado"))
    ccr.search_names = AsyncMock(return_value=[])
    monkeypatch.setattr(modulo, "custom_command_repo", ccr)
    dbf = MagicMock()
    dbf.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", dbf)
    eb = MagicMock()
    eb.prendi = AsyncMock(return_value=SimpleNamespace(tipo="tag"))
    monkeypatch.setattr(modulo, "embed_bottoni_repo", eb)
    c.repo, c.sched, c.ccr, c.eb = repo, sched, ccr, eb
    return c


def _i():
    server = fake_guild()
    utente = fake_member(5)
    utente.guild = server
    return fake_interaction(guild=server, user=utente), server


def scelta(valore):
    return SimpleNamespace(value=valore)


async def test_aggiungi_a_tempo_prenota_il_primo_giro(cog):
    i, server = _i()
    canale = fake_text_channel()
    await cog.aggiungi.callback(cog, i, "dado", scelta("intervallo"), "30m", None, canale, "")
    cog.repo.aggiungi.assert_awaited_once()
    assert cog.repo.aggiungi.await_args.args[1:5] == ("dado", "intervallo", "30m", canale.id)
    args = cog.sched.schedule.await_args.args
    assert args[2] == L.AZIONE_INNESCO and args[4] == {"innesco_id": 5}
    assert args[3] > datetime.now(timezone.utc)


async def test_aggiungi_a_tempo_vuole_il_canale(cog):
    i, _ = _i()
    await cog.aggiungi.callback(cog, i, "dado", scelta("intervallo"), "30m", None, None, "")
    cog.repo.aggiungi.assert_not_awaited()
    i.response.send_message.assert_awaited()


@pytest.mark.parametrize("tipo, valore", [("intervallo", "5m"), ("orario", "*/5 * * * *"), ("reazione", "ciao"), ("bottone", "x")])
async def test_aggiungi_rifiuta_valori_storti(cog, tipo, valore):
    i, _ = _i()
    await cog.aggiungi.callback(cog, i, "dado", scelta(tipo), valore, None, fake_text_channel(), "")
    cog.repo.aggiungi.assert_not_awaited()
    cog.sched.schedule.assert_not_awaited()


async def test_aggiungi_ruolo_usa_il_ruolo_e_vuole_il_canale(cog):
    i, _ = _i()
    ruolo = fake_role(555000000000000001, "Vip")
    await cog.aggiungi.callback(cog, i, "dado", scelta("ruolo_dato"), "", ruolo, fake_text_channel(), "")
    assert cog.repo.aggiungi.await_args.args[3] == "555000000000000001"
    cog.sched.schedule.assert_not_awaited()  # non è a tempo
    i, _ = _i()
    await cog.aggiungi.callback(cog, i, "dado", scelta("ruolo_dato"), "", None, fake_text_channel(), "")
    assert cog.repo.aggiungi.await_count == 1


async def test_aggiungi_tag_inesistente_o_pieno_o_gia_presente(cog):
    i, _ = _i()
    cog.ccr.get_tag.return_value = None
    await cog.aggiungi.callback(cog, i, "dado", scelta("reazione"), "👍", None, None, "")
    cog.repo.aggiungi.assert_not_awaited()
    cog.ccr.get_tag.return_value = SimpleNamespace(name="dado")
    for esito in ("pieno", "esiste"):
        cog.repo.aggiungi.return_value = (esito, None)
        i, _ = _i()
        await cog.aggiungi.callback(cog, i, "dado", scelta("intervallo"), "30m", None, fake_text_channel(), "")
    cog.sched.schedule.assert_not_awaited()


async def test_aggiungi_bottone_deve_esistere(cog):
    i, _ = _i()
    cog.eb.prendi.return_value = None
    await cog.aggiungi.callback(cog, i, "dado", scelta("bottone"), "benvenuto:2", None, None, "")
    cog.repo.aggiungi.assert_not_awaited()
    cog.eb.prendi.return_value = SimpleNamespace(tipo="link")  # un link non preme niente
    await cog.aggiungi.callback(cog, i, "dado", scelta("bottone"), "benvenuto:2", None, None, "")
    cog.repo.aggiungi.assert_not_awaited()
    cog.eb.prendi.return_value = SimpleNamespace(tipo="tag")
    await cog.aggiungi.callback(cog, i, "dado", scelta("bottone"), "benvenuto:2", None, None, "")
    cog.repo.aggiungi.assert_awaited_once()


async def test_reazione_fa_partire_il_tag(cog):
    server = fake_guild()
    server.get_channel_or_thread = MagicMock(return_value=fake_text_channel())
    cog.bot.get_guild = MagicMock(return_value=server)
    cog.repo.per_tipo.return_value = [riga()]
    membro = fake_member(7)
    membro.bot = False
    payload = SimpleNamespace(guild_id=server.id, channel_id=3, member=membro, emoji=discord.PartialEmoji(name="👍"), user_id=7)
    await cog.on_raw_reaction_add(payload)
    cog.tag_cog.esegui_innesco.assert_awaited_once()
    assert cog.tag_cog.esegui_innesco.await_args.kwargs["membro"] is membro


async def test_reazione_ignora_bot_altra_emoji_e_altro_canale(cog):
    server = fake_guild()
    server.get_channel_or_thread = MagicMock(return_value=fake_text_channel())
    cog.bot.get_guild = MagicMock(return_value=server)
    cog.repo.per_tipo.return_value = [riga(canale_id=99)]
    bot_membro = fake_member(8)
    bot_membro.bot = True
    umano = fake_member(7)
    umano.bot = False
    for membro, emoji, canale in ((bot_membro, "👍", 99), (umano, "👎", 99), (umano, "👍", 3)):
        cog._cache.clear()
        await cog.on_raw_reaction_add(SimpleNamespace(guild_id=server.id, channel_id=canale, member=membro,
                                                      emoji=discord.PartialEmoji(name=emoji), user_id=membro.id))
    cog.tag_cog.esegui_innesco.assert_not_awaited()


async def test_reazione_in_privato_non_fa_niente(cog):
    await cog.on_raw_reaction_add(SimpleNamespace(guild_id=None, channel_id=3, member=None, emoji=discord.PartialEmoji(name="👍"), user_id=7))
    cog.repo.per_tipo.assert_not_awaited()


async def test_ruolo_dato_e_tolto(cog):
    server = fake_guild()
    canale = fake_text_channel()
    server.get_channel = MagicMock(return_value=canale)
    r = fake_role(555000000000000001, "Vip")
    prima, dopo = fake_member(7), fake_member(7)
    prima.guild = dopo.guild = server
    prima.bot = dopo.bot = False
    prima.roles, dopo.roles = [], [r]

    async def per_tipo(guild_id, tipo):
        return [riga(tipo=tipo, valore="555000000000000001", canale_id=canale.id)] if tipo in ("ruolo_dato", "ruolo_tolto") else []

    cog.repo.per_tipo.side_effect = per_tipo
    await cog.on_member_update(prima, dopo)
    assert cog.tag_cog.esegui_innesco.await_count == 1
    cog._cache.clear()
    await cog.on_member_update(dopo, prima)  # il ruolo si toglie
    assert cog.tag_cog.esegui_innesco.await_count == 2
    prima.roles = dopo.roles = [r]
    await cog.on_member_update(prima, dopo)  # nessun cambio
    assert cog.tag_cog.esegui_innesco.await_count == 2


async def test_giro_riprenota_prima_di_eseguire(cog):
    server = fake_guild()
    cog.bot.get_guild = MagicMock(return_value=server)
    server.get_channel = MagicMock(return_value=fake_text_channel())
    cog.repo.prendi_per_id.return_value = riga(tipo="intervallo", valore="30m", canale_id=3)
    ordine = []
    cog.sched.schedule.side_effect = lambda *a, **k: ordine.append("riprenota")
    cog.tag_cog.esegui_innesco.side_effect = lambda *a, **k: ordine.append("esegui")
    await cog.handle_innesco(server.id, 0, {"innesco_id": 5})
    assert ordine == ["riprenota", "esegui"]


async def test_giro_di_un_innesco_tolto_finisce_la_catena(cog):
    cog.repo.prendi_per_id.return_value = None
    await cog.handle_innesco(1, 0, {"innesco_id": 5})
    cog.sched.schedule.assert_not_awaited()
    cog.tag_cog.esegui_innesco.assert_not_awaited()


async def test_giro_in_ora_esclusa_salta_ma_riprenota(cog, monkeypatch):
    server = fake_guild()
    cog.bot.get_guild = MagicMock(return_value=server)
    server.get_channel = MagicMock(return_value=fake_text_channel())
    cog.repo.prendi_per_id.return_value = riga(tipo="orario", valore="0 9 * * *", canale_id=3, escludi="0-24")
    monkeypatch.setattr(modulo.L, "escluso", lambda *a: True)
    await cog.handle_innesco(server.id, 0, {"innesco_id": 5})
    cog.sched.schedule.assert_awaited_once()
    cog.tag_cog.esegui_innesco.assert_not_awaited()


async def test_togli_elenco_avvia_ora(cog):
    i, _ = _i()
    cog.repo.togli.return_value = True
    await cog.togli.callback(cog, i, 5)
    cog.repo.togli.assert_awaited_once_with(i.guild.id, 5)
    i, _ = _i()
    cog.repo.elenco.return_value = [riga(), riga(id=6, tipo="intervallo", valore="30m", canale_id=3)]
    await cog.elenco.callback(cog, i)
    testo = i.response.send_message.await_args.args[0]
    assert "dado" in testo and "30m" in testo
    i, _ = _i()
    cog.repo.prendi.return_value = riga(tipo="intervallo", valore="30m", canale_id=3)
    cog.bot.get_channel = MagicMock(return_value=fake_text_channel())
    i.guild.get_channel = MagicMock(return_value=fake_text_channel())
    await cog.avvia_ora.callback(cog, i, 5)
    cog.tag_cog.esegui_innesco.assert_awaited()


async def test_canale_cancellato_toglie_i_suoi_inneschi(cog):
    canale = fake_text_channel()
    await cog.on_guild_channel_delete(canale)
    cog.repo.togli_per_canale.assert_awaited_once_with(canale.guild.id, canale.id)
