"""
tests/test_guild_clan_role_service.py
=========================================
Test di core/guild_clan_role_service.py — sincronizzazione dei ruoli
Discord condivisi "Capo Clan"/"Admin Clan" e degli overwrite
per-categoria (SPEC.md §15.14). Nessun database qui: solo oggetti
Discord finti fedeli (tests/support/discord_fakes.py).

SEC-4/SEC-17: un ruolo già esistente con quel nome viene assegnato
solo se supera core.role_safety.check_role_assignable.
"""

import logging
from unittest.mock import MagicMock, create_autospec

import aiohttp
import discord
import pytest

from core.guild_clan_role_service import (
    ADMIN_CLAN_ROLE_NAME,
    CAPO_CLAN_ROLE_NAME,
    clear_member_clan_presence,
    get_or_create_shared_role,
    grant_member_access,
    grant_officer_access,
    revoke_access,
    sync_member_clan_role,
    sync_shared_role,
)
from tests.support.discord_fakes import fake_guild, fake_member, fake_role


def _forbidden() -> discord.Forbidden:
    risposta = create_autospec(aiohttp.ClientResponse, instance=True)
    risposta.status = 403
    risposta.reason = "Forbidden"
    return discord.Forbidden(risposta, "niente permessi")


def _FakeCategory(category_id: int = 1, forbidden: bool = False) -> MagicMock:
    """
    Categoria finta (autospec) che ricorda gli overwrite impostati in
    `overwrites_impostati`, come farebbe Discord.
    """
    categoria = create_autospec(discord.CategoryChannel, instance=True)
    categoria.id = category_id
    categoria.overwrites_impostati = {}

    async def _set_permissions(target, *, overwrite=None, reason=None):
        if forbidden:
            raise _forbidden()
        if overwrite is None:
            categoria.overwrites_impostati.pop(target, None)
        else:
            categoria.overwrites_impostati[target] = overwrite

    categoria.set_permissions.side_effect = _set_permissions
    return categoria


def _FakeMember(member_id: int) -> MagicMock:
    """Membro finto (autospec) i cui ruoli cambiano con add/remove_roles."""
    membro = fake_member(member_id)

    async def _add_roles(*roles, reason=None, atomic=True):
        membro.roles.extend(r for r in roles if r not in membro.roles)

    async def _remove_roles(*roles, reason=None, atomic=True):
        membro.roles[:] = [r for r in membro.roles if r not in roles]

    membro.add_roles.side_effect = _add_roles
    membro.remove_roles.side_effect = _remove_roles
    return membro


def _FakeGuild(
    roles: list | None = None,
    forbidden_create_role: bool = False,
    permessi_everyone: discord.Permissions | None = None,
) -> MagicMock:
    """
    Server finto (autospec) col ruolo del bot in alto. `create_role`
    si comporta come Discord: un ruolo creato senza `permissions`
    eredita i permessi di @everyone.
    """
    bot = fake_member(999, "Yokai Bot", bot=True)
    bot.top_role = fake_role(900, "Yokai Bot", position=50)
    server = fake_guild(1, me=bot)
    server.default_role = fake_role(0, "@everyone", position=0, permissions=permessi_everyone)
    server.roles = list(roles or [])
    server.ruoli_creati = []

    async def _create_role(**kwargs):
        if forbidden_create_role:
            raise _forbidden()
        ruolo = fake_role(
            1000 + len(server.ruoli_creati),
            kwargs["name"],
            position=1,
            permissions=kwargs.get("permissions", server.default_role.permissions),
        )
        server.roles.append(ruolo)
        server.ruoli_creati.append(ruolo)
        return ruolo

    server.create_role.side_effect = _create_role
    return server


def _FakeRole(role_id: int, name: str, **opzioni) -> MagicMock:
    opzioni.setdefault("position", 1)
    return fake_role(role_id, name, **opzioni)


@pytest.mark.asyncio
async def test_get_or_create_shared_role_crea_se_assente():
    guild = _FakeGuild()

    ruolo = await get_or_create_shared_role(guild, CAPO_CLAN_ROLE_NAME)

    assert ruolo is not None
    assert ruolo.name == CAPO_CLAN_ROLE_NAME
    assert len(guild.ruoli_creati) == 1


