"""
tests/test_guild_clan_repo.py
=================================
Test di GuildClanRepository contro PostgreSQL reale.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.guild_clan_repo import (
    ROLE_ADMIN,
    ROLE_OWNER,
    GuildClanRepository,
)

ORA = datetime.now(timezone.utc)


@pytest.fixture
def repo(clean_db):
    return GuildClanRepository(pool_provider=lambda: clean_db)


async def _crea_clan(repo, guild_id=100, tag="ABC", owner_id=1, deadline=None):
    return await repo.create_clan(
        guild_id, tag=tag, name="Il Mio Clan", owner_id=owner_id,
        officialize_deadline=deadline or (ORA + timedelta(hours=24)),
    )


# ----------------------------------------------------------------------
# Creazione e ciclo di vita del clan
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_clan_parte_in_deficit(repo):
    clan_id = await _crea_clan(repo)

    clan = await repo.get_clan(clan_id)
    assert clan.treasury_balance == -15_000
    assert clan.officialized is False


@pytest.mark.asyncio
async def test_create_clan_aggiunge_il_founder_come_owner(repo):
    clan_id = await _crea_clan(repo, owner_id=42)

    membro = await repo.get_member(clan_id, user_id=42)
    assert membro.role == ROLE_OWNER


@pytest.mark.asyncio
async def test_create_clan_registra_il_deficit_nel_registro(repo):
    clan_id = await _crea_clan(repo)

    # Nessun metodo pubblico legge il registro grezzo qui, ma la
    # classifica donazioni lo usa - verifichiamo indirettamente che
    # il deficit NON compaia come donazione (reason diverso).
    classifica = await repo.get_donation_leaderboard(clan_id)
    assert classifica == []


@pytest.mark.asyncio
async def test_tag_univoco_per_server(repo):
    await _crea_clan(repo, guild_id=100, tag="ABC")

    with pytest.raises(Exception):  # violazione UNIQUE(guild_id, tag)
        await _crea_clan(repo, guild_id=100, tag="ABC")


@pytest.mark.asyncio
async def test_stesso_tag_su_server_diversi_e_permesso(repo):
    id1 = await _crea_clan(repo, guild_id=100, tag="ABC")
    id2 = await _crea_clan(repo, guild_id=200, tag="ABC")

    assert id1 != id2


@pytest.mark.asyncio
async def test_is_tag_taken(repo):
    await _crea_clan(repo, guild_id=100, tag="ABC")

    assert await repo.is_tag_taken(100, "ABC") is True
    assert await repo.is_tag_taken(100, "XYZ") is False
    assert await repo.is_tag_taken(200, "ABC") is False  # server diverso


@pytest.mark.asyncio
async def test_set_officialized(repo):
    clan_id = await _crea_clan(repo)
    await repo.set_officialized(clan_id)

    assert (await repo.get_clan(clan_id)).officialized is True


@pytest.mark.asyncio
async def test_get_unofficialized_expired(repo):
    scaduto = await _crea_clan(repo, tag="OLD", deadline=ORA - timedelta(hours=1))
    non_scaduto = await _crea_clan(repo, tag="NEW", deadline=ORA + timedelta(hours=1))

    scaduti = await repo.get_unofficialized_expired(ORA)

    assert [c.id for c in scaduti] == [scaduto]


@pytest.mark.asyncio
async def test_get_unofficialized_expired_esclude_gia_ufficializzati(repo):
    clan_id = await _crea_clan(repo, deadline=ORA - timedelta(hours=1))
    await repo.set_officialized(clan_id)

    assert await repo.get_unofficialized_expired(ORA) == []


@pytest.mark.asyncio
async def test_delete_clan_rimuove_tutto(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=100)

    await repo.delete_clan(clan_id)

    assert await repo.get_clan(clan_id) is None
    assert await repo.list_members(clan_id) == []


@pytest.mark.asyncio
async def test_unlock_channel_scala_e_conta_solo_se_tutto_torna(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=15_000 + 60_000)

    assert await repo.unlock_channel(clan_id, expected_unlocked=0, cost=25_000) is True
    # Stesso acquisto ripetuto (doppio clic): i canali sbloccati non sono più 0.
    assert await repo.unlock_channel(clan_id, expected_unlocked=0, cost=25_000) is False
    # Saldo insufficiente per il secondo canale.
    assert await repo.unlock_channel(clan_id, expected_unlocked=1, cost=50_000) is False

    clan = await repo.get_clan(clan_id)
    assert clan.channels_unlocked == 1
    assert clan.treasury_balance == 35_000


@pytest.mark.asyncio
async def test_refund_channel_unlock_rimette_tutto_com_era(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=15_000 + 25_000)
    await repo.unlock_channel(clan_id, expected_unlocked=0, cost=25_000)

    await repo.refund_channel_unlock(clan_id, 25_000)

    clan = await repo.get_clan(clan_id)
    assert clan.channels_unlocked == 0
    assert clan.treasury_balance == 25_000


@pytest.mark.asyncio
async def test_add_voice_ticks_accumula(repo):
    clan_id = await _crea_clan(repo)
    await repo.add_voice_ticks(clan_id)
    await repo.add_voice_ticks(clan_id, count=59)

    assert (await repo.get_clan(clan_id)).total_voice_ticks == 60


@pytest.mark.asyncio
async def test_add_voice_ticks_valore_non_positivo_solleva(repo):
    clan_id = await _crea_clan(repo)
    with pytest.raises(ValueError):
        await repo.add_voice_ticks(clan_id, count=0)


@pytest.mark.asyncio
async def test_set_guild_boost_expiry(repo):
    clan_id = await _crea_clan(repo)
    scadenza = ORA + timedelta(hours=24)

    await repo.set_guild_boost_expiry(clan_id, scadenza)

    assert (await repo.get_clan(clan_id)).guild_boost_expires_at == scadenza


@pytest.mark.asyncio
async def test_set_member_boost_expiry(repo):
    clan_id = await _crea_clan(repo)
    scadenza = ORA + timedelta(hours=24)

    await repo.set_member_boost_expiry(clan_id, user_id=1, expires_at=scadenza)

    assert (await repo.get_member(clan_id, 1)).boost_expires_at == scadenza


# ----------------------------------------------------------------------
# Membri
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_member_e_count(repo):
    clan_id = await _crea_clan(repo)
    await repo.add_member(clan_id, user_id=2)
    await repo.add_member(clan_id, user_id=3)

    assert await repo.count_members(clan_id) == 3  # owner + 2


@pytest.mark.asyncio
async def test_add_member_ripetuto_non_duplica(repo):
    clan_id = await _crea_clan(repo)
    await repo.add_member(clan_id, user_id=2)
    await repo.add_member(clan_id, user_id=2)

    assert await repo.count_members(clan_id) == 2


@pytest.mark.asyncio
async def test_remove_member(repo):
    clan_id = await _crea_clan(repo)
    await repo.add_member(clan_id, user_id=2)

    assert await repo.remove_member(clan_id, user_id=2) is True
    assert await repo.get_member(clan_id, user_id=2) is None


@pytest.mark.asyncio
async def test_set_member_role(repo):
    clan_id = await _crea_clan(repo)
    await repo.add_member(clan_id, user_id=2)

    await repo.set_member_role(clan_id, user_id=2, role=ROLE_ADMIN)

    assert (await repo.get_member(clan_id, user_id=2)).role == ROLE_ADMIN


@pytest.mark.asyncio
async def test_count_members_with_role(repo):
    clan_id = await _crea_clan(repo, owner_id=1)
    await repo.add_member(clan_id, user_id=2, role=ROLE_ADMIN)
    await repo.add_member(clan_id, user_id=3, role=ROLE_ADMIN)

    assert await repo.count_members_with_role(clan_id, ROLE_ADMIN) == 2
    assert await repo.count_members_with_role(clan_id, ROLE_OWNER) == 1


@pytest.mark.asyncio
async def test_get_member_clan_in_guild(repo):
    clan_id = await _crea_clan(repo, guild_id=100, owner_id=1)

    clan = await repo.get_member_clan_in_guild(100, user_id=1)
    assert clan.id == clan_id


@pytest.mark.asyncio
async def test_get_member_clan_in_guild_nessun_clan(repo):
    assert await repo.get_member_clan_in_guild(100, user_id=999) is None


# ----------------------------------------------------------------------
# Tesoreria
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_donate_aumenta_il_saldo(repo):
    clan_id = await _crea_clan(repo)

    nuovo_saldo = await repo.donate(clan_id, user_id=1, amount=20_000)

    assert nuovo_saldo == -15_000 + 20_000


@pytest.mark.asyncio
async def test_donate_importo_non_positivo_solleva(repo):
    clan_id = await _crea_clan(repo)
    with pytest.raises(ValueError):
        await repo.donate(clan_id, user_id=1, amount=0)


@pytest.mark.asyncio
async def test_spend_from_treasury_con_saldo_sufficiente(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=50_000)  # saldo: 35.000

    riuscito = await repo.spend_from_treasury(clan_id, amount=25_000, reason="channel_unlock")

    assert riuscito is True
    assert (await repo.get_clan(clan_id)).treasury_balance == 10_000


@pytest.mark.asyncio
async def test_spend_from_treasury_saldo_insufficiente_non_scrive(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=15_000)  # saldo: 0

    riuscito = await repo.spend_from_treasury(clan_id, amount=25_000, reason="channel_unlock")

    assert riuscito is False
    assert (await repo.get_clan(clan_id)).treasury_balance == 0


@pytest.mark.asyncio
async def test_apply_treasury_delta_positivo(repo):
    clan_id = await _crea_clan(repo)
    await repo.apply_treasury_delta(clan_id, amount=500, reason="tick")

    assert (await repo.get_clan(clan_id)).treasury_balance == -15_000 + 500


@pytest.mark.asyncio
async def test_apply_treasury_delta_negativo_senza_verifica_saldo(repo):
    clan_id = await _crea_clan(repo)
    # Il saldo è già -15.000: apply_treasury_delta non verifica nulla,
    # a differenza di spend_from_treasury - lo fa scendere comunque.
    await repo.apply_treasury_delta(clan_id, amount=-1000, reason="monthly_decay")

    assert (await repo.get_clan(clan_id)).treasury_balance == -16_000


@pytest.mark.asyncio
async def test_transfer_between_treasuries(repo):
    da = await _crea_clan(repo, guild_id=100, tag="AAA", owner_id=1)
    verso = await _crea_clan(repo, guild_id=200, tag="BBB", owner_id=1)
    await repo.donate(da, user_id=1, amount=50_000)  # saldo "da": 35.000

    riuscito = await repo.transfer_between_treasuries(da, verso, amount=20_000)

    assert riuscito is True
    assert (await repo.get_clan(da)).treasury_balance == 15_000
    assert (await repo.get_clan(verso)).treasury_balance == -15_000 + 20_000


@pytest.mark.asyncio
async def test_transfer_between_treasuries_saldo_insufficiente(repo):
    da = await _crea_clan(repo, guild_id=100, tag="AAA")
    verso = await _crea_clan(repo, guild_id=200, tag="BBB")

    riuscito = await repo.transfer_between_treasuries(da, verso, amount=100_000)

    assert riuscito is False


@pytest.mark.asyncio
async def test_transfer_between_treasuries_verso_se_stesso_solleva(repo):
    clan_id = await _crea_clan(repo)
    with pytest.raises(ValueError):
        await repo.transfer_between_treasuries(clan_id, clan_id, amount=100)


@pytest.mark.asyncio
async def test_list_clans_owned_by_attraversa_i_server(repo):
    proprio_1 = await _crea_clan(repo, guild_id=100, tag="AAA", owner_id=1)
    proprio_2 = await _crea_clan(repo, guild_id=200, tag="BBB", owner_id=1)  # server diverso
    await _crea_clan(repo, guild_id=100, tag="CCC", owner_id=2)  # altro owner

    clan_ids = {c.id for c in await repo.list_clans_owned_by(1)}

    assert clan_ids == {proprio_1, proprio_2}


@pytest.mark.asyncio
async def test_list_clans_owned_by_nessuna_gilda_lista_vuota(repo):
    assert await repo.list_clans_owned_by(999) == []


@pytest.mark.asyncio
async def test_get_donation_leaderboard(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=100)
    await repo.donate(clan_id, user_id=2, amount=500)
    await repo.donate(clan_id, user_id=1, amount=50)  # seconda donazione, si somma

    classifica = await repo.get_donation_leaderboard(clan_id)

    assert classifica[0] == (2, 500)
    assert classifica[1] == (1, 150)


@pytest.mark.asyncio
async def test_get_donation_leaderboard_esclude_movimenti_di_sistema(repo):
    clan_id = await _crea_clan(repo)
    await repo.apply_treasury_delta(clan_id, amount=1000, reason="tick")  # non una donazione

    assert await repo.get_donation_leaderboard(clan_id) == []


# ----------------------------------------------------------------------
# XP di gilda e classifica clan
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_xp(repo):
    clan_id = await _crea_clan(repo)

    await repo.add_xp(clan_id, amount=1000)
    await repo.add_xp(clan_id, amount=500)

    assert (await repo.get_clan(clan_id)).total_xp == 1500


@pytest.mark.asyncio
async def test_add_xp_importo_non_positivo_solleva(repo):
    clan_id = await _crea_clan(repo)
    with pytest.raises(ValueError):
        await repo.add_xp(clan_id, amount=0)


@pytest.mark.asyncio
async def test_get_clan_leaderboard_ordinata_per_xp(repo):
    basso = await _crea_clan(repo, guild_id=100, tag="LOW")
    alto = await _crea_clan(repo, guild_id=100, tag="HIGH")
    await repo.add_xp(basso, amount=100)
    await repo.add_xp(alto, amount=9000)

    classifica = await repo.get_clan_leaderboard(100)

    assert [c.id for c in classifica] == [alto, basso]


@pytest.mark.asyncio
async def test_get_clan_leaderboard_solo_del_server_giusto(repo):
    await _crea_clan(repo, guild_id=100, tag="AAA")
    altro = await _crea_clan(repo, guild_id=200, tag="BBB")
    await repo.add_xp(altro, amount=9000)

    classifica = await repo.get_clan_leaderboard(100)

    assert altro not in [c.id for c in classifica]


# ----------------------------------------------------------------------
# Classifica MENSILE di gilda (SPEC.md §15.10, variante mancante)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_monthly_clan_leaderboard_ordinata_per_xp_del_periodo(repo):
    basso = await _crea_clan(repo, guild_id=100, tag="LOW")
    alto = await _crea_clan(repo, guild_id=100, tag="HIGH")
    await repo.add_xp(basso, amount=100)
    await repo.add_xp(alto, amount=9000)

    # Il periodo è quello corrente reale (add_xp accredita nel mese di
    # adesso): un valore fisso come "2026-09" fallisce al cambio di mese.
    periodo_corrente = datetime.now(timezone.utc).strftime("%Y-%m")
    classifica = await repo.get_monthly_clan_leaderboard(100, period=periodo_corrente)

    assert [(c.id, xp) for c, xp in classifica] == [(alto, 9000), (basso, 100)]


@pytest.mark.asyncio
async def test_get_monthly_clan_leaderboard_non_conta_periodi_diversi(repo):
    clan_id = await _crea_clan(repo, guild_id=100, tag="ABC")
    await repo.add_xp(clan_id, amount=9000)  # accreditata nel periodo corrente reale

    classifica = await repo.get_monthly_clan_leaderboard(100, period="1999-01")

    assert classifica == []


@pytest.mark.asyncio
async def test_get_monthly_clan_leaderboard_non_intacca_il_totale_alltime(repo):
    """Il totale all-time (clans.total_xp, mai azzerato) e la
    classifica mensile sono due assi indipendenti: aggiungere XP
    aggiorna entrambi, ma leggerne uno non ha alcun effetto
    sull'altro."""
    clan_id = await _crea_clan(repo, guild_id=100, tag="ABC")
    await repo.add_xp(clan_id, amount=100)
    await repo.add_xp(clan_id, amount=200)

    classifica_mensile = await repo.get_monthly_clan_leaderboard(100)
    classifica_alltime = await repo.get_clan_leaderboard(100)

    assert classifica_mensile[0][1] == 300
    assert classifica_alltime[0].total_xp == 300


