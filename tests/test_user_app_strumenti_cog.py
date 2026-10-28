"""
tests/test_user_app_strumenti_cog.py
====================================
SPEC B.3 e B.4 (#107): `/strumenti`, `/note`, «Stato rete iYokai» e il profilo con livello e clan.
Database vero per le note; Discord finto con oggetti fedeli.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

import cogs.user_app.personal as personale
import cogs.user_app.strumenti as strumenti
from core.repositories.user_app_note_repo import user_app_note_repo
from tests.support.discord_fakes import fake_interaction, fake_member


@pytest.fixture
def cog():
    return strumenti.StrumentiCog(MagicMock(tree=MagicMock()))


def _i(user_id=7):
    return fake_interaction(user=fake_member(user_id=user_id))


def _testo(i):
    return i.response.send_message.await_args.args[0] if i.response.send_message.await_args.args else None


async def test_calcola_e_converti(cog):
    i = _i()
    await cog.calcola.callback(cog, i, "(2+3)*4")
    assert "**20**" in _testo(i)
    i = _i()
    await cog.converti.callback(cog, i, 1.0, "km", "m")
    assert "**1000**" in _testo(i)
    i = _i()
    await cog.converti.callback(cog, i, 1.0, "km", "kg")
    assert "non si possono convertire" in _testo(i)
    i = _i()
    await cog.calcola.callback(cog, i, "1/0")
    assert "zero" in _testo(i)


async def test_fuso_colore_qr(cog):
    i = _i()
    await cog.fuso.callback(cog, i, "Asia/Tokyo", "UTC", "12:00")
    assert "**21:00**" in _testo(i)
    i = _i()
    await cog.fuso.callback(cog, i, "Marte/Olimpo", "UTC", None)
    assert "Fuso orario sconosciuto" in _testo(i)
    i = _i()
    await cog.colore.callback(cog, i, "f80")
    inviato = i.response.send_message.await_args.kwargs
    assert inviato["embed"].title == "#ff8800" and inviato["file"].filename == "colore.png" and inviato["ephemeral"]
    i = _i()
    await cog.qr.callback(cog, i, "https://iyokai.example")
    assert i.response.send_message.await_args.kwargs["file"].filename == "qr.png"


@pytest.fixture
def note_db(monkeypatch, clean_db):
    monkeypatch.setattr(user_app_note_repo, "_pool_provider", lambda: clean_db)
    return clean_db


async def test_note_e_liste_per_utente(cog, note_db):
    i = _i(7)
    await cog.aggiungi.callback(cog, i, "comprare il pane", None)
    assert "numero" in _testo(i)
    await cog.aggiungi.callback(cog, _i(7), "latte", "Spesa")
    await cog.aggiungi.callback(cog, _i(8), "nota di un altro", None)

    i = _i(7)
    await cog.elenco.callback(cog, i, None)
    embed = i.response.send_message.await_args.kwargs["embed"]
    assert "comprare il pane" in embed.description and "altro" not in embed.description
    assert "`spesa`" in embed.description  # la lista è nominata
    i = _i(7)
    await cog.elenco.callback(cog, i, "SPESA")
    assert "latte" in i.response.send_message.await_args.kwargs["embed"].description


async def test_elenco_lungo_mostra_righe_intere_e_dice_quante_ne_mancano(cog, note_db):
    """Il tetto è 100 voci: quelle che non stanno nell'embed non spariscono in silenzio."""
    import re

    for n in range(30):
        await user_app_note_repo.aggiungi(7, "", f"voce {n} " + "x" * 290)
    i = _i(7)
    await cog.elenco.callback(cog, i, None)
    corpo = i.response.send_message.await_args.kwargs["embed"].description

    mostrate = re.findall(r"^`\d+` · voce \d+ x+$", corpo, flags=re.M)
    altre = re.search(r"altre (\d+)", corpo)
    assert altre is not None and len(mostrate) + int(altre.group(1)) == 30
    assert len(corpo) <= 4096


async def test_rimuovi_solo_le_proprie_voci(cog, note_db):
    altro = await user_app_note_repo.aggiungi(8, "", "di un altro")
    mia = await user_app_note_repo.aggiungi(7, "", "mia")
    i = _i(7)
    await cog.rimuovi.callback(cog, i, altro)
    assert "Non trovo" in _testo(i)
    assert await user_app_note_repo.elenco(8, "")  # quella dell'altro c'è ancora
    i = _i(7)
    await cog.rimuovi.callback(cog, i, mia)
    assert "tolta" in _testo(i)


async def test_tetto_delle_voci_e_risposta_chiara(cog, note_db, monkeypatch):
    monkeypatch.setattr(strumenti, "MAX_VOCI_PER_UTENTE", 2)
    monkeypatch.setattr(
        user_app_note_repo, "aggiungi",
        lambda u, l, t_: user_app_note_repo.__class__.aggiungi(user_app_note_repo, u, l, t_, massimo=2),
    )
    for _ in range(2):
        await cog.aggiungi.callback(cog, _i(7), "x", None)
    i = _i(7)
    await cog.aggiungi.callback(cog, i, "x", None)
    assert "Hai già 2 voci" in _testo(i)


async def test_stato_rete_solo_per_se_stessi(cog):
    altro = SimpleNamespace(id=99)
    i = _i(7)
    with patch.object(strumenti.global_ban_repo, "network_summary", AsyncMock()) as lettura:
        await cog.menu_stato_rete(i, altro)
    lettura.assert_not_awaited()  # nessuna lettura sul conto di un altro
    assert "solo per te stesso" in _testo(i)

    i = _i(7)
    ora = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with patch.object(strumenti.global_ban_repo, "network_summary", AsyncMock(return_value=(0, None, None))):
        await cog.menu_stato_rete(i, SimpleNamespace(id=7))
    assert "Nessun ban" in _testo(i)
    i = _i(7)
    with patch.object(strumenti.global_ban_repo, "network_summary", AsyncMock(return_value=(2, ora, ora))):
        await cog.menu_stato_rete(i, SimpleNamespace(id=7))
    assert "2 server" in _testo(i) and i.response.send_message.await_args.kwargs["ephemeral"]


async def test_profilo_mostra_livello_e_clan_solo_in_un_server():
    utente = MagicMock(spec=discord.User)
    utente.display_name, utente.name, utente.id, utente.bot = "Yo", "yo", 7, False
    utente.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    utente.accent_color = None
    utente.banner = None
    utente.display_avatar.url = "https://x/a.png"
    totali = SimpleNamespace(level=12, xp_total=3456)
    clan = SimpleNamespace(tag="YK", name="Yokai")
    with patch.object(personale.leveling_repo, "get_totals", AsyncMock(return_value=totali)), \
            patch.object(personale.guild_clan_repo, "get_member_clan_in_guild", AsyncMock(return_value=clan)):
        livello, nome_clan = await personale._livello_e_clan(555, 7)
        assert await personale._livello_e_clan(None, 7) == (None, None)  # in DM niente
    embed = personale._embed_profilo(utente, "it", livello, nome_clan)
    campi = {c.name: c.value for c in embed.fields}
    assert campi["Livello"] == "12 · 3.456 XP" and campi["Clan"] == "[YK] Yokai"
    assert "Livello" not in {c.name for c in personale._embed_profilo(utente).fields}


async def test_un_errore_del_database_non_rompe_il_profilo():
    with patch.object(personale.leveling_repo, "get_totals", AsyncMock(side_effect=RuntimeError("db"))):
        assert await personale._livello_e_clan(555, 7) == (None, None)
