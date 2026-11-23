"""
tests/test_top_settimanale.py
=============================
Top 10 della settimana pubblicata da sola (LIV-061): scelta della settimana, testo, archivio e annuncio una volta sola.
Funzioni coperte: LIV-061
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import monthly_winners_announcer as modulo
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.top_settimanale_repo import TopSettimanaleRepository
from core import top_settimanale_logic as logica
from core.top_settimanale_logic import da_annunciare, settimana_precedente

LUNEDI = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)  # settimana 48 appena iniziata


# LIV-061
def test_la_settimana_da_annunciare_e_quella_appena_finita_anche_a_cavallo_d_anno():
    assert settimana_precedente(LUNEDI) == "2026-W47"
    assert settimana_precedente(datetime(2027, 1, 4, 1, tzinfo=timezone.utc)) == "2026-W53"
    assert da_annunciare(None, LUNEDI) and da_annunciare("2026-W46", LUNEDI)
    assert not da_annunciare("2026-W47", LUNEDI)


# LIV-061
def test_il_testo_ha_al_massimo_dieci_righe_con_le_medaglie_e_dice_se_e_vuoto():
    voci = [(i, 100 - i) for i in range(1, 15)]
    righe = logica.testo_top(voci, "XP").split("\n")
    assert len(righe) == 10 and righe[0].startswith("🥇") and righe[3].startswith("4.")
    assert "Nessuna attività" in logica.testo_top([], "XP")


# LIV-061
@pytest.mark.asyncio
async def test_l_annuncio_della_settimana_parte_una_volta_sola(clean_db, monkeypatch):
    archivio = TopSettimanaleRepository(pool_provider=lambda: clean_db)
    livelli = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "top_settimanale_repo", archivio)
    monkeypatch.setattr(modulo, "leveling_repo", livelli)
    await archivio.imposta(5, 50, gia_coperta="2026-W46")
    canale = MagicMock(spec=discord.TextChannel)
    canale.send = AsyncMock()
    guild = MagicMock()
    guild.get_channel.return_value = canale
    bot = MagicMock()
    bot.get_guild.side_effect = lambda g: guild if g == 5 else None
    settimana = settimana_precedente(LUNEDI)
    monkeypatch.setattr(modulo, "settimana_precedente", lambda adesso=None: settimana)
    monkeypatch.setattr(livelli, "top_xp_period", AsyncMock(return_value=[]))
    await modulo.monthly_winners_announcer.tick_settimanale(bot, LUNEDI)
    canale.send.assert_awaited_once()
    assert "Nessuna attività" in canale.send.await_args.kwargs["embed"].description
    assert canale.send.await_args.kwargs["allowed_mentions"].users is False
    await modulo.monthly_winners_announcer.tick_settimanale(bot, LUNEDI)
    canale.send.assert_awaited_once()  # la seconda volta non rimanda
    assert (await archivio.leggi(5)).ultima_annunciata == settimana
    assert await archivio.togli(5) and await archivio.leggi(5) is None
