"""
tests/test_leveling_velocita.py
===============================
#124 B7 (LIV-001, 002, 003): XP minimo e massimo per messaggio, pausa fino a un'ora, velocità generale.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import ConfigLivelli, LevelingSettings, xp_con_moltiplicatore, xp_messaggio
from core.repositories.leveling_settings_repo import LevelingSettingsRepository

GUILD = 100


def test_liv001_xp_a_sorte_tra_minimo_e_massimo():
    i = LevelingSettings(text_xp=15, text_xp_max=100)
    visti = {xp_messaggio(i, "x", False) for _ in range(400)}
    assert min(visti) >= 15 and max(visti) <= 100 and len(visti) > 10
    assert xp_messaggio(i, "x", False, scelta=lambda a, b: b) == 100
    assert xp_messaggio(LevelingSettings(text_xp=15), "x", False) == 15  # massimo 0: fisso
    assert xp_messaggio(LevelingSettings(text_xp=15, text_xp_max=10), "x", False) == 15


def test_liv003_la_velocita_moltiplica_ogni_guadagno():
    c = ConfigLivelli(impostazioni=LevelingSettings(xp_percentuale=250), mult_canali={1: 2.0})
    assert c.moltiplicatore([9], []) == 2.5
    assert c.moltiplicatore([1], []) == 5.0  # insieme al moltiplicatore del canale
    assert xp_con_moltiplicatore(10, c.moltiplicatore([9], [])) == 25
    assert ConfigLivelli().moltiplicatore([9], []) == 1.0
    assert xp_con_moltiplicatore(10, ConfigLivelli(impostazioni=LevelingSettings(xp_percentuale=25)).moltiplicatore([1], [])) == 3  # 2,5 arrotondato


@pytest.fixture
def repo(clean_db):
    return LevelingSettingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_liv001_002_003_limiti_dell_archivio(repo):
    i = await repo.set_options(GUILD, text_xp=10, text_xp_max=50, text_cooldown_seconds=3600, xp_percentuale=500)
    assert (i.text_xp_max, i.text_cooldown_seconds, i.xp_percentuale) == (50, 3600, 500)
    for no in ({"text_cooldown_seconds": 3601}, {"xp_percentuale": 24}, {"xp_percentuale": 501},
               {"text_xp_max": 101}, {"text_xp_max": 5}, {"text_xp": 60}):
        with pytest.raises(ValueError):
            await repo.set_options(GUILD, **no)


@pytest.mark.asyncio
async def test_liv001_il_cog_da_l_xp_scelto_a_sorte_con_la_velocita(monkeypatch):
    from unittest.mock import AsyncMock, create_autospec
    from core.repositories.leveling_repo import LevelingRepository, TextXpResult

    finto = create_autospec(LevelingRepository, instance=True)
    finto.add_text_xp.return_value = TextXpResult(granted=False, new_xp_total=0, leveled_up=False, new_level=0)
    monkeypatch.setattr(modulo, "leveling_repo", finto)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    config = ConfigLivelli(impostazioni=LevelingSettings(text_xp=20, text_xp_max=20, xp_percentuale=150))
    from tests.support.discord_fakes import fake_guild, fake_member

    await cog._assegna_xp_testo(fake_member(3), fake_guild(GUILD), None, config, [], [1], 20)
    assert finto.add_text_xp.await_args.kwargs["amount"] == 30
