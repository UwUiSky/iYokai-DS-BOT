"""
tests/test_tickets_transcript.py
================================
Transcript alla chiusura di un ticket (M 6.8, BUG-5, LIM-55):
- con l'intent Message Content acceso (come in main.py) il transcript
  contiene il testo dei messaggi e i nomi degli allegati;
- con l'intent spento Discord consegna i messaggi vuoti: il transcript
  lo dice in testa invece di sembrare un ticket senza testo;
- un transcript grande viene diviso in più file, ognuno sotto il
  limite di peso.

Database vero (clean_db); il ticket si apre e si chiude con il codice di
produzione. Il bot è un `commands.Bot` vero, non collegato.
"""

import datetime
from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from cogs.logging.basic_logs import SETTING_LOG_CHANNEL
from cogs.tickets.tickets import TicketsCog, _open_ticket_channel
from core.database import db
from core.scheduler import Scheduler
from core.ticket_logic import split_text_by_size
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)

ID_SERVER = 100
ID_UTENTE = 20
ID_CANALE_LOG = 7001
DIECI_MIB = 10 * 1024 * 1024


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    await db.set_guild_setting(ID_SERVER, SETTING_LOG_CHANNEL, ID_CANALE_LOG)
    yield
    database_module.db._modules_cache.clear()


def _bot(message_content: bool = True) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = message_content
    return commands.Bot(command_prefix="!", intents=intents)


def _messaggio(nome: str, testo: str, allegati: tuple[str, ...] = ()):
    autore = fake_member(name=nome)
    autore.__str__ = lambda self: nome
    messaggio = fake_message(author=autore, content=testo)
    messaggio.created_at = datetime.datetime(2026, 10, 5, 9, 30, tzinfo=datetime.timezone.utc)
    messaggio.attachments = []
    for nome_file in allegati:
        allegato = create_autospec(discord.Attachment, instance=True)
        allegato.filename = nome_file
        messaggio.attachments.append(allegato)
    return messaggio


class Scena:
    def __init__(self, messaggi) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.utente = fake_member(ID_UTENTE)
        self.utente.guild = self.guild
        self.guild.get_member.side_effect = lambda uid: self.utente if uid == ID_UTENTE else None
        self.canale_log = fake_text_channel(ID_CANALE_LOG, "log")
        self.guild.get_channel.side_effect = (
            lambda cid: self.canale_log if cid == ID_CANALE_LOG else None
        )
        self.canale = fake_text_channel(1000, "ticket-0001")

        async def _storia():
            for messaggio in messaggi:
                yield messaggio

        self.canale.history.side_effect = lambda **kwargs: _storia()
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.create_text_channel.return_value = self.canale

    async def apri_e_chiudi(self, cog) -> None:
        apertura = fake_interaction(guild=self.guild, user=self.utente)
        await _open_ticket_channel(apertura, self.guild, self.categoria, "Supporto")
        chiusura = fake_interaction(guild=self.guild, user=self.utente, channel=self.canale)
        await cog.close.callback(cog, chiusura)

    def file_nel_log(self) -> list[tuple[str, str]]:
        return _file_inviati(self.canale_log.send)

    def file_in_dm(self) -> list[tuple[str, str]]:
        return _file_inviati(self.utente.send)


def _file_inviati(finto) -> list[tuple[str, str]]:
    """(nome, contenuto) di ogni file mandato, nell'ordine di invio."""
    inviati = []
    for chiamata in finto.call_args_list:
        file = chiamata.kwargs["file"]
        inviati.append((file.filename, file.fp.read().decode("utf-8")))
    return inviati


async def test_il_transcript_contiene_il_testo_e_gli_allegati():
    scena = Scena(
        [
            _messaggio("mario", "Non riesco a entrare nel vocale"),
            _messaggio("staff", "Prova a riavviare Discord"),
            _messaggio("mario", "", allegati=("schermata.png", "log.txt")),
        ]
    )

    await scena.apri_e_chiudi(TicketsCog(_bot()))

    for inviati in (scena.file_nel_log(), scena.file_in_dm()):
        assert len(inviati) == 1
        nome, testo = inviati[0]
        assert nome == "ticket-0001-transcript.txt"
        assert "mario: Non riesco a entrare nel vocale" in testo
        assert "staff: Prova a riavviare Discord" in testo
        assert "schermata.png" in testo and "log.txt" in testo
        assert "Message Content" not in testo


async def test_con_l_intent_spento_il_transcript_lo_dice_in_testa():
    """Senza l'intent Discord consegna `content` vuoto anche via REST."""
    scena = Scena([_messaggio("mario", ""), _messaggio("staff", "")])

    await scena.apri_e_chiudi(TicketsCog(_bot(message_content=False)))

    _, testo = scena.file_nel_log()[0]
    intestazione = testo.split("\n\n")[0]
    assert "Message Content" in intestazione
    assert "ATTENZIONE" in intestazione


async def test_un_transcript_grande_viene_diviso_in_file_sotto_il_limite(monkeypatch):
    monkeypatch.setattr(modulo, "MAX_TRANSCRIPT_FILE_BYTES", 2000)
    messaggi = [_messaggio("mario", f"messaggio {n:03d} " + "è" * 80) for n in range(60)]
    scena = Scena(messaggi)

    await scena.apri_e_chiudi(TicketsCog(_bot()))

    for inviati in (scena.file_nel_log(), scena.file_in_dm()):
        assert len(inviati) > 1
        tutto = ""
        for numero, (nome, testo) in enumerate(inviati, start=1):
            assert nome == f"ticket-0001-transcript-parte-{numero}-di-{len(inviati)}.txt"
            assert len(testo.encode("utf-8")) <= 2000
            tutto += testo
        for n in range(60):
            assert f"messaggio {n:03d}" in tutto


def test_il_limite_di_peso_resta_sotto_dieci_mib():
    assert modulo.MAX_TRANSCRIPT_FILE_BYTES < DIECI_MIB


def test_dividi_testo_rispetta_i_byte_non_i_caratteri():
    testo = "\n".join("è" * 50 for _ in range(10)) + "\n"  # "è" pesa 2 byte

    parti = split_text_by_size(testo, max_bytes=250)

    assert len(parti) > 1
    assert all(len(parte.encode("utf-8")) <= 250 for parte in parti)
    assert "".join(parti) == testo


def test_dividi_testo_una_riga_piu_lunga_del_limite_viene_spezzata():
    parti = split_text_by_size("x" * 1000 + "\nfine\n", max_bytes=300)

    assert all(len(parte.encode("utf-8")) <= 300 for parte in parti)
    assert "".join(parti) == "x" * 1000 + "\nfine\n"


def test_dividi_testo_corto_resta_un_solo_pezzo():
    assert split_text_by_size("ciao\n", max_bytes=300) == ["ciao\n"]


async def test_un_file_rifiutato_non_ferma_il_dm_all_utente():
    scena = Scena([_messaggio("mario", "ciao")])
    scena.canale_log.send.side_effect = discord.HTTPException(
        MagicMock(status=413, reason="Payload Too Large"), "troppo grande"
    )

    await scena.apri_e_chiudi(TicketsCog(_bot()))

    assert len(scena.file_in_dm()) == 1
