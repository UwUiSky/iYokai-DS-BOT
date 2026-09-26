"""
tests/test_leveling_repo.py
==============================
Test di LevelingRepository contro PostgreSQL reale. La matematica
(soglie di livello, anti-farm vocale) è già coperta da
tests/test_leveling_logic.py: qui si verifica che la PERSISTENZA sia
corretta — transazioni, rollover giornaliero, saldo mai negativo,
classifiche filtrate correttamente.
"""

from datetime import date, timedelta

import pytest

from core.repositories.leveling_repo import LevelingRepository
from core.leveling_logic import TEXT_XP_COOLDOWN_SECONDS, period_key


@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_totali_di_default_per_utente_mai_visto(repo):
    totali = await repo.get_totals(100, 1)
    assert totali.xp_total == 0
    assert totali.level == 0
    assert totali.coins_total == 0


@pytest.mark.asyncio
async def test_add_text_xp_primo_messaggio_assegna_xp(repo):
    risultato = await repo.add_text_xp(100, 1)
    assert risultato.granted is True
    assert risultato.new_xp_total > 0


@pytest.mark.asyncio
async def test_add_text_xp_rispetta_il_cooldown(repo):
    primo = await repo.add_text_xp(100, 1)
    secondo = await repo.add_text_xp(100, 1)  # subito dopo, stesso utente
    assert primo.granted is True
    assert secondo.granted is False
    assert secondo.new_xp_total == primo.new_xp_total  # nessun XP in più


@pytest.mark.asyncio
async def test_add_text_xp_persiste_nei_totali(repo):
    await repo.add_text_xp(100, 1)
    totali = await repo.get_totals(100, 1)
    assert totali.xp_total > 0


@pytest.mark.asyncio
async def test_add_text_xp_registra_attivita_nel_periodo_corrente(repo):
    await repo.add_text_xp(100, 1)
    classifica = await repo.top_xp_period(100)
    assert len(classifica) == 1
    assert classifica[0].user_id == 1


@pytest.mark.asyncio
async def test_add_voice_minute_idoneo_assegna_xp_e_coin(repo):
    grant = await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=True)
    assert grant is not None
    assert grant.xp_granted > 0
    assert grant.coins_granted > 0

    totali = await repo.get_totals(100, 1)
    assert totali.xp_total == grant.xp_granted
    assert totali.coins_total == grant.coins_granted


@pytest.mark.asyncio
async def test_add_voice_minute_non_idoneo_non_assegna_nulla(repo):
    grant = await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=False)
    assert grant is None

    totali = await repo.get_totals(100, 1)
    assert totali.xp_total == 0
    assert totali.coins_total == 0


@pytest.mark.asyncio
async def test_add_voice_minute_traccia_il_canale_anche_se_non_idoneo(repo, clean_db):
    # Anche senza guadagno, il canale corrente va tracciato: serve
    # al minuto SUCCESSIVO per sapere se c'è stato un cambio canale.
    await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=False)
    row = await clean_db.fetchrow(
        "SELECT voice_channel_id FROM leveling_totals WHERE guild_id=100 AND user_id=1"
    )
    assert row["voice_channel_id"] == 5000


@pytest.mark.asyncio
async def test_add_voice_minute_consecutivi_si_accumulano(repo, clean_db):
    await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=True)
    await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=True)
    row = await clean_db.fetchrow(
        "SELECT voice_consecutive_minutes FROM leveling_totals WHERE guild_id=100 AND user_id=1"
    )
    assert row["voice_consecutive_minutes"] == 2


@pytest.mark.asyncio
async def test_add_voice_minute_cambio_canale_riazzera_i_consecutivi(repo, clean_db):
    await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=True)
    await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=True)
    await repo.add_voice_minute(100, 1, current_channel_id=6000, is_eligible=True)  # canale diverso
    row = await clean_db.fetchrow(
        "SELECT voice_consecutive_minutes, voice_channel_id FROM leveling_totals WHERE guild_id=100 AND user_id=1"
    )
    assert row["voice_consecutive_minutes"] == 1
    assert row["voice_channel_id"] == 6000


@pytest.mark.asyncio
async def test_add_voice_minute_rollover_giornaliero(repo, clean_db):
    # Simula un utente che ha già accumulato minuti IERI: il prossimo
    # minuto di oggi deve ripartire da zero, non sommarsi a ieri.
    await clean_db.execute(
        """
        INSERT INTO leveling_totals (guild_id, user_id, voice_minutes_today, voice_activity_date)
        VALUES (100, 1, 300, $1)
        """,
        date.today() - timedelta(days=1),
    )
    await repo.add_voice_minute(100, 1, current_channel_id=5000, is_eligible=True)
    row = await clean_db.fetchrow(
        "SELECT voice_minutes_today FROM leveling_totals WHERE guild_id=100 AND user_id=1"
    )
    assert row["voice_minutes_today"] == 1  # non 301


@pytest.mark.asyncio
async def test_add_coins_positivo_e_negativo(repo):
    saldo = await repo.add_coins(100, 1, 500)
    assert saldo == 500
    saldo = await repo.add_coins(100, 1, -200)
    assert saldo == 300


@pytest.mark.asyncio
async def test_transfer_coins_con_saldo_sufficiente(repo):
    await repo.add_coins(100, 1, 1000)
    trasferito = await repo.transfer_coins(100, from_user_id=1, to_user_id=2, amount=300)
    assert trasferito is True

    mittente = await repo.get_totals(100, 1)
    destinatario = await repo.get_totals(100, 2)
    assert mittente.coins_total == 700
    assert destinatario.coins_total == 300


