"""
tests/test_leveling_ruoli_classifica.py
=======================================
#124 B8 (LIV-044, 045): ruoli di classifica (primo, primi 3, primi 10) con il lavoro orario.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.leveling.ruoli_classifica as modulo
from cogs.leveling.ruoli_classifica import RuoliClassificaCog
from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
from core.leveling_ruoli_classifica_logic import differenze, fascia_di_posizione, fasce_degli_utenti
from core.repositories.leveling_repo import LeaderboardEntry, leveling_repo
from core.repositories.leveling_ruoli_classifica_repo import LevelingRuoliClassificaRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.moduli import attiva_livelli

GUILD = 100


# ---------------------------------------------------------------- logica
def test_liv045_fascia_piu_stretta():
    assert [fascia_di_posizione(p, (1, 3, 10)) for p in (1, 2, 3, 4, 10, 11)] == [1, 3, 3, 10, 10, None]
    assert fascia_di_posizione(2, (1, 10)) == 10  # senza il ruolo dei primi 3 vale quello dei primi 10
    assert fasce_degli_utenti([7, 8, 9], {1, 3}) == {7: 1, 8: 3, 9: 3}


def test_liv044_chi_cambia_fascia_riceve_il_nuovo_e_perde_il_vecchio():
    desiderate = {7: 1, 8: 3}
    possessori = {1: {8}, 3: {7, 9}}
    da_dare, da_togliere = differenze(desiderate, possessori)
    assert da_dare == [(7, 1), (8, 3)]
    assert da_togliere == [(7, 3), (8, 1), (9, 3)]
    assert differenze({7: 1}, {1: {7}}) == ([], [])  # già a posto: niente da fare


# ---------------------------------------------------------------- archivio
@pytest.mark.asyncio
async def test_liv044_archivio_un_ruolo_per_fascia(clean_db):
    r = LevelingRuoliClassificaRepository(pool_provider=lambda: clean_db)
    await r.imposta(GUILD, 1, 11)
    await r.imposta(GUILD, 1, 12)  # sostituisce
    await r.imposta(GUILD, 10, 13)
    assert await r.elenco(GUILD) == {1: 12, 10: 13}
    assert await r.server_con_ruoli() == [GUILD]
    assert await r.togli(GUILD, 1) and not await r.togli(GUILD, 1)
    with pytest.raises(ValueError):
        await r.imposta(GUILD, 5, 1)


# ---------------------------------------------------------------- cog
@pytest.fixture
async def cog(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    repo = LevelingRuoliClassificaRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_ruoli_classifica_repo", repo)
    monkeypatch.setattr(modulo, "PAUSA_TRA_MODIFICHE", 0)
    import types

    bot = types.SimpleNamespace(tree=None, wait_until_ready=AsyncMock())
    c = RuoliClassificaCog(bot=bot)
    yield c
    c.cog_unload()


def _comando(cog):
    return next(c for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None) if c.qualified_name == "admin-livelli classifica-ruoli")


def _scelta(v):
    s = MagicMock()
    s.value, s.name = v, str(v)
    return s


def _ruolo(rid, pos, membri=()):
    r = fake_role(role_id=rid, name=f"r{rid}")
    r.position = pos
    r.members = list(membri)
    r.managed = False
    r.is_default.return_value = False
    r.permissions = discord.Permissions.none()
    return r


@pytest.mark.asyncio
async def test_liv044_il_comando_chiede_il_permesso_e_la_gerarchia(cog):
    guild = fake_guild(GUILD, "Casa", owner_id=555)
    utente = fake_member(7)
    utente.top_role = _ruolo(1, 5)
    comando = _comando(cog)
    inter = fake_interaction(guild=guild, user=utente, permissions=discord.Permissions.none())
    await comando.callback(cog, inter, _scelta(1), _ruolo(50, 2))
    assert await modulo.leveling_ruoli_classifica_repo.elenco(GUILD) == {}
    inter2 = fake_interaction(guild=guild, user=utente, permissions=discord.Permissions(manage_guild=True))
    await comando.callback(cog, inter2, _scelta(1), _ruolo(51, 9))  # più alto di chi comanda
    assert await modulo.leveling_ruoli_classifica_repo.elenco(GUILD) == {}


@pytest.mark.asyncio
async def test_liv044_aggiorna_server_da_toglie_e_non_tocca_con_classifica_vuota(cog, monkeypatch):
    primo, secondo, vecchio = fake_member(1), fake_member(2), fake_member(3)
    for m in (primo, secondo, vecchio):
        m.add_roles, m.remove_roles = AsyncMock(), AsyncMock()
    r1, r3 = _ruolo(21, 1, [vecchio]), _ruolo(22, 1, [])
    guild = fake_guild(GUILD, "Casa")
    guild.get_member = lambda uid: {1: primo, 2: secondo, 3: vecchio}.get(uid)
    guild.get_role = lambda rid: {21: r1, 22: r3}.get(rid)
    guild.me = fake_member(999)
    guild.me.top_role = _ruolo(900, 50)
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)
    await modulo.leveling_ruoli_classifica_repo.imposta(GUILD, 1, 21)
    await modulo.leveling_ruoli_classifica_repo.imposta(GUILD, 3, 22)

    monkeypatch.setattr(leveling_repo, "top_xp_alltime", AsyncMock(return_value=[]))
    assert await cog.aggiorna_server(guild) == 0  # classifica vuota: nessuno perde niente
    vecchio.remove_roles.assert_not_awaited()

    monkeypatch.setattr(leveling_repo, "top_xp_alltime", AsyncMock(return_value=[
        LeaderboardEntry(1, 100), LeaderboardEntry(2, 50), LeaderboardEntry(77, 40)]))  # 77 non è nel server
    assert await cog.aggiorna_server(guild) == 3
    primo.add_roles.assert_awaited_once_with(r1, reason="Ruolo di classifica")
    secondo.add_roles.assert_awaited_once_with(r3, reason="Ruolo di classifica")
    vecchio.remove_roles.assert_awaited_once_with(r1, reason="Ruolo di classifica")


@pytest.mark.asyncio
async def test_liv044_senza_gestisci_ruoli_il_bot_non_prova(cog, monkeypatch):
    guild = fake_guild(GUILD, "Casa")
    guild.me = fake_member(999)
    guild.me.guild_permissions = discord.Permissions.none()
    await modulo.leveling_ruoli_classifica_repo.imposta(GUILD, 1, 21)
    leggi = AsyncMock()
    monkeypatch.setattr(leveling_repo, "top_xp_alltime", leggi)
    assert await cog.aggiorna_server(guild) == 0
    leggi.assert_not_awaited()
