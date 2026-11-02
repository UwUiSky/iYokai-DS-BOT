"""
tests/test_ticket_transcript_html.py
====================================
#120 (D66) blocco T2: transcript HTML sicuro, formato a scelta e ZIP con le sole immagini ricodificate
(TKT-070, 071, 074). Regole pure e invio nel cog.
"""

import re
import zipfile
import io

from core import ticket_transcript_logic as tr
from core.ticket_transcript_logic import AllegatoT, IntestazioneT, MessaggioT

H = IntestazioneT(7, (("Categoria", "<b>x</b>"),), None)


def test_il_testo_dell_utente_e_escapato_ovunque():
    brutto = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
    m = MessaggioT("2026-11-02 10:00", brutto, brutto, (AllegatoT(brutto, 10, "ab" * 32),))
    pagina = tr.html_in_parti(H, [m])[0]
    assert "<script" not in pagina and "<img" not in pagina  # il testo resta testo (escapato, mai un tag)
    assert "&lt;script&gt;" in pagina
    assert "&lt;b&gt;x&lt;/b&gt;" in pagina  # anche l'intestazione


def test_csp_e_nessuna_risorsa_remota():
    m = MessaggioT("10:00", "mario", "ciao https://esempio.it/a.png", (AllegatoT("a.png", 1, "cd", b"\x89PNGfake"),))
    pagina = tr.html_in_parti(H, [m])[0]
    assert "Content-Security-Policy" in pagina and "default-src &#39;none&#39;" in pagina
    assert not re.search(r'(src|href)=["\']?(https?:)?//', pagina)
    assert "url(" not in pagina and "@import" not in pagina
    assert 'src="data:image/png;base64,' in pagina


def test_senza_copia_ricodificata_niente_immagine_solo_nome_peso_e_impronta():
    m = MessaggioT("10:00", "mario", "", (AllegatoT("a.png", 12, "ff" * 32, b""),))
    pagina = tr.html_in_parti(H, [m])[0]
    assert "<img" not in pagina and "a.png" in pagina and "12 byte" in pagina and "ff" * 32 in pagina


def test_avatar_a_iniziali():
    assert tr.iniziali("Mario Rossi") == "MR" and tr.iniziali("yokai") == "YO" and tr.iniziali("  ") == "?"


def test_file_troppo_grande_perde_le_immagini_poi_si_divide():
    png = b"x" * 5000
    msgs = [MessaggioT("10:00", "u", "t" * 400, (AllegatoT("a.png", 1, "aa", png),)) for _ in range(40)]
    intero = tr.html_in_parti(H, msgs, 10**9)
    assert len(intero) == 1 and "<img" in intero[0]
    senza = tr.html_in_parti(H, msgs, len(intero[0].encode()) - 1)
    assert len(senza) >= 1 and all("<img" not in p for p in senza)
    parti = tr.html_in_parti(H, msgs, 6000)
    assert len(parti) > 1 and all(len(p.encode()) <= 6000 for p in parti)
    assert "parte 1 di" in parti[0]


def test_zip_ha_solo_le_immagini_ricodificate_e_l_elenco():
    a = [AllegatoT("foto.jpg", 100, "ab" * 32, b"PNG-RICODIFICATO"), AllegatoT("doc.pdf", 50, "cd" * 32, b"")]
    z = zipfile.ZipFile(io.BytesIO(tr.zip_allegati(a)))
    nomi = z.namelist()
    assert nomi == [f"immagine-001-{'ab' * 4}.png", "elenco-allegati.txt"]
    assert z.read(nomi[0]) == b"PNG-RICODIFICATO"
    elenco = z.read("elenco-allegati.txt").decode()
    assert "foto.jpg" in elenco and "doc.pdf" in elenco and "non incluso" in elenco
    assert tr.zip_allegati([]) is None


def test_formato_valido():
    assert [tr.formato_valido(x) for x in ("html", "entrambi", "testo", "zip", None)] == [
        "html", "entrambi", "testo", "testo", "testo"]


