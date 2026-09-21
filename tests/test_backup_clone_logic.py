"""
tests/test_backup_clone_logic.py
====================================
Test di core/backup_clone_logic.py con oggetti finti che replicano
l'interfaccia REALE di discord.Guild/discord.Role (attributi e firme
verificati prima di scrivere il codice) — non è possibile una
connessione Discord vera in questo ambiente.
"""

import discord
import pytest

from core.backup_clone_logic import clone_roles, remap_permission_overwrites


class _FakeRole(discord.Role):
    """Eredita davvero da discord.Role — serve perché
    remap_permission_overwrites() fa isinstance(..., discord.Role),
    che un oggetto finto senza questa eredità non supererebbe mai
    (trovato scrivendo questo stesso test). permissions/colour sono
    property di sola lettura che leggono da _permissions/_colour
    (int), diverso da id/name/position/hoist/mentionable/managed che
    sono attributi normali assegnabili — verificato prima di
    scrivere, non presunto."""

    def __init__(
        self,
        role_id: int,
        name: str,
        position: int,
        is_default: bool = False,
        managed: bool = False,
        permissions=None,
        colour=None,
        hoist: bool = False,
        mentionable: bool = False,
    ) -> None:
        self.id = role_id
        self.name = name
        self.position = position
        self._is_default = is_default
        self.managed = managed
        self._permissions = (permissions or discord.Permissions.none()).value
        self._colour = (colour or discord.Colour.default()).value
        self.hoist = hoist
        self.mentionable = mentionable

    def is_default(self) -> bool:
        return self._is_default


class _FakeTargetGuild:
    def __init__(self) -> None:
        self.chiamate_create_role: list[dict] = []
        self._ruoli_creati: dict[int, _FakeRole] = {}
        self._prossimo_id = 9000
        self.default_role = _FakeRole(0, "@everyone", 0, is_default=True)

    async def create_role(self, **kwargs) -> _FakeRole:
        self.chiamate_create_role.append(kwargs)
        nuovo_id = self._prossimo_id
        self._prossimo_id += 1
        nuovo_ruolo = _FakeRole(
            nuovo_id,
            kwargs["name"],
            position=len(self._ruoli_creati) + 1,
            permissions=kwargs.get("permissions"),
            colour=kwargs.get("colour"),
            hoist=kwargs.get("hoist", False),
            mentionable=kwargs.get("mentionable", False),
        )
        self._ruoli_creati[nuovo_id] = nuovo_ruolo
        return nuovo_ruolo

    def get_role(self, role_id: int):
        return self._ruoli_creati.get(role_id)


class _FakeSourceGuild:
    def __init__(self, roles: list[_FakeRole]) -> None:
        self.roles = roles


@pytest.mark.asyncio
async def test_clone_roles_ignora_everyone_e_managed():
    everyone = _FakeRole(1, "@everyone", 0, is_default=True)
    gestito = _FakeRole(2, "Bot Musicale", 1, managed=True)
    normale = _FakeRole(3, "Moderatore", 2)

    source = _FakeSourceGuild([everyone, gestito, normale])
    target = _FakeTargetGuild()

    mappa = await clone_roles(source, target)

    assert len(target.chiamate_create_role) == 1
    assert target.chiamate_create_role[0]["name"] == "Moderatore"
    assert 3 in mappa
    assert 1 not in mappa
    assert 2 not in mappa


@pytest.mark.asyncio
async def test_clone_roles_preserva_nome_permessi_colore():
    permessi = discord.Permissions(administrator=True)
    colore = discord.Colour.blue()
    ruolo = _FakeRole(
        5, "Admin", 1, permissions=permessi, colour=colore, hoist=True, mentionable=True
    )

    source = _FakeSourceGuild([ruolo])
    target = _FakeTargetGuild()

    await clone_roles(source, target)

    chiamata = target.chiamate_create_role[0]
    assert chiamata["name"] == "Admin"
    assert chiamata["permissions"] == permessi
    assert chiamata["colour"] == colore
    assert chiamata["hoist"] is True
    assert chiamata["mentionable"] is True


@pytest.mark.asyncio
async def test_clone_roles_crea_dal_piu_basso_al_piu_alto():
    alto = _FakeRole(1, "Alto", position=3)
    basso = _FakeRole(2, "Basso", position=1)
    medio = _FakeRole(3, "Medio", position=2)

    source = _FakeSourceGuild([alto, basso, medio])
    target = _FakeTargetGuild()

    await clone_roles(source, target)

    nomi_in_ordine = [c["name"] for c in target.chiamate_create_role]
    assert nomi_in_ordine == ["Basso", "Medio", "Alto"]


@pytest.mark.asyncio
async def test_clone_roles_restituisce_la_mappa_id_corretta():
    ruolo = _FakeRole(42, "Test", 1)
    source = _FakeSourceGuild([ruolo])
    target = _FakeTargetGuild()

    mappa = await clone_roles(source, target)

    assert 42 in mappa
    nuovo_id = mappa[42]
    assert target.get_role(nuovo_id).name == "Test"


class TestRemapPermissionOverwrites:
    def test_overwrite_per_ruolo_viene_rimappato(self):
        ruolo_originale = _FakeRole(10, "Mod", 1)
        ruolo_clonato = _FakeRole(20, "Mod", 1)
        target = _FakeTargetGuild()
        target._ruoli_creati[20] = ruolo_clonato

        overwrite_finto = object()
        source_overwrites = {ruolo_originale: overwrite_finto}
        role_id_map = {10: 20}

        risultato = remap_permission_overwrites(source_overwrites, role_id_map, target)

        assert risultato == {ruolo_clonato: overwrite_finto}

    def test_overwrite_per_everyone_va_sul_default_role_di_destinazione(self):
        everyone_originale = _FakeRole(1, "@everyone", 0, is_default=True)
        target = _FakeTargetGuild()

        overwrite_finto = object()
        source_overwrites = {everyone_originale: overwrite_finto}

        risultato = remap_permission_overwrites(source_overwrites, {}, target)

        assert risultato == {target.default_role: overwrite_finto}

    def test_ruolo_non_clonato_viene_saltato(self):
        ruolo_managed = _FakeRole(99, "Bot Role", 1, managed=True)
        target = _FakeTargetGuild()

        source_overwrites = {ruolo_managed: object()}
        # role_id_map non contiene 99, dato che clone_roles lo avrebbe
        # saltato (managed=True) - remap deve gestirlo senza sollevare.
        risultato = remap_permission_overwrites(source_overwrites, {}, target)

        assert risultato == {}

    def test_overwrite_per_membro_singolo_viene_saltato(self):
        class _FakeMember:
            id = 555

        target = _FakeTargetGuild()
        source_overwrites = {_FakeMember(): object()}

        risultato = remap_permission_overwrites(source_overwrites, {}, target)

        assert risultato == {}
