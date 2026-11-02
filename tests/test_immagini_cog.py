"""
tests/test_immagini_cog.py
==========================
Cog del filtro immagini (D62): ascolta gli allegati e applica l'esito; comando dell'owner per la libreria.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

from cogs.automod import immagini as cog_mod
from core import immagini_opzioni as op
from core import immagini_pipeline as pl
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel

GUILD = 777000803


def allegato(nome="foto.png", tipo="image/png", size=100):
    a = create_autospec(discord.Attachment, instance=True)
    a.filename, a.content_type, a.size = nome, tipo, size
    a.read = AsyncMock(return_value=b"dati")
    return a


@pytest.fixture
def ambiente(monkeypatch):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = cog_mod.ImmaginiCog(bot)
    adesso = discord.utils.utcnow()
    membro = fake_member(555, "utente")
    membro.joined_at = adesso - timedelta(days=100)
    membro.created_at = adesso - timedelta(days=900)
    membro.guild_permissions = discord.Permissions.none()
    membro.mention = "<@555>"
    guild = fake_guild(GUILD, owner_id=1)
    guild.member_count = 100
    membro.guild = guild
    canale = fake_text_channel(111)
    log = fake_text_channel(222)
    guild.get_channel = MagicMock(side_effect=lambda i: log if i == 222 else None)
    msg = fake_message(author=membro, channel=canale, guild=guild)
    msg.attachments = [allegato()]
    azioni = SimpleNamespace(cancella=AsyncMock(), isola=AsyncMock())
    dm = AsyncMock(return_value=True)
    modlog = AsyncMock()
    segnala = AsyncMock()
    monkeypatch.setattr(cog_mod, "opzioni_immagini", SimpleNamespace(leggi=AsyncMock(return_value=op.OpzioniImmagini(True, "cancella", 10, 222))))
    monkeypatch.setattr(cog_mod.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    monkeypatch.setattr(automod_advanced_repo, "get_settings", AsyncMock(return_value=SimpleNamespace(exempt_channel_ids=(), exempt_role_ids=())))
    monkeypatch.setattr(cog_mod.bot_roles, "cancella_messaggio", azioni.cancella)
    monkeypatch.setattr(cog_mod.bot_roles, "isola", azioni.isola)
    monkeypatch.setattr(cog_mod, "try_dm", dm)
    monkeypatch.setattr(cog_mod, "post_to_mod_log", modlog)
    monkeypatch.setattr(cog_mod.libreria_immagini, "segnala", segnala)
    monkeypatch.setattr(cog_mod, "lingua_risposta", AsyncMock(return_value="it"))
    return SimpleNamespace(cog=cog, msg=msg, membro=membro, guild=guild, log=log, azioni=azioni, dm=dm, modlog=modlog, segnala=segnala)


def esito(verdetto, **kw):
    return pl.EsitoImmagine(verdetto, "ab" * 32, kw.pop("motivi", ("coda_firma_archivio",)), **kw)


def analisi(monkeypatch, e):
    monkeypatch.setattr(cog_mod, "analizza_immagine", AsyncMock(return_value=e))


@pytest.mark.asyncio
async def test_immagine_pulita_non_fa_nulla(ambiente, monkeypatch):
    analisi(monkeypatch, esito("pulita", motivi=()))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.azioni.cancella.assert_not_called()
    ambiente.log.send.assert_not_called()


@pytest.mark.asyncio
async def test_malevola_cancella_avvisa_logga_senza_file_e_segnala(ambiente, monkeypatch):
    analisi(monkeypatch, esito("malevola"))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.azioni.cancella.assert_awaited_once_with(ambiente.msg)
    ambiente.dm.assert_awaited_once()
    ambiente.azioni.isola.assert_awaited_once()  # primo invio malevolo: timeout
    invio = ambiente.log.send.await_args.kwargs
    assert "file" not in invio and "files" not in invio
    embed = invio["embed"]
    assert any("abababababababab" in f.value for f in embed.fields)
    ambiente.segnala.assert_awaited_once()


@pytest.mark.asyncio
async def test_senza_canale_di_log_si_usa_il_registro_di_moderazione(ambiente, monkeypatch):
    cog_mod.opzioni_immagini.leggi.return_value = op.OpzioniImmagini(True, "cancella", 10, None)
    analisi(monkeypatch, esito("sospetta"))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.modlog.assert_awaited_once()
    ambiente.azioni.isola.assert_not_called()


@pytest.mark.asyncio
async def test_azione_avvisa_non_cancella(ambiente, monkeypatch):
    cog_mod.opzioni_immagini.leggi.return_value = op.OpzioniImmagini(True, "avvisa", 10, 222)
    analisi(monkeypatch, esito("sospetta"))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.azioni.cancella.assert_not_called()
    ambiente.msg.channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_filtro_spento_non_scarica_nulla(ambiente, monkeypatch):
    cog_mod.opzioni_immagini.leggi.return_value = op.OpzioniImmagini(False)
    analisi(monkeypatch, esito("malevola"))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.msg.attachments[0].read.assert_not_called()


@pytest.mark.parametrize("caso", ["gestisce_server", "amministratore", "proprietario", "canale_esente", "ruolo_esente"])
@pytest.mark.asyncio
async def test_staff_ed_esenti_si_controllano_come_tutti(ambiente, monkeypatch, caso):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    # Un account staff rubato e' il caso tipico (D63): le esenzioni AutoMod non valgono per questo filtro.
    analisi(monkeypatch, esito("malevola"))
    ruolo = MagicMock(id=999)
    ambiente.membro.roles = [ruolo]
    if caso == "gestisce_server":
        ambiente.membro.guild_permissions = discord.Permissions(manage_guild=True)
    elif caso == "amministratore":
        ambiente.membro.guild_permissions = discord.Permissions(administrator=True)
    elif caso == "proprietario":
        ambiente.guild.owner_id = ambiente.membro.id
    elif caso == "canale_esente":
        automod_advanced_repo.get_settings.return_value = SimpleNamespace(exempt_channel_ids=(ambiente.msg.channel.id,), exempt_role_ids=())
    else:
        automod_advanced_repo.get_settings.return_value = SimpleNamespace(exempt_channel_ids=(), exempt_role_ids=(999,))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.azioni.cancella.assert_awaited_once_with(ambiente.msg)
    ambiente.dm.assert_awaited_once()
    ambiente.azioni.isola.assert_awaited_once()
    ambiente.log.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_bot_e_messaggi_senza_immagini_ignorati(ambiente, monkeypatch):
    analisi(monkeypatch, esito("malevola"))
    ambiente.membro.bot = True
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.membro.bot = False
    ambiente.msg.attachments = [allegato("note.txt", "text/plain")]
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.azioni.cancella.assert_not_called()


@pytest.mark.asyncio
async def test_allegato_enorme_non_si_scarica(ambiente, monkeypatch):
    analisi(monkeypatch, esito("malevola"))
    ambiente.msg.attachments = [allegato(size=50 * 1024 * 1024)]
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.msg.attachments[0].read.assert_not_called()


@pytest.mark.asyncio
async def test_coda_piena_account_nuovo_riprova(ambiente, monkeypatch):
    ambiente.membro.created_at = discord.utils.utcnow() - timedelta(days=2)
    monkeypatch.setattr(ambiente.cog, "_avvisa_owner", AsyncMock())
    analisi(monkeypatch, pl.EsitoImmagine(non_analizzata=pl.NON_ANALIZZATA_CODA))
    await ambiente.cog.on_message(ambiente.msg)
    ambiente.azioni.cancella.assert_awaited_once()
    ambiente.segnala.assert_not_called()


@pytest.mark.asyncio
async def test_errore_nel_filtro_non_esce_dal_listener(ambiente, monkeypatch):
    monkeypatch.setattr(cog_mod, "analizza_immagine", AsyncMock(side_effect=RuntimeError("boom")))
    await ambiente.cog.on_message(ambiente.msg)  # non solleva


@pytest.mark.asyncio
async def test_comando_owner_solo_per_il_proprietario(ambiente):
    inter = fake_interaction(user=fake_member(42))
    scelta = cog_mod.AZIONI_LIBRERIA[0]
    await ambiente.cog.libreria.callback(ambiente.cog, inter, scelta, None, None)
    inter.response.send_message.assert_awaited_once()
    assert inter.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_comando_owner_approva_e_aggiunge(ambiente, clean_db, monkeypatch):
    import core.database as database_module
    from core.immagini_trappola_service import LibreriaImmagini
    from core.repositories.immagini_trappola_repo import ImmaginiTrappolaRepository

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    lib = LibreriaImmagini(repo=ImmaginiTrappolaRepository(pool_provider=lambda: clean_db))
    monkeypatch.setattr(cog_mod, "libreria_immagini", lib)
    sha = "ef" * 32
    inter = fake_interaction(user=fake_member(cog_mod.config.OWNER_ID))
    scelte = {c.value: c for c in cog_mod.AZIONI_LIBRERIA}
    await ambiente.cog.libreria.callback(ambiente.cog, inter, scelte["aggiungi"], sha, None)
    assert (await lib.cerca_sha(sha, 1)).stato == "approvata"
    await lib.imposta_stato(sha, "candidata")
    await ambiente.cog.libreria.callback(ambiente.cog, inter, scelte["approva"], sha[:8], None)
    assert (await lib.cerca_sha(sha, 1)).stato == "approvata"
    await ambiente.cog.libreria.callback(ambiente.cog, inter, scelte["rifiuta"], "123456", None)
    assert "libreria" in inter.response.send_message.await_args.args[0]  # prefisso assente: «non è in libreria»
    await ambiente.cog.libreria.callback(ambiente.cog, inter, scelte["elenca"], None, None)
    assert "approvata: 1" in inter.response.send_message.await_args.args[0]
