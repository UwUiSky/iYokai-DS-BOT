"""
tests/test_guild_clan_role_service.py
=========================================
Test di core/guild_clan_role_service.py — sincronizzazione dei ruoli
Discord condivisi "Capo Clan"/"Admin Clan" e degli overwrite
per-categoria (SPEC.md §15.14). Nessun database qui: solo oggetti
Discord finti, come già fatto per gli altri worker/comandi.
"""

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


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


class _FakeRole:
    def __init__(self, role_id: int, name: str) -> None:
        self.id = role_id
        self.name = name

    def __eq__(self, other) -> bool:
        return isinstance(other, _FakeRole) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)


class _FakeCategory:
    def __init__(self, category_id: int = 1) -> None:
        self.id = category_id
        self.overwrites_impostati: dict = {}
        self._forbidden = False

    async def set_permissions(self, target, overwrite=None) -> None:
        if self._forbidden:
            raise discord.Forbidden(response=_FakeHTTPResponse(), message="niente permessi")
        if overwrite is None:
            self.overwrites_impostati.pop(target, None)
        else:
            self.overwrites_impostati[target] = overwrite


class _FakeMember:
    def __init__(self, member_id: int) -> None:
        self.id = member_id
        self.roles: list = []
        self.chiamate_add_roles: list = []
        self.chiamate_remove_roles: list = []

    def __eq__(self, other) -> bool:
        return isinstance(other, _FakeMember) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        return f"Utente#{self.id}"

    async def add_roles(self, *roles, reason=None) -> None:
        self.chiamate_add_roles.append(roles)
        for r in roles:
            if r not in self.roles:
                self.roles.append(r)

    async def remove_roles(self, *roles, reason=None) -> None:
        self.chiamate_remove_roles.append(roles)
        for r in roles:
            if r in self.roles:
                self.roles.remove(r)


class _FakeGuild:
    def __init__(self, guild_id: int = 1, roles: list | None = None, forbidden_create_role: bool = False) -> None:
        self.id = guild_id
        self.roles = roles or []
        self._next_role_id = 1000
        self._forbidden_create_role = forbidden_create_role
        self.ruoli_creati: list = []

    async def create_role(self, name: str, mentionable: bool = False, reason=None):
        if self._forbidden_create_role:
            raise discord.Forbidden(response=_FakeHTTPResponse(), message="niente permessi")
        ruolo = _FakeRole(self._next_role_id, name)
        self._next_role_id += 1
        self.roles.append(ruolo)
        self.ruoli_creati.append(ruolo)
        return ruolo


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
    assert len(membro.chiamate_add_roles) == 1


@pytest.mark.asyncio
async def test_sync_shared_role_non_aggiunge_due_volte():
    ruolo = _FakeRole(5, CAPO_CLAN_ROLE_NAME)
    guild = _FakeGuild(roles=[ruolo])
    membro = _FakeMember(1)
    membro.roles.append(ruolo)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, True)

    assert len(membro.chiamate_add_roles) == 0


@pytest.mark.asyncio
async def test_sync_shared_role_rimuove_quando_non_deve_piu_averlo():
    ruolo = _FakeRole(5, CAPO_CLAN_ROLE_NAME)
    guild = _FakeGuild(roles=[ruolo])
    membro = _FakeMember(1)
    membro.roles.append(ruolo)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, False)

    assert ruolo not in membro.roles
    assert len(membro.chiamate_remove_roles) == 1


@pytest.mark.asyncio
async def test_sync_shared_role_non_rimuove_se_non_lo_aveva():
    guild = _FakeGuild()
    membro = _FakeMember(1)

    await sync_shared_role(guild, membro, CAPO_CLAN_ROLE_NAME, False)

    assert len(membro.chiamate_remove_roles) == 0


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
