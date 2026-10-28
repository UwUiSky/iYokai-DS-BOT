"""
tests/test_log_catalogo_r7.py
=============================
Catalogo log (#119), giro r7: inviti scritti nei messaggi (LOG-005), messaggi
fissati (LOG-006), chi scollega o sposta a forza in vocale (LOG-012), ogni
evento acceso o spento (LOG-017), archivio di un canale con i messaggi
appena cancellati (LOG-027, LOG-030); mod-log e AutoMod dal router (§18.1).
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.advanced_logs as advanced
import cogs.logging.basic_logs as basic
import cogs.logging.log_config as config
import cogs.logging.logs_query as query
import cogs.logging.message_logs as messaggi
from core import bot_roles
from core import log_eventi_logic as eventi
from core import message_log_logic as logica
from core.channel_router import TIPO_MESSAGGI, TIPO_VOCE
from core.message_log_logic import Ignorati
from core.repositories.log_eventi_repo import LogEventiRepository, log_eventi_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel

SERVER = 700


def _spenti(monkeypatch, *chiavi):
    async def finto(_guild_id):
        return frozenset(chiavi)

    monkeypatch.setattr(log_eventi_repo, "spenti", finto)


@pytest.fixture(autouse=True)
def _tutti_accesi(monkeypatch):
    """Senza database tutti gli eventi sono accesi; i test che spengono usano _spenti."""
    _spenti(monkeypatch)


# ====================================================================
# LOG-017 — interruttori
# ====================================================================
def test_ogni_evento_dei_log_ha_un_interruttore_e_stanno_in_un_menu():
    assert len(eventi.INTERRUTTORI) <= 25
    assert all(len(etichetta) <= 100 for etichetta, _ in eventi.INTERRUTTORI.values())
    for evento in advanced.EVENT_TITLES:
        assert eventi.interruttore_di(evento) is not None, evento
    for evento in ("member_join", "member_remove", "member_ban", "member_unban", "role_update",
                   "nickname_update", "timeout_update", "avatar_update", "role_create", "role_delete",
                   "message_delete", "message_bulk_delete", "message_edit", "invite_posted"):
        assert eventi.interruttore_di(evento) is not None, evento


def test_scelte_rapide():
    assert eventi.spenti_da_scelta("tutto") == frozenset()
    assert eventi.spenti_da_scelta("niente") == frozenset(eventi.INTERRUTTORI)
    assert eventi.spenti_da_scelta("predefinito") == frozenset({"voce_propri"})
    assert eventi.spenti_da_scelta("elenco", ["ingressi"]) == frozenset(eventi.INTERRUTTORI) - {"ingressi"}
    assert not eventi.acceso("voice_self_mute", frozenset({"voce_propri"}))
    assert eventi.acceso("evento_senza_interruttore", frozenset(eventi.INTERRUTTORI))


@pytest.mark.asyncio
async def test_repository_salva_e_rilegge(clean_db):
    repo = LogEventiRepository(pool_provider=lambda: clean_db)
    assert await repo.spenti(SERVER) == frozenset()
    await repo.imposta(SERVER, frozenset({"ingressi", "voce"}))
    assert await repo.spenti(SERVER) == frozenset({"ingressi", "voce"})
    assert not await repo.evento_acceso(SERVER, "voice_join")
    assert await repo.evento_acceso(SERVER, "member_ban")
    await repo.imposta(SERVER, frozenset())
    assert await repo.spenti(SERVER) == frozenset()


@pytest.mark.asyncio
async def test_lettura_lenta_non_rimette_in_cache_gli_interruttori_vecchi(clean_db):
    """Un evento legge (vecchio), l'admin spegne, la lettura finisce: la cache non torna indietro."""
    via = asyncio.Event()
    letto = asyncio.Event()

    class PoolLento:
        async def fetch(self, *args):
            righe = await clean_db.fetch(*args)
            letto.set()
            await via.wait()
            return righe

        def acquire(self):
            return clean_db.acquire()

    repo = LogEventiRepository(pool_provider=PoolLento)
    lettura = asyncio.create_task(repo.spenti(SERVER))
    await letto.wait()
    await repo.imposta(SERVER, frozenset({"ingressi"}))
    via.set()
    assert await lettura == frozenset()
    assert not await repo.evento_acceso(SERVER, "member_join")


