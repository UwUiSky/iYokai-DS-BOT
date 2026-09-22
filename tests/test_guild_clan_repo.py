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
async def test_increment_channels_unlocked(repo):
    clan_id = await _crea_clan(repo)
    await repo.increment_channels_unlocked(clan_id)
    await repo.increment_channels_unlocked(clan_id)

    assert (await repo.get_clan(clan_id)).channels_unlocked == 2


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
