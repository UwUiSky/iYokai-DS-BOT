"""
tests/test_message_logs.py
==========================
Log dei messaggi (NF-02): cancellato, modificato, cancellato in blocco.
Tagli ai limiti di Discord, cose ignorate, file sotto i 10 MiB.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.logging.message_logs as modulo
from core.database import Database
from core.message_log_logic import (
    FILE_MAX_BYTE,
    Ignorati,
    MessaggioArchiviato,
    da_ignorare,
    file_blocco,
    normalizza_prefisso,
    tronca,
)
from core.repositories.event_log_repo import EventLogRepository
from core.repositories.log_ignora_repo import LogIgnoraRepository
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel

GUILD = 500
CANALE = 11


# ---------------------------------------------------------------- logica
def test_tronca_rispetta_il_limite_e_lo_dice():
    assert tronca("ciao", 10) == "ciao"
    t = tronca("x" * 5000, 1024)
    assert len(t) == 1024 and t.endswith("…")


def test_ignorati_canale_categoria_thread_utente_prefisso():
    ig = Ignorati(canali=frozenset({1, 2, 3}), utenti=frozenset({9}), prefissi=("!", "?"))
    base = dict(channel_id=50, author_id=8, testo="ciao")
    assert not da_ignorare(ig, **base)
    assert da_ignorare(ig, **{**base, "channel_id": 1})
    assert da_ignorare(ig, **base, category_id=2)
    assert da_ignorare(ig, **base, thread_parent_id=3)
    assert da_ignorare(ig, **{**base, "author_id": 9})
    assert da_ignorare(ig, **{**base, "testo": "!play x"})
    assert not da_ignorare(ig, **{**base, "testo": "ciao !"})


def test_prefisso_vuoto_o_lungo_e_rifiutato():
    assert normalizza_prefisso("  ! ") == "!"
    assert normalizza_prefisso("   ") is None
    assert normalizza_prefisso("x" * 21) is None


def test_file_del_blocco_resta_sotto_il_limite_di_peso():
    grandi = [
        MessaggioArchiviato(i, 1, "Mario", "ò" * 500, "2026-10-11 10:00:00") for i in range(20_000)
    ]
    dati = file_blocco(grandi, 0)
    assert len(dati) < FILE_MAX_BYTE
    assert b"righe omesse" in dati


# ------------------------------------------------------------------- cog
@pytest.fixture
def ambiente(monkeypatch):
    canale_log = fake_text_channel(channel_id=999)
    canale_log.send = AsyncMock()
    server = fake_guild(guild_id=GUILD)
    canale_msg = fake_text_channel(channel_id=CANALE)
    server.get_channel_or_thread = MagicMock(return_value=canale_msg)
    bot = MagicMock()
    bot.get_guild.return_value = server

    db_finto = create_autospec(Database, instance=True)
    db_finto.get_guild_setting.return_value = 999
    monkeypatch.setattr(modulo, "db", db_finto)
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=True))
    ignora = create_autospec(LogIgnoraRepository, instance=True)
    ignora.carica.return_value = Ignorati()
    monkeypatch.setattr(modulo, "log_ignora_repo", ignora)
    eventi = create_autospec(EventLogRepository, instance=True)
    monkeypatch.setattr(modulo, "event_log_repo", eventi)
    monkeypatch.setattr(modulo.router, "destinazione", AsyncMock(return_value=canale_log))
    cog = modulo.MessageLogsCog(bot)
    return cog, canale_log, ignora, eventi, server


def _messaggio(testo="ciao", autore_bot=False, allegati=()):
    m = MagicMock()
    m.id = 70
    m.content = testo
    m.author = fake_member(user_id=42, bot=autore_bot)
    m.author.id = 42
    m.attachments = [MagicMock(filename=n) for n in allegati]
    return m


def _payload_delete(messaggio):
    p = MagicMock()
    p.guild_id = GUILD
    p.channel_id = CANALE
    p.message_id = 70
    p.cached_message = messaggio
    return p


async def test_cancellato_in_cache_mostra_autore_testo_e_allegati(ambiente):
    cog, canale_log, _, eventi, _ = ambiente
    await cog.on_raw_message_delete(_payload_delete(_messaggio("addio", allegati=["a.png"])))
    embed = canale_log.send.call_args.kwargs["embed"]
    assert embed.description == "addio"
    campi = {c.name: c.value for c in embed.fields}
    assert "42" in campi["Autore"] and "a.png" in campi["Allegati"]
    eventi.log_event.assert_awaited_once()
    assert "addio" not in str(eventi.log_event.await_args)  # nessun testo nel database


async def test_cancellato_molto_lungo_resta_un_embed_valido(ambiente):
    cog, canale_log, *_ = ambiente
    await cog.on_raw_message_delete(_payload_delete(_messaggio("x" * 6000)))
    embed = canale_log.send.call_args.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert len(embed) <= 6000


async def test_cancellato_fuori_cache_lo_dice_senza_contenuto(ambiente):
    cog, canale_log, *_ = ambiente
    await cog.on_raw_message_delete(_payload_delete(None))
    embed = canale_log.send.call_args.kwargs["embed"]
    assert "non disponibile" in embed.description


async def test_messaggio_di_un_bot_non_viene_registrato(ambiente):
    cog, canale_log, *_ = ambiente
    await cog.on_raw_message_delete(_payload_delete(_messaggio(autore_bot=True)))
    canale_log.send.assert_not_awaited()


async def test_canale_ignorato_non_viene_registrato(ambiente):
    cog, canale_log, ignora, *_ = ambiente
    ignora.carica.return_value = Ignorati(canali=frozenset({CANALE}))
    await cog.on_raw_message_delete(_payload_delete(_messaggio()))
    canale_log.send.assert_not_awaited()


async def test_senza_logging_avanzato_non_scrive(ambiente, monkeypatch):
    cog, canale_log, *_ = ambiente
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=False))
    await cog.on_raw_message_delete(_payload_delete(_messaggio()))
    canale_log.send.assert_not_awaited()


async def test_modifica_mostra_prima_e_dopo_tagliati_a_1024(ambiente):
    cog, canale_log, *_ = ambiente
    prima, dopo = _messaggio("a" * 3000), _messaggio("b" * 3000)
    dopo.guild = prima.guild = ambiente[4]
    dopo.channel = prima.channel = fake_text_channel(channel_id=CANALE)
    dopo.jump_url = "https://discord.com/x"
    await cog.on_message_edit(prima, dopo)
    campi = {c.name: c.value for c in canale_log.send.call_args.kwargs["embed"].fields}
    assert len(campi["Prima"]) == 1024 and len(campi["Dopo"]) == 1024


async def test_modifica_senza_cambio_di_testo_e_ignorata(ambiente):
    cog, canale_log, *_ = ambiente
    m = _messaggio("uguale")
    m.guild = ambiente[4]
    await cog.on_message_edit(m, m)
    canale_log.send.assert_not_awaited()


async def test_blocco_un_solo_riepilogo_con_un_file(ambiente):
    cog, canale_log, *_ = ambiente
    cache = []
    for n in range(3):
        m = _messaggio(f"testo {n}")
        m.id = 100 + n
        m.created_at = discord.utils.utcnow()
        cache.append(m)
    p = MagicMock()
    p.guild_id, p.channel_id = GUILD, CANALE
    p.message_ids = {100, 101, 102, 103, 104}
    p.cached_messages = cache
    await cog.on_raw_bulk_message_delete(p)
    canale_log.send.assert_awaited_once()
    kw = canale_log.send.call_args.kwargs
    assert "5" in kw["embed"].description and "2" in kw["embed"].description
    assert kw["file"].filename == "messaggi_cancellati.txt"
    assert b"testo 1" in kw["file"].fp.getvalue()


# ---------------------------------------------------- rafforzamento (revisione)
from core import message_log_logic as logica
from core.message_log_logic import riga_blocco, senza_accento_grave


@pytest.fixture(autouse=True)
def _eventi_accesi(monkeypatch):
    """LOG-017: senza database tutti gli eventi sono accesi."""
    from tests.support.router_fakes import nessun_evento_spento

    nessun_evento_spento(monkeypatch)


async def test_senza_logging_avanzato_modifica_e_blocco_non_scrivono(ambiente, monkeypatch):
    cog, canale_log, _, _, server = ambiente
    monkeypatch.setattr(modulo, "logging_avanzato_attivo", AsyncMock(return_value=False))
    prima, dopo = _messaggio("a"), _messaggio("b")
    prima.guild = dopo.guild = server
    await cog.on_message_edit(prima, dopo)
    p = MagicMock(guild_id=GUILD, channel_id=CANALE, message_ids={1}, cached_messages=[_messaggio("x")])
    await cog.on_raw_bulk_message_delete(p)
    canale_log.send.assert_not_awaited()


async def test_blocco_toglie_dal_file_i_messaggi_ignorati_e_dei_bot(ambiente):
    cog, canale_log, ignora, _, _ = ambiente
    ignora.carica.return_value = Ignorati(utenti=frozenset({7}))
    visibile, ignorato, bot = _messaggio("visibile"), _messaggio("ignorato"), _messaggio("di bot", autore_bot=True)
    for n, (m, uid) in enumerate([(visibile, 42), (ignorato, 7), (bot, 43)]):
        m.id, m.author.id = 100 + n, uid
        m.created_at = discord.utils.utcnow()
    p = MagicMock(guild_id=GUILD, channel_id=CANALE, message_ids={100, 101, 102}, cached_messages=[visibile, ignorato, bot])
    await cog.on_raw_bulk_message_delete(p)
    dati = canale_log.send.call_args.kwargs["file"].fp.getvalue()
    assert b"visibile" in dati and b"ignorato" not in dati and b"di bot" not in dati


async def test_blocco_dentro_un_canale_ignorato_non_scrive(ambiente):
    cog, canale_log, ignora, _, _ = ambiente
    ignora.carica.return_value = Ignorati(canali=frozenset({CANALE}))
    p = MagicMock(guild_id=GUILD, channel_id=CANALE, message_ids={1}, cached_messages=[])
    await cog.on_raw_bulk_message_delete(p)
    canale_log.send.assert_not_awaited()


async def test_tre_accenti_gravi_nel_testo_non_chiudono_un_blocco_di_codice(ambiente):
    cog, canale_log, *_ = ambiente
    assert "```" not in senza_accento_grave("a ```code``` b")
    await cog.on_raw_message_delete(_payload_delete(_messaggio("x ```y``` z")))
    assert "```" not in canale_log.send.call_args.kwargs["embed"].description


async def test_modifica_di_un_bot_non_si_registra_e_non_interroga_gli_ignorati(ambiente):
    cog, canale_log, ignora, _, server = ambiente
    prima, dopo = _messaggio("a", autore_bot=True), _messaggio("b", autore_bot=True)
    prima.guild = dopo.guild = server
    await cog.on_message_edit(prima, dopo)
    canale_log.send.assert_not_awaited()
    ignora.carica.assert_not_awaited()


def test_nomi_degli_allegati_con_accento_grave_e_righe_con_a_capo():
    assert "`a'b.png`" in logica.testo_allegati(["a`b.png"])
    riga = riga_blocco(MessaggioArchiviato(1, 2, "Mario", "uno\ndue", "2026-10-11 10:00:00"))
    assert "uno ⏎ due" in riga and "\n" not in riga


def test_elenco_degli_ignorati_lunghissimo_resta_sotto_1900():
    ig = Ignorati(canali=frozenset(range(10**18, 10**18 + 300)))
    assert len(logica.testo_elenco_ignorati(ig)) <= 1900


async def test_due_aggiunte_insieme_con_un_posto_solo_ne_entra_una(clean_db):
    import asyncio

    repo = LogIgnoraRepository(pool_provider=lambda: clean_db)
    esiti = await asyncio.gather(
        repo.aggiungi(GUILD, "canale", "1", 1), repo.aggiungi(GUILD, "canale", "2", 1)
    )
    assert sorted(esiti) == [False, True]


async def test_gli_ignorati_si_tengono_in_memoria_e_si_rileggono_dopo_una_scrittura(clean_db):
    repo = LogIgnoraRepository(pool_provider=lambda: clean_db)
    letture = []
    originale = repo._leggi

    async def spia(guild_id):
        letture.append(guild_id)
        return await originale(guild_id)

    repo._leggi = spia
    await repo.carica(GUILD)
    await repo.carica(GUILD)
    assert len(letture) == 1
    await repo.aggiungi(GUILD, "utente", "9", 10)
    assert (await repo.carica(GUILD)).utenti == frozenset({9})
    await repo.rimuovi(GUILD, "utente", "9")
    assert (await repo.carica(GUILD)).utenti == frozenset()
    assert len(letture) == 3


async def test_modifica_il_cui_testo_di_prima_va_ignorato_non_si_scrive(ambiente):
    """Cacciatore-bug: 'password: hunter2' -> 'ok' mostrava il testo da ignorare nel campo Prima."""
    cog, canale_log, ignora, _, server = ambiente
    ignora.carica.return_value = Ignorati(regex=("password",))
    prima, dopo = _messaggio("password: hunter2"), _messaggio("ok")
    prima.guild = dopo.guild = server
    prima.channel = dopo.channel = fake_text_channel(channel_id=CANALE)
    await cog.on_message_edit(prima, dopo)
    canale_log.send.assert_not_awaited()