@pytest.mark.asyncio
async def test_evento_spento_non_arriva_nel_canale(monkeypatch):
    _spenti(monkeypatch, "ingressi")
    invio = AsyncMock()
    monkeypatch.setattr(basic.router, "invia_a", invio)
    canale = fake_text_channel()
    canale.guild = fake_guild(guild_id=SERVER)
    await basic._send_log(canale, discord.Embed(title="x"), "member_join")
    invio.assert_not_awaited()
    await basic._send_log(canale, discord.Embed(title="x"), "member_ban")
    invio.assert_awaited_once()


@pytest.mark.asyncio
async def test_evento_avanzato_spento_non_cerca_nemmeno_il_canale(monkeypatch):
    _spenti(monkeypatch, "emoji")
    canale = AsyncMock(return_value=None)
    monkeypatch.setattr(advanced, "advanced_log_channel", canale)
    await advanced.send_event_embed(fake_guild(guild_id=SERVER), "sticker_create", "x")
    canale.assert_not_awaited()


@pytest.mark.asyncio
async def test_vista_eventi_salva_scelte_e_scelte_rapide(monkeypatch):
    imposta = AsyncMock()
    monkeypatch.setattr(log_eventi_repo, "imposta", imposta)
    vista = config.VistaEventi(autore_id=1, guild_id=SERVER, spenti=frozenset())
    assert len(vista.menu.options) == len(eventi.INTERRUTTORI)
    assert all(o.default for o in vista.menu.options)
    i = fake_interaction()
    vista.menu._values = ["ingressi", "ban"]
    await vista._scelti(i)
    assert imposta.await_args.args == (SERVER, frozenset(eventi.INTERRUTTORI) - {"ingressi", "ban"})
    nuova = i.response.edit_message.await_args.kwargs["view"]
    assert {o.value for o in nuova.menu.options if o.default} == {"ingressi", "ban"}
    await vista._rapida("predefinito")(fake_interaction())
    assert imposta.await_args.args == (SERVER, frozenset({"voce_propri"}))


@pytest.mark.asyncio
async def test_vista_eventi_solo_per_chi_l_ha_aperta(monkeypatch):
    monkeypatch.setattr(config.BaseView, "interaction_check", AsyncMock(return_value=True))
    vista = config.VistaEventi(autore_id=1, guild_id=SERVER, spenti=frozenset())
    assert await vista.interaction_check(fake_interaction(user=fake_member(user_id=1)))
    assert not await vista.interaction_check(fake_interaction(user=fake_member(user_id=2)))


# ====================================================================
# LOG-005 — inviti scritti nei messaggi
# ====================================================================
@pytest.fixture
def cog_messaggi(monkeypatch):
    _spenti(monkeypatch)
    monkeypatch.setattr(messaggi, "logging_avanzato_attivo", AsyncMock(return_value=True))
    ignora = MagicMock()
    ignora.carica = AsyncMock(return_value=Ignorati())
    monkeypatch.setattr(messaggi, "log_ignora_repo", ignora)
    monkeypatch.setattr(messaggi.event_log_repo, "log_event", AsyncMock())
    canale_log = fake_text_channel(channel_id=999)
    monkeypatch.setattr(messaggi.db, "get_guild_setting", AsyncMock(return_value=999))
    monkeypatch.setattr(messaggi.router, "destinazione", AsyncMock(return_value=canale_log))
    invio = AsyncMock(return_value=True)
    monkeypatch.setattr(messaggi.router, "invia_a", invio)
    return messaggi.MessageLogsCog(MagicMock()), invio


@pytest.mark.asyncio
async def test_invito_scritto_si_registra(cog_messaggi):
    cog, invio = cog_messaggi
    m = fake_message(guild=fake_guild(guild_id=SERVER), content="entra su discord.gg/abcde e https://discord.com/invite/xyz12")
    m.author.bot = False
    m.jump_url = "https://discord.com/channels/1/2/3"
    await cog.on_message(m)
    embed = invio.await_args.kwargs["embed"]
    assert "Invito" in embed.title
    assert "discord.gg/abcde" in embed.fields[2].value and "discord.gg/xyz12" in embed.fields[2].value
    messaggi.event_log_repo.log_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_messaggio_senza_inviti_o_di_un_bot_non_si_registra(cog_messaggi):
    cog, invio = cog_messaggi
    m = fake_message(guild=fake_guild(guild_id=SERVER), content="ciao a tutti")
    m.author.bot = False
    await cog.on_message(m)
    bot = fake_message(guild=fake_guild(guild_id=SERVER), content="discord.gg/abcde")
    bot.author.bot = True
    await cog.on_message(bot)
    invio.assert_not_awaited()


