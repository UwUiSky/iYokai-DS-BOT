"""
tests/test_leveling_importi_e_tetto.py
======================================
NF-15 (#86), parte rimasta: importi di /daily e /work per server e tetto di
livello (LIV-005); più la correzione della docstring di leveling.py (#65).
Funzioni coperte: SPEC §22.14
"""

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import LevelingSettings, did_level_up, level_for_xp, xp_for_level
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.moduli import attiva_livelli

GUILD = 100


def test_la_docstring_non_dice_piu_che_il_contenuto_e_spento():
    # #65 (commento del 04/10): l'intent del contenuto è acceso.
    testo = " ".join((modulo.__doc__ or "").split())
    assert "non legge mai message.content" not in testo


def test_tetto_di_livello_nella_logica():
    xp_alto = xp_for_level(10) + 5
    assert level_for_xp(xp_alto) == 10
    assert level_for_xp(xp_alto, max_level=4) == 4
    assert level_for_xp(xp_alto, max_level=0) == 10  # 0 = nessun tetto
    # Già al tetto: altri XP non fanno salire di livello.
    assert did_level_up(xp_for_level(4), xp_for_level(4) + 500, max_level=4) == (False, 4)
    assert did_level_up(0, xp_for_level(6), max_level=4) == (True, 4)


@pytest.fixture
def repo_impostazioni(clean_db):
    return LevelingSettingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_importi_e_tetto_si_salvano_e_hanno_limiti(repo_impostazioni):
    base = (await repo_impostazioni.get_config(GUILD)).impostazioni
    assert (base.daily_coins, base.work_min, base.work_max, base.max_level) == (200, 20, 80, 0)

    await repo_impostazioni.set_options(
        GUILD, daily_coins=500, work_min=10, work_max=30, max_level=50
    )
    i = (await repo_impostazioni.get_config(GUILD)).impostazioni
    assert (i.daily_coins, i.work_min, i.work_max, i.max_level) == (500, 10, 30, 50)

    for campi in ({"daily_coins": 10_001}, {"max_level": 1001}, {"work_min": -1}):
        with pytest.raises(ValueError):
            await repo_impostazioni.set_options(GUILD, **campi)
    # Il minimo del lavoro non supera il massimo (anche rispetto al valore già salvato).
    with pytest.raises(ValueError):
        await repo_impostazioni.set_options(GUILD, work_min=31)
    with pytest.raises(ValueError):
        await repo_impostazioni.set_options(GUILD, work_max=5)
    assert (await repo_impostazioni.get_config(GUILD)).impostazioni.work_max == 30


@pytest.fixture
async def cog_e_repo(clean_db, monkeypatch):
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", repo)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    return cog, repo, leveling_settings_repo


def _interazione():
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(1))


@pytest.mark.asyncio
async def test_daily_e_work_usano_gli_importi_del_server(cog_e_repo):
    cog, repo, impostazioni = cog_e_repo
    await impostazioni.set_options(GUILD, daily_coins=500, work_min=33, work_max=33)

    await cog.daily.callback(cog, _interazione())
    assert (await repo.get_totals(GUILD, 1)).coins_total == 500
    await cog.work.callback(cog, _interazione())
    assert (await repo.get_totals(GUILD, 1)).coins_total == 533


@pytest.mark.asyncio
async def test_il_comando_xp_accetta_importi_e_tetto(cog_e_repo):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    cog, _, impostazioni = cog_e_repo
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    interazione = _interazione()
    await comandi["level impostazioni xp"].callback(
        cog, interazione, testo=None, attesa=None, voce_xp=None, voce_coin=None,
        moltiplicatori=None, daily=250, lavoro_min=5, lavoro_max=15, livello_massimo=20,
    )
    i = (await impostazioni.get_config(GUILD)).impostazioni
    assert (i.daily_coins, i.work_min, i.work_max, i.max_level) == (250, 5, 15, 20)


@pytest.mark.asyncio
async def test_xp_testuale_non_supera_il_tetto(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    await repo.add_text_xp(GUILD, 7, amount=xp_for_level(4) + 1000, cooldown_seconds=10, max_level=4)
    assert (await repo.get_totals(GUILD, 7)).level == 4


@pytest.mark.asyncio
async def test_xp_vocale_non_supera_il_tetto(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    await repo.add_text_xp(GUILD, 8, amount=xp_for_level(3) + 1, cooldown_seconds=10, max_level=3)
    imp = LevelingSettings(voice_xp_per_minute=50, max_level=3)
    risultati = await repo.add_voice_minutes(GUILD, [(8, 1, True)], imp)
    assert risultati[8] is not None
    assert (await repo.get_totals(GUILD, 8)).level == 3
    assert risultati[8].leveled_up is False


@pytest.mark.asyncio
async def test_la_rank_card_al_livello_massimo_non_ha_un_prossimo_livello(cog_e_repo, monkeypatch):
    cog, repo, impostazioni = cog_e_repo
    await impostazioni.set_options(GUILD, max_level=3)
    await repo.add_text_xp(GUILD, 1, amount=xp_for_level(3) + 700, cooldown_seconds=10, max_level=3)
    visti = []

    async def finta(funzione, dati, avatar, sfondo=None):
        visti.append(dati)
        return b"png"

    monkeypatch.setattr(modulo, "run_image_task", finta)
    interazione = _interazione()
    await cog.rank.callback(cog, interazione, member=None)

    assert visti and visti[0].livello == 3
    assert visti[0].xp_richiesti == 0 and visti[0].xp_nel_livello == 0