@pytest.mark.asyncio
async def test_get_monthly_clan_leaderboard_solo_del_server_giusto(repo):
    await _crea_clan(repo, guild_id=100, tag="AAA")
    altro = await _crea_clan(repo, guild_id=200, tag="BBB")
    await repo.add_xp(altro, amount=9000)

    classifica = await repo.get_monthly_clan_leaderboard(100)

    assert classifica == []


@pytest.mark.asyncio
async def test_get_monthly_clan_leaderboard_clan_senza_attivita_non_appare(repo):
    await _crea_clan(repo, guild_id=100, tag="ABC")  # nessuna XP mai assegnata

    classifica = await repo.get_monthly_clan_leaderboard(100)

    assert classifica == []


@pytest.mark.asyncio
async def test_apply_text_tick_traccia_anche_la_classifica_mensile(repo):
    clan_id = await _crea_clan(repo, owner_id=1, guild_id=100)

    await repo.apply_text_tick(clan_id, user_id=1)

    classifica = await repo.get_monthly_clan_leaderboard(100)
    assert classifica == [((await repo.get_clan(clan_id)), 30)]  # TEXT_TICK_XP


# ----------------------------------------------------------------------
# Decadimento mensile tesoreria
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_officialized_clans_solo_ufficializzati(repo):
    ufficializzato = await _crea_clan(repo, tag="OK")
    await repo.set_officialized(ufficializzato)
    await _crea_clan(repo, tag="NO")  # non ufficializzato

    clan = await repo.list_officialized_clans()

    assert [c.id for c in clan] == [ufficializzato]