@pytest.mark.asyncio
async def test_inviti_scritti_spenti_non_si_registrano(cog_messaggi, monkeypatch):
    cog, invio = cog_messaggi
    _spenti(monkeypatch, "inviti_scritti")
    m = fake_message(guild=fake_guild(guild_id=SERVER), content="discord.gg/abcde")
    m.author.bot = False
    await cog.on_message(m)
    invio.assert_not_awaited()


# ====================================================================
# LOG-006 e LOG-012 — dal registro di controllo
# ====================================================================
def _voce(azione, extra, target=None, utente=42):
    return SimpleNamespace(action=azione, guild=fake_guild(guild_id=SERVER), extra=extra, target=target, user_id=utente)


@pytest.mark.asyncio
async def test_fissato_e_scollegato_a_forza(monkeypatch):
    monkeypatch.setattr(advanced, "logging_avanzato_attivo", AsyncMock(return_value=True))
    monkeypatch.setattr(advanced.event_log_repo, "log_event", AsyncMock())
    invio = AsyncMock()
    monkeypatch.setattr(advanced, "send_event_embed", invio)
    cog = advanced.AdvancedLogsCog(bot=MagicMock())
    canale = fake_text_channel(channel_id=5)
    await cog.on_audit_log_entry_create(_voce(
        discord.AuditLogAction.message_pin, SimpleNamespace(channel=canale, message_id=77), target=fake_member(user_id=9)
    ))
    guild, evento, testo = invio.await_args.args
    assert evento == "message_pin" and "<@42>" in testo and "<@9>" in testo and "77" in testo
    assert invio.await_args.kwargs["tipo"] == TIPO_MESSAGGI
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.member_disconnect, SimpleNamespace(count=1)))
    assert invio.await_args.args[1] == "voice_force_disconnect"
    assert invio.await_args.kwargs["tipo"] == TIPO_VOCE
    await cog.on_audit_log_entry_create(_voce(
        discord.AuditLogAction.member_move, SimpleNamespace(channel=canale, count=1)
    ))
    assert invio.await_args.args[1] == "voice_force_move" and "<#5>" in invio.await_args.args[2]
    # Altre voci del registro: niente.
    invio.reset_mock()
    await cog.on_audit_log_entry_create(_voce(discord.AuditLogAction.ban, None))
    invio.assert_not_awaited()


# ====================================================================
# LOG-027 e LOG-030 — archivio di un canale
# ====================================================================
def _archiviato(i, testo="ciao"):
    return logica.MessaggioArchiviato(i, 1, "utente", testo, "2026-10-15 10:00:00")


def test_cancellati_recenti_scadono_e_hanno_un_tetto():
    adesso = [0.0]
    memoria = logica.CancellatiRecenti(lambda: adesso[0])
    for i in range(logica.CANCELLATI_PER_CANALE + 5):
        memoria.aggiungi(1, _archiviato(i))
    assert len(memoria.di(1)) == logica.CANCELLATI_PER_CANALE
    adesso[0] = logica.CANCELLATI_SECONDI + 1
    assert memoria.di(1) == []


def test_archivio_in_ordine_con_i_cancellati_e_diviso_sotto_il_massimo():
    parti = logica.file_archivio("generale", [_archiviato(3), _archiviato(1)], [_archiviato(2, "via")], 10_000)
    assert len(parti) == 1
    testo = parti[0].decode()
    assert testo.index("#1") < testo.index("[cancellato]") < testo.index("#3")
    grandi = [_archiviato(i, "x" * 4000) for i in range(30)]
    parti = logica.file_archivio("generale", grandi, [], 20_000)
    assert len(parti) > 1 and all(len(p) <= 20_000 for p in parti)
    assert sum(p.decode().count("x" * 4000) for p in parti) == 30