# ====================================================================
# Cog: file del transcript secondo le opzioni del pannello
# ====================================================================
import base64
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from core.immagini_byte_logic import MALEVOLA, PULITA
from core.immagini_pipeline import EsitoImmagine
from core.ticket_opzioni_logic import Opzioni
from tests.support.discord_fakes import fake_guild, fake_member, fake_message, fake_text_channel


def _allegato(nome, contenuto=b"ORIGINALE", tipo="image/png"):
    a = create_autospec(discord.Attachment, instance=True)
    a.filename, a.size, a.content_type = nome, len(contenuto), tipo
    a.read = AsyncMock(return_value=contenuto)
    return a


def _scena(allegati):
    autore = fake_member(name="mario")
    autore.__str__ = lambda self: "mario"
    autore.bot = False
    m = fake_message(author=autore, content="<b>ciao</b>")
    m.created_at = datetime.datetime(2026, 11, 2, 9, 30, tzinfo=datetime.timezone.utc)
    m.attachments = allegati
    m.embeds = []

    async def storia():
        yield m

    canale = fake_text_channel(1000, "ticket-0001")
    canale.history.side_effect = lambda **kw: storia()
    ticket = SimpleNamespace(
        ticket_number=1, user_id=20, created_at=m.created_at, category_label=None, priority="normal",
        claimed_by=None, close_reason=None, panel_id=5,
    )
    cog = modulo.TicketsCog(commands.Bot(command_prefix="!", intents=discord.Intents.default()))
    return cog, fake_guild(100), canale, ticket


async def test_opzioni_di_base_danno_il_solo_testo(monkeypatch):
    monkeypatch.setattr(modulo, "_opzioni_pannello", AsyncMock(return_value=Opzioni()))
    cog, guild, canale, ticket = _scena([])
    assert [n for n, _ in await cog._file_transcript(guild, canale, ticket)] == ["ticket-0001-transcript.txt"]


async def test_html_entrambi_e_zip_usano_solo_la_copia_ricodificata(monkeypatch):
    monkeypatch.setattr(modulo, "_opzioni_pannello", AsyncMock(return_value=Opzioni(transcript_formato="entrambi", allegati_zip=True)))
    esiti = {"buona.png": EsitoImmagine(PULITA, "ab" * 32, png=b"RICODIFICATO"),
             "trappola.png": EsitoImmagine(MALEVOLA, "cd" * 32)}
    monkeypatch.setattr(modulo, "analizza_immagine", AsyncMock(side_effect=lambda dati, nome, tipo, g: esiti[nome]))
    cog, guild, canale, ticket = _scena([_allegato("buona.png"), _allegato("trappola.png"), _allegato("note.pdf", tipo="application/pdf")])
    file = dict(await cog._file_transcript(guild, canale, ticket))
    assert sorted(file) == ["ticket-0001-allegati.zip", "ticket-0001-transcript.html", "ticket-0001-transcript.txt"]
    html = file["ticket-0001-transcript.html"].decode()
    assert base64.b64encode(b"RICODIFICATO").decode() in html and base64.b64encode(b"ORIGINALE").decode() not in html
    assert "&lt;b&gt;ciao&lt;/b&gt;" in html and "trappola.png" in html and "note.pdf" in html
    z = zipfile.ZipFile(io.BytesIO(file["ticket-0001-allegati.zip"]))
    assert b"ORIGINALE" not in b"".join(z.read(n) for n in z.namelist())
    assert z.read(z.namelist()[0]) == b"RICODIFICATO"


async def test_un_allegato_che_non_si_legge_non_ferma_il_transcript(monkeypatch):
    monkeypatch.setattr(modulo, "_opzioni_pannello", AsyncMock(return_value=Opzioni(transcript_formato="html")))
    rotto = _allegato("rotta.png")
    rotto.read = AsyncMock(side_effect=discord.HTTPException(AsyncMock(status=500, reason="x"), "boom"))
    cog, guild, canale, ticket = _scena([rotto])
    file = dict(await cog._file_transcript(guild, canale, ticket))
    assert "rotta.png" in file["ticket-0001-transcript.html"].decode()
