"""
tests/test_giveaway_guidato.py
==============================
UTL-121 (D124): creazione guidata del giveaway. Lettura dei dati, creazione solo alla conferma,
Annulla senza niente di scritto, permesso tolto a metà, canale e requisiti.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.giveaway_guidato_logic import durata_leggibile, leggi_base, leggi_durata, leggi_requisiti, pulisci_premio


def test_durata_in_minuti_ore_giorni():
    assert leggi_durata("90") == 90 and leggi_durata("2h") == 120 and leggi_durata("3d") == 4320
    assert leggi_durata("0") is None and leggi_durata("43201") is None and leggi_durata("abc") is None
    assert leggi_durata("30 giorni") is None


def test_base_valida_e_errori():
    dati, err = leggi_base("  Nitro \n‮ ", "1h", "2")
    assert err is None and dati == {"premio": "Nitro", "durata": 60, "vincitori": 2}
    assert leggi_base("", "1h", "1")[1] == "giveaway_guidato_err_premio"
    assert leggi_base("x", "zzz", "1")[1] == "giveaway_guidato_err_durata"
    assert leggi_base("x", "1h", "51")[1] == "giveaway_guidato_err_vincitori"
    assert leggi_base("x", "1h", "")[0]["vincitori"] == 1


def test_premio_tagliato_e_senza_controllo():
    assert len(pulisci_premio("a" * 500)) == 200
    assert "\x00" not in pulisci_premio("a\x00b")


def test_requisiti():
    assert leggi_requisiti("5", "10")[0] == {"livello_min": 5, "messaggi_min": 10}
    assert leggi_requisiti("", "")[0] == {"livello_min": 0, "messaggi_min": 0}
    assert leggi_requisiti("-1", "0")[1] == "giveaway_guidato_err_requisiti"
    assert leggi_requisiti("1001", "0")[1] == "giveaway_guidato_err_requisiti"


def test_durata_leggibile():
    assert durata_leggibile(1500) == "1 g 1 h"


# ------------------------------------------------------------------ cog
import discord  # noqa: E402

import cogs.utility.giveaway_guidato as cog  # noqa: E402
from core.procedura_guidata import Fase, StatoProcedura  # noqa: E402
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel  # noqa: E402

DATI = {"premio": "Nitro", "durata": 60, "vincitori": 1, "canale_id": 111, "livello_min": 0, "messaggi_min": 0}


@pytest.fixture
def mondo(monkeypatch):
    repo = MagicMock()
    repo.create_giveaway = AsyncMock(return_value=5)
    repo.get_opzioni = AsyncMock(return_value=None)
    repo.get_giveaway = AsyncMock(return_value=None)
    repo.mark_ended = AsyncMock()
    repo.set_message_id = AsyncMock()
    monkeypatch.setattr(cog, "giveaway_repo", repo)
    monkeypatch.setattr(cog, "embed_annuncio", lambda *a, **k: discord.Embed(title="x"))
    monkeypatch.setattr(cog, "puo_usare", AsyncMock(return_value=True))
    monkeypatch.setattr(cog.db, "is_module_active_for_guild", AsyncMock(return_value=True))
    monkeypatch.setattr(cog, "motivo_se_il_bot_non_puo", lambda *a: None)
    monkeypatch.setattr(cog, "lingua_risposta", AsyncMock(return_value="it"))
    monkeypatch.setattr(cog, "lingua_interazione", AsyncMock(return_value="it"))
    canale = fake_text_channel(111)
    canale.send = AsyncMock(return_value=MagicMock(id=900))
    guild = fake_guild()
    guild.get_channel = MagicMock(return_value=canale)
    guild.get_role = MagicMock(return_value=None)
    return repo, canale, guild


@pytest.mark.asyncio
async def test_conferma_crea_e_annuncia(mondo):
    repo, canale, guild = mondo
    inter = fake_interaction(guild=guild, user=fake_member(user_id=7))
    testo = await cog.crea_giveaway(inter, dict(DATI))
    repo.create_giveaway.assert_awaited_once()
    assert repo.create_giveaway.await_args.args[1] == 111
    assert canale.send.await_args.kwargs["allowed_mentions"].everyone is False
    repo.set_message_id.assert_awaited_once_with(5, 900)
    assert "Giveaway creato" in testo


@pytest.mark.asyncio
async def test_permesso_tolto_prima_della_conferma_non_crea(mondo, monkeypatch):
    repo, _canale, guild = mondo
    monkeypatch.setattr(cog, "puo_usare", AsyncMock(return_value=False))
    with pytest.raises(ValueError):
        await cog.crea_giveaway(fake_interaction(guild=guild), dict(DATI))
    repo.create_giveaway.assert_not_awaited()


@pytest.mark.asyncio
async def test_annuncio_non_inviato_chiude_il_giveaway(mondo):
    repo, canale, guild = mondo
    canale.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "x"))
    with pytest.raises(ValueError):
        await cog.crea_giveaway(fake_interaction(guild=guild), dict(DATI))
    repo.mark_ended.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_annulla_non_scrive_niente(mondo):
    from core.procedura_guidata import VistaGuidata

    repo, _c, guild = mondo
    stato = StatoProcedura(7, cog.PASSI, dict(DATI))
    vista = VistaGuidata(
        stato, titolo="t", lingua="it", permesso=cog.permesso,
        costruttori={"giveaway_guidato_base": cog._costruisci_base},
        testi={p.chiave: (lambda v: "") for p in cog.PASSI}, riepilogo=lambda v: "", conferma=cog.crea_giveaway,
    )
    await vista._annulla(fake_interaction(guild=guild, user=fake_member(user_id=7)))
    assert stato.fase is Fase.ANNULLATA
    repo.create_giveaway.assert_not_awaited()


def test_riepilogo_mostra_tutto_e_non_ping():
    testo = cog.testo_riepilogo({**DATI, "ruolo_id": 77}, "it")
    assert "Nitro" in testo and "<#111>" in testo and "<@&77>" in testo and "1 h" in testo
