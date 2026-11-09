"""
tests/test_conteggio.py
=======================
D69 B14 (UTL-186, 187, 188, 189, 190, 192): gioco del conteggio su più canali, modi (binario, romani, lettere),
filtro, punizione, ruolo dell'ultimo e classifica. Archivio su PostgreSQL vero.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.conteggio as modulo
from core.conteggio_logic import a_lettere, a_romano, da_romano, leggi_numero, scrivi_numero
from core.repositories.counting_game_repo import NON_CAMBIA, CountingGameRepository, TroppiCanali
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel

G = 1


# ------------------------------------------------------------------ logica pura
def test_romani_andata_e_ritorno():
    assert a_romano(1994) == "MCMXCIV" and da_romano("MCMXCIV") == 1994
    assert da_romano("IIII") is None and da_romano("") is None and da_romano("abc") is None
    assert all(da_romano(a_romano(n)) == n for n in range(1, 4000))


def test_lettere():
    assert a_lettere(21) == "ventuno" and a_lettere(28) == "ventotto"
    assert a_lettere(100) == "cento" and a_lettere(1000) == "mille"
    assert leggi_numero("ventuno", "lettere") == 21 and leggi_numero("pippo", "lettere") is None
    assert leggi_numero(a_lettere(1234), "lettere") == 1234


def test_leggi_numero_per_modo_e_filtro():
    assert leggi_numero("101", "binario") == 5 and leggi_numero("102", "binario") is None
    assert leggi_numero("XIV", "romani") == 14
    assert leggi_numero("12 che bello", "decimale", "solo_numero") is None
    assert leggi_numero("12 che bello", "decimale", "con_testo") == 12
    assert leggi_numero("ciao", "decimale", "con_testo") is None
    assert leggi_numero("1" * 12) is None
    assert scrivi_numero(5, "binario") == "101" and scrivi_numero(4, "romani") == "IV"


# ------------------------------------------------------------------ archivio
@pytest.fixture
def repo(clean_db):
    return CountingGameRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_piu_canali_con_tetto_a_dieci(repo):
    for c in range(10):
        assert await repo.aggiungi_canale(G, 100 + c) is True
    with pytest.raises(TroppiCanali):
        await repo.aggiungi_canale(G, 999)
    await repo.aggiungi_canale(G, 100, "binario")  # un canale già presente si può cambiare
    assert (await repo.get(G, 100)).modo == "binario"
    assert len(await repo.elenco(G)) == 10
    assert await repo.togli_canale(G, 100) is True and await repo.togli_canale(G, 100) is False


@pytest.mark.asyncio
async def test_register_giusto_sbagliato_e_punteggi(repo):
    await repo.aggiungi_canale(G, 5)
    assert await repo.register(G, 6, 1, 1) is None
    assert (await repo.register(G, 5, 1, 1)).corretto
    assert not (await repo.register(G, 5, 1, 2)).corretto  # stessa persona due volte
    e = await repo.register(G, 5, 2, 1)
    assert e.corretto and e.precedente is None
    e = await repo.register(G, 5, 3, 2)
    assert e.corretto and e.precedente == 2 and e.record == 2
    classifica = await repo.classifica(G, 5, 10)
    assert {p.user_id: (p.giusti, p.sbagliati) for p in classifica}[1] == (1, 1)
    assert await repo.conta_giocatori(G, None) == 3


@pytest.mark.asyncio
async def test_punizione_e_blocco(repo):
    await repo.aggiungi_canale(G, 5)
    assert await repo.imposta_regole(G, 5, punizione_minuti=30) is True
    assert await repo.imposta_regole(G, 77, punizione_minuti=30) is False
    e = await repo.register(G, 5, 9, 7)
    assert not e.corretto and e.bloccato_fino > datetime.now(timezone.utc) + timedelta(minutes=29)
    assert await repo.blocco_attivo(G, 5, 9) is not None and await repo.blocco_attivo(G, 5, 8) is None
    await repo.imposta_regole(G, 5, punizione_minuti=NON_CAMBIA, ruolo_ultimo=44)
    s = await repo.get(G, 5)
    assert s.punizione_minuti == 30 and s.ruolo_ultimo == 44


@pytest.mark.asyncio
async def test_blocco_scaduto_non_vale(repo, clean_db):
    await repo.aggiungi_canale(G, 5)
    await clean_db.execute(
        "INSERT INTO conteggio_blocchi (guild_id, channel_id, user_id, scade_il) VALUES (1, 5, 3, now() - interval '1 hour')"
    )
    assert await repo.blocco_attivo(G, 5, 3) is None


@pytest.mark.asyncio
async def test_register_in_parallelo_ne_passa_uno(repo):
    await repo.aggiungi_canale(G, 5)
    await repo.register(G, 5, 1, 1)
    esiti = await asyncio.gather(*(repo.register(G, 5, 10 + i, 2) for i in range(6)))
    assert sum(1 for e in esiti if e.corretto) == 1


@pytest.mark.asyncio
async def test_la_riga_di_prima_viene_portata_nella_tabella_nuova(clean_db):
    sql = open("core/migrations/0552_conteggio_canali.sql", encoding="utf-8").read()
    await clean_db.execute("DELETE FROM conteggio_canali")
    await clean_db.execute(
        "INSERT INTO counting_games (guild_id, channel_id, current, last_user_id, best) VALUES (8, 80, 4, 2, 9)"
    )
    await clean_db.execute(sql)
    s = await CountingGameRepository(pool_provider=lambda: clean_db).get(8, 80)
    assert (s.current, s.best, s.modo) == (4, 9, "decimale")


# ------------------------------------------------------------------ cog
class _Scena:
    def __init__(self, monkeypatch, repo):
        self.repo = repo
        monkeypatch.setattr(modulo, "counting_game_repo", repo)
        db = MagicMock()
        db.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db)
        self.cog = modulo.ConteggioCog(MagicMock())
        self.guild = fake_guild(G)
        self.canale = fake_text_channel(5)

    def messaggio(self, testo, utente):
        m = fake_message(author=fake_member(utente), channel=self.canale, guild=self.guild, content=testo)
        m.type = discord.MessageType.default
        m.author.bot = False
        m.add_reaction = AsyncMock()
        self.canale.send = AsyncMock()
        return m


@pytest.mark.asyncio
async def test_listener_giusto_sbagliato_e_blocco(monkeypatch, repo):
    s = _Scena(monkeypatch, repo)
    await repo.aggiungi_canale(G, 5, "binario")
    await repo.imposta_regole(G, 5, punizione_minuti=10)
    m = s.messaggio("1", 1)
    await s.cog.on_message(m)
    m.add_reaction.assert_awaited_with("✅")
    m = s.messaggio("11", 1)  # 3 in binario, ma stessa persona: sbagliato
    await s.cog.on_message(m)
    m.add_reaction.assert_awaited_with("❌")
    s.canale.send.assert_awaited()
    assert "1" in s.canale.send.await_args.args[0]
    m = s.messaggio("1", 1)
    await s.cog.on_message(m)
    m.add_reaction.assert_awaited_with("⛔")
    assert (await repo.get(G, 5)).current == 0


@pytest.mark.asyncio
async def test_listener_ignora_chiacchiera_bot_e_altri_canali(monkeypatch, repo):
    s = _Scena(monkeypatch, repo)
    await repo.aggiungi_canale(G, 5)
    m = s.messaggio("ciao a tutti", 1)
    await s.cog.on_message(m)
    m.add_reaction.assert_not_awaited()
    m = s.messaggio("1", 1)
    m.author.bot = True
    await s.cog.on_message(m)
    m.add_reaction.assert_not_awaited()
    s.canale.id = 6
    m = s.messaggio("1", 1)
    await s.cog.on_message(m)
    m.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_ruolo_dell_ultimo_passa_di_mano(monkeypatch, repo):
    s = _Scena(monkeypatch, repo)
    await repo.aggiungi_canale(G, 5)
    await repo.imposta_regole(G, 5, ruolo_ultimo=44)
    ruolo = MagicMock(id=44)
    s.guild.get_role = MagicMock(return_value=ruolo)
    primo = s.messaggio("1", 1)
    primo.author.__class__ = discord.Member
    primo.author.add_roles = AsyncMock()
    await s.cog.on_message(primo)
    primo.author.add_roles.assert_awaited_once()
    vecchio = MagicMock(roles=[ruolo])
    vecchio.remove_roles = AsyncMock()
    s.guild.get_member = MagicMock(return_value=vecchio)
    secondo = s.messaggio("2", 2)
    secondo.author.__class__ = discord.Member
    secondo.author.add_roles = AsyncMock()
    await s.cog.on_message(secondo)
    vecchio.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_canale_cancellato_toglie_il_gioco(monkeypatch, repo):
    s = _Scena(monkeypatch, repo)
    await repo.aggiungi_canale(G, 5)
    await s.cog.on_guild_channel_delete(SimpleNamespace(id=5, guild=SimpleNamespace(id=G)))
    assert await repo.get(G, 5) is None


@pytest.mark.asyncio
async def test_comando_canale_aggiunge_elenca_e_toglie(monkeypatch, repo):
    s = _Scena(monkeypatch, repo)
    monkeypatch.setattr(modulo, "motivo_se_il_bot_non_puo", lambda *a, **k: None)
    sc = lambda v: SimpleNamespace(value=v)  # noqa: E731
    i = fake_interaction(guild=s.guild)
    await s.cog.conteggio_canale.callback(s.cog, i, sc("aggiungi"), s.canale, sc("romani"), None)
    assert (await repo.get(G, 5)).modo == "romani"
    i = fake_interaction(guild=s.guild)
    await s.cog.conteggio_canale.callback(s.cog, i, sc("elenco"), None, None, None)
    assert "<#5>" in i.response.send_message.await_args.args[0]
    i = fake_interaction(guild=s.guild)
    await s.cog.conteggio_canale.callback(s.cog, i, sc("togli"), s.canale, None, None)
    assert await repo.get(G, 5) is None


@pytest.mark.asyncio
async def test_comando_regole_e_classifica(monkeypatch, repo):
    s = _Scena(monkeypatch, repo)
    await repo.aggiungi_canale(G, 5)
    i = fake_interaction(guild=s.guild)
    await s.cog.conteggio_regole.callback(s.cog, i, s.canale, 15, None, False)
    assert (await repo.get(G, 5)).punizione_minuti == 15
    for u in range(1, 13):
        await repo.register(G, 5, u, u)
    i = fake_interaction(guild=s.guild)
    await s.cog.conteggio_classifica.callback(s.cog, i, None, 2)
    embed = i.followup.send.await_args.kwargs["embed"]
    assert "2" in embed.footer.text and len(embed.description.split("\n")) == 2


@pytest.mark.asyncio
async def test_i_comandi_stanno_nell_albero():
    from tests.support.full_tree import build_full_bot, close_full_bot

    bot, _ = await build_full_bot()
    try:
        nomi = {c.qualified_name for c in bot.tree.walk_commands()}
    finally:
        await close_full_bot(bot)
    assert {"admin-giochi conteggio canale", "admin-giochi conteggio regole", "giochi conteggio classifica"} <= nomi