@pytest.mark.asyncio
async def test_get_or_create_shared_role_riusa_quello_esistente():
    esistente = _FakeRole(5, CAPO_CLAN_ROLE_NAME)
    guild = _FakeGuild(roles=[esistente])

    ruolo = await get_or_create_shared_role(guild, CAPO_CLAN_ROLE_NAME)

    assert ruolo is esistente
    assert len(guild.ruoli_creati) == 0


@pytest.mark.asyncio
async def test_get_or_create_shared_role_permessi_mancanti_ritorna_none():
    guild = _FakeGuild(forbidden_create_role=True)

    ruolo = await get_or_create_shared_role(guild, CAPO_CLAN_ROLE_NAME)

    assert ruolo is None


@pytest.mark.asyncio
async def test_sync_shared_role_aggiunge_quando_deve_averlo():
    guild = _FakeGuild()
    membro = _FakeMember(1)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, True)

    assert len(membro.roles) == 1
    assert membro.roles[0].name == CAPO_CLAN_ROLE_NAME
    membro.add_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_shared_role_non_aggiunge_due_volte():
    ruolo = _FakeRole(5, CAPO_CLAN_ROLE_NAME)
    guild = _FakeGuild(roles=[ruolo])
    membro = _FakeMember(1)
    membro.roles.append(ruolo)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, True)

    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_shared_role_rimuove_quando_non_deve_piu_averlo():
    ruolo = _FakeRole(5, CAPO_CLAN_ROLE_NAME)
    guild = _FakeGuild(roles=[ruolo])
    membro = _FakeMember(1)
    membro.roles.append(ruolo)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, False)

    assert ruolo not in membro.roles
    membro.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_shared_role_non_rimuove_se_non_lo_aveva():
    guild = _FakeGuild()
    membro = _FakeMember(1)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, False)

    membro.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_member_access_imposta_overwrite_base():
    categoria = _FakeCategory()
    membro = _FakeMember(1)

    await grant_member_access(categoria, membro)

    assert categoria.overwrites_impostati[membro].manage_channels is not True


@pytest.mark.asyncio
async def test_grant_officer_access_imposta_overwrite_estesi():
    categoria = _FakeCategory()
    membro = _FakeMember(1)

    await grant_officer_access(categoria, membro)

    assert categoria.overwrites_impostati[membro].manage_channels is True
    assert categoria.overwrites_impostati[membro].view_channel is True


@pytest.mark.asyncio
async def test_grant_access_con_categoria_none_non_fa_nulla():
    membro = _FakeMember(1)
    await grant_member_access(None, membro)
    await grant_officer_access(None, membro)
    await revoke_access(None, membro)
    # nessuna eccezione: è il comportamento atteso quando il clan
    # non ha ancora una categoria Discord.


@pytest.mark.asyncio
async def test_revoke_access_rimuove_overwrite():
    categoria = _FakeCategory()
    membro = _FakeMember(1)
    await grant_officer_access(categoria, membro)

    await revoke_access(categoria, membro)

    assert membro not in categoria.overwrites_impostati


@pytest.mark.asyncio
async def test_sync_member_clan_role_owner_da_ruolo_e_overwrite_ufficiale():
    guild = _FakeGuild()
    categoria = _FakeCategory()
    membro = _FakeMember(1)

    await sync_member_clan_role(guild, categoria, membro, "owner")

    assert any(r.name == CAPO_CLAN_ROLE_NAME for r in membro.roles)
    assert not any(r.name == ADMIN_CLAN_ROLE_NAME for r in membro.roles)
    assert categoria.overwrites_impostati[membro].manage_channels is True


@pytest.mark.asyncio
async def test_sync_member_clan_role_admin_da_ruolo_e_overwrite_ufficiale():
    guild = _FakeGuild()
    categoria = _FakeCategory()
    membro = _FakeMember(1)

    await sync_member_clan_role(guild, categoria, membro, "admin")

    assert any(r.name == ADMIN_CLAN_ROLE_NAME for r in membro.roles)
    assert not any(r.name == CAPO_CLAN_ROLE_NAME for r in membro.roles)
    assert categoria.overwrites_impostati[membro].manage_channels is True


@pytest.mark.asyncio
async def test_sync_member_clan_role_member_da_overwrite_base_senza_ruoli():
    guild = _FakeGuild()
    categoria = _FakeCategory()
    membro = _FakeMember(1)

    await sync_member_clan_role(guild, categoria, membro, "member")

    assert membro.roles == []
    assert categoria.overwrites_impostati[membro].manage_channels is not True
    assert categoria.overwrites_impostati[membro].view_channel is True