@pytest.mark.asyncio
async def test_apply_monthly_decay_applica_il_dieci_percento(repo):
    clan_id = await _crea_clan(repo)
    await repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    saldo_prima, saldo_dopo = await repo.apply_monthly_decay(clan_id, period="2026-09")

    assert saldo_prima == 100_000
    assert saldo_dopo == 90_000
    assert (await repo.get_clan(clan_id)).last_decay_period == "2026-09"


@pytest.mark.asyncio
async def test_apply_monthly_decay_su_saldo_negativo_non_lo_tocca(repo):
    clan_id = await _crea_clan(repo)  # saldo: -15.000, ancora in deficit

    saldo_prima, saldo_dopo = await repo.apply_monthly_decay(clan_id, period="2026-09")

    assert saldo_prima == -15_000
    assert saldo_dopo == -15_000


@pytest.mark.asyncio
async def test_apply_monthly_decay_delta_corretto_con_saldo_cambiato_dopo_la_lista(repo):
    """
    Regressione per il bug del delta calcolato sul saldo "stale": se tra
    la lettura non bloccata (list_officialized_clans, usata dal worker
    per decidere quali clan processare) e la scrittura sotto lock
    (apply_monthly_decay) il saldo del clan cambia — ad esempio per una
    donazione arrivata nel frattempo — apply_monthly_decay deve
    restituire (saldo_prima, saldo_dopo) calcolati SUL SALDO REALE letto
    sotto FOR UPDATE, non su quello (ormai vecchio) letto dalla lista.
    """
    clan_id = await _crea_clan(repo)
    await repo.set_officialized(clan_id)
    await repo.donate(clan_id, user_id=1, amount=115_000)  # saldo: 100.000

    clan_da_lista_prima_della_donazione = (
        await repo.list_officialized_clans()
    )  # snapshot preso PRIMA di una seconda donazione simulata sotto

    # Simula una donazione arrivata dopo lo snapshot ma prima del lock.
    await repo.donate(clan_id, user_id=2, amount=50_000)  # saldo: 150.000

    saldo_prima, saldo_dopo = await repo.apply_monthly_decay(clan_id, period="2026-09")

    # Il delta deve basarsi sul saldo REALE (150.000), non su quello
    # ottenuto dalla lista presa prima della seconda donazione.
    assert saldo_prima == 150_000
    assert saldo_dopo == 135_000
    assert [c.treasury_balance for c in clan_da_lista_prima_della_donazione] == [100_000]


# ----------------------------------------------------------------------
# Lato TESTUALE del guadagno ×2 di gilda (SPEC.md §15.14)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_text_tick_assegna_xp_di_gilda(repo):
    clan_id = await _crea_clan(repo, owner_id=1)

    assegnato = await repo.apply_text_tick(clan_id, user_id=1)

    assert assegnato is True
    assert (await repo.get_clan(clan_id)).total_xp == 30  # TEXT_TICK_XP


@pytest.mark.asyncio
async def test_apply_text_tick_rispetta_il_cooldown(repo):
    clan_id = await _crea_clan(repo, owner_id=1)

    await repo.apply_text_tick(clan_id, user_id=1)
    assegnato_di_nuovo = await repo.apply_text_tick(clan_id, user_id=1)

    assert assegnato_di_nuovo is False
    assert (await repo.get_clan(clan_id)).total_xp == 30  # solo il primo


@pytest.mark.asyncio
async def test_apply_text_tick_utente_non_membro_non_assegna(repo):
    clan_id = await _crea_clan(repo, owner_id=1)

    assegnato = await repo.apply_text_tick(clan_id, user_id=999)

    assert assegnato is False
    assert (await repo.get_clan(clan_id)).total_xp == 0
