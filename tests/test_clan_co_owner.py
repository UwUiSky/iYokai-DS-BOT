"""
tests/test_clan_co_owner.py
===========================
M 9.14: il ruolo co_owner si assegna con /clan promuovi, al massimo uno
per gilda, e vale come un ufficiale (può invitare, espellere, comprare).
Database vero.
Funzioni coperte: SPEC §15.14
"""

import asyncio

import pytest

from core.repositories.guild_clan_repo import ROLE_CO_OWNER
from tests.support.concorrenza import apri_connessioni
from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _crea_clan_con_categoria,
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

GUILD_ID = 100
CAPO = 1


async def _gilda_con_membri(clan_repo, guild, membri: list[int]):
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    for user_id in membri:
        await clan_repo.add_member(clan_id, user_id)
    return clan_id, categoria


async def _promuovi(cog, guild, membro, ruolo: str):
    interazione = _FakeInteraction(guild, user=_FakeMember(CAPO))
    await cog.clan_promuovi.callback(cog, interazione, membro=membro, ruolo=ruolo)
    return interazione


@pytest.mark.asyncio
async def test_promozione_a_co_owner(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, categoria = await _gilda_con_membri(clan_repo, guild, [2])
    vice = _FakeMember(2)

    interazione = await _promuovi(cog, guild, vice, "co_owner")

    assert "co_owner" in interazione.response.sent_messages[0]
    assert (await clan_repo.get_member(clan_id, 2)).role == ROLE_CO_OWNER
    assert (await clan_repo.get_clan(clan_id)).co_owner_id == 2
    # Su Discord vale come un ufficiale: può gestire i canali della gilda.
    assert categoria.overwrites_impostati[vice].manage_channels is True
    # E /clan info lo mostra.
    info = _FakeInteraction(guild, user=_FakeMember(CAPO))
    await cog.clan_info.callback(cog, info, tag=None)
    assert any(campo.name == "Co-Owner" for campo in info.response.sent_embeds[0].fields)


@pytest.mark.asyncio
async def test_un_solo_co_owner_per_gilda(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _gilda_con_membri(clan_repo, guild, [2, 3])
    await _promuovi(cog, guild, _FakeMember(2), "co_owner")

    interazione = await _promuovi(cog, guild, _FakeMember(3), "co_owner")

    assert "ha già un Co-Owner" in interazione.response.sent_messages[0]
    assert (await clan_repo.get_member(clan_id, 3)).role == "member"
    assert (await clan_repo.get_clan(clan_id)).co_owner_id == 2


@pytest.mark.asyncio
async def test_due_promozioni_a_co_owner_insieme_ne_passa_una(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _gilda_con_membri(clan_repo, guild, [2, 3])

    await asyncio.gather(
        _promuovi(cog, guild, _FakeMember(2), "co_owner"),
        _promuovi(cog, guild, _FakeMember(3), "co_owner"),
    )

    assert await clan_repo.count_members_with_role(clan_id, ROLE_CO_OWNER) == 1


@pytest.mark.asyncio
async def test_co_owner_retrocesso_o_espulso_libera_il_posto(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _gilda_con_membri(clan_repo, guild, [2, 3])
    await _promuovi(cog, guild, _FakeMember(2), "co_owner")

    await _promuovi(cog, guild, _FakeMember(2), "member")
    assert (await clan_repo.get_clan(clan_id)).co_owner_id is None

    await _promuovi(cog, guild, _FakeMember(3), "co_owner")
    espulsione = _FakeInteraction(guild, user=_FakeMember(CAPO))
    await cog.clan_espelli.callback(cog, espulsione, membro=_FakeMember(3))
    assert (await clan_repo.get_clan(clan_id)).co_owner_id is None


@pytest.mark.asyncio
async def test_co_owner_espelle_un_admin_ma_un_admin_non_espelle_il_co_owner(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, _ = await _gilda_con_membri(clan_repo, guild, [2, 3, 4])
    await _promuovi(cog, guild, _FakeMember(2), "co_owner")
    await _promuovi(cog, guild, _FakeMember(3), "admin")
    await _promuovi(cog, guild, _FakeMember(4), "admin")

    da_admin = _FakeInteraction(guild, user=_FakeMember(3))
    await cog.clan_espelli.callback(cog, da_admin, membro=_FakeMember(2))
    assert await clan_repo.get_member(clan_id, 2) is not None

    da_co_owner = _FakeInteraction(guild, user=_FakeMember(2))
    await cog.clan_espelli.callback(cog, da_co_owner, membro=_FakeMember(4))
    assert await clan_repo.get_member(clan_id, 4) is None
