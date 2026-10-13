"""
tests/test_custom_commands.py
=============================
NF-09 (#80) e M 10.15: comandi personalizzati (tag) con testo o embed, ruolo da
dare o togliere, pausa; uso con /utility tag e con il prefisso del server
(colonna guild_config.prefix, prima morta).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.custom_commands as modulo
from cogs.utility.custom_commands import CustomCommandsCog
from core.custom_command_logic import (
    MAX_TAG,
    azione_ruolo,
    costruisci_risposta,
    nome_da_messaggio,
    normalizza_nome,
    pausa_residua,
    valida_prefisso,
)
from core.repositories.custom_command_repo import CustomCommandRepository
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)
from tests.support.percorsi import comando_nel_gruppo

ORA = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- logica pura
@pytest.mark.parametrize("grezzo, atteso", [("Regole", "regole"), ("  ciao-mondo_1 ", "ciao-mondo_1"),
                                              ("a" * 33, None), ("", None), ("ci ao", None), ("a/b", None), ("è", None)])
def test_normalizza_nome(grezzo, atteso):
    assert normalizza_nome(grezzo) == atteso


@pytest.mark.parametrize("prefisso, valido", [("!", True), ("?!", True), (".", True), ("", False), ("abcd", False),
                                                ("a", False), ("1", False), (" ", False), ("/", False), ("@", False),
                                                ("#", False), ("<", False), ("!!!!", False)])
def test_valida_prefisso(prefisso, valido):
    assert (valida_prefisso(prefisso) is None) is valido


def test_nome_da_messaggio():
    assert nome_da_messaggio("!regole", "!") == ("regole", "")
    assert nome_da_messaggio("!Regole  uno due", "!") == ("regole", "uno due")
    assert nome_da_messaggio("regole", "!") is None
    assert nome_da_messaggio("!", "!") is None
    assert nome_da_messaggio("!!x", "!") is None
    assert nome_da_messaggio("!regole", None) is None


def test_costruisci_risposta_senza_str_format_e_con_menzioni_neutre():
    testo = costruisci_risposta("Ciao {user}, {args} {x:>99999999} {sconosciuto}", {"user": "<@1>", "args": "@everyone <@&123456789012345678>"})
    assert "{x:>99999999}" in testo and "{sconosciuto}" in testo
    assert "@everyone" not in testo.replace("@​everyone", "")
    assert "<@&123456789012345678>" not in testo


def test_costruisci_risposta_resta_entro_2000():
    assert len(costruisci_risposta("{args}" * 50, {"args": "x" * 1000})) <= 2000


def test_pausa_residua():
    assert pausa_residua(None, ORA, 30) == 0
    assert pausa_residua(ORA - timedelta(seconds=10), ORA, 30) == pytest.approx(20)
    assert pausa_residua(ORA - timedelta(seconds=40), ORA, 30) == 0
    assert pausa_residua(ORA, ORA, 0) == 0


@pytest.mark.parametrize("azione, ha, atteso", [("dai", False, "dai"), ("dai", True, None), ("togli", True, "togli"),
                                                  ("togli", False, None), ("alterna", False, "dai"),
                                                  ("alterna", True, "togli"), ("nessuna", False, None)])
def test_azione_ruolo(azione, ha, atteso):
    assert azione_ruolo(azione, ha) == atteso


# --------------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return CustomCommandRepository(pool_provider=lambda: clean_db)


async def _crea(repo, guild=1, nome="regole", **kw):
    campi = dict(response="Testo", use_embed=False, role_id=None, role_action="nessuna", cooldown_seconds=0,
                 ping_ruoli=False, created_by=7)
    campi.update(kw)
    return await repo.create_tag(guild, nome, **campi)


@pytest.mark.asyncio
async def test_crea_leggi_elenca_elimina(repo):
    assert await _crea(repo) == "ok"
    assert await _crea(repo) == "esiste"
    tag = await repo.get_tag(1, "regole")
    assert tag.response == "Testo" and tag.use_embed is False
    assert [t.name for t in await repo.list_tags(1)] == ["regole"]
    assert await repo.delete_tag(1, "regole") is True
    assert await repo.delete_tag(1, "regole") is False
    assert await repo.get_tag(1, "regole") is None


@pytest.mark.asyncio
async def test_tetto_dei_tag_per_server(repo):
    for i in range(MAX_TAG):
        assert await _crea(repo, nome=f"t{i}") == "ok"
    assert await _crea(repo, nome="troppo") == "pieno"
    assert await _crea(repo, guild=2, nome="troppo") == "ok"


@pytest.mark.asyncio
async def test_modifica_cambia_solo_i_campi_dati(repo):
    await _crea(repo, response="Vecchio", cooldown_seconds=30)
    assert await repo.update_tag(1, "regole", response="Nuovo") is True
    tag = await repo.get_tag(1, "regole")
    assert tag.response == "Nuovo" and tag.cooldown_seconds == 30
    assert await repo.update_tag(1, "assente", response="x") is False


@pytest.mark.asyncio
async def test_prefisso_per_server(repo):
    assert await repo.get_prefix(1) is None
    await repo.set_prefix(1, "!")
    assert await repo.get_prefix(1) == "!"
    await repo.set_prefix(1, None)
    assert await repo.get_prefix(1) is None


@pytest.mark.asyncio
async def test_conteggio_usi(repo):
    await _crea(repo)
    await repo.add_use(1, "regole")
    await repo.add_use(1, "regole")
    assert (await repo.get_tag(1, "regole")).uses == 2


# -------------------------------------------------------------------------- cog
def _tag(**kw):
    base = dict(guild_id=1, name="regole", response="Ciao {user} {args}", use_embed=False, role_id=None,
                role_action="nessuna", cooldown_seconds=0, ping_ruoli=False, uses=0)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def scena(monkeypatch):
    cog = CustomCommandsCog(MagicMock())
    repo = MagicMock()
    repo.get_tag = AsyncMock(return_value=_tag())
    repo.add_use = AsyncMock()
    repo.get_prefix = AsyncMock(return_value="!")
    repo.create_tag = AsyncMock(return_value="ok")
    repo.update_tag = AsyncMock(return_value=True)
    repo.set_prefix = AsyncMock()
    repo.list_tags = AsyncMock(return_value=[])
    monkeypatch.setattr(modulo, "custom_command_repo", repo)
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    modulo._ultimo_uso.__init__(100)  # cache vuota
    modulo._cache_prefissi.__init__(100)
    cog.repo = repo
    return cog


def _interazione(utente=None):
    server = fake_guild()
    server.me.top_role = fake_role(900, "Bot", position=50)
    utente = utente or fake_member(5)
    utente.guild = server
    utente.add_roles = AsyncMock()
    utente.remove_roles = AsyncMock()
    utente.display_name = "Mario"
    i = fake_interaction(guild=server, user=utente)
    return i, server, utente


@pytest.mark.asyncio
async def test_uso_con_slash_risponde_con_testo_senza_ping(scena):
    i, server, utente = _interazione()
    await scena.tag.callback(scena, i, "regole", "@everyone")
    kw = i.response.send_message.await_args.kwargs
    testo = i.response.send_message.await_args.args[0]
    assert "Mario" in testo or "<@5>" in testo
    assert "@everyone" not in testo.replace("@​everyone", "")
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].roles is False
    scena.repo.add_use.assert_awaited_once()


@pytest.mark.asyncio
async def test_tag_inesistente(scena):
    scena.repo.get_tag.return_value = None
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "boh", "")
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_pausa_blocca_il_secondo_uso(scena):
    scena.repo.get_tag.return_value = _tag(cooldown_seconds=60)
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "")
    i2, *_ = _interazione()
    await scena.tag.callback(scena, i2, "regole", "")
    assert i2.response.send_message.await_args.kwargs["ephemeral"] is True
    assert "attendere" in i2.response.send_message.await_args.args[0].lower() or "aspetta" in i2.response.send_message.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_tag_con_ruolo_lo_da(scena):
    i, server, utente = _interazione()
    ruolo = fake_role(10, "Gioco", position=1)
    server.get_role = lambda rid: ruolo
    scena.repo.get_tag.return_value = _tag(role_id=10, role_action="dai")
    await scena.tag.callback(scena, i, "regole", "")
    utente.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_ruolo_diventato_pericoloso_non_si_da_ma_il_tag_risponde(scena):
    i, server, utente = _interazione()
    ruolo = fake_role(10, "Admin", position=1, permissions=discord.Permissions(administrator=True))
    server.get_role = lambda rid: ruolo
    scena.repo.get_tag.return_value = _tag(role_id=10, role_action="dai")
    await scena.tag.callback(scena, i, "regole", "")
    utente.add_roles.assert_not_awaited()
    i.response.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_embed_tag(scena):
    scena.repo.get_tag.return_value = _tag(use_embed=True, response="x" * 1900)
    i, *_ = _interazione()
    await scena.tag.callback(scena, i, "regole", "")
    assert isinstance(i.response.send_message.await_args.kwargs["embed"], discord.Embed)


@pytest.mark.asyncio
async def test_prefisso_nel_messaggio_attiva_il_tag(scena):
    server = fake_guild()
    server.me.top_role = fake_role(900, "Bot", position=50)
    canale = fake_text_channel()
    canale.send = AsyncMock()
    autore = fake_member(5)
    autore.guild = server
    autore.display_name = "Mario"
    msg = fake_message(1, author=autore, channel=canale, guild=server, content="!regole ciao")
    await scena.on_message(msg)
    canale.send.assert_awaited_once()
    assert canale.send.await_args.kwargs["allowed_mentions"].everyone is False


@pytest.mark.asyncio
async def test_prefisso_ignora_bot_e_messaggi_senza_prefisso(scena):
    server = fake_guild()
    canale = fake_text_channel()
    canale.send = AsyncMock()
    bot = fake_member(6, bot=True)
    await scena.on_message(fake_message(1, author=bot, channel=canale, guild=server, content="!regole"))
    umano = fake_member(5)
    await scena.on_message(fake_message(2, author=umano, channel=canale, guild=server, content="regole"))
    canale.send.assert_not_awaited()
    scena.repo.get_tag.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_rifiuta_nome_non_valido_e_ruolo_non_assegnabile(scena):
    i, server, utente = _interazione()
    utente.top_role = fake_role(800, "Admin", position=60)
    await scena.crea.callback(scena, i, "NOME CON SPAZI", "x", False, None, "nessuna", 0)
    scena.repo.create_tag.assert_not_awaited()
    ruolo = fake_role(10, "Gestito", position=1, managed=True)
    i2, server2, utente2 = _interazione()
    utente2.top_role = fake_role(800, "Admin", position=60)
    await scena.crea.callback(scena, i2, "ok", "x", False, ruolo, "dai", 0)
    scena.repo.create_tag.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_ruolo_senza_azione_o_azione_senza_ruolo_rifiutati(scena):
    i, server, utente = _interazione()
    utente.top_role = fake_role(800, "Admin", position=60)
    await scena.crea.callback(scena, i, "ok", "x", False, None, "dai", 0)
    scena.repo.create_tag.assert_not_awaited()


@pytest.mark.asyncio
async def test_crea_ok_salva_ping_ruoli_secondo_i_permessi(scena):
    i, server, utente = _interazione(fake_member(5, guild_permissions=discord.Permissions(mention_everyone=True)))
    utente.top_role = fake_role(800, "Admin", position=60)
    await scena.crea.callback(scena, i, "ok", "x", False, None, "nessuna", 0)
    assert scena.repo.create_tag.await_args.kwargs["ping_ruoli"] is True


@pytest.mark.asyncio
async def test_prefisso_comando_valida(scena):
    i, *_ = _interazione()
    await scena.prefisso.callback(scena, i, "abc")
    scena.repo.set_prefix.assert_not_awaited()
    await scena.prefisso.callback(scena, i, "!")
    scena.repo.set_prefix.assert_awaited_once_with(i.guild.id, "!")


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("crea", "modifica", "elimina", "elenco", "prefisso"):
        assert comando_nel_gruppo("moduli", f"comandi {nome}") is not None
    tag = comando_nel_gruppo("utility", "tag")
    opzioni = {o["name"]: o for o in tag.to_dict(bot.tree)["options"]}
    assert opzioni["nome"]["max_length"] == 32 and opzioni["argomenti"]["max_length"] <= 500
    crea = {o["name"]: o for o in comando_nel_gruppo("moduli", "comandi crea").to_dict(bot.tree)["options"]}
    assert crea["testo"]["max_length"] == 2000 and crea["nome"]["max_length"] == 32