@pytest.mark.asyncio
async def test_transfer_coins_con_saldo_insufficiente_fallisce(repo):
    await repo.add_coins(100, 1, 100)
    trasferito = await repo.transfer_coins(100, from_user_id=1, to_user_id=2, amount=500)
    assert trasferito is False

    # Nessuna scrittura deve essere avvenuta: il mittente mantiene il
    # saldo originale, il destinatario resta a zero.
    mittente = await repo.get_totals(100, 1)
    destinatario = await repo.get_totals(100, 2)
    assert mittente.coins_total == 100
    assert destinatario.coins_total == 0


@pytest.mark.asyncio
async def test_transfer_coins_importo_non_positivo_solleva_errore(repo):
    with pytest.raises(ValueError):
        await repo.transfer_coins(100, from_user_id=1, to_user_id=2, amount=0)


@pytest.mark.asyncio
async def test_set_last_daily_e_last_work(repo):
    from datetime import datetime, timezone
    ora = datetime.now(timezone.utc)
    await repo.set_last_daily(100, 1, ora)
    await repo.set_last_work(100, 1, ora)

    totali = await repo.get_totals(100, 1)
    assert totali.last_daily_at is not None
    assert totali.last_work_at is not None


@pytest.mark.asyncio
async def test_leaderboard_xp_alltime_ordinata_correttamente(repo):
    await repo.add_coins(100, 1, 0)  # crea la riga senza XP
    await repo.add_text_xp(100, 1)
    await repo.add_text_xp(100, 2)
    await repo.add_text_xp(100, 2)  # bloccato dal cooldown, ma proviamoci comunque

    classifica = await repo.top_xp_alltime(100)
    assert len(classifica) >= 1
    # Ordine decrescente garantito dalla query.
    importi = [entry.amount for entry in classifica]
    assert importi == sorted(importi, reverse=True)


@pytest.mark.asyncio
async def test_leaderboard_non_mischia_server_diversi(repo):
    await repo.add_text_xp(100, 1)
    await repo.add_text_xp(200, 1)

    classifica_100 = await repo.top_xp_alltime(100)
    classifica_200 = await repo.top_xp_alltime(200)
    assert len(classifica_100) == 1
    assert len(classifica_200) == 1


@pytest.mark.asyncio
async def test_leaderboard_period_filtra_sul_periodo_corrente(repo, clean_db):
    await repo.add_text_xp(100, 1)

    # Inseriamo manualmente attività di un periodo PASSATO per un
    # altro utente: non deve comparire nella classifica del periodo
    # corrente.
    await clean_db.execute(
        """
        INSERT INTO leveling_activity (guild_id, user_id, period_key, xp)
        VALUES (100, 999, '2020-01', 99999)
        """
    )

    classifica = await repo.top_xp_period(100)
    user_ids = {entry.user_id for entry in classifica}
    assert 999 not in user_ids
    assert 1 in user_ids


# ======================================================================
# Decadimento settimanale coin personali (SPEC.md §15.15)
# ======================================================================

PERIODO = "2026-W39"


@pytest.mark.asyncio
async def test_list_users_needing_weekly_decay_include_chi_ha_saldo_e_non_decaduto(repo):
    await repo.add_coins(100, 1, 500)

    da_decadere = await repo.list_users_needing_weekly_decay(PERIODO)

    assert (100, 1) in da_decadere


@pytest.mark.asyncio
async def test_list_users_needing_weekly_decay_esclude_saldo_al_minimo(repo):
    await repo.add_coins(100, 1, 1)  # saldo 1: decadimento è no-op

    da_decadere = await repo.list_users_needing_weekly_decay(PERIODO)

    assert (100, 1) not in da_decadere


@pytest.mark.asyncio
async def test_list_users_needing_weekly_decay_esclude_chi_ha_gia_il_periodo_coperto(
    repo, clean_db
):
    await repo.add_coins(100, 1, 500)
    await repo.apply_weekly_decay(100, 1, PERIODO)

    da_decadere = await repo.list_users_needing_weekly_decay(PERIODO)

    assert (100, 1) not in da_decadere


@pytest.mark.asyncio
async def test_list_users_needing_weekly_decay_non_mischia_server_diversi(repo):
    await repo.add_coins(100, 1, 500)
    await repo.add_coins(200, 1, 500)

    da_decadere = await repo.list_users_needing_weekly_decay(PERIODO)

    assert (100, 1) in da_decadere
    assert (200, 1) in da_decadere


@pytest.mark.asyncio
async def test_apply_weekly_decay_riduce_il_saldo_del_10_percento(repo):
    await repo.add_coins(100, 1, 500)

    prima, dopo = await repo.apply_weekly_decay(100, 1, PERIODO)

    assert prima == 500
    assert dopo == 450
    assert (await repo.get_totals(100, 1)).coins_total == 450


@pytest.mark.asyncio
async def test_apply_weekly_decay_marca_il_periodo_coperto(repo, clean_db):
    await repo.add_coins(100, 1, 500)
    await repo.apply_weekly_decay(100, 1, PERIODO)

    row = await clean_db.fetchrow(
        "SELECT last_weekly_decay_period FROM leveling_totals WHERE guild_id = 100 AND user_id = 1"
    )
    assert row["last_weekly_decay_period"] == PERIODO


@pytest.mark.asyncio
async def test_apply_weekly_decay_su_utente_senza_riga_non_solleva_errore(repo):
    # Utente mai visto (nessuna riga in leveling_totals): saldo 0,
    # il decadimento non deve creare una riga né sollevare eccezioni
    # (non c'è nulla su cui fare UPDATE — la lista da decadere non lo
    # includerebbe comunque, ma il metodo resta sicuro se chiamato).
    prima, dopo = await repo.apply_weekly_decay(100, 999, PERIODO)
    assert prima == 0
    assert dopo == 0