@pytest.mark.asyncio
async def test_archivio_canale_manda_il_file_e_controlla_i_permessi(monkeypatch):
    _spenti(monkeypatch)
    cog = query.LogsQueryCog(MagicMock())
    canale = fake_text_channel(channel_id=31, name="generale")
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, read_message_history=True)
    vero = fake_message(message_id=10, content="primo")
    vero.created_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    vero.attachments = []

    async def storia(limit):
        assert limit == 50
        yield vero

    canale.history = storia
    messaggi.cancellati_recenti.aggiungi(31, _archiviato(11, "sparito"))
    i = fake_interaction(guild=fake_guild(guild_id=SERVER))
    await cog.archivio_canale.callback(cog, i, canale, 50)
    i.response.defer.assert_awaited_once()
    file = i.followup.send.await_args.kwargs["file"]
    testo = file.fp.read().decode()
    assert "primo" in testo and "[cancellato]" in testo and "sparito" in testo

    # Evento «messaggi cancellati» spento dopo: quelli in memoria non escono.
    _spenti(monkeypatch, "messaggi_cancellati")
    i = fake_interaction(guild=fake_guild(guild_id=SERVER))
    await cog.archivio_canale.callback(cog, i, canale, 50)
    testo = i.followup.send.await_args.kwargs["file"].fp.read().decode()
    assert "primo" in testo and "sparito" not in testo
    _spenti(monkeypatch)

    canale.permissions_for.return_value = discord.Permissions.none()
    i = fake_interaction(guild=fake_guild(guild_id=SERVER))
    await cog.archivio_canale.callback(cog, i, canale, 50)
    assert "Non puoi" in i.response.send_message.await_args.args[0]
    i.response.defer.assert_not_awaited()


# ====================================================================
# D15 — i canali creati da /log li vede anche iYokai Mod
# ====================================================================
def test_canali_riservati_visibili_anche_a_mod():
    guild = fake_guild(guild_id=SERVER)
    membro_mod = fake_member(user_id=4242, bot=True)
    guild.get_member.side_effect = {4242: membro_mod}.get
    mod = MagicMock(spec=discord.Client)
    mod.user = membro_mod
    bot_roles.registra_mod(mod)
    try:
        regole = config._riservato(guild)
    finally:
        bot_roles.registra_mod(None)
    assert regole[membro_mod].send_messages and regole[membro_mod].view_channel
    assert membro_mod not in config._riservato(guild)


def _canale_con_storia(lunghezza: int, letti: list, attesa: asyncio.Event | None = None):
    canale = fake_text_channel(channel_id=32, name="lungo")
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, read_message_history=True)

    async def storia(limit):
        if attesa is not None:
            await attesa.wait()
        for n in range(limit):
            m = fake_message(message_id=1000 + n, content="x" * lunghezza)
            m.created_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
            m.attachments = []
            letti.append(n)
            yield m

    canale.history = storia
    return canale


@pytest.mark.asyncio
async def test_archivio_si_ferma_oltre_il_tetto_di_testo(monkeypatch):
    """20.000 messaggi da 4000 caratteri non restano tutti in memoria."""
    monkeypatch.setattr(query, "ARCHIVIO_BYTE_MAX", 20_000)
    cog = query.LogsQueryCog(MagicMock())
    letti: list = []
    canale = _canale_con_storia(4000, letti)
    i = fake_interaction(guild=fake_guild(guild_id=SERVER))
    await cog.archivio_canale.callback(cog, i, canale, 500)
    assert len(letti) < 10
    testi = [c.args[0] for c in i.followup.send.await_args_list if c.args]
    assert any("Mi sono fermato" in t for t in testi)


@pytest.mark.asyncio
async def test_archivio_uno_alla_volta_per_server():
    cog = query.LogsQueryCog(MagicMock())
    via = asyncio.Event()
    canale = _canale_con_storia(10, [], via)
    primo = fake_interaction(guild=fake_guild(guild_id=SERVER))
    secondo = fake_interaction(guild=fake_guild(guild_id=SERVER))
    lavoro = asyncio.create_task(cog.archivio_canale.callback(cog, primo, canale, 5))
    await asyncio.sleep(0)
    await asyncio.wait_for(cog.archivio_canale.callback(cog, secondo, canale, 5), 1)
    assert "già" in secondo.response.send_message.await_args.args[0]
    secondo.response.defer.assert_not_awaited()
    via.set()
    await lavoro
    primo.followup.send.assert_awaited()


def test_evento_ignorato_canale_categoria_utente_ruolo():
    from core.message_log_logic import Ignorati, evento_ignorato

    ig = Ignorati(canali=frozenset({10}), utenti=frozenset({5}), ruoli=frozenset({77}), prefissi=("!",), regex=("x",))
    assert evento_ignorato(ig, channel_ids=[1, 10, None])
    assert evento_ignorato(ig, channel_ids=[None], user_id=5)
    assert evento_ignorato(ig, ruoli=[3, 77])
    assert not evento_ignorato(ig, channel_ids=[1, None], user_id=6, ruoli=[3])
    assert not evento_ignorato(Ignorati(), channel_ids=[10], user_id=5)
