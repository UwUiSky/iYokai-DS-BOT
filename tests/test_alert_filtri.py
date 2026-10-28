"""
tests/test_alert_filtri.py
==========================
Filtri e pausa degli avvisi (#129: ALR-030, 031, 032, 033, 036).
Logica pura in core/alert_options_logic.py; il flusso in core/live_alert_flow.py.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core.alert_options_logic import AlertOptions, motivo_silenzio, parse_parole
from core.live_alert_flow import pubblica_cambio_live
from tests.support.discord_fakes import fake_text_channel

ADESSO = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def test_parole_separate_da_virgola():
    assert parse_parole(" Torneo, -replica ,, ") == ["torneo", "-replica"]
    assert parse_parole("") == []


def test_senza_filtri_si_pubblica():
    assert motivo_silenzio(AlertOptions(), "titolo", "gioco", ADESSO) is None


def test_pausa_zittisce():
    assert motivo_silenzio(AlertOptions(paused=True), "t", "g", ADESSO) == "pausa"


def test_titolo_deve_contenere_una_parola():
    opz = AlertOptions(title_words="torneo, finale")
    assert motivo_silenzio(opz, "Grande FINALE oggi", "", ADESSO) is None
    assert motivo_silenzio(opz, "Chiacchiere", "", ADESSO) == "titolo"


def test_parola_con_meno_esclude_le_repliche():
    opz = AlertOptions(title_words="-replica,-rerun")
    assert motivo_silenzio(opz, "Torneo (REPLICA)", "", ADESSO) == "titolo"
    assert motivo_silenzio(opz, "Torneo live", "", ADESSO) is None


def test_solo_parole_escluse_e_incluse_insieme():
    opz = AlertOptions(title_words="torneo,-replica")
    assert motivo_silenzio(opz, "Torneo", "", ADESSO) is None
    assert motivo_silenzio(opz, "Torneo replica", "", ADESSO) == "titolo"
    assert motivo_silenzio(opz, "Altro", "", ADESSO) == "titolo"


def test_gioco_deve_essere_uno_dell_elenco():
    opz = AlertOptions(game_filter="Valorant, Just Chatting")
    assert motivo_silenzio(opz, "t", "valorant", ADESSO) is None
    assert motivo_silenzio(opz, "t", "Minecraft", ADESSO) == "gioco"
    assert motivo_silenzio(opz, "t", "", ADESSO) == "gioco"


def test_pausa_minima_tra_due_avvisi():
    opz = AlertOptions(min_gap_minutes=30, last_published_at=ADESSO - timedelta(minutes=10))
    assert motivo_silenzio(opz, "t", "g", ADESSO) == "attesa"
    opz2 = AlertOptions(min_gap_minutes=30, last_published_at=ADESSO - timedelta(minutes=31))
    assert motivo_silenzio(opz2, "t", "g", ADESSO) is None


def _contesto(monkeypatch):
    import core.live_alert_flow as f

    avviso = AsyncMock(return_value=77)
    monkeypatch.setattr(f, "avviso_live", avviso)
    monkeypatch.setattr(f, "aggiorna_ruolo_live", AsyncMock())
    repo = MagicMock(set_last_message=AsyncMock(), touch_published=AsyncMock(),
                     other_live_for_member=AsyncMock(return_value=False))
    monkeypatch.setattr(f, "alert_options_repo", repo)
    canale = fake_text_channel(1)
    canale.__class__ = discord.TextChannel
    guild = MagicMock()
    guild.get_channel.return_value = canale
    bot = MagicMock()
    bot.get_guild.return_value = guild
    sub = MagicMock(id=3, guild_id=5, channel_id=1)
    stato = MagicMock(update_last_known_live=AsyncMock())
    return avviso, repo, bot, sub, stato


async def _vai(bot, sub, stato, opz, **extra):
    await pubblica_cambio_live(
        bot, sub, "TW", in_diretta=True, testo="x", url=None, opz=opz, ruolo_live_id=None,
        repo_stato=stato, avvisi=MagicMock(), nome="Twitch", **extra,
    )


@pytest.mark.asyncio
async def test_avviso_in_pausa_non_pubblica_e_non_avanza_lo_stato(monkeypatch):
    avviso, repo, bot, sub, stato = _contesto(monkeypatch)
    await _vai(bot, sub, stato, AlertOptions(paused=True), titolo="t", gioco="g")
    avviso.assert_not_awaited()
    stato.update_last_known_live.assert_not_awaited()


@pytest.mark.asyncio
async def test_titolo_non_ammesso_non_pubblica(monkeypatch):
    avviso, repo, bot, sub, stato = _contesto(monkeypatch)
    await _vai(bot, sub, stato, AlertOptions(title_words="torneo"), titolo="chiacchiere")
    avviso.assert_not_awaited()


@pytest.mark.asyncio
async def test_avviso_ammesso_pubblica_e_ricorda_l_orario(monkeypatch):
    avviso, repo, bot, sub, stato = _contesto(monkeypatch)
    await _vai(bot, sub, stato, AlertOptions(title_words="torneo", min_gap_minutes=5), titolo="Torneo!")
    avviso.assert_awaited_once()
    stato.update_last_known_live.assert_awaited_once()
    repo.touch_published.assert_awaited_once_with("TW", 3, 5)


@pytest.mark.asyncio
async def test_diretta_ravvicinata_non_viene_annunciata_a_meta(monkeypatch):
    """ALR-033: una diretta dentro la pausa minima è assorbita. L'orario si sposta in avanti,
    così a pausa scaduta la STESSA diretta non viene annunciata a metà."""
    avviso, repo, bot, sub, stato = _contesto(monkeypatch)
    recente = datetime.now(timezone.utc) - timedelta(minutes=10)
    await _vai(bot, sub, stato, AlertOptions(min_gap_minutes=30, last_published_at=recente), titolo="t")
    avviso.assert_not_awaited()
    repo.touch_published.assert_awaited_once_with("TW", 3, 5)


@pytest.mark.asyncio
async def test_filtro_gioco_non_zittisce_youtube(monkeypatch):
    """YouTube non dice il gioco: il filtro sul gioco vale solo per Twitch e Kick."""
    avviso, repo, bot, sub, stato = _contesto(monkeypatch)
    await _vai(bot, sub, stato, AlertOptions(game_filter="Valorant"), titolo="t")
    avviso.assert_awaited_once()


def test_gioco_sconosciuto_non_filtra():
    assert motivo_silenzio(AlertOptions(game_filter="Valorant"), "t", None, ADESSO) is None
