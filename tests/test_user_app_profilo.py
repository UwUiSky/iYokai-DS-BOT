"""
tests/test_user_app_profilo.py
==============================
SPEC B.6 (#107): profilo globale di iYokai App (livello da tutti i server, clan, medaglie, rank card) e la sua
privacy: gli altri lo vedono solo se la persona ha acceso `/impostazioni profilo`.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.user_app.personal as personale
from core import user_app_profilo as up
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.user_app_repo import UserAppRepository
from tests.support.discord_fakes import fake_interaction, fake_member


@pytest.fixture
def db(monkeypatch, clean_db):
    repo = UserAppRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(up, "user_app_repo", repo)
    monkeypatch.setattr("core.user_app_impostazioni.user_app_repo", repo)
    monkeypatch.setattr(up, "leveling_repo", LevelingRepository(pool_provider=lambda: clean_db))
    monkeypatch.setattr(personale, "leveling_repo", up.leveling_repo)
    return repo, clean_db


async def _dati(clean_db, user_id=7):
    await clean_db.execute(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total, level, coins_total) VALUES (1, $1, 500, 3, 10), (2, $1, 700, 4, 5)",
        user_id,
    )
    await clean_db.execute("INSERT INTO profile_items (guild_id, user_id, item_id) VALUES (1, $1, 'stella'), (2, $1, 'oceano')", user_id)


async def test_profilo_globale_somma_i_server(db):
    _, clean_db = db
    await _dati(clean_db)
    p = await up.profilo_globale(7)
    assert (p.xp_totale, p.server, p.monete) == (1200, 2, 15)
    assert p.livello == up.level_for_xp(1200) and p.medaglie == ("oceano", "stella")
    assert up.testo_medaglie(p.medaglie) == "⭐"  # lo sfondo non è un badge
    dati = up.dati_rank_card("Yo", p)
    assert dati.xp_totale == 1200 and dati.collezione == 2 and dati.posizione is None


async def test_senza_dati_il_profilo_globale_e_vuoto(db):
    p = await up.profilo_globale(99)
    assert (p.livello, p.xp_totale, p.server, p.clan, p.medaglie) == (0, 0, 0, (), ())


def _utente(user_id):
    u = MagicMock(spec=discord.User)
    u.display_name, u.name, u.id, u.bot = "Yo", "yo", user_id, False
    u.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    u.accent_color = None
    u.banner = None
    u.display_avatar.url = "https://x/a.png"
    u.display_avatar.read = AsyncMock(return_value=b"")
    return u


@pytest.fixture
def cog(db):
    bot = MagicMock(tree=MagicMock())
    bot.fetch_user = AsyncMock(side_effect=lambda uid: _utente(uid))
    return personale.PersonaleCog(bot)


def _i(user_id):
    i = fake_interaction(user=fake_member(user_id=user_id))
    i.guild_id = None
    return i


def _embed(i):
    return i.followup.send.await_args.kwargs["embed"]


async def test_per_se_stessi_il_profilo_ha_i_dati_globali_e_la_carta(cog, db):
    _, clean_db = db
    await _dati(clean_db, 7)
    i = _i(7)
    await cog.profilo.callback(cog, i, None, True)
    campi = {c.name: c.value for c in _embed(i).fields}
    assert "1.200 XP" in campi["Livello globale"] and "2 server" in campi["Livello globale"] and campi["Medaglie"] == "⭐"
    assert i.followup.send.await_args.kwargs["file"].filename == "profilo.png"
    assert _embed(i).image.url == "attachment://profilo.png"


async def test_gli_altri_non_vedono_i_dati_globali_se_non_li_hai_resi_pubblici(cog, db):
    repo, clean_db = db
    await _dati(clean_db, 7)
    i = _i(8)
    await cog.profilo.callback(cog, i, _utente(7), True)
    assert "Livello globale" not in {c.name for c in _embed(i).fields}
    assert "file" not in i.followup.send.await_args.kwargs
    assert "proprietario" in _embed(i).footer.text

    await repo.imposta(7, "profilo_pubblico", True)
    i = _i(8)
    await cog.profilo.callback(cog, i, _utente(7), False)
    assert "Livello globale" in {c.name for c in _embed(i).fields}


async def test_un_errore_nei_dati_globali_non_rompe_il_profilo(cog, monkeypatch):
    monkeypatch.setattr(personale, "profilo_globale", AsyncMock(side_effect=RuntimeError("db")))
    i = _i(7)
    await cog.profilo.callback(cog, i, None, False)
    assert "Livello globale" not in {c.name for c in _embed(i).fields}


async def test_il_profilo_segue_la_scelta_privata_o_pubblica(cog, db):
    repo, _ = db
    i = _i(7)
    await cog.menu_profilo(i, _utente(7))
    assert i.followup.send.await_args.kwargs["ephemeral"] is True
    await repo.imposta(7, "risposte_private", False)
    i = _i(7)
    await cog.menu_profilo(i, _utente(7))
    assert i.followup.send.await_args.kwargs["ephemeral"] is False
