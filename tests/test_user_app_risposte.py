"""
tests/test_user_app_risposte.py
===============================
SPEC B.5 (#107): risposte salvate personali di iYokai App (logica, comandi e menu «Salva come risposta pronta»).
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.user_app.risposte as rr
from core import user_app_risposte as ur
from core.repositories.user_app_repo import UserAppRepository
from core.user_app_strumenti import ErroreStrumento
from tests.support.discord_fakes import fake_interaction, fake_member, fake_message


def test_nome_colore_e_immagine():
    assert ur.normalizza_nome("  Saluto-1 ") == "saluto-1"
    for brutto in ("", "con spazio", "x" * 33, "è", "a/b"):
        with pytest.raises(ErroreStrumento):
            ur.normalizza_nome(brutto)
    assert ur.colore_intero("#ff8800") == 0xFF8800 and ur.colore_intero("") is None
    with pytest.raises(ErroreStrumento):
        ur.colore_intero("rosso")
    assert ur.immagine_valida("https://x.example/a.png") == "https://x.example/a.png" and ur.immagine_valida(" ") is None
    for cattivo in ("http://x.example/a.png", "javascript:alert(1)", "https://" + "a" * 300, "ftp://x/y"):
        with pytest.raises(ErroreStrumento):
            ur.immagine_valida(cattivo)
    assert ur.e_embed("T", None, None) and ur.e_embed(None, 0, None) and not ur.e_embed("", None, "")


@pytest.fixture
def cog(monkeypatch, clean_db):
    repo = UserAppRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(rr, "user_app_repo", repo)
    c = rr.RisposteCog(MagicMock(tree=MagicMock()))
    c.repo = repo
    return c


def _i(user_id=7):
    i = fake_interaction(user=fake_member(user_id=user_id))
    i.response.send_modal = AsyncMock()
    return i


def _testo(i):
    return i.response.send_message.await_args.args[0]


async def test_salva_usa_testo_semplice_e_privata_a_richiesta(cog):
    i = _i()
    await cog.salva_cmd.callback(cog, i, "Ciao", "Ciao a tutti!")
    assert "salvata" in _testo(i)
    i = _i()
    await cog.usa.callback(cog, i, "ciao", False)
    assert _testo(i) == "Ciao a tutti!" and i.response.send_message.await_args.kwargs["ephemeral"] is False
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].everyone is False
    i = _i()
    await cog.usa.callback(cog, i, "CIAO", True)
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_salva_embed_con_titolo_colore_e_immagine(cog):
    i = _i()
    await cog.salva_cmd.callback(cog, i, "regole", "Sii gentile", "Regole", "#00ff00", "https://x.example/r.png")
    i = _i()
    await cog.usa.callback(cog, i, "regole", False)
    embed = i.response.send_message.await_args.kwargs["embed"]
    assert (embed.title, embed.description, embed.color.value, embed.image.url) == ("Regole", "Sii gentile", 0x00FF00, "https://x.example/r.png")


async def test_salva_rifiuta_dati_non_validi_e_aggiorna(cog):
    i = _i()
    await cog.salva_cmd.callback(cog, i, "no spazi", "x")
    assert "da 1 a 32" in _testo(i)
    i = _i()
    await cog.salva_cmd.callback(cog, i, "a", "x", "", "blu", "")
    assert "Non" in _testo(i) or "colore" in _testo(i).lower()
    await cog.salva_cmd.callback(cog, _i(), "a", "uno")
    i = _i()
    await cog.salva_cmd.callback(cog, i, "a", "due")
    assert "aggiornata" in _testo(i)


async def test_solo_le_proprie_risposte_e_tetto(cog, monkeypatch):
    await cog.salva_cmd.callback(cog, _i(7), "mia", "x")
    i = _i(8)
    await cog.usa.callback(cog, i, "mia", False)
    assert "Non trovo" in _testo(i)
    i = _i(8)
    await cog.rimuovi.callback(cog, i, "mia")
    assert "Non trovo" in _testo(i)
    monkeypatch.setattr(cog.repo, "salva_risposta", AsyncMock(return_value="piena"))
    i = _i(7)
    await cog.salva_cmd.callback(cog, i, "altra", "x")
    assert "toglierne" in _testo(i)


async def test_elenco_e_rimozione(cog):
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "Non hai" in _testo(i)
    await cog.salva_cmd.callback(cog, _i(), "uno", "x")
    await cog.salva_cmd.callback(cog, _i(), "due", "y")
    i = _i()
    await cog.elenco.callback(cog, i)
    assert "`due`" in i.response.send_message.await_args.kwargs["embed"].description
    i = _i()
    await cog.rimuovi.callback(cog, i, "uno")
    assert "tolta" in _testo(i)


async def test_menu_salva_come_risposta_pronta(cog):
    m = fake_message(1, content="Benvenuto nel server!")
    m.embeds = []
    i = _i()
    await cog.menu_salva(i, m)
    modulo = i.response.send_modal.await_args.args[0]
    modulo.nome._value = "benvenuto"
    i2 = _i()
    await modulo.on_submit(i2)
    assert "salvata" in _testo(i2)
    assert (await cog.repo.risposta(7, "benvenuto"))["testo"] == "Benvenuto nel server!"
    vuoto = fake_message(2, content="")
    vuoto.embeds = []
    i = _i()
    await cog.menu_salva(i, vuoto)
    assert "non ha testo" in _testo(i)


async def test_autocompletamento_dei_nomi(cog):
    await cog.salva_cmd.callback(cog, _i(), "saluto", "x")
    await cog.salva_cmd.callback(cog, _i(), "sera", "y")
    scelte = await rr._completa_nomi(_i(), "sa")
    assert [c.value for c in scelte] == ["saluto"]