@pytest.mark.asyncio
async def test_sync_member_clan_role_da_admin_a_member_rimuove_ruolo_e_declassa_overwrite():
    guild = _FakeGuild()
    categoria = _FakeCategory()
    membro = _FakeMember(1)
    await sync_member_clan_role(guild, categoria, membro, "admin")

    await sync_member_clan_role(guild, categoria, membro, "member")

    assert not any(r.name == ADMIN_CLAN_ROLE_NAME for r in membro.roles)
    assert categoria.overwrites_impostati[membro].manage_channels is not True


@pytest.mark.asyncio
async def test_clear_member_clan_presence_rimuove_tutto():
    guild = _FakeGuild()
    categoria = _FakeCategory()
    membro = _FakeMember(1)
    await sync_member_clan_role(guild, categoria, membro, "owner")

    await clear_member_clan_presence(guild, categoria, membro)

    assert membro.roles == []
    assert membro not in categoria.overwrites_impostati


# ============================================================================
# SEC-4/SEC-17 — il ruolo condiviso passa da check_role_assignable.
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("nome_ruolo", [CAPO_CLAN_ROLE_NAME, ADMIN_CLAN_ROLE_NAME])
async def test_un_ruolo_esistente_con_permessi_pericolosi_non_viene_assegnato(nome_ruolo, caplog):
    # Chiunque possa gestire i ruoli può chiamare un ruolo "Admin Clan":
    # il bot non deve distribuirlo a ogni admin di clan.
    pericoloso = _FakeRole(5, nome_ruolo, permissions=discord.Permissions(administrator=True))
    guild = _FakeGuild(roles=[pericoloso])
    membro = _FakeMember(1)

    with caplog.at_level(logging.WARNING, logger="core.guild_clan_role_service"):
        await sync_shared_role(guild, membro, nome_ruolo, True)

    membro.add_roles.assert_not_awaited()
    assert membro.roles == []
    assert any("administrator" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_un_ruolo_esistente_sopra_quello_del_bot_non_viene_assegnato():
    in_alto = _FakeRole(5, CAPO_CLAN_ROLE_NAME, position=99)
    guild = _FakeGuild(roles=[in_alto])
    membro = _FakeMember(1)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, True)

    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_un_ruolo_gestito_da_un_integrazione_non_viene_assegnato():
    gestito = _FakeRole(5, CAPO_CLAN_ROLE_NAME, managed=True)
    guild = _FakeGuild(roles=[gestito])
    membro = _FakeMember(1)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, True)

    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_il_ruolo_rifiutato_non_blocca_gli_overwrite_di_categoria():
    pericoloso = _FakeRole(
        5, ADMIN_CLAN_ROLE_NAME, permissions=discord.Permissions(manage_guild=True)
    )
    guild = _FakeGuild(roles=[pericoloso])
    categoria = _FakeCategory()
    membro = _FakeMember(1)

    await sync_member_clan_role(guild, categoria, membro, "admin")

    assert pericoloso not in membro.roles
    assert categoria.overwrites_impostati[membro].manage_channels is True


@pytest.mark.asyncio
async def test_un_ruolo_diventato_pericoloso_si_puo_ancora_togliere():
    # Il controllo vale solo per ASSEGNARE: chi viene declassato deve
    # perdere il ruolo anche se nel frattempo è diventato pericoloso.
    pericoloso = _FakeRole(
        5, ADMIN_CLAN_ROLE_NAME, permissions=discord.Permissions(administrator=True)
    )
    guild = _FakeGuild(roles=[pericoloso])
    membro = _FakeMember(1)
    membro.roles.append(pericoloso)

    await sync_shared_role(guild, membro, ADMIN_CLAN_ROLE_NAME, False)

    assert pericoloso not in membro.roles


@pytest.mark.asyncio
async def test_il_ruolo_creato_dal_bot_non_ha_permessi_e_viene_assegnato():
    # Su Discord un ruolo creato senza `permissions` eredita quelli di
    # @everyone, che di solito comprendono "menziona @everyone": il
    # controllo lo rifiuterebbe. Il ruolo è solo un'etichetta, quindi
    # nasce senza alcun permesso.
    guild = _FakeGuild(
        permessi_everyone=discord.Permissions(send_messages=True, mention_everyone=True)
    )
    membro = _FakeMember(1)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, True)

    assert guild.ruoli_creati[0].permissions == discord.Permissions.none()
    assert membro.roles == guild.ruoli_creati
