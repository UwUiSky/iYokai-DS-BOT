"""
tests/test_movimenti_voce_b16.py
================================
Storico personale dei movimenti (ECO-007) e tetto vocale giornaliero scelto dal server (ECO-161), #125 B16.
Funzioni coperte: catalogo #125
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.leveling_logic import LevelingSettings, compute_voice_minute
from core.repositories.economia_repo import EconomiaRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository

G = 100


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        eco=EconomiaRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        imp=LevelingSettingsRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


def test_tetto_vocale_scelto_dal_server():
    assert compute_voice_minute(5, 100, False, 100).capped is True  # 100 minuti già fatti con tetto 100
    assert compute_voice_minute(5, 100, False, 101).capped is False
    assert compute_voice_minute(5, 359, False).capped is False and compute_voice_minute(5, 360, False).capped is True  # base 360
    assert LevelingSettings().voce_max_minuti == 360


@pytest.mark.asyncio
async def test_il_tetto_vocale_ha_i_suoi_limiti(r):
    for brutto in (29, 1441, -1):
        with pytest.raises(ValueError):
            await r.imp.set_options(G, voce_max_minuti=brutto)
    await r.imp.set_options(G, voce_max_minuti=120)
    assert (await r.imp.get_config(G, fresco=True)).impostazioni.voce_max_minuti == 120


@pytest.mark.asyncio
async def test_storico_dei_movimenti_in_ordine_e_a_pagine(r):
    await r.lev.add_coins(G, 1, 100)  # guadagno
    await r.lev.add_coins(G, 2, 50)
    assert await r.lev.transfer_coins(G, 1, 2, 30, tassa=3) is True
    assert await r.lev.spend_coins(G, 1, 10) is True
    assert await r.lev.claim_daily(G, 1, 20, 60, datetime.now(timezone.utc)) is True
    righe = await r.eco.movimenti(G, 1)
    assert [(x["delta"], x["motivo"]) for x in righe] == [(20, "daily"), (-10, "spesa"), (-30, "pagamento"), (100, "guadagno")]
    assert [(x["delta"], x["motivo"]) for x in await r.eco.movimenti(G, 2)][:1] == [(27, "pagamento ricevuto")]
    assert await r.eco.movimenti(G, 1, 2) == [] and await r.eco.movimenti(G + 1, 1) == []
    assert [x["delta"] for x in await r.eco.movimenti(G, 3)] == []
